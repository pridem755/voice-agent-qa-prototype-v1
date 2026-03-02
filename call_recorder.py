import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

TRANSCRIPTS_DIR = Path("transcripts")


class CallRecorder:
    """Recording and saving call transcripts with timestamps and metadata."""
    
    def __init__(self, scenario_name: str):
        """
        Initializing call recorder for a specific scenario.
        """
        self._scenario_name = scenario_name
        self._started_at = datetime.now()
        self._turns: list[dict] = []

        # Ensuring transcripts directory exists
        TRANSCRIPTS_DIR.mkdir(exist_ok=True)

    def add_turn(self, speaker: str, text: str) -> None:
        """
        Adding a conversation turn to the transcript.
        
        Args:
            speaker: Speaker identifier (agent/patient)
            text: Spoken text content
        """
        elapsed = (datetime.now() - self._started_at).total_seconds()
        self._turns.append({
            "speaker": speaker.upper(),
            "text": text,
            "elapsed": elapsed,
        })
        log.debug("[%s @ %.1fs] %s", speaker.upper(), elapsed, text)

    def save(self) -> Path:
        """
        Saving transcript to disk with metadata.
        
        Returns:
            Path to saved transcript file
            
        Raises:
            IOError: If file write fails
        """
        ended_at = datetime.now()
        duration_s = (ended_at - self._started_at).total_seconds()
        timestamp = self._started_at.strftime("%Y%m%d_%H%M%S")

        # Sanitizing scenario name for safe filename
        safe_name = "".join(
            c if c.isalnum() or c == "_" else "_" 
            for c in self._scenario_name
        )
        filename = TRANSCRIPTS_DIR / f"{safe_name}_{timestamp}.txt"

        divider = "─" * 65

        lines = [
            divider,
            "CALL TRANSCRIPT",
            f"Scenario : {self._scenario_name}",
            f"Started : {self._started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Ended : {ended_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration : {int(duration_s)}s",
            f"Turns : {len(self._turns)}",
            divider,
            "",
        ]

        for turn in self._turns:
            # Formatting elapsed time as [MM:SS]
            m = int(turn["elapsed"]) // 60
            s= int(turn["elapsed"]) % 60
            timestamp_label = f"[{m:02d}:{s:02d}]"
            speaker_label = turn["speaker"].ljust(7)
            lines.append(f"{timestamp_label} {speaker_label}: {turn['text']}")

        lines.extend(["", divider, ""])

        try:
            filename.write_text("\n".join(lines), encoding="utf-8")
            log.info(
                "Transcript saved - %s (%d turns, %ds)",
                filename,
                len(self._turns),
                int(duration_s),
            )
        except IOError as exc:
            log.error("Failed to save transcript %s: %s", filename, exc)
            raise

        return filename

    @property
    def turn_count(self) -> int:
        """Number of conversation turns recorded."""
        return len(self._turns)
