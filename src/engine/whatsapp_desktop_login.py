"""
Independent Desktop WhatsApp Web Login Process.
Opens a clean Chromium desktop window on Windows so the user can scan the official
live WhatsApp Web QR code in real-time with zero expiration delay, zero lag, and 100% reliability.
Once authenticated, it saves session tokens to .whatsapp_web_session/ and closes automatically.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WhatsAppDesktopLogin")

SESSION_DIR = ".whatsapp_web_session"
STATE_FILE = ".whatsapp_signal_state.json"
QR_IMAGE_PATH = ".whatsapp_qr.png"

def cleanup_orphaned_sessions(session_dir: str = SESSION_DIR):
    """Kills any chrome processes holding the session lock and cleans Singleton locks."""
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name']):
            try:
                name = (p.info.get('name') or '').lower()
                if 'chrome' in name:
                    cmd = " ".join(p.cmdline() or [])
                    if session_dir in cmd or 'ms-playwright' in cmd:
                        p.kill()
            except Exception:
                pass
    except Exception:
        pass

    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lf_path = os.path.join(session_dir, lock_file)
        if os.path.exists(lf_path):
            try:
                os.remove(lf_path)
            except Exception:
                pass

def run_desktop_login():
    import asyncio
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

    logger.info("Starting Desktop WhatsApp Web Login...")
    
    # Update state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            state["status"] = "AWAITING_DESKTOP_LOGIN"
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    cleanup_orphaned_sessions(SESSION_DIR)
    os.makedirs(SESSION_DIR, exist_ok=True)

    with sync_playwright() as p:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        browser_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--window-size=1280,850"
        ]

        ctx = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            user_agent=user_agent,
            args=browser_args,
            viewport={"width": 1280, "height": 850}
        )

        # Mask webdriver and inject modern Chrome 133 Client Hints
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            if (!navigator.userAgentData) {
                navigator.userAgentData = {
                    brands: [
                        { brand: 'Not(A:Brand', version: '99' },
                        { brand: 'Google Chrome', version: '133' },
                        { brand: 'Chromium', version: '133' }
                    ],
                    mobile: false,
                    platform: 'Windows'
                };
            }
            window.navigator.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)

        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://web.whatsapp.com", wait_until="commit", timeout=30000)

            logger.info("==========================================")
            logger.info("🚀 WhatsApp Web Desktop Window is now OPEN!")
            logger.info("Scan the QR code on your screen using your phone's WhatsApp.")
            logger.info("Once linked, this window will automatically save and close.")
            logger.info("==========================================")
            logged_in = False
            spinner_cycles = 0
            reloaded = False

            # Wait up to 180 seconds (3 minutes) for user to scan
            for _ in range(120):
                # 1. Multi-attribute check for authenticated state
                is_auth = False
                try:
                    is_auth = page.evaluate("""() => Boolean(
                        document.querySelector('div#pane-side') ||
                        document.querySelector('header') ||
                        document.querySelector('[data-testid="chat-list"]') ||
                        document.querySelector('[data-testid="conversation-panel-wrapper"]') ||
                        (window.localStorage && (window.localStorage.getItem('last-wid') || window.localStorage.getItem('last-wid-md')))
                    )""")
                except Exception:
                    pass

                if is_auth:
                    logged_in = True
                    break

                # 2. Check if phone scanned and connecting / syncing messages
                is_connecting = False
                try:
                    is_connecting = page.evaluate("""() => {
                        const text = document.body ? document.body.innerText : '';
                        return Boolean(
                            document.querySelector('[data-icon="connecting"]') ||
                            document.querySelector('div[role="progressbar"]') ||
                            document.querySelector('progress') ||
                            text.includes('Loading your chats') ||
                            text.includes('Organizing messages') ||
                            text.includes('Connecting')
                        );
                    }""")
                except Exception:
                    pass

                if is_connecting:
                    if os.path.exists(STATE_FILE):
                        try:
                            with open(STATE_FILE, "r", encoding="utf-8") as f:
                                s = json.load(f)
                            if s.get("status") != "CONNECTING":
                                s["status"] = "CONNECTING"
                                with open(STATE_FILE, "w", encoding="utf-8") as f:
                                    json.dump(s, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass
                    if os.path.exists(QR_IMAGE_PATH):
                        try:
                            os.remove(QR_IMAGE_PATH)
                        except Exception:
                            pass
                    time.sleep(1.5)
                    continue

                # Auto-click reload button if QR expired
                try:
                    reload_btn = page.locator("button:has-text('Reload'), [role='button']:has-text('Reload'), span[data-icon='reload'], span[data-icon='refresh'], div[data-testid='link-device-qr-code'] button, div[data-ref] button").first
                    if reload_btn.count() > 0 and reload_btn.is_visible():
                        reload_btn.click()
                        time.sleep(1.0)
                except Exception:
                    pass

                # Save fresh QR screenshot for Streamlit UI sync
                try:
                    qr_box = page.locator("div[data-testid='link-device-qr-code'], div[data-testid='link-device-qr-code'] canvas, canvas").first
                    if qr_box.count() > 0 and qr_box.is_visible():
                        box = qr_box.bounding_box()
                        if box and box.get("width", 0) > 60:
                            qr_box.screenshot(path=QR_IMAGE_PATH)
                            if os.path.exists(STATE_FILE):
                                with open(STATE_FILE, "r", encoding="utf-8") as f:
                                    s = json.load(f)
                                s["qr_updated_at"] = datetime.now(timezone.utc).isoformat()
                                if s.get("status") not in ["AUTHENTICATED", "CONNECTED", "CONNECTING"]:
                                    s["status"] = "AWAITING_QR_SCAN"
                                with open(STATE_FILE, "w", encoding="utf-8") as f:
                                    json.dump(s, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

                time.sleep(1.5)

            if logged_in:
                logger.info("🎉 WhatsApp Web Authenticated successfully on desktop! Flushing session...")
                time.sleep(2.0)  # Allow cookies and IndexedDB to settle
                if os.path.exists(STATE_FILE):
                    try:
                        with open(STATE_FILE, "r", encoding="utf-8") as f:
                            state = json.load(f)
                        state["status"] = "AUTHENTICATED"
                        with open(STATE_FILE, "w", encoding="utf-8") as f:
                            json.dump(state, f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass
                if os.path.exists(QR_IMAGE_PATH):
                    try:
                        os.remove(QR_IMAGE_PATH)
                    except Exception:
                        pass
                logger.info("Session saved. Closing login window.")
            else:
                logger.warning("Desktop login timed out after 3 minutes.")
                if os.path.exists(STATE_FILE):
                    try:
                        with open(STATE_FILE, "r", encoding="utf-8") as f:
                            state = json.load(f)
                        state["status"] = "LOGIN_TIMED_OUT"
                        with open(STATE_FILE, "w", encoding="utf-8") as f:
                            json.dump(state, f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass

        finally:
            try:
                ctx.close()
            except Exception:
                pass

if __name__ == "__main__":
    run_desktop_login()
