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

#Loading environment variables from .env file before importing other modules
load_dotenv()

from orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

#Port the FastAPI server listens on locally
SERVER_PORT = int(os.getenv("PORT", 8000))


# ---------------------------------------------------------------------------
#Server management
# ---------------------------------------------------------------------------

def start_server_thread() -> threading.Thread:
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

#Waiting for the FastAPI server to be responsive before proceeding with calls
def wait_for_server(timeout: int = 30) -> bool:
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


#---------------------------------------------------------------------------
#ngrok tunnel management
#---------------------------------------------------------------------------

def start_ngrok(port: int) -> str:
    #First check if the user has set a webhook URL in the environment
    if os.getenv("WEBHOOK_BASE_URL"):
        url = os.getenv("WEBHOOK_BASE_URL")
        logger.info(f"Using configured webhook URL: {url}")
        return url

    try:
        #Try using pyngrok if available for better control and reliability
        from pyngrok import ngrok as pyngrok
        tunnel = pyngrok.connect(port, "http")
        public_url = tunnel.public_url.replace("http://", "https://")
        logger.info(f"ngrok tunnel: {public_url}")
        return public_url

    except ImportError:
        #Fall back to ngrok CLI
        logger.info("pyngrok not found — trying ngrok CLI")
        return _start_ngrok_cli(port)


def _start_ngrok_cli(port: int) -> str:
    """Starting ngrok via CLI and parse the public URL from its API."""
    import httpx

    #Starting ngrok in background
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
                    logger.info(f"ngrok tunnel: {url}")
                    return url
        except Exception:
            time.sleep(1)

    proc.kill()
    raise RuntimeError(
        "ngrok failed to start. Install ngrok from https://ngrok.com/download "
        "or set WEBHOOK_BASE_URL in your .env file."
    )


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

#Running pre-flight checks to ensure all required environment variables and scenario files are present 
def run_preflight_checks() -> None:
    errors = []

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
            "See .env.example for required variables.\n"
        )
        sys.exit(1)

    logger.info(f"Preflight OK — {len(scenario_files)} scenario(s) ready")


#---------------------------------------------------------------------------
#Main
#---------------------------------------------------------------------------

async def main(scenario_filter: str = None, dry_run: bool = False):
    """Main async entrypoint."""

    #Validating config before doing anything
    run_preflight_checks()

    if dry_run:
        orch = Orchestrator()
        scenarios = orch.load_scenarios()
        print("\nAvailable scenarios:")
        for s in scenarios:
            print(f"  [{s['id']}] {s['name']}")
        return

    #Starting the FastAPI webhook server
    logger.info("Starting FastAPI server...")
    start_server_thread()
    if not wait_for_server():
        logger.error("FastAPI server failed to start within 30s")
        sys.exit(1)
    logger.info(f"Server ready on port {SERVER_PORT}")

    #Starting ngrok tunnel so Twilio can reach us
    logger.info("Starting ngrok tunnel...")
    public_url = start_ngrok(SERVER_PORT)
    os.environ["WEBHOOK_BASE_URL"] = public_url
    logger.info(f"Public webhook URL: {public_url}")

    #Brief pause to ensure everything is settled before calls start
    await asyncio.sleep(2)

    #Running the test scenarios
    orch = Orchestrator()
    await orch.run_all(filter_id=scenario_filter)

    logger.info("Test run complete. Check reports/ for results.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PrettyGood AI Assessment Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                  Run all 12 scenarios
  python run.py --scenario 07    Run only the emergency scenario
  python run.py --dry-run        List scenarios without calling
        """,
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        metavar="ID",
        help="Run a specific scenario by ID (e.g. '01', '07')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List scenarios without making any calls",
    )
    args = parser.parse_args()

    asyncio.run(main(scenario_filter=args.scenario, dry_run=args.dry_run))
