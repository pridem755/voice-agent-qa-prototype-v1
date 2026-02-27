import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TRANSCRIPTS_DIR = Path("transcripts")

#---------------------------------------------------------------------------
#TranscriptLogger: manages the recording and saving of call transcripts, including speaker turns and timestamps
#---------------------------------------------------------------------------
class TranscriptLogger:
    def __init__(self):
        TRANSCRIPTS_DIR.mkdir(exist_ok=True)

        self.call_sid: Optional[str] = None
        self.stream_sid: Optional[str] = None
        self.started_at: Optional[float] = None
        self.turns: list[dict] = []

    def start_call(self, call_sid: str, stream_sid: str) -> None:
        """
        Initializing transcript for a new call.
        """
        self.call_sid = call_sid
        self.stream_sid = stream_sid
        self.started_at = time.time()
        self.turns = []
        logger.debug(f"Transcript initialized for call {call_sid}")

    # Adding a turn to the transcript, recording speaker, text, and elapsed time for logging and later saving.
    def add_turn(self, speaker: str, text: str) -> None:
        now = time.time()
        elapsed = (now - self.started_at) if self.started_at else 0.0

        turn = {
            "index": len(self.turns) + 1,
            "speaker": speaker,
            "text": text.strip(),
            "timestamp": now,
            "elapsed_seconds": round(elapsed, 2),
        }
        self.turns.append(turn)

        #printing to stdout for real-time monitoring
        tag = "AGENT  " if speaker == "agent" else "PATIENT"
        elapsed_str = f"{elapsed:6.1f}s"
        logger.info(f"  [{elapsed_str}] {tag}: {text}")

    # Saving the transcript to disk in a structured JSON format
    def save(self, call_sid: Optional[str] = None) -> Path:
        sid = call_sid or self.call_sid or f"unknown_{int(time.time())}"
        ended_at = time.time()
        duration = (ended_at - self.started_at) if self.started_at else 0

        transcript = {
            "call_sid": sid,
            "stream_sid": self.stream_sid,
            "started_at": datetime.fromtimestamp(
                self.started_at, tz=timezone.utc
            ).isoformat() if self.started_at else None,
            "ended_at": datetime.fromtimestamp(
                ended_at, tz=timezone.utc
            ).isoformat(),
            "duration_seconds": round(duration, 1),
            "turn_count": len(self.turns),
            "turns": self.turns,
        }

        output_path = TRANSCRIPTS_DIR / f"{sid}.json"
        with open(output_path, "w") as f:
            json.dump(transcript, f, indent=2)

        logger.info(
            f"Transcript saved: {output_path} "
            f"({len(self.turns)} turns, {duration:.0f}s)"
        )
        return output_path

    #converting the transcript into a human-readable text format
    def to_text(self) -> str:
        lines = [f"Call: {self.call_sid}\n{'='*50}"]
        for turn in self.turns:
            tag = "AGENT  " if turn["speaker"] == "agent" else "PATIENT"
            lines.append(f"[{turn['elapsed_seconds']:6.1f}s] {tag}: {turn['text']}")
        return "\n".join(lines)

    #loading a transcript from a JSON file, reconstructing the TranscriptLogger instance with its data. 
    @classmethod
    def load(cls, path: Path) -> "TranscriptLogger":
        with open(path) as f:
            data = json.load(f)

        instance = cls()
        instance.call_sid = data.get("call_sid")
        instance.stream_sid = data.get("stream_sid")
        instance.turns = data.get("turns", [])
        return instance
