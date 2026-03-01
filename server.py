"""
FastAPI server - Twilio webhook handler and WebSocket bridge.

Handles incoming calls from Twilio, manages bidirectional audio streaming,
orchestrates agent-patient conversation via speech pipeline and patient brain.
"""
import asyncio
import base64
import json
import logging
from typing import Optional
from pathlib import Path
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
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


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok"}


@app.post("/incoming")
async def incoming_call(request: Request) -> Response:
    """
    Handle incoming call from Twilio.
    
    Returns TwiML instructing Twilio to connect to WebSocket stream.
    """
    ws_url = f"wss://{settings.public_host}/media-stream"
    log.info("Incoming call answered, streaming to %s", ws_url)

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
    Handle bidirectional audio streaming via WebSocket.
    
    Manages conversation between Twilio (agent audio) and patient brain,
    with speech-to-text and text-to-speech processing.
    """
    await websocket.accept()
    log.info("WebSocket accepted, waiting for stream start")

    stream_sid: Optional[str] = None

    # Loading current scenario
    try:
        scenario = json.loads(Path("current_scenario.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        log.warning("Cannot load current_scenario.json (%s), using fallback", exc)
        scenario = {
            "name": "fallback",
            "persona": "A patient who wants to schedule a routine check-up.",
            "goal": "Schedule an appointment for next week.",
        }

    log.info("Running scenario: %s", scenario.get("name"))

    # Initializing per-call components
    brain = PatientBrain(scenario=scenario)
    speech = SpeechPipeline()
    recorder = CallRecorder(scenario_name=scenario.get("name", "unknown"))

    async def receive_loop():
        """Receive audio from Twilio and feed to speech pipeline."""
        nonlocal stream_sid
        try:
            async for raw_text in websocket.iter_text():
                message = json.loads(raw_text)
                event_type = message.get("event")

                if event_type == "start":
                    stream_sid = message["start"]["streamSid"]
                    log.info("Media stream started — SID: %s", stream_sid)

                elif event_type == "media":
                    audio_bytes = base64.b64decode(message["media"]["payload"])
                    await speech.feed_audio(audio_bytes)

                elif event_type == "stop":
                    log.info("Twilio sent stop event — ending call")
                    break

        except WebSocketDisconnect:
            log.info("WebSocket disconnected by Twilio")
        except Exception as exc:
            log.error("Error in receive loop: %s", exc)

    async def brain_loop():
        """Process transcripts and generate patient responses."""
        # Waiting for stream_sid to be set by receive_loop
        while stream_sid is None:
            await asyncio.sleep(0.1)

        try:
            async for agent_text in speech.utterances():
                agent_text = agent_text.strip()
                if not agent_text:
                    continue

                log.info("[Agent] %s", agent_text)
                recorder.add_turn(speaker="agent", text=agent_text)

                # Generating patient response via GPT-4
                patient_reply = await brain.respond(agent_text)
                log.info("[Patient] %s", patient_reply)
                recorder.add_turn(speaker="patient", text=patient_reply)

                # Sending patient's reply back to Twilio
                await speech.speak(
                    text=patient_reply,
                    websocket=websocket,
                    stream_sid=stream_sid,
                )

                # Checking if patient brain signaled end of call
                if brain.should_hang_up():
                    log.info("Patient brain signaled end of call — closing")
                    await websocket.close()
                    break
        except Exception as exc:
            log.error("Error in brain loop: %s", exc)

    # Running all coroutines concurrently
    try:
        await asyncio.gather(
            receive_loop(),
            brain_loop(),
            speech.listen(),
        )
    except Exception as exc:
        log.error("Session error: %s", exc, exc_info=True)
    finally:
        path = recorder.save()
        log.info("Transcript written → %s", path)
        await speech.close()


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=settings.server_port,
        reload=False,
        log_level="info",
    )
