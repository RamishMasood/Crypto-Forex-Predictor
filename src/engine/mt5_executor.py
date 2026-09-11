"""
MetaTrader 5 (Exness) Automated Trade Execution & Multi-Target Position Manager.
Provides institutional-grade order routing:
  - Exact lot size calculation based on balance, stop distance, contract size, and broker tick rules.
  - Multi-target order splitting (TP1, TP2, TP3) with native broker server take-profits.
  - Automated Breakeven (BE) shifting upon TP1 fulfillment.
  - Live open position tracking, PnL monitoring, and history reporting.
"""

import os
import time
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

class MT5TradeExecutor:
    """
    Handles live order execution, risk-based lot sizing, multi-target scaling,
    and position tracking directly on MetaTrader 5 (Exness).
    """
    MAGIC_NUMBER = 999888  # Unique identifier for Quant Terminal trades

    def __init__(self):
        self._ensure_connection()

    def _ensure_connection(self) -> bool:
        try:
            import MetaTrader5 as mt5
            term_info = mt5.terminal_info()
            if term_info is not None and getattr(term_info, 'connected', False):
                return True
            exness_path = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
            default_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
            path = exness_path if os.path.exists(exness_path) else default_path
            if os.path.exists(path):
                ok = mt5.initialize(path=path)
            else:
                ok = mt5.initialize()
            return bool(ok)
        except Exception:
            return False

    def get_symbol_trade_specs(self, broker_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch contract size, volume limits, point value, digits, and filling modes.
        """
        if not self._ensure_connection():
            return None
        try:
            import MetaTrader5 as mt5
            s_info = mt5.symbol_info(broker_symbol)
            if s_info is None:
                mt5.symbol_select(broker_symbol, True)
                s_info = mt5.symbol_info(broker_symbol)
                if s_info is None:
                    return None

            raw_v_min = float(s_info.volume_min) if s_info.volume_min is not None else 0.01
            raw_v_max = float(s_info.volume_max) if s_info.volume_max is not None else 100.0
            raw_v_step = float(s_info.volume_step) if s_info.volume_step is not None else 0.01

            # MT5 returns 1e-08 or 0.0 for untradeable/uninitialized symbols
            vol_min = raw_v_min if raw_v_min >= 0.01 else 0.01
            vol_step = raw_v_step if raw_v_step >= 0.01 else 0.01
            vol_max = raw_v_max if raw_v_max >= vol_min else max(100.0, vol_min)

            return {
                'symbol': broker_symbol,
                'digits': int(s_info.digits),
                'point': float(s_info.point),
                'contract_size': float(s_info.trade_contract_size if s_info.trade_contract_size > 0 else 100000.0),
                'volume_min': vol_min,
                'volume_max': vol_max,
                'volume_step': vol_step,
                'trade_tick_value': float(s_info.trade_tick_value if s_info.trade_tick_value > 0 else 1.0),
                'trade_tick_size': float(s_info.trade_tick_size if s_info.trade_tick_size > 0 else s_info.point),
                'spread': int(s_info.spread),
                'filling_mode': int(s_info.filling_mode),
                'currency': getattr(s_info, 'currency_profit', 'USD')
            }
        except Exception:
            return None

    def calculate_lot_and_risk(
        self,
        broker_symbol: str,
        entry_price: float,
        stop_loss_price: float,
        balance_usd: float,
        risk_pct: float = 1.5,
        tp1_pct: float = 50.0,
        tp2_pct: float = 30.0,
        tp3_pct: float = 20.0,
        tp1_price: Optional[float] = None,
        tp2_price: Optional[float] = None,
        tp3_price: Optional[float] = None,
        custom_lots: Optional[Dict[str, float]] = None,
        total_volume_lots: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates exact volume (lots), risk in dollars, risk in %, margin required,
        splits volume across TP1, TP2, and TP3 according to broker constraints (or direct custom lots / total volume override),
        and computes expected reward in dollars ($) for each target.
        """
        specs = self.get_symbol_trade_specs(broker_symbol)
        if not specs:
            # Fallback when MT5 IPC is disconnected or terminal is offline
            is_gold = 'XAU' in broker_symbol.upper() or 'GOLD' in broker_symbol.upper()
            is_cent = broker_symbol.lower().endswith('c')
            
            if is_gold:
                contract_size = 1.0 if is_cent else 100.0
                point_val = 0.01
                digits_val = 2
            else:
                contract_size = 1000.0 if is_cent else 100000.0
                point_val = 0.0001
                digits_val = 5

            specs = {
                'contract_size': contract_size,
                'volume_min': 0.01,
                'volume_step': 0.01,
                'volume_max': 100.0,
                'point': point_val,
                'digits': digits_val
            }

        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0 or entry_price <= 0:
            return {'error': 'Invalid entry or stop loss price'}

        target_risk_usd = balance_usd * (risk_pct / 100.0)
        contract_size = specs['contract_size']
        vol_min = float(specs.get('volume_min', 0.01))
        if vol_min < 0.01:
            vol_min = 0.01
        vol_step = float(specs.get('volume_step', 0.01))
        if vol_step < 0.01:
            vol_step = 0.01
        vol_max = float(specs.get('volume_max', 100.0))
        if vol_max < vol_min:
            vol_max = max(100.0, vol_min)

        # Risk per 1.0 standard lot = sl_distance * contract_size
        risk_per_one_lot = sl_distance * contract_size
        if risk_per_one_lot <= 0:
            return {'error': 'Cannot calculate risk per lot'}

        # Minimum required balance to afford this stop loss at minimum lot
        min_lot_risk_usd = vol_min * risk_per_one_lot

        if custom_lots and any(custom_lots.values()):
            # Direct manual lots specified by user for each TP
            l1 = max(0.0, round(custom_lots.get('tp1_lots', 0.0), 2))
            l2 = max(0.0, round(custom_lots.get('tp2_lots', 0.0), 2))
            l3 = max(0.0, round(custom_lots.get('tp3_lots', 0.0), 2))
            
            # Clamp to volume step
            lot1 = round(round(l1 / vol_step) * vol_step, 4)
            lot2 = round(round(l2 / vol_step) * vol_step, 4)
            lot3 = round(round(l3 / vol_step) * vol_step, 4)

            total_lots = round(lot1 + lot2 + lot3, 4)
            if total_lots < vol_min:
                total_lots = vol_min
                lot1 = vol_min
                lot2 = 0.0
                lot3 = 0.0

            actual_risk_usd = total_lots * risk_per_one_lot
            actual_risk_pct = (actual_risk_usd / balance_usd * 100.0) if balance_usd > 0 else 0.0

            tp1_pct = round((lot1 / total_lots * 100.0), 1) if total_lots > 0 else 0.0
            tp2_pct = round((lot2 / total_lots * 100.0), 1) if total_lots > 0 else 0.0
            tp3_pct = round((lot3 / total_lots * 100.0), 1) if total_lots > 0 else 0.0
        else:
            if total_volume_lots is not None and total_volume_lots > 0:
                steps = round(total_volume_lots / vol_step)
                total_lots = max(vol_min, min(vol_max, steps * vol_step))
                total_lots = round(total_lots, 4)
            else:
                raw_lots = target_risk_usd / risk_per_one_lot
                steps = round(raw_lots / vol_step)
                total_lots = max(vol_min, min(vol_max, steps * vol_step))
                total_lots = round(total_lots, 4)

            # Recalculate actual risk with rounded lots
            actual_risk_usd = total_lots * risk_per_one_lot
            actual_risk_pct = (actual_risk_usd / balance_usd * 100.0) if balance_usd > 0 else risk_pct

            # Split across TP1, TP2, TP3
            norm_sum = tp1_pct + tp2_pct + tp3_pct
            if norm_sum <= 0:
                tp1_pct, tp2_pct, tp3_pct = 50.0, 30.0, 20.0
                norm_sum = 100.0

            p1 = tp1_pct / norm_sum
            p2 = tp2_pct / norm_sum
            p3 = tp3_pct / norm_sum

            # To split into multiple child orders, each child order MUST be >= vol_min!
            if total_lots >= round(3 * vol_min, 4):
                # 3 child orders possible
                avail = round(total_lots - 3 * vol_min, 4)
                avail_steps = int(round(avail / vol_step))
                s1 = int(round(avail_steps * p1))
                s2 = int(round(avail_steps * p2))
                s3 = max(0, avail_steps - s1 - s2)
                lot1 = round(vol_min + s1 * vol_step, 4)
                lot2 = round(vol_min + s2 * vol_step, 4)
                lot3 = round(vol_min + s3 * vol_step, 4)
            elif total_lots >= round(2 * vol_min, 4):
                # 2 child orders possible
                avail = round(total_lots - 2 * vol_min, 4)
                avail_steps = int(round(avail / vol_step))
                denom = p1 + p2 if (p1 + p2) > 0 else 1.0
                s1 = int(round(avail_steps * (p1 / denom)))
                s2 = max(0, avail_steps - s1)
                lot1 = round(vol_min + s1 * vol_step, 4)
                lot2 = round(vol_min + s2 * vol_step, 4)
                lot3 = 0.0
            else:
                # Only 1 child order possible (total_lots < 2 * vol_min)
                lot1 = round(total_lots, 4)
                lot2 = 0.0
                lot3 = 0.0

        # Compute dollar reward ($) for each TP level
        tp1_dist = abs(tp1_price - entry_price) if tp1_price is not None else 0.0
        tp2_dist = abs(tp2_price - entry_price) if tp2_price is not None else 0.0
        tp3_dist = abs(tp3_price - entry_price) if tp3_price is not None else 0.0

        tp1_reward_usd = round(lot1 * tp1_dist * contract_size, 2)
        tp2_reward_usd = round(lot2 * tp2_dist * contract_size, 2)
        tp3_reward_usd = round(lot3 * tp3_dist * contract_size, 2)
        total_reward_usd = round(tp1_reward_usd + tp2_reward_usd + tp3_reward_usd, 2)

        return {
            'symbol': broker_symbol,
            'balance_usd': balance_usd,
            'target_risk_pct': risk_pct,
            'target_risk_usd': round(target_risk_usd, 2),
            'actual_risk_usd': round(actual_risk_usd, 2),
            'actual_risk_pct': round(actual_risk_pct, 2),
            'total_lots': total_lots,
            'min_lot_risk_usd': round(min_lot_risk_usd, 2),
            'lot_split': {
                'tp1_lots': lot1,
                'tp2_lots': lot2,
                'tp3_lots': lot3,
                'tp1_pct': tp1_pct,
                'tp2_pct': tp2_pct,
                'tp3_pct': tp3_pct,
                'tp1_reward_usd': tp1_reward_usd,
                'tp2_reward_usd': tp2_reward_usd,
                'tp3_reward_usd': tp3_reward_usd,
                'total_reward_usd': total_reward_usd
            },
            'tp1_reward_usd': tp1_reward_usd,
            'tp2_reward_usd': tp2_reward_usd,
            'tp3_reward_usd': tp3_reward_usd,
            'total_reward_usd': total_reward_usd,
            'contract_size': contract_size,
            'volume_min': vol_min,
            'sl_distance': sl_distance,
            'sl_distance_pct': round((sl_distance / entry_price) * 100.0, 3)
        }

    def execute_multi_target_trade(
        self,
        broker_symbol: str,
        action: str,  # 'BUY' or 'SELL'
        sl_price: float,
        tp1_price: float,
        tp2_price: float,
        tp3_price: float,
        lot_split: Dict[str, float],
        deviation_points: int = 20
    ) -> Dict[str, Any]:
        """
        Executes multi-target orders on Exness MT5:
          - Submits child orders for each non-zero TP lot.
          - Configures exact SL and TP directly with the broker.
        """
        if not self._ensure_connection():
            return {'success': False, 'error': 'MetaTrader 5 terminal not connected'}

        try:
            import MetaTrader5 as mt5

            term_info = mt5.terminal_info()
            if term_info and not term_info.trade_allowed:
                return {
                    'success': False,
                    'error': 'Algo/AutoTrading is disabled in your MetaTrader 5 terminal. Please click the "Algo Trading" (AutoTrading) button on your MT5 top toolbar or press Ctrl+E / Tools -> Options -> Expert Advisors -> check "Allow Algo Trading". (Code: 10027)'
                }

            specs = self.get_symbol_trade_specs(broker_symbol)
            if not specs:
                return {'success': False, 'error': f'Symbol specs unavailable for {broker_symbol}'}

            digits = specs['digits']
            order_type = mt5.ORDER_TYPE_BUY if 'BUY' in action.upper() else mt5.ORDER_TYPE_SELL

            tick = mt5.symbol_info_tick(broker_symbol)
            if tick is None:
                return {'success': False, 'error': f'Cannot get live tick for {broker_symbol}'}

            sl = round(float(sl_price), digits)
            tp1 = round(float(tp1_price), digits)
            tp2 = round(float(tp2_price), digits)
            tp3 = round(float(tp3_price), digits)

            filling_mode = specs.get('filling_mode', 3)
            type_filling = mt5.ORDER_FILLING_IOC if (filling_mode & 2) else mt5.ORDER_FILLING_FOK

            batch_id = int(time.time()) % 1000000  # Unique 6-digit trade batch ID
            orders_to_place = [
                ('TP1', lot_split.get('tp1_lots', 0.0), tp1),
                ('TP2', lot_split.get('tp2_lots', 0.0), tp2),
                ('TP3', lot_split.get('tp3_lots', 0.0), tp3),
            ]

            placed_tickets = []
            errors = []
            vol_min = float(specs.get('volume_min', 0.01))

            for label, volume, tp_target in orders_to_place:
                if volume <= 0:
                    continue
                if volume < vol_min:
                    errors.append(f"{label} (lots: {volume:.2f}) is below broker minimum ({vol_min:.2f}) for {broker_symbol}")
                    continue

                fresh_tick = mt5.symbol_info_tick(broker_symbol) or tick
                entry_p = fresh_tick.ask if order_type == mt5.ORDER_TYPE_BUY else fresh_tick.bid

                request = {
                    'action': mt5.TRADE_ACTION_DEAL,
                    'symbol': broker_symbol,
                    'volume': float(volume),
                    'type': order_type,
                    'price': round(float(entry_p), digits),
                    'sl': sl,
                    'tp': tp_target,
                    'deviation': deviation_points,
                    'magic': self.MAGIC_NUMBER,
                    'comment': f'QS_{batch_id}_{label}',
                    'type_time': mt5.ORDER_TIME_GTC,
                    'type_filling': type_filling,
                }

                result = mt5.order_send(request)
                if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                    ret_code = getattr(result, 'retcode', -1)
                    comment = getattr(result, 'comment', 'Order send failed')
                    errors.append(f"{label} (lots: {volume}) failed: {comment} (Code: {ret_code})")
                else:
                    placed_tickets.append({
                        'label': label,
                        'ticket': int(result.order),
                        'volume': float(volume),
                        'price': float(result.price),
                        'sl': sl,
                        'tp': tp_target
                    })

            if placed_tickets:
                return {
                    'success': True,
                    'batch_id': batch_id,
                    'broker_symbol': broker_symbol,
                    'symbol': broker_symbol,
                    'action': action,
                    'orders_placed': len(placed_tickets),
                    'tickets': placed_tickets,
                    'errors': errors if errors else None
                }
            else:
                return {
                    'success': False,
                    'symbol': broker_symbol,
                    'error': "; ".join(errors) if errors else "No orders could be executed."
                }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_open_positions(self, broker_symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch all open positions on Exness MT5 with live PnL and details.
        """
        if not self._ensure_connection():
            return []

        try:
            import MetaTrader5 as mt5
            positions = mt5.positions_get(symbol=broker_symbol) if broker_symbol else mt5.positions_get()
            if positions is None:
                return []

            results = []
            for p in positions:
                pos_type = 'BUY' if p.type == 0 else 'SELL'
                open_price = float(p.price_open)
                curr_price = float(p.price_current)
                profit_usd = float(p.profit)
                volume = float(p.volume)
                sl = float(p.sl)
                tp = float(p.tp)

                ret_pct = 0.0
                if open_price > 0:
                    if pos_type == 'BUY':
                        ret_pct = ((curr_price - open_price) / open_price) * 100.0
                    else:
                        ret_pct = ((open_price - curr_price) / open_price) * 100.0

                results.append({
                    'ticket': int(p.ticket),
                    'symbol': p.symbol,
                    'type': pos_type,
                    'volume': volume,
                    'price_open': open_price,
                    'price_current': curr_price,
                    'sl': sl,
                    'tp': tp,
                    'profit': round(profit_usd, 2),
                    'return_pct': round(ret_pct, 2),
                    'comment': p.comment,
                    'magic': int(p.magic),
                    'time': datetime.fromtimestamp(p.time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                })

            return results
        except Exception:
            return []

    def close_position(self, ticket: int) -> Dict[str, Any]:
        """
        Closes an open position by ticket number immediately at market.
        """
        if not self._ensure_connection():
            return {'success': False, 'error': 'MT5 terminal not connected'}

        try:
            import MetaTrader5 as mt5
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return {'success': False, 'error': f'Position {ticket} not found'}

            pos = positions[0]
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                return {'success': False, 'error': f'Cannot get tick for {pos.symbol}'}

            price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
            specs = self.get_symbol_trade_specs(pos.symbol) or {}
            filling_mode = specs.get('filling_mode', 3)
            type_filling = mt5.ORDER_FILLING_IOC if (filling_mode & 2) else mt5.ORDER_FILLING_FOK

            request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'position': ticket,
                'symbol': pos.symbol,
                'volume': float(pos.volume),
                'type': close_type,
                'price': price,
                'deviation': 20,
                'magic': self.MAGIC_NUMBER,
                'comment': 'QuantSniper_Close',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': type_filling
            }

            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                return {'success': True, 'ticket': ticket, 'close_price': result.price}
            else:
                comment = getattr(result, 'comment', 'Close failed')
                retcode = getattr(result, 'retcode', -1)
                return {'success': False, 'error': f"{comment} (Code: {retcode})"}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def move_to_breakeven(self, ticket: int, spread_buffer_points: int = 5, target_sl: Optional[float] = None) -> Dict[str, Any]:
        """
        Shifts the Stop-Loss of a position to its institutional Breakeven Mark (+ buffer) or explicit target_sl.
        """
        if not self._ensure_connection():
            return {'success': False, 'error': 'MT5 terminal not connected'}

        try:
            import MetaTrader5 as mt5
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return {'success': False, 'error': f'Position {ticket} not found'}

            pos = positions[0]
            specs = self.get_symbol_trade_specs(pos.symbol)
            if not specs:
                return {'success': False, 'error': 'Symbol specs unavailable'}

            point = specs['point']
            digits = specs['digits']
            open_p = float(pos.price_open)

            # Check if explicit target_sl provided or if batch comment has stored institutional BE
            resolved_be = target_sl
            if resolved_be is None or resolved_be <= 0:
                pos_cmt = str(pos.comment or '')
                if 'QS_' in pos_cmt:
                    parts = pos_cmt.split('_')
                    if len(parts) >= 2:
                        batch_id = parts[1]
                        try:
                            state_file = Path(".autonomous_trader_state.json")
                            if state_file.exists():
                                with open(state_file, 'r', encoding='utf-8') as f:
                                    st_data = json.load(f)
                                b_info = st_data.get('open_batches', {}).get(str(batch_id), {})
                                if b_info.get('breakeven_sl'):
                                    resolved_be = float(b_info['breakeven_sl'])
                        except Exception:
                            pass

            if resolved_be is not None and resolved_be > 0:
                new_sl = round(resolved_be, digits)
            else:
                buffer_val = spread_buffer_points * point
                if pos.type == mt5.ORDER_TYPE_BUY:
                    new_sl = round(open_p + buffer_val, digits)
                else:
                    new_sl = round(open_p - buffer_val, digits)

            request = {
                'action': mt5.TRADE_ACTION_SLTP,
                'position': ticket,
                'symbol': pos.symbol,
                'sl': new_sl,
                'tp': float(pos.tp)
            }

            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                return {'success': True, 'ticket': ticket, 'new_sl': new_sl}
            else:
                comment = getattr(result, 'comment', 'BE modify failed')
                retcode = getattr(result, 'retcode', -1)
                return {'success': False, 'error': f"{comment} (Code: {retcode})"}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def check_and_apply_auto_breakeven(self, broker_symbol: Optional[str] = None, batch_breakeven_sl_map: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """
        Auto-Breakeven Monitor:
        Finds open Quant Terminal child orders (magic == 999888).
        Triggers Breakeven if:
          1. Any TP1 child deal has closed in profit (TP1 hit confirmation in broker history), OR
          2. Open position is in profit (return_pct >= 0.08% or price reached TP1).
        Automatically modifies remaining open positions to the exact Institutional Breakeven Mark!
        """
        if not self._ensure_connection():
            return []

        import MetaTrader5 as mt5

        # Auto-load batch breakeven SL map if not explicitly passed
        if batch_breakeven_sl_map is None:
            try:
                state_file = Path(".autonomous_trader_state.json")
                if state_file.exists():
                    with open(state_file, 'r', encoding='utf-8') as f:
                        st_data = json.load(f)
                    batch_breakeven_sl_map = {
                        str(bid): float(binfo['breakeven_sl'])
                        for bid, binfo in st_data.get('open_batches', {}).items()
                        if binfo.get('breakeven_sl')
                    }
            except Exception:
                batch_breakeven_sl_map = {}

        # Find all closed TP1 deals in recent history (past 24h) and record their batch_ids / symbols
        closed_tp1_batches = set()
        closed_tp1_symbols = set()
        try:
            now_utc = datetime.now(timezone.utc)
            deals = mt5.history_deals_get(now_utc - timedelta(hours=24), now_utc)
            if deals:
                for d in deals:
                    if d.profit > 0 and d.entry == 1:
                        cmt = str(d.comment)
                        deal_sym = getattr(d, 'symbol', '')
                        if 'QS_' in cmt:
                            # format QS_<batch_id>_<TP>
                            parts = cmt.split('_')
                            if len(parts) >= 3 and parts[2].startswith('TP1'):
                                closed_tp1_batches.add(parts[1])
                                closed_tp1_symbols.add(deal_sym)
                        elif 'tp' in cmt.lower() or d.magic == self.MAGIC_NUMBER:
                            closed_tp1_symbols.add(deal_sym)
        except Exception:
            pass

        open_pos = self.get_open_positions(broker_symbol)
        quant_orders = [p for p in open_pos if p['magic'] == self.MAGIC_NUMBER]
        results = []

        for pos in quant_orders:
            open_p = pos['price_open']
            curr_p = pos['price_current']
            pos_type = pos['type']
            current_sl = pos['sl']
            pos_sym = pos['symbol']
            pos_cmt = pos.get('comment', '')

            is_profitable = (curr_p > open_p) if pos_type == 'BUY' else (curr_p < open_p)
            sl_at_be = (current_sl >= open_p) if pos_type == 'BUY' else (current_sl <= open_p and current_sl > 0)

            # Check if THIS specific order's batch had its TP1 hit, OR fallback to same symbol profit
            pos_batch = None
            if 'QS_' in pos_cmt:
                parts = pos_cmt.split('_')
                if len(parts) >= 2:
                    pos_batch = parts[1]

            batch_tp1_hit = (pos_batch is not None and pos_batch in closed_tp1_batches)
            symbol_tp1_hit = (pos_sym in closed_tp1_symbols and is_profitable and pos['return_pct'] >= 0.05)
            high_profit_hit = (is_profitable and pos['return_pct'] >= 0.15)

            should_be = is_profitable and (batch_tp1_hit or symbol_tp1_hit or high_profit_hit)

            if should_be and not sl_at_be:
                target_be_sl = None
                if batch_breakeven_sl_map and pos_batch and str(pos_batch) in batch_breakeven_sl_map:
                    target_be_sl = batch_breakeven_sl_map[str(pos_batch)]

                res = self.move_to_breakeven(pos['ticket'], target_sl=target_be_sl)
                if res.get('success'):
                    results.append({
                        'ticket': pos['ticket'],
                        'status': 'MOVED_TO_BREAKEVEN',
                        'new_sl': res['new_sl']
                    })

        return results

    def get_trade_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieves closed trades history from Exness MT5.
        """
        if not self._ensure_connection():
            return []

        try:
            import MetaTrader5 as mt5
            from_date = datetime.now() - timedelta(days=days)
            to_date = datetime.now() + timedelta(days=1)
            deals = mt5.history_deals_get(from_date, to_date)
            if deals is None or len(deals) == 0:
                return []

            results = []
            for d in reversed(deals):
                if d.entry == 1:
                    deal_type = 'SELL' if d.type == 1 else 'BUY'
                    profit = float(d.profit)
                    results.append({
                        'deal_id': int(d.ticket),
                        'order_id': int(d.order),
                        'symbol': d.symbol,
                        'type': deal_type,
                        'volume': float(d.volume),
                        'price': float(d.price),
                        'profit': round(profit, 2),
                        'commission': round(float(d.commission), 2),
                        'swap': round(float(d.swap), 2),
                        'comment': d.comment,
                        'time': datetime.fromtimestamp(d.time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                    })
            return results
        except Exception:
            return []
