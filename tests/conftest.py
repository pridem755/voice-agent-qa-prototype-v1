
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Directory fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path

@pytest.fixture
def transcripts_dir(tmp_path):
    d = tmp_path / "transcripts"
    d.mkdir()
    return d


@pytest.fixture
def reports_dir(tmp_path):
    d = tmp_path / "reports"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_scenario():
    return {
        "id": "01",
        "name": "Test Scenario",
        "persona": "You are a 35-year-old patient named Alice.",
        "goal": "Schedule a routine checkup.",
        "edge_case_instructions": "Be cooperative and polite.",
    }

@pytest.fixture
def sample_transcript_data():
    return {
        "call_sid": "CA1234567890abcdef",
        "stream_sid": "MZ1234567890abcdef",
        "started_at": "2024-01-15T10:30:00+00:00",
        "ended_at": "2024-01-15T10:32:15+00:00",
        "duration_seconds": 135.0,
        "turn_count": 6,
        "turns": [
            {
                "index": 1,
                "speaker": "agent",
                "text": "Hello, thank you for calling. How can I help you today?",
                "timestamp": 1705312200.0,
                "elapsed_seconds": 0.0,
            },
            {
                "index": 2,
                "speaker": "patient",
                "text": "Hi, I need to schedule an appointment.",
                "timestamp": 1705312205.0,
                "elapsed_seconds": 5.0,
            },
            {
                "index": 3,
                "speaker": "agent",
                "text": "Of course! What day works best for you?",
                "timestamp": 1705312210.0,
                "elapsed_seconds": 10.0,
            },
            {
                "index": 4,
                "speaker": "patient",
                "text": "Can I come in on Sunday at 10am?",
                "timestamp": 1705312215.0,
                "elapsed_seconds": 15.0,
            },
            {
                "index": 5,
                "speaker": "agent",
                "text": "I've scheduled you for Sunday at 10am. You're all set!",
                "timestamp": 1705312220.0,
                "elapsed_seconds": 20.0,
            },
            {
                "index": 6,
                "speaker": "patient",
                "text": "Great, thank you!",
                "timestamp": 1705312225.0,
                "elapsed_seconds": 25.0,
            },
        ],
    }

# ---------------------------------------------------------------------------
# Bug analysis fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_transcript_file(tmp_path, sample_transcript_data):
    path = tmp_path / "CA1234567890abcdef.json"
    path.write_text(json.dumps(sample_transcript_data, indent=2))
    return path

@pytest.fixture
def sample_bugs():
    return [
        {
            "severity": "high",
            "category": "scheduling_error",
            "description": "Agent confirmed Sunday appointment but office is closed on weekends.",
            "agent_quote": "I've scheduled you for Sunday at 10am. You're all set!",
            "expected_behavior": "Agent should inform patient the office is closed on weekends and offer a weekday slot.",
            "transcript_location": "mid-call",
        },
        {
            "severity": "medium",
            "category": "failed_to_clarify",
            "description": "Agent did not ask for patient's name or date of birth before confirming.",
            "agent_quote": "You're all set!",
            "expected_behavior": "Agent should verify patient identity before booking.",
            "transcript_location": "mid-call",
        },
    ]

# ---------------------------------------------------------------------------
# PatientBrain fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_run_results(sample_bugs):
    """Mock orchestrator results for multiple calls."""
    return [
        {
            "scenario_id": "01",
            "scenario_name": "Simple Appointment Scheduling",
            "call_sid": "CA1234567890abcdef",
            "status": "completed",
            "transcript_path": "transcripts/CA1234567890abcdef.json",
            "bugs": sample_bugs,
            "duration_seconds": 135.0,
            "error": None,
        },
        {
            "scenario_id": "02",
            "scenario_name": "Rescheduling an Existing Appointment",
            "call_sid": "CA9876543210fedcba",
            "status": "completed",
            "transcript_path": "transcripts/CA9876543210fedcba.json",
            "bugs": [],
            "duration_seconds": 98.0,
            "error": None,
        },
        {
            "scenario_id": "07",
            "scenario_name": "Urgent Symptoms",
            "call_sid": "CAfedcba1234567890",
            "status": "completed",
            "transcript_path": "transcripts/CAfedcba1234567890.json",
            "bugs": [sample_bugs[0]],
            "duration_seconds": 60.0,
            "error": None,
        },
    ]


# ---------------------------------------------------------------------------
# Mock API client fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_openai_client():
    mock_client = AsyncMock()

    # Build a realistic response object structure matching openai SDK
    mock_choice = MagicMock()
    mock_choice.message.content = "I'd like to schedule an appointment please."

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_openai_bug_response():
    """Mock OpenAI response that returns a valid bug analysis JSON."""
    mock_client = AsyncMock()

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps([
        {
            "severity": "high",
            "category": "scheduling_error",
            "description": "Agent confirmed Sunday appointment but office is closed on weekends.",
            "agent_quote": "I've scheduled you for Sunday at 10am.",
            "expected_behavior": "Inform patient the office is closed on weekends.",
            "transcript_location": "mid-call",
        }
    ])

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_twilio_client():
    """Mock Twilio REST client for orchestrator tests."""
    mock_client = MagicMock()

    #Mock call creation
    mock_call = MagicMock()
    mock_call.sid = "CA1234567890abcdef"
    mock_client.calls.create.return_value = mock_call

    #Mock call status fetching to simulate a completed call
    mock_call_status = MagicMock()
    mock_call_status.status = "completed"
    mock_client.calls.return_value.fetch.return_value = mock_call_status

    return mock_client
