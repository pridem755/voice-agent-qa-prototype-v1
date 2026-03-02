import pytest
from unittest.mock import AsyncMock, MagicMock
from patient_brain import PatientBrain


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


class TestInit:
    """Tests for PatientBrain initialization."""
    
    def test_stores_scenario(self, sample_scenario):
        """Verifying scenario is stored correctly."""
        brain = PatientBrain(sample_scenario)
        assert brain._scenario == sample_scenario
    
    def test_initial_turn_count_is_zero(self, sample_scenario):
        """Checking turn count starts at zero."""
        brain = PatientBrain(sample_scenario)
        assert brain.turn_count == 0
    
    def test_initial_hang_up_is_false(self, sample_scenario):
        """Ensuring hang-up flag starts as False."""
        brain = PatientBrain(sample_scenario)
        assert brain.should_hang_up() is False
    
    def test_system_prompt_contains_persona(self, sample_scenario):
        """Checking persona appears in system prompt."""
        brain = PatientBrain(sample_scenario)
        assert sample_scenario["persona"] in brain._system_prompt
    
    def test_system_prompt_contains_goal(self, sample_scenario):
        """Verifying goal appears in system prompt."""
        brain = PatientBrain(sample_scenario)
        assert sample_scenario["goal"] in brain._system_prompt
    
    def test_history_starts_empty(self, sample_scenario):
        """Ensuring conversation history starts empty."""
        brain = PatientBrain(sample_scenario)
        assert brain._history == []


class TestRespond:
    """Tests for generating patient responses."""
    
    @pytest.mark.asyncio
    async def test_returns_text(self, sample_scenario):
        """Verifying respond returns string."""
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("I need an appointment.")
        
        result = await brain.respond("Hello, how can I help?")
        
        assert result == "I need an appointment."
    
    @pytest.mark.asyncio
    async def test_increments_turn_count(self, sample_scenario):
        """Checking turn count increments after response."""
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("Sure.")
        
        await brain.respond("Hello")
        
        assert brain.turn_count == 1
    
    @pytest.mark.asyncio
    async def test_appends_to_history(self, sample_scenario):
        """Verifying response is added to history."""
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("Hi there.")
        
        await brain.respond("Hello")
        
        assert len(brain._history) == 2
        assert brain._history[1]["role"] == "assistant"
        assert brain._history[1]["content"] == "Hi there."
    
    @pytest.mark.asyncio
    async def test_accumulates_history(self, sample_scenario):
        """Checking multiple responses accumulate in history."""
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("Ok.")
        
        await brain.respond("Hello")
        await brain.respond("What day?")
        await brain.respond("Monday works")
        
        assert len(brain._history) == 6
    
    @pytest.mark.asyncio
    async def test_hangup_token_sets_flag(self, sample_scenario):
        """Ensuring <HANGUP> token sets hang-up flag."""
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("Thanks, goodbye! <HANGUP>")
        
        await brain.respond("Is there anything else?")
        
        assert brain.should_hang_up() is True
    
    @pytest.mark.asyncio
    async def test_hangup_token_stripped_from_reply(self, sample_scenario):
        """Verifying <HANGUP> token is removed from response."""
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("Thanks, goodbye! <HANGUP>")
        
        result = await brain.respond("Anything else?")
        
        assert "<HANGUP>" not in result
        assert "Thanks, goodbye!" in result
    
    @pytest.mark.asyncio
    async def test_max_turns_triggers_hangup(self, sample_scenario):
        """Checking max turns limit triggers hang-up."""
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("Ok.")
        
        # Simulating reaching max turns 
        brain._turn_count = 39
        await brain.respond("Hello")
        
        assert brain.should_hang_up() is True
    
    @pytest.mark.asyncio
    async def test_api_error_returns_fallback(self, sample_scenario):
        """Ensuring API errors return fallback response."""
        brain = PatientBrain(sample_scenario)
        brain._client = AsyncMock()
        brain._client.chat.completions.create = AsyncMock(
            side_effect=Exception("Network error")
        )
        
        result = await brain.respond("Hello")
        
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_api_error_does_not_crash(self, sample_scenario):
        """Checking API errors don't raise exceptions."""
        brain = PatientBrain(sample_scenario)
        brain._client = AsyncMock()
        brain._client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("Unexpected")
        )
        
        try:
            await brain.respond("Hello")
        except Exception:
            pytest.fail("respond() should handle errors without raising")


class TestShouldHangUp:
    """Tests for hang-up detection."""
    
    def test_false_initially(self, sample_scenario):
        """Verifying should_hang_up returns False initially."""
        brain = PatientBrain(sample_scenario)
        assert brain.should_hang_up() is False
    
    @pytest.mark.asyncio
    async def test_true_after_hangup_token(self, sample_scenario):
        """Checking should_hang_up returns True after <HANGUP>."""
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("Bye! <HANGUP>")
        
        await brain.respond("Goodbye")
        
        assert brain.should_hang_up() is True


class TestConversationSummary:
    """Tests for conversation history summary."""
    
    def test_returns_list(self, sample_scenario):
        """Verifying conversation_summary returns list."""
        brain = PatientBrain(sample_scenario)
        assert isinstance(brain.conversation_summary(), list)
    
    def test_empty_before_any_turns(self, sample_scenario):
        """Checking summary is empty before any turns."""
        brain = PatientBrain(sample_scenario)
        assert brain.conversation_summary() == []
    
    @pytest.mark.asyncio
    async def test_contains_turns_after_respond(self, sample_scenario):
        """Ensuring summary contains turns after responses."""
        brain = PatientBrain(sample_scenario)
        brain._client = mock_openai("I need help.")
        
        await brain.respond("Hello")
        
        summary = brain.conversation_summary()
        assert len(summary) == 2
        assert summary[1]["content"] == "I need help."


class TestScenarioHandling:
    """Tests for scenario processing."""
    
    def test_minimal_scenario_uses_defaults(self):
        """Checking minimal scenario uses default values."""
        brain = PatientBrain({"id": "00", "name": "Minimal"})
        
        assert brain._system_prompt is not None
        assert len(brain._system_prompt) > 0
    
    def test_persona_affects_system_prompt(self):
        """Verifying different personas create different prompts."""
        brain1 = PatientBrain({
            "persona": "You are Pride Mudondo, 24 years old.",
            "goal": "Schedule an appointment.",
        })
        brain2 = PatientBrain({
            "persona": "You are Alice Johnson, 70 years old.",
            "goal": "Request a prescription refill.",
        })
        
        assert "Pride" in brain1._system_prompt
        assert "Alice" in brain2._system_prompt
        assert brain1._system_prompt != brain2._system_prompt
    
    def test_all_scenario_fields_accepted(self):
        """Ensuring all scenario fields are processed."""
        full_scenario = {
            "id": "07",
            "name": "Urgent Symptoms",
            "persona": "You are Pride Mudondo, 24 years old.",
            "goal": "Get urgent medical advice.",
            "edge_cases": "Describe symptoms clearly.",
        }
        
        brain = PatientBrain(full_scenario)
        
        assert brain._scenario["id"] == "07"
        assert "Pride" in brain._system_prompt
        assert "urgent" in brain._system_prompt.lower()
