"""
Independent Desktop WhatsApp Web Login Process.
Opens a native Chromium desktop window on Windows so the user can scan the official
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

def run_desktop_login():
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

    try:
        import subprocess
        subprocess.run(
            ["powershell", "-Command", "Get-Process -Name 'chrome' -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*ms-playwright*' } | Stop-Process -Force"],
            capture_output=True, timeout=5
        )
    except Exception:
        pass

    os.makedirs(SESSION_DIR, exist_ok=True)
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

    with sync_playwright() as p:
        browser_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check"
        ]

        ctx = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            user_agent=user_agent,
            args=browser_args,
            viewport={"width": 1100, "height": 800}
        )

        # Apply Anti-Bot / Anti-Webdriver Masking Script
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
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
            window.navigator.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)

        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://web.whatsapp.com", wait_until="load", timeout=60000)

            logger.info("Desktop WhatsApp window open. Awaiting user scan from phone...")
            logged_in = False

            # Wait up to 180 seconds (3 minutes) for user to scan
            for _ in range(120):
                # Auto-click reload button if QR expired
                try:
                    reload_btn = page.locator("div[data-ref] button, div[data-ref] [role='button'], span[data-icon='reload'], span[data-icon='refresh']").first
                    if reload_btn.count() > 0 and reload_btn.is_visible():
                        reload_btn.click()
                        time.sleep(1.0)
                except Exception:
                    pass

                # Also save a fresh QR for the Streamlit dashboard
                try:
                    data_ref_el = page.locator("div[data-ref]").first
                    if data_ref_el.count() > 0:
                        d_ref = data_ref_el.get_attribute("data-ref")
                        if d_ref and len(d_ref) > 15:
                            import qrcode
                            qr = qrcode.QRCode(box_size=10, border=2)
                            qr.add_data(d_ref)
                            qr.make(fit=True)
                            img = qr.make_image(fill_color="black", back_color="white")
                            img.save(QR_IMAGE_PATH)
                            if os.path.exists(STATE_FILE):
                                with open(STATE_FILE, "r", encoding="utf-8") as f:
                                    s = json.load(f)
                                s["qr_updated_at"] = datetime.now(timezone.utc).isoformat()
                                with open(STATE_FILE, "w", encoding="utf-8") as f:
                                    json.dump(s, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

                # Check if authenticated
                if page.locator("div#pane-side, div[data-testid='chat-list'], header").count() > 0:
                    logged_in = True
                    break
                time.sleep(1.5)

            if logged_in:
                logger.info("🎉 WhatsApp Web Authenticated successfully on desktop! Flushing session...")
                time.sleep(3) # Allow cookies and IndexedDB to settle
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
