import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from twilio.rest import Client as TwilioClient
from config import settings
from qa_analyzer import QAAnalyzer

log = logging.getLogger(__name__)

SCENARIOS_DIR = Path("scenarios")
TRANSCRIPTS_DIR = Path("transcripts")

#--------------------------------------------------------------------------
# Scenario management and call orchestration
#--------------------------------------------------------------------------
def load_scenarios(prefix: str = "") -> list[dict]:
    files = sorted(SCENARIOS_DIR.glob("*.json"))
    if not files:
        log.error("No scenario files found in %s", SCENARIOS_DIR)
        sys.exit(1)

    scenarios = []
    for path in files:
        if prefix and not path.stem.startswith(prefix):
            continue
        try:
            with open(path) as fh:
                data = json.load(fh)
            #Injecting the filename stem as the scenario name if not set
            data.setdefault("name", path.stem)
            scenarios.append(data)
            log.info("Loaded scenario: %s", data["name"])
        except json.JSONDecodeError as exc:
            log.warning("Skipping %s - invalid JSON: %s", path, exc)

    return scenarios

def write_current_scenario(scenario: dict):
    with open("current_scenario.json", "w") as fh:
        json.dump(scenario, fh, indent=2)
    log.debug("Wrote current_scenario.json: %s", scenario["name"])

#Placing a call via Twilio's REST API, specifying our webhook for call instructions
def place_call(twilio_client: TwilioClient) -> str:
    webhook_url = f"https://{settings.public_host}/incoming"
    log.info(
        "Placing call: %s - %s via %s",
        settings.twilio_from_number,
        settings.target_phone_number,
        webhook_url,
    )

    call = twilio_client.calls.create(
        to=settings.target_phone_number,
        from_=settings.twilio_from_number,
        url=webhook_url,
        method="POST",
        #Recording the call on Twilio's side as a backup 
        record=True,
    )
    log.info("Call placed — SID: %s", call.sid)
    return call.sid

#Polling Twilio for call status until it reaches a terminal state or times out
def wait_for_call(twilio_client: TwilioClient, call_sid: str, timeout: int):
    terminal_statuses = {"completed", "failed", "busy", "no-answer", "canceled"}
    start = time.monotonic()

    while True:
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            log.warning("Call %s timed out after %ds — moving to next scenario", call_sid, timeout)
            break

        call = twilio_client.calls(call_sid).fetch()
        status = call.status
        log.info("Call status: %s (%.0fs elapsed)", status, elapsed)

        if status in terminal_statuses:
            log.info("Call %s ended with status: %s", call_sid, status)
            break

        time.sleep(5) 

#Running through all scenarios: placing calls, waiting for completion, and then running post-call analysis on the transcripts.
async def run_all(dry_run: bool = False, scenario_prefix: str = ""):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    scenarios = load_scenarios(prefix=scenario_prefix)
    log.info("Found %d scenario(s) to run", len(scenarios))

    if dry_run:
        for s in scenarios:
            print(f"  [{s['name']}] {s.get('goal', 'No goal specified')}")
        return

    twilio_client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)

    results: list[dict] = []

    for i, scenario in enumerate(scenarios, start=1):
        log.info("─" * 60)
        log.info("Scenario %d/%d: %s", i, len(scenarios), scenario["name"])
        log.info("─" * 60)

        #Telling the server which scenario to use for the next incoming call
        write_current_scenario(scenario)

        #Giving the server a moment to register the new scenario file
        await asyncio.sleep(1)

        #Placing the call and wait for it to finish
        call_sid = place_call(twilio_client)
        #Waiting for the call to complete, with a timeout to prevent hanging on bad scenarios
        await asyncio.get_event_loop().run_in_executor(
            None,
            wait_for_call,
            twilio_client,
            call_sid,
            settings.call_timeout_seconds,
        )

        results.append({"scenario": scenario["name"], "call_sid": call_sid})

       #Adding a short pause between calls to avoid overwhelming the system and to allow for any cleanup
        if i < len(scenarios):
            log.info("Waiting 10s before next call...")
            await asyncio.sleep(10)

    log.info("All %d calls completed", len(scenarios))

    #------Post-call QA analysis-----------------------------------------------------------
    log.info("Running QA analysis on transcripts...")
    analyzer = QAAnalyzer()
    await analyzer.analyse_all(TRANSCRIPTS_DIR)

    log.info("Done. Check transcripts/, reports/bug_report.md, reports/run_summary.md")


#Command-line interface to allow filtering scenarios by prefix
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice bot test orchestrator")
    parser.add_argument(
        "--scenario",
        default="",
        metavar="PREFIX",
        help="Only run scenarios whose filename starts with this prefix (e.g. '03')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List scenarios without placing any calls",
    )
    args = parser.parse_args()

    asyncio.run(run_all(dry_run=args.dry_run, scenario_prefix=args.scenario))


class Orchestrator:
    def load_scenarios(self, prefix=""):
        return load_scenarios(prefix=prefix)

    async def run_all(self, filter_id=None):
        await run_all(scenario_prefix=filter_id or "")