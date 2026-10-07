"""
WhatsApp Signal AI Parser with Multimodal Image Recognition, Persistent Setup Memory & Strict Risk Gates.
Decodes unformatted Hinglish, Roman Urdu, and English Forex, Gold, and Crypto signal channels
(such as Tradingpapa.com, Forex/Gold signals), manages multi-pair lifecycles, and correlates confirmations.
Uses Google Gemini Flash REST API with intelligent heuristic fallback.
"""

import os
import re
import json
import time
import base64
import logging
import requests
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

try:
    from src.utils.env_loader import load_env
    load_env()
except Exception:
    pass

logger = logging.getLogger("WhatsAppSignalParser")

SETUPS_CACHE_FILE = ".whatsapp_pending_setups.json"
ENTRY_TRIGGERS_CACHE_FILE = ".whatsapp_entry_triggers.json"

def is_conditional_candle_pattern(text: str) -> bool:
    """
    Detects whether a message specifies a conditional candlestick formation,
    price action condition, rejection, retest, or breakout that must form BEFORE entering.
    e.g. '4150.957 pr agr engulfed candle bany 5 mins Ki to sell krna',
         'Sell after strong engulfed candle', 'agar 5m candle close ho to enter'.
    """
    if not text:
        return False
    t = text.lower()
    candle_keywords = [
        "engulf", "engulfed", "engulfing", "candle", "kandle",
        "rejection", "pinbar", "breakout", "retest", "wick", "bounce"
    ]
    has_candle_kw = any(k in t for k in candle_keywords)
    cond_framing = [
        "agr", "agar", "if", "jab", "when", "after", "wait for",
        "hone par", "hone pr", "close hone", "close ho", "bany to", "bane to", "baney to",
        "to sell", "to buy", "to enter", "tab sell", "tab buy", "tab enter", "pr sell", "pe sell"
    ]
    has_cond_framing = any(c in t for c in cond_framing)
    if has_candle_kw and has_cond_framing:
        return True

    patterns = [
        r'(?:agr|agar|if|jab|when)\s+.*(?:candle|kandle|engulf|bany|bane|close|rejection|retest)',
        r'(?:candle|kandle|engulf|bany|bane|close|rejection|retest).*(?:to|tab|phir|then)\s+(?:sell|buy|enter|short|long)',
        r'(?:sell|buy|enter|short|long)\s+after\s+(?:strong\s+)?(?:engulf|candle|rejection)',
        r'after\s+(?:strong\s+)?engulf',
        r'wait\s+for\s+confirmation.*(?:engulf|candle|close|rejection)',
        r'(?:5\s*mins?|15\s*mins?|1h|4h|1\s*hour)\s*(?:ki\s*)?(?:candle|close|engulf)',
        r'candle\s*(?:close|bany|bane|banay)\s*(?:hone|pe|par|pr|to)',
        r'rejection\s*(?:mile|dekhe|bany|bane)\s*(?:to|tab|par|pe|pr)',
        r'retest\s*(?:par|pe|pr|hone)\s*(?:to|sell|buy|enter)'
    ]
    return any(re.search(p, t) for p in patterns)

def is_explicit_entry_command(text: str) -> bool:
    """
    Detects explicit admin live execution commands such as 'enter ho jao', 'le lo', 'let's go', 'entered'.
    If the message is framed conditionally (e.g. 'agr candle bany to enter'), returns False.
    """
    if not text:
        return False
    t = text.lower()
    if is_conditional_candle_pattern(text):
        return False
    explicit_patterns = [
        r'\benter\s*(?:ho\s*jao|hojao|karo|karlo|now|karein)\b',
        r'\ble\s*lo\b',
        r'\blelo\b',
        r'\ble\s*li\s*trade\b',
        r'\ble\s*li\b',
        r'\ble\s*liya\b',
        r'\ble\s*liye\b',
        r"\blet'?s\s*go\b",
        r'\bgo\s*for\s*it\b',
        r'\bghus\s*jao\b',
        r'\bactive\s*now\b',
        r'\btrade\s*active\b',
        r'\bactive\s*guys\b',
        r'\bentered\b',
        r'\bdone\s*enter\b',
        r'\btaken\b',
        r'\brunning\s*now\b',
        r'\bbuy\s*(?:[a-z0-9/_-]+\s+)?now\b',
        r'\bsell\s*(?:[a-z0-9/_-]+\s+)?now\b',
        r'\bshort\s*(?:[a-z0-9/_-]+\s+)?now\b',
        r'\blong\s*(?:[a-z0-9/_-]+\s+)?now\b'
    ]
    return any(re.search(p, t) for p in explicit_patterns)

class WhatsAppSignalParser:
    """
    Parses messy natural language messages and screenshots from signal channels,
    maintains persistent symbol setup memory across days/hours, correlates
    follow-up confirmation triggers (e.g. 'Entered', MT5 screenshots),
    tracks multi-pair lifecycles, and enforces strict safety gates (Never trade without SL & TP).
    """

    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            try:
                from src.utils.env_loader import load_env
                load_env()
            except Exception:
                pass
            api_key = os.environ.get("GEMINI_API_KEY", "")
        self.api_key = (api_key or "").strip()
        self.setups_cache = self._load_setups_cache()
        self.preferred_model: Optional[str] = "gemini-3.8-flash"

    def set_api_key(self, key: str):
        if key:
            self.api_key = key.strip()

    def _load_setups_cache(self) -> Dict[str, Any]:
        if os.path.exists(SETUPS_CACHE_FILE):
            try:
                with open(SETUPS_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {SETUPS_CACHE_FILE}: {e}")
        return {}

    def _save_setups_cache(self):
        try:
            with open(SETUPS_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.setups_cache, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving {SETUPS_CACHE_FILE}: {e}")

    def _load_entry_triggers(self) -> Dict[str, Any]:
        if os.path.exists(ENTRY_TRIGGERS_CACHE_FILE):
            try:
                with open(ENTRY_TRIGGERS_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_entry_triggers(self, triggers: Dict[str, Any]):
        try:
            with open(ENTRY_TRIGGERS_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(triggers, f, indent=2)
        except Exception:
            pass

    def store_entry_trigger(self, symbol: str, direction: str, raw_message: str):
        """Stores an active entry command (e.g. 'EURGBP mein enter ho jao') awaiting SL/TP levels."""
        clean_sym = symbol.upper().replace("/", "").replace("_", "").strip()
        triggers = self._load_entry_triggers()
        triggers[clean_sym] = {
            "symbol": clean_sym,
            "direction": direction,
            "raw_message": raw_message,
            "timestamp": time.time(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self._save_entry_triggers(triggers)
        logger.info(f"Stored active entry trigger for {clean_sym} ({direction}) from message: '{raw_message[:50]}'")

    def get_active_entry_trigger(self, symbol: str, max_age_seconds: float = 900.0) -> Optional[Dict[str, Any]]:
        """Checks if admin commanded entry for this symbol in the last 15 minutes."""
        clean_sym = symbol.upper().replace("/", "").replace("_", "").strip()
        triggers = self._load_entry_triggers()
        trig = triggers.get(clean_sym)
        if not trig:
            for k, v in triggers.items():
                if k in clean_sym or clean_sym in k:
                    trig = v
                    break
        if trig:
            age = time.time() - float(trig.get("timestamp", 0))
            if age <= max_age_seconds:
                return trig
            else:
                self.clear_entry_trigger(clean_sym)
        return None

    def clear_entry_trigger(self, symbol: str):
        clean_sym = symbol.upper().replace("/", "").replace("_", "").strip()
        triggers = self._load_entry_triggers()
        removed = False
        if clean_sym in triggers:
            del triggers[clean_sym]
            removed = True
        for k in list(triggers.keys()):
            if k in clean_sym or clean_sym in k:
                del triggers[k]
                removed = True
        if removed:
            self._save_entry_triggers(triggers)

    def get_all_setups(self) -> Dict[str, Any]:
        """Always reloads the latest setups from disk to guarantee cross-process synchronization."""
        self.setups_cache = self._load_setups_cache()
        return self.setups_cache.copy()

    def get_cached_setup(self, symbol: str) -> Optional[Dict[str, Any]]:
        self.setups_cache = self._load_setups_cache()
        if not symbol:
            return None
        clean_sym = symbol.upper().replace("/", "").replace("_", "").strip()
        # Direct lookup
        if clean_sym in self.setups_cache:
            return self.setups_cache[clean_sym]
        # Partial match / alias
        for k, v in self.setups_cache.items():
            if k in clean_sym or clean_sym in k:
                return v
        return None

    def get_latest_pending_setup(self, channel_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves the most recent setup marked PENDING_CONFIRMATION from persistent cache.
        Allows one-word confirmations like 'Entered' to correlate automatically.
        """
        self.setups_cache = self._load_setups_cache()
        pending = [
            data for data in self.setups_cache.values()
            if isinstance(data, dict) and data.get("status") == "PENDING_CONFIRMATION"
        ]
        if not pending:
            return None
        # Sort by updated_at descending
        pending.sort(key=lambda x: str(x.get("updated_at", "")), reverse=True)
        return pending[0]

    def store_setup(self, symbol: str, setup_data: Dict[str, Any]):
        clean_sym = symbol.upper().replace("/", "").replace("_", "").strip()
        setup_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.setups_cache = self._load_setups_cache()
        self.setups_cache[clean_sym] = setup_data
        self._save_setups_cache()
        logger.info(f"Stored setup in persistent cache for '{clean_sym}': {setup_data}")

    def mark_setup_status(self, symbol: str, status: str, condition: Optional[str] = None):
        """
        Updates the execution status of a setup in persistent memory
        (e.g., CONFIRMED_ACTIVE once MT5 order successfully opens, or EXECUTION_FAILED / CLOSED).
        """
        clean_sym = symbol.upper().replace("/", "").replace("_", "").strip() if symbol else ""
        if not clean_sym:
            return
        setup = self.get_cached_setup(clean_sym)
        if setup:
            setup["status"] = status
            if condition:
                setup["condition"] = condition
            setup["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.store_setup(clean_sym, setup)
            logger.info(f"Updated setup {clean_sym} status to {status} ({condition})")

    def delete_setup(self, symbol: str) -> bool:
        """
        Permanently removes a setup from persistent setup memory (.whatsapp_pending_setups.json).
        """
        clean_sym = symbol.upper().replace("/", "").replace("_", "").strip() if symbol else ""
        if not clean_sym:
            return False
        self.setups_cache = self._load_setups_cache()
        removed = False
        if clean_sym in self.setups_cache:
            del self.setups_cache[clean_sym]
            removed = True
        for k in list(self.setups_cache.keys()):
            if clean_sym in k or k in clean_sym:
                del self.setups_cache[k]
                removed = True
        if removed:
            self._save_setups_cache()
            logger.info(f"Permanently deleted setup for '{clean_sym}' from persistent memory.")
        return removed

    def build_system_prompt(self, open_trades: List[Dict[str, Any]], channel_name: Optional[str] = None) -> str:
        self.setups_cache = self._load_setups_cache()
        cached_summary = []
        for sym, data in self.setups_cache.items():
            tps_str = f"TP1: {data.get('tp1')}, TP2: {data.get('tp2')}, TP3: {data.get('tp3')}, TP4: {data.get('tp4')}, TP5: {data.get('tp5')}"
            cached_summary.append(
                f"- {sym} [{data.get('status', 'SAVED')}]: {data.get('action', 'TRADE')} (Entry: {data.get('entry')}, SL: {data.get('stop_loss')}, {tps_str}, condition: '{data.get('condition', '')}', saved: {data.get('updated_at', 'recently')})"
            )
        cached_str = "\n".join(cached_summary) if cached_summary else "No setups currently saved in cache."

        open_summary = []
        for t in open_trades:
            open_summary.append(f"- Ticket #{t.get('ticket')}: {t.get('symbol')} {t.get('type')} Vol: {t.get('volume')} Entry: {t.get('price_open')} SL: {t.get('sl')} TP: {t.get('tp')} Profit: ${t.get('profit', 0.0)}")
        open_str = "\n".join(open_summary) if open_summary else "No open trades currently running in MT5."

        triggers = self._load_entry_triggers()
        trig_summary = []
        for sym, t_data in triggers.items():
            age_min = round((time.time() - float(t_data.get('timestamp', 0))) / 60, 1)
            trig_summary.append(f"- {sym} [{t_data.get('direction', 'TRADE')}]: '{t_data.get('raw_message', '')}' (commanded {age_min} mins ago - awaiting setup levels)")
        trig_str = "\n".join(trig_summary) if trig_summary else "No pending entry commands."

        target_channel_str = f"Active Channel: \"{channel_name}\"" if channel_name else "Active Channel: Tradingpapa.com forex (gold and silver)"

        return f"""You are an ultra-intelligent, institutional Forex, Gold, and Crypto Trade Signal Parser.
You decode unformatted Hinglish, Roman Urdu, and English trading signal messages and screenshots (specifically channels like Tradingpapa.com).

{target_channel_str}

### PERSISTENT SYMBOL SETUP DATABASE (Saved setups awaiting confirmation or actively running):
{cached_str}

### RECENT ACTIVE ENTRY COMMANDS (Admin commanded entry; awaiting setup levels):
{trig_str}

### CURRENTLY RUNNING TRADES ON MT5:
{open_str}

### CORE RULES & INTENT UNDERSTANDING:
1. **CHANNEL CONTEXT & SYMBOL INFERENCE**:
   - In tradingpapa forex, price ranges in the 2000s to 5000s (e.g. 4154.873) are GOLD / XAUUSD.
   - If the message mentions "btc", "btcusd", or "bitcoin" or price is 60,000-150,000 -> map to **BTCUSD**.
   - If the message mentions "eth", "ethusd", or "ethereum" or price is 2,000-5,000 in crypto context -> map to **ETHUSD**.
   - If a message specifies price levels near an open trade (e.g. "Cut the trade if it reach 4159" when GOLD was entered at 4155), correlate with that exact open symbol (XAUUSD)!
   - If a new ENTRY signal omits the symbol name, it defaults to GOLD / XAUUSD in this channel.

1.05 **CRITICAL: ATTACHED CHART / SCREENSHOT SYMBOL IDENTIFICATION (HIGHEST PRIORITY OVER CHANNEL DEFAULT)**:
   - When an image or TradingView chart screenshot is attached to the message:
     - You MUST read the symbol/pair from the chart image!
     - In TradingView charts: Look at the top-left title (e.g. "British Pound / Australian Dollar · 1h · FOREXCOM" -> **GBPAUD**; "Euro / US Dollar" -> **EURUSD**; "Gold / US Dollar" -> **XAUUSD**) and the red/blue price badge on the right axis (e.g. "GBPAUD 1.90037")!
     - The symbol shown in the chart image ALWAYS OVERRIDES ANY CHANNEL DEFAULT! If the chart shows British Pound / Australian Dollar (GBPAUD), the symbol is **GBPAUD**, NEVER XAUUSD!

1.06 **CRITICAL: TRADE MANAGEMENT ACTIONS (PARTIAL CLOSE, CLOSE ALL, SL MODIFICATION, HOLD) APPLY TO OPEN MT5 TRADES**:
   - When the admin commands a trade management action (such as "TP1 book 80% position", "90% nikal lo", "cut this trade", "close all", "SL to BE", "hold"):
     1. First check if a chart/image is attached -> extract the symbol from the chart!
     2. Second check `### CURRENTLY RUNNING TRADES ON MT5`:
        - Look at which symbols actually have active positions running on MT5!
        - If only ONE symbol is currently running on MT5 (e.g. `GBPAUD`), then the action APPLIES TO THAT RUNNING SYMBOL (`GBPAUD`)!
        - NEVER output XAUUSD if XAUUSD is NOT currently open on MT5 and another trade (e.g. GBPAUD) IS running! You cannot book profits or cut a trade that doesn't exist!
     3. Third check `### RECENT CONVERSATION HISTORY`:
        - Look at what admin discussed in recent messages (e.g. if admin said "GBPAUD ko hold rakhna" or "Still waiting for Gold", it confirms Gold has NOT entered and GBPAUD is the active trade)!

1.1 **CRITICAL: QUOTED / REPLIED-TO MESSAGE CORRELATION (HIGHEST PRIORITY OVER RECENT TRADES)**:
   - When the admin sends a message that replies to an earlier message (indicated by `### QUOTED / REPLIED-TO MESSAGE:`):
     - **For Exits / Cuts / Closures ("Cut this trade", "Cut krdo yrr", "Exit karlo", "Close this", "Nikal jao")**:
       - You MUST extract the symbol directly from the **QUOTED / REPLIED-TO MESSAGE**!
       - **Example Scenario**:
         Suppose WhatsApp trade for GOLD was opened at 09:15, and earlier trade for EURUSD was opened at 08:30.
         Now admin REPLIES to the EURUSD setup with: *"Cut this trade"* or *"Cut krdo yrr"*.
         The symbol MUST BE `"EURUSD"`. It MUST NEVER be GOLD, NEVER null, and NEVER the latest trade!
         Output: `action: "CLOSE_ALL"`, `symbol: "EURUSD"`, `explanation: "Admin replied to EURUSD setup to cut/close it."`
     - **For Entry Confirmation ("Entered", "Enter ho jao", "Active now")**:
       - The setup being entered is the one in the QUOTED message. Use that symbol and levels.
     - **For SL Modifications / Breakeven ("SL cost pe", "BE kar do", "SL to 4159")**:
       - Apply to the symbol quoted in the reply.
     - **Only when NO symbol is in the message AND NO symbol is in the quoted message (or there is no quote)**:
       - Only in this scenario should `symbol: null` be output to target the single most recent WhatsApp trade.

2. **CRITICAL: TWO-STEP ENTRY CORRELATION RULE (Admin Entry Command + Subsequent Setup Card)**:
   - Admin frequently works in two sequential steps:
     Step 1: Admin commands entry: e.g. "EURGBP mein enter ho jao sabhi long side", "BTC buy now", "Gold enter ho jao" (without SL/TP levels).
     Step 2: Admin posts the setup card:
       "EURGBP
        Long
        Entry - 0.85435
        SL - 0.85412
        TP 1 0.85461
        TP 2 0.85486
        Enter with confirmation otherwise skip this signal"
   - **WHEN STEP 1 ARRIVES**: Admin ordered entry, but SL/TP levels are not yet provided in this message.
     Output: `action: "ENTRY_TRIGGERED"`, `symbol: "EURGBP"`, `direction: "BUY"`, `safety_gate_passed: false`, `blocked_reason: "Admin commanded entry. Awaiting SL/TP setup card."`
   - **WHEN STEP 2 ARRIVES**: The admin ALREADY commanded "enter ho jao" in Step 1 (check RECENT CONVERSATION HISTORY and ACTIVE ENTRY COMMANDS)!
     Therefore, the disclaimer "Enter with confirmation otherwise skip this signal" IS SUPERSEDED AND ALREADY CONFIRMED!
     You MUST output:
     `action: "ENTER"`, `symbol: "EURGBP"`, `direction: "BUY"`, `stop_loss: 0.85412`, `tp1: 0.85461`, `tp2: 0.85486`, `confirmation_required: false`, `safety_gate_passed: true`!
     This executes immediately on MT5 at current market price!
   - **CASE B: PURE PRICE LIMIT / TOUCH SIGNALS (WITHOUT CANDLE PATTERN REQUIREMENT)**:
     - When admin posts a standard signal with an entry price or price zone (e.g. "Buy limit Gold 2470", "Gold buy @ 2502, wait for confirmation SL 2480 TP 2515") that does NOT require a candlestick pattern:
       You MUST output:
       `action: "ENTER"`, `symbol`: Extracted symbol (e.g. "BTCUSD", "XAUUSD"), `direction`: "BUY" or "SELL", `entry_price`: Explicit numeric entry price (or midpoint of entry zone), `stop_loss`: Exact SL, `tp1`, `tp2`, `tp3`... `safety_gate_passed`: true!
       NOTE: The MT5 Executor checks live market price against `entry_price`. If current market price is already near the entry price, it enters MARKET immediately without waiting. If price is far away, it places a PENDING LIMIT ORDER on MT5!

2.1 **CRITICAL: CONDITIONAL CANDLESTICK / PATTERN SETUPS ARE NEVER IMMEDIATE ENTRIES OR LIMITS**:
   - When a message specifies a future CANDLESTICK FORMATION, PRICE-ACTION, OR REJECTION CONDITION:
     Examples:
     - "4150.957 pr agr engulfed candle bany 5 mins Ki to sell krna"
     - "Sell after strong engulfed candle"
     - "agr 5m candle close ho to enter karna"
     - "agar rejection candle bane to buy/sell"
     - "retest hone par sell karna"
     - "agar 5m closing mile tab lelo"
   - **RULE**: This is a CONDITIONAL SETUP waiting for a price pattern to form. The candle has NOT engulfed or formed yet!
     You MUST output:
     `action: "SETUP_SAVED"`,
     `symbol`: Extracted symbol (e.g. "XAUUSD"),
     `direction`: "BUY" or "SELL",
     `entry_price`: Numeric price if mentioned (e.g. 4150.957),
     `stop_loss`: Exact SL (from message or pending cache),
     `tp1`, `tp2`, `tp3`: Exact TPs (from message or pending cache),
     `confirmation_required`: true,
     `safety_gate_passed`: true,
     `condition`: "Wait for 5m engulfed candle formation" (or exact condition),
     `explanation`: "Conditional candlestick pattern setup saved. Waiting for admin MT5 screenshot or entry trigger ('enter ho jao', 'le lo', 'let's go') before executing."
   - **DO NOT** output `action: "ENTER"` for conditional candle setups!

3. **CONFIRMATION TRIGGER / EXECUTION FOR SAVED SETUPS**:
   - When the admin follows up with an EXPLICIT LIVE ENTRY COMMAND:
     - "Entered", "Enter ho jao", "Active now", "Le li trade", "Enter now", "Short entered", "Ghus jao", "Let's go", "Le lo", "Lelo", "Buy now", "Sell now"
     - OR posts an MT5 mobile position screenshot showing an active open position (e.g. "GOLD, sell 2.00 4 155.22"):
     - You MUST correlate this with the saved pending setup in the database!
     - `action`: "ENTER"
     - `symbol`: Symbol of the pending setup (e.g. "BTCUSD" or "XAUUSD")
     - `direction`: Direction of pending setup
     - `stop_loss`: Exact SL from the pending setup
     - `tp1`, `tp2`, `tp3`, `tp4`, `tp5`: Exact TPs from the pending setup!
     - `confirmation_required`: false
     - `safety_gate_passed`: true
     - Note: Because SL and TP are retrieved from the verified pending setup, this passes the safety gate!

4. **EARLY CUT / STOP-LOSS MODIFICATION & BREAKEVEN**:
   - When admin says:
     - "Cut the trade if it reach 4159 or 4160", "4159 pe cut kardo", "agar 4159 touch kare to exit"
     - "SL cost pe le aao" / "SL to BE" / "Move SL to 4159" / "SL band kar do" / "Breakeven kar do" / "Risk free kar do"
     - `action`: "MODIFY_SL"
     - `symbol`: "XAUUSD" or specified coin
     - `stop_loss`: 4159.0 (if price specified) or null (if breakeven/cost requested)
     - `explanation`: "Tighten SL to 4159.0 or move to breakeven as instructed by admin"

5. **FULL EXIT / CUT SIGNAL (ROMAN URDU / HINDI / ENGLISH)**:
   - When admin says:
     - "Cut krdo yrr", "Cut kardo", "Cut krdo ye trade", "Exit karlo sabhi", "Close all", "Book karlo", "Nikal jao", "All positions booked"
     - `action`: "CLOSE_ALL"
     - `symbol`:
       1. If admin mentions a pair in text (e.g. "Gold", "BTC") -> output that symbol ("XAUUSD", "BTCUSD").
       2. If admin REPLIED to an earlier message (see `### QUOTED / REPLIED-TO MESSAGE:`) that contains a pair (e.g. replying to an EURUSD setup with "Cut this trade" or "Cut krdo yrr") -> output that quoted symbol ("EURUSD")!
       3. ONLY IF NO SYMBOL IS IN TEXT AND NO QUOTED MESSAGE CONTAINS A PAIR -> output `symbol: null`! (The executor will then close only the single most recent WhatsApp trade).

6. **PARTIAL PROFIT BOOKING & DYNAMIC PERCENTAGE (CRITICAL)**:
   - When admin commands partial profit booking, closing part of the trade, or locking gains:
     Examples:
     - "90% nikal lo baqi lage rehne do" / "90% book karlo" -> `volume_pct: 90.0`, `move_to_be: true`
     - "80% nikal lo baqi hold" / "80% close kar do" -> `volume_pct: 80.0`, `move_to_be: true`
     - "70% nikal lo" / "75% nikal lo" -> `volume_pct: 70.0` / `75.0`
     - "TP1 hit 90% nikal lo baqi hold" -> `volume_pct: 90.0`, `target_tp: "TP1"`, `move_to_be: true`
     - "TP1 hit book profit safe traders" -> `volume_pct: 50.0`, `target_tp: "TP1"`
     - "TP2 hit 80% nikal lo baqi runner" -> `volume_pct: 80.0`, `target_tp: "TP2"`, `move_to_be: true`
     - "half close kar do" / "50% book" -> `volume_pct: 50.0`
     - "thoda profit nikal lo" / "partially close" -> `volume_pct: 50.0`
   - **Fields**:
     - `action`: "PARTIAL_CLOSE"
     - `symbol`:
       - If a pair is mentioned in text (e.g. "Gold 80% nikal lo") -> output that symbol ("XAUUSD").
       - If admin REPLIED to an earlier message (see `### QUOTED / REPLIED-TO MESSAGE:`) -> output that quoted symbol!
       - If no symbol in text or quote -> output `null` (defaults to most recent WhatsApp trade).
     - `volume_pct`: Exact numeric percentage (e.g. 90.0, 80.0, 70.0, 50.0). Extract the exact number stated by admin!
     - `target_tp`: "TP1", "TP2", "TP3", or null if not specifically mentioned.
     - `move_to_be`: true if admin also said "baqi lage rehne do", "SL cost pe", "risk free", or "baqi hold".

7. **ADVISORIES, COMMENTARY & HOLD**:
   - When admin says:
     - "Low risk", "Trade Zara risky haii low risk m rehna", "High risk alert", "Drama bna rhi market", "Hold wohi kary Jo kr skta", "Fear & Manipulation", or posts macro news (e.g. Trump sanction news)
     - `action`: "HOLD"
     - `explanation`: "Admin market commentary / risk advisory"

8. **CANCEL / INVALIDATE PENDING SETUP OR LIMIT ORDER**:
   - When admin says:
     - "Ignore US100 trade I told you before, Invalid now", "Cancel setup", "US100 invalid now", "Invalid now", "Setup invalid", "Skip US100 ab mat lena", "Cancel US100 order", "Cancel limit"
     - `action`: "CANCEL_SETUP"
     - `symbol`: "US100" (or specified coin)
     - `explanation`: "Pending setup / MT5 limit order cancelled and invalidated as commanded by admin"

9. **MULTIMODAL IMAGE RECOGNITION (SCREENSHOTS & CHARTS)**:
   - If an image is provided:
     - **MT5 Mobile Position Screenshot (Proof of Entry)**:
       Examples: Black/dark mobile MT5 screen with blue/red profit lines such as:
       `GOLD, sell 2.00  4 185.47 -> 4 183.82  330.00`
       or `BTCUSD, buy 0.05  90 200 -> 90 450  125.00`
       This visual screenshot proves the admin has entered the market live!
       You MUST output:
       `action`: "ENTER",
       `symbol`: Extracted symbol (e.g. "XAUUSD" for GOLD, "BTCUSD", "EURUSD"),
       `direction`: "BUY" or "SELL" (read from screenshot),
       `entry_price`: The open price shown in the screenshot,
       `is_screenshot_proof`: true,
       `stop_loss`: Exact SL from the pending setup cache for this symbol (or from screenshot),
       `tp1`, `tp2`, `tp3`: Exact TPs from the pending setup cache,
       `safety_gate_passed`: true,
       `explanation`: "Admin posted MT5 mobile screenshot showing active position. Triggers immediate market entry if not already in trade."
     - **TradingView / Chart Analysis Screenshot**:
       Extract symbol, direction (arrow / candle bounce pattern), entry zone, SL, and TP targets. If no explicit SL/TP is written, extract key support/resistance boundaries from chart.
     - **News Screenshot**:
       Classify as market sentiment advisory -> `action: "HOLD"`.

10. **MULTI-PAIR INDEPENDENCE & MULTI-ACTION MESSAGES**:
    - Admin may track multiple symbols simultaneously (e.g. BTCUSD and GOLD).
    - If a message contains actions for MULTIPLE pairs (e.g. "BTC USD ka SL band kar do aur Gold ka trade cut kar do"), return a JSON object with `"signals"` array containing each parsed trade action!

11. **STRICT ZERO-HALLUCINATION SAFETY GATE**:
    - NEVER fabricate, guess, or invent numbers!
    - If a brand-new immediate entry is commanded WITHOUT SL and TP in the message, quote, image, or pending setup cache, mark `action: "BLOCKED"`, `safety_gate_passed: false`.

### JSON OUTPUT FORMAT (Strict JSON only, no markdown wrappers):
Single signal format:
{{
  "is_actionable": true / false,
  "action": "ENTER" | "SETUP_SAVED" | "PARTIAL_CLOSE" | "CLOSE_ALL" | "MODIFY_SL" | "HOLD" | "IGNORE" | "BLOCKED" | "CANCEL_SETUP",
  "symbol": "XAUUSD",
  "direction": "BUY" | "SELL" | null,
  "entry_price": 4154.873 or null,
  "stop_loss": 4162.706 or null,
  "tp1": 4144.002 or null,
  "tp2": 4131.297 or null,
  "tp3": 4120.328 or null,
  "tp4": 4109.817 or null,
  "tp5": 4098.897 or null,
  "volume_pct": 50.0 or null,
  "confirmation_required": true / false,
  "safety_gate_passed": true / false,
  "condition": "strong engulfed candle" or null,
  "blocked_reason": null or "STRICT SAFETY GATE: Missing Stop-Loss (SL) or Take-Profit (TP). Trade execution blocked.",
  "explanation": "Clear explanation in English or Roman Urdu"
}}

Or for multiple actions/pairs in one message:
{{
  "is_actionable": true,
  "action": "MULTI_SIGNAL",
  "signals": [
     {{ ... first signal object ... }},
     {{ ... second signal object ... }}
  ]
}}
"""

    def parse_message(
        self,
        message_text: str,
        quoted_text: Optional[str] = None,
        recent_history: Optional[List[Any]] = None,
        open_trades: Optional[List[Dict[str, Any]]] = None,
        channel_name: Optional[str] = None,
        image_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends message and optional image to Gemini Flash with full context (history, pending setups, open trades)
        and returns parsed actionable trade intent. Falls back to intelligent heuristic parser if offline.
        """
        clean_text = (message_text or "").strip()
        has_image = bool(image_path and os.path.exists(image_path))

        if not clean_text and not has_image:
            return {"is_actionable": False, "action": "IGNORE", "explanation": "Empty message"}

        if not clean_text and has_image:
            clean_text = "[Screenshot / Image Attachment]"

        if self.api_key is None:
            # Dynamically reload from environment / .env before giving up
            try:
                from src.utils.env_loader import load_env
                load_env()
            except Exception:
                pass
            self.api_key = (os.environ.get("GEMINI_API_KEY", "") or "").strip()

        if not self.api_key:
            logger.info("No Gemini API Key provided. Using intelligent heuristic signal parser.")
            return self._heuristic_fallback_parse(clean_text, quoted_text, open_trades, channel_name, image_path)

        open_trades = open_trades or []
        recent_history = recent_history or []

        system_instruction = self.build_system_prompt(open_trades, channel_name)

        history_context = ""
        if recent_history:
            history_lines = []
            for m in recent_history[-15:]:
                if isinstance(m, dict):
                    t_str = f"[{m.get('time', '')}] " if m.get('time') else ""
                    q_str = f" (in reply to: '{m.get('quoted_text')}')" if m.get('quoted_text') else ""
                    img_str = " [Image attached]" if m.get('has_image') else ""
                    history_lines.append(f"- {t_str}{m.get('text', '')}{img_str}{q_str}")
                else:
                    history_lines.append(f"- {str(m)}")
            history_context = "### RECENT CONVERSATION HISTORY (Chronological channel timeline):\n" + "\n".join(history_lines) + "\n\n"

        quoted_context = f"### QUOTED / REPLIED-TO MESSAGE:\n\"{quoted_text.strip()}\"\n\n" if quoted_text else ""
        user_content = f"{history_context}{quoted_context}### NEW INCOMING MESSAGE TO PARSE:\n\"{clean_text}\"\n\nParse this message accurately into the required JSON schema."

        parts = [{"text": f"{system_instruction}\n\n{user_content}"}]

        # Multimodal image attachment
        if has_image:
            try:
                with open(image_path, "rb") as img_f:
                    img_bytes = img_f.read()
                ext = os.path.splitext(image_path)[1].lower()
                mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                b64_data = base64.b64encode(img_bytes).decode("utf-8")
                parts.append({
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": b64_data
                    }
                })
                logger.info(f"Attached multimodal image ({mime_type}, {len(img_bytes)} bytes) to Gemini payload.")
            except Exception as img_err:
                logger.warning(f"Error encoding image for Gemini: {img_err}")

        payload = {
            "contents": [
                {
                    "parts": parts
                }
            ],
            "generationConfig": {
                "temperature": 0.05,
                "response_mime_type": "application/json"
            }
        }

        # Available Gemini Flash / Vision models (Exact requested cascade: 3.8 -> 3.7 -> 3.6 -> 3.5 -> 3.5-lite -> 2.5-flash-lite)
        models = [
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-2.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash-lite",
            "gemini-flash-latest",
            "gemini-flash-lite-latest"
        ]
        if self.preferred_model and self.preferred_model in models:
            models.remove(self.preferred_model)
            models.insert(0, self.preferred_model)

        last_error = ""
        payload_bytes = json.dumps(payload).encode("utf-8")

        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            res_json = None
            api_error_encountered = False

            # Primary: curl.exe (uses Windows Schannel, immune to OpenSSL SSLEOFError, fast & reliable)
            try:
                res = subprocess.run(
                    ["curl.exe", "--ssl-no-revoke", "-4", "-s", "--max-time", "14", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", "@-"],
                    input=payload_bytes,
                    capture_output=True,
                    timeout=16
                )
                if res.returncode == 0 and res.stdout:
                    out = res.stdout.decode("utf-8", errors="ignore").strip()
                    if out.startswith("{"):
                        d = json.loads(out)
                        if "error" in d:
                            api_error_encountered = True
                            err_msg = d.get("error", {}).get("message", "")
                            err_code = d.get("error", {}).get("code", 0)
                            last_error = f"HTTP {err_code}: {err_msg[:60]}"
                            logger.info(f"Gemini {model} returned API error {err_code} ({err_msg[:60]}). Falling back...")
                        else:
                            res_json = d
                elif res.returncode in [6, 7, 28, 35]:
                    logger.info(f"curl.exe network code {res.returncode} on {model}. Cascading to next model...")
                    continue
            except Exception as e:
                logger.debug(f"curl.exe exception on {model}: {e}")

            # Fallback: python requests
            if not res_json and not api_error_encountered:
                try:
                    resp = requests.post(url, json=payload, timeout=14)
                    if resp.status_code == 200:
                        res_json = resp.json()
                    else:
                        last_error = f"HTTP {resp.status_code}: {resp.text[:80]}"
                        logger.info(f"Gemini {model} HTTP {resp.status_code}. Falling back...")
                except Exception as e:
                    last_error = str(e)

            if res_json:
                candidates = res_json.get("candidates", [])
                if candidates:
                    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    try:
                        # Clean any stray markdown fences
                        cleaned_json = raw_text.strip()
                        if cleaned_json.startswith("```json"):
                            cleaned_json = cleaned_json[7:]
                        if cleaned_json.startswith("```"):
                            cleaned_json = cleaned_json[3:]
                        if cleaned_json.endswith("```"):
                            cleaned_json = cleaned_json[:-3]
                        parsed = json.loads(cleaned_json.strip())
                        self.preferred_model = model
                        logger.info(f"Successfully parsed WhatsApp signal with Gemini {model}!")
                        return self._post_process_parsed_signal(parsed, clean_text, quoted_text, channel_name, recent_history=recent_history, open_trades=open_trades)
                    except Exception as parse_err:
                        logger.warning(f"Error parsing JSON from {model}: {parse_err}")

        # Fallback to intelligent heuristic parser if Gemini calls fail
        logger.warning(f"Gemini API cascade exhausted ({last_error}). Falling back to intelligent heuristic parser.")
        return self._heuristic_fallback_parse(clean_text, quoted_text, open_trades, channel_name, image_path, recent_history=recent_history)

    def _infer_symbol(self, text: str, channel_name: Optional[str] = None, open_trades: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        """
        Deduces the trading symbol from text, price levels, open WhatsApp trades, persistent setups cache, and channel context.
        """
        t_low = text.lower()
        known_symbols = {
            "btc": "BTCUSD", "btcusd": "BTCUSD", "bitcoin": "BTCUSD",
            "eth": "ETHUSD", "ethusd": "ETHUSD", "ethereum": "ETHUSD",
            "gold": "XAUUSD", "xauusd": "XAUUSD", "xau": "XAUUSD",
            "silver": "XAGUSD", "xagusd": "XAGUSD", "xag": "XAGUSD",
            "us100": "US100", "nas100": "US100", "ustec": "US100",
            "us30": "US30", "dj30": "US30",
            "us500": "US500", "spx500": "US500",
            "eurusd": "EURUSD", "gbpusd": "GBPUSD", "usdjpy": "USDJPY",
            "gbpaud": "GBPAUD", "usdchf": "USDCHF",
            "eurgbp": "EURGBP", "gbpjpy": "GBPJPY", "usoil": "USOIL", "oil": "USOIL"
        }

        # 1. Direct symbol mentions
        for k, v in known_symbols.items():
            if re.search(r'\b' + re.escape(k) + r'\b', t_low):
                return v

        # 2. Price level magnitude inference
        num_matches = [float(n.replace(",", "")) for n in re.findall(r'\b\d{2,6}(?:\.\d+)?\b', text)]
        c_low = (channel_name or "").lower()

        for num in num_matches:
            # 2000 - 5500: Gold (forex channel) or ETH (crypto channel)
            if 1900 <= num <= 5500:
                if "crypto" in c_low:
                    return "ETHUSD"
                return "XAUUSD"
            # 20000 - 150000: Bitcoin
            if 20000 <= num <= 150000:
                return "BTCUSD"
            # 16000 - 24000: Nasdaq
            if 16000 <= num <= 24000 and "crypto" not in c_low:
                return "US100"
            # 18 - 60: Silver
            if 18 <= num <= 60 and ("silver" in c_low or "gold" in c_low):
                return "XAGUSD"

        # 3. Proximity to open WhatsApp trade prices (Strictly ignore Autonomous 999888 trades)
        valid_open = [
            ot for ot in (open_trades or [])
            if int(ot.get("magic", 0)) != 999888 and not str(ot.get("comment", "")).startswith("QS_")
        ]
        if valid_open and num_matches:
            best_sym = None
            min_dist = float('inf')
            for ot in valid_open:
                open_p = float(ot.get("price_open", 0.0))
                s = ot.get("symbol", "").upper().replace("M", "")
                for num in num_matches:
                    dist = abs(num - open_p)
                    # Close proximity match (< 5% relative price difference)
                    if open_p > 0 and (dist / open_p) < 0.05:
                        if dist < min_dist:
                            min_dist = dist
                            best_sym = s
            if best_sym:
                return best_sym

        # 4. Check active open WhatsApp trades (distinct symbol count)
        if valid_open:
            distinct_open_symbols = list({
                ot.get("symbol", "").upper().replace("M", "")
                for ot in valid_open
                if ot.get("symbol")
            })
            if len(distinct_open_symbols) == 1:
                return distinct_open_symbols[0]

        # 5. Check persistent setups cache for active or pending setups
        self.setups_cache = self._load_setups_cache()
        active_cached = [
            (sym, data) for sym, data in self.setups_cache.items()
            if isinstance(data, dict) and data.get("status") in ["CONFIRMED_ACTIVE", "PENDING_CONFIRMATION"]
        ]
        if active_cached:
            active_cached.sort(key=lambda x: str(x[1].get("updated_at", "")), reverse=True)
            return active_cached[0][0]

        # 6. Channel specialization default
        if "gold" in c_low or "silver" in c_low or "forex" in c_low:
            return "XAUUSD"
        if "crypto" in c_low:
            return "BTCUSD"

        return "XAUUSD"

    def _heuristic_fallback_parse(
        self,
        text: str,
        quoted_text: Optional[str] = None,
        open_trades: Optional[List[Dict[str, Any]]] = None,
        channel_name: Optional[str] = None,
        image_path: Optional[str] = None,
        recent_history: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Intelligent rule-based parser that handles specific Hinglish/English patterns,
        confirmation sequences, multi-pair instructions, and quoted reply messages even if Gemini API is offline.
        """
        t_low = text.lower().strip()
        q_low = quoted_text.lower().strip() if quoted_text else ""
        combined_text = f"{q_low} {t_low}" if q_low else t_low
        open_trades = open_trades or []

        # 0. Multi-coin / Multi-instruction detection in single message
        # e.g. "BTC USD ka SL band kar do aur Gold ka trade cut kar do"
        known_symbols = {
            "btc": "BTCUSD", "btcusd": "BTCUSD", "bitcoin": "BTCUSD",
            "eth": "ETHUSD", "ethusd": "ETHUSD", "ethereum": "ETHUSD",
            "gold": "XAUUSD", "xauusd": "XAUUSD", "xau": "XAUUSD",
            "silver": "XAGUSD", "xagusd": "XAGUSD", "xag": "XAGUSD"
        }
        symbols_found = set()
        for k, v in known_symbols.items():
            if re.search(r'\b' + re.escape(k) + r'\b', t_low):
                symbols_found.add(v)

        if len(symbols_found) >= 2:
            clauses = re.split(r'[\n;]+|\b(?:aur|and|lekin|saath\s+mein|saath\s+me|phir|then|also)\b', text, flags=re.IGNORECASE)
            sub_signals = []
            for clause in clauses:
                cl_clean = clause.strip()
                if not cl_clean:
                    continue
                cl_sig = self._heuristic_fallback_parse(cl_clean, quoted_text=quoted_text, open_trades=open_trades, channel_name=channel_name, recent_history=recent_history)
                if cl_sig.get("is_actionable") and cl_sig.get("action") not in ["IGNORE"]:
                    sub_signals.append(cl_sig)

            if len(sub_signals) >= 2:
                return {
                    "is_actionable": True,
                    "action": "MULTI_SIGNAL",
                    "signals": sub_signals,
                    "explanation": f"Multi-pair instructions: {len(sub_signals)} actions parsed."
                }

        # 0.5. Cancel / Invalidate pending setup (e.g. "Ignore US100 trade I told you before, Invalid now", "Cancel setup", "US100 invalid now")
        has_setup_levels = bool(re.search(r'\bsl\b|\bstop\b', t_low) and re.search(r'\btp\b|\btarget\b', t_low))
        cancel_patterns = [
            r'\b(?:cancel|radd)\s*(?:the\s*)?(?:trade|setup|signal|order)\b',
            r'\b(?:trade|setup|signal|order)\s*(?:is\s*)?invalid\b',
            r'\binvalid\s*now\b',
            r'\b(?:ignore|skip)\s*(?:the\s*)?(?:trade|setup|order)\s*(?:i\s*told|before)\b',
            r'\bab\s*mat\s*lena\b'
        ]
        is_cancel = any(re.search(p, t_low) for p in cancel_patterns)
        if is_cancel and not has_setup_levels:
            target_sym = self._infer_symbol(text, channel_name, open_trades) or "US100"
            return self._post_process_parsed_signal({
                "is_actionable": True,
                "action": "CANCEL_SETUP",
                "symbol": target_sym,
                "explanation": f"Pending setup for {target_sym} invalidated and removed from memory by admin."
            }, text, quoted_text, channel_name, recent_history=recent_history, open_trades=open_trades)

        # 1. Non-trade noise / polls / commentary
        noise_keywords = [
            "did you catch", "poll", "select one", "i caught", "i missed", "vote",
            "react", "subscribed", "joined", "thanks", "congrats"
        ]
        if any(w in t_low for w in noise_keywords):
            return {"is_actionable": False, "action": "IGNORE", "explanation": "Channel commentary/poll"}

        # 2. Risk alerts, market manipulation & advisory commentary -> HOLD
        hold_keywords = [
            "low risk", "trade zara risky", "high risk alert", "fear & manipulation",
            "fear and manipulation", "drama bna rhi market", "drama bana rahi",
            "hold wohi kary", "jo risk ly skta", "liquidity sweep", "market manipulate",
            "hold on", "hold rakho", "safe traders stay out"
        ]
        if any(w in t_low for w in hold_keywords) and not is_explicit_entry_command(text):
            return {
                "is_actionable": True,
                "action": "HOLD",
                "symbol": self._infer_symbol(text, channel_name, open_trades) or "XAUUSD",
                "explanation": "Admin market commentary / risk advisory (HOLD position)."
            }

        # 2.5. Uncaptioned screenshot attachment -> HOLD (advisory/chart/news)
        if image_path and (not text or text.strip() in ["[Screenshot / Image Attachment]", ""]):
            sym = self._infer_symbol(text, channel_name, open_trades) or "XAUUSD"
            return {
                "is_actionable": True,
                "action": "HOLD",
                "symbol": sym,
                "explanation": "Admin posted screenshot (chart/news advisory). Awaiting trade confirmation instructions."
            }

        # 3. Detect symbol
        detected_sym = self._infer_symbol(text, channel_name, open_trades)
        if not detected_sym and quoted_text:
            detected_sym = self._infer_symbol(quoted_text, channel_name, open_trades)

        # 4. Early Cut / SL Modification / Breakeven rules
        # Matches: "Cut the trade if it reach 4159", "4159 pe cut kardo", "agar 4159 hit kare to cut", "SL 4159", "sl band kar do", "cost pe le aao"
        num_extracted_sl = None
        is_modify_sl = False

        cond_cut_m = (
            re.search(r'cut(?:\s+the\s+trade)?\s+(?:if\s+it\s+reach(?:es)?|at)\s+([\d,.]+)', t_low)
            or re.search(r'agar\s+([\d,.]+)\s*(?:pe|par|touch|hit|reach)', t_low)
            or re.search(r'([\d,.]+)\s*(?:pe|par)\s*(?:cut|exit|nikal|sl)', t_low)
            or re.search(r'cut\s*(?:krdo|kardo)?\s*(?:if|agar)?\s*([\d,.]+)', t_low)
            or re.search(r'sl\s*(?:to|at|pe|par)\s*([\d,.]+)', t_low)
            or re.search(r'(?:modify|move|trail)\s*sl\s*(?:to|at|pe|par)?\s*([\d,.]+)', t_low)
        )
        if cond_cut_m:
            num_extracted_sl = float(cond_cut_m.group(1).replace(",", ""))
            is_modify_sl = True

        be_keywords = [
            "sl band", "cost pe", "cost par", "breakeven", "break even",
            "be pe", "sl to be", "risk free", "entry pe sl", "sl cost"
        ]
        if any(w in t_low for w in be_keywords):
            is_modify_sl = True

        if is_modify_sl:
            sym = detected_sym or self._infer_symbol(text, channel_name, open_trades) or "XAUUSD"
            expl = f"SL modification level set to {num_extracted_sl} for {sym}" if num_extracted_sl else f"Stop-Loss moved to Breakeven for {sym}"
            return self._post_process_parsed_signal({
                "is_actionable": True,
                "action": "MODIFY_SL",
                "symbol": sym,
                "stop_loss": num_extracted_sl,
                "explanation": expl
            }, text, quoted_text, channel_name, recent_history=recent_history, open_trades=open_trades)

        # 5. Full Exit / Close All (e.g. Image 5: "Cut krdo yrr", "All positions booked")
        close_keywords = [
            "cut krdo", "cut kardo", "exit karlo", "exit kardo", "exit ho jao", "close all",
            "all positions booked", "all booked", "book karte chalo", "all exit", "nikal jao",
            "full book", "close full", "cut the trade now", "cut trade now", "trade cut kar do",
            "trade cut kardo"
        ]
        if any(w in t_low for w in close_keywords):
            sym = detected_sym or self._infer_symbol(text, channel_name, open_trades) or "XAUUSD"
            return self._post_process_parsed_signal({
                "is_actionable": True,
                "action": "CLOSE_ALL",
                "symbol": sym,
                "explanation": f"Full exit / cut signal received for {sym}"
            }, text, quoted_text, channel_name, recent_history=recent_history, open_trades=open_trades)

        # 6. Partial Close / Profit Booking
        # e.g. "BTC USD ka 90% nikal lo TP mein se", "80% nikal lo baqi lage rehne do", "TP1 hit 90% nikal lo", "70% nikal lo"
        partial_keywords = [
            "partial", "partially", "nikal lo", "nikalo", "percent", "%",
            "kuch close", "tp close", "tp uska close", "tp1 book", "tp2 book",
            "tp1 hit", "tp2 hit", "book karlo", "book kar lo", "safe book", "half close"
        ]
        if any(w in t_low for w in partial_keywords):
            pct = 50.0
            pct_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:%|percent)', t_low)
            if not pct_match:
                pct_match = re.search(r'\b(95|90|85|80|75|70|65|60|50|40|30|25|20)\b\s*(?:nikal|close|book)', t_low)
            if pct_match:
                pct = float(pct_match.group(1))

            target_tp = None
            if "tp1" in t_low:
                target_tp = "TP1"
            elif "tp2" in t_low:
                target_tp = "TP2"
            elif "tp3" in t_low:
                target_tp = "TP3"

            move_be = any(k in t_low for k in ["cost", "be", "breakeven", "risk free", "hold", "lage rehne"])

            sym = detected_sym or self._infer_symbol(text, channel_name, open_trades)
            if not sym and quoted_text:
                q_up = quoted_text.upper()
                for p in open_trades or []:
                    ps = str(p.get("symbol", "")).upper()
                    if ps in q_up or ps.replace("M", "") in q_up:
                        sym = ps
                        break

            return self._post_process_parsed_signal({
                "is_actionable": True,
                "action": "PARTIAL_CLOSE",
                "symbol": sym,
                "volume_pct": pct,
                "target_tp": target_tp,
                "move_to_be": move_be,
                "explanation": f"Booked {pct}% profit on {sym or 'latest trade'}"
            }, text, quoted_text, channel_name, recent_history=recent_history, open_trades=open_trades)

        # 7. Detailed Setup with SL and TP (e.g. Image 1: Best Entry Zones, TP1-TP5, SL)
        target_src = q_low if ("sl" in q_low and "sl" not in t_low) else t_low
        has_sl = bool(re.search(r'\bsl\b|\bstop\b', target_src))
        has_tp = bool(re.search(r'\btp\b|\btp1\b|\btarget\b', target_src))

        if has_sl and has_tp:
            direction = "SELL" if any(w in target_src for w in ["short", "sell"]) else "BUY"

            entry_m = (
                re.search(r'(?:entry\s*zones?|entry|enter(?:\s*karengay|\s*karenge|\s*karna)?|\bzone\b)\s*[-:=@at\s]*(?:at\s*)?([\d,.]+)', target_src)
                or re.search(r'([\d,.]+)\s*(?:pe|par)\s*(?:entry|enter)', target_src)
            )
            sl_m = (
                re.search(r'(?:sl|stop\s*loss|stop)\s*(?:hoga|hogi|rakhna|at|pe|par|is|=|-|:|\s)*\s*([\d,.]+)', target_src)
                or re.search(r'([\d,.]+)\s*(?:ka|pe|par)\s*sl', target_src)
            )
            tp1_m = (
                re.search(r'(?:tp\s*1|tp1|target\s*1)\s*(?:hoga|hogi|at|pe|par|is|=|-|:|\s)*\s*([\d,.]+)', target_src)
                or re.search(r'([\d,.]+)\s*(?:ka|pe|par)\s*tp1', target_src)
            )
            tp2_m = (
                re.search(r'(?:tp\s*2|tp2|target\s*2)\s*(?:hoga|hogi|at|pe|par|is|=|-|:|\s)*\s*([\d,.]+)', target_src)
                or re.search(r'([\d,.]+)\s*(?:ka|pe|par)\s*tp2', target_src)
            )
            tp3_m = (
                re.search(r'(?:tp\s*3|tp3|target\s*3)\s*(?:hoga|hogi|at|pe|par|is|=|-|:|\s)*\s*([\d,.]+)', target_src)
            )
            tp4_m = (
                re.search(r'(?:tp\s*4|tp4|target\s*4)\s*(?:hoga|hogi|at|pe|par|is|=|-|:|\s)*\s*([\d,.]+)', target_src)
            )
            tp5_m = (
                re.search(r'(?:tp\s*5|tp5|target\s*5)\s*(?:hoga|hogi|at|pe|par|is|=|-|:|\s)*\s*([\d,.]+)', target_src)
            )

            entry_p = float(entry_m.group(1).replace(",", "")) if entry_m else None
            sl_p = float(sl_m.group(1).replace(",", "")) if sl_m else None
            tp1_p = float(tp1_m.group(1).replace(",", "")) if tp1_m else None
            tp2_p = float(tp2_m.group(1).replace(",", "")) if tp2_m else None
            tp3_p = float(tp3_m.group(1).replace(",", "")) if tp3_m else None
            tp4_p = float(tp4_m.group(1).replace(",", "")) if tp4_m else None
            tp5_p = float(tp5_m.group(1).replace(",", "")) if tp5_m else None

            # Check if confirmation required
            is_candle_cond = is_conditional_candle_pattern(text)
            req_confirm = is_candle_cond or any(w in t_low for w in [
                "wait for confirmation", "confirmation", "confirm", "skip this signal",
                "after strong engulfed", "engulfed candle", "otherwise skip"
            ])
            # Check if admin already commanded entry for this symbol in recent history / active triggers!
            has_prior_entry = bool(self.get_active_entry_trigger(detected_sym or "XAUUSD"))
            if not has_prior_entry and recent_history:
                sym_chk = (detected_sym or "XAUUSD").lower()
                for m in recent_history[-8:]:
                    m_txt = (m.get('text', '') if isinstance(m, dict) else str(m)).lower()
                    if any(w in m_txt for w in ["enter ho jao", "enter long", "enter short", "enter now", "ghus jao", "buy now", "sell now", "sabhi long", "sabhi short", "long side", "short side", "mein enter"]) and (sym_chk in m_txt or "sabhi" in m_txt or "traders" in m_txt):
                        has_prior_entry = True
                        break

            # If candlestick pattern condition is present, prior entry does NOT override it!
            if has_prior_entry and not is_candle_cond:
                action_type = "ENTER"
                req_confirm = False
            else:
                action_type = "SETUP_SAVED" if req_confirm else "ENTER"

            parsed = {
                "is_actionable": True,
                "action": action_type,
                "symbol": detected_sym or "XAUUSD",
                "direction": direction,
                "entry_price": entry_p,
                "stop_loss": sl_p,
                "tp1": tp1_p,
                "tp2": tp2_p,
                "tp3": tp3_p,
                "tp4": tp4_p,
                "tp5": tp5_p,
                "confirmation_required": req_confirm,
                "condition": f"Wait for candle pattern formation: {text.strip()}" if is_candle_cond else ("wait for confirmation" if req_confirm else None),
                "explanation": f"Setup parsed: {direction} {detected_sym or 'XAUUSD'} SL: {sl_p} TP1: {tp1_p} (Confirm required: {req_confirm})"
            }
            return self._post_process_parsed_signal(parsed, text, quoted_text, channel_name, recent_history=recent_history, open_trades=open_trades)

        # 7.5. Standalone Candlestick / Pattern Condition (e.g. "4150.957 pr agr engulfed candle bany 5 mins Ki to sell krna")
        if is_conditional_candle_pattern(text):
            sym = detected_sym or self._infer_symbol(text, channel_name, open_trades) or "XAUUSD"
            entry_m = (
                re.search(r'(?:entry\s*zones?|entry|enter(?:\s*karengay|\s*karenge|\s*karna)?|\bzone\b)\s*[-:=@at\s]*(?:at\s*)?([\d,.]+)', text)
                or re.search(r'([\d,.]+)\s*(?:pe|par|pr)\s*(?:entry|enter|agr|agar)', text)
                or re.search(r'([\d,.]+)\s*(?:pr|pe|par)', text)
            )
            entry_p = float(entry_m.group(1).replace(",", "")) if entry_m else None
            direction = "SELL" if any(w in t_low for w in ["short", "sell"]) else ("BUY" if any(w in t_low for w in ["buy", "long"]) else "SELL")

            cached = self.get_cached_setup(sym)
            sl_val = cached.get("stop_loss") if cached else None
            tp1_val = cached.get("tp1") if cached else None
            tp2_val = cached.get("tp2") if cached else None
            tp3_val = cached.get("tp3") if cached else None

            parsed = {
                "is_actionable": True,
                "action": "SETUP_SAVED",
                "symbol": sym,
                "direction": direction,
                "entry_price": entry_p or (cached.get("entry") if cached else None),
                "stop_loss": sl_val,
                "tp1": tp1_val,
                "tp2": tp2_val,
                "tp3": tp3_val,
                "confirmation_required": True,
                "condition": f"Wait for candle pattern formation: {text.strip()}",
                "safety_gate_passed": True,
                "explanation": f"Candlestick pattern setup for {sym}. Saved as pending setup awaiting admin confirmation trigger ('enter ho jao', 'le lo', 'let's go') or MT5 screenshot."
            }
            return self._post_process_parsed_signal(parsed, text, quoted_text, channel_name, recent_history=recent_history, open_trades=open_trades)

        # 8. Confirmation Triggers & Direct Trade Calls (e.g. "Entered", "Buy BTC now", "Sell now", "Active now", "Let's go", "Le lo")
        is_confirm_trigger = is_explicit_entry_command(text)
        if is_confirm_trigger:
            direction = "SELL" if any(w in combined_text for w in ["short", "sell"]) else ("BUY" if any(w in combined_text for w in ["buy", "long"]) else None)
            parsed = {
                "is_actionable": True,
                "action": "ENTER",
                "symbol": detected_sym or None,
                "direction": direction,
                "explanation": f"Order / confirmation trigger execution on {detected_sym or 'pending setup'}"
            }
            return self._post_process_parsed_signal(parsed, text, quoted_text, channel_name, recent_history=recent_history, open_trades=open_trades)

        return {"is_actionable": False, "action": "IGNORE", "explanation": "Non-actionable message"}

    def _post_process_parsed_signal(
        self,
        parsed: Dict[str, Any],
        raw_message: str,
        quoted_text: Optional[str] = None,
        channel_name: Optional[str] = None,
        recent_history: Optional[List[Any]] = None,
        open_trades: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Validates parsed output, syncs with persistent setup store,
        correlates confirmation triggers with pending setups,
        and rigorously enforces safety gates (Never execute without SL/TP).
        """
        # Handle multi-signal bundles
        if isinstance(parsed, dict) and isinstance(parsed.get("signals"), list):
            proc_list = []
            for s in parsed["signals"]:
                proc_list.append(self._post_process_parsed_signal(
                    s, raw_message, quoted_text, channel_name, recent_history, open_trades=open_trades
                ))
            parsed["signals"] = proc_list
            return parsed
        elif isinstance(parsed, list):
            return [self._post_process_parsed_signal(s, raw_message, quoted_text, channel_name, recent_history, open_trades=open_trades) for s in parsed]

        action = str(parsed.get("action", "IGNORE")).upper()
        symbol = str(parsed.get("symbol") or "").upper().replace("/", "").replace("_", "").strip()

        raw_low = raw_message.lower()
        q_low = quoted_text.lower() if quoted_text else ""
        combined_text = f"{raw_low} {q_low}"

        # Check active open WhatsApp trades (strictly ignoring Autonomous 999888 / QS_)
        valid_open = [
            ot for ot in (open_trades or [])
            if int(ot.get("magic", 0)) != 999888 and not str(ot.get("comment", "")).startswith("QS_")
        ]
        open_symbols = list({
            str(ot.get("symbol", "")).upper().replace("M", "").replace("/", "").replace("_", "").strip()
            for ot in valid_open
            if ot.get("symbol")
        })

        # CRITICAL: TRADE MANAGEMENT RE-ALIGNMENT (PARTIAL_CLOSE, CLOSE_ALL, MODIFY_SL, HOLD)
        # If admin is managing active trades, ensure symbol correlates with actual running MT5 trades!
        if action in ["PARTIAL_CLOSE", "CLOSE_ALL", "MODIFY_SL", "HOLD"]:
            explicit_other = False
            for s_name in ["BTC", "ETH", "US100", "US30", "EURUSD", "GBPUSD", "XAGUSD"]:
                if re.search(r'\b' + re.escape(s_name.lower()) + r'\b', raw_low):
                    if s_name not in open_symbols:
                        explicit_other = True
                        break

            clean_sym = symbol.upper().replace("/", "").replace("_", "").replace("M", "").strip() if symbol else ""
            if not explicit_other and open_symbols and (not clean_sym or clean_sym not in open_symbols):
                if len(open_symbols) == 1:
                    logger.info(f"🎯 Re-aligning {action} symbol from '{clean_sym}' to active open WhatsApp trade '{open_symbols[0]}'")
                    parsed["symbol"] = open_symbols[0]
                    symbol = open_symbols[0]
                elif recent_history:
                    for m in reversed(recent_history[-10:]):
                        m_txt = (m.get('text', '') if isinstance(m, dict) else str(m)).lower()
                        matched_h_sym = None
                        for osym in open_symbols:
                            if osym.lower() in m_txt or osym.lower().replace("usd", "") in m_txt:
                                matched_h_sym = osym
                                break
                        if matched_h_sym:
                            logger.info(f"🎯 Correlated {action} symbol '{matched_h_sym}' from recent history: '{m_txt[:40]}'")
                            parsed["symbol"] = matched_h_sym
                            symbol = matched_h_sym
                            break

        # CRITICAL SAFETY GATE: CANDLESTICK / PATTERN CONDITION INTERCEPT
        is_candle_cond = is_conditional_candle_pattern(raw_message)
        has_explicit_cmd = is_explicit_entry_command(raw_message)
        is_screenshot = bool(parsed.get("is_screenshot_proof"))

        if is_candle_cond and not has_explicit_cmd and not is_screenshot:
            action = "SETUP_SAVED"
            parsed["action"] = "SETUP_SAVED"
            parsed["confirmation_required"] = True
            if not parsed.get("condition") or parsed.get("condition") == "wait for confirmation":
                parsed["condition"] = f"Wait for candle pattern formation: {raw_message.strip()}"

        confirm_trigger_words = [
            "entered", "enter ho jao", "active now", "trade active", "active guys",
            "le li trade", "le li", "enter now", "short entered", "buy entered",
            "ghus jao", "done enter", "taken", "running now"
        ]
        is_confirmation_trigger = any(re.search(r'\b' + re.escape(w) + r'\b', raw_low) for w in confirm_trigger_words)

        # 0. Cancellation / Invalidation of pending setups
        if action in ["CANCEL_SETUP", "INVALIDATE"]:
            clean_s = symbol.upper().replace("/", "").replace("_", "").strip() if symbol else ""
            if clean_s:
                self.clear_entry_trigger(clean_s)
            removed = False
            if clean_s and clean_s in self.setups_cache:
                del self.setups_cache[clean_s]
                removed = True
            to_del = [k for k in list(self.setups_cache.keys()) if (clean_s and (k in clean_s or clean_s in k))]
            for k in to_del:
                if k in self.setups_cache:
                    del self.setups_cache[k]
                    removed = True
            if removed:
                self._save_setups_cache()
                logger.info(f"Invalidated and removed setup for '{clean_s}' from persistent memory.")
            parsed["is_actionable"] = True
            parsed["action"] = "CANCEL_SETUP"
            parsed["symbol"] = clean_s or "ALL"
            parsed["explanation"] = parsed.get("explanation") or f"Setup for {clean_s} invalidated/cancelled by admin."
            return parsed

        # 1. TWO-STEP CORRELATION CHECK:
        # If this message provides setup levels (SL and TP), check if admin ALREADY commanded entry before this card!
        sym = symbol or self._infer_symbol(raw_message, channel_name) or "XAUUSD"
        has_sl = bool(parsed.get("stop_loss"))
        has_tp1 = bool(parsed.get("tp1"))

        active_trigger = self.get_active_entry_trigger(sym)
        if not active_trigger and recent_history:
            sym_low = sym.lower()
            for m in (recent_history[-8:] if isinstance(recent_history, list) else []):
                m_txt = (m.get("text", "") if isinstance(m, dict) else str(m)).lower()
                if any(w in m_txt for w in ["enter ho jao", "enter long", "enter short", "enter now", "taking entry", "ghus jao", "buy now", "sell now", "sabhi long", "sabhi short", "long side", "short side", "mein enter"]) and (sym_low in m_txt or "sabhi" in m_txt or "traders" in m_txt):
                    active_trigger = {
                        "symbol": sym,
                        "direction": "SELL" if any(k in m_txt for k in ["short", "sell"]) else "BUY",
                        "raw_message": m_txt
                    }
                    break

        if (action in ["SETUP_SAVED", "ENTER"] or parsed.get("confirmation_required")) and has_sl and has_tp1 and not is_candle_cond:
            if active_trigger:
                logger.info(f"Prior entry trigger confirmed for {sym} ('{active_trigger.get('raw_message')}')! Overriding confirmation requirement and executing ENTER!")
                parsed["is_actionable"] = True
                parsed["action"] = "ENTER"
                parsed["symbol"] = sym
                parsed["confirmation_required"] = False
                parsed["safety_gate_passed"] = True
                parsed["blocked_reason"] = None
                parsed["direction"] = parsed.get("direction") or active_trigger.get("direction", "BUY")
                parsed["explanation"] = f"Prior entry command ('{active_trigger.get('raw_message')}') confirmed by admin! Executing {parsed.get('direction')} on {sym} with SL {parsed.get('stop_loss')} and TP1 {parsed.get('tp1')}."
                self.clear_entry_trigger(sym)
                clean_s = sym.upper().replace("/", "").replace("_", "").strip()
                c = self.get_cached_setup(clean_s)
                if c:
                    c["action"] = parsed.get("direction", c.get("action", "BUY"))
                    c["stop_loss"] = parsed.get("stop_loss", c.get("stop_loss"))
                    c["tp1"] = parsed.get("tp1", c.get("tp1"))
                    c["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self.store_setup(clean_s, c)
                return parsed

        # 1.5. If message was a standalone SETUP awaiting confirmation, store it in persistent memory
        if action == "SETUP_SAVED" or parsed.get("confirmation_required"):
            parsed["symbol"] = sym
            parsed["action"] = "SETUP_SAVED"
            parsed["safety_gate_passed"] = True
            parsed["blocked_reason"] = None

            cached = self.get_cached_setup(sym)
            if cached:
                parsed["stop_loss"] = parsed.get("stop_loss") or cached.get("stop_loss")
                parsed["tp1"] = parsed.get("tp1") or cached.get("tp1")
                parsed["tp2"] = parsed.get("tp2") or cached.get("tp2")
                parsed["tp3"] = parsed.get("tp3") or cached.get("tp3")
                parsed["tp4"] = parsed.get("tp4") or cached.get("tp4")
                parsed["tp5"] = parsed.get("tp5") or cached.get("tp5")
                parsed["entry_price"] = parsed.get("entry_price") or cached.get("entry")
                parsed["direction"] = parsed.get("direction") or cached.get("action", "SELL")

            if parsed.get("stop_loss") and parsed.get("tp1"):
                setup_data = {
                    "symbol": sym,
                    "action": parsed.get("direction", "SELL"),
                    "entry": parsed.get("entry_price"),
                    "stop_loss": parsed.get("stop_loss"),
                    "tp1": parsed.get("tp1"),
                    "tp2": parsed.get("tp2"),
                    "tp3": parsed.get("tp3"),
                    "tp4": parsed.get("tp4"),
                    "tp5": parsed.get("tp5"),
                    "condition": parsed.get("condition") or "wait for confirmation",
                    "status": "PENDING_CONFIRMATION",
                    "raw_message": raw_message
                }
                self.store_setup(sym, setup_data)
                logger.info(f"Stored pending confirmation setup for {sym}: SL={setup_data['stop_loss']} TP1={setup_data['tp1']}")
            return parsed

        # 2. If message is an ENTER action, resolve missing symbol & pull SL/TP from pending setup or quote
        if action in ["ENTER", "BUY", "SELL"]:
            # If symbol not specified (e.g. single-word 'Entered'), pull from latest pending setup
            if not symbol or symbol in ["NONE", "UNKNOWN", "NULL"]:
                latest_pending = self.get_latest_pending_setup(channel_name)
                if latest_pending:
                    symbol = latest_pending.get("symbol", "XAUUSD")
                    parsed["symbol"] = symbol
                    logger.info(f"Correlated single-word confirmation trigger with pending setup for '{symbol}'!")
                else:
                    symbol = self._infer_symbol(raw_message, channel_name) or "XAUUSD"
                    parsed["symbol"] = symbol

            # Pull levels from quoted reply if available
            if quoted_text and (not parsed.get("stop_loss") or not parsed.get("tp1")):
                sl_m = re.search(r'(?:sl|stop\s*loss)\s*[-:]*\s*([\d,.]+)', q_low)
                tp1_m = re.search(r'tp\s*1\s*[-:]*\s*([\d,.]+)', q_low)
                tp2_m = re.search(r'tp\s*2\s*[-:]*\s*([\d,.]+)', q_low)
                entry_m = re.search(r'(?:entry|zones?)\s*[-:]*\s*([\d,.]+)', q_low)
                if sl_m:
                    parsed["stop_loss"] = float(sl_m.group(1).replace(",", ""))
                if tp1_m:
                    parsed["tp1"] = float(tp1_m.group(1).replace(",", ""))
                if tp2_m:
                    parsed["tp2"] = float(tp2_m.group(1).replace(",", ""))
                if entry_m and not parsed.get("entry_price"):
                    parsed["entry_price"] = float(entry_m.group(1).replace(",", ""))

            # Correlate with persistent setup store if levels missing
            cached = self.get_cached_setup(symbol) if symbol else None
            if not cached and not symbol:
                cached = self.get_latest_pending_setup(channel_name)

            if cached and (not parsed.get("stop_loss") or not parsed.get("tp1")):
                logger.info(f"Retrieved historical SL/TP levels from persistent setup for {symbol}: {cached}")
                parsed["stop_loss"] = parsed.get("stop_loss") or cached.get("stop_loss")
                parsed["tp1"] = parsed.get("tp1") or cached.get("tp1")
                parsed["tp2"] = parsed.get("tp2") or cached.get("tp2")
                parsed["tp3"] = parsed.get("tp3") or cached.get("tp3")
                parsed["tp4"] = parsed.get("tp4") or cached.get("tp4")
                parsed["tp5"] = parsed.get("tp5") or cached.get("tp5")
                parsed["direction"] = parsed.get("direction") or cached.get("action", "BUY")
                parsed["entry_price"] = parsed.get("entry_price") or cached.get("entry")
                # Note: Cached setup status is managed by WhatsAppSignalExecutor upon actual MT5 order confirmation
                c_up = False
                if not cached.get("stop_loss") and parsed.get("stop_loss"):
                    cached["stop_loss"] = parsed.get("stop_loss")
                    c_up = True
                if c_up:
                    cached["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self.store_setup(symbol, cached)

            # STRICT ZERO-HALLUCINATION SAFETY GATE CHECK
            sl = parsed.get("stop_loss")
            tp1 = parsed.get("tp1")
            if not sl or float(sl) <= 0 or not tp1 or float(tp1) <= 0:
                clean_s = symbol.upper().replace("/", "").replace("_", "").strip() if symbol else (self._infer_symbol(raw_message, channel_name) or "XAUUSD")
                direction = parsed.get("direction") or ("SELL" if any(w in raw_low for w in ["short", "sell"]) else "BUY")
                # If admin explicitly commanded entry but SL/TP levels are not yet provided
                if any(w in raw_low for w in ["enter", "ghus jao", "buy", "sell", "long", "short", "active", "le li", "taking"]):
                    self.store_entry_trigger(clean_s, direction, raw_message)
                    parsed["is_actionable"] = True
                    parsed["action"] = "ENTRY_TRIGGERED"
                    parsed["symbol"] = clean_s
                    parsed["direction"] = direction
                    parsed["safety_gate_passed"] = False
                    parsed["blocked_reason"] = f"Admin commanded {direction} entry on {clean_s}. Awaiting SL/TP setup card."
                    parsed["explanation"] = f"Admin commanded {direction} entry on {clean_s}. Active entry trigger saved, ready to execute when setup card is posted."
                    logger.info(f"⚡ Saved ACTIVE_ENTRY_TRIGGER for {clean_s} ({direction}). Awaiting setup card.")
                else:
                    parsed["is_actionable"] = False
                    parsed["action"] = "BLOCKED"
                    parsed["safety_gate_passed"] = False
                    parsed["blocked_reason"] = "STRICT SAFETY GATE: Missing Stop-Loss (SL) or Take-Profit (TP). Trade execution blocked."
                    logger.warning(f"BLOCKED EXECUTION for {symbol}: SL or TP1 missing. Gate active.")
            else:
                parsed["safety_gate_passed"] = True
                clean_s = symbol.upper().replace("/", "").replace("_", "").strip() if symbol else ""
                if clean_s:
                    self.clear_entry_trigger(clean_s)
                    c = self.get_cached_setup(clean_s)
                    if c:
                        # Keep levels in sync without falsely claiming live MT5 trade before execution
                        c["action"] = parsed.get("direction", c.get("action", "BUY"))
                        c["stop_loss"] = parsed.get("stop_loss", c.get("stop_loss"))
                        c["tp1"] = parsed.get("tp1", c.get("tp1"))
                        c["tp2"] = parsed.get("tp2", c.get("tp2"))
                        c["tp3"] = parsed.get("tp3", c.get("tp3"))
                        c["tp4"] = parsed.get("tp4", c.get("tp4"))
                        c["tp5"] = parsed.get("tp5", c.get("tp5"))
                        c["updated_at"] = datetime.now(timezone.utc).isoformat()
                        self.store_setup(clean_s, c)

        return parsed
