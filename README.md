# Voice Bot QA System

An automated testing framework for evaluating voice agents in medical office settings. This system places real phone calls through Twilio, simulates realistic patient interactions using GPT-4, and analyzes conversation quality to identify bugs and areas for improvement.

## Overview

Testing voice agents manually is time-consuming and inconsistent. This system automates the entire process by acting as a patient caller, conducting full conversations with your voice agent, recording the interactions, and using AI to analyze the agent's responses for errors, inconsistencies, and quality issues.

The system runs 13 different test scenarios (add more) covering common situations like appointment scheduling, medication refills, and edge cases like confused patients or urgent medical symptoms. After completing all tests, it generates detailed bug reports with specific examples and recommendations.

## What This System Does

The testing process works in several stages:

First, the orchestrator loads a test scenario that defines a patient persona, their goal for the call, and any special behaviors they should exhibit. For example, one scenario might be a 24-year-old patient trying to schedule an appointment on a Sunday to test if the agent properly handles weekend scheduling.

Next, the system places a real phone call to a voice agent using Twilio. A FastAPI server receives the audio stream and handles the conversation in real-time.

During the call, the patient brain module uses GPT-4 to roleplay as the patient. It generates natural, contextual responses based on what the agent says, maintaining the persona and working toward the goal defined in the scenario.

All conversations are transcribed using Deepgram for speech-to-text, and the patient's responses are converted back to speech using ElevenLabs text-to-speech before being sent to the agent.

Every conversation turn is recorded with timestamps, creating a complete transcript of the call. After all test scenarios complete, GPT-4 analyzes each transcript to identify potential bugs, categorize them by severity, and provide specific recommendations for improvement.

## Prerequisites

You will need the following to run this system (the system runs on command line interface):

- Python 3.10 or higher installed on your machine
- A Twilio account with a phone number for placing calls
- An OpenAI API key with access to GPT-4
- A Deepgram API key for speech-to-text transcription
- An ElevenLabs API key for text-to-speech synthesis
- ngrok installed for creating webhook tunnels

All of these services offer free tiers or trials or less costs that should be sufficient for initial testing.

## Installation

Start by cloning this repository to your local machine:

```bash
git clone https://github.com/pridem755/voice-agent-qa-prototype-v1
cd voice-bot
```

Create a Python virtual environment to keep dependencies isolated:

```bash
python -m venv venv
```

Activate the virtual environment. On Windows:

```bash
venv\Scripts\activate
```

On Mac or Linux:

```bash
source venv/bin/activate
```

Install all required Python packages:

```bash
pip install -r requirements.txt
```

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

Open the .env file in a text editor and add your credentials. Here's what each variable means:

**Twilio Configuration**
- TWILIO_ACCOUNT_SID: Your Twilio account identifier from the console
- TWILIO_AUTH_TOKEN: Your Twilio authentication token
- TWILIO_FROM_NUMBER: The Twilio phone number that will place calls
- TARGET_PHONE_NUMBER: The phone number of the voice agent you want to test

**OpenAI Configuration**
- OPENAI_API_KEY: Your OpenAI API key
- OPENAI_MODEL: The model to use, typically gpt-4o

**Deepgram Configuration**
- DEEPGRAM_API_KEY: Your Deepgram API key for speech recognition

**ElevenLabs Configuration**
- ELEVENLABS_API_KEY: Your ElevenLabs API key for voice synthesis
- ELEVENLABS_VOICE_ID: The voice ID to use, default is Rachel

**Server Configuration**
- SERVER_PORT: The local port for the webhook server, default is 8000
- PUBLIC_HOST: Your ngrok URL, you'll set this after starting ngrok

**Behavior Configuration**
- CALL_TIMEOUT_SECONDS: Maximum duration for each call in seconds, default is 600
- MAX_TURNS: Maximum conversation turns before forcing a hang-up, default is 40

**Config file**
-do not forget to place the target_phone_contacts which is called for testing

Generate the test scenario files:

```bash
python setup_scenarios.py
```

This creates 13 JSON files in the scenarios directory, each defining a different test case.

## Running the Tests

To run all test scenarios:

```bash
python run.py
```

This command will start the webhook server, open an ngrok tunnel for Twilio to reach your local server, and begin placing test calls. The entire process takes approximately 25 to 35 minutes to complete all 13 scenarios.

To run only specific scenarios, use the scenario flag with a prefix:

```bash
python run.py --scenario 01
```

This runs only scenarios whose ID starts with "01". You can use any prefix to filter scenarios.

To see what scenarios will run without actually placing calls:

```bash
python run.py --dry-run
```

## Understanding the Output

After the tests complete (all scenarios run), you'll find several output directories:

The transcripts directory contains text files for each call. These files show the full conversation with timestamps, speaker labels, and metadata like call duration. Each transcript is named with the scenario name and timestamp.

The reports directory contains two key files. The bug_report.md file lists all identified issues across all scenarios. Each bug includes the severity level, the exact timestamp where it occurred, what the agent said, what the problem was, and what the agent should have done instead.

The run_summary.md file provides statistics about the test run, including how many calls completed successfully, how many bugs were found, and a list of all transcript files.

## Test Scenarios Explained

The system includes 13 carefully designed test scenarios:

**Scenario 01: Simple Appointment Scheduling**
This is a baseline test with a straightforward new patient requesting an appointment. The patient is cooperative and polite, testing normal scheduling functionality.

**Scenario 02: Rescheduling an Existing Appointment**
Tests the agent's ability to find and modify existing appointments. The patient needs a specific time that fits their work schedule.

**Scenario 03: Medication Refill**
A post-surgical patient requests a prescription refill with some urgency since they're running low on medication.

**Scenario 04: Office Hours Inquiry**
Tests whether the agent provides accurate information about operating hours, location, and parking.

**Scenario 05: Insurance Verification**
A patient with new insurance needs to verify coverage before booking. Tests the agent's ability to handle insurance questions.

**Scenario 06: Sunday Appointment Trap**
This is a bug-hunting scenario. The patient persistently requests Sunday appointments to test if the agent incorrectly schedules on closed days.

**Scenario 07: Appointment Cancellation**
Tests cancellation flow and whether the agent respects the patient's decision not to reschedule.

**Scenario 08: Confused Patient**
A distracted patient who changes direction mid-conversation. Tests the agent's patience and ability to help disorganized callers.

**Scenario 09: Urgent Symptoms**
Critical safety test. A patient with potential post-surgical infection symptoms should be directed to urgent care, not scheduled for a routine appointment.

**Scenario 10: New Patient Onboarding**
Tests the new patient intake process, including what documents to bring and online form availability.

**Scenario 11: Interruptions Test**
A patient who frequently interrupts the agent. Tests conversation flow management and context retention.

**Scenario 12: Medical Records Request**
Tests HIPAA compliance. The agent should mention authorization forms, not just agree to send records immediately.

**Scenario 13: Difficult Patient**
A frustrated patient having a bad day who needs multiple things done in one call. Tests the agent's ability to handle stressed callers and multi-part requests.

## Project Structure

Here's how the codebase is organized:

**Core Modules**

- call_recorder.py handles recording conversation transcripts with timestamps and speaker labels
- config.py manages all configuration and environment variables
- orchestrator.py loads scenarios, places calls, waits for completion, and triggers analysis
- patient_brain.py uses GPT-4 to simulate patient responses based on scenario definitions
- qa_analyzer.py analyzes transcripts with GPT-4 to identify bugs and generate reports
- run.py is the main entry point that starts the server and orchestrates the test run
- server.py runs the FastAPI webhook server that receives Twilio audio streams
- setup_scenarios.py generates the test scenario definition files
- speech.py handles the speech processing pipeline including Deepgram and ElevenLabs integration

**Generated Directories**

- scenarios contains JSON files defining each test case
- transcripts stores the recorded conversation files
- reports contains the bug analysis and summary reports

**Testing**

The tests directory contains the test suite with 59 tests covering the core modules. Run tests with pytest.

## How the System Works Internally

When you run the system, several components work together:

The orchestrator loads scenario files from the scenarios directory. For each scenario, it writes the scenario definition to a current_scenario.json file that the server will read, waits one second for the server to load the scenario, then places a Twilio call.

The Twilio call connects to your webhook server through an ngrok tunnel. The server accepts the WebSocket connection and begins streaming audio bidirectionally.

Audio from the agent flows through Deepgram for transcription. When speech ends, the transcript is passed to the patient brain module.

The patient brain maintains conversation context and uses GPT-4 to generate an appropriate response based on the scenario persona and goal. This response is converted to speech using ElevenLabs and streamed back to Twilio.

The call recorder logs every turn with timestamps. When the patient brain decides the conversation is complete or the maximum turn limit is reached, it signals a hang-up.

After all calls finish, the QA analyzer reads each transcript and uses GPT-4 to identify bugs. It looks for factual errors, logical inconsistencies, safety issues, poor user experience, and failure to handle edge cases gracefully.

The analyzer generates two markdown reports: a detailed bug report with specific examples and a summary with statistics.

## Common Issues and Solutions

**Server Won't Start**

If you see an error that port 8000 is already in use, another application is using that port. Either stop the other application or change SERVER_PORT in your .env file to a different port like 8001.

Make sure your .env file exists and contains all required variables. The system will fail to start if API keys are missing.

**Calls Not Connecting**

First, verify that ngrok is running and that your PUBLIC_HOST in .env matches the ngrok URL exactly. The URL should look like https://something.ngrok-free.dev.

Check that your Twilio phone numbers in .env are correct and in E.164 format, starting with a plus sign.

If calls connect but immediately disconnect, check the server logs for errors. The issue is often with the WebSocket connection or audio streaming setup.

**No Audio or Transcription Issues**

Verify your Deepgram API key is valid and has available credits. Check the Deepgram dashboard to confirm.

Make sure the ElevenLabs voice ID is correct. The default is Rachel, but you can use any voice from your ElevenLabs account.

If transcripts are empty, the speech detection thresholds might be too aggressive. You can adjust MIN_SILENCE_WITH_FINAL and MIN_SILENCE_NO_FINAL in speech.py.

**GPT-4 API Errors**

Confirm your OpenAI API key has access to GPT-4. Not all API keys have this access by default.

Check your OpenAI account for rate limits or billing issues. The system makes many API calls, so ensure you have sufficient credits.

If you're getting timeout errors, the OpenAI API might be experiencing high load. Try running fewer scenarios at once or increasing the timeout values.

**Missing Transcripts or Reports**

Make sure the transcripts and reports directories exist and have write permissions. The system creates these automatically, but permission issues can prevent this.

Check the console output for error messages. The system logs when it saves files, so missing logs indicate where the failure occurred.

If reports are empty even though transcripts exist, check that the QA analyzer is running after all calls complete. Look for the "Running QA analysis" log message.

## Running the Test Suite

The project includes a comprehensive test suite with 59 tests. To run all tests:

```bash
pytest tests/
```

For more detailed output showing each test name:

```bash
pytest tests/ -v
```

To see test coverage:

```bash
pytest --cov=. tests/
```

To run only tests for a specific module:

```bash
pytest tests/test_patient_brain.py
```

The test suite covers the core modules with unit tests and integration tests that verify components work together correctly.

## Customizing the System

You can customize several aspects of the system:

**Adding New Scenarios**

Edit setup_scenarios.py and add a new dictionary to the SCENARIOS list. Each scenario needs an id, name, persona, goal, and edge_cases field. The persona describes who the patient is, the goal explains what they want to accomplish, and edge_cases provide special instructions for handling unusual situations.

After adding scenarios, run python setup_scenarios.py again to regenerate the JSON files.

**Adjusting Speech Detection**

If the patient interrupts the agent too often or waits too long before responding, adjust the timing constants in speech.py. The AdaptiveEndOfSpeechDetector class has MIN_SILENCE_WITH_FINAL and MIN_SILENCE_NO_FINAL that control how long to wait before considering speech ended.

**Modifying Patient Behavior**

The patient brain system prompt in patient_brain.py defines how the simulated patient behaves. You can edit this prompt to make patients more or less verbose, more or less cooperative, or add new behaviors.

**Changing Analysis Criteria**

The QA analyzer system prompt in qa_analyzer.py defines what counts as a bug. You can modify this to look for different issues or change severity classifications.

## Best Practices

Run a single scenario first to verify everything is working before running all 13 scenarios. Use python run.py --scenario 01 to test with just one call.

Monitor the first few calls closely by watching the console output. This helps you catch configuration issues early.

Review the bug reports carefully. The AI analyzer is sophisticated but not perfect. Use your judgment to determine which identified issues are genuine bugs versus false positives.

Save your transcripts and reports for comparison over time. This lets you track improvement as you fix issues.

Consider running tests regularly as you make changes to your voice agent. This helps catch regressions early.

## Technical Architecture

The system uses an event-driven architecture with asynchronous Python throughout.

The FastAPI server handles incoming WebSocket connections from Twilio using async handlers. When audio arrives, it's queued and processed by the speech pipeline.

The speech pipeline maintains a Deepgram WebSocket connection for real-time transcription. It uses an adaptive end-of-speech detector that considers both silence duration and whether Deepgram marked a transcript as final.

The patient brain is stateless between turns but maintains conversation history. Each response is generated by sending the full conversation context to GPT-4 along with the scenario-specific system prompt.

Audio encoding uses the mulaw format at 8kHz sample rate, which is standard for telephony. The system converts between formats as needed for different APIs.

All components use structured logging to make debugging easier. Log levels range from debug (verbose) to error (critical issues only).

## Contributing to the Project

If you'd like to contribute improvements:

Fork the repository and create a new branch for your changes. Use descriptive branch names like feature/add-sms-scenarios or fix/speech-detection-timing.

Make your changes and add tests for any new functionality. The project maintains high test coverage, so new code should include corresponding tests.

Ensure all existing tests still pass by running pytest tests/ before submitting.

Follow the existing code style. The project uses docstrings for all functions and classes, type hints for parameters and returns, and clear comments for complex logic.

Submit a pull request with a clear description of what changed and why. Reference any related issues.

## Credits and Technologies

This system builds on several excellent technologies:

Twilio provides the telephony infrastructure for placing calls and streaming audio. The Programmable Voice API and Media Streams feature make real-time voice interaction possible.

OpenAI's GPT-4 powers both the patient simulation and the transcript analysis. The model's ability to maintain context and generate natural responses is central to realistic testing.

Deepgram provides fast, accurate speech-to-text transcription with low latency, which is essential for real-time conversation.

ElevenLabs offers natural-sounding text-to-speech synthesis with minimal latency, making the simulated patient sound realistic.

FastAPI provides the async web framework for handling WebSocket connections efficiently.

The project also uses Pydantic for configuration management, pytest for testing, and several other open-source libraries listed in requirements.txt.

## License

This project is released under the MIT License. See the LICENSE file for full details.

## Getting Help

If you encounter issues not covered in the troubleshooting section, check the GitHub issues to see if others have experienced the same problem.

When reporting a new issue, include the relevant log output, your Python version, and the approximate section of the README where you encountered the problem. This helps maintainers diagnose and fix issues quickly.

For questions about how the system works or how to customize it for your use case, consider opening a discussion on GitHub rather than an issue.



                              ++++++++++++++++++ PRIDE MUDONDO ++++++++++++++++++++