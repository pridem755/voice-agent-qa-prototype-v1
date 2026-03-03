import pytest
from unittest.mock import AsyncMock, MagicMock
from call_recorder import CallRecorder
from patient_brain import PatientBrain
from qa_analyzer import QAAnalyzer

def mock_openai(reply: str):
    """
    Creating mock OpenAI client with specified reply.
    
    Args:
        reply: Text response to return
        
    Returns:
        Mocked AsyncOpenAI client
    """
    mock_client = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = reply
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


class TestCallRecorderToQAAnalyzer:
    """Tests for CallRecorder."""
    
    @pytest.mark.asyncio
    async def test_full_recording_and_analysis_pipeline(
        self,
        tmp_path,
        monkeypatch,
        mock_openai_analysis_response,
    ):
        """Verifying complete transcript recording and analysis flow."""
        monkeypatch.chdir(tmp_path)
        
        # Recording a call
        recorder = CallRecorder("test_scenario")
        recorder.add_turn("agent", "Hello, how can I help you today?")
        recorder.add_turn("patient", "Can I book an appointment for Sunday?")
        recorder.add_turn("agent", "Sure, I've booked you for Sunday at 10am!")
        recorder.add_turn("patient", "Great, thanks!")
        
        transcript_path = recorder.save()
        assert transcript_path.exists()
        
        # Analyzing the transcript
        (tmp_path / "reports").mkdir()
        analyzer = QAAnalyzer()
        analyzer._client = mock_openai_analysis_response
        
        result = await analyzer.analyze_transcript(transcript_path)
        
        assert len(result) > 0
        assert "Bug:" in result or "No issues found" in result
    
    @pytest.mark.asyncio
    async def test_empty_transcript_handled(self, tmp_path, monkeypatch):
        """Checking empty transcripts are handled gracefully."""
        monkeypatch.chdir(tmp_path)
        
        recorder = CallRecorder("empty_test")
        transcript_path = recorder.save()
        
        analyzer = QAAnalyzer()
        result = await analyzer.analyze_transcript(transcript_path)
        
        # Should not crash, may return empty or "No issues"
        assert isinstance(result, str)


class TestPatientBrainWithCallRecorder:
    """Tests for PatientBrain + CallRecorder integration."""
    
    @pytest.mark.asyncio
    async def test_conversation_is_fully_logged(
        self,
        sample_scenario,
        tmp_path,
        monkeypatch,
    ):
        """Verifying entire conversation is recorded."""
        monkeypatch.chdir(tmp_path)
        
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("I'd like Monday morning please.")
        
        recorder = CallRecorder("test_scenario")
        
        agent_utterances = [
            "Hello, how can I help you today?",
            "What day works best for you?",
            "Great, I've booked you for Monday at 10am.",
        ]
        
        for agent_text in agent_utterances:
            recorder.add_turn("agent", agent_text)
            patient_response = await brain.respond(agent_text)
            if patient_response:
                recorder.add_turn("patient", patient_response)
        
        assert recorder.turn_count >= 3
        
        # Checking agent turns were recorded
        agent_turns = [
            t for t in recorder._turns 
            if t["speaker"] == "AGENT"
        ]
        assert len(agent_turns) == 3
    
    @pytest.mark.asyncio
    async def test_transcript_reflects_scenario_goal(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Ensuring patient brain uses scenario goal in responses."""
        scenario = {
            "id": "01",
            "name": "Test",
            "persona": "You are Pride Mudondo, 24 years old.",
            "goal": "Schedule a checkup appointment.",
            "edge_cases": "Be cooperative.",
        }
        
        client = mock_openai("I need to schedule a checkup please.")
        brain = PatientBrain(scenario)
        brain._client = client
        
        await brain.respond("Hello, how can I help?")
        
        # Verifying system prompt contains scenario details
        call_args = client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        system_msg = messages[0]
        
        assert system_msg["role"] == "system"
        assert "Pride" in system_msg["content"]
        assert "checkup" in system_msg["content"]
    
    @pytest.mark.asyncio
    async def test_saved_transcript_is_readable(
        self,
        sample_scenario,
        tmp_path,
        monkeypatch,
    ):
        """Checking saved transcripts can be read back."""
        monkeypatch.chdir(tmp_path)
        
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("Yes, Monday works.")
        
        recorder = CallRecorder("readable_test")
        recorder.add_turn("agent", "What day works for you?")
        patient_reply = await brain.respond("What day works for you?")
        recorder.add_turn("patient", patient_reply)
        
        path = recorder.save()
        content = path.read_text()
        
        assert "What day works for you?" in content
        assert patient_reply in content


class TestScenarioLoading:
    """Tests for scenario definition handling."""
    
    def test_all_required_fields_accepted(self):
        """Verifying all scenario fields are processed correctly."""
        full_scenario = {
            "id": "07",
            "name": "Urgent Symptoms",
            "persona": "You are Pride Mudondo, 24 years old.",
            "goal": "Get medical advice or urgent appointment.",
            "edge_cases": "Describe symptoms clearly.",
        }
        
        brain = PatientBrain(full_scenario)
        
        assert brain._scenario["id"] == "07"
        assert "Pride" in brain._system_prompt
    
    def test_minimal_scenario_uses_defaults(self):
        """Checking minimal scenarios work with defaults."""
        brain = PatientBrain({"id": "00", "name": "Minimal"})
        
        assert brain._system_prompt is not None
        assert len(brain._system_prompt) > 0
    
    def test_different_personas_create_different_prompts(self):
        """Ensuring persona variation affects system prompt."""
        brain1 = PatientBrain({
            "persona": "You are Pride, 24 years old.",
            "goal": "Schedule appointment.",
        })
        brain2 = PatientBrain({
            "persona": "You are Alice, 70 years old with diabetes.",
            "goal": "Request prescription refill.",
        })
        
        assert "Pride" in brain1._system_prompt
        assert "Alice" in brain2._system_prompt
        assert "diabetes" in brain2._system_prompt
        assert brain1._system_prompt != brain2._system_prompt


class TestEndToEndWorkflow:
    """Tests for complete end-to-end workflows."""
    
    @pytest.mark.asyncio
    async def test_record_analyze_workflow(
        self,
        tmp_path,
        monkeypatch,
        mock_openai_analysis_response,
    ):
        """Testing full record - save - analyze workflow."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        
        #Recording conversation
        recorder = CallRecorder("workflow_test")
        recorder.add_turn("agent", "How can I help?")
        recorder.add_turn("patient", "I need an appointment on Sunday")
        recorder.add_turn("agent", "Sure, booked for Sunday!")
        
        transcript_path = recorder.save()
        
        #Analyziong transcript
        analyzer = QAAnalyzer()
        analyzer._client = mock_openai_analysis_response
        
        analysis = await analyzer.analyze_transcript(transcript_path)
        
        #Verifying analysis was performed
        assert len(analysis) > 0
        assert isinstance(analysis, str)
