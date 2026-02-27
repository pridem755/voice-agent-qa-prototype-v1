import pytest
from unittest.mock import AsyncMock, MagicMock
from patient_brain import PatientBrain


#--------Helpers-----------------------------------------------------

def make_brain(sample_scenario, mock_client=None):
    brain = PatientBrain(sample_scenario)
    if mock_client:
        brain._client = mock_client
    return brain


def mock_openai(reply: str):
    mock_client = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = reply
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


#-----------------Init -------------------------------------------------------------

class TestInit:
    def test_scenario_stored(self, sample_scenario):
        brain = PatientBrain(sample_scenario)
        assert brain._scenario == sample_scenario

    def test_initial_turn_count_is_zero(self, sample_scenario):
        brain = PatientBrain(sample_scenario)
        assert brain.turn_count == 0

    def test_initial_hang_up_is_false(self, sample_scenario):
        brain = PatientBrain(sample_scenario)
        assert brain.should_hang_up() is False

    def test_system_prompt_contains_persona(self, sample_scenario):
        brain = PatientBrain(sample_scenario)
        assert sample_scenario["persona"] in brain._system_prompt

    def test_system_prompt_contains_goal(self, sample_scenario):
        brain = PatientBrain(sample_scenario)
        assert sample_scenario["goal"] in brain._system_prompt

    def test_history_starts_empty(self, sample_scenario):
        brain = PatientBrain(sample_scenario)
        assert brain._history == []


#---------------respond()-----------------------------------------------------------------------

class TestRespond:

    @pytest.mark.asyncio
    async def test_respond_returns_text(self, sample_scenario):
        brain = make_brain(sample_scenario, mock_openai("I need an appointment."))
        result = await brain.respond("Hello, how can I help?")
        assert result == "I need an appointment."

    @pytest.mark.asyncio
    async def test_respond_increments_turn_count(self, sample_scenario):
        brain = make_brain(sample_scenario, mock_openai("Sure."))
        await brain.respond("Hello")
        assert brain.turn_count == 1

    @pytest.mark.asyncio
    async def test_respond_appends_to_history(self, sample_scenario):
        brain = make_brain(sample_scenario, mock_openai("Hi there."))
        await brain.respond("Hello")
        assert len(brain._history) == 1
        assert brain._history[0]["role"] == "assistant"
        assert brain._history[0]["content"] == "Hi there."

    @pytest.mark.asyncio
    async def test_respond_accumulates_history(self, sample_scenario):
        brain = make_brain(sample_scenario, mock_openai("Ok."))
        await brain.respond("Hello")
        await brain.respond("What day?")
        await brain.respond("Monday works")
        assert len(brain._history) == 3

    @pytest.mark.asyncio
    async def test_hangup_token_sets_hang_up(self, sample_scenario):
        brain = make_brain(
            sample_scenario,
            mock_openai("Thanks, goodbye! <HANGUP>")
        )
        await brain.respond("Is there anything else?")
        assert brain.should_hang_up() is True

    @pytest.mark.asyncio
    async def test_hangup_token_stripped_from_reply(self, sample_scenario):
        brain = make_brain(
            sample_scenario,
            mock_openai("Thanks, goodbye! <HANGUP>")
        )
        result = await brain.respond("Anything else?")
        assert "<HANGUP>" not in result

    @pytest.mark.asyncio
    async def test_api_error_returns_fallback(self, sample_scenario):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Network error")
        )
        brain = make_brain(sample_scenario, mock_client)
        result = await brain.respond("Hello")
        assert result is not None 
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_api_error_does_not_raise(self, sample_scenario):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("Unexpected")
        )
        brain = make_brain(sample_scenario, mock_client)
        try:
            await brain.respond("Hello")
        except Exception:
            pytest.fail("respond() raised instead of handling the error")


#------------should_hang_up()----------------------------------------------------------------

class TestShouldHangUp:

    def test_false_initially(self, sample_scenario):
        brain = PatientBrain(sample_scenario)
        assert brain.should_hang_up() is False

    @pytest.mark.asyncio
    async def test_true_after_hangup_token(self, sample_scenario):
        brain = make_brain(sample_scenario, mock_openai("Bye! <HANGUP>"))
        await brain.respond("Goodbye")
        assert brain.should_hang_up() is True


#----------conversation_summary()----------------------------------------------------------------

class TestConversationSummary:
    def test_returns_list(self, sample_scenario):
        brain = PatientBrain(sample_scenario)
        assert isinstance(brain.conversation_summary(), list)

    def test_empty_before_any_turns(self, sample_scenario):
        brain = PatientBrain(sample_scenario)
        assert brain.conversation_summary() == []

    @pytest.mark.asyncio
    async def test_contains_turns_after_respond(self, sample_scenario):
        brain = make_brain(sample_scenario, mock_openai("I need help."))
        await brain.respond("Hello")
        summary = brain.conversation_summary()
        assert len(summary) == 1
        assert summary[0]["content"] == "I need help."