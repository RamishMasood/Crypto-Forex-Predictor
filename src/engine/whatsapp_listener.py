"""
WhatsApp Web Persistent Listener using Playwright.
Renders login QR code, maintains persistent browser session in .whatsapp_web_session/,
monitors selected signal channel, and routes incoming messages to the AI Parser and MT5 Executor.
"""

import os
import time
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone

from src.engine.whatsapp_signal_parser import WhatsAppSignalParser
from src.engine.whatsapp_signal_executor import WhatsAppSignalExecutor

logger = logging.getLogger("WhatsAppListener")

SESSION_DIR = ".whatsapp_web_session"
QR_IMAGE_PATH = ".whatsapp_qr.png"
STATE_FILE = ".whatsapp_signal_state.json"
SETTINGS_FILE = ".whatsapp_signal_settings.json"

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
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.sync_channels_event = threading.Event()
        self.pending_channel_switch: Optional[str] = None
        self.is_syncing_channels = False
        self.is_running = False
        self.seen_messages = set()
        self.recent_channel_messages: List[str] = []
        self._sync_settings()

    def request_channel_sync(self) -> Dict[str, Any]:
        """
        Triggers followed channels discovery.
        If background worker is active, signals live Playwright page.
        If stopped, launches a brief standalone discovery thread.
        """
        if self.is_running:
            self.sync_channels_event.set()
            return {"success": True, "mode": "online", "message": "Channel sync signaled to running listener"}
        else:
            def _standalone_task():
                self.is_syncing_channels = True
                try:
                    self._discover_channels_standalone()
                finally:
                    self.is_syncing_channels = False
            t = threading.Thread(target=_standalone_task, daemon=True, name="WhatsAppStandaloneChannelSync")
            t.start()
            return {"success": True, "mode": "offline", "message": "Offline channel discovery started"}

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
        state["is_worker_running"] = self.is_running
        state["has_qr"] = os.path.exists(QR_IMAGE_PATH)
        return state

    def start(self):
        """Starts background monitoring thread."""
        with self._lock:
            if self.is_running:
                logger.info("WhatsApp listener is already running.")
                return
            self.stop_event.clear()
            self._sync_settings()
            self.thread = threading.Thread(target=self._worker_loop, daemon=True, name="WhatsAppListenerWorker")
            self.thread.start()
            self.is_running = True
            logger.info("WhatsApp listener thread started.")

    def open_desktop_login_window(self) -> Dict[str, Any]:
        """
        Launches Chromium in visible mode (headless=False) so the user can scan the official
        WhatsApp Web QR code on their desktop screen with zero latency, no camera glare, and automatic refresh.
        Once authenticated, it saves the session to .whatsapp_web_session/ and closes.
        """
        if self.is_running:
            self.stop()
            time.sleep(1.5)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"success": False, "error": "Playwright is not installed."}

        state = self.executor.load_state()
        state["status"] = "AWAITING_DESKTOP_LOGIN"
        self.executor.save_state(state)

        def _desktop_thread():
            logger.info("Opening desktop visible WhatsApp login window...")
            try:
                with sync_playwright() as p:
                    os.makedirs(SESSION_DIR, exist_ok=True)
                    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ctx = p.chromium.launch_persistent_context(
                        user_data_dir=SESSION_DIR,
                        headless=False,
                        user_agent=user_agent,
                        args=["--disable-blink-features=AutomationControlled"],
                        viewport={"width": 1100, "height": 800}
                    )
                    try:
                        page = ctx.pages[0] if ctx.pages else ctx.new_page()
                        page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=60000)

                        logged_in = False
                        # Wait up to 180 seconds for user to scan
                        for _ in range(90):
                            if page.locator("div#pane-side, div[data-testid='chat-list'], header").count() > 0:
                                logged_in = True
                                break
                            time.sleep(2)

                        if logged_in:
                            logger.info("WhatsApp Authenticated via desktop window! Flushing session...")
                            time.sleep(3)
                            s = self.executor.load_state()
                            s["status"] = "AUTHENTICATED"
                            self.executor.save_state(s)
                            if os.path.exists(QR_IMAGE_PATH):
                                try:
                                    os.remove(QR_IMAGE_PATH)
                                except Exception:
                                    pass
                        else:
                            s = self.executor.load_state()
                            s["status"] = "LOGIN_TIMED_OUT"
                            self.executor.save_state(s)
                    finally:
                        try:
                            ctx.close()
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"Error in desktop WhatsApp login: {e}")
                s = self.executor.load_state()
                s["status"] = f"DESKTOP_LOGIN_ERROR: {str(e)[:60]}"
                self.executor.save_state(s)

        t = threading.Thread(target=_desktop_thread, daemon=True, name="WhatsAppDesktopLogin")
        t.start()
        return {"success": True, "message": "Desktop WhatsApp login window launched"}

    def stop(self):
        """Stops background monitoring thread."""
        with self._lock:
            if not self.is_running:
                return
            self.stop_event.set()
            self.is_running = False
            state = self.executor.load_state()
            state["status"] = "STOPPED"
            self.executor.save_state(state)
            logger.info("WhatsApp listener stopping...")


    def process_message_now(self, message_text: str, quoted_text: Optional[str] = None, msg_time: Optional[str] = None) -> Dict[str, Any]:
        """
        Public method to parse and execute a message immediately (Live or Simulated)
        with full quoted reply context and channel history.
        """
        self._sync_settings()
        clean_text = message_text.strip()
        if not clean_text:
            return {"success": False, "error": "Empty message"}

        # Fetch live MT5 open positions for context
        open_positions = self.executor.executor.get_open_positions()

        # Send to Gemini Flash AI Parser with quoted context & history
        parsed = self.parser.parse_message(
            message_text=clean_text,
            quoted_text=quoted_text,
            recent_history=self.recent_channel_messages,
            open_trades=open_positions
        )

        # Store in rolling history buffer with time and reply links
        now_time_str = msg_time or datetime.now(timezone.utc).strftime("%H:%M")
        self.recent_channel_messages.append({
            "time": now_time_str,
            "text": clean_text,
            "quoted_text": quoted_text
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

    def _worker_loop(self):
        """Main Playwright loop running in background."""
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
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=True,
                user_agent=user_agent,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 850},
                device_scale_factor=2
            )

            try:
                page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
                page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=45000)

                # Wait for either QR Canvas or Chat Pane
                logged_in = False
                qr_rendered = False

                for _ in range(35):
                    if self.stop_event.is_set():
                        break

                    # Check if already authenticated
                    if page.locator("div#pane-side, div[data-testid='chat-list'], header").count() > 0:
                        logged_in = True
                        break

                    # Check for reload button overlay if QR expired
                    reload_btn = page.locator("div[data-ref] button, div[data-ref] [role='button'], span[data-icon='reload'], span[data-icon='refresh']").first
                    if reload_btn.count() > 0 and reload_btn.is_visible():
                        try:
                            reload_btn.click()
                            logger.info("Auto-clicked WhatsApp QR reload button overlay.")
                            time.sleep(1.5)
                        except Exception:
                            pass

                    # Check for QR canvas
                    canvas_locator = page.locator("canvas")
                    if canvas_locator.count() > 0:
                        try:
                            canvas_locator.first.screenshot(path=QR_IMAGE_PATH)
                            qr_rendered = True
                            state = self.executor.load_state()
                            state["status"] = "AWAITING_QR_SCAN"
                            state["qr_updated_at"] = datetime.now(timezone.utc).isoformat()
                            self.executor.save_state(state)
                        except Exception as qr_err:
                            logger.debug(f"QR screenshot capture retry: {qr_err}")

                    time.sleep(2)

                if self.stop_event.is_set():
                    browser_context.close()
                    return

                # Wait for user scan if not yet logged in
                if not logged_in and qr_rendered:
                    logger.info("Awaiting QR code scan by user from WhatsApp mobile...")
                    while not self.stop_event.is_set():
                        if page.locator("div#pane-side, div[data-testid='chat-list'], header").count() > 0:
                            logged_in = True
                            break

                        # Auto-click reload overlay if expired
                        try:
                            reload_btn = page.locator("div[data-ref] button, div[data-ref] [role='button'], span[data-icon='reload'], span[data-icon='refresh']").first
                            if reload_btn.count() > 0 and reload_btn.is_visible():
                                reload_btn.click()
                                logger.info("Clicked QR reload overlay in wait loop.")
                                time.sleep(2)
                        except Exception:
                            pass

                        # Periodically refresh QR screenshot
                        try:
                            canvas_el = page.locator("canvas").first
                            if canvas_el.count() > 0 and canvas_el.is_visible():
                                canvas_el.screenshot(path=QR_IMAGE_PATH)
                                state = self.executor.load_state()
                                state["qr_updated_at"] = datetime.now(timezone.utc).isoformat()
                                self.executor.save_state(state)
                        except Exception:
                            pass
                        time.sleep(2.5)

                if logged_in:
                    logger.info("WhatsApp Web Authenticated successfully!")
                    if os.path.exists(QR_IMAGE_PATH):
                        try:
                            os.remove(QR_IMAGE_PATH)
                        except Exception:
                            pass

                    settings = self.executor.load_settings()
                    target_channel = settings.get("selected_channel", "Tradingpapa.com forex (gold and silver)")

                    state = self.executor.load_state()
                    state["status"] = "CONNECTED"
                    state["connected_channel"] = target_channel
                    self.executor.save_state(state)

                    # 1. Automatically discover followed channels on connect
                    try:
                        self._discover_followed_channels(page)
                    except Exception as disc_err:
                        logger.warning(f"Initial channel discovery error: {disc_err}")

                    # 2. Open target channel / chat
                    self._open_channel(page, target_channel)

                    # Continuous message polling loop
                    while not self.stop_event.is_set():
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
                        time.sleep(3)

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

    def _open_channel(self, page, channel_name: str):
        """Searches or clicks on the specified channel."""
        try:
            time.sleep(2)
            # Try finding the chat in the sidebar list directly
            channel_locator = page.locator(f"span[title*='{channel_name[:15]}'], div[title*='{channel_name[:15]}']").first
            if channel_locator.count() > 0:
                channel_locator.click()
                logger.info(f"Opened channel: {channel_name}")
                state = self.executor.load_state()
                state["connected_channel"] = channel_name
                self.executor.save_state(state)
                return

            # Use search bar
            search_box = page.locator("div[contenteditable='true'][data-tab='3'], div[contenteditable='true']").first
            if search_box.count() > 0:
                search_box.click()
                search_box.fill(channel_name)
                time.sleep(2)
                result_item = page.locator(f"span[title*='{channel_name[:15]}'], div[role='listitem']").first
                if result_item.count() > 0:
                    result_item.click()
                    logger.info(f"Successfully found and opened channel: {channel_name}")
                    state = self.executor.load_state()
                    state["connected_channel"] = channel_name
                    self.executor.save_state(state)
        except Exception as e:
            logger.warning(f"Could not automatically open channel '{channel_name}': {e}")

    def _extract_channel_names_from_page(self, page) -> List[str]:
        """Helper to extract clean channel titles from current WhatsApp Web DOM."""
        names = set()
        locators_to_try = [
            "div#pane-side span[title]",
            "div[role='listitem'] span[title]",
            "div[data-testid='cell-frame-title'] span",
            "div[role='gridcell'] span[title]",
            "div[role='listitem'] span[dir='auto']",
            "header span[title]"
        ]
        system_words = {
            "channels", "find channels", "stay updated", "explore", "search", 
            "directory", "updates", "status", "chats", "communities", "settings",
            "new chat", "menu", "unread", "draft", "typing...", "online"
        }
        for sel in locators_to_try:
            try:
                for el in page.locator(sel).all():
                    try:
                        t = (el.get_attribute("title") or el.inner_text() or "").strip()
                        if not t or len(t) < 2 or len(t) > 75:
                            continue
                        if t.isdigit() or (":" in t and len(t) <= 8):
                            continue
                        if t.lower() in system_words:
                            continue
                        names.add(t)
                    except Exception:
                        pass
            except Exception:
                pass
        return list(names)

    def _discover_followed_channels(self, page) -> List[str]:
        """
        Discovers all followed channels in WhatsApp Web by:
        1. Checking existing visible chat/channel items.
        2. Clicking the Channels/Newsletters navigation tab if available.
        3. Extracting all channel names from the Channels pane.
        4. Switching back to Chats tab.
        """
        all_channels = set()
        
        # 1. Collect currently visible channels/chats
        try:
            initial_names = self._extract_channel_names_from_page(page)
            all_channels.update(initial_names)
        except Exception as e:
            logger.debug(f"Initial channel extraction: {e}")

        # 2. Click Channels / Newsletters tab on the left navigation rail
        try:
            channels_tab = page.locator("button[aria-label*='Channel'], button[aria-label*='channel'], button[title*='Channel'], span[data-icon*='newsletter'], button[aria-label*='Newsletter'], span[data-icon='newsletter-outline']").first
            if channels_tab.count() > 0:
                channels_tab.click()
                time.sleep(2.5)
                
                # Extract names in the Channels pane
                channel_names = self._extract_channel_names_from_page(page)
                all_channels.update(channel_names)
                
                # Switch back to Chats tab
                chats_tab = page.locator("button[aria-label*='Chat'], button[aria-label*='chat'], button[title*='Chats'], span[data-icon*='chats'], span[data-icon='chat']").first
                if chats_tab.count() > 0:
                    chats_tab.click()
                    time.sleep(1.5)
        except Exception as e:
            logger.warning(f"Error navigating to Channels tab: {e}")

        # Ensure tradingpapa and current setting are preserved
        settings = self.executor.load_settings()
        curr = settings.get("selected_channel")
        if curr:
            all_channels.add(curr)
        all_channels.add("Tradingpapa.com forex (gold and silver)")

        def _sort_key(c_name):
            low = c_name.lower()
            if "tradingpapa" in low:
                return (0, low)
            if any(k in low for k in ["forex", "gold", "crypto", "trading", "signal"]):
                return (1, low)
            return (2, low)

        sorted_channels = sorted(list(all_channels), key=_sort_key)
        
        state = self.executor.load_state()
        state["followed_channels"] = sorted_channels
        self.executor.save_state(state)
        logger.info(f"Discovered {len(sorted_channels)} WhatsApp channels/chats: {sorted_channels}")
        return sorted_channels

    def _discover_channels_standalone(self) -> List[str]:
        """Quick standalone discovery pass when listener is stopped."""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=SESSION_DIR,
                    headless=True,
                    user_agent=user_agent,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 850}
                )
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=45000)
                    for _ in range(15):
                        if page.locator("div#pane-side, div[data-testid='chat-list'], header").count() > 0:
                            break
                        time.sleep(1)
                    return self._discover_followed_channels(page)
                finally:
                    try:
                        ctx.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Standalone channel discovery error: {e}")
            return []


    def _poll_channel_messages(self, page):
        """Scrapes newly arrived messages (including quoted reply text and timestamps) from open chat pane."""
        try:
            # Query message container elements
            containers = page.locator("div[data-testid='msg-container'], div.message-in").all()
            if not containers:
                return

            # Read latest 15 containers
            for container in containers[-15:]:
                try:
                    text_elem = container.locator("span.selectable-text").first
                    txt = text_elem.inner_text().strip() if text_elem.count() > 0 else ""
                    if not txt:
                        continue

                    # Extract quoted reply text if this message is a reply to an earlier setup
                    quote_elem = container.locator("div[data-testid='quoted-message'], div[aria-label*='Quoted'], div._amkd").first
                    quoted_text = quote_elem.inner_text().strip() if quote_elem.count() > 0 else None

                    # Extract timestamp
                    time_elem = container.locator("div[data-testid='msg-meta'] span, span[data-testid='msg-meta']").first
                    msg_time = time_elem.inner_text().strip() if time_elem.count() > 0 else ""

                    q_snippet = quoted_text[:20] if quoted_text else ""
                    msg_hash = f"{txt[:50]}_{len(txt)}_{q_snippet}"
                    if msg_hash not in self.seen_messages:
                        self.seen_messages.add(msg_hash)
                        logger.info(f"New incoming WhatsApp message detected: {txt[:60]} (Quoted: {q_snippet})...")
                        # Process message with full reply context
                        self.process_message_now(txt, quoted_text=quoted_text, msg_time=msg_time)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Polling channel error: {e}")
