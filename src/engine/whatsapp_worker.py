"""
Dedicated WhatsApp Web Worker Process.
Runs in its own isolated Python process on the main thread to ensure 100% reliable Playwright execution,
continuous live QR streaming to Streamlit, automated anti-expiration reload, anti-bot detection masking,
and zero GIL/thread-safety conflicts.
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

try:
    from src.utils.env_loader import load_env
    load_env()
except Exception:
    pass

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
    """Kills any orphaned chrome, chrome-headless-shell, or whatsapp python processes holding the session lock and cleans Singleton locks."""
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


def is_authenticated_eval(page) -> bool:
    """Robust multi-attribute JavaScript verification of logged-in WhatsApp Web state."""
    try:
        return bool(page.evaluate("""() => Boolean(
            document.querySelector('div#pane-side') ||
            document.querySelector('header') ||
            document.querySelector('[data-testid="chat-list"]') ||
            document.querySelector('[data-testid="conversation-panel-wrapper"]') ||
            (window.localStorage && (window.localStorage.getItem('last-wid') || window.localStorage.getItem('last-wid-md')))
        )"""))
    except Exception:
        return False


def is_chat_syncing_eval(page) -> bool:
    """
    Detects if phone scanned the QR and WhatsApp Web is actively syncing chats.
    Guaranteed: returns False if QR canvas / QR container is visible on screen.
    """
    try:
        return bool(page.evaluate("""() => {
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
                text.includes('Chats loading')
            );
        }"""))
    except Exception:
        return False


def capture_qr_code(page, executor) -> bool:
    """
    Captures live WhatsApp Web QR code with maximum clarity and zero expiration delay:
    1. Checks if already authenticated.
    2. Auto-clicks reload button if expired.
    3. Screenshots crisp live QR canvas / container.
    4. Fallback to extracting data-ref token and generating lossless QR image.
    5. Updates state with `qr_updated_at` timestamp.
    """
    try:
        if is_authenticated_eval(page):
            return False

        # 1. Auto-click reload button if QR expired
        reload_selectors = [
            "button:has-text('Reload')",
            "[role='button']:has-text('Reload')",
            "span[data-icon='reload']",
            "span[data-icon='refresh']",
            "div[data-testid='link-device-qr-code'] button",
            "div[data-testid='link-device-qr-code'] [role='button']",
            "div[data-ref] button",
            "div[data-ref] [role='button']",
            "div._akav button"
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

        # 2. Method 1: Capture crisp QR canvas / container
        qr_box = page.locator("div[data-testid='link-device-qr-code'], div[data-testid='link-device-qr-code'] canvas, canvas[aria-label*='Scan'], canvas").first
        if qr_box.count() > 0 and qr_box.is_visible():
            box = qr_box.bounding_box()
            if box and box.get("width", 0) > 50:
                try:
                    qr_box.screenshot(path=QR_IMAGE_PATH)
                    captured = True
                except Exception as c_err:
                    logger.debug(f"QR screenshot error: {c_err}")

        # 3. Method 2: Extract data-ref token fallback
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
                        logger.debug(f"QR code generation fallback error: {qr_err}")

        if captured:
            state = executor.load_state()
            if state.get("status") not in ["AUTHENTICATED", "CONNECTED"]:
                state["status"] = "AWAITING_QR_SCAN"
            state["qr_updated_at"] = datetime.now(timezone.utc).isoformat()
            executor.save_state(state)
            return True
    except Exception as e:
        logger.debug(f"Error capturing QR: {e}")
    return False


import re

SYSTEM_WORDS = {
    "(you)", "archived", "channels", "chats", "status", "photo", "video", 
    "sticker", "audio", "document", "pinned", "draft", "find channels", 
    "stay updated", "explore", "search", "directory", "updates", "communities", 
    "settings", "new chat", "menu", "unread", "typing...", "online",
    "yesterday", "today", "tomorrow", "sunday", "monday", "tuesday", "wednesday", 
    "thursday", "friday", "saturday", "disappearing messages", "end-to-end encrypted",
    "security code changed", "message deleted", "this message was deleted",
    "missed voice call", "missed video call", "waiting for this message",
    "react", "reactions", "pin", "reply", "forward"
}

_TIME_REGEX = re.compile(r'^\d{1,2}:\d{2}(\s*(am|pm|a\.m\.|p\.m\.))?$', re.IGNORECASE)
_DATE_REGEX = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$')


def is_valid_channel_or_chat_name(name: str) -> bool:
    if not name or len(name) < 3 or len(name) > 85:
        return False
    low = name.lower().strip()
    if "unread message" in low or "unread messages" in low:
        return False
    if low in SYSTEM_WORDS:
        return False
    if _TIME_REGEX.match(low) or _DATE_REGEX.match(low):
        return False
    if name.startswith("\u202a") or " added " in low or " left" in low:
        return False
    if "http://" in low or "https://" in low or "\n" in name:
        return False
    if name.strip().isdigit() or not any(c.isalnum() for c in name):
        return False
    # Filter pure phone numbers (e.g. +92 308..., 0321...)
    digits_only = re.sub(r'\D', '', name)
    if len(digits_only) >= 9 and len(re.sub(r'[\d\s\+\-\(\)]', '', name)) == 0:
        return False
    return True


def switch_to_tab(page, tab_type: str) -> bool:
    """
    Switches between 'channels' (Updates/Newsletters) and 'chats' (Chats/Groups).
    Tries Playwright locators first, then JavaScript fallback.
    """
    is_chan = (tab_type == "channels")
    chan_selectors = [
        "button[aria-label='Channels']",
        "button[aria-label*='Channel']",
        "button[aria-label='Updates']",
        "button[aria-label*='Update']",
        "button[aria-label='Newsletters']",
        "button[aria-label*='Newsletter']",
        "[data-navbar-item='true'][aria-label*='Channel']",
        "[data-navbar-item='true'][aria-label*='Update']",
        "[data-navbar-item='true'][aria-label*='Newsletter']",
        "div[role='button'][aria-label*='Channel']",
        "div[role='button'][aria-label*='Update']",
        "div[role='button'][aria-label*='Newsletter']",
        "span[data-icon='newsletter']",
        "span[data-icon='status-outline']",
        "span[data-icon='channel']"
    ]
    chat_selectors = [
        "button[aria-label='Chats']",
        "button[aria-label*='Chat']",
        "[data-navbar-item='true'][aria-label*='Chat']",
        "div[role='button'][aria-label*='Chat']",
        "span[data-icon='chat']",
        "span[data-icon='chats']",
        "span[data-icon='chat-outline']"
    ]
    selectors = chan_selectors if is_chan else chat_selectors

    for attempt in range(4):
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(force=True)
                    time.sleep(1.2)
                    return True
            except Exception:
                pass

        # JavaScript fallback targeting navigation containers only
        try:
            clicked = page.evaluate(r"""(isChan) => {
                const keys = isChan 
                    ? ['channel', 'channels', 'update', 'updates', 'newsletter', 'newsletters'] 
                    : ['chats', 'chat'];
                const icons = isChan 
                    ? ['newsletter', 'newsletter-outline', 'channel', 'status-outline', 'updates'] 
                    : ['chat', 'chats', 'chat-outline'];

                // 1. Check data-icon on svg/span
                for (const icon of icons) {
                    const iconEl = document.querySelector(`span[data-icon='${icon}']`);
                    if (iconEl) {
                        const btn = iconEl.closest('button, [role="button"], [data-navbar-item="true"]') || iconEl;
                        btn.click();
                        return true;
                    }
                }

                // 2. Check navigation rail buttons
                const navElements = document.querySelectorAll('header button, nav button, [role="navigation"] [role="button"], div[data-testid="chat-list"]');
                for (const b of navElements) {
                    const label = (b.getAttribute('aria-label') || b.getAttribute('title') || '').toLowerCase().trim();
                    if (keys.some(k => label === k || label.startsWith(k))) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }""", is_chan)
            if clicked:
                time.sleep(1.2)
                return True
        except Exception as e:
            logger.debug(f"switch_to_tab JS error: {e}")

        time.sleep(0.8)

    return False


def extract_visible_titles(page) -> list:
    """Extracts all candidate titles from visible sidebar DOM in one fast JavaScript call."""
    try:
        raw_titles = page.evaluate(r"""() => {
            const pane = document.querySelector('#pane-side, div[data-testid="chat-list"]');
            if (!pane) return [];
            const results = new Set();
            const elements = pane.querySelectorAll('span[title], div[role="listitem"] span[title], div[role="row"] span[title], div[data-testid="cell-frame-title"] span');
            for (const el of elements) {
                const t = (el.getAttribute('title') || el.innerText || '').trim();
                if (t && t.length >= 3 && t.length <= 85) {
                    results.add(t);
                }
            }
            return Array.from(results);
        }""")
        valid_titles = []
        for t in raw_titles:
            if is_valid_channel_or_chat_name(t):
                valid_titles.append(t)
        return valid_titles
    except Exception as e:
        logger.debug(f"Error in extract_visible_titles: {e}")
        return []


def scroll_and_collect_titles(page, max_scrolls: int = 12) -> set:
    """Scrolls down #pane-side progressively, collecting all virtualized items until the bottom is reached."""
    collected = set()
    try:
        for _ in range(max_scrolls):
            for t in extract_visible_titles(page):
                collected.add(t)

            scroll_res = page.evaluate(r"""() => {
                const pane = document.querySelector('#pane-side, div[data-testid="chat-list"]');
                if (!pane) return { scrolled: false, atBottom: true };
                const prevTop = pane.scrollTop;
                pane.scrollTop += 650;
                return {
                    scrolled: pane.scrollTop > prevTop,
                    atBottom: (pane.scrollTop + pane.clientHeight >= pane.scrollHeight - 25)
                };
            }""")

            time.sleep(0.5)
            if not scroll_res.get("scrolled") or scroll_res.get("atBottom"):
                for t in extract_visible_titles(page):
                    collected.add(t)
                break

        # Return pane to top for clean UI state
        page.evaluate(r"""() => {
            const pane = document.querySelector('#pane-side, div[data-testid="chat-list"]');
            if (pane) pane.scrollTop = 0;
        }""")
    except Exception as e:
        logger.debug(f"Error during scroll_and_collect_titles: {e}")
    return collected


def discover_followed_channels(page, executor) -> list:
    channels_set = set()
    groups_set = set()

    state = executor.load_state() if hasattr(executor, 'load_state') else executor
    state["is_syncing_channels"] = True
    if hasattr(executor, 'save_state'):
        executor.save_state(state)

    logger.info("Scanning WhatsApp Web for Channels & Groups...")

    # Step 1: Channels Tab Discovery (Only truly followed channels, excluding un-followed recommendations)
    try:
        if switch_to_tab(page, "channels"):
            time.sleep(1.8)
            followed_chan_titles = page.evaluate(r"""() => {
                const pane = document.querySelector('#pane-side, div[data-testid="chat-list"]');
                if (!pane) return [];
                const list = [];
                const rows = pane.querySelectorAll('div[role="listitem"], div[role="row"], div[data-testid="cell-frame-container"]');
                for (const row of rows) {
                    const hasFollowBtn = Boolean(row.querySelector('button, [role="button"]') && /follow/i.test(row.innerText));
                    if (!hasFollowBtn) {
                        const titleEl = row.querySelector('div[data-testid="cell-frame-title"] span[title], span[title]');
                        const t = titleEl ? (titleEl.getAttribute('title') || titleEl.innerText || '').trim() : '';
                        if (t && t.length >= 3) list.push(t);
                    }
                }
                return list;
            }""")
            for t in followed_chan_titles:
                if is_valid_channel_or_chat_name(t):
                    channels_set.add(t)
            logger.info(f"Discovered {len(channels_set)} followed channels from Channels tab.")
    except Exception as ce:
        logger.warning(f"Error discovering Channels tab: {ce}")

    # Step 2: Chats Tab Discovery using Groups Filter Pill
    try:
        if switch_to_tab(page, "chats"):
            time.sleep(1.5)
            # Click Groups filter pill
            page.evaluate(r"""() => {
                const buttons = Array.from(document.querySelectorAll('button, div[role="button"], span'));
                for (const b of buttons) {
                    const text = (b.innerText || '').trim();
                    if (/^Groups(\s+\d+)?$/i.test(text)) {
                        (b.closest('button, [role="button"]') || b).click();
                        return true;
                    }
                }
                return false;
            }""")
            time.sleep(1.2)
            raw_groups = scroll_and_collect_titles(page, max_scrolls=18)
            for g in raw_groups:
                if is_valid_channel_or_chat_name(g):
                    groups_set.add(g)
            logger.info(f"Discovered {len(groups_set)} groups from Groups filter.")

            # Reset back to All filter
            page.evaluate(r"""() => {
                const buttons = Array.from(document.querySelectorAll('button, div[role="button"], span'));
                for (const b of buttons) {
                    const text = (b.innerText || '').trim();
                    if (text === 'All') {
                        (b.closest('button, [role="button"]') || b).click();
                        return true;
                    }
                }
                return false;
            }""")
            time.sleep(0.5)
    except Exception as ge:
        logger.warning(f"Error discovering Groups tab: {ge}")

    # Ensure known channels are present
    channels_set.add("Tradingpapa.com forex (gold and silver)")
    channels_set.add("Tradingpapa.com crypto")

    def _sort_key(c_name):
        low = c_name.lower()
        if "tradingpapa" in low:
            return (0, low)
        if any(k in low for k in ["forex", "gold", "silver", "crypto", "trading", "signal", "fx", "vip", "community"]):
            return (1, low)
        return (2, low)

    sorted_channels = sorted(list(channels_set), key=_sort_key)
    sorted_groups = sorted(list(groups_set), key=_sort_key)

    state = executor.load_state() if hasattr(executor, 'load_state') else executor
    state["followed_channels"] = sorted_channels
    state["followed_groups"] = sorted_groups
    state["all_targets"] = [f"📢 [Channel] {c}" for c in sorted_channels] + [f"👥 [Group] {g}" for g in sorted_groups]
    state["is_syncing_channels"] = False
    state["last_channel_sync"] = datetime.now(timezone.utc).isoformat()
    if hasattr(executor, 'save_state'):
        executor.save_state(state)

    logger.info(f"Sync complete! Total: {len(sorted_channels)} channels and {len(sorted_groups)} groups.")
    return sorted_channels


def get_active_conversation_title(page) -> str:
    """Extracts the exact title of the currently open chat/channel from the conversation header."""
    try:
        return page.evaluate("""() => {
            const main = document.querySelector('#main, div[data-testid="conversation-panel-wrapper"], div[role="region"][aria-label*="Chat"], div[role="region"][aria-label*="Channel"], div[role="region"][aria-label*="Newsletter"]');
            if (!main) return "";
            const header = main.querySelector('header, div[data-testid="conversation-header"], div[role="button"][data-testid="conversation-info-header"]');
            if (!header) return "";
            
            const titleCandidates = header.querySelectorAll('span[title], [data-testid="conversation-info-header"] span, div[role="button"] span[dir="auto"], span[dir="auto"]');
            for (const el of titleCandidates) {
                const t = (el.getAttribute('title') || el.innerText || '').trim();
                if (t && t.length >= 2 && !['online', 'typing...', 'click here', 'channel info'].some(s => t.toLowerCase().includes(s))) {
                    return t;
                }
            }
            const raw = (header.innerText || '').trim();
            return raw ? raw.split('\\n')[0].trim() : "";
        }""") or ""
    except Exception:
        return ""


def is_matching_target(active_title: str, target_channel: str) -> bool:
    if not active_title or not target_channel:
        return False
    clean_target = (
        target_channel.replace("📢 [Channel] ", "")
        .replace("👥 [Group] ", "")
        .replace("📢 ", "")
        .replace("👥 ", "")
        .strip()
    )
    act = active_title.strip()
    if not clean_target or not act:
        return False

    # 1. Direct case-insensitive match
    if clean_target.lower() == act.lower():
        return True

    # 1.5. Clean trailing dots/ellipsis (e.g. "Tradingpapa.com for..." -> "Tradingpapa.com for")
    act_clean = re.sub(r'[\.\…\s]+$', '', act.lower())
    tgt_clean = re.sub(r'[\.\…\s]+$', '', clean_target.lower())
    if tgt_clean.startswith(act_clean) and len(act_clean) >= 12:
        return True

    # 2. Strict Alphanumeric normalized comparison
    norm_target = re.sub(r'[^\w\s]', '', clean_target.lower())
    norm_target = re.sub(r'\s+', ' ', norm_target).strip()

    norm_act = re.sub(r'[^\w\s]', '', act.lower())
    norm_act = re.sub(r'\s+', ' ', norm_act).strip()

    if norm_target and norm_act:
        if norm_target == norm_act:
            return True
        if norm_target.startswith(norm_act) and len(norm_act) >= 12:
            return True

    # 3. Tradingpapa specialized comparison (ensures crypto vs forex are strictly segregated)
    if "tradingpapa" in norm_target and "tradingpapa" in norm_act:
        target_forex = any(k in norm_target for k in ["forex", "gold", "silver"])
        target_crypto = "crypto" in norm_target

        act_has_forex = any(k in norm_act for k in ["forex", "gold", "silver", "for"])
        act_has_crypto = any(k in norm_act for k in ["crypto", "cryp"])

        if target_forex and act_has_forex and not act_has_crypto:
            return True
        if target_crypto and act_has_crypto and not act_has_forex:
            return True
        # If active title is truncated as "tradingpapa.com for..." and target is forex:
        if target_forex and ("for" in norm_act or norm_act.startswith("tradingpapacom for")):
            return True

    return False


def click_target_in_sidebar(page, clean_target: str) -> bool:
    """Clicks matching channel or group card in WhatsApp sidebar or search results, strictly by card title."""
    try:
        # Strategy 1: Playwright get_by_title -- handles dots, parens, special chars natively
        for scope_sel in ['#side', '#pane-side', "div[data-testid='search-results']"]:
            try:
                scope = page.locator(scope_sel)
                if scope.count() > 0:
                    loc = scope.get_by_title(clean_target, exact=True).first
                    if loc.count() > 0 and loc.is_visible():
                        loc.click(force=True)
                        return True
            except Exception:
                pass

        # Strategy 2: CSS attribute selector with double-quote wrapping to avoid escaping issues
        try:
            safe_title = clean_target.replace('"', '&quot;')
            native_loc = page.locator(
                f'#side span[title="{safe_title}"], '
                f'div[data-testid="search-results"] span[title="{safe_title}"], '
                f'#pane-side span[title="{safe_title}"]'
            ).first
            if native_loc.count() > 0 and native_loc.is_visible():
                native_loc.click(force=True)
                return True
        except Exception:
            pass

        return page.evaluate(r"""(cleanTarget) => {
            function normalizeStr(s) {
                return (s || '').toLowerCase().replace(/[^\w\s]/g, '').replace(/\s+/g, ' ').trim();
            }

            const normTarget = normalizeStr(cleanTarget);
            if (!normTarget) return false;

            const isTP = normTarget.includes("tradingpapa");
            const hasForex = normTarget.includes("forex") || normTarget.includes("gold") || normTarget.includes("silver");
            const hasCrypto = normTarget.includes("crypto");

            function doClick(element) {
                const clickable = element.closest('div[role="listitem"], div[role="row"], div[data-testid="cell-frame-container"], [role="button"]') || element;
                clickable.scrollIntoView({ block: 'center' });
                clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                clickable.click();
                return true;
            }

            // Priority 1: Check elements with explicit title attribute or cell-frame-title matching normTarget
            const candidateElements = Array.from(document.querySelectorAll(
                'span[title], div[title], [data-testid="cell-frame-title"] span, [data-testid="cell-frame-title"] div, div[data-testid="search-results"] span[dir="auto"]'
            ));
            for (const el of candidateElements) {
                const raw = (el.getAttribute('title') || el.innerText || '').trim();
                const norm = normalizeStr(raw);
                if (!norm) continue;

                let matched = false;
                if (isTP && norm.includes("tradingpapa")) {
                    if (hasForex && (norm.includes("forex") || norm.includes("gold") || norm.includes("silver"))) matched = true;
                    if (hasCrypto && norm.includes("crypto")) matched = true;
                } else if (norm === normTarget) {
                    matched = true;
                }

                if (matched) {
                    return doClick(el);
                }
            }

            // Priority 2: Check all candidate cards in sidebar and search results
            const cards = Array.from(document.querySelectorAll(
                'div[data-testid="search-results"] div[role="row"], div[data-testid="search-results"] div[role="listitem"], #pane-side div[role="row"], #pane-side div[role="listitem"], div[data-testid="cell-frame-container"]'
            ));
            for (const card of cards) {
                const titleCandidates = Array.from(card.querySelectorAll(
                    '[data-testid="cell-frame-title"] span, span[title], div[data-testid="cell-frame-primary"] span, header span'
                ));
                for (const tc of titleCandidates) {
                    const txt = (tc.getAttribute('title') || tc.innerText || '').trim();
                    if (!txt || txt.length < 2) continue;
                    if (/^\d{1,2}:\d{2}(\s*(am|pm))?$/i.test(txt)) continue;

                    const norm = normalizeStr(txt);
                    let matched = false;
                    if (isTP && norm.includes("tradingpapa")) {
                        if (hasForex && (norm.includes("forex") || norm.includes("gold") || norm.includes("silver"))) matched = true;
                        if (hasCrypto && norm.includes("crypto")) matched = true;
                    } else if (norm === normTarget) {
                        matched = true;
                    }

                    if (matched) {
                        return doClick(card);
                    }
                }
            }
            return false;
        }""", clean_target)
    except Exception as e:
        logger.debug(f"click_target_in_sidebar error: {e}")
        return False


def scroll_and_find_target(page, clean_target: str, max_scrolls: int = 15) -> bool:
    """Scrolls sidebar step by step giving React virtualization time to render items."""
    try:
        if click_target_in_sidebar(page, clean_target):
            return True

        for _ in range(max_scrolls):
            scrolled = page.evaluate("""() => {
                // Cover Chats tab AND Channels tab sidebar panes
                const pane = document.querySelector(
                    '#pane-side, div[data-testid="chat-list"], ' +
                    'div[data-testid="channels-list"], div[data-testid="pane-channels"], ' +
                    '#pane-channels, div[aria-label="Channel list"], ' +
                    'div[aria-label="Chats"], div[aria-label="Chat list"]'
                );
                if (!pane) return false;
                const prev = pane.scrollTop;
                pane.scrollTop += 550;
                return pane.scrollTop > prev;
            }""")
            if not scrolled:
                break
            time.sleep(0.35)
            if click_target_in_sidebar(page, clean_target):
                return True

        # Reset to top if not found
        page.evaluate("""() => {
            const pane = document.querySelector(
                '#pane-side, div[data-testid="chat-list"], ' +
                'div[data-testid="channels-list"], div[data-testid="pane-channels"], ' +
                '#pane-channels, div[aria-label="Channel list"], ' +
                'div[aria-label="Chats"], div[aria-label="Chat list"]'
            );
            if (pane) pane.scrollTop = 0;
        }""")
        time.sleep(0.2)
    except Exception as e:
        logger.debug(f"scroll_and_find_target error: {e}")
    return False


def snapshot_existing_messages(page, seen_messages: set):
    """
    Snapshots all existing messages currently visible in the active chat container
    so that historical chatter is NOT processed as live incoming signals.
    """
    try:
        main_pane = page.locator("div#main, div[data-testid='conversation-panel-wrapper'], div[data-testid='conversation-panel-messages']").first
        if main_pane.count() == 0:
            return 0
        containers = main_pane.locator("div[data-testid='msg-container'], div.message-in, div.message-out").all()
        added_count = 0
        for container in containers:
            try:
                text_elem = container.locator("span.selectable-text, span[dir='ltr'], span[dir='rtl'], div.copyable-text").first
                txt = text_elem.inner_text().strip() if text_elem.count() > 0 else ""

                img_elem = container.locator("img[src*='blob:'], img[src*='data:'], div[data-testid='image-thumb'] img, div._ak8l img, div._ak8o img, div[role='button'] img, div._amk4 img").first
                has_image = img_elem.count() > 0 and img_elem.is_visible()

                quote_elem = container.locator("div[data-testid='quoted-message'], div[aria-label*='Quoted'], div._amkd").first
                quoted_text = quote_elem.inner_text().strip() if quote_elem.count() > 0 else None

                if not txt and not has_image:
                    continue

                q_snippet = quoted_text[:20] if quoted_text else ""
                has_img_flag = "1" if has_image else "0"
                msg_hash = f"{txt[:60]}_{len(txt)}_{q_snippet}_{has_img_flag}"

                if msg_hash not in seen_messages:
                    seen_messages.add(msg_hash)
                    added_count += 1
            except Exception:
                pass
        logger.info(f"🛡️ Baseline message snapshot initialized: {len(seen_messages)} total historical messages ignored ({added_count} newly registered).")
        return added_count
    except Exception as e:
        logger.debug(f"Snapshot existing messages error: {e}")
        return 0


def open_channel(page, channel_name: str, executor):
    clean_target = (
        channel_name.replace("📢 [Channel] ", "")
        .replace("👥 [Group] ", "")
        .replace("📢 ", "")
        .replace("👥 ", "")
        .strip()
    )
    if not clean_target:
        return False

    logger.info(f"Opening target channel / chat: '{clean_target}'...")

    # 1. Check if already open
    curr_title = get_active_conversation_title(page)
    if is_matching_target(curr_title, clean_target):
        logger.info(f"Target '{clean_target}' is already open in main pane.")
        state = executor.load_state()
        state["connected_channel"] = curr_title
        executor.save_state(state)
        return True

    state = executor.load_state()
    followed_chans = state.get("followed_channels", [])
    followed_grps = state.get("followed_groups", [])

    # Determine type — default to chats (handles DM, groups and channels)
    if channel_name.startswith("📢") or "[channel]" in channel_name.lower():
        is_channel_target = True
    elif channel_name.startswith("👥") or "[group]" in channel_name.lower():
        is_channel_target = False
    elif clean_target in followed_chans:
        is_channel_target = True
    elif clean_target in followed_grps:
        is_channel_target = False
    else:
        is_channel_target = ("channel" in channel_name.lower() or "tradingpapa" in clean_target.lower())

    def _try_open_after_click() -> bool:
        """Wait up to 4s for active title to match clean_target after a click."""
        for _ in range(8):
            time.sleep(0.5)
            curr = get_active_conversation_title(page)
            if is_matching_target(curr, clean_target):
                logger.info(f"✅ Successfully opened '{clean_target}' (active: '{curr}')")
                st = executor.load_state()
                st["connected_channel"] = curr
                executor.save_state(st)
                return True
        return False

    # ── Attempt A: Switch to correct tab, scroll sidebar ──────────────────────
    if is_channel_target:
        switch_to_tab(page, "channels")
    else:
        switch_to_tab(page, "chats")
    time.sleep(0.8)

    logger.info(f"Scanning sidebar for '{clean_target}'...")
    if scroll_and_find_target(page, clean_target, max_scrolls=12):
        if _try_open_after_click():
            return True

    # ── Attempt B: Also try the other tab (personal chats appear in Chats) ───
    if is_channel_target:
        switch_to_tab(page, "chats")
    else:
        switch_to_tab(page, "channels")
    time.sleep(0.6)
    if scroll_and_find_target(page, clean_target, max_scrolls=8):
        if _try_open_after_click():
            return True

    # ── Attempt C: WhatsApp Universal Search (works for all types) ────────────
    logger.info(f"Searching WhatsApp for '{clean_target}'...")
    try:
        # Go back to Chats tab — search works best from there for all types
        switch_to_tab(page, "chats")
        time.sleep(0.4)

        # Close any open search/overlay
        try:
            page.keyboard.press("Escape")
            time.sleep(0.25)
        except Exception:
            pass

        # Focus search box — try many selectors used across WhatsApp Web versions
        search_focused = False
        search_selectors = [
            "div[data-testid='chat-list-search'] [contenteditable='true']",
            "div[data-testid='search-container'] [contenteditable='true']",
            "div[role='textbox'][data-tab='3']",
            "div[role='textbox'][title*='Search']",
            "div[role='textbox'][aria-label*='Search']",
            "input[aria-label*='Search']",
            "div[role='textbox']",
            "#side [role='textbox']",
            "#side input",
        ]
        for sel in search_selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.click(force=True)
                    time.sleep(0.2)
                    search_focused = True
                    break
            except Exception:
                pass

        if not search_focused:
            # WhatsApp keyboard shortcut to open search
            try:
                page.keyboard.press("Control+/")
                time.sleep(0.3)
            except Exception:
                pass

        # Type the search keyword — use the real name, NOT aggressively stripped.
        # Stripping `.` from "Tradingpapa.com" gives "Tradingpapacom" which WhatsApp can't find.
        # Use the first ~22 chars of the real name which is enough to uniquely identify any chat.
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        time.sleep(0.15)
        # Trim to first word-boundary segment (<=22 chars) so it fits search and avoids mismatches
        words = clean_target.split()
        search_kw = ""
        for w in words:
            if len(search_kw) + len(w) + 1 <= 22:
                search_kw = (search_kw + " " + w).strip()
            else:
                break
        if not search_kw:
            search_kw = clean_target[:22]
        page.keyboard.type(search_kw, delay=30)
        time.sleep(2.2)  # Give WhatsApp time to render all result sections


        # ── Sub-attempt C1: Exact title match in search results ───────────────
        if click_target_in_sidebar(page, clean_target):
            if _try_open_after_click():
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                return True

        # ── Sub-attempt C2: Click first card in Chats section of search results
        # Safe: we typed the exact name so first Chats result is very likely correct
        logger.info(f"Trying first-result click in search for '{clean_target}'...")
        clicked_first = page.evaluate(r"""(normTarget) => {
            function normalizeStr(s) {
                return (s || '').toLowerCase().replace(/[^\w\s]/g, '').replace(/\s+/g, ' ').trim();
            }
            // Look for the Chats section header, then grab the first item after it
            const allElements = Array.from(document.querySelectorAll('div[data-testid="search-results"] div, #side div'));

            // Strategy 1: find span with matching title attribute (exact or fuzzy)
            for (const el of allElements) {
                const spans = el.querySelectorAll('span[title]');
                for (const sp of spans) {
                    const t = (sp.getAttribute('title') || '').trim();
                    const nt = normalizeStr(t);
                    if (nt && nt === normTarget) {
                        const row = sp.closest('div[role="listitem"], div[role="row"], div[data-testid="cell-frame-container"]');
                        if (row) {
                            row.scrollIntoView({ block: 'center' });
                            row.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                            row.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                            row.click();
                            return 'title_attr_match';
                        }
                    }
                }
            }

            // Strategy 2: look for search result rows and pick first one whose title contains our keyword
            const searchRows = Array.from(document.querySelectorAll(
                'div[data-testid="search-results"] div[role="row"], div[data-testid="search-results"] div[role="listitem"], #side div[data-testid*="cell"] div[role="row"]'
            ));
            for (const row of searchRows) {
                const titleEls = row.querySelectorAll('span[title], div[data-testid="cell-frame-title"] span');
                for (const te of titleEls) {
                    const t = (te.getAttribute('title') || te.innerText || '').trim();
                    if (normalizeStr(t) === normTarget) {
                        row.scrollIntoView({ block: 'center' });
                        row.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        row.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        row.click();
                        return 'row_title_match';
                    }
                }
            }
            return false;
        }""", re.sub(r'[^\w\s]', '', clean_target.lower()).strip())

        if clicked_first:
            logger.info(f"Search first-result strategy: {clicked_first}")
            if _try_open_after_click():
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                return True

        logger.warning(f"Target '{clean_target}' card not found in search results. Refusing to press Enter.")
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        time.sleep(0.3)

    except Exception as se:
        logger.debug(f"Search box open channel error: {se}")

    logger.warning(f"Could not open target channel '{clean_target}' after all attempts!")
    return False


def run_worker():
    global stop_requested
    import asyncio
    if sys.platform == 'win32':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception:
        pass

    parser = WhatsAppSignalParser()
    executor = WhatsAppSignalExecutor()

    # Sync Gemini API key
    settings = executor.load_settings()
    api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
    parser.set_api_key(api_key)

    state = executor.load_state()
    state["status"] = "INITIALIZING"
    state["worker_pid"] = os.getpid()
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

        # Mask webdriver and inject modern Chrome 133 Client Hints
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
            logger.info("Navigating to https://web.whatsapp.com...")
            page.goto("https://web.whatsapp.com", wait_until="commit", timeout=45000)

            logged_in = False
            had_qr = False
            last_loop_log = time.time()

            while not stop_requested:
                # 1. Multi-attribute check for authenticated state
                if is_authenticated_eval(page):
                    logged_in = True
                    break

                # 2. Capture / refresh live QR code first whenever visible
                qr_captured = capture_qr_code(page, executor)
                if qr_captured:
                    had_qr = True
                    time.sleep(1.2)
                    continue

                # 3. Check if phone scanned and chats are syncing
                if is_chat_syncing_eval(page):
                    state = executor.load_state()
                    if state.get("status") != "CONNECTING":
                        state["status"] = "CONNECTING"
                        executor.save_state(state)
                    if os.path.exists(QR_IMAGE_PATH):
                        try:
                            os.remove(QR_IMAGE_PATH)
                        except Exception:
                            pass
                    time.sleep(1.2)
                    continue

                if time.time() - last_loop_log > 5.0:
                    last_loop_log = time.time()
                    try:
                        p_title = page.title()
                        p_url = page.url
                        logger.info(f"Waiting for WhatsApp Auth/QR... Page Title: '{p_title}' | URL: '{p_url}'")
                    except Exception:
                        pass

                time.sleep(1.0)

            if logged_in:
                logger.info("🎉 WhatsApp Web Authenticated successfully!")
                if os.path.exists(QR_IMAGE_PATH):
                    try:
                        os.remove(QR_IMAGE_PATH)
                    except Exception:
                        pass

                # Allow WhatsApp Web React hydration to mount navigation rail & chats
                time.sleep(3.5)

                settings = executor.load_settings()
                _raw_target = settings.get("selected_channel", "Tradingpapa.com forex (gold and silver)")
                target_channel = (
                    _raw_target
                    .replace("📢 [Channel] ", "").replace("👥 [Group] ", "")
                    .replace("📢 ", "").replace("👥 ", "").strip()
                ) or "Tradingpapa.com forex (gold and silver)"

                state = executor.load_state()
                state["status"] = "CONNECTED"
                state["connected_channel"] = target_channel
                executor.save_state(state)

                if len(state.get("followed_channels", [])) == 0 or len(state.get("followed_groups", [])) == 0:
                    try:
                        discover_followed_channels(page, executor)
                    except Exception as de:
                        logger.warning(f"Initial channel discovery error: {de}")

                try:
                    if open_channel(page, target_channel, executor):
                        snapshot_existing_messages(page, seen_messages)
                except Exception as oe:
                    logger.warning(f"Error opening target channel: {oe}")

                # Fast message polling loop
                last_settings_check = time.time()
                while not stop_requested:
                    # Strict disconnect check: ONLY trigger if chat list is GONE AND QR canvas is VISIBLE
                    is_chat_list_present = is_authenticated_eval(page)
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
                        capture_qr_code(page, executor)
                        break

                    # Check for UI channel sync request or channel change every 1.5s
                    now = time.time()
                    if now - last_settings_check > 1.5:
                        last_settings_check = now
                        curr_state = executor.load_state()
                        if curr_state.get("request_channel_sync"):
                            curr_state["request_channel_sync"] = False
                            curr_state["is_syncing_channels"] = True
                            executor.save_state(curr_state)
                            logger.info("Dynamic channel sync requested from UI. Refreshing...")
                            try:
                                discover_followed_channels(page, executor)
                            except Exception as sync_e:
                                logger.warning(f"Dynamic channel sync error: {sync_e}")
                            finally:
                                end_state = executor.load_state()
                                end_state["is_syncing_channels"] = False
                                executor.save_state(end_state)
                            if open_channel(page, target_channel, executor):
                                snapshot_existing_messages(page, seen_messages)

                        curr_settings = executor.load_settings()
                        curr_key = (curr_settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")).strip()
                        if curr_key and curr_key != parser.api_key:
                            parser.set_api_key(curr_key)
                            logger.info("🔑 Gemini API key dynamically synchronized in WhatsApp worker.")

                        _raw_curr = curr_settings.get("selected_channel", target_channel)
                        curr_target = (
                            _raw_curr
                            .replace("📢 [Channel] ", "").replace("👥 [Group] ", "")
                            .replace("📢 ", "").replace("👥 ", "").strip()
                        ) or target_channel
                        if curr_target != target_channel:
                            target_channel = curr_target
                            logger.info(f"Target channel changed in UI to: {target_channel}")
                            seen_messages.clear()
                            recent_history.clear()
                            if open_channel(page, target_channel, executor):
                                snapshot_existing_messages(page, seen_messages)


                    # 1. STRICT ACTIVE HEADER VERIFICATION:
                    active_title = get_active_conversation_title(page)
                    if not is_matching_target(active_title, target_channel):
                        now_ts = time.time()
                        if now_ts - getattr(run_worker, "_last_mismatch_log", 0) > 5.0:
                            run_worker._last_mismatch_log = now_ts
                            logger.warning(
                                f"Active chat '{active_title}' does NOT match target '{target_channel}'. "
                                "Refusing to poll. Re-aligning to target channel..."
                            )
                        open_channel(page, target_channel, executor)
                        # NOTE: NEVER call snapshot_existing_messages here during live runtime!
                        time.sleep(0.8)
                        continue

                    # 2. STRICT CONVERSATION SCOPING & UNREAD BUTTON AUTO-CLICK:
                    main_pane = page.locator("div#main, div[data-testid='conversation-panel-wrapper'], div[data-testid='conversation-panel-messages']").first
                    if main_pane.count() == 0:
                        time.sleep(0.3)
                        continue

                    # Auto-click unread badge / down-arrow and scroll to bottom
                    try:
                        page.evaluate("""() => {
                            // Click scroll-to-bottom or unread badge button if present
                            const downBtn = document.querySelector(
                                'div[data-testid="scroll-to-bottom"], span[data-icon="down"], ' +
                                'span[data-icon="down-context"], div[data-testid="down-context"], ' +
                                'button[aria-label*="down" i], [aria-label*="unread" i], [aria-label*="scroll to bottom" i]'
                            );
                            if (downBtn) {
                                const clickable = downBtn.closest('button, [role="button"]') || downBtn;
                                clickable.click();
                            }
                            // Scroll all scrollable elements inside conversation pane
                            const main = document.querySelector('#main, div[data-testid="conversation-panel-wrapper"]');
                            if (main) {
                                const scrollables = Array.from(main.querySelectorAll('div, div[tabindex="-1"]')).filter(el => {
                                    const style = window.getComputedStyle(el);
                                    return (style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight;
                                });
                                for (const s of scrollables) {
                                    s.scrollTop = s.scrollHeight;
                                }
                            }
                        }""")
                    except Exception:
                        pass

                    # 3. FAST ATOMIC JAVASCRIPT MESSAGE EXTRACTION (0ms latency, zero DOM race conditions):
                    extracted_messages = []
                    try:
                        extracted_messages = page.evaluate("""() => {
                            const main = document.querySelector('#main, div[data-testid="conversation-panel-wrapper"]');
                            if (!main) return [];

                            // Find candidate message containers inside #main
                            const containers = Array.from(main.querySelectorAll(
                                'div[data-testid="msg-container"], div.message-in, div.message-out, ' +
                                'div[role="row"], div[data-testid="newsletter-message-container"]'
                            ));
                            const list = [];

                            for (const c of containers.slice(-25)) {
                                // Extract text: try copyable-text first, then selectable-text, then spans
                                let txt = '';
                                const copyable = c.querySelector('div.copyable-text');
                                if (copyable) {
                                    txt = (copyable.innerText || '').trim();
                                }
                                if (!txt) {
                                    const selectable = c.querySelector('span.selectable-text');
                                    if (selectable) {
                                        txt = (selectable.innerText || '').trim();
                                    }
                                }
                                if (!txt) {
                                    const spans = Array.from(c.querySelectorAll('span[dir="ltr"], span[dir="rtl"]'));
                                    const parts = spans.map(s => (s.innerText || '').trim()).filter(s => s.length > 0);
                                    if (parts.length > 0) {
                                        txt = parts.join('\\n').trim();
                                    }
                                }

                                const imgNode = c.querySelector('img[src*="blob:"], img[src*="data:"], div[data-testid="image-thumb"] img, div._ak8l img, div._ak8o img, div[role="button"] img, div._amk4 img');
                                const hasImg = Boolean(imgNode && imgNode.offsetParent !== null);

                                if (!txt && !hasImg) continue;

                                const quoteNode = c.querySelector('div[data-testid="quoted-message"], div[aria-label*="Quoted"]');
                                const quotedText = quoteNode ? (quoteNode.innerText || '').trim() : null;

                                const timeNode = c.querySelector('div[data-testid="msg-meta"] span, span[data-testid="msg-meta"]');
                                const msgTime = timeNode ? (timeNode.innerText || '').trim() : '';

                                const dataId = c.getAttribute('data-id') || c.closest('[data-id]')?.getAttribute('data-id') || '';

                                list.push({
                                    id: dataId,
                                    text: txt,
                                    quoted_text: quotedText,
                                    time: msgTime,
                                    has_image: hasImg
                                });
                            }
                            return list;
                        }""")
                    except Exception as ex_err:
                        logger.debug(f"Atomic JS extraction error: {ex_err}")

                    if extracted_messages:
                        for msg_data in extracted_messages:
                            txt = msg_data.get("text", "").strip()
                            quoted_text = msg_data.get("quoted_text")
                            msg_time = msg_data.get("time") or ""
                            has_img = msg_data.get("has_image", False)
                            data_id = msg_data.get("id") or ""

                            if not txt and not has_img:
                                continue

                            q_snip = (quoted_text or "")[:20]
                            img_flag = "1" if has_img else "0"
                            if data_id:
                                msg_hash = f"id_{data_id}"
                            else:
                                msg_hash = f"{txt[:60]}_{len(txt)}_{q_snip}_{img_flag}"

                            if msg_hash not in seen_messages:
                                seen_messages.add(msg_hash)
                                logger.info(f"⚡ Incoming WhatsApp signal: {txt[:60]}...")

                                image_path = None
                                if has_img and not txt:
                                    txt = "[Screenshot / Image Attachment]"
                                    try:
                                        img_loc = main_pane.locator("img[src*='blob:'], img[src*='data:']").last
                                        if img_loc.count() > 0:
                                            os.makedirs(".whatsapp_media", exist_ok=True)
                                            image_path = os.path.abspath(f".whatsapp_media/wa_msg_{int(time.time()*1000)}.png")
                                            img_loc.screenshot(path=image_path)
                                    except Exception:
                                        pass

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
                                    "has_image": bool(image_path or has_img)
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

                    time.sleep(0.3)

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

    state = executor.load_state()
    state["status"] = "STOPPED"
    state["worker_pid"] = None
    executor.save_state(state)
    logger.info("WhatsApp worker exited.")


if __name__ == "__main__":
    run_worker()
