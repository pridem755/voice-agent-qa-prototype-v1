import asyncio
import audioop
import base64
import json
import logging
import time
from typing import AsyncGenerator, Optional
from dataclasses import dataclass
import httpx
import miniaudio
from deepgram import DeepgramClient, DeepgramClientOptions, LiveOptions, LiveTranscriptionEvents
from config import settings

log = logging.getLogger(__name__)

#-----------------------------------------------------------------------
#This module handles the speech processing pipeline: by receiving audio from Twilio, sending it to Deepgram for transcription, and sending TTS responses back to Twilio. 
#-------------------------------------------------------------------------
@dataclass
class SpeechEndSignal:
    silence_duration: float
    has_final_transcript: bool
    transcript_text: str
    confidence: str
#adaptive algorithm to determine when the user has finished speaking
class AdaptiveEndOfSpeechDetector:
    def __init__(self):
        self.MIN_SILENCE_WITH_FINAL = 1.5
        self.MIN_SILENCE_NO_FINAL = 3.5
        self.MAX_WAIT = 8.0
        
        self.last_speech_time = 0
        self.last_final_transcript_time = 0
        self.has_final_transcript = False
        self.current_transcript = ""
        
    def on_audio_received(self):
        self.last_speech_time = time.time()
    
    def on_transcript(self, text: str, is_final: bool):
        self.current_transcript = text
        if is_final:
            self.has_final_transcript = True
            self.last_final_transcript_time = time.time()
            log.debug(f"Final transcript: {text}")
        else:
            log.debug(f"Partial transcript: {text}")
    
    def get_silence_duration(self) -> float:
        return time.time() - self.last_speech_time
    
    def is_speech_ended(self) -> SpeechEndSignal:
        silence = self.get_silence_duration()
        if self.has_final_transcript and silence >= self.MIN_SILENCE_WITH_FINAL:
            return SpeechEndSignal(
                silence_duration=silence,
                has_final_transcript=True,
                transcript_text=self.current_transcript,
                confidence="certain"
            )
        
        if silence >= self.MIN_SILENCE_NO_FINAL:
            return SpeechEndSignal(
                silence_duration=silence,
                has_final_transcript=self.has_final_transcript,
                transcript_text=self.current_transcript,
                confidence="high"
            )
        
        if silence >= 1.0:
            return SpeechEndSignal(
                silence_duration=silence,
                has_final_transcript=self.has_final_transcript,
                transcript_text=self.current_transcript,
                confidence="medium"
            )
        
        return SpeechEndSignal(
            silence_duration=silence,
            has_final_transcript=self.has_final_transcript,
            transcript_text=self.current_transcript,
            confidence="low"
        )
    
    def reset_for_new_turn(self):
        self.has_final_transcript = False
        self.current_transcript = ""


class SpeechPipeline:
    def __init__(self):
        self._utterance_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=0)
        self._deepgram_connection = None
        self._closed = False
        self._is_speaking = False 
        
        self.end_detector = AdaptiveEndOfSpeechDetector()

        self._dg_client = DeepgramClient(
            settings.deepgram_api_key,
            config=DeepgramClientOptions(options={"keepalive": "true"}),
        )

    async def listen(self):
        self._deepgram_connection = self._dg_client.listen.asynclive.v("1")

        async def on_transcript(self_dg, result, **kwargs):
            try:
                transcript = result.channel.alternatives[0].transcript
                is_final = result.is_final
                
                if transcript.strip():
                    self.end_detector.on_transcript(transcript, is_final)
                    
                    if is_final and len(transcript.strip()) > 3:
                        log.debug("Deepgram final transcript: %s", transcript)
                        await self._wait_for_speech_end()
                        await self._utterance_queue.put(transcript)
                        
            except (AttributeError, IndexError) as exc:
                log.warning("Malformed Deepgram event: %s", exc)

        async def on_error(self_dg, error, **kwargs):
            log.error("Deepgram error: %s", error)

        async def on_close(self_dg, close, **kwargs):
            log.info("Deepgram connection closed")
            await self._utterance_queue.put(None)

        self._deepgram_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
        self._deepgram_connection.on(LiveTranscriptionEvents.Error, on_error)
        self._deepgram_connection.on(LiveTranscriptionEvents.Close, on_close)

        options = LiveOptions(
            model="nova-2",
            language="en-US",
            encoding="mulaw",
            sample_rate=8000,
            channels=1,
            punctuate=True,
            endpointing=3000,
            interim_results=True,
        )
        
        await self._deepgram_connection.start(options)
    
    async def _wait_for_speech_end(self):
        max_wait = self.end_detector.MAX_WAIT
        check_interval = 0.3
        wait_start = time.time()
        
        while time.time() - wait_start < max_wait:
            signal = self.end_detector.is_speech_ended()
            
            if signal.confidence in ["high", "certain"]:
                log.info(f"Speech ended ({signal.confidence}, {signal.silence_duration:.1f}s)")
                return
            
            await asyncio.sleep(check_interval)
        
        log.warning("Max wait exceeded - responding anyway")

    async def feed_audio(self, mulaw_bytes: bytes):
        if self._deepgram_connection and not self._closed and not self._is_speaking:
            self.end_detector.on_audio_received()
            await self._deepgram_connection.send(mulaw_bytes)

    async def utterances(self) -> AsyncGenerator[str, None]:
        while True:
            item = await self._utterance_queue.get()
            if item is None:
                break
            yield item

    async def speak(self, text: str, websocket, stream_sid: Optional[str]):
        if not text.strip():
            return

        self._is_speaking = True
        log.info(f"Speaking to stream_sid: {stream_sid}, text: {text[:50]}")

        try:
            mp3_bytes = await self._elevenlabs_tts(text)
            log.info(f"TTS returned {len(mp3_bytes)} bytes, first 4: {mp3_bytes[:4]}")

            decoded = miniaudio.decode(
                mp3_bytes,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=1,
                sample_rate=8000,
            )
            raw_pcm = bytes(decoded.samples)

            if len(raw_pcm) % 2 != 0:
                raw_pcm = raw_pcm[:-1]

            audio_mulaw = audioop.lin2ulaw(raw_pcm, 2)
            log.info(f"Converted to {len(audio_mulaw)} mulaw bytes")

            chunk_size = 160
            for i in range(0, len(audio_mulaw), chunk_size):
                chunk = audio_mulaw[i : i + chunk_size]
                payload = base64.b64encode(chunk).decode("utf-8")
                message = json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload},
                })
                try:
                    await websocket.send_text(message)
                except Exception as exc:
                    log.warning("Failed to send audio chunk: %s", exc)
                    break

            log.debug("Spoke %d chars, %d mulaw bytes", len(text), len(audio_mulaw))

        except Exception as exc:
            log.error("TTS/decode failed: %s", exc)

        finally:
            await asyncio.sleep(2.0) 
            self._is_speaking = False
            self.end_detector.reset_for_new_turn()

    async def _elevenlabs_tts(self, text: str) -> bytes:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.content

    async def close(self):
        self._closed = True
        if self._deepgram_connection:
            try:
                await self._deepgram_connection.finish()
            except Exception as exc:
                log.warning("Error closing Deepgram connection: %s", exc)