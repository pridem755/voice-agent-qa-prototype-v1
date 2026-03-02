import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

# Event loop fixture
@pytest.fixture(scope="session")
def event_loop():
    """Providing event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# Directory fixtures
@pytest.fixture
def tmp_dir(tmp_path):
    """Temporary directory for test files."""
    return tmp_path


@pytest.fixture
def transcripts_dir(tmp_path):
    """Temporary transcripts directory."""
    d = tmp_path / "transcripts"
    d.mkdir()
    return d


@pytest.fixture
def reports_dir(tmp_path):
    """Temporary reports directory."""
    d = tmp_path / "reports"
    d.mkdir()
    return d


# Sample data fixtures
@pytest.fixture
def sample_scenario():
    """Sample test scenario definition."""
    return {
        "id": "01",
        "name": "Test Scenario",
        "persona": "You are Pride Mudondo, a 24-year-old patient.",
        "goal": "Schedule a routine checkup appointment.",
        "edge_cases": "Be cooperative and polite.",
    }


@pytest.fixture
def sample_transcript_text():
    """Sample transcript in .txt format (matches call_recorder output)."""
    return """_________________________________________________________________
CALL TRANSCRIPT
Scenario : test_scenario
Started  : 2024-01-15 10:30:00
Ended    : 2024-01-15 10:32:15
Duration : 135s
Turns    : 6
─────────────────────────────────────────────────────────────────

[00:00] AGENT  : Hello, thank you for calling. How can I help you today?
[00:05] PATIENT: Hi, I need to schedule an appointment.
[00:10] AGENT  : Of course! What day works best for you?
[00:15] PATIENT: Can I come in on Sunday at 10am?
[00:20] AGENT  : I've scheduled you for Sunday at 10am. You're all set!
[00:25] PATIENT: Great, thank you!

─────────────────────────────────────────────────────────────────
"""


@pytest.fixture
def sample_transcript_file(tmp_path, sample_transcript_text):
    """Sample transcript file on disk."""
    path = tmp_path / "test_scenario_20240115_103000.txt"
    path.write_text(sample_transcript_text, encoding="utf-8")
    return path


# Mock API client fixtures
@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for patient brain tests."""
    mock_client = AsyncMock()

    # Building realistic response structure
    mock_choice = MagicMock()
    mock_choice.message.content = "I'd like to schedule an appointment please."

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_openai_analysis_response():
    """Mock OpenAI response for QA analysis."""
    mock_client = AsyncMock()

    mock_choice = MagicMock()
    mock_choice.message.content = """### Bug: Sunday appointment scheduled
**Severity**: High
**Timestamp**: [00:20] in the transcript
**Agent said**: "I've scheduled you for Sunday at 10am."
**Problem**: Agent confirmed Sunday appointment but office is closed on weekends.
**Expected**: Inform patient the office is closed on weekends and offer weekday slot.
"""

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_twilio_client():
    """Mock Twilio REST client for orchestrator tests."""
    mock_client = MagicMock()

    # Mocking call creation
    mock_call = MagicMock()
    mock_call.sid = "CA1234567890abcdef"
    mock_client.calls.create.return_value = mock_call

    # Mocking call status fetch (completed call)
    mock_call_status = MagicMock()
    mock_call_status.status = "completed"
    mock_client.calls.return_value.fetch.return_value = mock_call_status

    return mock_client
