import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest
from bug_analyzer import Bug, BugAnalyzer

#---------------------------------------------------------------------------
#Tests for the Bug dataclass and related functionality
#---------------------------------------------------------------------------
class TestBugDataclass:
    def test_bug_to_dict_contains_all_fields(self):
        bug = Bug(
            severity="high",
            category="scheduling_error",
            description="Agent booked Sunday appointment.",
            agent_quote="You're booked for Sunday.",
            expected_behavior="Should reject weekend bookings.",
            transcript_location="mid-call",
        )
        d = bug.to_dict()

        assert d["severity"] == "high"
        assert d["category"] == "scheduling_error"
        assert d["description"] == "Agent booked Sunday appointment."
        assert d["agent_quote"] == "You're booked for Sunday."
        assert d["expected_behavior"] == "Should reject weekend bookings."
        assert d["transcript_location"] == "mid-call"

    def test_bug_to_markdown_contains_severity(self):
        bug = Bug(
            severity="critical",
            category="hallucination",
            description="Agent invented a medication.",
            agent_quote="You should take 500mg of Zoloft.",
            expected_behavior="Agent should not give medication advice.",
            transcript_location="early",
        )
        md = bug.to_markdown()
        assert "CRITICAL" in md

    def test_bug_to_markdown_contains_category(self):
        bug = Bug(
            severity="medium",
            category="failed_to_clarify",
            description="Agent assumed patient's name.",
            agent_quote="Hello John!",
            expected_behavior="Agent should ask for the patient's name.",
            transcript_location="early",
        )
        md = bug.to_markdown()
        assert "Failed To Clarify" in md  

    def test_bug_to_markdown_contains_agent_quote(self):
        bug = Bug(
            severity="low",
            category="poor_ux",
            description="Overly verbose response.",
            agent_quote="That is a great question and I am so happy you asked...",
            expected_behavior="Keep responses concise.",
            transcript_location="mid-call",
        )
        md = bug.to_markdown()
        assert "That is a great question" in md

    def test_bug_to_markdown_has_no_emojis(self):
        bug = Bug(
            severity="high",
            category="scheduling_error",
            description="Test",
            agent_quote="Test quote",
            expected_behavior="Expected",
            transcript_location="end",
        )
        md = bug.to_markdown()
        # Check for common emoji unicode ranges
        for char in md:
            code = ord(char)
            assert not (0x1F300 <= code <= 0x1F9FF), f"Found emoji character: {char}"

#---------------------------------------------------------------------------
#Tests for the BugAnalyzer class
#---------------------------------------------------------------------------
class TestLoadTranscript:
    def test_loads_valid_transcript(self, sample_transcript_file):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        result = analyzer._load_transcript(sample_transcript_file)
        assert result is not None
        assert "AGENT" in result
        assert "PATIENT" in result

    def test_formats_transcript_as_dialogue(self, sample_transcript_file):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        result = analyzer._load_transcript(sample_transcript_file)
        assert "[1]" in result
        assert "[2]" in result

    def test_includes_agent_text(self, sample_transcript_file):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        result = analyzer._load_transcript(sample_transcript_file)
        assert "Hello, thank you for calling" in result

    def test_returns_none_for_missing_file(self, tmp_path):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        missing = tmp_path / "nonexistent.json"
        result = analyzer._load_transcript(missing)
        assert result is None

    def test_returns_none_for_empty_turns(self, tmp_path):
        empty_transcript = tmp_path / "empty.json"
        empty_transcript.write_text(json.dumps({
            "call_sid": "CA123",
            "turns": []
        }))
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        result = analyzer._load_transcript(empty_transcript)
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("this is not json {{{")
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        result = analyzer._load_transcript(bad_file)
        assert result is None

#---------------------------------------------------------------------------
#Tests for the full analyze() pipeline with mocked OpenAI responses
#---------------------------------------------------------------------------
class TestParseBugs:
    def test_parses_valid_bug_list(self):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        raw = json.dumps([
            {
                "severity": "high",
                "category": "scheduling_error",
                "description": "Booked Sunday.",
                "agent_quote": "You're set for Sunday.",
                "expected_behavior": "Reject weekend bookings.",
                "transcript_location": "mid-call",
            }
        ])
        bugs = analyzer._parse_bugs(raw)
        assert len(bugs) == 1
        assert isinstance(bugs[0], Bug)
        assert bugs[0].severity == "high"
        assert bugs[0].category == "scheduling_error"

    def test_parses_bugs_wrapped_in_object(self):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        raw = json.dumps({
            "bugs": [
                {
                    "severity": "medium",
                    "category": "no_answer",
                    "description": "Agent ignored question.",
                    "agent_quote": "Moving on...",
                    "expected_behavior": "Answer the question.",
                    "transcript_location": "end",
                }
            ]
        })
        bugs = analyzer._parse_bugs(raw)
        assert len(bugs) == 1
        assert bugs[0].category == "no_answer"

    def test_parses_empty_list(self):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        bugs = analyzer._parse_bugs("[]")
        assert bugs == []

    def test_returns_empty_list_on_invalid_json(self):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        bugs = analyzer._parse_bugs("not valid json at all")
        assert bugs == []

    def test_skips_malformed_bug_entries(self):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        raw = json.dumps([
            {
                "severity": "high",
                "category": "scheduling_error",
                "description": "Valid bug",
                "agent_quote": "Quote",
                "expected_behavior": "Expected",
                "transcript_location": "early",
            },
            None,  
            "not a dict",  
        ])
        bugs = analyzer._parse_bugs(raw)
        assert len(bugs) == 1
        assert bugs[0].description == "Valid bug"

    def test_normalizes_severity_to_lowercase(self):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        raw = json.dumps([
            {
                "severity": "HIGH",  
                "category": "scheduling_error",
                "description": "Test",
                "agent_quote": "Test",
                "expected_behavior": "Test",
                "transcript_location": "early",
            }
        ])
        bugs = analyzer._parse_bugs(raw)
        assert bugs[0].severity == "high"

    def test_handles_missing_optional_fields_gracefully(self):
        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        raw = json.dumps([
            {
                "severity": "low",
                "category": "poor_ux",
            }
        ])
        bugs = analyzer._parse_bugs(raw)
        assert len(bugs) == 1
        assert bugs[0].description == ""
        assert bugs[0].agent_quote == ""

#----------------------------------------------------------------------------
#Edge case tests for the analyze() method
#----------------------------------------------------------------------------   
class TestSaveBugReport:
    def test_saves_json_report(self, tmp_path, sample_transcript_file, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        bugs = [
            Bug("high", "scheduling_error", "Test", "Quote", "Expected", "early")
        ]
        analyzer._save_bug_report(bugs=bugs, transcript_path=sample_transcript_file)

        json_files = list((tmp_path / "reports").glob("bugs_*.json"))
        assert len(json_files) == 1

    def test_saves_markdown_report(self, tmp_path, sample_transcript_file, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        bugs = [
            Bug("high", "scheduling_error", "Test", "Quote", "Expected", "early")
        ]
        analyzer._save_bug_report(bugs=bugs, transcript_path=sample_transcript_file)

        md_files = list((tmp_path / "reports").glob("bugs_*.md"))
        assert len(md_files) == 1

    def test_json_report_is_valid(self, tmp_path, sample_transcript_file, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        bugs = [
            Bug("high", "scheduling_error", "Sunday bug", "Quote", "Expected", "early")
        ]
        analyzer._save_bug_report(bugs=bugs, transcript_path=sample_transcript_file)

        json_file = list((tmp_path / "reports").glob("bugs_*.json"))[0]
        data = json.loads(json_file.read_text())

        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["description"] == "Sunday bug"

    def test_empty_bugs_creates_no_bugs_message(
        self, tmp_path, sample_transcript_file, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        analyzer._save_bug_report(bugs=[], transcript_path=sample_transcript_file)

        md_file = list((tmp_path / "reports").glob("bugs_*.md"))[0]
        content = md_file.read_text()
        assert "No bugs found" in content

#---------------------------------------------------------------------------
#Tests for the full analyze() method with mocked OpenAI API calls
#---------------------------------------------------------------------------
class TestAnalyzePipeline:
    @pytest.mark.asyncio
    async def test_analyze_returns_bug_list(
        self, sample_transcript_file, mock_openai_bug_response, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        analyzer = BugAnalyzer()
        analyzer.client = mock_openai_bug_response

        bugs = await analyzer.analyze(sample_transcript_file)
        assert isinstance(bugs, list)
        assert len(bugs) == 1
        assert isinstance(bugs[0], Bug)

    @pytest.mark.asyncio
    async def test_analyze_returns_empty_list_for_missing_transcript(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        missing = tmp_path / "nonexistent.json"
        analyzer = BugAnalyzer.__new__(BugAnalyzer)

        bugs = await analyzer.analyze(missing)
        assert bugs == []
