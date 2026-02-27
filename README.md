# Voice Bot — PGAI Engineering Assessment

An automated voice bot that calls the PGAI test line, simulates realistic patient
scenarios, records transcripts, and automatically identifies bugs in the AI agent.

---

## Quick Start (single command after setup)

```bash
# Terminal 1 — start the webhook server
uvicorn server:app --host 0.0.0.0 --port 8000

# Terminal 2 — expose to the internet via ngrok
ngrok http 8000

# Terminal 3 — run all scenarios
python orchestrator.py
```

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.10+ | python.org |
| ngrok | Any | ngrok.com/download |
| pip | Latest | bundled with Python |

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd voice-bot
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Variable | Where to get it |
|----------|----------------|
| `TWILIO_ACCOUNT_SID` | [console.twilio.com](https://console.twilio.com) → Account Info |
| `TWILIO_AUTH_TOKEN` | Same page |
| `TWILIO_FROM_NUMBER` | Twilio Console → Phone Numbers → Buy a Number |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `DEEPGRAM_API_KEY` | [console.deepgram.com](https://console.deepgram.com) |
| `ELEVENLABS_API_KEY` | [elevenlabs.io](https://elevenlabs.io) → Profile |
| `PUBLIC_HOST` | Set after starting ngrok (see below) |

### 5. Start ngrok

```bash
ngrok http 8000
```

Copy the Forwarding URL (e.g. `abc123.ngrok.io`) and set it in `.env`:

```
PUBLIC_HOST=abc123.ngrok.io
```

> **Important:** ngrok assigns a new URL each time you restart it (unless you have
> a paid account with a fixed subdomain). Update `PUBLIC_HOST` in `.env` each session.

### 6. Start the webhook server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 7. Run the test scenarios

```bash
# Run all 12 scenarios
python orchestrator.py

# Run a single scenario by filename prefix
python orchestrator.py --scenario 06

# Dry run — list scenarios without calling
python orchestrator.py --dry-run
```

---

## Output

After a run you will find:

```
transcripts/          ← Full call transcripts (one .txt per call)
reports/
  bug_report.md       ← Auto-generated QA analysis (review before submitting)
  run_summary.md      ← Stats: calls made, issues found
```

---

## Project Structure

```
voice-bot/
├── server.py           # FastAPI server + Twilio WebSocket bridge
├── orchestrator.py     # Main entry point — runs all scenarios
├── patient_brain.py    # GPT-4o patient persona logic
├── speech.py           # Deepgram STT + ElevenLabs TTS pipeline
├── call_recorder.py    # Transcript writer
├── qa_analyzer.py      # Post-call bug detection (GPT-4o)
├── config.py           # Centralised settings (reads from .env)
├── scenarios/          # Test scenario JSON files
├── transcripts/        # Generated call transcripts
├── recordings/         # Twilio call recordings (MP3)
├── reports/            # Bug report + run summary
├── requirements.txt
├── .env.example
└── README.md
```

---

## Scenarios

| # | Name | Tests |
|---|------|-------|
| 01 | schedule_appointment | Basic scheduling flow |
| 02 | reschedule_appointment | Modify existing booking |
| 03 | medication_refill | Prescription management |
| 04 | office_hours_inquiry | Information retrieval |
| 05 | insurance_verification | Insurance/billing queries |
| 06 | sunday_appointment_trap | Bug hunt: Sunday booking |
| 07 | cancel_appointment | Cancellation + policy |
| 08 | confused_patient | Elderly/unclear patient stress test |
| 09 | urgent_symptoms | Safety-critical triage handling |
| 10 | new_patient | Onboarding flow |
| 11 | interruptions_test | Conversation robustness |
| 12 | medical_records_request | HIPAA compliance check |

---

## Cost Estimate (12 calls, ~2 min each)

| Service | Cost |
|---------|------|
| Twilio | ~$1.50 |
| Deepgram | ~$0.60 |
| ElevenLabs | ~$1.50 |
| OpenAI (GPT-4o) | ~$3.00 |
| **Total** | **~$6.60** |

Well within the $20 budget.

---

## Troubleshooting

**`ValidationError` on startup**
→ Missing environment variable. Check your `.env` against `.env.example`.

**Twilio error 11200 (HTTP retrieval failure)**
→ ngrok is not running, or `PUBLIC_HOST` in `.env` is wrong/stale.

**No transcript generated**
→ Check server logs. The call may have hung up before the WebSocket opened.

**Deepgram connection refused**
→ Verify `DEEPGRAM_API_KEY` is correct and you have a Nova-2 plan.
