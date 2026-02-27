import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

TRANSCRIPTS_DIR = Path("transcripts")

#---------------------------------------------------------------------------
#Call recording and transcript management
#---------------------------------------------------------------------------
class CallRecorder:
    def __init__(self, scenario_name: str):
        self._scenario_name = scenario_name
        self._started_at = datetime.now()
        self._turns: list[dict] = [] 

        #Ensuring the output directory exists
        TRANSCRIPTS_DIR.mkdir(exist_ok=True)

    #Adding a turn to the transcript, recording speaker, text, and elapsed time for logging and later saving.
    def add_turn(self, speaker: str, text: str):
        elapsed = (datetime.now() - self._started_at).total_seconds()
        self._turns.append(
            {
                "speaker": speaker.upper(),
                "text": text,
                "elapsed": elapsed,
            }
        )
        log.debug("[%s @ %.1fs] %s", speaker.upper(), elapsed, text)

    #saving the transcript to disk in a human-readable format, including metadata 
    def save(self) -> Path:
        ended_at = datetime.now()
        duration_s = (ended_at - self._started_at).total_seconds()
        timestamp = self._started_at.strftime("%Y%m%d_%H%M%S")

        #sanitizing the scenario name for safe filenames
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in self._scenario_name)
        filename = TRANSCRIPTS_DIR / f"{safe_name}_{timestamp}.txt"

        divider = "─" * 65

        lines = [
            divider,
            "CALL TRANSCRIPT",
            f"Scenario : {self._scenario_name}",
            f"Started  : {self._started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Ended    : {ended_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration : {int(duration_s)}s",
            f"Turns    : {len(self._turns)}",
            divider,
            "",
        ]

        for turn in self._turns:
            #Formatting elapsed time as [MM:SS] and aligning speaker labels for readability
            m = int(turn["elapsed"]) // 60
            s = int(turn["elapsed"]) % 60
            timestamp_label = f"[{m:02d}:{s:02d}]"
            speaker_label = turn["speaker"].ljust(7)
            lines.append(f"{timestamp_label} {speaker_label} : {turn['text']}")

        lines.extend(["", divider, ""])

        with open(filename, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        log.info("Transcript saved → %s (%d turns, %ds)", filename, len(self._turns), int(duration_s))
        return filename

    @property
    def turn_count(self) -> int:
        return len(self._turns)
