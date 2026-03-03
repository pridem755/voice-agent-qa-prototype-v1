import asyncio
import base64
import json
import logging
import hmac
import hashlib
from typing import Optional
from pathlib import Path
from urllib.parse import urlencode
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Form
from fastapi.responses import Response
from config import settings
from patient_brain import PatientBrain
from speech import SpeechPipeline
from call_recorder import CallRecorder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)
app = FastAPI(title="Voice Bot — Twilio Bridge", version="1.0.0")


def validate_twilio_request(url: str, params: dict, signature: str) -> bool:
    """
    Validating Twilio webhook signature.
    
    Args:
        url: The full URL Twilio called (scheme + host + path)
        params: Form parameters from request
        signature: X-Twilio-Signature header value
    Returns:
        True if signature is valid or validation is disabled
    """
    if not settings.twilio_auth_token:
        log.warning("Twilio signature validation disabled (no auth token)")
        return True
    
    if not signature:
        return False
    
    # Building the signature string: URL + sorted params
    sorted_params = sorted(params.items())
    data_to_sign = url + ''.join(f"{k}{v}" for k, v in sorted_params)
    
    # Computing HMAC-SHA1 and base64 encode
    expected = base64.b64encode(
        hmac.new(
            settings.twilio_auth_token.encode('utf-8'),
            data_to_sign.encode('utf-8'),
            hashlib.sha1
        ).digest()
    ).decode('utf-8')
    return hmac.compare_digest(signature, expected)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok"}


@app.post("/incoming")
async def incoming_call(
    request: Request,
    From: str = Form(...),
    To: str = Form(...),
    CallSid: str = Form(...),
):
    """
    Handling incoming call from Twilio.
    
    Returns TwiML instructing Twilio to connect to WebSocket stream.
    Validates Twilio signature for security.
    
    """
    # Validating signature if configured
    signature = request.headers.get("X-Twilio-Signature", "")
    
    scheme = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    host = request.headers.get("X-Forwarded-Host", request.url.netloc)
    path = request.url.path
    full_url = f"{scheme}://{host}{path}"
    
    # Getting all form params
    form_data = await request.form()
    params = dict(form_data)
    
    if not validate_twilio_request(full_url, params, signature):
        log.error("Invalid Twilio signature - potential security issue")
        log.debug("URL: %s, Params: %s, Signature: %s", full_url, params, signature)
        raise HTTPException(status_code=403, detail="Invalid signature")

    log.info("Incoming call: From=%s, To=%s, CallSid=%s", From, To, CallSid)
    ws_url = f"wss://{settings.public_host}/media-stream"
    log.info("Streaming to %s", ws_url)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="text/xml")


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """
    Handling bidirectional audio streaming via WebSocket.
    
    """
    await websocket.accept()
    log.info("WebSocket accepted, waiting for stream start")

    # Session state
    stream_sid: Optional[str] = None
    
    # Coordination primitives
    stream_sid_ready = asyncio.Event()
    deepgram_ready = asyncio.Event()
    shutdown_requested = asyncio.Event()
    
    # Task tracking
    tasks = []

    # Loading current scenario
    try:
        scenario = json.loads(Path("current_scenario.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        log.warning("Cannot load current_scenario.json (%s), using fallback", exc)
        scenario = {
            "name": "fallback",
            "persona": "A patient who wants to call.",
            "goal": "Patient calling for assistance.",
        }
    log.info("Running scenario: %s", scenario.get("name"))

    # Initializing per-call components
    brain = PatientBrain(scenario=scenario)
    speech = SpeechPipeline()
    recorder = CallRecorder(scenario_name=scenario.get("name", "unknown"))

    async def deepgram_startup():
        """
        Starting Deepgram connection and verify it's working.
        
        Sets deepgram_ready only after connection is established.
        """
        try:
            await speech.listen()
            
            # Verifying connection is actually established
            await asyncio.sleep(0.2)
            
            if speech._deepgram_connection is None:
                log.error("Deepgram connection is None after listen()")
                shutdown_requested.set()
                return
            
            deepgram_ready.set()
            log.info("Deepgram connection established and ready")
            await shutdown_requested.wait()
            
        except Exception as exc:
            log.error("Failed to establish Deepgram connection: %s", exc, exc_info=True)
            shutdown_requested.set()

    async def receive_loop():
        """
        Receiving audio from Twilio and feed to speech pipeline.
    
        """
        nonlocal stream_sid
        deepgram_wait_logged = False
        
        try:
            async for raw_text in websocket.iter_text():
                if shutdown_requested.is_set():
                    break
                
                # Parsing message defensively
                try:
                    message = json.loads(raw_text)
                except json.JSONDecodeError as exc:
                    log.warning("Malformed JSON from Twilio: %s", exc)
                    continue
                
                event_type = message.get("event")
                
                if event_type == "start":
                    try:
                        stream_sid = message["start"]["streamSid"]
                        log.info("Media stream started - SID: %s", stream_sid)
                        stream_sid_ready.set()
                    except KeyError as exc:
                        log.error("Malformed start event: %s", exc)
                        shutdown_requested.set()
                        break

                elif event_type == "media":
                    # Waiting for Deepgram to be ready
                    if not deepgram_ready.is_set():
                        if not deepgram_wait_logged:
                            log.info("Waiting for Deepgram connection...")
                            deepgram_wait_logged = True
                        
                        try:
                            await asyncio.wait_for(deepgram_ready.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            log.error("Deepgram not ready after 5s - shutting down")
                            shutdown_requested.set()
                            break
                    
                    try:
                        audio_bytes = base64.b64decode(message["media"]["payload"])
                        await speech.feed_audio(audio_bytes)
                    except (KeyError, base64.binascii.Error) as exc:
                        log.warning("Malformed media event: %s", exc)
                        continue
                    except Exception as exc:
                        log.error("Error feeding audio: %s", exc)
                        shutdown_requested.set()
                        break

                elif event_type == "stop":
                    log.info("Twilio sent stop event - ending call")
                    shutdown_requested.set()
                    break

        except WebSocketDisconnect:
            log.info("WebSocket disconnected by Twilio")
            shutdown_requested.set()
        except Exception as exc:
            log.error("Error in receive loop: %s", exc, exc_info=True)
            shutdown_requested.set()
        finally:
            log.debug("receive_loop exiting")

    async def brain_loop():
        """
        Processing transcripts and generate patient responses.
        
        """
        try:
            # Waiting for prerequisites with timeout
            try:
                await asyncio.wait_for(stream_sid_ready.wait(), timeout=10.0)
                await asyncio.wait_for(deepgram_ready.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                log.error("Timeout waiting for stream initialization")
                shutdown_requested.set()
                return

            async for agent_text in speech.utterances():
                if shutdown_requested.is_set():
                    log.debug("brain_loop received shutdown signal")
                    break
                    
                agent_text = agent_text.strip()
                if not agent_text:
                    continue

                log.info("[Agent] %s", agent_text)
                recorder.add_turn(speaker="agent", text=agent_text)

                # Generating patient response with timeout
                try:
                    patient_reply = await asyncio.wait_for(
                        brain.respond(agent_text),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    log.error("Timeout waiting for brain - LLM stalled")
                    patient_reply = "I'm sorry, could you repeat that?"
                except Exception as exc:
                    log.error("Error generating response: %s", exc, exc_info=True)
                    patient_reply = "I'm having trouble understanding. Can you try again?"

                log.info("[Patient] %s", patient_reply)
                
                # Sending patient's reply back to Twilio
                try:
                    await speech.speak(
                        text=patient_reply,
                        websocket=websocket,
                        stream_sid=stream_sid,
                    )
                    recorder.add_turn(speaker="patient", text=patient_reply)
                    
                except Exception as exc:
                    log.error("Error sending speech: %s", exc, exc_info=True)
                    shutdown_requested.set()
                    break

                # Checking if patient brain signaled end of call
                if brain.should_hang_up():
                    log.info("Patient brain signaled end of call")
                    shutdown_requested.set()
                    break
                    
        except Exception as exc:
            log.error("Error in brain loop: %s", exc, exc_info=True)
            shutdown_requested.set()
        finally:
            log.debug("brain_loop exiting")

    async def shutdown_coordinator():
        """
        Coordinating clean shutdown when shutdown_requested is set.
        
        """
        await shutdown_requested.wait()
        log.info("Shutdown coordinator activated")
        
        try:
            # Closing speech pipeline 
            await speech.close()
        except Exception as exc:
            log.debug("Error closing speech pipeline : %s", exc)

        await asyncio.sleep(0.3)

    # Create tasks
    tasks = [
        asyncio.create_task(deepgram_startup(), name="deepgram"),
        asyncio.create_task(receive_loop(), name="receive"),
        asyncio.create_task(brain_loop(), name="brain"),
        asyncio.create_task(shutdown_coordinator(), name="shutdown"),
    ]
    
    try:
        # Waiting for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
        for task, result in zip(tasks, results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                log.error(
                    "Task %s raised exception: %s",
                    task.get_name(),
                    result,
                    exc_info=result
                )
                
    except Exception as exc:
        log.error("Session error: %s", exc, exc_info=True)
    finally:
        # Ensure shutdown is requested
        shutdown_requested.set()
        
        # Cancel any still-running tasks
        for task in tasks:
            if not task.done():
                log.debug("Cancelling task: %s", task.get_name())
                task.cancel()
        
        # Wait for cancellation to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Ensuring speech pipeline is closed (idempotent)
        try:
            if not speech._closed:
                await speech.close()
        except Exception as exc:
            log.debug("Speech close in finally: %s", exc)
        
        # Save transcript
        try:
            path = recorder.save()
            log.info("Transcript written - %s", path)
        except Exception as exc:
            log.error("Error saving transcript: %s", exc)
        
        # Close WebSocket if still open
        try:
            await websocket.close()
        except Exception:
            pass  
        log.info("Session cleanup complete")


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=settings.server_port,
        reload=False,
        log_level="info",
    )