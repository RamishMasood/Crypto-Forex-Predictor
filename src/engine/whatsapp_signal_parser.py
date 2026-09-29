"""
WhatsApp Signal AI Parser with Persistent Setup Memory & Strict Risk Gates.
Uses Google Gemini Flash REST API (Zero SDK dependencies) to parse unformatted
Hinglish / Roman Urdu / English Forex & Indices signals and manage trade lifecycles.
"""

import os
import json
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("WhatsAppSignalParser")

SETUPS_CACHE_FILE = ".whatsapp_pending_setups.json"

class WhatsAppSignalParser:
    """
    Parses messy natural language messages from signal channels,
    maintains persistent symbol setup memory across days/hours,
    and enforces strict safety gates (Never trade without SL & TP).
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.setups_cache = self._load_setups_cache()

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

    def get_cached_setup(self, symbol: str) -> Optional[Dict[str, Any]]:
        clean_sym = symbol.upper().replace("/", "").replace("_", "").strip()
        # Direct lookup or alias
        if clean_sym in self.setups_cache:
            return self.setups_cache[clean_sym]
        for k, v in self.setups_cache.items():
            if k in clean_sym or clean_sym in k:
                return v
        return None

    def store_setup(self, symbol: str, setup_data: Dict[str, Any]):
        clean_sym = symbol.upper().replace("/", "").replace("_", "").strip()
        setup_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.setups_cache[clean_sym] = setup_data
        self._save_setups_cache()
        logger.info(f"Stored setup in persistent cache for '{clean_sym}': {setup_data}")

    def build_system_prompt(self, open_trades: List[Dict[str, Any]]) -> str:
        cached_summary = []
        for sym, data in self.setups_cache.items():
            cached_summary.append(
                f"- {sym}: {data.get('action', 'TRADE')} (Entry: {data.get('entry')}, SL: {data.get('stop_loss')}, "
                f"TP1: {data.get('tp1')}, TP2: {data.get('tp2')}, saved at {data.get('updated_at', 'recently')})"
            )
        cached_str = "\n".join(cached_summary) if cached_summary else "None"

        open_summary = []
        for t in open_trades:
            open_summary.append(f"- Ticket #{t.get('ticket')}: {t.get('symbol')} {t.get('type')} Vol: {t.get('volume')} Profit: ${t.get('profit', 0.0)}")
        open_str = "\n".join(open_summary) if open_summary else "No open trades currently in MT5"

        return f"""You are an elite, risk-averse Institutional Forex & Crypto Trade Parser specialized in decoding unformatted Hinglish, Roman Urdu, and English trading signal channels (such as Tradingpapa.com, Forex/Gold signals).

### PERSISTENT SYMBOL SETUP DATABASE (Previously stored levels for symbols):
{cached_str}

### CURRENTLY RUNNING TRADES ON MT5:
{open_str}

### CORE INSTRUCTIONS & PARSING RULES:
1. **MESSAGE TYPES & CONFIRMATION SEQUENCES**:
   - **SETUP (Awaiting Confirmation)**: When a message gives levels but contains phrases like "enter with confirmation", "entry after confirmation", "wait for confirmation", or "otherwise skip", Action: "SETUP_SAVED", confirmation_required: true. (DO NOT enter immediately!).
   - **CONFIRMATION TRIGGER / ENTRY**: When a message says "BTC trade active", "trade active now", "enter ho jao sabhi", "active now", or the admin replies to an earlier setup message, Action: "ENTER". Pull the symbol, direction, SL, and TPs from the quoted reply or the persistent setup database!
   - **DIRECT ENTRY**: When an immediate market order is called with levels, Action: "ENTER".
   - **PARTIAL_CLOSE**: When profit booking is called (e.g. "TP2 book karlo sabhi 95% position ko or 5% hold rakho", "Close half now"). Action: "PARTIAL_CLOSE", volume_pct: 95.0.
   - **CLOSE_ALL**: When full exit is called (e.g. "All positions booked in USDJPY guys and enjoy the profit", "All positions booked guys in US100 enjoy"). Action: "CLOSE_ALL".
   - **MODIFY_SL**: When SL change is called (e.g. "Move SL to BE", "SL cost pe le aao", "Trailing SL"). Action: "MODIFY_SL".
   - **HOLD**: Advises staying in trade (e.g. "Hold on guys both positions !"). Action: "HOLD".
   - **IGNORE**: Noise, chat, polls, reactions, performance recaps (e.g. "3 trades, 3 TPs Did you catch them? Poll", "Low risk ke sath guys"). Action: "IGNORE".

2. **WHATSAPP REPLY / QUOTED MESSAGES**:
   - When a message is a reply to an earlier setup (quoted text is provided), the quoted message is the direct parent reference! Derive the symbol, direction, SL, and TPs directly from the quoted message.

3. **STRICT SAFETY GATE REQUIREMENT**:
   - An "ENTER" action MUST HAVE a valid `stop_loss` (> 0) and at least `tp1` (> 0).
   - If the message says "enter ho jao" or "trade active" but gives no SL/TP, CHECK the quoted message or the PERSISTENT SYMBOL SETUP DATABASE!
   - If SL or TP1 is missing across message, quote, and database, you MUST flag `safety_gate_passed: false` and set `blocked_reason: "Missing Stop-Loss or Take-Profit"`.

### JSON OUTPUT FORMAT (Strict valid JSON only, no markdown formatting outside JSON):
{{
  "is_actionable": true / false,
  "action": "ENTER" | "SETUP_SAVED" | "PARTIAL_CLOSE" | "CLOSE_ALL" | "MODIFY_SL" | "HOLD" | "IGNORE",
  "symbol": "US100",
  "direction": "BUY" | "SELL" | null,
  "entry_price": 30450.0 or null,
  "stop_loss": 30590.0 or null,
  "tp1": 30315.0 or null,
  "tp2": 30140.0 or null,
  "tp3": null,
  "volume_pct": 95.0 or null,
  "confirmation_required": true / false,
  "safety_gate_passed": true / false,
  "blocked_reason": null or "Missing Stop-Loss or Take-Profit",
  "explanation": "Brief reasoning in English or Roman Urdu"
}}
"""

    def parse_message(
        self,
        message_text: str,
        quoted_text: Optional[str] = None,
        recent_history: Optional[List[Any]] = None,
        open_trades: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Sends message to Gemini Flash with full context (including quoted replies and history)
        and returns parsed actionable trade intent.
        """
        if not message_text or not message_text.strip():
            return {"is_actionable": False, "action": "IGNORE", "explanation": "Empty message"}

        if not self.api_key:
            logger.info("No Gemini API Key provided. Using intelligent heuristic signal parser.")
            return self._heuristic_fallback_parse(message_text, quoted_text, open_trades)

        open_trades = open_trades or []
        recent_history = recent_history or []

        system_instruction = self.build_system_prompt(open_trades)

        history_context = ""
        if recent_history:
            history_lines = []
            for m in recent_history[-15:]:
                if isinstance(m, dict):
                    t_str = f"[{m.get('time', '')}] " if m.get('time') else ""
                    q_str = f" (in reply to: '{m.get('quoted_text')}')" if m.get('quoted_text') else ""
                    history_lines.append(f"- {t_str}{m.get('text', '')}{q_str}")
                else:
                    history_lines.append(f"- {str(m)}")
            history_context = "### RECENT CONVERSATION HISTORY (Chronological channel timeline):\n" + "\n".join(history_lines) + "\n\n"

        quoted_context = f"### QUOTED / REPLIED-TO MESSAGE:\n\"{quoted_text.strip()}\"\n\n" if quoted_text else ""
        user_content = f"{history_context}{quoted_context}### NEW INCOMING MESSAGE TO PARSE:\n\"{message_text.strip()}\"\n\nParse this message accurately into the required JSON schema."

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_instruction}\n\n{user_content}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.05,
                "response_mime_type": "application/json"
            }
        }

        # Try Gemini 2.0 Flash or fallback to 1.5 Flash
        models = ["gemini-2.0-flash", "gemini-1.5-flash"]
        last_error = ""

        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            try:
                resp = requests.post(url, json=payload, timeout=12)
                if resp.status_code == 200:
                    res_json = resp.json()
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        parsed = json.loads(raw_text)

                        # Process setup persistence & safety gate verification
                        return self._post_process_parsed_signal(parsed, message_text)
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text}"
                    logger.warning(f"Gemini API model {model} returned {resp.status_code}. Attempting fallback...")
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error querying Gemini model {model}: {e}")

        # If Gemini API failed due to quota/network, fallback to heuristic parser
        logger.warning(f"Gemini API failed ({last_error}). Falling back to intelligent heuristic parser.")
        return self._heuristic_fallback_parse(message_text, open_trades)

    def _heuristic_fallback_parse(self, text: str, quoted_text: Optional[str] = None, open_trades: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Intelligent rule-based parser that handles specific Hinglish/English patterns,
        confirmation sequences, and quoted reply messages even if Gemini API key is offline.
        """
        import re
        t_low = text.lower()
        q_low = quoted_text.lower() if quoted_text else ""
        combined_text = f"{q_low} {t_low}" if q_low else t_low
        open_trades = open_trades or []

        # 1. Non-trade noise / polls / commentary
        if any(w in t_low for w in ["did you catch", "poll", "select one", "i caught", "i missed", "low risk ke sath"]):
            return {"is_actionable": False, "action": "IGNORE", "explanation": "Channel commentary/poll"}

        # 2. Hold instructions
        if "hold on" in t_low or ("hold rakho" in t_low and not ("book" in t_low)):
            return {"is_actionable": True, "action": "HOLD", "explanation": "Admin advised to hold position."}

        # 3. Detect symbol (check message, quoted message, then open trades)
        known_symbols = ["BTC", "ETH", "US100", "NAS100", "XAUUSD", "GOLD", "SILVER", "XAGUSD", "USDJPY", "EURGBP", "EURUSD", "GBPUSD", "GBPJPY", "BTCUSD", "ETHUSD"]
        detected_sym = None
        for s in known_symbols:
            if re.search(r'\b' + s.lower() + r'\b', t_low):
                detected_sym = "BTCUSD" if s == "BTC" else ("ETHUSD" if s == "ETH" else ("XAUUSD" if s == "GOLD" else ("XAGUSD" if s == "SILVER" else s)))
                break

        if not detected_sym and q_low:
            for s in known_symbols:
                if re.search(r'\b' + s.lower() + r'\b', q_low):
                    detected_sym = "BTCUSD" if s == "BTC" else ("ETHUSD" if s == "ETH" else ("XAUUSD" if s == "GOLD" else ("XAGUSD" if s == "SILVER" else s)))
                    break

        if not detected_sym and open_trades:
            detected_sym = open_trades[0].get("symbol", "").replace("/", "").replace("_", "").upper()

        # 4. Close All / All Booked
        if any(w in t_low for w in ["all positions booked", "all booked", "book karte chalo", "all exit"]):
            return self._post_process_parsed_signal({
                "is_actionable": True,
                "action": "CLOSE_ALL",
                "symbol": detected_sym or "US100",
                "explanation": f"Full exit signal for {detected_sym}"
            }, text)

        # 5. Partial Close / Profit Booking
        if "book" in t_low or "partial" in t_low:
            pct = 50.0
            pct_match = re.search(r'(\d+)\s*%', t_low)
            if pct_match:
                pct = float(pct_match.group(1))
            return self._post_process_parsed_signal({
                "is_actionable": True,
                "action": "PARTIAL_CLOSE",
                "symbol": detected_sym or (list(self.setups_cache.keys())[0] if self.setups_cache else "US100"),
                "volume_pct": pct,
                "explanation": f"Booked {pct}% profit"
            }, text)

        # 6. Detailed Setup with SL and TP (e.g. Screenshot 2)
        target_src = q_low if ("sl" in q_low and "sl" not in t_low) else t_low
        if "sl" in target_src and ("tp" in target_src or "tp 1" in target_src or "tp1" in target_src):
            direction = "SELL" if any(w in target_src for w in ["short", "sell"]) else "BUY"
            
            entry_m = re.search(r'entry\s*[-:]*\s*([\d,.]+)', target_src)
            sl_m = re.search(r'sl\s*[-:]*\s*([\d,.]+)', target_src)
            tp1_m = re.search(r'tp\s*1\s*[-:]*\s*([\d,.]+)', target_src)
            tp2_m = re.search(r'tp\s*2\s*[-:]*\s*([\d,.]+)', target_src)

            entry_p = float(entry_m.group(1).replace(",", "")) if entry_m else None
            sl_p = float(sl_m.group(1).replace(",", "")) if sl_m else None
            tp1_p = float(tp1_m.group(1).replace(",", "")) if tp1_m else None
            tp2_p = float(tp2_m.group(1).replace(",", "")) if tp2_m else None

            # Check if this setup requires confirmation
            req_confirm = any(w in t_low for w in ["confirmation", "confirm", "skip", "after confirmation", "wait"])
            action_type = "SETUP_SAVED" if req_confirm else "ENTER"

            parsed = {
                "is_actionable": True,
                "action": action_type,
                "symbol": detected_sym or "US100",
                "direction": direction,
                "entry_price": entry_p,
                "stop_loss": sl_p,
                "tp1": tp1_p,
                "tp2": tp2_p,
                "confirmation_required": req_confirm,
                "explanation": f"Setup parsed: {direction} {detected_sym} SL: {sl_p} TP1: {tp1_p} (Confirm required: {req_confirm})"
            }
            return self._post_process_parsed_signal(parsed, text, quoted_text)

        # 7. Confirmation / Execution Trigger (e.g. "BTC trade active", "trade active now", "enter ho jao sabhi Short ki side")
        if any(w in t_low for w in ["trade active", "active now", "active guys", "enter ho jao", "enter now", "buy now", "short now", "sell now"]):
            direction = "SELL" if any(w in combined_text for w in ["short", "sell"]) else "BUY"
            parsed = {
                "is_actionable": True,
                "action": "ENTER",
                "symbol": detected_sym or "BTCUSD",
                "direction": direction,
                "explanation": f"Confirmation trigger execution on {detected_sym} {direction}"
            }
            return self._post_process_parsed_signal(parsed, text, quoted_text)

        return {"is_actionable": False, "action": "IGNORE", "explanation": "Non-actionable message"}

    def _post_process_parsed_signal(self, parsed: Dict[str, Any], raw_message: str, quoted_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Validates parsed output, syncs with persistent setup store,
        tracks confirmation requirements, and rigorously enforces safety gates.
        """
        action = str(parsed.get("action", "IGNORE")).upper()
        symbol = str(parsed.get("symbol") or "").upper().replace("/", "").replace("_", "").strip()

        # 1. If message was a SETUP, store it in persistent memory
        if action == "SETUP_SAVED" or (parsed.get("stop_loss") and parsed.get("tp1")):
            if symbol and parsed.get("stop_loss") and parsed.get("tp1"):
                setup_data = {
                    "symbol": symbol,
                    "action": parsed.get("direction", "BUY"),
                    "entry": parsed.get("entry_price"),
                    "stop_loss": parsed.get("stop_loss"),
                    "tp1": parsed.get("tp1"),
                    "tp2": parsed.get("tp2"),
                    "tp3": parsed.get("tp3"),
                    "status": "PENDING_CONFIRMATION" if parsed.get("confirmation_required") else "ACTIVE",
                    "raw_message": raw_message
                }
                self.store_setup(symbol, setup_data)

        # 2. If message is an ENTER action, pull SL/TP from quoted reply OR setup cache
        if action == "ENTER":
            # First check quoted reply message if provided
            if quoted_text and (not parsed.get("stop_loss") or not parsed.get("tp1")):
                import re
                q_low = quoted_text.lower()
                sl_m = re.search(r'sl\s*[-:]*\s*([\d,.]+)', q_low)
                tp1_m = re.search(r'tp\s*1\s*[-:]*\s*([\d,.]+)', q_low)
                tp2_m = re.search(r'tp\s*2\s*[-:]*\s*([\d,.]+)', q_low)
                entry_m = re.search(r'entry\s*[-:]*\s*([\d,.]+)', q_low)
                if sl_m:
                    parsed["stop_loss"] = float(sl_m.group(1).replace(",", ""))
                if tp1_m:
                    parsed["tp1"] = float(tp1_m.group(1).replace(",", ""))
                if tp2_m:
                    parsed["tp2"] = float(tp2_m.group(1).replace(",", ""))
                if entry_m and not parsed.get("entry_price"):
                    parsed["entry_price"] = float(entry_m.group(1).replace(",", ""))

            # Next check persistent setup database
            cached = self.get_cached_setup(symbol) if symbol else None
            if (not parsed.get("stop_loss") or not parsed.get("tp1")) and cached:
                logger.info(f"Retrieved historical SL/TP levels from setup cache for {symbol}: {cached}")
                parsed["stop_loss"] = parsed.get("stop_loss") or cached.get("stop_loss")
                parsed["tp1"] = parsed.get("tp1") or cached.get("tp1")
                parsed["tp2"] = parsed.get("tp2") or cached.get("tp2")
                parsed["tp3"] = parsed.get("tp3") or cached.get("tp3")
                parsed["direction"] = parsed.get("direction") or cached.get("action")
                parsed["entry_price"] = parsed.get("entry_price") or cached.get("entry")
                # Mark cached setup as confirmed active
                cached["status"] = "CONFIRMED_ACTIVE"
                self.store_setup(symbol, cached)

            # STRICT SAFETY GATE CHECK (User Requirement: "trade jab tak na le jab tak AI ko SL aur TP na miljaen")
            sl = parsed.get("stop_loss")
            tp1 = parsed.get("tp1")
            if not sl or float(sl) <= 0 or not tp1 or float(tp1) <= 0:
                parsed["is_actionable"] = False
                parsed["action"] = "BLOCKED"
                parsed["safety_gate_passed"] = False
                parsed["blocked_reason"] = "STRICT SAFETY GATE: Missing Stop-Loss (SL) or Take-Profit (TP). Trade execution blocked."
                logger.warning(f"BLOCKED EXECUTION for {symbol}: SL or TP1 missing. Gate active.")
            else:
                parsed["safety_gate_passed"] = True

        return parsed
