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
import webrtcvad
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
    post_hangover_silence: float
    has_final_transcript: bool
    transcript_text: str
    confidence: str


class AdaptiveEndOfSpeechDetector:
    """
    Detecting when speaker has finished talking using VAD.
    
    """
    
    # Detection thresholds
    MAX_WAIT = 10.0
    
    def __init__(self) -> None:
        """Initializing detector with VAD and clean state."""
        # Transcript state
        self.has_final_transcript = False
        self.current_transcript = ""
        
        # VAD configuration for 8kHz telephony
        self.vad = webrtcvad.Vad(2)  
        self.frame_duration_ms = 20
        self.frame_size = int(8000 * self.frame_duration_ms / 1000) * 2  
        
        # VAD state tracking
        self.pcm_buffer = bytearray()
        self.consecutive_silence_frames = 0
        
        # Hangover configuration
        self.hangover_frames = int(250 / self.frame_duration_ms)  
        
        # Post-hangover silence threshold
        self.post_hangover_silence_frames = int(1200 / self.frame_duration_ms)  
        
        # Timing
        self.post_hangover_silence_start = None
        self.last_speech_time = None  
    
    def process_vad_frame(self, mulaw_bytes: bytes) -> None:
        """Processing audio through VAD to detect speech vs silence."""
        try:
            pcm_bytes = audioop.ulaw2lin(mulaw_bytes, 2)
        except Exception as exc:
            log.debug("Failed to convert mulaw: %s", exc)
            return
        
        self.pcm_buffer.extend(pcm_bytes)
        
        while len(self.pcm_buffer) >= self.frame_size:
            frame = bytes(self.pcm_buffer[:self.frame_size])
            self.pcm_buffer = self.pcm_buffer[self.frame_size:]
            
            try:
                is_speech = self.vad.is_speech(frame, 8000)
            except Exception as exc:
                log.debug("VAD error: %s", exc)
                continue
            
            if is_speech:
                self.consecutive_silence_frames = 0
                self.post_hangover_silence_start = None
                self.last_speech_time = time.time() 
            else:
                self.consecutive_silence_frames += 1
                
                if self.consecutive_silence_frames > self.hangover_frames:
                    if self.post_hangover_silence_start is None:
                        self.post_hangover_silence_start = time.time()
    
    def on_transcript(self, text: str, is_final: bool) -> None:
        """Processing transcript from Deepgram."""
        self.current_transcript = text
        
        if is_final:
            self.has_final_transcript = True
            log.debug("Final: %s", text)
        else:
            log.debug("Partial: %s", text)
    
    def speech_detected_recently(self, threshold_seconds: float = 0.5) -> bool:
        """
        Check if speech was detected recently (for barge-in detection).
        
        Args:
            threshold_seconds: How recently to consider as "recent" (default 0.5s)
        Returns:
            True if speech detected within threshold
        """
        if self.last_speech_time is None:
            return False
        return (time.time() - self.last_speech_time) < threshold_seconds
    
    def get_post_hangover_silence(self) -> float:
        """Getting duration of silence AFTER hangover period."""
        if self.post_hangover_silence_start is None:
            return 0.0
        return time.time() - self.post_hangover_silence_start
    
    def is_in_hangover(self) -> bool:
        """Checking if currently in hangover period."""
        return 0 < self.consecutive_silence_frames <= self.hangover_frames
    
    def get_post_hangover_frames(self) -> int:
        """Getting number of silence frames AFTER hangover."""
        if self.consecutive_silence_frames <= self.hangover_frames:
            return 0
        return self.consecutive_silence_frames - self.hangover_frames
    
    def is_speech_ended(self) -> SpeechEndSignal:
        """Checking if speech has ended based on current VAD state."""
        post_hangover_silence = self.get_post_hangover_silence()
        post_hangover_frames = self.get_post_hangover_frames()
        
        if self.is_in_hangover():
            return SpeechEndSignal(
                post_hangover_silence=0.0,
                has_final_transcript=self.has_final_transcript,
                transcript_text=self.current_transcript,
                confidence="low",
            )
        
        silence_threshold_met = post_hangover_frames >= self.post_hangover_silence_frames
        
        if self.has_final_transcript and silence_threshold_met:
            return SpeechEndSignal(
                post_hangover_silence=post_hangover_silence,
                has_final_transcript=True,
                transcript_text=self.current_transcript,
                confidence="high",
            )

        if silence_threshold_met and self.current_transcript.strip():
            return SpeechEndSignal(
                post_hangover_silence=post_hangover_silence,
                has_final_transcript=False,
                transcript_text=self.current_transcript,
                confidence="medium",
            )
        
        return SpeechEndSignal(
            post_hangover_silence=post_hangover_silence,
            has_final_transcript=self.has_final_transcript,
            transcript_text=self.current_transcript,
            confidence="low",
        )
    
    def reset_for_new_turn(self) -> None:
        """Resetting state for next conversation turn."""
        self.has_final_transcript = False
        self.current_transcript = ""
        self.consecutive_silence_frames = 0
        self.post_hangover_silence_start = None
        self.last_speech_time = None
        self.pcm_buffer.clear()

class SpeechPipeline:
    """Managing bidirectional audio streaming pipeline."""
    
    # Audio configuration
    SAMPLE_RATE = 8000
    CHANNELS = 1
    ENCODING = "mulaw"
    CHUNK_SIZE = 160
    AUDIO_BUFFER_DELAY = 1.5
    
    # Deepgram configuration
    DG_MODEL = "nova-2"
    DG_LANGUAGE = "en-US"
    DG_ENDPOINTING = 1500
    
    # Transcript validation
    MIN_TRANSCRIPT_LENGTH = 3
    
    # Detection timing
    SPEECH_END_CHECK_INTERVAL = 0.1
    
    # Operational limits
    MAX_QUEUE_SIZE = 10
    DEEPGRAM_SEND_TIMEOUT = 1.0
    
    def __init__(self) -> None:
        """Initializing speech pipeline."""
        self._utterance_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._deepgram_connection = None
        self._closed = False
        self._is_speaking = False
        
        # Single-flight guard for queueing 
        self._queue_lock = asyncio.Lock()
        self._latest_queue_id = -1  
        self._next_queue_id = 0  
        
        # Single active wait task
        self._active_wait_task: Optional[asyncio.Task] = None
        
        # Fallback monitor
        self._monitor_task: Optional[asyncio.Task] = None
        self._last_partial_check = 0.0
        
        # Barge-in tracking
        self._tts_started_at = None
        self.end_detector = AdaptiveEndOfSpeechDetector()
        self._dg_client = DeepgramClient(
            settings.deepgram_api_key,
            config=DeepgramClientOptions(options={"keepalive": "true"}),
        )

    async def listen(self) -> None:
        """Starting listening for audio via Deepgram."""
        self._deepgram_connection = self._dg_client.listen.asynclive.v("1")

        async def on_transcript(self_dg, result, **kwargs):
            """Handling transcript events from Deepgram."""
            try:
                transcript = result.channel.alternatives[0].transcript
                is_final = result.is_final
                
                if not transcript.strip():
                    return
                
                # Update detector state
                self.end_detector.on_transcript(transcript, is_final)
                
                # Trigger wait on substantial final transcripts
                if is_final and len(transcript.strip()) > self.MIN_TRANSCRIPT_LENGTH:
                    # Cancel previous wait (non-blocking)
                    if self._active_wait_task and not self._active_wait_task.done():
                        self._active_wait_task.cancel()
                    
                    log.debug("Final: %s - starting wait", transcript)
                    
                    # Generate unique ID for this queue attempt
                    queue_id = self._next_queue_id
                    self._next_queue_id += 1
                    
                    # Start new wait with frozen transcript and ID
                    self._active_wait_task = asyncio.create_task(
                        self._wait_and_queue_utterance(transcript, queue_id)
                    )
                        
            except (AttributeError, IndexError) as exc:
                log.warning("Malformed Deepgram event: %s", exc)

        async def on_error(self_dg, error, **kwargs):
            """Handling error events from Deepgram."""
            log.error("Deepgram error: %s", error)

        async def on_close(self_dg, close, **kwargs):
            """Handling connection close events."""
            log.info("Deepgram connection closed")
            
            # Cancel background tasks
            if self._active_wait_task:
                self._active_wait_task.cancel()
            if self._monitor_task:
                self._monitor_task.cancel()
            
            # Signal shutdown (non-blocking)
            try:
                self._utterance_queue.put_nowait(None)
            except asyncio.QueueFull:
                log.warning("Queue full during shutdown, draining...")

        # Register handlers
        self._deepgram_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
        self._deepgram_connection.on(LiveTranscriptionEvents.Error, on_error)
        self._deepgram_connection.on(LiveTranscriptionEvents.Close, on_close)

        # Configure Deepgram
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
        
        # Start fallback monitor
        self._monitor_task = asyncio.create_task(self._monitor_partial_transcripts())
    
    async def _monitor_partial_transcripts(self) -> None:
        """Monitoring for Deepgram stalls - trigger fallback if VAD says done but no final."""
        try:
            while not self._closed:
                await asyncio.sleep(1.0)
                
                # Skip if recently checked, speaking, or already waiting
                now = time.time()
                if (now - self._last_partial_check < 2.0 or 
                    self._is_speaking or 
                    (self._active_wait_task and not self._active_wait_task.done())):
                    continue
                
                signal = self.end_detector.is_speech_ended()
                
                if signal.confidence == "medium" and signal.transcript_text.strip():
                    self._last_partial_check = now
                    
                    log.info("Fallback: Deepgram stalled, using partial '%s'", signal.transcript_text[:30])
                    
                    queue_id = self._next_queue_id
                    self._next_queue_id += 1
                    
                    self._active_wait_task = asyncio.create_task(
                        self._wait_and_queue_utterance(signal.transcript_text, queue_id)
                    )
                        
        except asyncio.CancelledError:
            log.debug("Monitor cancelled")
    
    async def _wait_and_queue_utterance(self, utterance_snapshot: str, queue_id: int) -> None:
        """
        Waiting for VAD confirmation and queue the utterance (single-flight).
        
        Args:
            utterance_snapshot: Frozen transcript from when wait was triggered
            queue_id: Monotonic ID for this queue attempt
        """
        try:
            log.debug(f"Wait #{queue_id} started for: {utterance_snapshot[:30]}")
            
            # Wait for VAD confirmation
            await self._wait_for_speech_end()
            
            # Single-flight guard: only latest queue_id wins
            async with self._queue_lock:
                # Only queue if this is newer than what was already queued
                if queue_id <= self._latest_queue_id:
                    log.debug(f"Wait #{queue_id} stale (latest={self._latest_queue_id}), skipping")
                    return
                
                # Queue the snapshot
                if utterance_snapshot and len(utterance_snapshot.strip()) > self.MIN_TRANSCRIPT_LENGTH:
                    try:
                        await asyncio.wait_for(
                            self._utterance_queue.put(utterance_snapshot),
                            timeout=1.0
                        )
                        
                        # Update latest queued ID
                        self._latest_queue_id = queue_id
                        
                        log.info(f"Wait #{queue_id} queued: {utterance_snapshot}")
                        
                    except asyncio.TimeoutError:
                        log.error(f"Wait #{queue_id} queue.put() timed out - downstream slow")
                else:
                    log.warning(f"Wait #{queue_id} snapshot too short")
                
        except asyncio.CancelledError:
            log.debug(f"Wait #{queue_id} cancelled")
            raise
    
    async def _wait_for_speech_end(self) -> None:
        """Waiting for VAD to confirm speech has ended."""
        max_wait = self.end_detector.MAX_WAIT
        wait_start = time.time()
        
        await asyncio.sleep(0.05)
        
        while time.time() - wait_start < max_wait:
            signal = self.end_detector.is_speech_ended()
            
            # Accept HIGH or MEDIUM confidence
            if signal.confidence in ["high", "medium"]:
                log.info(
                    "Speech ended [%s, %.2fs post-hangover, %d frames]",
                    signal.confidence,
                    signal.post_hangover_silence,
                    self.end_detector.get_post_hangover_frames(),
                )
                return
            
            await asyncio.sleep(self.SPEECH_END_CHECK_INTERVAL)
        
        log.warning("Timeout after %.1fs", max_wait)

    async def feed_audio(self, mulaw_bytes: bytes) -> None:
        """
        Feeding audio to Deepgram and VAD.
        
        """
        if self._deepgram_connection and not self._closed:
            # Always process VAD
            self.end_detector.process_vad_frame(mulaw_bytes)
            
            # Only send to Deepgram when NOT speaking
            if not self._is_speaking:
                try:
                    await asyncio.wait_for(
                        self._deepgram_connection.send(mulaw_bytes),
                        timeout=self.DEEPGRAM_SEND_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    log.error("Deepgram send timeout - websocket may be stalled")
                except Exception as exc:
                    log.error("Deepgram send failed: %s", exc)

    async def utterances(self) -> AsyncGenerator[str, None]:
        """Async generator yielding complete user utterances."""
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
        """Convert text to speech and send to Twilio."""
        if not text.strip():
            return

        self._is_speaking = True
        self._tts_started_at = time.time()
        log.info("Speaking: %s... (%d chars)", text[:50], len(text))

        try:
            mp3_bytes = await self._elevenlabs_tts(text)
            decoded = miniaudio.decode(
                mp3_bytes,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=self.CHANNELS,
                sample_rate=self.SAMPLE_RATE,
            )
            raw_pcm = bytes(decoded.samples)

            if len(raw_pcm) % 2 != 0:
                raw_pcm = raw_pcm[:-1]

            audio_mulaw = audioop.lin2ulaw(raw_pcm, 2)

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

        except (httpx.HTTPError, miniaudio.DecodeError, ValueError) as exc:
            log.error("TTS/decode failed: %s", exc)

        finally:
            await asyncio.sleep(self.AUDIO_BUFFER_DELAY)
            self._is_speaking = False
            
            # Detecting barge-in
            if self._tts_started_at and self.end_detector.last_speech_time:
                if self.end_detector.last_speech_time > self._tts_started_at:
                    log.info("Barge-in detected - preserving state")
                else:
                    self.end_detector.reset_for_new_turn()
            else:
                self.end_detector.reset_for_new_turn()
            
            self._tts_started_at = None

    async def _elevenlabs_tts(self, text: str) -> bytes:
        """Converting text to speech using ElevenLabs API."""
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
        """Cleaning up resources and close Deepgram connection."""
        self._closed = True
        
        # Cancelling background tasks
        if self._active_wait_task:
            self._active_wait_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()
            
        if self._deepgram_connection:
            try:
                await self._deepgram_connection.finish()
                log.info("Deepgram connection closed successfully")
            except Exception as exc:
                log.warning("Error closing Deepgram connection: %s", exc)