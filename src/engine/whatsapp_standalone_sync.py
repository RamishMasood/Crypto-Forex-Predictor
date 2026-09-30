import os
import sys
import time
import json
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WhatsAppStandaloneSync")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SESSION_DIR = os.path.join(PROJECT_ROOT, ".whatsapp_web_session")
STATE_FILE  = os.path.join(PROJECT_ROOT, ".whatsapp_signal_state.json")


def is_worker_running() -> bool:
    """Return True if the main worker process is alive (owns the browser session)."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        pid = state.get("worker_pid")
        if not pid:
            return False
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def run_standalone_sync():
    from src.engine.whatsapp_signal_executor import WhatsAppSignalExecutor

    executor = WhatsAppSignalExecutor()

    # ── Safety check: never open a second browser when the worker is alive ────
    # The worker already owns the user-data-dir lock. A second chrome instance
    # with the same dir causes "Access denied on LOCK" and kills both processes.
    if is_worker_running():
        logger.info(
            "Main worker is running — signaling it to sync channels instead of "
            "launching a competing browser. Standalone mode skipped."
        )
        # Signal the already-running worker to do the sync
        state = executor.load_state()
        state["request_channel_sync"] = True
        executor.save_state(state)
        return

    from src.engine.whatsapp_worker import discover_followed_channels
    from playwright.sync_api import sync_playwright

    # Only remove singleton LOCK files — do NOT kill any processes here
    if os.path.exists(SESSION_DIR):
        for root, dirs, files in os.walk(SESSION_DIR):
            for fname in files:
                if fname in ["SingletonLock", "SingletonCookie", "SingletonSocket"] or fname.endswith(".lock"):
                    try:
                        os.remove(os.path.join(root, fname))
                    except Exception:
                        pass
    os.makedirs(SESSION_DIR, exist_ok=True)

    state = executor.load_state()
    state["is_syncing_channels"] = True
    executor.save_state(state)

    logger.info("Starting standalone WhatsApp channels & groups discovery...")

    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-infobars",
        "--window-size=1280,850",
        "--disable-session-crashed-bubble",
        "--disable-features=Translate,OptimizationHints,MediaRouter"
    ]
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=True,
                user_agent=user_agent,
                args=browser_args,
                viewport={"width": 1280, "height": 850}
            )
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto("https://web.whatsapp.com", wait_until="commit", timeout=45000)

                # Wait for WhatsApp Web authentication / sidebar to mount
                for _ in range(30):
                    time.sleep(1.0)
                    try:
                        if page.evaluate("() => Boolean(document.querySelector('div#pane-side, div[data-testid=\"chat-list\"]'))"):
                            break
                    except Exception:
                        break
                time.sleep(3.0)

                discover_followed_channels(page, executor)
                logger.info("Standalone sync completed successfully!")
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error during standalone discovery: {e}")
    finally:
        state = executor.load_state()
        state["is_syncing_channels"] = False
        executor.save_state(state)

if __name__ == "__main__":
    run_standalone_sync()
