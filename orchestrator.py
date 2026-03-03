import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from twilio.rest import Client as TwilioClient
from config import settings
from qa_analyzer import QAAnalyzer

log = logging.getLogger(__name__)

# Directory paths
SCENARIOS_DIR = Path("scenarios")
TRANSCRIPTS_DIR = Path("transcripts")

# Timing constants
SCENARIO_SETUP_DELAY = 1.0 
INTER_CALL_DELAY = 10.0  
POLL_INTERVAL = 5.0 

# Terminal call statuses
TERMINAL_STATUSES = {"completed", "failed", "busy", "no-answer", "canceled"}


def load_scenarios(prefix: str = "") -> list[dict]:
    """
    Loading scenario definitions from JSON files.
   
    """
    files = sorted(SCENARIOS_DIR.glob("*.json"))
    if not files:
        log.error("No scenario files found in %s", SCENARIOS_DIR)
        sys.exit(1)

    scenarios = []
    for path in files:
        if prefix and not path.stem.startswith(prefix):
            continue
            
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Injecting filename stem as scenario name if not set
            data.setdefault("name", path.stem)
            scenarios.append(data)
            log.info("Loaded scenario: %s", data["name"])
        except (json.JSONDecodeError, IOError) as exc:
            log.warning("Skipping %s - error: %s", path, exc)

    return scenarios


def write_current_scenario(scenario: dict) -> None:
    """
    Writing scenario to current_scenario.json for server to read.
    
    Args:
        scenario: Scenario dictionary to write
    """
    try:
        Path("current_scenario.json").write_text(
            json.dumps(scenario, indent=2),
            encoding="utf-8",
        )
        log.debug("Wrote current_scenario.json: %s", scenario["name"])
    except IOError as exc:
        log.error("Failed to write current_scenario.json: %s", exc)
        raise


def place_call(twilio_client: TwilioClient) -> str:
    """
    Placing a call via Twilio REST API.
    
    Args:
        twilio_client: Initialized Twilio client
        
    Returns:
        Call SID (session identifier)
    """
    webhook_url = f"https://{settings.public_host}/incoming"
    log.info(
        "Placing call: %s - %s via %s",
        settings.twilio_from_number,
        settings.target_phone_number,
        webhook_url,
    )

    try:
        call = twilio_client.calls.create(
            to=settings.target_phone_number,
            from_=settings.twilio_from_number,
            url=webhook_url,
            method="POST",
            record=True, 
        )
        log.info("Call placed - SID: %s", call.sid)
        return call.sid
    except Exception as exc:
        log.error("Failed to place call: %s", exc)
        raise


def wait_for_call(
    twilio_client: TwilioClient,
    call_sid: str,
    timeout: int,
) -> str:
    """
    Polling Twilio for call status until terminal state or timeout.
    
    Args:
        twilio_client: Initialized Twilio client
        call_sid: Call session identifier
        timeout: Maximum seconds to wait
        
    Returns:
        Final call status
    """
    start = time.monotonic()

    while True:
        elapsed = int(time.monotonic() - start)
        if elapsed > timeout:
            log.warning(
                "Call %s timed out after %ds - moving to next scenario",
                call_sid,
                timeout,
            )
            return "timeout"

        try:
            call = twilio_client.calls(call_sid).fetch()
            status = call.status
            log.info("Call status: %s (%ds elapsed)", status, elapsed)

            if status in TERMINAL_STATUSES:
                log.info("Call %s ended with status: %s", call_sid, status)
                return status
        except Exception as exc:
            log.error("Error checking call status: %s", exc)
            return "error"

        time.sleep(POLL_INTERVAL)


async def run_all(dry_run: bool = False, scenario_prefix: str = "") -> None:
    """
    Running all test scenarios: place calls, wait for completion, analyze results.
    
    Args:
        dry_run: If True, list scenarios without placing calls
        scenario_prefix: Optional prefix to filter scenarios
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    scenarios = load_scenarios(prefix=scenario_prefix)
    log.info("Found %d scenario(s) to run", len(scenarios))

    if dry_run:
        for s in scenarios:
            print(f"[{s['name']}] {s.get('goal', 'No goal specified')}")
        return

    twilio_client = TwilioClient(
        settings.twilio_account_sid,
        settings.twilio_auth_token,
    )

    for i, scenario in enumerate(scenarios, start=1):
        log.info("─" * 60)
        log.info("Scenario %d/%d: %s", i, len(scenarios), scenario["name"])
        log.info("─" * 60)

        # Writing scenario for server to load
        write_current_scenario(scenario)

        # Allowing server time to load scenario
        await asyncio.sleep(SCENARIO_SETUP_DELAY)

        # Placing call and waiting for completion
        try:
            call_sid = place_call(twilio_client)
        except Exception:
            log.error("Failed to place call for scenario %s", scenario["name"])
            continue

        # Waiting for call to complete with timeout
        await asyncio.get_event_loop().run_in_executor(
            None,
            wait_for_call,
            twilio_client,
            call_sid,
            settings.call_timeout_seconds,
        )

        # Pausing between calls to avoid overwhelming system
        if i < len(scenarios):
            log.info("Waiting %.0fs before next call...", INTER_CALL_DELAY)
            await asyncio.sleep(INTER_CALL_DELAY)

    log.info("All %d calls completed", len(scenarios))

    # Running post-call QA analysis
    log.info("Running QA analysis on transcripts...")
    analyzer = QAAnalyzer()
    await analyzer.analyze_all(TRANSCRIPTS_DIR)

    log.info(
        "Done. Check transcripts/, reports/bug_report.md, reports/run_summary.md"
    )

def main():
    """CLI entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Voice bot test orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python orchestrator.py                  Run all scenarios
  python orchestrator.py --scenario 03    Run only scenario 03
  python orchestrator.py --dry-run        List scenarios without calling
        """,
    )
    parser.add_argument(
        "--scenario",
        default="",
        metavar="PREFIX",
        help="Only run scenarios whose filename starts with scenario PREFIX",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List scenarios without placing any calls",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_all(dry_run=args.dry_run, scenario_prefix=args.scenario))
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        sys.exit(0)
    except Exception as exc:
        log.error("Orchestrator failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
