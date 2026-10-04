"""
WhatsApp Signal MT5 Trade Executor.
Executes and manages trades derived from WhatsApp Signal Channel messages
with strict risk capping, lot size control, position tracking, and isolated Magic Number management.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from src.engine.mt5_executor import MT5TradeExecutor
from src.data.forex_feeds import MT5ExnessProvider

try:
    from src.utils.env_loader import load_env
    load_env()
except Exception:
    pass

logger = logging.getLogger("WhatsAppSignalExecutor")

SETTINGS_FILE = ".whatsapp_signal_settings.json"
STATE_FILE = ".whatsapp_signal_state.json"

WHATSAPP_MAGIC_NUMBER = 777666  # Dedicated Magic Number strictly isolating WhatsApp trades from Autonomous Engine (999888)
WHATSAPP_COMMENT_PREFIX = "WAPP"

DEFAULT_SETTINGS = {
    "enabled": True,
    "selected_channel": "Tradingpapa.com forex (gold and silver)",
    "gemini_api_key": "",
    "max_dollar_risk": 50.0,
    "batch_lot_size": 0.05,
    "max_active_signal_trades": 5,
    "auto_be_on_tp1": True
}

class WhatsAppSignalExecutor:
    """
    Interfaces between parsed AI signals and MT5 execution.
    Honors all user risk controls: Lot Size, Max Dollar Risk Cap, Max Concurrent Trades.
    Guarantees strict isolation from Autonomous Trader Engine.
    """

    def __init__(self, parser=None):
        self.executor = MT5TradeExecutor()
        self.exness_provider = MT5ExnessProvider()
        self.settings = self.load_settings()
        self.state = self.load_state()
        self.parser = parser
        if self.parser is None:
            try:
                from src.engine.whatsapp_signal_parser import WhatsAppSignalParser
                self.parser = WhatsAppSignalParser()
            except Exception:
                self.parser = None

    def load_settings(self) -> Dict[str, Any]:
        res = DEFAULT_SETTINGS.copy()

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    res.update(data)
            except Exception as e:
                logger.error(f"Error loading {SETTINGS_FILE}: {e}")

        # ALWAYS fetch API key exclusively from .env and environment (never expose secret in JSON file)
        try:
            from src.utils.env_loader import load_env
            load_env()
        except Exception:
            pass

        env_key = os.environ.get("GEMINI_API_KEY", "").strip()
        res["gemini_api_key"] = env_key

        return res

    def save_settings(self, new_settings: Dict[str, Any]):
        try:
            # 1. Strictly persist secret key to .env file and environment
            api_key = str(new_settings.get("gemini_api_key", "")).strip()
            if api_key:
                try:
                    from src.utils.env_loader import set_env_variable
                    set_env_variable("GEMINI_API_KEY", api_key)
                except Exception as env_err:
                    logger.debug(f"Could not write to .env: {env_err}")
                os.environ["GEMINI_API_KEY"] = api_key

            # 2. Scrub secret key from JSON file so it NEVER leaks into git
            file_settings = new_settings.copy()
            file_settings["gemini_api_key"] = ""  # Keep blank in git-visible JSON!

            self.settings = new_settings  # In-memory settings keeps the active key
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(file_settings, f, indent=2)

            logger.info("WhatsApp Signal settings saved successfully (Secret key strictly in .env).")
        except Exception as e:
            logger.error(f"Error saving {SETTINGS_FILE}: {e}")

    def load_state(self) -> Dict[str, Any]:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {STATE_FILE}: {e}")
        return {
            "status": "IDLE",
            "active_signal_trades": {},
            "activity_log": [],
            "last_message_processed": None,
            "connected_channel": None
        }

    def save_state(self, new_state: Dict[str, Any]):
        try:
            self.state = new_state
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(new_state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving {STATE_FILE}: {e}")

    def _append_log(self, entry: Dict[str, Any]):
        state = self.load_state()
        logs = state.get("activity_log", [])
        entry["timestamp"] = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

        # Robust deduplication guard: prevent identical consecutive/recent messages from duplicating in log
        new_raw = (entry.get("raw_message") or "").strip()
        new_action = str(entry.get("action") or "").strip()
        new_sym = str(entry.get("symbol") or "").strip()

        if new_raw:
            for ex in logs[:8]:
                ex_raw = (ex.get("raw_message") or "").strip()
                ex_action = str(ex.get("action") or "").strip()
                ex_sym = str(ex.get("symbol") or "").strip()
                if ex_raw == new_raw and ex_action == new_action and ex_sym == new_sym:
                    # Update status/details in place instead of duplicating the row
                    ex["status"] = entry.get("status", ex.get("status"))
                    ex["details"] = entry.get("details", ex.get("details"))
                    ex["timestamp"] = entry["timestamp"]
                    self.save_state(state)
                    return

        logs.insert(0, entry)
        state["activity_log"] = logs[:100]  # keep latest 100
        self.save_state(state)

    def resolve_broker_symbol(self, raw_symbol: str) -> Optional[str]:
        clean = raw_symbol.upper().replace("/", "").replace("_", "").strip()

        # Handle specific common names
        mapping_aliases = {
            "US100": ["USTECm", "USTEC", "US100m", "US100", "NAS100m", "NAS100"],
            "NAS100": ["USTECm", "USTEC", "NAS100m", "NAS100", "US100m"],
            "US30": ["US30m", "US30", "DJ30m", "DJ30"],
            "US500": ["US500m", "US500", "SPX500m", "SP500"],
            "GOLD": ["XAUUSDm", "XAUUSD", "GOLDm"],
            "XAUUSD": ["XAUUSDm", "XAUUSD", "GOLDm"],
            "SILVER": ["XAGUSDm", "XAGUSD", "SILVERm"],
            "XAGUSD": ["XAGUSDm", "XAGUSD", "SILVERm"],
            "OIL": ["USOILm", "USOIL"],
            "USOIL": ["USOILm", "USOIL"],
            "BTCUSD": ["BTCUSDm", "BTCUSD"],
            "ETHUSD": ["ETHUSDm", "ETHUSD"]
        }

        try:
            import MetaTrader5 as mt5
            self.executor._ensure_connection()

            # Check aliases first
            if clean in mapping_aliases:
                for candidate in mapping_aliases[clean]:
                    s_info = mt5.symbol_info(candidate)
                    if s_info is not None:
                        if not s_info.visible:
                            mt5.symbol_select(candidate, True)
                        return candidate

            # Check via Exness Provider
            found = self.exness_provider.get_exness_symbol(raw_symbol)
            if found:
                return found

            # Try raw or standard suffix
            for suffix in ["m", "", "c", ".r"]:
                cand = f"{clean}{suffix}"
                s_info = mt5.symbol_info(cand)
                if s_info is not None:
                    if not s_info.visible:
                        mt5.symbol_select(cand, True)
                    return cand

            return clean
        except Exception as e:
            logger.error(f"Error resolving broker symbol for {raw_symbol}: {e}")
            return clean

    def _get_whatsapp_positions(self, symbol: Optional[str] = None, broker_sym: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        STRICT ISOLATION GUARANTEE:
        Returns ONLY open MT5 positions that belong exclusively to WhatsApp Signals.
        Positions belonging to Autonomous Trader (Magic 999888 / QS_) are strictly excluded!
        """
        all_positions = self.executor.get_open_positions()
        state = self.load_state()
        active_trades = state.get("active_signal_trades", {})

        # Collect all recorded ticket IDs for WhatsApp trades
        recorded_tickets = set()
        for t_info in active_trades.values():
            for tkt in t_info.get("tickets", []):
                if isinstance(tkt, dict):
                    recorded_tickets.add(int(tkt.get("ticket", 0)))
                else:
                    try:
                        recorded_tickets.add(int(tkt))
                    except Exception:
                        pass

        wa_positions = []
        for p in all_positions:
            p_magic = int(p.get("magic", 0))
            p_comment = str(p.get("comment", ""))
            p_ticket = int(p.get("ticket", 0))

            # HARD GUARD: NEVER touch Autonomous Engine trades (Magic 999888 or comment starting with QS_)!
            if p_magic == self.executor.MAGIC_NUMBER or p_comment.startswith("QS_"):
                continue

            # Check if this position is definitively a WhatsApp Signal trade
            is_wa_trade = (
                p_magic == WHATSAPP_MAGIC_NUMBER
                or p_comment.startswith(WHATSAPP_COMMENT_PREFIX)
                or p_ticket in recorded_tickets
            )
            if not is_wa_trade:
                continue

            # Match symbol if specified
            if symbol or broker_sym:
                p_sym = str(p.get("symbol", "")).upper()
                s_match = (symbol and symbol in p_sym) or (broker_sym and broker_sym in p_sym)
                if not s_match:
                    continue

            wa_positions.append(p)

        return wa_positions

    def get_open_whatsapp_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        STRICT ISOLATION GUARANTEE:
        Returns ONLY open MT5 positions that belong exclusively to WhatsApp Signals (Magic 777666 / WAPP).
        Positions belonging to Autonomous Trader (Magic 999888 / QS_) are strictly excluded!
        """
        return self._get_whatsapp_positions(symbol=symbol)

    def get_pending_whatsapp_orders(self, symbol: Optional[str] = None, broker_sym: Optional[str] = None) -> List[Any]:
        """
        Returns active pending orders (limit/stop) placed by WhatsApp Signals (Magic 777666 / WAPP).
        """
        if not self.executor._ensure_connection():
            return []
        import MetaTrader5 as mt5
        b_sym = broker_sym or (self.resolve_broker_symbol(symbol) if symbol else None)
        try:
            orders = mt5.orders_get(symbol=b_sym) if b_sym else mt5.orders_get()
        except Exception as e:
            logger.debug(f"orders_get error: {e}")
            orders = None

        if not orders:
            return []

        wa_orders = []
        for o in orders:
            o_magic = int(getattr(o, 'magic', 0))
            o_cmt = str(getattr(o, 'comment', ''))
            if o_magic == WHATSAPP_MAGIC_NUMBER or o_cmt.startswith(WHATSAPP_COMMENT_PREFIX):
                if symbol or b_sym:
                    o_sym = str(getattr(o, 'symbol', '')).upper()
                    if (symbol and symbol in o_sym) or (b_sym and b_sym in o_sym):
                        wa_orders.append(o)
                else:
                    wa_orders.append(o)
        return wa_orders

    def cancel_pending_whatsapp_orders(self, symbol: Optional[str] = None) -> List[int]:
        """
        Cancels any active MT5 pending limit/stop orders for WhatsApp (Magic 777666 / WAPP).
        """
        if not self.executor._ensure_connection():
            return []
        import MetaTrader5 as mt5
        cancelled = []
        pending_orders = self.get_pending_whatsapp_orders(symbol=symbol)
        for o in pending_orders:
            tkt = int(getattr(o, 'ticket', 0))
            req = {
                'action': mt5.TRADE_ACTION_REMOVE,
                'order': tkt,
                'magic': WHATSAPP_MAGIC_NUMBER
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                cancelled.append(tkt)
                logger.info(f"🗑️ Cancelled MT5 WhatsApp pending limit order #{tkt} for {getattr(o, 'symbol', '')}")
            else:
                comm = getattr(res, 'comment', 'Remove failed') if res else 'No response'
                logger.warning(f"Failed to cancel MT5 pending order #{tkt}: {comm}")
        return cancelled

    def place_pending_whatsapp_order(
        self,
        broker_sym: str,
        direction: str,
        target_entry: float,
        sl_price: float,
        tp1_price: float,
        tp2_price: float = 0.0,
        tp3_price: float = 0.0,
        lot_split: Dict[str, float] = None,
        raw_symbol: str = ""
    ) -> Dict[str, Any]:
        """
        Places a Pending Limit or Stop Order on MT5 when current market price is not close to signal entry.
        """
        if not self.executor._ensure_connection():
            return {"success": False, "error": "MT5 not connected"}

        import MetaTrader5 as mt5
        tick = mt5.symbol_info_tick(broker_sym)
        if not tick:
            return {"success": False, "error": f"Cannot fetch tick for {broker_sym}"}

        specs = self.executor.get_symbol_trade_specs(broker_sym)
        if not specs:
            return {"success": False, "error": f"Cannot fetch specs for {broker_sym}"}

        digits = specs['digits']
        type_filling = specs['filling_mode']
        current_price = tick.ask if direction == "BUY" else tick.bid

        # Determine pending order type
        if direction == "BUY":
            order_type = mt5.ORDER_TYPE_BUY_LIMIT if target_entry < current_price else mt5.ORDER_TYPE_BUY_STOP
            order_label = "BUY_LIMIT" if target_entry < current_price else "BUY_STOP"
        else:
            order_type = mt5.ORDER_TYPE_SELL_LIMIT if target_entry > current_price else mt5.ORDER_TYPE_SELL_STOP
            order_label = "SELL_LIMIT" if target_entry > current_price else "SELL_STOP"

        orders_to_place = []
        if lot_split:
            if lot_split.get('tp1_lots', 0.0) > 0:
                orders_to_place.append(('TP1', lot_split['tp1_lots'], tp1_price))
            if lot_split.get('tp2_lots', 0.0) > 0 and tp2_price > 0:
                orders_to_place.append(('TP2', lot_split['tp2_lots'], tp2_price))
            if lot_split.get('tp3_lots', 0.0) > 0 and tp3_price > 0:
                orders_to_place.append(('TP3', lot_split['tp3_lots'], tp3_price))

        if not orders_to_place:
            orders_to_place.append(('TP1', 0.05, tp1_price))

        placed_tickets = []
        errors = []

        for label, volume, tp_val in orders_to_place:
            req = {
                'action': mt5.TRADE_ACTION_PENDING,
                'symbol': broker_sym,
                'volume': float(volume),
                'type': order_type,
                'price': round(float(target_entry), digits),
                'sl': round(float(sl_price), digits) if sl_price > 0 else 0.0,
                'tp': round(float(tp_val), digits) if tp_val > 0 else 0.0,
                'deviation': 20,
                'magic': WHATSAPP_MAGIC_NUMBER,
                'comment': f"{WHATSAPP_COMMENT_PREFIX}_{label}_LIMIT",
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': type_filling
            }
            res = mt5.order_send(req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                placed_tickets.append(int(res.order))
                logger.info(f"📌 Placed MT5 Pending {order_label} #{res.order} on {broker_sym} @ {target_entry} (Vol: {volume}, SL: {sl_price}, TP: {tp_val})")
            else:
                comm = getattr(res, 'comment', 'Unknown error') if res else 'No response'
                errors.append(f"{label} failed: {comm}")

        if placed_tickets:
            return {
                "success": True,
                "order_type": order_label,
                "tickets": placed_tickets,
                "price": target_entry,
                "sl": sl_price,
                "tp1": tp1_price
            }
        else:
            return {"success": False, "error": "; ".join(errors)}

    def sync_active_whatsapp_trades(self) -> Dict[str, Any]:
        """
        Synchronizes state['active_signal_trades'] and persistent setup memory with live open WhatsApp positions on MT5.
        If a position was closed on MT5 (via TP, SL, or manual close), it is removed from active state
        and marked as CLOSED in persistent setup memory.
        STRICT ISOLATION: Only touches WhatsApp Signal positions (Magic 777666 / WAPP).
        """
        state = self.load_state()
        active_trades = state.get("active_signal_trades", {})

        # Fetch live open WhatsApp positions directly from MT5
        live_positions = self.get_open_whatsapp_positions()
        live_tickets = {int(p["ticket"]) for p in live_positions if "ticket" in p}
        mt5_connected = self.executor._ensure_connection()

        changed = False

        if mt5_connected:
            # 1. Reconcile active_signal_trades with MT5
            for sym in list(active_trades.keys()):
                trade_info = active_trades[sym]

                # If trade is currently a pending limit/stop order
                if trade_info.get("is_pending"):
                    pending_wa = self.get_pending_whatsapp_orders(symbol=sym)
                    if not pending_wa:
                        # Order is no longer in pending orders! Check if it triggered into an active position
                        live_pos = self.get_open_whatsapp_positions(symbol=sym)
                        if live_pos:
                            logger.info(f"WhatsApp pending limit order for {sym} has triggered and is now active on MT5!")
                            trade_info["is_pending"] = False
                            trade_info["tickets"] = [{"ticket": int(p.get("ticket")), "label": p.get("comment")} for p in live_pos]
                            changed = True
                            if self.parser:
                                self.parser.mark_setup_status(sym, "CONFIRMED_ACTIVE", condition="Pending limit order triggered & filled on MT5")
                        else:
                            logger.info(f"WhatsApp pending limit order for {sym} was cancelled or expired. Purging from active state.")
                            active_trades.pop(sym, None)
                            changed = True
                    continue

                tickets = trade_info.get("tickets", [])
                int_tickets = []
                for t in tickets:
                    if isinstance(t, dict):
                        int_tickets.append(int(t.get("ticket", 0)))
                    else:
                        try:
                            int_tickets.append(int(t))
                        except Exception:
                            pass

                is_alive = any(t in live_tickets for t in int_tickets) if int_tickets else False
                if not is_alive and int_tickets:
                    logger.info(f"WhatsApp trade for {sym} (Tickets: {int_tickets}) has closed on MT5. Removing from active state.")
                    active_trades.pop(sym, None)
                    changed = True
                    if self.parser:
                        self.parser.mark_setup_status(sym, "CLOSED", condition="Active MT5 trade has closed")

            # 2. Synchronize Persistent Setups Cache (.whatsapp_pending_setups.json):
            # If any setup is marked CONFIRMED_ACTIVE, but MT5 has NO open WhatsApp positions for that symbol,
            # immediately transition the status to CLOSED so it never falsely lingers as active!
            if self.parser:
                cached_setups = self.parser.get_all_setups()
                for s_sym, s_data in cached_setups.items():
                    if isinstance(s_data, dict) and s_data.get("status") == "CONFIRMED_ACTIVE":
                        clean_ssym = s_sym.upper().replace("/", "").replace("_", "").replace("M", "").strip()
                        has_live = False
                        for p in live_positions:
                            p_sym = str(p.get("symbol", "")).upper().replace("/", "").replace("_", "").replace("M", "").strip()
                            if clean_ssym == p_sym or clean_ssym in p_sym or p_sym in clean_ssym:
                                has_live = True
                                break
                        if not has_live:
                            logger.info(f"Persistent setup for {s_sym} was CONFIRMED_ACTIVE, but no live MT5 WhatsApp positions exist. Updating status to CLOSED.")
                            self.parser.mark_setup_status(s_sym, "CLOSED", condition="Active MT5 trade has closed")

            # 3. Self-healing adoption: If there are live WhatsApp positions on MT5 not registered in active_signal_trades,
            # adopt them so active tracking is continuous and uninterrupted
            for p in live_positions:
                p_sym = str(p.get("symbol", "")).upper().replace("M", "")
                p_ticket = int(p.get("ticket", 0))
                found = False
                for a_sym, a_info in active_trades.items():
                    clean_asym = a_sym.upper().replace("/", "").replace("_", "").replace("M", "").strip()
                    if clean_asym == p_sym or clean_asym in p_sym or p_sym in clean_asym:
                        t_list = a_info.get("tickets", [])
                        t_int_list = [int(x.get("ticket") if isinstance(x, dict) else x) for x in t_list]
                        if p_ticket not in t_int_list:
                            t_list.append({"ticket": p_ticket, "label": p.get("comment", "MT5")})
                            a_info["tickets"] = t_list
                            changed = True
                        found = True
                        break
                if not found and p_ticket:
                    active_trades[p_sym] = {
                        "symbol": p.get("symbol"),
                        "direction": "BUY" if p.get("type", 0) == 0 else "SELL",
                        "entry": p.get("price_open"),
                        "sl": p.get("sl"),
                        "tp1": p.get("tp"),
                        "tickets": [{"ticket": p_ticket, "label": p.get("comment", "MT5")}],
                        "magic": p.get("magic", WHATSAPP_MAGIC_NUMBER),
                        "opened_at": datetime.now(timezone.utc).isoformat()
                    }
                    changed = True
                    if self.parser:
                        self.parser.mark_setup_status(p_sym, "CONFIRMED_ACTIVE", condition="Live trade entered & running on MT5")

        if changed:
            state["active_signal_trades"] = active_trades
            self.save_state(state)

        return active_trades

    def execute_parsed_signal(self, parsed: Dict[str, Any], raw_message: str, quoted_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes trade or management action on MT5 according to the parsed AI signal.
        Guarantees 100% strict isolation from Autonomous Trader trades.
        """
        # Multi-signal support: if parsed contains a list of signals (e.g. multi-pair or multi-action)
        signals_list = None
        if isinstance(parsed, list):
            signals_list = parsed
        elif isinstance(parsed, dict) and isinstance(parsed.get("signals"), list):
            signals_list = parsed.get("signals")

        if signals_list:
            results = []
            for sig in signals_list:
                res = self.execute_parsed_signal(sig, raw_message, quoted_text=quoted_text)
                results.append(res)
            return {
                "success": any(r.get("success") for r in results) if results else True,
                "status": "MULTI_SIGNAL_EXECUTED",
                "results": results
            }

        action = str(parsed.get("action", "IGNORE")).upper()
        symbol = str(parsed.get("symbol") or "").upper().replace("/", "").replace("_", "").strip()

        # 1. SETUP_SAVED action (no market entry yet, persistent levels stored)
        if action == "SETUP_SAVED":
            tps_summary = f"TP1: {parsed.get('tp1')}, TP2: {parsed.get('tp2')}"
            if parsed.get('tp3'):
                tps_summary += f", TP3: {parsed.get('tp3')}"
            cond_str = f" [Condition: {parsed.get('condition')}]" if parsed.get('condition') else ""
            self._append_log({
                "action": "SETUP_SAVED",
                "symbol": symbol,
                "status": "SAVED TO MEMORY",
                "details": f"Entry: {parsed.get('entry_price')}, SL: {parsed.get('stop_loss')}, {tps_summary}{cond_str} (Awaiting confirmation)",
                "raw_message": raw_message
            })
            return {"success": True, "status": "SETUP_SAVED"}

        # 1.4 ENTRY_TRIGGERED (Admin commanded entry; active trigger saved, awaiting setup card)
        if action == "ENTRY_TRIGGERED":
            dir_str = str(parsed.get("direction") or "TRADE").upper()
            details = parsed.get("explanation") or f"Admin commanded {dir_str} entry on {symbol}. Awaiting SL/TP setup card."
            self._append_log({
                "action": "ENTRY_TRIGGERED",
                "symbol": symbol or "-",
                "status": "AWAITING SL/TP",
                "details": details,
                "raw_message": raw_message
            })
            return {"success": True, "status": "ENTRY_TRIGGERED", "details": details}

        # 1.5 CANCEL_SETUP / INVALIDATE / DELETE
        if action in ["CANCEL_SETUP", "INVALIDATE", "DELETE"]:
            clean_s = symbol.upper().replace("/", "").replace("_", "").strip() if symbol else ""
            if self.parser and clean_s:
                self.parser.clear_entry_trigger(clean_s)
                self.parser.delete_setup(clean_s)

            # Cancel any active MT5 pending limit/stop orders for this symbol (or all if not specified)
            cancelled_tkts = self.cancel_pending_whatsapp_orders(symbol=clean_s if clean_s else None)

            # Atomic direct deletion from SETUPS_CACHE_FILE
            from src.engine.whatsapp_signal_parser import SETUPS_CACHE_FILE
            if os.path.exists(SETUPS_CACHE_FILE):
                try:
                    with open(SETUPS_CACHE_FILE, "r", encoding="utf-8") as f:
                        sc = json.load(f)
                    changed = False
                    for k in list(sc.keys()):
                        if clean_s and (clean_s in k or k in clean_s):
                            sc.pop(k, None)
                            changed = True
                        elif not clean_s or clean_s == "ALL":
                            sc.pop(k, None)
                            changed = True
                    if changed:
                        with open(SETUPS_CACHE_FILE, "w", encoding="utf-8") as f:
                            json.dump(sc, f, indent=2)
                except Exception as del_err:
                    logger.debug(f"Error purging setup from cache file: {del_err}")

            # Also clear from active_signal_trades if it was recorded as pending
            state = self.load_state()
            active_trades = state.get("active_signal_trades", {})
            changed_state = False
            for k in list(active_trades.keys()):
                if (clean_s and (clean_s in k or k in clean_s)) or not clean_s:
                    if active_trades[k].get("is_pending"):
                        active_trades.pop(k, None)
                        changed_state = True
            if changed_state:
                state["active_signal_trades"] = active_trades
                self.save_state(state)

            details = parsed.get("explanation") or f"Setup for {symbol} has been invalidated and removed from memory."
            if cancelled_tkts:
                details += f" (Cancelled MT5 pending limit orders: {cancelled_tkts})"
            self._append_log({
                "action": "CANCEL_SETUP",
                "symbol": symbol or "-",
                "status": "SETUP CANCELLED",
                "details": details,
                "raw_message": raw_message
            })
            return {"success": True, "status": "SETUP_CANCELLED", "details": details, "cancelled_tickets": cancelled_tkts}

        # 2. HOLD action (Advisory, commentary, hold positions)
        if action == "HOLD":
            expl = parsed.get("explanation", "Admin advised to hold positions / market advisory.")
            self._append_log({
                "action": "HOLD",
                "symbol": symbol or "ALL",
                "status": "HOLD POSITIONS",
                "details": expl,
                "raw_message": raw_message
            })
            return {"success": True, "status": "HOLD"}

        # 3. IGNORE / Noise
        if action == "IGNORE":
            expl = parsed.get("explanation", "Non-actionable message")
            trading_keywords = [
                "buy", "sell", "long", "short", "tp", "tp1", "tp2", "tp3", "sl",
                "entry", "gold", "xau", "btc", "eth", "forex", "crypto", "zone",
                "pip", "target", "close", "cut", "lot", "leverage", "trade", "signal"
            ]
            raw_low = (raw_message or "").lower()
            # Only append to user-facing activity log if message has trading keywords but was ignored/filtered
            if any(k in raw_low for k in trading_keywords):
                self._append_log({
                    "action": "IGNORE",
                    "symbol": symbol or "-",
                    "status": "IGNORED (Noise Filter)",
                    "details": expl,
                    "raw_message": raw_message
                })
            return {"success": True, "status": "IGNORED", "details": expl}

        # If blocked by safety gate for live market entry, log and exit
        if action == "BLOCKED" or not parsed.get("safety_gate_passed", True):
            reason = parsed.get("blocked_reason") or "Safety Gate Blocked: Missing SL/TP"
            self._append_log({
                "action": "BLOCKED",
                "symbol": symbol or "-",
                "status": "REJECTED (Missing SL/TP)",
                "details": reason,
                "raw_message": raw_message
            })
            return {"success": False, "status": "BLOCKED", "reason": reason}

        # Check MT5 connection
        if not self.executor._ensure_connection():
            msg = "MT5 terminal is not running or connected."
            self._append_log({
                "action": action,
                "symbol": symbol,
                "status": "MT5 ERROR",
                "details": msg,
                "raw_message": raw_message
            })
            return {"success": False, "status": "ERROR", "reason": msg}

        settings = self.load_settings()
        state = self.load_state()
        active_trades = state.get("active_signal_trades", {})

        # 4. ENTER MARKET ORDER (With Dedicated WhatsApp Magic Number & Comment Prefix)
        if action == "ENTER":
            # 4.0 Sync active trades with live MT5 state
            active_trades = self.sync_active_whatsapp_trades()

            max_active = int(settings.get("max_active_signal_trades", 5))
            if len(active_trades) >= max_active:
                reason = f"Max Active Signal Trades Cap Reached ({len(active_trades)}/{max_active}). Skipping new entry."
                self._append_log({
                    "action": "ENTER",
                    "symbol": symbol,
                    "status": "SKIPPED (Max Active Cap)",
                    "details": reason,
                    "raw_message": raw_message
                })
                return {"success": False, "status": "CAP_REACHED", "reason": reason}

            broker_sym = self.resolve_broker_symbol(symbol)
            direction = str(parsed.get("direction", "BUY")).upper()
            sl_price = float(parsed.get("stop_loss") or 0.0)
            tp1_price = float(parsed.get("tp1") or 0.0)
            tp2_price = float(parsed.get("tp2") or 0.0)
            tp3_price = float(parsed.get("tp3") or 0.0)
            tp4_price = float(parsed.get("tp4") or 0.0)
            tp5_price = float(parsed.get("tp5") or 0.0)
            target_entry = float(parsed.get("entry_price") or 0.0)
            is_screenshot_proof = bool(parsed.get("is_screenshot_proof", False))

            # If screenshot proof or missing SL/TP, recover SL/TP from cached setup
            if (sl_price <= 0 or tp1_price <= 0) and self.parser:
                cached_s = self.parser.get_cached_setup(symbol) or self.parser.get_latest_pending_setup()
                if cached_s:
                    if sl_price <= 0:
                        sl_price = float(cached_s.get("stop_loss") or 0.0)
                    if tp1_price <= 0:
                        tp1_price = float(cached_s.get("tp1") or 0.0)
                    if tp2_price <= 0:
                        tp2_price = float(cached_s.get("tp2") or 0.0)
                    if tp3_price <= 0:
                        tp3_price = float(cached_s.get("tp3") or 0.0)

            # HARD SAFETY GATE: Never place an order on MT5 without explicit, valid SL and TP1
            if sl_price <= 0 or tp1_price <= 0 or not parsed.get("safety_gate_passed", False):
                reason = "STRICT SAFETY GATE: Missing or zero Stop-Loss (SL) or Take-Profit (TP1). Execution blocked."
                self._append_log({
                    "action": "BLOCKED",
                    "symbol": symbol,
                    "status": "REJECTED (Missing SL/TP)",
                    "details": reason,
                    "raw_message": raw_message
                })
                logger.warning(f"BLOCKED MT5 ORDER: {symbol} has invalid SL ({sl_price}) or TP1 ({tp1_price}). Safety Gate active.")
                return {"success": False, "status": "BLOCKED", "reason": reason}

            # 4.1 STRICT GUARD: DUPLICATE ACTIVE SETUP SUPPRESSION (WHATSAPP TRADES ONLY)
            # If this symbol/setup already has an active WhatsApp trade running on MT5, NEVER re-enter until it closes!
            open_wa_positions = self.get_open_whatsapp_positions(symbol=symbol)
            has_active_trade = bool(open_wa_positions) or (symbol in active_trades and not active_trades[symbol].get("is_pending"))

            if has_active_trade:
                active_entry = active_trades.get(symbol, {})
                existing_dir = active_entry.get("direction")
                if not existing_dir and open_wa_positions:
                    pos_type = open_wa_positions[0].get("type", 0)
                    existing_dir = "BUY" if pos_type == 0 else "SELL"

                existing_sl = active_entry.get("sl")
                existing_tp1 = active_entry.get("tp1")

                # If admin sent MT5 screenshot proof showing they are in trade, and we are ALREADY in trade:
                if is_screenshot_proof:
                    details = f"Trade for {symbol} is ALREADY ACTIVE on MT5. Screenshot proof confirmed; no duplicate entry needed."
                    logger.info(f"ℹ️ {details}")
                    self._append_log({
                        "action": f"ENTER {direction}",
                        "symbol": broker_sym,
                        "status": "SKIPPED (Already In Market)",
                        "details": details,
                        "raw_message": raw_message
                    })
                    return {"success": True, "status": "ALREADY_ACTIVE_SKIPPED", "details": details}

                # Duplicate setup check: same trading pair and (same direction OR matching SL/TP levels)
                is_same_setup = (
                    (existing_dir and direction.upper() == existing_dir.upper())
                    or (existing_sl and abs(float(existing_sl) - sl_price) < 0.001)
                    or (existing_tp1 and abs(float(existing_tp1) - tp1_price) < 0.001)
                    or (not existing_dir and not existing_sl)
                )

                if is_same_setup:
                    active_tids = [p.get("ticket") for p in open_wa_positions] or active_entry.get("tickets", [])
                    reason = (
                        f"Duplicate active setup suppressed: WhatsApp trade for {symbol} ({existing_dir or direction}) "
                        f"is ALREADY ACTIVE on MT5 (Tickets: {active_tids}, SL: {existing_sl or sl_price}, TP1: {existing_tp1 or tp1_price}). "
                        f"Duplicate entry is strictly blocked until the active trade closes."
                    )
                    logger.info(f"🚫 {reason}")
                    self._append_log({
                        "action": f"ENTER {direction}",
                        "symbol": broker_sym,
                        "status": "SKIPPED (Active Setup Running)",
                        "details": reason,
                        "raw_message": raw_message
                    })
                    return {
                        "success": False,
                        "status": "DUPLICATE_ACTIVE_SETUP_SKIPPED",
                        "reason": reason
                    }

            # Get current live price
            import MetaTrader5 as mt5
            tick = mt5.symbol_info_tick(broker_sym)
            if not tick:
                reason = f"Cannot fetch tick for broker symbol '{broker_sym}'."
                self._append_log({
                    "action": "ENTER",
                    "symbol": broker_sym,
                    "status": "FAILED",
                    "details": reason,
                    "raw_message": raw_message
                })
                return {"success": False, "status": "FAILED", "reason": reason}

            current_market_price = tick.ask if direction == "BUY" else tick.bid

            # Proximity check:
            # If target entry is specified, calculate relative difference
            diff_pct = abs(current_market_price - target_entry) / target_entry if target_entry > 0 else 0.0

            # Proximity threshold: 0.15% (e.g. ~$4 on Gold, ~$100 on BTC, ~15 pips)
            # If price is close (<= 0.15%), or no entry price specified, or screenshot proof arrived:
            # Enter immediately at MARKET!
            should_enter_market = is_screenshot_proof or (target_entry <= 0) or (diff_pct <= 0.0015)

            cfg_lot = float(settings.get("batch_lot_size", 0.05))
            max_risk_cap = float(settings.get("max_dollar_risk", 50.0))

            if should_enter_market:
                # Cancel any old pending limit orders for this symbol first
                self.cancel_pending_whatsapp_orders(symbol=broker_sym)

                entry_price = current_market_price

                # Calculate Lot Size and Risk
                lot_sizing = self.executor.calculate_lot_and_risk(
                    broker_symbol=broker_sym,
                    entry_price=entry_price,
                    stop_loss_price=sl_price,
                    balance_usd=10000.0,
                    total_volume_lots=cfg_lot,
                    tp1_price=tp1_price,
                    tp2_price=tp2_price if tp2_price > 0 else None,
                    tp3_price=tp3_price if tp3_price > 0 else None
                )

                actual_risk = float(lot_sizing.get("actual_risk_usd", 0.0))
                lot_split = lot_sizing.get("lot_split", {})

                # Enforce Max Dollar Risk Cap
                if max_risk_cap > 0 and actual_risk > max_risk_cap:
                    total_lots = float(lot_sizing.get("total_lots", cfg_lot))
                    if total_lots > 0 and actual_risk > 0:
                        scale_factor = max_risk_cap / actual_risk
                        scaled_lot = max(0.01, round(int((total_lots * scale_factor) / 0.01) * 0.01, 2))
                        lot_sizing = self.executor.calculate_lot_and_risk(
                            broker_symbol=broker_sym,
                            entry_price=entry_price,
                            stop_loss_price=sl_price,
                            balance_usd=10000.0,
                            total_volume_lots=scaled_lot,
                            tp1_price=tp1_price,
                            tp2_price=tp2_price if tp2_price > 0 else None,
                            tp3_price=tp3_price if tp3_price > 0 else None
                        )
                        actual_risk = float(lot_sizing.get("actual_risk_usd", 0.0))
                        lot_split = lot_sizing.get("lot_split", {})

                if max_risk_cap > 0 and actual_risk > max_risk_cap:
                    reason = f"Risk ${actual_risk:.2f} exceeds Max Dollar Risk Cap (${max_risk_cap:.2f}). Skipped."
                    self._append_log({
                        "action": "ENTER",
                        "symbol": broker_sym,
                        "status": "SKIPPED (Risk Cap)",
                        "details": reason,
                        "raw_message": raw_message
                    })
                    return {"success": False, "status": "RISK_CAP_EXCEEDED", "reason": reason}

                # Submit Market Order with dedicated WhatsApp Magic Number & Comment Prefix
                trade_res = self.executor.execute_multi_target_trade(
                    broker_symbol=broker_sym,
                    action=direction,
                    sl_price=sl_price,
                    tp1_price=tp1_price,
                    tp2_price=tp2_price,
                    tp3_price=tp3_price,
                    lot_split=lot_split,
                    strategy_tag="WhatsApp_Signal",
                    custom_magic=WHATSAPP_MAGIC_NUMBER,
                    custom_comment_prefix=WHATSAPP_COMMENT_PREFIX
                )

                if trade_res.get("success"):
                    tickets = trade_res.get("tickets", [])
                    active_trades[symbol] = {
                        "symbol": symbol,
                        "broker_symbol": broker_sym,
                        "direction": direction,
                        "entry_price": entry_price,
                        "sl": sl_price,
                        "tp1": tp1_price,
                        "tp2": tp2_price,
                        "tp3": tp3_price,
                        "tp4": tp4_price,
                        "tp5": tp5_price,
                        "tickets": tickets,
                        "lot_split": lot_split,
                        "magic": WHATSAPP_MAGIC_NUMBER,
                        "is_pending": False,
                        "opened_at": datetime.now(timezone.utc).isoformat()
                    }
                    state["active_signal_trades"] = active_trades
                    self.save_state(state)

                    if self.parser:
                        self.parser.mark_setup_status(symbol, "CONFIRMED_ACTIVE", condition="Live trade entered & running on MT5")

                    trigger_src = "Screenshot Proof" if is_screenshot_proof else ("Live Price Near Entry" if target_entry > 0 else "Direct Signal")
                    details = f"Executed {direction} {broker_sym} @ {entry_price:.5f} ({trigger_src}) | SL: {sl_price} | TP1: {tp1_price} | Tickets: {tickets}"
                    self._append_log({
                        "action": f"ENTER {direction}",
                        "symbol": broker_sym,
                        "status": "EXECUTED",
                        "details": details,
                        "raw_message": raw_message
                    })
                    return {"success": True, "status": "EXECUTED", "details": details}
                else:
                    err = trade_res.get("error", "Order placement failed.")
                    if self.parser:
                        self.parser.mark_setup_status(symbol, "EXECUTION_FAILED", condition=f"Order rejected by MT5: {err}")
                    self._append_log({
                        "action": f"ENTER {direction}",
                        "symbol": broker_sym,
                        "status": "ORDER ERROR",
                        "details": err,
                        "raw_message": raw_message
                    })
                    return {"success": False, "status": "ORDER_FAILED", "error": err}

            else:
                # Market price is far from target entry price -> Place MT5 Pending Limit Order!
                existing_pending = self.get_pending_whatsapp_orders(symbol=symbol, broker_sym=broker_sym)
                if existing_pending:
                    existing_prices = [float(getattr(o, 'price_open', 0.0)) for o in existing_pending]
                    if any(abs(p - target_entry) < 0.001 for p in existing_prices):
                        reason = f"Pending limit order for {broker_sym} @ {target_entry} is ALREADY ACTIVE on MT5."
                        logger.info(f"📌 {reason}")
                        return {"success": True, "status": "PENDING_ALREADY_ACTIVE", "details": reason}
                    else:
                        # Cancel outdated pending order
                        self.cancel_pending_whatsapp_orders(symbol=broker_sym)

                # Calculate lot size at target entry price
                lot_sizing = self.executor.calculate_lot_and_risk(
                    broker_symbol=broker_sym,
                    entry_price=target_entry,
                    stop_loss_price=sl_price,
                    balance_usd=10000.0,
                    total_volume_lots=cfg_lot,
                    tp1_price=tp1_price,
                    tp2_price=tp2_price if tp2_price > 0 else None,
                    tp3_price=tp3_price if tp3_price > 0 else None
                )
                actual_risk = float(lot_sizing.get("actual_risk_usd", 0.0))
                lot_split = lot_sizing.get("lot_split", {})

                if max_risk_cap > 0 and actual_risk > max_risk_cap:
                    total_lots = float(lot_sizing.get("total_lots", cfg_lot))
                    if total_lots > 0 and actual_risk > 0:
                        scale_factor = max_risk_cap / actual_risk
                        scaled_lot = max(0.01, round(int((total_lots * scale_factor) / 0.01) * 0.01, 2))
                        lot_sizing = self.executor.calculate_lot_and_risk(
                            broker_symbol=broker_sym,
                            entry_price=target_entry,
                            stop_loss_price=sl_price,
                            balance_usd=10000.0,
                            total_volume_lots=scaled_lot,
                            tp1_price=tp1_price,
                            tp2_price=tp2_price if tp2_price > 0 else None,
                            tp3_price=tp3_price if tp3_price > 0 else None
                        )
                        lot_split = lot_sizing.get("lot_split", {})

                pending_res = self.place_pending_whatsapp_order(
                    broker_sym=broker_sym,
                    direction=direction,
                    target_entry=target_entry,
                    sl_price=sl_price,
                    tp1_price=tp1_price,
                    tp2_price=tp2_price,
                    tp3_price=tp3_price,
                    lot_split=lot_split
                )

                if pending_res.get("success"):
                    tickets = pending_res.get("tickets", [])
                    active_trades[symbol] = {
                        "symbol": symbol,
                        "broker_symbol": broker_sym,
                        "direction": direction,
                        "entry_price": target_entry,
                        "sl": sl_price,
                        "tp1": tp1_price,
                        "tp2": tp2_price,
                        "tp3": tp3_price,
                        "tp4": tp4_price,
                        "tp5": tp5_price,
                        "tickets": tickets,
                        "lot_split": lot_split,
                        "magic": WHATSAPP_MAGIC_NUMBER,
                        "is_pending": True,
                        "opened_at": datetime.now(timezone.utc).isoformat()
                    }
                    state["active_signal_trades"] = active_trades
                    self.save_state(state)

                    if self.parser:
                        self.parser.mark_setup_status(symbol, "PENDING_CONFIRMATION", condition=f"Placed MT5 Pending Limit @ {target_entry}")

                    details = (
                        f"Placed MT5 Pending {pending_res.get('order_type')} for {broker_sym} @ {target_entry} "
                        f"(Live: {current_market_price:.5f}, Dist: {diff_pct*100:.2f}%) | SL: {sl_price} | TP1: {tp1_price} | Tickets: {tickets}"
                    )
                    self._append_log({
                        "action": f"LIMIT {direction}",
                        "symbol": broker_sym,
                        "status": "PENDING ORDER PLACED",
                        "details": details,
                        "raw_message": raw_message
                    })
                    return {"success": True, "status": "PENDING_LIMIT_PLACED", "details": details}
                else:
                    err = pending_res.get("error", "Pending limit order placement failed.")
                    self._append_log({
                        "action": f"LIMIT {direction}",
                        "symbol": broker_sym,
                        "status": "PENDING ORDER ERROR",
                        "details": err,
                        "raw_message": raw_message
                    })
                    return {"success": False, "status": "PENDING_ORDER_FAILED", "error": err}

        # 5. CLOSE_ALL (STRICTLY closes ONLY WhatsApp positions, NEVER Autonomous trades)
        if action == "CLOSE_ALL":
            # Priority Fallback: If symbol was not explicitly extracted, but a quoted_text was passed
            # (e.g. admin replied to an older trade signal saying "Cut this trade"),
            # extract and match the symbol from quoted_text against open WhatsApp positions!
            if (not symbol or symbol in ["ALL", ""]) and quoted_text:
                q_upper = str(quoted_text).upper()
                live_wa_positions = self.get_open_whatsapp_positions()
                for p in live_wa_positions:
                    p_sym = str(p.get("symbol", "")).upper()
                    clean_p = p_sym.replace("M", "").replace("/", "").replace("_", "")
                    if clean_p in q_upper or p_sym in q_upper or (clean_p in ["XAUUSD", "GOLD"] and any(k in q_upper for k in ["GOLD", "XAU"])):
                        symbol = p_sym
                        logger.info(f"🎯 Correlated target symbol '{symbol}' from WhatsApp quoted reply: '{quoted_text[:50]}'")
                        break

            broker_sym = self.resolve_broker_symbol(symbol) if symbol else None
            target_positions = self._get_whatsapp_positions(symbol, broker_sym)

            # If symbol not specified (admin said unquoted "cut krdo yrr" / "cut kardo trade"):
            # User requirement: "sabse recent jo lagayi hogi na WhatsApp se trade wo wali cut karni hai, agar wo mention nahi kar raha."
            if (not symbol or symbol in ["ALL", ""]) and target_positions:
                sorted_pos = sorted(target_positions, key=lambda x: str(x.get("time", "")), reverse=True)
                most_recent_sym = sorted_pos[0].get("symbol")
                target_positions = [p for p in sorted_pos if p.get("symbol") == most_recent_sym]
                symbol = most_recent_sym

            closed_count = 0
            for pos in target_positions:
                res = self.executor.close_position(pos["ticket"])
                if res.get("success"):
                    closed_count += 1

            # Also cancel any pending limit orders for this symbol so they don't trigger later
            if symbol:
                self.cancel_pending_whatsapp_orders(symbol=symbol)

            # Clean from active_signal_trades
            if symbol and symbol in active_trades:
                del active_trades[symbol]
            elif not symbol:
                active_trades.clear()
            for k in list(active_trades.keys()):
                if symbol and (symbol in k or k in symbol):
                    active_trades.pop(k, None)
            state["active_signal_trades"] = active_trades
            self.save_state(state)

            # Clean from persistent setups cache
            from src.engine.whatsapp_signal_parser import SETUPS_CACHE_FILE
            if os.path.exists(SETUPS_CACHE_FILE):
                try:
                    with open(SETUPS_CACHE_FILE, "r", encoding="utf-8") as f:
                        sc = json.load(f)
                    for k in list(sc.keys()):
                        if (symbol and (symbol in k or k in symbol)) or not symbol:
                            sc.pop(k, None)
                    with open(SETUPS_CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(sc, f, indent=2)
                except Exception:
                    pass

            details = f"Closed {closed_count} WhatsApp signal positions for {symbol or 'ALL'}. Autonomous positions untouched."
            self._append_log({
                "action": "CLOSE_ALL",
                "symbol": symbol or "ALL",
                "status": "ALL BOOKED",
                "details": details,
                "raw_message": raw_message
            })
            return {"success": True, "status": "ALL_CLOSED", "details": details}

        # 6. PARTIAL_CLOSE (STRICTLY touches ONLY WhatsApp positions)
        if action == "PARTIAL_CLOSE":
            pct = float(parsed.get("volume_pct") or 50.0)
            target_tp = parsed.get("target_tp")
            move_be = parsed.get("move_to_be", False)

            # 1. Fallback symbol correlation from quoted_text if symbol is null
            if (not symbol or symbol in ["ALL", ""]) and quoted_text:
                q_upper = str(quoted_text).upper()
                live_wa_positions = self.get_open_whatsapp_positions()
                for p in live_wa_positions:
                    p_sym = str(p.get("symbol", "")).upper()
                    clean_p = p_sym.replace("M", "").replace("/", "").replace("_", "")
                    if clean_p in q_upper or p_sym in q_upper or (clean_p in ["XAUUSD", "GOLD"] and any(k in q_upper for k in ["GOLD", "XAU"])):
                        symbol = p_sym
                        logger.info(f"🎯 Correlated target symbol '{symbol}' for PARTIAL_CLOSE from quoted reply")
                        break

            broker_sym = self.resolve_broker_symbol(symbol) if symbol else None
            target_positions = self._get_whatsapp_positions(symbol, broker_sym)

            # 2. If symbol still not specified, target the single most recent WhatsApp trade
            if (not symbol or symbol in ["ALL", ""]) and target_positions:
                sorted_pos = sorted(target_positions, key=lambda x: str(x.get("time", "")), reverse=True)
                most_recent_sym = sorted_pos[0].get("symbol")
                target_positions = [p for p in sorted_pos if p.get("symbol") == most_recent_sym]
                symbol = most_recent_sym

            if not target_positions:
                details = f"No open WhatsApp positions found for {symbol or 'target'} to partially close."
                self._append_log({
                    "action": "PARTIAL_CLOSE",
                    "symbol": symbol or "-",
                    "status": "NO OPEN POSITIONS",
                    "details": details,
                    "raw_message": raw_message
                })
                return {"success": False, "status": "NO_POSITIONS", "details": details}

            total_open_vol = sum(float(p.get("volume", 0.0)) for p in target_positions)

            # Calculate target volume to close based on dynamic percentage
            # Enforce that if pct < 100%, at least min volume (0.01) remains running!
            raw_close_vol = round(total_open_vol * (pct / 100.0), 2)
            if pct < 100.0 and total_open_vol > 0.01:
                max_closable = round(total_open_vol - 0.01, 2)
                target_close_vol = min(raw_close_vol, max_closable)
            else:
                target_close_vol = raw_close_vol

            target_close_vol = max(0.01, target_close_vol)
            remaining_to_close = target_close_vol

            # Sort positions so TP1 closes first, then TP2, and TP3 runner is preserved
            def tp_sort_key(p):
                cmt = str(p.get("comment", "")).upper()
                if "_TP1" in cmt:
                    return 1
                if "_TP2" in cmt:
                    return 2
                if "_TP3" in cmt:
                    return 3
                return 4

            sorted_positions = sorted(target_positions, key=tp_sort_key)

            closed_details = []
            for pos in sorted_positions:
                if remaining_to_close <= 0.001:
                    break
                p_vol = float(pos.get("volume", 0.0))
                ticket = pos["ticket"]
                if p_vol <= remaining_to_close:
                    res = self.executor.close_position(ticket)
                    if res.get("success"):
                        closed_details.append(f"Ticket #{ticket} full ({p_vol} lots)")
                        remaining_to_close = round(remaining_to_close - p_vol, 2)
                else:
                    res = self.executor.close_position(ticket, volume=remaining_to_close)
                    if res.get("success"):
                        closed_details.append(f"Ticket #{ticket} partial ({remaining_to_close} lots)")
                        remaining_to_close = 0.0

            # If admin requested or auto_be is on, move remaining runner tickets to Breakeven
            be_details = []
            if move_be or settings.get("auto_be_on_tp1", True):
                remaining_positions = self._get_whatsapp_positions(symbol)
                for rp in remaining_positions:
                    r_tkt = rp["ticket"]
                    be_res = self.executor.move_to_breakeven(r_tkt)
                    if be_res.get("success"):
                        be_details.append(f"#{r_tkt}")

            be_msg = f" | Runners moved to BE: {be_details}" if be_details else ""
            details = f"Booked {pct}% WhatsApp profits on {symbol} (Closed: {target_close_vol:.2f}/{total_open_vol:.2f} lots). Actions: {closed_details}{be_msg}"
            self._append_log({
                "action": "PARTIAL_CLOSE",
                "symbol": symbol or "ACTIVE",
                "status": f"BOOKED {pct}%",
                "details": details,
                "raw_message": raw_message
            })
            return {"success": True, "status": "PARTIAL_CLOSED", "details": details, "volume_closed": target_close_vol}

        # 7. MODIFY_SL (Early cut level / SL tightening / Breakeven)
        if action == "MODIFY_SL":
            broker_sym = self.resolve_broker_symbol(symbol) if symbol else None
            target_positions = self._get_whatsapp_positions(symbol, broker_sym)
            target_sl = parsed.get("stop_loss")
            modified_count = 0

            import MetaTrader5 as mt5
            tick = mt5.symbol_info_tick(broker_sym) if broker_sym else None
            curr_ask = tick.ask if tick else 0.0
            curr_bid = tick.bid if tick else 0.0

            for pos in target_positions:
                ticket = pos["ticket"]
                pos_type = pos.get("type", "BUY")

                # If target_sl is specified (e.g. "Cut the trade if it reach 4159"):
                if target_sl and float(target_sl) > 0:
                    sl_val = float(target_sl)
                    # Check emergency price breach: if market already crossed emergency cut price, close immediately
                    if pos_type == "SELL" and curr_ask >= sl_val > 0:
                        self.executor.close_position(ticket)
                        modified_count += 1
                        continue
                    elif pos_type == "BUY" and curr_bid <= sl_val > 0:
                        self.executor.close_position(ticket)
                        modified_count += 1
                        continue

                    # Otherwise modify MT5 Stop-Loss to target_sl
                    res = self.executor.move_to_breakeven(ticket, target_sl=sl_val)
                    if res.get("success"):
                        modified_count += 1
                else:
                    # Move to Breakeven
                    res = self.executor.move_to_breakeven(ticket)
                    if res.get("success"):
                        modified_count += 1

            details = f"Updated Stop-Loss / Early Cut ({target_sl or 'BE'}) for {modified_count} WhatsApp positions of {symbol or 'ALL'}."
            self._append_log({
                "action": "MODIFY_SL",
                "symbol": symbol or "ALL",
                "status": f"SL TO {target_sl or 'BE'}",
                "details": details,
                "raw_message": raw_message
            })
            return {"success": True, "status": "SL_MODIFIED", "details": details}

        return {"success": True, "status": "PROCESSED"}
