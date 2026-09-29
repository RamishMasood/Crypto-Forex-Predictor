"""
WhatsApp Signal MT5 Trade Executor.
Executes and manages trades derived from WhatsApp Signal Channel messages
with strict risk capping, lot size control, and position tracking.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from src.engine.mt5_executor import MT5TradeExecutor
from src.data.forex_feeds import MT5ExnessProvider

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
    """

    def __init__(self):
        self.executor = MT5TradeExecutor()
        self.exness_provider = MT5ExnessProvider()
        self.settings = self.load_settings()
        self.state = self.load_state()

    def load_settings(self) -> Dict[str, Any]:
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    res = DEFAULT_SETTINGS.copy()
                    res.update(data)
                    return res
            except Exception as e:
                logger.error(f"Error loading {SETTINGS_FILE}: {e}")
        return DEFAULT_SETTINGS.copy()

    def save_settings(self, new_settings: Dict[str, Any]):
        try:
            self.settings = new_settings
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(new_settings, f, indent=2)
            logger.info("WhatsApp Signal settings saved successfully.")
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

    def execute_parsed_signal(self, parsed: Dict[str, Any], raw_message: str) -> Dict[str, Any]:
        """
        Executes trade or management action on MT5 according to the parsed AI signal.
        """
        action = str(parsed.get("action", "IGNORE")).upper()
        symbol = str(parsed.get("symbol") or "").upper().replace("/", "").replace("_", "").strip()

        # If blocked by safety gate, log and exit
        if action == "BLOCKED" or not parsed.get("safety_gate_passed", True):
            reason = parsed.get("blocked_reason", "Safety Gate Blocked: Missing SL/TP")
            self._append_log({
                "action": "BLOCKED",
                "symbol": symbol or "-",
                "status": "REJECTED (Missing SL/TP)",
                "details": reason,
                "raw_message": raw_message
            })
            return {"success": False, "status": "BLOCKED", "reason": reason}

        # 1. SETUP_SAVED action (no market entry yet, just saved levels)
        if action == "SETUP_SAVED":
            self._append_log({
                "action": "SETUP_SAVED",
                "symbol": symbol,
                "status": "SAVED TO MEMORY",
                "details": f"Entry: {parsed.get('entry_price')}, SL: {parsed.get('stop_loss')}, TP1: {parsed.get('tp1')}, TP2: {parsed.get('tp2')}",
                "raw_message": raw_message
            })
            return {"success": True, "status": "SETUP_SAVED"}

        # 2. HOLD action
        if action == "HOLD":
            self._append_log({
                "action": "HOLD",
                "symbol": symbol or "ALL",
                "status": "HOLD POSITIONS",
                "details": parsed.get("explanation", "Admin advised to hold positions."),
                "raw_message": raw_message
            })
            return {"success": True, "status": "HOLD"}

        # 3. IGNORE / Noise
        if action == "IGNORE":
            return {"success": True, "status": "IGNORED"}

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

        # 4. ENTER MARKET ORDER
        if action == "ENTER":
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
            sl_price = float(parsed.get("stop_loss", 0.0))
            tp1_price = float(parsed.get("tp1", 0.0))
            tp2_price = float(parsed.get("tp2") or 0.0)
            tp3_price = float(parsed.get("tp3") or 0.0)

            # Get current price
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

            entry_price = tick.ask if direction == "BUY" else tick.bid

            # Calculate Lot Size and Risk
            cfg_lot = float(settings.get("batch_lot_size", 0.05))
            max_risk_cap = float(settings.get("max_dollar_risk", 50.0))

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
                # Try to scale down lots
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
                        tp2_price=tp2_price if tp2_price > 0 else None
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

    def execute_parsed_signal(self, parsed: Dict[str, Any], raw_message: str) -> Dict[str, Any]:
        """
        Executes trade or management action on MT5 according to the parsed AI signal.
        Guarantees 100% strict isolation from Autonomous Trader trades.
        """
        action = str(parsed.get("action", "IGNORE")).upper()
        symbol = str(parsed.get("symbol") or "").upper().replace("/", "").replace("_", "").strip()

        # If blocked by safety gate, log and exit
        if action == "BLOCKED" or not parsed.get("safety_gate_passed", True):
            reason = parsed.get("blocked_reason", "Safety Gate Blocked: Missing SL/TP")
            self._append_log({
                "action": "BLOCKED",
                "symbol": symbol or "-",
                "status": "REJECTED (Missing SL/TP)",
                "details": reason,
                "raw_message": raw_message
            })
            return {"success": False, "status": "BLOCKED", "reason": reason}

        # 1. SETUP_SAVED action (no market entry yet, just saved levels)
        if action == "SETUP_SAVED":
            self._append_log({
                "action": "SETUP_SAVED",
                "symbol": symbol,
                "status": "SAVED TO MEMORY",
                "details": f"Entry: {parsed.get('entry_price')}, SL: {parsed.get('stop_loss')}, TP1: {parsed.get('tp1')}, TP2: {parsed.get('tp2')}",
                "raw_message": raw_message
            })
            return {"success": True, "status": "SETUP_SAVED"}

        # 2. HOLD action
        if action == "HOLD":
            self._append_log({
                "action": "HOLD",
                "symbol": symbol or "ALL",
                "status": "HOLD POSITIONS",
                "details": parsed.get("explanation", "Admin advised to hold positions."),
                "raw_message": raw_message
            })
            return {"success": True, "status": "HOLD"}

        # 3. IGNORE / Noise
        if action == "IGNORE":
            return {"success": True, "status": "IGNORED"}

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
            sl_price = float(parsed.get("stop_loss", 0.0))
            tp1_price = float(parsed.get("tp1", 0.0))
            tp2_price = float(parsed.get("tp2") or 0.0)
            tp3_price = float(parsed.get("tp3") or 0.0)

            # Get current price
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

            entry_price = tick.ask if direction == "BUY" else tick.bid

            # Calculate Lot Size and Risk
            cfg_lot = float(settings.get("batch_lot_size", 0.05))
            max_risk_cap = float(settings.get("max_dollar_risk", 50.0))

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
                        tp2_price=tp2_price if tp2_price > 0 else None
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

            # Submit Order with dedicated WhatsApp Magic Number & Comment Prefix
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
                    "tickets": tickets,
                    "lot_split": lot_split,
                    "magic": WHATSAPP_MAGIC_NUMBER,
                    "opened_at": datetime.now(timezone.utc).isoformat()
                }
                state["active_signal_trades"] = active_trades
                self.save_state(state)

                details = f"Executed {direction} {broker_sym} @ {entry_price:.5f} | SL: {sl_price} | TP1: {tp1_price} | Tickets: {tickets}"
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
                self._append_log({
                    "action": f"ENTER {direction}",
                    "symbol": broker_sym,
                    "status": "ORDER ERROR",
                    "details": err,
                    "raw_message": raw_message
                })
                return {"success": False, "status": "ORDER_FAILED", "error": err}

        # 5. CLOSE_ALL (STRICTLY closes ONLY WhatsApp positions, NEVER Autonomous trades)
        if action == "CLOSE_ALL":
            broker_sym = self.resolve_broker_symbol(symbol)
            target_positions = self._get_whatsapp_positions(symbol, broker_sym)

            closed_count = 0
            for pos in target_positions:
                res = self.executor.close_position(pos["ticket"])
                if res.get("success"):
                    closed_count += 1

            if symbol in active_trades:
                del active_trades[symbol]
                state["active_signal_trades"] = active_trades
                self.save_state(state)

            details = f"Closed {closed_count} WhatsApp signal positions for {symbol} ({broker_sym}). Autonomous positions untouched."
            self._append_log({
                "action": "CLOSE_ALL",
                "symbol": symbol,
                "status": "ALL BOOKED",
                "details": details,
                "raw_message": raw_message
            })
            return {"success": True, "status": "ALL_CLOSED", "details": details}

        # 6. PARTIAL_CLOSE (STRICTLY touches ONLY WhatsApp positions)
        if action == "PARTIAL_CLOSE":
            pct = float(parsed.get("volume_pct") or 50.0)
            broker_sym = self.resolve_broker_symbol(symbol)
            target_positions = self._get_whatsapp_positions(symbol, broker_sym)

            closed_tickets = []
            for pos in target_positions:
                res = self.executor.close_position(pos["ticket"])
                if res.get("success"):
                    closed_tickets.append(pos["ticket"])

            details = f"Booked {pct}% WhatsApp profits on {symbol or 'positions'}. Closed tickets: {closed_tickets}"
            self._append_log({
                "action": "PARTIAL_CLOSE",
                "symbol": symbol or "ACTIVE",
                "status": f"BOOKED {pct}%",
                "details": details,
                "raw_message": raw_message
            })
            return {"success": True, "status": "PARTIAL_CLOSED", "details": details}

        # 7. MODIFY_SL (STRICTLY modifies ONLY WhatsApp positions)
        if action == "MODIFY_SL":
            broker_sym = self.resolve_broker_symbol(symbol)
            target_positions = self._get_whatsapp_positions(symbol, broker_sym)
            be_count = 0
            for pos in target_positions:
                res = self.executor.move_to_breakeven(pos["ticket"])
                if res.get("success"):
                    be_count += 1

            details = f"Shifted Stop-Loss to Breakeven for {be_count} WhatsApp positions of {symbol}."
            self._append_log({
                "action": "MODIFY_SL",
                "symbol": symbol,
                "status": "SL TO BE",
                "details": details,
                "raw_message": raw_message
            })
            return {"success": True, "status": "SL_MODIFIED", "details": details}

        return {"success": True, "status": "PROCESSED"}
