import asyncio
import base64
import json
import logging
from typing import Optional
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from config import settings
from patient_brain import PatientBrain
from speech import SpeechPipeline
from call_recorder import CallRecorder

#------Logging ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

#-------FastAPI application------------------------------------------------------------
app = FastAPI(title="Voice Bot — Twilio Bridge", version="1.0.0")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/incoming")
async def incoming_call(request: Request) -> Response:
    ws_url = f"wss://{settings.public_host}/media-stream"
    log.info("Incoming call answered — streaming to %s", ws_url)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="text/xml")

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    log.info("WebSocket accepted — waiting for stream start")

    stream_sid: Optional[str] = None

    #-------Load current scenario------------------------------------------------
    try:
        with open("current_scenario.json") as fh:
            scenario = json.load(fh)
    except FileNotFoundError:
        log.warning("current_scenario.json not found — using fallback scenario")
        scenario = {
            "name": "fallback",
            "persona": "A patient who wants to schedule a routine check-up.",
            "goal": "Schedule an appointment for next week.",
        }

    log.info("Running scenario: %s", scenario.get("name"))

    #-------Per-call component initialisation--------------------------------------
    brain = PatientBrain(scenario=scenario)
    speech = SpeechPipeline()
    recorder = CallRecorder(scenario_name=scenario.get("name", "unknown"))

    #-------Coroutines-------------------------------------------------------------
    async def receive_loop():
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

    async def brain_loop():
        # Wait for stream_sid to be set by receive_loop
        while stream_sid is None:
            await asyncio.sleep(0.1)

        # Patient speaks first when call connects
        opening = await brain.respond("Hello?")
        log.info("[Patient] %s", opening)
        recorder.add_turn(speaker="patient", text=opening)
        await speech.speak(text=opening, websocket=websocket, stream_sid=stream_sid)

        async for agent_text in speech.utterances():
            agent_text = agent_text.strip()
            if not agent_text:
                continue

            log.info("[Agent] %s", agent_text)
            recorder.add_turn(speaker="agent", text=agent_text)

            # GPT-4o plays the patient
            patient_reply = await brain.respond(agent_text)
            log.info("[Patient] %s", patient_reply)
            recorder.add_turn(speaker="patient", text=patient_reply)

            # Send the patient's reply back to Twilio to be spoken aloud
            await speech.speak(
                text=patient_reply,
                websocket=websocket,
                stream_sid=stream_sid,
            )

            # Check if the brain has signalled to end the call
            if brain.should_hang_up():
                log.info("Patient brain signalled end of call — closing")
                await websocket.close()
                break

    #-------Run all coroutines concurrently--------------------------------------
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


#------Standalone entry point----------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=settings.server_port,
        reload=False,
        log_level="info",
    )
