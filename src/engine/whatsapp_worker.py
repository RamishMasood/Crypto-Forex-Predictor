"""
Dedicated WhatsApp Web Worker Process.
Runs in its own Python process on the main thread to ensure 100% reliable Playwright IocpProactor execution,
seamless live QR streaming to Streamlit, automated anti-expiration reload, and zero GIL/thread-safety issues.
"""

import os
import sys
import time
import json
import logging
import signal
from datetime import datetime, timezone

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.engine.whatsapp_signal_parser import WhatsAppSignalParser
from src.engine.whatsapp_signal_executor import WhatsAppSignalExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("WhatsAppWorker")

SESSION_DIR = ".whatsapp_web_session"
QR_IMAGE_PATH = ".whatsapp_qr.png"
STATE_FILE = ".whatsapp_signal_state.json"
SETTINGS_FILE = ".whatsapp_signal_settings.json"

stop_requested = False

def handle_sigterm(signum, frame):
    global stop_requested
    logger.info("Termination signal received. Exiting worker...")
    stop_requested = True

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

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

def capture_qr_code(page, executor) -> bool:
    """Detects live QR canvas and saves to disk for Streamlit auto-refresh."""
    try:
        # 1. Auto-click reload button if QR expired
        reload_selectors = [
            "button:has-text('Reload')",
            "[role='button']:has-text('Reload')",
            "span[data-icon='reload']",
            "span[data-icon='refresh']",
            "button:has-text('reload')",
            "[role='button']:has-text('reload')",
            "div[data-ref] button",
            "div._akav button"
        ]
        for sel in reload_selectors:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                try:
                    btn.click()
                    time.sleep(0.6)
                    break
                except Exception:
                    pass

        # 2. Method 1: Capture crisp canvas
        canvas_elem = page.locator("canvas[aria-label*='Scan'], div[data-ref] canvas, div[data-testid='qrcode'] canvas, canvas").first
        if canvas_elem.count() > 0 and canvas_elem.is_visible():
            box = canvas_elem.bounding_box()
            if box and box.get("width", 0) > 50:
                try:
                    canvas_elem.screenshot(path=QR_IMAGE_PATH)
                    state = executor.load_state()
                    if state.get("status") not in ["AUTHENTICATED", "CONNECTED"]:
                        state["status"] = "AWAITING_QR_SCAN"
                    state["qr_updated_at"] = datetime.now(timezone.utc).isoformat()
                    executor.save_state(state)
                    return True
                except Exception as c_err:
                    logger.debug(f"Canvas screenshot error: {c_err}")

        # 3. Method 2: Extract data-ref token fallback
        data_ref_elem = page.locator("div[data-ref]").first
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
                    state = executor.load_state()
                    if state.get("status") not in ["AUTHENTICATED", "CONNECTED"]:
                        state["status"] = "AWAITING_QR_SCAN"
                    state["qr_updated_at"] = datetime.now(timezone.utc).isoformat()
                    executor.save_state(state)
                    return True
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Error capturing QR: {e}")
    return False

def is_valid_channel_or_chat_name(name: str) -> bool:
    if not name or len(name) < 3 or len(name) > 75:
        return False
    low = name.lower().strip()
    if "unread message" in low or "unread messages" in low:
        return False
    system_words = {
        "(you)", "archived", "channels", "chats", "status", "photo", "video", 
        "sticker", "audio", "document", "pinned", "draft", "find channels", 
        "stay updated", "explore", "search", "directory", "updates", "communities", 
        "settings", "new chat", "menu", "unread", "typing...", "online"
    }
    if low in system_words:
        return False
    if name.startswith("\u202a") or name.startswith("+") or " added " in low or " left" in low:
        return False
    if "http://" in low or "https://" in low or "\n" in name:
        return False
    if name.strip().isdigit() or not any(c.isalnum() for c in name):
        return False
    return True

def extract_channel_names_from_page(page) -> list:
    names = set()
    locators = [
        "div#pane-side span[title]",
        "div[role='listitem'] span[title]",
        "div[data-testid='cell-frame-title'] span",
        "div[role='gridcell'] span[title]",
        "div[role='listitem'] span[dir='auto']",
        "header span[title]"
    ]
    for sel in locators:
        try:
            for el in page.locator(sel).all():
                try:
                    t = (el.get_attribute("title") or el.inner_text() or "").strip()
                    if is_valid_channel_or_chat_name(t):
                        names.add(t)
                except Exception:
                    pass
        except Exception:
            pass
    return list(names)

def discover_followed_channels(page, executor) -> list:
    channels_set = set()
    groups_set = set()
    try:
        chan_btn = page.locator("button[aria-label='Channels'], [data-navbar-item='true'][aria-label*='Channel']").first
        if chan_btn.count() > 0:
            chan_btn.click(force=True)
            time.sleep(2.0)
            pane = page.locator("div#pane-side").first
            for _ in range(4):
                for name in extract_channel_names_from_page(page):
                    channels_set.add(name)
                try:
                    pane.evaluate("el => el.scrollTop += 600")
                except Exception:
                    pass
                time.sleep(0.8)
    except Exception as ce:
        logger.warning(f"Error extracting from Channels tab: {ce}")

    try:
        chats_btn = page.locator("button[aria-label='Chats'], [data-navbar-item='true'][aria-label*='Chat']").first
        if chats_btn.count() > 0:
            chats_btn.click(force=True)
            time.sleep(2.0)
            pane = page.locator("div#pane-side").first
            for _ in range(3):
                for name in extract_channel_names_from_page(page):
                    if name not in channels_set:
                        groups_set.add(name)
                try:
                    pane.evaluate("el => el.scrollTop += 600")
                except Exception:
                    pass
                time.sleep(0.8)
    except Exception as ge:
        logger.warning(f"Error extracting from Chats tab: {ge}")

    channels_set.add("Tradingpapa.com forex (gold and silver)")
    channels_set.add("Tradingpapa.com crypto")

    def _sort_key(c_name):
        low = c_name.lower()
        if "tradingpapa" in low:
            return (0, low)
        if any(k in low for k in ["forex", "gold", "crypto", "trading", "signal"]):
            return (1, low)
        return (2, low)

    sorted_channels = sorted(list(channels_set), key=_sort_key)
    sorted_groups = sorted(list(groups_set), key=_sort_key)

    state = executor.load_state()
    state["followed_channels"] = sorted_channels
    state["followed_groups"] = sorted_groups
    state["all_targets"] = [f"📢 [Channel] {c}" for c in sorted_channels] + [f"👥 [Group] {g}" for g in sorted_groups]
    executor.save_state(state)
    logger.info(f"Discovered {len(sorted_channels)} channels and {len(sorted_groups)} groups!")
    return sorted_channels

def open_channel(page, channel_name: str, executor):
    clean_target = (
        channel_name.replace("📢 [Channel] ", "")
        .replace("👥 [Group] ", "")
        .replace("📢 ", "")
        .replace("👥 ", "")
        .strip()
    )
    try:
        time.sleep(1)
        channel_locator = page.locator(f"span[title*='{clean_target[:15]}'], div[title*='{clean_target[:15]}']").first
        if channel_locator.count() > 0:
            channel_locator.click(force=True)
            state = executor.load_state()
            state["connected_channel"] = clean_target
            executor.save_state(state)
            time.sleep(1.5)
            try:
                page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
            return

        chan_tab_btn = page.locator("button[aria-label='Channels'], [data-navbar-item='true'][aria-label*='Channel']").first
        if chan_tab_btn.count() > 0:
            chan_tab_btn.click(force=True)
            time.sleep(1.5)
            chan_item = page.locator(f"span[title*='{clean_target[:15]}'], div[title*='{clean_target[:15]}']").first
            if chan_item.count() > 0:
                chan_item.click(force=True)
                state = executor.load_state()
                state["connected_channel"] = clean_target
                executor.save_state(state)
                time.sleep(1.5)
                return

        search_box = page.locator("div[contenteditable='true']").first
        if search_box.count() > 0:
            search_box.click()
            search_box.fill(clean_target)
            time.sleep(2)
            result_item = page.locator(f"span[title*='{clean_target[:15]}'], div[role='listitem']").first
            if result_item.count() > 0:
                result_item.click(force=True)
                state = executor.load_state()
                state["connected_channel"] = clean_target
                executor.save_state(state)
                time.sleep(1.5)
    except Exception as e:
        logger.warning(f"Could not open channel '{clean_target}': {e}")

def run_worker():
    global stop_requested
    import asyncio
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

    parser = WhatsAppSignalParser()
    executor = WhatsAppSignalExecutor()

    # Sync Gemini API key
    settings = executor.load_settings()
    api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
    parser.set_api_key(api_key)

    state = executor.load_state()
    state["status"] = "INITIALIZING"
    executor.save_state(state)

    cleanup_orphaned_sessions(SESSION_DIR)
    os.makedirs(SESSION_DIR, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed.")
        state["status"] = "ERROR_NO_PLAYWRIGHT"
        executor.save_state(state)
        return

    seen_messages = set()
    recent_history = []

    with sync_playwright() as p:
        browser_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1100,800"
        ]

        browser_context = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            args=browser_args,
            viewport={"width": 1100, "height": 800}
        )

        try:
            page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
            logger.info("Navigating to https://web.whatsapp.com...")
            page.goto("https://web.whatsapp.com", wait_until="commit", timeout=30000)

            logged_in = False
            spinner_cycles = 0
            reloaded = False

            while not stop_requested:
                # 1. Check if authenticated
                if page.locator("div#pane-side, div[data-testid='chat-list']").count() > 0:
                    logged_in = True
                    break

                # 2. Check if connecting
                if page.locator("[data-icon='connecting']").count() > 0:
                    state = executor.load_state()
                    if state.get("status") != "CONNECTING":
                        state["status"] = "CONNECTING"
                        executor.save_state(state)

                # 3. Capture QR code
                qr_captured = capture_qr_code(page, executor)
                if not qr_captured:
                    spinner_cycles += 1
                    if spinner_cycles % 5 == 0:
                        try:
                            page.screenshot(path="scratch/worker_page_state.png")
                        except Exception:
                            pass
                    # If spinner is stuck for 15s without a canvas, reload once to unstick WebSocket
                    if spinner_cycles >= 10 and not reloaded:
                        logger.info("Loading spinner held. Refreshing page...")
                        reloaded = True
                        try:
                            page.reload(wait_until="commit")
                        except Exception:
                            pass
                        time.sleep(2.0)
                        spinner_cycles = 0
                else:
                    spinner_cycles = 0

                time.sleep(1.5)

            if logged_in:
                logger.info("🎉 WhatsApp Web Authenticated successfully!")
                if os.path.exists(QR_IMAGE_PATH):
                    try:
                        os.remove(QR_IMAGE_PATH)
                    except Exception:
                        pass

                settings = executor.load_settings()
                target_channel = settings.get("selected_channel", "Tradingpapa.com forex (gold and silver)")

                state = executor.load_state()
                state["status"] = "CONNECTED"
                state["connected_channel"] = target_channel
                executor.save_state(state)

                if len(state.get("followed_channels", [])) == 0:
                    try:
                        discover_followed_channels(page, executor)
                    except Exception as de:
                        logger.warning(f"Channel discovery error: {de}")

                try:
                    open_channel(page, target_channel, executor)
                except Exception as oe:
                    logger.warning(f"Error opening target channel: {oe}")

                # Message polling loop
                while not stop_requested:
                    # Check if session logged out
                    if page.locator("div[data-ref]").count() > 0 or page.locator("div[data-testid='qrcode']").count() > 0:
                        logger.warning("WhatsApp Web session disconnected / awaiting QR scan!")
                        capture_qr_code(page, executor)
                        break

                    containers = page.locator("div[data-testid='msg-container'], div[role='row'], div._amk4, div[data-id], div.message-in").all()
                    if containers:
                        for container in containers[-15:]:
                            try:
                                text_elem = container.locator("span.selectable-text, span[dir='ltr'], span[dir='rtl'], div.copyable-text").first
                                txt = text_elem.inner_text().strip() if text_elem.count() > 0 else ""

                                img_elem = container.locator("img[src*='blob:'], img[src*='data:'], div[data-testid='image-thumb'] img, div._ak8l img, div._ak8o img, div[role='button'] img, div._amk4 img").first
                                has_image = img_elem.count() > 0 and img_elem.is_visible()
                                image_path = None

                                if not txt and not has_image:
                                    continue

                                if has_image:
                                    try:
                                        os.makedirs(".whatsapp_media", exist_ok=True)
                                        image_path = os.path.abspath(f".whatsapp_media/wa_msg_{int(time.time()*1000)}.png")
                                        img_elem.screenshot(path=image_path)
                                        if not txt:
                                            txt = "[Screenshot / Image Attachment]"
                                    except Exception:
                                        pass

                                quote_elem = container.locator("div[data-testid='quoted-message'], div[aria-label*='Quoted'], div._amkd").first
                                quoted_text = quote_elem.inner_text().strip() if quote_elem.count() > 0 else None

                                time_elem = container.locator("div[data-testid='msg-meta'] span, span[data-testid='msg-meta'], div._amkd").first
                                msg_time = time_elem.inner_text().strip() if time_elem.count() > 0 else ""

                                q_snippet = quoted_text[:20] if quoted_text else ""
                                has_img_flag = "1" if image_path else "0"
                                msg_hash = f"{txt[:60]}_{len(txt)}_{q_snippet}_{has_img_flag}"

                                if msg_hash not in seen_messages:
                                    seen_messages.add(msg_hash)
                                    logger.info(f"⚡ Incoming WhatsApp signal: {txt[:60]}...")
                                    open_positions = executor.get_open_whatsapp_positions()
                                    parsed = parser.parse_message(
                                        message_text=txt,
                                        quoted_text=quoted_text,
                                        recent_history=recent_history,
                                        open_trades=open_positions,
                                        channel_name=target_channel,
                                        image_path=image_path
                                    )
                                    recent_history.append({
                                        "time": msg_time or datetime.now(timezone.utc).strftime("%H:%M"),
                                        "text": txt,
                                        "quoted_text": quoted_text,
                                        "has_image": bool(image_path)
                                    })
                                    if len(recent_history) > 30:
                                        recent_history.pop(0)

                                    exec_res = executor.execute_parsed_signal(parsed, txt)
                                    state = executor.load_state()
                                    state["last_message_processed"] = {
                                        "text": txt,
                                        "quoted_text": quoted_text,
                                        "image_path": image_path,
                                        "parsed": parsed,
                                        "result": exec_res,
                                        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                                    }
                                    executor.save_state(state)
                            except Exception:
                                pass

                    time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error in WhatsApp worker: {e}", exc_info=True)
            state = executor.load_state()
            state["status"] = f"ERROR: {str(e)[:100]}"
            executor.save_state(state)
        finally:
            try:
                browser_context.close()
            except Exception:
                pass

if __name__ == "__main__":
    run_worker()
