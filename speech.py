"""
Speech processing pipeline for voice bot.

Handles bidirectional audio streaming between Twilio, Deepgram, and ElevenLabs.
Manages transcription, end-of-speech detection, and text-to-speech conversion.
"""
import asyncio
import audioop
import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Optional
import httpx
import miniaudio
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveOptions,
    LiveTranscriptionEvents,
)

from config import settings

log = logging.getLogger(__name__)


@dataclass
class SpeechEndSignal:
    """Signal indicating speech end detection status."""
    silence_duration: float
    has_final_transcript: bool
    transcript_text: str
    confidence: str


class AdaptiveEndOfSpeechDetector:
    """
    Detects when speaker has finished talking.
    
    Uses silence duration and transcript finality to determine
    speech end with varying confidence levels (low/medium/high/certain).
    """
    
    # Detection thresholds (class constants)
    MIN_SILENCE_WITH_FINAL = 1.5 
    MIN_SILENCE_NO_FINAL = 3.5    
    MAX_WAIT = 8.0                
    MEDIUM_CONFIDENCE_THRESHOLD = 1.0 
    
    def __init__(self) -> None:
        """Initialize detector with clean state."""
        self.last_speech_time = 0.0
        self.has_final_transcript = False
        self.current_transcript = ""
        
    def on_audio_received(self) -> None:
        """Update timestamp when audio is received."""
        self.last_speech_time = time.time()
    
    def on_transcript(self, text: str, is_final: bool) -> None:
        """
        Process transcript from Deepgram.
        
        Args:
            text: Transcribed text
            is_final: Whether Deepgram marked this as final
        """
        self.current_transcript = text
        if is_final:
            self.has_final_transcript = True
            log.debug("Final transcript: %s", text)
        else:
            log.debug("Partial transcript: %s", text)
    
    def get_silence_duration(self) -> float:
        """Calculate seconds of silence since last audio."""
        return time.time() - self.last_speech_time
    
    def is_speech_ended(self) -> SpeechEndSignal:
        """
        Check if speech has ended based on silence and transcript state.
        
        Returns:
            SpeechEndSignal with confidence level and metadata
        """
        silence = self.get_silence_duration()
        
        # High confidence: final transcript + sufficient silence
        if self.has_final_transcript and silence >= self.MIN_SILENCE_WITH_FINAL:
            return SpeechEndSignal(
                silence_duration=silence,
                has_final_transcript=True,
                transcript_text=self.current_transcript,
                confidence="certain",
            )
        
        # High confidence: long silence even without final
        if silence >= self.MIN_SILENCE_NO_FINAL:
            return SpeechEndSignal(
                silence_duration=silence,
                has_final_transcript=self.has_final_transcript,
                transcript_text=self.current_transcript,
                confidence="high",
            )
        
        # Medium confidence: moderate silence
        if silence >= self.MEDIUM_CONFIDENCE_THRESHOLD:
            return SpeechEndSignal(
                silence_duration=silence,
                has_final_transcript=self.has_final_transcript,
                transcript_text=self.current_transcript,
                confidence="medium",
            )
        
        # Low confidence: still speaking
        return SpeechEndSignal(
            silence_duration=silence,
            has_final_transcript=self.has_final_transcript,
            transcript_text=self.current_transcript,
            confidence="low",
        )
    
    def reset_for_new_turn(self) -> None:
        """Reset state for next conversation turn."""
        self.has_final_transcript = False
        self.current_transcript = ""


class SpeechPipeline:
    """
    Manages bidirectional audio streaming pipeline.
    
    Handles:
    - Audio streaming to Deepgram for transcription
    - End-of-speech detection
    - Text-to-speech via ElevenLabs
    - Audio encoding/decoding for Twilio
    """
    
    # Audio configuration constants
    SAMPLE_RATE = 8000
    CHANNELS = 1
    ENCODING = "mulaw"
    CHUNK_SIZE = 160
    AUDIO_BUFFER_DELAY = 2.0
    
    # Deepgram configuration
    DG_MODEL = "nova-2"
    DG_LANGUAGE = "en-US"
    DG_ENDPOINTING = 3000
    
    # Transcript validation
    MIN_TRANSCRIPT_LENGTH = 3
    
    # Detection timing
    SPEECH_END_CHECK_INTERVAL = 0.3
    
    def __init__(self) -> None:
        """Initialize speech pipeline with Deepgram client."""
        self._utterance_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=0)
        self._deepgram_connection = None
        self._closed = False
        self._is_speaking = False
        
        self.end_detector = AdaptiveEndOfSpeechDetector()

        self._dg_client = DeepgramClient(
            settings.deepgram_api_key,
            config=DeepgramClientOptions(options={"keepalive": "true"}),
        )

    async def listen(self) -> None:
        """
        Start listening for audio via Deepgram.
        
        Sets up WebSocket connection with event handlers for transcripts,
        errors, and connection closure.
        """
        self._deepgram_connection = self._dg_client.listen.asynclive.v("1")

        # Deepgram event handlers (nested functions with closure)
        async def on_transcript(self_dg, result, **kwargs):
            """Handle transcript events from Deepgram."""
            try:
                transcript = result.channel.alternatives[0].transcript
                is_final = result.is_final
                
                if transcript.strip():
                    self.end_detector.on_transcript(transcript, is_final)
                    
                    # Only queue substantial final transcripts
                    if is_final and len(transcript.strip()) > self.MIN_TRANSCRIPT_LENGTH:
                        log.debug("Deepgram final transcript: %s", transcript)
                        await self._wait_for_speech_end()
                        await self._utterance_queue.put(transcript)
                        
            except (AttributeError, IndexError) as exc:
                log.warning("Malformed Deepgram event: %s", exc)

        async def on_error(self_dg, error, **kwargs):
            """Handle error events from Deepgram."""
            log.error("Deepgram error: %s", error)

        async def on_close(self_dg, close, **kwargs):
            """Handle connection close events."""
            log.info("Deepgram connection closed")
            await self._utterance_queue.put(None)

        # Registering event handlers
        self._deepgram_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
        self._deepgram_connection.on(LiveTranscriptionEvents.Error, on_error)
        self._deepgram_connection.on(LiveTranscriptionEvents.Close, on_close)

        # Configuring Deepgram options
        options = LiveOptions(
            model=self.DG_MODEL,
            language=self.DG_LANGUAGE,
            encoding=self.ENCODING,
            sample_rate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            punctuate=True,
            endpointing=self.DG_ENDPOINTING,
            interim_results=True,
        )
        
        await self._deepgram_connection.start(options)
    
    async def _wait_for_speech_end(self) -> None:
        """
        Wait for speech to end based on adaptive detection.
        
        Polls end detector until high/certain confidence or timeout.
        """
        max_wait = self.end_detector.MAX_WAIT
        wait_start = time.time()
        
        while time.time() - wait_start < max_wait:
            signal = self.end_detector.is_speech_ended()
            
            if signal.confidence in ["high", "certain"]:
                log.info(
                    "Speech ended (%s, %.1fs silence)",
                    signal.confidence,
                    signal.silence_duration,
                )
                return
            
            await asyncio.sleep(self.SPEECH_END_CHECK_INTERVAL)
        
        log.warning("Max wait exceeded - responding anyway")

    async def feed_audio(self, mulaw_bytes: bytes) -> None:
        """
        Feed audio to Deepgram (only when not speaking).
        
        Args:
            mulaw_bytes: Raw mulaw-encoded audio from Twilio
        """
        if self._deepgram_connection and not self._closed and not self._is_speaking:
            self.end_detector.on_audio_received()
            await self._deepgram_connection.send(mulaw_bytes)

    async def utterances(self) -> AsyncGenerator[str, None]:
        """
        Async generator yielding complete user utterances.
        
        Yields:
            Transcribed text from Deepgram
        """
        while True:
            item = await self._utterance_queue.get()
            if item is None:
                break
            yield item

    async def speak(
        self,
        text: str,
        websocket,
        stream_sid: Optional[str],
    ) -> None:
        """
        Convert text to speech and send to Twilio.
        
        Args:
            text: Text to speak
            websocket: WebSocket connection to Twilio
            stream_sid: Twilio stream identifier
        """
        if not text.strip():
            return

        self._is_speaking = True
        log.info("Speaking to stream_sid: %s, text: %s...", stream_sid, text[:50])

        try:
            # Getting TTS audio from ElevenLabs
            mp3_bytes = await self._elevenlabs_tts(text)
            log.info("TTS returned %d bytes", len(mp3_bytes))

            # Decoding MP3 to PCM
            decoded = miniaudio.decode(
                mp3_bytes,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=self.CHANNELS,
                sample_rate=self.SAMPLE_RATE,
            )
            raw_pcm = bytes(decoded.samples)

            # Ensuring even number of bytes for 16-bit samples
            if len(raw_pcm) % 2 != 0:
                raw_pcm = raw_pcm[:-1]

            # Converting to mulaw for Twilio
            audio_mulaw = audioop.lin2ulaw(raw_pcm, 2)
            log.info("Converted to %d mulaw bytes", len(audio_mulaw))

            # Sending in chunks to Twilio
            for i in range(0, len(audio_mulaw), self.CHUNK_SIZE):
                chunk = audio_mulaw[i : i + self.CHUNK_SIZE]
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

        except (httpx.HTTPError, miniaudio.DecodeError, ValueError) as exc:
            log.error("TTS/decode failed: %s", exc)

        finally:
            # Waiting for audio playback to complete
            await asyncio.sleep(self.AUDIO_BUFFER_DELAY)
            self._is_speaking = False
            self.end_detector.reset_for_new_turn()

    async def _elevenlabs_tts(self, text: str) -> bytes:
        """
        Convert text to speech using ElevenLabs API.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            MP3 audio bytes
            
        Raises:
            httpx.HTTPError: If API request fails
        """
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

    async def close(self) -> None:
        """Clean up resources and close Deepgram connection."""
        self._closed = True
        if self._deepgram_connection:
            try:
                await self._deepgram_connection.finish()
            except Exception as exc:
                log.warning("Error closing Deepgram connection: %s", exc)