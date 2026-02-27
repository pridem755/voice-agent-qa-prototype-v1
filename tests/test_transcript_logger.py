import json
import time
from pathlib import Path
import pytest
from transcript_logger import TranscriptLogger


class TestTranscriptLoggerInit:
    def test_initial_state_is_empty(self):
        logger = TranscriptLogger()
        assert logger.call_sid is None
        assert logger.stream_sid is None
        assert logger.started_at is None
        assert logger.turns == []

    def test_start_call_sets_metadata(self):
        logger = TranscriptLogger()
        before = time.time()
        logger.start_call(call_sid="CA123", stream_sid="MZ456")
        after = time.time()

        assert logger.call_sid == "CA123"
        assert logger.stream_sid == "MZ456"
        assert before <= logger.started_at <= after

    def test_start_call_resets_turns(self):
        logger = TranscriptLogger()
        logger.start_call("CA111", "MZ111")
        logger.add_turn("agent", "Hello")

        #Simulating reuse for a second call
        logger.start_call("CA222", "MZ222")
        assert logger.turns == []
        assert logger.call_sid == "CA222"

#---------------------------------------------------------------------------
# Tests for add_turn() method, ensuring correct data is stored and elapsed time is calculated.
#---------------------------------------------------------------------------
class TestAddTurn:
    def test_add_turn_stores_correct_speaker(self):
        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        logger.add_turn("agent", "Hello there.")
        assert logger.turns[0]["speaker"] == "agent"

    def test_add_turn_stores_correct_text(self):
        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        logger.add_turn("patient", "  I need an appointment.  ")
        #Text should be stripped of leading/trailing whitespace
        assert logger.turns[0]["text"] == "I need an appointment."

    def test_add_turn_increments_index(self):
        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        logger.add_turn("agent", "Hello")
        logger.add_turn("patient", "Hi")
        logger.add_turn("agent", "How can I help?")

        assert logger.turns[0]["index"] == 1
        assert logger.turns[1]["index"] == 2
        assert logger.turns[2]["index"] == 3

    def test_add_turn_records_timestamp(self):
        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        before = time.time()
        logger.add_turn("agent", "Hello")
        after = time.time()

        assert before <= logger.turns[0]["timestamp"] <= after

    def test_add_turn_calculates_elapsed_seconds(self):
        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        time.sleep(0.05)  # 50ms pause
        logger.add_turn("agent", "Hello")

        elapsed = logger.turns[0]["elapsed_seconds"]
        assert 0.01 <= elapsed <= 2.0

    def test_multiple_turns_accumulate(self):
        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")

        turns_data = [
            ("agent", "Hello"),
            ("patient", "Hi, I need help"),
            ("agent", "Of course"),
            ("patient", "Thanks"),
        ]
        for speaker, text in turns_data:
            logger.add_turn(speaker, text)

        assert len(logger.turns) == 4
        for i, (speaker, text) in enumerate(turns_data):
            assert logger.turns[i]["speaker"] == speaker
            assert logger.turns[i]["text"] == text

#---------------------------------------------------------------------------
# Tests for save() and load() methods, including JSON structure and data integrity.
#---------------------------------------------------------------------------
class TestSaveAndLoad:
    def test_save_creates_file(self, tmp_path, monkeypatch):
        # Redirect transcripts dir to tmp_path
        monkeypatch.chdir(tmp_path)
        (tmp_path / "transcripts").mkdir()

        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        logger.add_turn("agent", "Hello")

        path = logger.save()
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_file_contains_valid_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "transcripts").mkdir()

        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        logger.add_turn("agent", "Hello")
        logger.add_turn("patient", "Hi")

        path = logger.save()
        data = json.loads(path.read_text())

        assert data["call_sid"] == "CA123"
        assert data["stream_sid"] == "MZ456"
        assert len(data["turns"]) == 2

    def test_save_records_turn_count(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "transcripts").mkdir()

        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        for i in range(5):
            logger.add_turn("agent" if i % 2 == 0 else "patient", f"Turn {i}")

        path = logger.save()
        data = json.loads(path.read_text())
        assert data["turn_count"] == 5

    def test_load_restores_turns(self, sample_transcript_file):
        logger = TranscriptLogger.load(sample_transcript_file)
        assert len(logger.turns) == 6
        assert logger.turns[0]["speaker"] == "agent"
        assert logger.turns[1]["speaker"] == "patient"

    def test_load_restores_call_sid(self, sample_transcript_file):
        logger = TranscriptLogger.load(sample_transcript_file)
        assert logger.call_sid == "CA1234567890abcdef"

    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "transcripts").mkdir()

        original = TranscriptLogger()
        original.start_call("CA999", "MZ999")
        original.add_turn("agent", "How can I help?")
        original.add_turn("patient", "I need a refill.")
        original.add_turn("agent", "Sure, which medication?")

        path = original.save()
        restored = TranscriptLogger.load(path)

        assert len(restored.turns) == 3
        assert restored.turns[1]["text"] == "I need a refill."
        assert restored.call_sid == "CA999"

#---------------------------------------------------------------------------
# Additional tests for to_text() method
#---------------------------------------------------------------------------    
class TestToText:
    def test_to_text_includes_all_speakers(self):
        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        logger.add_turn("agent", "Hello")
        logger.add_turn("patient", "Hi there")

        text = logger.to_text()
        assert "AGENT" in text
        assert "PATIENT" in text

    def test_to_text_includes_all_content(self):
        logger = TranscriptLogger()
        logger.start_call("CA123", "MZ456")
        logger.add_turn("agent", "Hello, how can I help?")
        logger.add_turn("patient", "I need an appointment.")

        text = logger.to_text()
        assert "Hello, how can I help?" in text
        assert "I need an appointment." in text

    def test_to_text_includes_call_sid(self):
        logger = TranscriptLogger()
        logger.start_call("CA_UNIQUE_SID", "MZ456")
        text = logger.to_text()
        assert "CA_UNIQUE_SID" in text
