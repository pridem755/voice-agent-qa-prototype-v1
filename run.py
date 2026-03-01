"""
Main test runner - Orchestrates server, ngrok, and test scenarios.

Starts FastAPI server, establishes ngrok tunnel for Twilio webhooks,
and runs test scenarios via orchestrator.
"""
import argparse
import asyncio
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Loading environment variables before importing other modules
load_dotenv()

from orchestrator import run_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Server configuration
SERVER_PORT = int(os.getenv("PORT", 8000))


def start_server_thread() -> threading.Thread:
    """
    Start FastAPI server in background thread.
    
    Returns:
        Thread running the server
    """
    def run():
        from server import app
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=SERVER_PORT,
            log_level="warning",
            access_log=False,
        )

    thread = threading.Thread(target=run, daemon=True, name="fastapi-server")
    thread.start()
    return thread


def wait_for_server(timeout: int = 30) -> bool:
    """
    Wait for FastAPI server to be responsive.
    
    Args:
        timeout: Maximum seconds to wait
        
    Returns:
        True if server is ready, False if timeout
    """
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://localhost:{SERVER_PORT}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def start_ngrok(port: int) -> str:
    """
    Start ngrok tunnel or use configured webhook URL.
    
    Args:
        port: Local port to tunnel
        
    Returns:
        Public HTTPS URL for webhooks
    """
    # Checking for configured webhook URL
    if os.getenv("WEBHOOK_BASE_URL"):
        url = os.getenv("WEBHOOK_BASE_URL")
        log.info("Using configured webhook URL: %s", url)
        return url

    try:
        # Attempting pyngrok for better control
        from pyngrok import ngrok as pyngrok
        tunnel = pyngrok.connect(port, "http")
        public_url = tunnel.public_url.replace("http://", "https://")
        log.info("ngrok tunnel: %s", public_url)
        return public_url

    except ImportError:
        # Falling back to ngrok CLI
        log.info("pyngrok not found — trying ngrok CLI")
        return _start_ngrok_cli(port)


def _start_ngrok_cli(port: int) -> str:
    """
    Start ngrok via CLI and parse public URL.
    
    Args:
        port: Local port to tunnel
        
    Returns:
        Public HTTPS URL
        
    Raises:
        RuntimeError: If ngrok fails to start
    """
    import httpx

    # Starting ngrok in background
    proc = subprocess.Popen(
        ["ngrok", "http", str(port), "--log=stdout"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = httpx.get("http://localhost:4040/api/tunnels", timeout=2)
            tunnels = r.json().get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    url = t["public_url"]
                    log.info("ngrok tunnel: %s", url)
                    return url
        except Exception:
            time.sleep(1)

    proc.kill()
    raise RuntimeError(
        "ngrok failed to start. Please ensure ngrok is installed and in your PATH, "
        "or set WEBHOOK_BASE_URL in your .env file."
    )


def run_preflight_checks() -> None:
    """
    Validate environment and scenario files before running.
    
    Exits with error code if critical requirements are missing.
    """
    errors = []

    # Checking required environment variables
    required_env = [
        "OPENAI_API_KEY",
        "DEEPGRAM_API_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_FROM_NUMBER",
    ]
    for var in required_env:
        if not os.getenv(var):
            errors.append(f"Missing environment variable: {var}")

    # Checking for scenario files
    scenario_files = list(Path("scenarios").glob("scenario_*.json"))
    if not scenario_files:
        errors.append(
            "No scenario files found. Run: python setup_scenarios.py"
        )

    if errors:
        print("\n[PREFLIGHT FAILED]\n")
        for err in errors:
            print(f"  - {err}")
        print(
            "\nFix the above issues and try again.\n"
        )
        sys.exit(1)

    log.info("Preflight OK — %d scenario(s) ready", len(scenario_files))


async def main(scenario_filter: str = None, dry_run: bool = False):
    """
    Main async entry point.
    
    Args:
        scenario_filter: Optional scenario prefix filter
        dry_run: If True, list scenarios without running
    """
    # Validating configuration
    run_preflight_checks()

    if dry_run:
        from orchestrator import load_scenarios
        scenarios = load_scenarios()
        print("\nAvailable scenarios:")
        for s in scenarios:
            print(f"  [{s.get('id', '??')}] {s['name']}")
        return

    # Starting FastAPI webhook server
    log.info("Starting FastAPI server...")
    start_server_thread()
    if not wait_for_server():
        log.error("FastAPI server failed to start within 30s")
        sys.exit(1)
    log.info("Server ready on port %d", SERVER_PORT)

    # Starting ngrok tunnel for Twilio webhooks
    log.info("Starting ngrok tunnel...")
    public_url = start_ngrok(SERVER_PORT)
    os.environ["WEBHOOK_BASE_URL"] = public_url
    log.info("Public webhook URL: %s", public_url)

    # Allowing services to settle
    await asyncio.sleep(2)

    # Running test scenarios
    await run_all(scenario_prefix=scenario_filter or "")

    log.info("Test run complete. Check reports/ for results.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Voice bot test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                  Run all scenarios
  python run.py --scenario 03    Run only scenario 03
  python run.py --dry-run        List scenarios without calling
        """,
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        metavar="PREFIX",
        help="Run specific scenario by prefix (e.g. '01', '03')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List scenarios without making any calls",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(scenario_filter=args.scenario, dry_run=args.dry_run))
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        sys.exit(0)
    except Exception as exc:
        log.error("Fatal error: %s", exc, exc_info=True)
        sys.exit(1)
