import time
from pathlib import Path
import pytest
from call_recorder import CallRecorder


class TestCallRecorderInit:
    """Tests for CallRecorder initialization."""
    
    def test_stores_scenario_name(self):
        """Verifying scenario name is stored correctly."""
        recorder = CallRecorder("test_scenario")
        assert recorder._scenario_name == "test_scenario"
    
    def test_initial_turn_count_is_zero(self):
        """Checking turn count starts at zero."""
        recorder = CallRecorder("test")
        assert recorder.turn_count == 0
    
    def test_creates_transcripts_directory(self, tmp_path, monkeypatch):
        """Ensuring transcripts directory is created."""
        monkeypatch.chdir(tmp_path)
        recorder = CallRecorder("test")
        assert (tmp_path / "transcripts").exists()


class TestAddTurn:
    """Tests for adding conversation turns."""
    
    def test_stores_speaker(self):
        """Checking speaker is stored correctly."""
        recorder = CallRecorder("test")
        recorder.add_turn("agent", "Hello")
        assert recorder._turns[0]["speaker"] == "AGENT"
    
    def test_stores_text(self):
        """Verifying text content is stored."""
        recorder = CallRecorder("test")
        recorder.add_turn("patient", "I need an appointment")
        assert recorder._turns[0]["text"] == "I need an appointment"
    
    def test_uppercases_speaker(self):
        """Ensuring speaker names are uppercased."""
        recorder = CallRecorder("test")
        recorder.add_turn("agent", "Hi")
        assert recorder._turns[0]["speaker"] == "AGENT"
        
        recorder.add_turn("patient", "Hello")
        assert recorder._turns[1]["speaker"] == "PATIENT"
    
    def test_records_elapsed_time(self):
        """Checking elapsed time is calculated."""
        recorder = CallRecorder("test")
        time.sleep(0.05)  
        recorder.add_turn("agent", "Hello")
        
        elapsed = recorder._turns[0]["elapsed"]
        assert 0.01 <= elapsed <= 2.0
    
    def test_multiple_turns_accumulate(self):
        """Verifying multiple turns are stored sequentially."""
        recorder = CallRecorder("test")
        
        turns_data = [
            ("agent", "Hello"),
            ("patient", "Hi, I need help"),
            ("agent", "Of course"),
            ("patient", "Thanks"),
        ]
        
        for speaker, text in turns_data:
            recorder.add_turn(speaker, text)
        
        assert len(recorder._turns) == 4
        for i, (speaker, text) in enumerate(turns_data):
            assert recorder._turns[i]["speaker"] == speaker.upper()
            assert recorder._turns[i]["text"] == text
    
    def test_turn_count_property(self):
        """Checking turn_count property works correctly."""
        recorder = CallRecorder("test")
        assert recorder.turn_count == 0
        
        recorder.add_turn("agent", "Hello")
        assert recorder.turn_count == 1
        
        recorder.add_turn("patient", "Hi")
        assert recorder.turn_count == 2


class TestSave:
    """Tests for saving transcripts to disk."""
    
    def test_creates_file(self, tmp_path, monkeypatch):
        """Verifying save creates a file."""
        monkeypatch.chdir(tmp_path)
        
        recorder = CallRecorder("test_scenario")
        recorder.add_turn("agent", "Hello")
        
        path = recorder.save()
        assert path.exists()
        assert path.suffix == ".txt"
    
    def test_file_contains_scenario_name(self, tmp_path, monkeypatch):
        """Checking scenario name appears in transcript."""
        monkeypatch.chdir(tmp_path)
        
        recorder = CallRecorder("test_scenario_123")
        recorder.add_turn("agent", "Hello")
        
        path = recorder.save()
        content = path.read_text()
        assert "test_scenario_123" in content
    
    def test_file_contains_turns(self, tmp_path, monkeypatch):
        """Ensuring all turns are written to file."""
        monkeypatch.chdir(tmp_path)
        
        recorder = CallRecorder("test")
        recorder.add_turn("agent", "How can I help?")
        recorder.add_turn("patient", "I need an appointment")
        
        path = recorder.save()
        content = path.read_text()
        
        assert "How can I help?" in content
        assert "I need an appointment" in content
    
    def test_file_contains_duration(self, tmp_path, monkeypatch):
        """Checking duration is recorded in transcript."""
        monkeypatch.chdir(tmp_path)
        
        recorder = CallRecorder("test")
        recorder.add_turn("agent", "Hello")
        time.sleep(0.05)
        
        path = recorder.save()
        content = path.read_text()
        
        assert "Duration" in content
    
    def test_file_contains_turn_count(self, tmp_path, monkeypatch):
        """Verifying turn count is recorded."""
        monkeypatch.chdir(tmp_path)
        
        recorder = CallRecorder("test")
        for i in range(5):
            speaker = "agent" if i % 2 == 0 else "patient"
            recorder.add_turn(speaker, f"Turn {i}")
        
        path = recorder.save()
        content = path.read_text()
        
        assert "Turns : 5" in content
    
    def test_sanitizes_scenario_name_in_filename(self, tmp_path, monkeypatch):
        """Ensuring special characters are sanitized in filename."""
        monkeypatch.chdir(tmp_path)
        
        recorder = CallRecorder("scenario/with\\special:chars")
        recorder.add_turn("agent", "Hello")
        
        path = recorder.save()
        # Filename should not contain special chars
        assert "/" not in path.name
        assert "\\" not in path.name
        assert ":" not in path.name