import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from bug_analyzer import BugAnalyzer
from patient_brain import PatientBrain
from report_generator import ReportGenerator
from transcript_logger import TranscriptLogger


def mock_openai(reply: str):
    mock_client = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = reply
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client

#---------------------------------------------------------------------------
# Integration tests covering multiple components working together, with mocked OpenAI API calls.
#---------------------------------------------------------------------------
class TestTranscriptToBugAnalyzer:
    @pytest.mark.asyncio
    async def test_full_transcript_analysis_pipeline(
        self, tmp_path, monkeypatch, mock_openai_bug_response
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "transcripts").mkdir()
        (tmp_path / "reports").mkdir()

        logger = TranscriptLogger()
        logger.start_call("CA_INTEGRATION_01", "MZ_STREAM_01")
        logger.add_turn("agent", "Hello, how can I help you today?")
        logger.add_turn("patient", "Can I book an appointment for Sunday?")
        logger.add_turn("agent", "Sure, I've booked you for Sunday at 10am!")
        logger.add_turn("patient", "Great, thanks!")
        transcript_path = logger.save()

        assert transcript_path.exists()

        analyzer = BugAnalyzer()
        analyzer.client = mock_openai_bug_response

        bugs = await analyzer.analyze(transcript_path)
        assert len(bugs) >= 1
        assert any(b.category == "scheduling_error" for b in bugs)

    @pytest.mark.asyncio
    async def test_empty_transcript_produces_no_bugs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "transcripts").mkdir()
        (tmp_path / "reports").mkdir()

        empty_path = tmp_path / "transcripts" / "CA_EMPTY.json"
        empty_path.write_text(json.dumps({"call_sid": "CA_EMPTY", "turns": []}))

        analyzer = BugAnalyzer.__new__(BugAnalyzer)
        bugs = await analyzer.analyze(empty_path)
        assert bugs == []

#---------------------------------------------------------------------------
# Tests for the ReportGenerator using sample bug data from BugAnalyzer
#---------------------------------------------------------------------------
class TestBugAnalyzerToReportGenerator:
    def test_bugs_appear_in_consolidated_report(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert "scheduling_error" in content.lower() or "Scheduling Error" in content
        assert "Agent confirmed Sunday appointment" in content

    def test_bug_count_matches_in_report(
        self, tmp_path, sample_run_results, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        total_bugs = sum(len(r["bugs"]) for r in sample_run_results)
        gen = ReportGenerator()
        path = gen.generate(results=sample_run_results, total_duration=293.0)
        content = path.read_text()

        assert f"**Total bugs found:** {total_bugs}" in content

    def test_zero_bug_run_report(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()

        clean_results = [
            {
                "scenario_id": str(i),
                "scenario_name": f"Clean Scenario {i}",
                "call_sid": f"CA{i:010d}",
                "status": "completed",
                "transcript_path": f"transcripts/CA{i:010d}.json",
                "bugs": [],
                "duration_seconds": 90.0,
                "error": None,
            }
            for i in range(1, 4)
        ]

        gen = ReportGenerator()
        path = gen.generate(results=clean_results, total_duration=270.0)
        content = path.read_text()

        assert "**Total bugs found:** 0" in content
        assert "No bugs found" in content

#---------------------------------------------------------------------------
# Tests for the PatientBrain and TranscriptLogger working together, with mocked OpenAI API calls.
#---------------------------------------------------------------------------
class TestPatientBrainWithTranscriptLogger:
    @pytest.mark.asyncio
    async def test_conversation_is_fully_logged(
        self, sample_scenario, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "transcripts").mkdir()

        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("I'd like Monday morning please.")

        logger = TranscriptLogger()
        logger.start_call("CA_BRAIN_TEST", "MZ_BRAIN_TEST")

        agent_utterances = [
            "Hello, how can I help you today?",
            "What day works best for you?",
            "Great, I've booked you for Monday at 10am.",
        ]

        for agent_text in agent_utterances:
            logger.add_turn("agent", agent_text)
            patient_response = await brain.respond(agent_text)
            if patient_response:
                logger.add_turn("patient", patient_response)

        assert len(logger.turns) >= 3
        agent_turns = [t for t in logger.turns if t["speaker"] == "agent"]
        assert len(agent_turns) == 3

    @pytest.mark.asyncio
    async def test_transcript_reflects_scenario_goal(self, tmp_path, monkeypatch):
        scenario = {
            "id": "01",
            "name": "Test",
            "persona": "You are Alice, a 35-year-old patient.",
            "goal": "Schedule a checkup.",
            "edge_cases": "Be cooperative.",
        }

        client = mock_openai("I need to schedule a checkup please.")
        brain = PatientBrain(scenario)
        brain._client = client

        await brain.respond("Hello, how can I help?")

        call_args = client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        system_msg = messages[0]

        assert system_msg["role"] == "system"
        assert "Alice" in system_msg["content"]
        assert "checkup" in system_msg["content"]

#---------------------------------------------------------------------------
# Tests for the PatientBrain's scenario loading and system prompt generation.
#---------------------------------------------------------------------------
class TestScenarioLoading:
    def test_all_required_scenario_fields_accepted(self):
        full_scenario = {
            "id": "07",
            "name": "Urgent Symptoms",
            "persona": "You are Kevin O'Brien, 55 years old.",
            "goal": "Get medical advice or an urgent appointment.",
            "edge_cases": "Describe symptoms clearly.",
        }
        brain = PatientBrain(full_scenario)
        assert brain._scenario["id"] == "07"
        assert "Kevin O'Brien" in brain._system_prompt

    def test_minimal_scenario_uses_defaults(self):
        brain = PatientBrain({"id": "00", "name": "Minimal"})
        assert brain._system_prompt is not None
        assert len(brain._system_prompt) > 0

    def test_scenario_persona_affects_system_prompt(self):
        brain1 = PatientBrain({
            "persona": "You are Alice, 30 years old.",
            "goal": "Schedule an appointment.",
        })
        brain2 = PatientBrain({
            "persona": "You are Bob, 70 years old with diabetes.",
            "goal": "Request a prescription refill.",
        })

        assert "Alice" in brain1._system_prompt
        assert "Bob" in brain2._system_prompt
        assert brain1._system_prompt != brain2._system_prompt