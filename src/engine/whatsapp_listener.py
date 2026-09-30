"""
WhatsApp Web Persistent Listener using Playwright.
Renders login QR code, maintains persistent browser session in .whatsapp_web_session/,
monitors selected signal channel, and routes incoming messages to the AI Parser and MT5 Executor.
"""

import os
import sys
import time
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone

from src.engine.whatsapp_signal_parser import WhatsAppSignalParser
from src.engine.whatsapp_signal_executor import WhatsAppSignalExecutor

try:
    from src.utils.env_loader import load_env
    load_env()
except Exception:
    pass

logger = logging.getLogger("WhatsAppListener")

SESSION_DIR = ".whatsapp_web_session"
QR_IMAGE_PATH = ".whatsapp_qr.png"
STATE_FILE = ".whatsapp_signal_state.json"
SETTINGS_FILE = ".whatsapp_signal_settings.json"

def cleanup_orphaned_sessions(session_dir: str = SESSION_DIR):
    """
    Kills any lingering chrome, chrome-headless-shell, whatsapp_worker, or whatsapp_desktop_login processes holding
    the session directory lock and cleanly removes singleton lock files to guarantee a fast, unblocked start.
    """
    try:
        import psutil
        current_pid = os.getpid()
        parent_pid = os.getppid() if hasattr(os, 'getppid') else None
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pid = p.info.get('pid')
                if pid in [current_pid, parent_pid]:
                    continue
                name = (p.info.get('name') or '').lower()
                cmd = ""
                try:
                    cmd = " ".join(p.info.get('cmdline') or []).lower()
                except Exception:
                    pass
                if 'python' in name and ('whatsapp_worker' in cmd or 'whatsapp_desktop_login' in cmd):
                    p.kill()
                elif 'chrome-headless-shell' in name or ('chrome' in name and (session_dir.lower() in cmd or 'ms-playwright' in cmd or 'playwright' in cmd)):
                    p.kill()
            except Exception:
                pass
    except Exception:
        pass

    if os.path.exists(session_dir):
        for root, dirs, files in os.walk(session_dir):
            for f in files:
                if f in ["SingletonLock", "SingletonCookie", "SingletonSocket", "LOCK"] or f.endswith(".lock"):
                    try:
                        os.remove(os.path.join(root, f))
                    except Exception:
                        pass

class WhatsAppListenerEngine:
    """
    Background worker managing Playwright browser session for WhatsApp Web.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(WhatsAppListenerEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.parser = WhatsAppSignalParser()
        self.executor = WhatsAppSignalExecutor()
        self.worker_process = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.sync_channels_event = threading.Event()
        self.pending_channel_switch: Optional[str] = None
        self.is_syncing_channels = False
        self.seen_messages = set()
        self.recent_channel_messages: List[str] = []
        self._sync_settings()

    @property
    def is_running(self) -> bool:
        if self.worker_process and self.worker_process.poll() is None:
            return True
        state = self.executor.load_state()
        pid = state.get("worker_pid")
        if pid:
            try:
                import psutil
                if psutil.pid_exists(pid):
                    p = psutil.Process(pid)
                    if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                        return True
            except Exception:
                pass
            if sys.platform == "win32":
                try:
                    import ctypes
                    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
                    if handle:
                        code = ctypes.c_ulong()
                        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
                        ctypes.windll.kernel32.CloseHandle(handle)
                        if code.value == 259:
                            return True
                except Exception:
                    pass
        return False

    def request_channel_sync(self) -> Dict[str, Any]:
        """
        Triggers followed channels discovery.
        Signals live worker via state file, or runs brief standalone discovery if stopped.
        """
        if self.is_running:
            self.sync_channels_event.set()
            state = self.executor.load_state()
            state["request_channel_sync"] = True
            self.executor.save_state(state)
            return {"success": True, "mode": "online", "message": "Channel sync signaled to running listener"}
        else:
            import subprocess
            import sys
            sync_script = os.path.join(os.path.dirname(__file__), "whatsapp_standalone_sync.py")
            subprocess.Popen([sys.executable, "-u", sync_script])
            state = self.executor.load_state()
            state["is_syncing_channels"] = True
            self.executor.save_state(state)
            return {"success": True, "mode": "standalone", "message": "Offline channel discovery subprocess launched"}

    def switch_channel(self, channel_name: str):
        """Switches active channel to monitor."""
        clean_name = channel_name.strip()
        if not clean_name:
            return
        self.pending_channel_switch = clean_name
        settings = self.executor.load_settings()
        settings["selected_channel"] = clean_name
        self.executor.save_settings(settings)

    def _sync_settings(self):
        settings = self.executor.load_settings()
        api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
        self.parser.set_api_key(api_key)

    def get_status(self) -> Dict[str, Any]:
        state = self.executor.load_state()
        is_alive = self.is_running
        state["is_worker_running"] = is_alive
        state["has_qr"] = os.path.exists(QR_IMAGE_PATH)
        return state

    def start(self):
        """Starts dedicated WhatsApp worker subprocess with isolated Proactor loop."""
        with self._lock:
            if self.is_running:
                logger.info("WhatsApp worker process is already running.")
                return
            self.stop_event.clear()
            self._sync_settings()
            cleanup_orphaned_sessions(SESSION_DIR)

            import subprocess
            import sys
            worker_path = os.path.join(os.path.dirname(__file__), "whatsapp_worker.py")
            cflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            self.worker_process = subprocess.Popen([sys.executable, "-u", worker_path], creationflags=cflags)
            state = self.executor.load_state()
            state["worker_pid"] = self.worker_process.pid
            state["status"] = "INITIALIZING"
            self.executor.save_state(state)
            logger.info(f"WhatsApp worker process started (PID {self.worker_process.pid}).")

    def open_desktop_login_window(self) -> Dict[str, Any]:
        """
        Launches WhatsApp Web login window on desktop so the user can scan the official
        WhatsApp Web QR code directly on their screen with zero latency and automatic refresh.
        """
        self.stop()
        time.sleep(0.8)
        import subprocess
        import sys
        desktop_script = os.path.join(os.path.dirname(__file__), "whatsapp_desktop_login.py")
        proc = subprocess.Popen([sys.executable, "-u", desktop_script])
        state = self.executor.load_state()
        state["desktop_pid"] = proc.pid
        state["status"] = "AWAITING_DESKTOP_LOGIN"
        self.executor.save_state(state)
        return {"success": True, "message": "WhatsApp desktop login window launched"}

    def stop(self):
        """Stops WhatsApp worker subprocess and cleanly terminates browser sessions."""
        with self._lock:
            state = self.executor.load_state()
            for pid_key in ["worker_pid", "desktop_pid"]:
                pid = state.get(pid_key)
                if pid:
                    try:
                        import psutil
                        if psutil.pid_exists(pid):
                            p = psutil.Process(pid)
                            p.terminate()
                            p.wait(timeout=2.0)
                    except Exception:
                        try:
                            p.kill()
                        except Exception:
                            pass
                    state[pid_key] = None

            if self.worker_process:
                try:
                    self.worker_process.terminate()
                    self.worker_process.wait(timeout=2.0)
                except Exception:
                    try:
                        self.worker_process.kill()
                    except Exception:
                        pass
                self.worker_process = None

            state["status"] = "STOPPED"
            self.executor.save_state(state)
            logger.info("WhatsApp listener stopping...")

        cleanup_orphaned_sessions(SESSION_DIR)

    def reset_session(self) -> Dict[str, Any]:
        """
        Kills any orphaned Playwright processes, wipes corrupt locks, and removes stale session data
        so a clean, unlocked QR pairing handshake can succeed immediately.
        """
        self.stop()
        cleanup_orphaned_sessions(SESSION_DIR)

        import shutil
        if os.path.exists(SESSION_DIR):
            try:
                shutil.rmtree(SESSION_DIR, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Error removing session dir: {e}")
        if os.path.exists(QR_IMAGE_PATH):
            try:
                os.remove(QR_IMAGE_PATH)
            except Exception:
                pass
        state = self.executor.load_state()
        state["status"] = "STOPPED"
        state["connected_channel"] = None
        self.executor.save_state(state)
        return {"success": True, "message": "WhatsApp session cleanly reset."}

    def logout(self) -> Dict[str, Any]:
        """
        Logs out of the current WhatsApp Web account, kills running browser sessions,
        wipes saved credentials from .whatsapp_web_session/, removes any stale QR file,
        and cleanly sets status to STOPPED.
        """
        logger.info("Logging out from WhatsApp Web...")
        self.stop()
        cleanup_orphaned_sessions(SESSION_DIR)

        import shutil
        if os.path.exists(SESSION_DIR):
            try:
                shutil.rmtree(SESSION_DIR, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Error removing session dir: {e}")
        if os.path.exists(QR_IMAGE_PATH):
            try:
                os.remove(QR_IMAGE_PATH)
            except Exception:
                pass

        state = self.executor.load_state()
        state["status"] = "STOPPED"
        state["connected_channel"] = None
        self.executor.save_state(state)
        logger.info("WhatsApp logout complete.")
        return {"success": True, "message": "Successfully logged out from WhatsApp."}



    def process_message_now(
        self,
        message_text: str,
        quoted_text: Optional[str] = None,
        msg_time: Optional[str] = None,
        image_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Public method to parse and execute a message immediately (Live or Simulated)
        with full quoted reply context, channel history, channel name, and optional multimodal screenshot.
        """
        self._sync_settings()
        clean_text = (message_text or "").strip()
        has_image = bool(image_path and os.path.exists(image_path))

        if not clean_text and not has_image:
            return {"success": False, "error": "Empty message"}

        if not clean_text and has_image:
            clean_text = "[Screenshot / Image Attachment]"

        state = self.executor.load_state()
        settings = self.executor.load_settings()
        channel_name = settings.get("selected_channel") or state.get("connected_channel") or ""

        # Fetch live MT5 open WhatsApp positions for context (strictly isolated from Autonomous Engine)
        open_positions = self.executor.get_open_whatsapp_positions()

        # Send to Gemini Flash AI Parser with quoted context, history, channel name & image
        parsed = self.parser.parse_message(
            message_text=clean_text,
            quoted_text=quoted_text,
            recent_history=self.recent_channel_messages,
            open_trades=open_positions,
            channel_name=channel_name,
            image_path=image_path
        )

        # Store in rolling history buffer with time, reply links, and image flag
        now_time_str = msg_time or datetime.now(timezone.utc).strftime("%H:%M")
        self.recent_channel_messages.append({
            "time": now_time_str,
            "text": clean_text,
            "quoted_text": quoted_text,
            "has_image": has_image
        })
        if len(self.recent_channel_messages) > 30:
            self.recent_channel_messages.pop(0)

        # Execute via MT5 Trade Executor
        exec_res = self.executor.execute_parsed_signal(parsed, clean_text)

        # Update last processed message in state
        state = self.executor.load_state()
        state["last_message_processed"] = {
            "text": clean_text,
            "quoted_text": quoted_text,
            "image_path": image_path,
            "parsed": parsed,
            "result": exec_res,
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        }
        self.executor.save_state(state)

        return {
            "success": exec_res.get("success", False),
            "parsed": parsed,
            "execution": exec_res
        }

    def _capture_and_generate_qr(self, page) -> bool:
        """
        Captures the live WhatsApp Web QR code with maximum clarity and zero expiration lag:
        1. Auto-clicks reload button if expired.
        2. Direct pixel-perfect screenshot of the live WhatsApp Web canvas.
        3. Fallback to extracting data-ref token and generating lossless QR image.
        4. Updates state with `qr_updated_at` timestamp.
        """
        try:
            # If already logged in, do not capture QR
            is_auth = False
            try:
                is_auth = page.evaluate("""() => Boolean(
                    document.querySelector('div#pane-side') ||
                    document.querySelector('header') ||
                    document.querySelector('[data-testid="chat-list"]') ||
                    (window.localStorage && (window.localStorage.getItem('last-wid') || window.localStorage.getItem('last-wid-md')))
                )""")
            except Exception:
                pass
            if is_auth:
                return False

            # Check for expired QR reload button overlay and auto-click it immediately
            reload_selectors = [
                "button:has-text('Reload')",
                "[role='button']:has-text('Reload')",
                "span[data-icon='reload']",
                "span[data-icon='refresh']",
                "div[data-testid='link-device-qr-code'] button",
                "div[data-testid='link-device-qr-code'] [role='button']",
                "div[data-ref] button",
                "div[data-ref] [role='button']"
            ]
            for sel in reload_selectors:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    try:
                        btn.click()
                        time.sleep(0.8)
                        break
                    except Exception:
                        pass

            captured = False
            # Method 1: Capture the exact, crisp live canvas / QR container rendered by WhatsApp
            qr_box = page.locator("div[data-testid='link-device-qr-code'], div[data-testid='link-device-qr-code'] canvas, canvas").first
            if qr_box.count() > 0 and qr_box.is_visible():
                box = qr_box.bounding_box()
                if box and box.get("width", 0) > 60:
                    try:
                        qr_box.screenshot(path=QR_IMAGE_PATH)
                        captured = True
                    except Exception as c_err:
                        logger.debug(f"QR screenshot error: {c_err}")

            # Method 2: If screenshot failed, extract data-ref and generate via qrcode
            if not captured:
                data_ref_elem = page.locator("div[data-testid='link-device-qr-code'], div[data-ref]").first
                if data_ref_elem.count() > 0:
                    data_ref = data_ref_elem.get_attribute("data-ref")
                    if data_ref and len(data_ref) > 15:
                        try:
                            import qrcode
                            qr = qrcode.QRCode(
                                version=None,
                                error_correction=qrcode.constants.ERROR_CORRECT_M,
                                box_size=10,
                                border=2,
                            )
                            qr.add_data(data_ref)
                            qr.make(fit=True)
                            img = qr.make_image(fill_color="black", back_color="white")
                            img.save(QR_IMAGE_PATH)
                            captured = True
                        except Exception as qr_err:
                            logger.debug(f"Direct QR code generation fallback: {qr_err}")

            if captured:
                state = self.executor.load_state()
                if state.get("status") not in ["AUTHENTICATED", "CONNECTED"]:
                    state["status"] = "AWAITING_QR_SCAN"
                state["qr_updated_at"] = datetime.now(timezone.utc).isoformat()
                self.executor.save_state(state)
                return True
        except Exception as e:
            logger.debug(f"Error capturing QR: {e}")
        return False

    def _worker_loop(self):
        """Main Playwright loop running with clean Chromium context and live QR streaming."""
        import sys
        import asyncio
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

        state = self.executor.load_state()
        state["status"] = "INITIALIZING"
        self.executor.save_state(state)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright is not installed.")
            state["status"] = "ERROR_NO_PLAYWRIGHT"
            self.executor.save_state(state)
            self.is_running = False
            return

        with sync_playwright() as p:
            os.makedirs(SESSION_DIR, exist_ok=True)
            browser_args = [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1100,800"
            ]

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

            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=True,
                user_agent=user_agent,
                args=browser_args,
                viewport={"width": 1280, "height": 850}
            )

            # Mask webdriver and inject modern Chrome 133 userAgentData
            browser_context.add_init_script("""
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
                page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
                page.goto("https://web.whatsapp.com", wait_until="load", timeout=45000)

                logged_in = False

                while not self.stop_event.is_set():
                    # 1. Multi-attribute check for authenticated state
                    is_authenticated = False
                    try:
                        is_authenticated = page.evaluate("""() => Boolean(
                            document.querySelector('div#pane-side') ||
                            document.querySelector('header') ||
                            document.querySelector('[data-testid="chat-list"]') ||
                            document.querySelector('[data-testid="conversation-panel-wrapper"]') ||
                            (window.localStorage && (window.localStorage.getItem('last-wid') || window.localStorage.getItem('last-wid-md')))
                        )""")
                    except Exception:
                        pass

                    if is_authenticated:
                        logged_in = True
                        break

                    # 2. Capture / refresh live QR code first whenever visible
                    qr_captured = self._capture_and_generate_qr(page)
                    if qr_captured:
                        time.sleep(1.2)
                        continue

                    # 3. Only if no QR is on screen, check if phone scanned and chats are syncing
                    is_connecting = False
                    try:
                        is_connecting = page.evaluate("""() => {
                            const hasQr = Boolean(
                                document.querySelector('canvas') ||
                                document.querySelector('[data-testid="link-device-qr-code"]') ||
                                document.querySelector('div[data-ref]')
                            );
                            if (hasQr) return false;

                            const text = document.body ? document.body.innerText : '';
                            return Boolean(
                                text.includes('Loading your chats') ||
                                text.includes('Organizing messages') ||
                                text.includes('Chats loading') ||
                                document.querySelector('[data-icon="connecting"]') ||
                                document.querySelector('div[role="progressbar"]') ||
                                document.querySelector('progress')
                            );
                        }""")
                    except Exception:
                        pass

                    if is_connecting:
                        state = self.executor.load_state()
                        if state.get("status") != "CONNECTING":
                            state["status"] = "CONNECTING"
                            self.executor.save_state(state)
                        if os.path.exists(QR_IMAGE_PATH):
                            try:
                                os.remove(QR_IMAGE_PATH)
                            except Exception:
                                pass
                        time.sleep(1.2)
                        continue

                    time.sleep(1.0)

                if logged_in:
                    logger.info("🎉 WhatsApp Web Authenticated successfully!")
                    if os.path.exists(QR_IMAGE_PATH):
                        try:
                            os.remove(QR_IMAGE_PATH)
                        except Exception:
                            pass

                    settings = self.executor.load_settings()
                    target_channel = settings.get("selected_channel", "Tradingpapa.com crypto")

                    # IMMEDIATELY write CONNECTED state so Streamlit UI updates instantly!
                    state = self.executor.load_state()
                    state["status"] = "CONNECTED"
                    state["connected_channel"] = target_channel
                    self.executor.save_state(state)

                    # Discover followed channels if not already cached (sequential, safe in same thread)
                    if len(state.get("followed_channels", [])) == 0:
                        try:
                            self._discover_followed_channels(page)
                        except Exception as disc_err:
                            logger.warning(f"Initial channel discovery error: {disc_err}")

                    # Open target channel / chat
                    try:
                        self._open_channel(page, target_channel)
                    except Exception as open_err:
                        logger.warning(f"Error opening channel {target_channel}: {open_err}")

                    # Continuous message polling loop (0.4s fast polling for near-instant message detection)
                    while not self.stop_event.is_set():
                        # Strict disconnect check: ONLY trigger if chat list is GONE AND QR canvas is VISIBLE
                        is_chat_list_present = False
                        try:
                            is_chat_list_present = page.evaluate("""() => Boolean(
                                document.querySelector('div#pane-side') ||
                                document.querySelector('header') ||
                                document.querySelector('[data-testid="chat-list"]') ||
                                (window.localStorage && (window.localStorage.getItem('last-wid') || window.localStorage.getItem('last-wid-md')))
                            )""")
                        except Exception:
                            pass

                        qr_visible = False
                        try:
                            qr_visible = (
                                page.locator("div[data-testid='link-device-qr-code'] canvas").is_visible()
                                or page.locator("canvas[aria-label*='Scan']").is_visible()
                            )
                        except Exception:
                            pass

                        if not is_chat_list_present and qr_visible:
                            logger.warning("WhatsApp Web session disconnected / awaiting QR scan!")
                            self._capture_and_generate_qr(page)
                            break

                        # Handle live on-demand channel sync
                        if self.sync_channels_event.is_set():
                            self.sync_channels_event.clear()
                            try:
                                self._discover_followed_channels(page)
                            except Exception as sync_e:
                                logger.warning(f"Dynamic channel sync error: {sync_e}")
                            settings = self.executor.load_settings()
                            target_channel = settings.get("selected_channel", "Tradingpapa.com forex (gold and silver)")
                            self._open_channel(page, target_channel)

                        # Handle dynamic channel switch
                        if self.pending_channel_switch:
                            target = self.pending_channel_switch
                            self.pending_channel_switch = None
                            self._open_channel(page, target)

                        self._poll_channel_messages(page)
                        time.sleep(0.4)

            except Exception as e:
                logger.error(f"Error in WhatsApp worker: {e}", exc_info=True)
                state = self.executor.load_state()
                state["status"] = f"ERROR: {str(e)[:100]}"
                self.executor.save_state(state)
            finally:
                try:
                    browser_context.close()
                except Exception:
                    pass
                self.is_running = False

    def _scroll_chat_to_bottom(self, page):
        """Scrolls open conversation pane to bottom so newest live messages are in DOM."""
        try:
            page.evaluate("""() => {
                const pane = document.querySelector('div[data-testid="conversation-panel-messages"], div[role="region"], div[tabindex="-1"], div._amkc');
                if (pane) pane.scrollTop = pane.scrollHeight;
            }""")
        except Exception:
            pass

    def _open_channel(self, page, channel_name: str):
        """Searches or clicks on the specified channel or group and scrolls to bottom."""
        clean_target = (
            channel_name.replace("📢 [Channel] ", "")
            .replace("👥 [Group] ", "")
            .replace("📢 ", "")
            .replace("👥 ", "")
            .strip()
        )
        try:
            time.sleep(1)
            # 1. Try finding in current sidebar list
            channel_locator = page.locator(f"span[title*='{clean_target[:15]}'], div[title*='{clean_target[:15]}']").first
            if channel_locator.count() > 0:
                channel_locator.click(force=True)
                logger.info(f"Opened channel/group directly: {clean_target}")
                state = self.executor.load_state()
                state["connected_channel"] = clean_target
                self.executor.save_state(state)
                time.sleep(1.5)
                self._scroll_chat_to_bottom(page)
                return

            # 2. Try Channels tab if not found on current tab
            chan_tab_btn = page.locator("button[aria-label='Channels'], [data-navbar-item='true'][aria-label*='Channel']").first
            if chan_tab_btn.count() > 0:
                chan_tab_btn.click(force=True)
                time.sleep(1.5)
                chan_item = page.locator(f"span[title*='{clean_target[:15]}'], div[title*='{clean_target[:15]}']").first
                if chan_item.count() > 0:
                    chan_item.click(force=True)
                    logger.info(f"Opened channel via Channels tab: {clean_target}")
                    state = self.executor.load_state()
                    state["connected_channel"] = clean_target
                    self.executor.save_state(state)
                    time.sleep(1.5)
                    self._scroll_chat_to_bottom(page)
                    return

            # 3. Use search box
            search_box = page.locator("div[contenteditable='true']").first
            if search_box.count() > 0:
                search_box.click()
                search_box.fill(clean_target)
                time.sleep(2)
                result_item = page.locator(f"span[title*='{clean_target[:15]}'], div[role='listitem']").first
                if result_item.count() > 0:
                    result_item.click(force=True)
                    logger.info(f"Successfully found and opened channel/group via search: {clean_target}")
                    state = self.executor.load_state()
                    state["connected_channel"] = clean_target
                    self.executor.save_state(state)
                    time.sleep(1.5)
                    self._scroll_chat_to_bottom(page)
        except Exception as e:
            logger.warning(f"Could not automatically open channel '{clean_target}': {e}")

    def _is_valid_channel_or_chat_name(self, name: str) -> bool:
        from src.engine.whatsapp_worker import is_valid_channel_or_chat_name
        return is_valid_channel_or_chat_name(name)

    def _discover_followed_channels(self, page) -> List[str]:
        """
        Discovers all followed channels AND groups from WhatsApp Web:
        1. Navigates to Channels tab, scrolls down, and extracts broadcast channels.
        2. Navigates to Chats tab, scrolls down, and extracts trading groups.
        3. Saves both categories separately and in combined list.
        """
        from src.engine.whatsapp_worker import discover_followed_channels
        return discover_followed_channels(page, self.executor)

    def _discover_channels_standalone(self) -> List[str]:
        """Quick standalone discovery pass when listener is stopped."""
        try:
            import sys
            import asyncio
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                try:
                    asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            from playwright.sync_api import sync_playwright
            from src.engine.whatsapp_worker import discover_followed_channels
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
            with sync_playwright() as p:
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=SESSION_DIR,
                    headless=True,
                    user_agent=user_agent,
                    args=browser_args,
                    viewport={"width": 1280, "height": 850}
                )
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.goto("https://web.whatsapp.com", wait_until="load", timeout=45000)
                    for _ in range(15):
                        if page.locator("div#pane-side, div[data-testid='chat-list'], header").count() > 0:
                            break
                        time.sleep(1)
                    return discover_followed_channels(page, self.executor)
                finally:
                    try:
                        ctx.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Standalone channel discovery error: {e}")
            return []


    def _poll_channel_messages(self, page):
        try:
            # Check for real disconnect: ONLY trigger if chat list is GONE AND QR canvas is VISIBLE
            is_chat_list_present = False
            try:
                is_chat_list_present = page.evaluate("""() => Boolean(
                    document.querySelector('div#pane-side') ||
                    document.querySelector('header') ||
                    document.querySelector('[data-testid="chat-list"]') ||
                    (window.localStorage && (window.localStorage.getItem('last-wid') || window.localStorage.getItem('last-wid-md')))
                )""")
            except Exception:
                pass

            qr_visible = False
            try:
                qr_visible = (
                    page.locator("div[data-testid='link-device-qr-code'] canvas").is_visible()
                    or page.locator("canvas[aria-label*='Scan']").is_visible()
                )
            except Exception:
                pass

            if not is_chat_list_present and qr_visible:
                logger.warning("WhatsApp Web session disconnected / awaiting QR scan!")
                self._capture_and_generate_qr(page)
                return

            # 1. STRICT ACTIVE HEADER VERIFICATION:
            settings = self.executor.load_settings()
            target_channel = settings.get("selected_channel", "")
            active_title = ""
            try:
                active_title = page.evaluate("""() => {
                    const mainHeader = document.querySelector('#main header, div[data-testid="conversation-header"], header._amie, header');
                    if (!mainHeader) return "";
                    const titleEl = mainHeader.querySelector('span[title], div[role="button"] span[title], [data-testid="conversation-info-header"] span, span[dir="auto"]');
                    return titleEl ? (titleEl.getAttribute('title') || titleEl.innerText || '').trim() : "";
                }""") or ""
            except Exception:
                pass

            if target_channel:
                clean_target = (
                    target_channel.replace("📢 [Channel] ", "")
                    .replace("👥 [Group] ", "")
                    .replace("📢 ", "")
                    .replace("👥 ", "")
                    .strip()
                    .lower()
                )
                act = active_title.strip().lower()
                if clean_target not in act and act not in clean_target:
                    return

            # 2. STRICT CONVERSATION SCOPING:
            # ONLY locate message containers INSIDE active conversation pane (#main)!
            main_pane = page.locator("div#main, div[data-testid='conversation-panel-wrapper'], div[data-testid='conversation-panel-messages']").first
            if main_pane.count() == 0:
                return

            containers = main_pane.locator("div[data-testid='msg-container'], div.message-in, div.message-out").all()
            if not containers:
                return

            # Read latest 15 containers
            for container in containers[-15:]:
                try:
                    # Selectable text in broadcast channels or chats
                    text_elem = container.locator("span.selectable-text, span[dir='ltr'], span[dir='rtl'], div.copyable-text").first
                    txt = text_elem.inner_text().strip() if text_elem.count() > 0 else ""

                    # Detect image element inside container
                    img_elem = container.locator("img[src*='blob:'], img[src*='data:'], div[data-testid='image-thumb'] img, div._ak8l img, div._ak8o img, div[role='button'] img, div._amk4 img").first
                    has_image = img_elem.count() > 0 and img_elem.is_visible()
                    image_path = None

                    if not txt and not has_image:
                        continue

                    # If image is attached, capture lossless screenshot for Gemini Flash Multimodal inspection
                    if has_image:
                        try:
                            os.makedirs(".whatsapp_media", exist_ok=True)
                            image_path = os.path.abspath(f".whatsapp_media/wa_msg_{int(time.time()*1000)}.png")
                            img_elem.screenshot(path=image_path)
                            if not txt:
                                txt = "[Screenshot / Image Attachment]"
                        except Exception as img_err:
                            logger.debug(f"Failed to capture image snapshot: {img_err}")

                    # Extract quoted reply text if this message is a reply to an earlier setup
                    quote_elem = container.locator("div[data-testid='quoted-message'], div[aria-label*='Quoted'], div._amkd").first
                    quoted_text = quote_elem.inner_text().strip() if quote_elem.count() > 0 else None

                    # Extract timestamp
                    time_elem = container.locator("div[data-testid='msg-meta'] span, span[data-testid='msg-meta'], div._amkd").first
                    msg_time = time_elem.inner_text().strip() if time_elem.count() > 0 else ""

                    q_snippet = quoted_text[:20] if quoted_text else ""
                    has_img_flag = "1" if image_path else "0"
                    msg_hash = f"{txt[:60]}_{len(txt)}_{q_snippet}_{has_img_flag}"
                    if msg_hash not in self.seen_messages:
                        self.seen_messages.add(msg_hash)
                        logger.info(f"⚡ Live incoming WhatsApp message detected: {txt[:70]} (Image: {has_image}, Quoted: {q_snippet})...")
                        # Process message with full reply context & image attachment immediately
                        self.process_message_now(txt, quoted_text=quoted_text, msg_time=msg_time, image_path=image_path)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Polling channel error: {e}")
