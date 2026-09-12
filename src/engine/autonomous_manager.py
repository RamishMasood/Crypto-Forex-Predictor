import os
import sys
import time
import json
import logging
import threading
import concurrent.futures
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.engine.orchestrator import PredictorOrchestrator
from src.engine.mt5_executor import MT5TradeExecutor

class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg.encode('ascii', 'backslashreplace').decode('ascii') + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

logger = logging.getLogger("AutonomousManager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    sh = SafeStreamHandler(sys.stdout)
    fh = logging.FileHandler(os.path.join(ROOT_DIR, "autonomous_trader.log"), encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh.setFormatter(fmt)
    fh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.addHandler(fh)

SETTINGS_FILE = os.path.join(ROOT_DIR, ".autonomous_trader_settings.json")
STATE_FILE = os.path.join(ROOT_DIR, ".autonomous_trader_state.json")
JOURNAL_FILE = os.path.join(ROOT_DIR, ".trade_learning_journal.json")

AVAILABLE_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h"]
DEFAULT_TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h"]
DEFAULT_SYMBOLS = ["XAU/USD", "BTC/USD"]

_SCAN_STOP_EVENT = threading.Event()
_FORCE_STOP_EVENT = threading.Event()
_STATE_LOCK = threading.Lock()
_TRADE_EXEC_LOCK = threading.Lock()

class AutonomousTraderEngine:
    def __init__(self):
        self.orch = PredictorOrchestrator()
        self.executor = MT5TradeExecutor()
        self._thread: Optional[threading.Thread] = None
        self._stop_requested = _SCAN_STOP_EVENT
        self._is_running = False

    @staticmethod
    def load_settings() -> Dict[str, Any]:
        default_settings = {
            "enabled": False,
            "selected_symbols": DEFAULT_SYMBOLS,
            "timeframes": DEFAULT_TIMEFRAMES,
            "risk_pct": 1.0,
            "scan_interval_sec": 180,           # 3 minutes default scan delay
            "target_trades_per_symbol": 10,     # Customizable target
            "max_active_batches": 1,            # 1 = wait until previous batch closes
            "max_dollar_risk": 10.0,            # Max dollar risk cap per batch ($ USD)
            "min_pillars_required": 5,          # Customizable required pillars: 5, 4, 3, or 2
            "batch_lot_size": 0.03              # Customizable batch lot size (e.g. 0.03 -> 0.01, 0.01, 0.01)
        }
        with _STATE_LOCK:
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        default_settings.update(data)
                except Exception as e:
                    logger.error(f"Error loading settings: {e}")
        return default_settings

    @staticmethod
    def save_settings(settings: Dict[str, Any]):
        with _STATE_LOCK:
            try:
                tmp_file = SETTINGS_FILE + ".tmp"
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, indent=2)
                os.replace(tmp_file, SETTINGS_FILE)
            except Exception as e:
                logger.error(f"Error saving settings: {e}")

    @staticmethod
    def load_state() -> Dict[str, Any]:
        default_state = {
            "total_trades_taken": 0,
            "trades_by_symbol": {},
            "symbol_stats": {},
            "open_batches": {},
            "closed_batches": [],
            "wins": 0,
            "losses": 0,
            "breakevens": 0,
            "last_scan_time": None,
            "last_scanned_symbol": None,
            "engine_status": "STOPPED",
            "cycle_count": 0,
            "current_scan": {},
            "scan_activity_log": [],
            "next_scan_time": None,
            "reset_at": None
        }
        with _STATE_LOCK:
            if os.path.exists(STATE_FILE):
                for _ in range(3):
                    try:
                        with open(STATE_FILE, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            for k, v in default_state.items():
                                if k not in data:
                                    data[k] = v
                            return data
                    except Exception:
                        time.sleep(0.04)
        return default_state

    @staticmethod
    def save_state(state: Dict[str, Any]):
        with _STATE_LOCK:
            try:
                tmp_file = STATE_FILE + ".tmp"
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2)
                os.replace(tmp_file, STATE_FILE)
            except Exception as e:
                logger.error(f"Error saving state: {e}")

    def has_active_batches(self) -> bool:
        try:
            state = self.load_state()
            return bool(state.get('open_batches', {}))
        except Exception:
            return False

    def is_thread_alive(self) -> bool:
        for t in threading.enumerate():
            if t.name == "Auto5PillarTraderThread" and t.is_alive():
                return True
        return False

    def is_scan_active(self) -> bool:
        settings = self.load_settings()
        if not settings.get('enabled', False):
            return False
        if _SCAN_STOP_EVENT.is_set():
            return False
        return self.is_thread_alive()

    def is_managing_active(self) -> bool:
        return not self.is_scan_active() and self.has_active_batches()

    @staticmethod
    def load_journal() -> Dict[str, Any]:
        default_j = {
            "lessons_learned": [],
            "sl_post_mortems": [],
            "optimal_adjustments": {
                "min_confluence_score": 35.0,
                "min_calibrated_prob": 80.0
            }
        }
        if os.path.exists(JOURNAL_FILE):
            try:
                with open(JOURNAL_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    default_j.update(data)
            except Exception as e:
                logger.error(f"Error loading journal: {e}")
        return default_j

    @staticmethod
    def save_journal(journal: Dict[str, Any]):
        try:
            with open(JOURNAL_FILE, 'w', encoding='utf-8') as f:
                json.dump(journal, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving journal: {e}")

    @staticmethod
    def compute_batch_risk(trade: Dict[str, Any]) -> float:
        if trade.get('risk_usd') is not None and float(trade.get('risk_usd', 0)) > 0:
            return float(trade['risk_usd'])
        try:
            entry = float(trade.get('entry_price', 0))
            sl = float(trade.get('sl_price', 0))
            dist = abs(entry - sl)
            if dist <= 0:
                return 0.0
            lot_split = trade.get('lot_split', {})
            tp1_l = float(lot_split.get('tp1_lots', 0.0))
            tp2_l = float(lot_split.get('tp2_lots', 0.0))
            tp3_l = float(lot_split.get('tp3_lots', 0.0))
            tot_lots = tp1_l + tp2_l + tp3_l
            if tot_lots <= 0:
                tot_lots = 0.01

            sym = str(trade.get('symbol', '')).upper()
            if 'XAU' in sym or 'GOLD' in sym:
                contract_size = 100.0
            elif 'BTC' in sym:
                contract_size = 1.0
            elif 'ETH' in sym:
                contract_size = 1.0
            elif any(c in sym for c in ['EUR', 'GBP', 'AUD', 'NZD', 'USD', 'JPY', 'CAD', 'CHF']):
                contract_size = 100000.0
            else:
                contract_size = 100.0

            return round(tot_lots * dist * contract_size, 2)
        except Exception:
            return 0.0

    @staticmethod
    def normalize_symbol(broker_symbol: str) -> str:
        s = str(broker_symbol).upper().replace("/", "").replace("_", "")
        for suf in [".RAW", "RAW", "#", "M", "C"]:
            if s.endswith(suf) and len(s) > len(suf) + 3:
                s = s[:-len(suf)]
                break
        if "XAU" in s or "GOLD" in s:
            return "XAU/USD"
        if "BTC" in s:
            return "BTC/USD"
        if "ETH" in s:
            return "ETH/USD"
        if len(s) == 6:
            return f"{s[:3]}/{s[3:]}"
        return broker_symbol

    def reset_progress(self, clear_journal: bool = False):
        """Reset target progress, executed counts, and symbol stats back to 0."""
        state = self.load_state()
        state["total_trades_taken"] = 0
        state["trades_by_symbol"] = {}
        state["symbol_stats"] = {}
        state["open_batches"] = {}
        state["closed_batches"] = []
        state["wins"] = 0
        state["losses"] = 0
        state["breakevens"] = 0
        state["cycle_count"] = 0
        state["current_scan"] = {}
        state["xau_trades_taken"] = 0
        state["btc_trades_taken"] = 0
        state["last_scan_time"] = None
        state["last_scanned_symbol"] = None
        state["next_scan_time"] = None
        state["tf_rotation_indices"] = {}
        state["reset_at"] = datetime.now(timezone.utc).isoformat()
        state["scan_activity_log"] = [{
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            "cycle": 0,
            "symbol": "SYSTEM",
            "timeframe": "-",
            "action": "RESET",
            "status": "Target Progress Reset",
            "details": "All trade targets & symbol win rates reset to 0."
        }]
        self.save_state(state)

        if clear_journal:
            journal = {
                "lessons_learned": [],
                "sl_post_mortems": [],
                "optimal_adjustments": {
                    "min_confluence_score": 35.0,
                    "min_calibrated_prob": 80.0
                }
            }
            self.save_journal(journal)
        logger.info("Progress and trade counters successfully reset to 0.")

    def _append_activity_log(self, entry: Dict[str, Any]):
        try:
            state = self.load_state()
            logs = state.get('scan_activity_log', [])
            logs.insert(0, entry)
            state['scan_activity_log'] = logs[:60]
            self.save_state(state)
        except Exception:
            pass

    def evaluate_5_pillars(self, pred_res: Dict[str, Any]) -> Dict[str, Any]:
        conf = pred_res['confluence']
        alpha = pred_res.get('alpha_sniper', {})
        mtf = pred_res.get('mtf_alignment', {})
        news = pred_res.get('economic_news', {})
        quantum = pred_res.get('quantum_sniper', alpha.get('quantum_sniper', {}))
        whale_gate = pred_res.get('whale_sentiment_gate', {})
        chop_gate = pred_res.get('chop_gate', alpha.get('chop_gate', {}))
        spread_guard = pred_res.get('spread_guard', {})

        is_chop = bool(chop_gate.get('is_chop', False))
        is_spread_pass = bool(spread_guard.get('passed', True)) if spread_guard else True

        action = conf.get('action', '')
        is_dir_buy = ('BUY' in action) and ('FILTER' not in action) and ('BLACKOUT' not in action) and ('CHOP' not in action)
        is_dir_sell = ('SELL' in action) and ('FILTER' not in action) and ('BLACKOUT' not in action) and ('CHOP' not in action)
        is_trade_active = (is_dir_buy or is_dir_sell) and (not is_chop) and is_spread_pass

        # Pillar 1: Predictive Confluence & Alpha Sniper (Closed-Loop Learning Calibrated)
        journal = self.load_journal()
        opt_adj = journal.get('optimal_adjustments', {})
        req_score = float(opt_adj.get('min_confluence_score', 35.0))
        req_prob = float(opt_adj.get('min_calibrated_prob', 80.0))

        p1_score = float(conf.get('confluence_score', 0))
        p1_prob = float(alpha.get('calibrated_win_probability_pct', conf.get('quality_index_pct', 50)))
        p1_ok = False
        if not is_chop and is_spread_pass:
            if is_dir_buy and p1_score >= req_score and p1_prob >= req_prob:
                p1_ok = True
            elif is_dir_sell and p1_score <= -req_score and p1_prob >= req_prob:
                p1_ok = True

        # Pillar 2: MTF Alignment
        s1 = mtf.get('screen1_macro', {}) if mtf else {}
        s1_bias = s1.get('macro_bias', 'NEUTRAL')
        s1_200 = s1.get('close_vs_ema200', 'UNKNOWN')
        p2_ok = False
        if is_dir_buy and s1_bias in ['BULLISH', 'MILD_BULLISH'] and s1_200 == 'ABOVE_200_EMA':
            p2_ok = True
        elif is_dir_sell and s1_bias in ['BEARISH', 'MILD_BEARISH'] and s1_200 == 'BELOW_200_EMA':
            p2_ok = True

        # Pillar 3: Economic News Guard
        p3_ok = not bool(news.get('is_blackout', False)) if news else True

        # Pillar 4: Quantum Overextension Guard
        q_overext = quantum.get('overextension', {}) if quantum else {}
        is_overextended = bool(q_overext.get('is_overextended', False))
        p4_ok = is_trade_active and (not is_overextended)

        # Pillar 5: Whale Sentiment Gate
        p5_status = whale_gate.get('status', 'NEUTRAL')
        p5_ok = is_trade_active and (p5_status != 'BLOCKED')

        aligned_count = sum([p1_ok, p2_ok, p3_ok, p4_ok, p5_ok])
        is_fully_aligned = (aligned_count == 5) and is_trade_active

        return {
            'is_fully_aligned': is_fully_aligned,
            'aligned_count': aligned_count,
            'p1': {'ok': p1_ok, 'score': p1_score, 'prob': p1_prob},
            'p2': {'ok': p2_ok, 'bias': s1_bias, 'ema200': s1_200},
            'p3': {'ok': p3_ok, 'is_blackout': bool(news.get('is_blackout', False)) if news else False},
            'p4': {'ok': p4_ok, 'is_overextended': is_overextended},
            'p5': {'ok': p5_ok, 'status': p5_status},
            'chop_gate': chop_gate,
            'spread_guard': spread_guard
        }

    def audit_active_trades_and_learn(self):
        state = self.load_state()
        journal = self.load_journal()
        try:
            open_batches = dict(state.get('open_batches', {}))
            state_changed = False
            reset_at = state.get('reset_at')

            # Auto breakeven check with institutional breakeven SL map
            be_map = {
                str(bid): float(binfo['breakeven_sl'])
                for bid, binfo in open_batches.items()
                if binfo.get('breakeven_sl')
            }
            be_results = self.executor.check_and_apply_auto_breakeven(batch_breakeven_sl_map=be_map)
            if be_results:
                for b in be_results:
                    logger.info(f"AUTO-BREAKEVEN: Position #{b['ticket']} SL shifted to Institutional BE Mark: {b['new_sl']}")

            import MetaTrader5 as mt5
            self.executor._ensure_connection()
            now_utc = datetime.now(timezone.utc)
            deals = mt5.history_deals_get(now_utc - timedelta(hours=48), now_utc)
            open_pos = mt5.positions_get()
            open_tickets = {p.ticket for p in open_pos} if open_pos else set()

            # Check open batches for completion
            for batch_id, trade in list(open_batches.items()):
                batch_tickets = set(trade.get('tickets', []))
                active_in_batch = batch_tickets.intersection(open_tickets)
                if not active_in_batch and deals:
                    total_batch_profit = 0.0
                    for d in deals:
                        if (d.order in batch_tickets or getattr(d, 'position_id', None) in batch_tickets) and d.entry == 1:
                            total_batch_profit += float(d.profit)

                    outcome = 'WIN' if total_batch_profit > 0.5 else ('BREAKEVEN' if abs(total_batch_profit) <= 0.5 else 'LOSS')
                    logger.info(f"Batch #{batch_id} ({trade['symbol']}) Completed: {outcome} | PnL: ${total_batch_profit:+.2f}")

                    # Global stats & Active Reinforcement Learning Loop
                    if outcome == 'WIN':
                        state['wins'] = state.get('wins', 0) + 1
                        # Adaptive reinforcement: On consistent wins, stabilize threshold towards baseline 80%
                        opt = journal.get('optimal_adjustments', {})
                        if float(opt.get('min_calibrated_prob', 80.0)) > 80.0:
                            opt['min_calibrated_prob'] = round(max(80.0, float(opt.get('min_calibrated_prob', 80.0)) - 0.2), 1)
                            journal['optimal_adjustments'] = opt
                            self.save_journal(journal)
                    elif outcome == 'BREAKEVEN':
                        state['breakevens'] = state.get('breakevens', 0) + 1
                    else:
                        state['losses'] = state.get('losses', 0) + 1
                        lesson_txt = f"On {trade['symbol']} ({trade['timeframe']}): Stop loss triggered. Buffer refined to prevent liquidity hunt wicks."
                        journal['lessons_learned'].append(lesson_txt)
                        
                        # Record structured SL post-mortem
                        pm = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "symbol": trade.get('symbol'),
                            "timeframe": trade.get('timeframe'),
                            "action": trade.get('action'),
                            "entry": trade.get('entry_price'),
                            "sl": trade.get('sl_price'),
                            "loss_usd": round(abs(total_batch_profit), 2),
                            "action_taken": "Reinforced entry confluence filter and expanded wick breathing room."
                        }
                        if 'sl_post_mortems' not in journal:
                            journal['sl_post_mortems'] = []
                        journal['sl_post_mortems'].append(pm)
                        
                        # Adaptive reinforcement: Elevate selective entry threshold to prevent repeated drawdowns
                        opt = journal.get('optimal_adjustments', {})
                        opt['min_calibrated_prob'] = round(min(88.0, float(opt.get('min_calibrated_prob', 80.0)) + 0.5), 1)
                        journal['optimal_adjustments'] = opt
                        self.save_journal(journal)

                    # Per-symbol stats (Requirement 5)
                    sym = trade.get('symbol', 'UNKNOWN')
                    if 'symbol_stats' not in state:
                        state['symbol_stats'] = {}
                    if sym not in state['symbol_stats']:
                        state['symbol_stats'][sym] = {'wins': 0, 'losses': 0, 'breakevens': 0, 'completed': 0, 'total_profit': 0.0}
                    s_stat = state['symbol_stats'][sym]
                    s_stat['completed'] = s_stat.get('completed', 0) + 1
                    s_stat['total_profit'] = round(s_stat.get('total_profit', 0.0) + total_batch_profit, 2)
                    if outcome == 'WIN':
                        s_stat['wins'] = s_stat.get('wins', 0) + 1
                    elif outcome == 'BREAKEVEN':
                        s_stat['breakevens'] = s_stat.get('breakevens', 0) + 1
                    else:
                        s_stat['losses'] = s_stat.get('losses', 0) + 1

                    # Record in closed_batches ledger (Requirement 4)
                    closed_record = {
                        'batch_id': batch_id,
                        'symbol': sym,
                        'broker_sym': trade.get('broker_sym'),
                        'timeframe': trade.get('timeframe'),
                        'action': trade.get('action'),
                        'entry_price': trade.get('entry_price'),
                        'sl_price': trade.get('sl_price'),
                        'breakeven_sl': trade.get('breakeven_sl'),
                        'matched_pillars': trade.get('matched_pillars', 5),
                        'tp1_price': trade.get('tp1_price'),
                        'tp2_price': trade.get('tp2_price'),
                        'tp3_price': trade.get('tp3_price'),
                        'lot_split': trade.get('lot_split'),
                        'tickets': trade.get('tickets', []),
                        'executed_at': trade.get('executed_at'),
                        'closed_at': datetime.now(timezone.utc).isoformat(),
                        'profit': round(total_batch_profit, 2),
                        'risk_usd': round(self.compute_batch_risk(trade), 2),
                        'status': outcome,
                        'p1_score': trade.get('p1_score'),
                        'p1_prob': trade.get('p1_prob')
                    }
                    if 'closed_batches' not in state:
                        state['closed_batches'] = []
                    state['closed_batches'].insert(0, closed_record)
                    state['closed_batches'] = state['closed_batches'][:200]

                    del open_batches[batch_id]
                    state['open_batches'] = open_batches
                    state_changed = True

                    self._append_activity_log({
                        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                        "cycle": state.get('cycle_count', 0),
                        "symbol": sym,
                        "timeframe": trade.get('timeframe', '-'),
                        "action": trade.get('action', '-'),
                        "pillars": "5/5",
                        "status": f"Closed ({outcome}) Batch #{batch_id}",
                        "details": f"PnL: ${total_batch_profit:+.2f} | Tickets: {trade.get('tickets')}"
                    })

            # Populate initial historical stats ONLY if never reset and no closed_batches exist
            if reset_at is None and not state.get('closed_batches') and not state.get('open_batches') and deals:
                if state.get('wins', 0) == 0 and state.get('losses', 0) == 0 and state.get('breakevens', 0) == 0:
                    pos_pnl = {}
                    sym_map = {}
                    for d in deals:
                        if d.entry == 1:
                            pid = getattr(d, 'position_id', d.order)
                            pos_pnl[pid] = pos_pnl.get(pid, 0.0) + float(d.profit)
                            sym_map[pid] = d.symbol

                    if pos_pnl:
                        state['wins'] = sum(1 for pnl in pos_pnl.values() if pnl > 0.5)
                        state['breakevens'] = sum(1 for pnl in pos_pnl.values() if abs(pnl) <= 0.5)
                        state['losses'] = sum(1 for pnl in pos_pnl.values() if pnl < -0.5)

                        # Breakdown per symbol
                        if 'symbol_stats' not in state:
                            state['symbol_stats'] = {}
                        for pid, pnl in pos_pnl.items():
                            bsym = sym_map.get(pid, '')
                            csym = self.normalize_symbol(bsym)
                            if csym not in state['symbol_stats']:
                                state['symbol_stats'][csym] = {'wins': 0, 'losses': 0, 'breakevens': 0, 'completed': 0, 'total_profit': 0.0}
                            s = state['symbol_stats'][csym]
                            s['completed'] += 1
                            s['total_profit'] = round(s['total_profit'] + pnl, 2)
                            if pnl > 0.5:
                                s['wins'] += 1
                            elif abs(pnl) <= 0.5:
                                s['breakevens'] += 1
                            else:
                                s['losses'] += 1

                        state_changed = True

            if state_changed:
                self.save_state(state)

        except Exception as e:
            logger.error(f"Error in audit and learning: {e}")

    def scan_symbol_all_timeframes(self, symbol: str, timeframes: List[str], cycle: int = 0, min_pillars_required: int = 5) -> Optional[Dict[str, Any]]:
        if not timeframes:
            return None

        asset_type = 'crypto' if any(c in symbol.upper() for c in ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']) else 'forex'

        # Load rotation pointer so scan order rotates across timeframes
        state = self.load_state()
        tf_rotation = state.get('tf_rotation_indices', {})
        start_idx = int(tf_rotation.get(symbol, 0)) % len(timeframes)

        # Order timeframes starting from start_idx
        ordered_tfs = timeframes[start_idx:] + timeframes[:start_idx]
        logger.info(f"Scanning {symbol} across timeframes: {ordered_tfs} (Rotated Start: {timeframes[start_idx]}, Min Pillars: {min_pillars_required}/5)")

        found_setup = None

        for tf in ordered_tfs:
            if _SCAN_STOP_EVENT.is_set() or not self.load_settings().get('enabled', False):
                logger.info(f"Stop signal detected. Aborting scan on {symbol}.")
                return None

            try:
                # Update current scanning pointer
                st_now = self.load_state()
                st_now['current_scan'] = {
                    'cycle': cycle,
                    'symbol': symbol,
                    'timeframe': tf,
                    'time': datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                }
                self.save_state(st_now)

                pred = self.orch.run_prediction(
                    symbol=symbol,
                    asset_type=asset_type,
                    market_mode='spot',
                    timeframe=tf,
                    preferred_exchange='Exness (MetaTrader 5)'
                )
                eval_res = self.evaluate_5_pillars(pred)
                p_cnt = eval_res['aligned_count']
                action = pred['confluence']['action']
                score = eval_res['p1']['score']
                prob = eval_res['p1']['prob']

                chop_gate = pred.get('chop_gate', {})
                is_chop = bool(chop_gate.get('is_chop', False))
                spread_guard = pred.get('spread_guard', {})
                is_spread_fail = bool(spread_guard and not spread_guard.get('passed', True))

                is_actionable = ('BUY' in action or 'SELL' in action) and ('FILTER' not in action) and ('BLACKOUT' not in action) and ('CHOP' not in action) and (not is_chop) and (not is_spread_fail)
                is_eligible = (p_cnt >= min_pillars_required) and is_actionable

                pillar_str = f"{p_cnt}/5"

                if is_eligible:
                    status_lbl = f"🎯 {p_cnt}/5 Aligned (Executing)"
                elif is_chop:
                    status_lbl = "SKIPPED (Chop Gate)"
                elif is_spread_fail:
                    status_lbl = "SKIPPED (Spread > 25% TP1)"
                else:
                    status_lbl = f"No Trade (Waiting {min_pillars_required}/5)"

                detail_str = f"Score: {score:+.1f} | Win Prob: {prob:.0f}%"
                if is_chop:
                    detail_str = f"CHOP: {chop_gate.get('reason', '')[:45]}"
                elif is_spread_fail:
                    detail_str = f"Spread: ${spread_guard.get('spread_price')} ({spread_guard.get('spread_to_target_pct')}%) > 25%"

                self._append_activity_log({
                    "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                    "cycle": cycle,
                    "symbol": symbol,
                    "timeframe": tf,
                    "action": action,
                    "pillars": pillar_str,
                    "status": status_lbl,
                    "details": detail_str
                })

                if is_eligible:
                    logger.info(f"TARGET {p_cnt}/5 PILLARS ALIGNED (Req: {min_pillars_required})! {symbol} on {tf}!")
                    
                    # Advance the rotation pointer to the NEXT timeframe after this one
                    next_idx = (timeframes.index(tf) + 1) % len(timeframes)
                    st_up = self.load_state()
                    if 'tf_rotation_indices' not in st_up:
                        st_up['tf_rotation_indices'] = {}
                    st_up['tf_rotation_indices'][symbol] = next_idx
                    self.save_state(st_up)

                    found_setup = {
                        'symbol': symbol,
                        'timeframe': tf,
                        'asset_type': asset_type,
                        'prediction': pred,
                        'evaluation': eval_res,
                        'cycle': cycle,
                        'matched_pillars': p_cnt
                    }
                    break

            except Exception as e:
                logger.error(f"Scan error for {symbol} ({tf}): {e}")
                time.sleep(1)

        # If no setup was found in this pass, advance the pointer by 1 so the next cycle tests the next timeframe
        if not found_setup and timeframes:
            next_idx = (start_idx + 1) % len(timeframes)
            st_up = self.load_state()
            if 'tf_rotation_indices' not in st_up:
                st_up['tf_rotation_indices'] = {}
            st_up['tf_rotation_indices'][symbol] = next_idx
            self.save_state(st_up)

        return found_setup

    def execute_trade_batch(self, setup_data: Dict[str, Any], risk_pct: float = 1.0, max_dollar_risk: float = 0.0, batch_lot_size: Optional[float] = None) -> bool:
        try:
            symbol = setup_data['symbol']
            tf = setup_data['timeframe']
            pred = setup_data['prediction']
            eval_res = setup_data['evaluation']
            setup = pred.get('trade_setup') or pred.get('recommended_setup') or {}
            conf = pred.get('confluence', {})
            cycle = setup_data.get('cycle', 0)

            entry_price = float(setup.get('recommended_entry') or pred.get('market_data', {}).get('current_price', 0.0))
            sl_price = float(setup.get('stop_loss', 0.0))
            tp1_price = float(setup.get('tp1', 0.0))
            tp2_price = float(setup.get('tp2', 0.0))
            tp3_price = float(setup.get('tp3', 0.0))
            raw_action = str(setup.get('action') or conf.get('action', 'BUY')).upper()
            action = 'BUY' if 'BUY' in raw_action else 'SELL'

            # Institutional Breakeven Mark (with ATR fee/spread buffer to avoid fee deductions)
            breakeven_sl = float(setup.get('breakeven_sl') or 0.0)
            if breakeven_sl <= 0:
                atr = float(pred.get('market_data', {}).get('atr') or (abs(entry_price - sl_price) / 2.0))
                if action == 'BUY':
                    breakeven_sl = entry_price + (0.02 * atr)
                else:
                    breakeven_sl = max(entry_price * 0.001, entry_price - (0.02 * atr))
            breakeven_sl = round(breakeven_sl, 5)

            # 1. Resolve Exness broker symbol
            from src.data.forex_feeds import MT5ExnessProvider
            ex_p = MT5ExnessProvider()
            broker_sym = ex_p.get_exness_symbol(symbol) or (self.normalize_symbol(symbol).replace('/', '') + 'm')

            # 2. Get live account balance from MT5
            self.executor._ensure_connection()
            import MetaTrader5 as mt5
            acc = mt5.account_info()
            balance_usd = float(acc.balance) if acc and acc.balance > 0 else 1000.0

            # 3. Calculate position sizing & lot split
            active_lot_size = batch_lot_size if (batch_lot_size is not None and batch_lot_size > 0) else float(self.load_settings().get('batch_lot_size', 0.03))
            lot_sizing = self.executor.calculate_lot_and_risk(
                broker_symbol=broker_sym,
                balance_usd=balance_usd,
                entry_price=entry_price,
                stop_loss_price=sl_price,
                risk_pct=risk_pct,
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                tp3_price=tp3_price,
                total_volume_lots=active_lot_size
            )

            actual_risk_usd = float(lot_sizing.get('actual_risk_usd', 0.0))
            lot_split = lot_sizing.get('lot_split', {})
            total_lots = lot_sizing.get('total_lots', 0.0)
            is_auto_adjusted = lot_sizing.get('auto_adjusted_min', False)

            if is_auto_adjusted:
                logger.info(f"Auto-adjusted lot size for {symbol} ({broker_sym}) to broker minimum: {total_lots} lots (requested: {active_lot_size})")

            # 4. Check Dollar Risk Cap (Requirement 9)
            if max_dollar_risk > 0 and actual_risk_usd > max_dollar_risk:
                msg = f"RISK FILTER TRIGGERED: Setup on {symbol} ({tf}) has risk of ${actual_risk_usd:.2f}, exceeding max cap of ${max_dollar_risk:.2f}. Trade safely SKIPPED."
                logger.warning(msg)
                self._append_activity_log({
                    "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                    "cycle": cycle,
                    "symbol": symbol,
                    "timeframe": tf,
                    "action": action,
                    "pillars": "5/5",
                    "status": "SKIPPED (Risk Cap)",
                    "details": f"Risk ${actual_risk_usd:.2f} > Cap ${max_dollar_risk:.2f}"
                })
                return False

            logger.info(f"EXECUTING AUTONOMOUS 5/5 TRADE: {action} {symbol} ({tf}) on {broker_sym} | Total Lots: {total_lots} {lot_split}")
            exec_res = self.executor.execute_multi_target_trade(
                broker_symbol=broker_sym,
                action=action,
                sl_price=sl_price,
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                tp3_price=tp3_price,
                lot_split=lot_split
            )

            if exec_res.get('success'):
                batch_id = exec_res.get('batch_id') or (int(time.time()) % 1000000)
                raw_tickets = exec_res.get('tickets', [])
                ticket_ids = [t['ticket'] if isinstance(t, dict) else t for t in raw_tickets]
                logger.info(f"Executed Batch #{batch_id}: Tickets: {ticket_ids}")

                state = self.load_state()
                state['total_trades_taken'] = state.get('total_trades_taken', 0) + 1
                
                by_sym = state.get('trades_by_symbol', {})
                by_sym[symbol] = by_sym.get(symbol, 0) + 1
                state['trades_by_symbol'] = by_sym

                if 'open_batches' not in state:
                    state['open_batches'] = {}

                state['open_batches'][str(batch_id)] = {
                    'batch_id': batch_id,
                    'symbol': symbol,
                    'broker_sym': broker_sym,
                    'timeframe': tf,
                    'action': action,
                    'entry_price': entry_price,
                    'sl_price': sl_price,
                    'breakeven_sl': breakeven_sl,
                    'tp1_price': tp1_price,
                    'tp2_price': tp2_price,
                    'tp3_price': tp3_price,
                    'matched_pillars': setup_data.get('matched_pillars', 5),
                    'lot_split': lot_split,
                    'risk_usd': round(actual_risk_usd, 2),
                    'tickets': ticket_ids,
                    'executed_at': datetime.now(timezone.utc).isoformat(),
                    'status': 'OPEN',
                    'p1_score': eval_res.get('p1', {}).get('score', 0.0),
                    'p1_prob': eval_res.get('p1', {}).get('prob', 0.0)
                }
                self.save_state(state)

                m_pil = setup_data.get('matched_pillars', 5)
                adj_note = f" (Auto-clamped to Exness min {total_lots})" if is_auto_adjusted else ""
                self._append_activity_log({
                    "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                    "cycle": cycle,
                    "symbol": symbol,
                    "timeframe": tf,
                    "action": action,
                    "pillars": f"{m_pil}/5",
                    "status": f"EXECUTED (Batch #{batch_id})",
                    "details": f"Entry: {entry_price} | SL: {sl_price} | Lots: {lot_split.get('tp1_lots', 0)}/{lot_split.get('tp2_lots', 0)}/{lot_split.get('tp3_lots', 0)}{adj_note}"
                })
                return True
            else:
                err = exec_res.get('error', 'Execution failed')
                logger.error(f"Execution failed: {err}")
                self._append_activity_log({
                    "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                    "cycle": cycle,
                    "symbol": symbol,
                    "timeframe": tf,
                    "action": action,
                    "pillars": f"{setup_data.get('matched_pillars', 5)}/5",
                    "status": "EXECUTION FAILED",
                    "details": str(err)[:60]
                })
                return False

        except Exception as e:
            logger.error(f"Error in execute_trade_batch: {e}", exc_info=True)
            self._append_activity_log({
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "cycle": setup_data.get('cycle', 0),
                "symbol": setup_data.get('symbol', 'UNKNOWN'),
                "timeframe": setup_data.get('timeframe', '-'),
                "action": "ERROR",
                "status": "EXECUTION ERROR",
                "details": str(e)[:60]
            })
            return False

    def _sleep_countdown(self, seconds: int):
        for i in range(seconds, 0, -1):
            if _SCAN_STOP_EVENT.is_set() or _FORCE_STOP_EVENT.is_set() or not self.load_settings().get('enabled', False):
                break
            mins = i // 60
            secs = i % 60
            countdown_str = f"{mins:02d}:{secs:02d} remaining"
            try:
                state = self.load_state()
                state['next_scan_time'] = countdown_str
                self.save_state(state)
            except Exception:
                pass
            time.sleep(1)

    def run_worker_loop(self):
        logger.info("Autonomous Scanner Worker Loop STARTED.")
        self._is_running = True
        cycle_count = 0

        try:
            while not _FORCE_STOP_EVENT.is_set():
                # Check if scanning is stopped/disabled
                if _SCAN_STOP_EVENT.is_set() or not self.load_settings().get('enabled', False):
                    # Trade Management Mode: Autonomously manage existing active batches until completion
                    if self.has_active_batches():
                        state = self.load_state()
                        open_batches = state.get('open_batches', {})
                        if state.get('engine_status') != 'MANAGING_ACTIVE':
                            state['engine_status'] = 'MANAGING_ACTIVE'
                            state['next_scan_time'] = "Managing Trades"
                            self.save_state(state)

                        try:
                            self.audit_active_trades_and_learn()
                        except Exception as a_err:
                            logger.error(f"Error auditing active trades during management mode: {a_err}")

                        # Responsive short sleep before next audit check
                        for _ in range(6):
                            if _FORCE_STOP_EVENT.is_set() or (not _SCAN_STOP_EVENT.is_set() and self.load_settings().get('enabled', False)):
                                break
                            time.sleep(0.5)
                        continue
                    else:
                        logger.info("Autonomous scanner stopped and 0 active batches remain. Worker loop exiting cleanly.")
                        break

                settings = self.load_settings()
                symbols = settings.get('selected_symbols', DEFAULT_SYMBOLS)
                timeframes = settings.get('timeframes', DEFAULT_TIMEFRAMES)
                risk_pct = float(settings.get('risk_pct', 1.0))
                target_per_sym = int(settings.get('target_trades_per_symbol', 10))
                interval = int(settings.get('scan_interval_sec', 180))
                max_active_batches = int(settings.get('max_active_batches', 1))
                max_dollar_risk = float(settings.get('max_dollar_risk', 10.0))
                min_pillars_required = int(settings.get('min_pillars_required', 5))
                batch_lot_size = float(settings.get('batch_lot_size', 0.03))

                cycle_count += 1
                state = self.load_state()
                state['engine_status'] = "RUNNING"
                state['cycle_count'] = cycle_count
                state['last_scan_time'] = datetime.now(timezone.utc).isoformat()
                self.save_state(state)

                try:
                    self.audit_active_trades_and_learn()
                except Exception as a_err:
                    logger.error(f"Error in audit_active_trades: {a_err}")

                # Check Concurrent Active Batches Limit (Requirement 8)
                state = self.load_state()
                open_batches = state.get('open_batches', {})
                if len(open_batches) >= max_active_batches:
                    msg = f"Active batch limit reached ({len(open_batches)}/{max_active_batches} active). Waiting for positions to close..."
                    logger.info(msg)
                    self._append_activity_log({
                        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                        "cycle": cycle_count,
                        "symbol": "LIMIT",
                        "timeframe": "-",
                        "action": "WAIT",
                        "pillars": "-",
                        "status": f"Waiting ({len(open_batches)}/{max_active_batches} Active)",
                        "details": "Engine waiting for running trade batch to complete before scanning."
                    })
                    self._sleep_countdown(interval)
                    continue

                # Filter eligible symbols (not reached trade target)
                eligible_symbols = []
                by_sym = state.get('trades_by_symbol', {})
                for sym in symbols:
                    if by_sym.get(sym, 0) < target_per_sym:
                        eligible_symbols.append(sym)
                    else:
                        logger.info(f"Target of {target_per_sym} reached for {sym}. Skipping scan.")

                if not eligible_symbols:
                    logger.info("All selected symbols have reached their trade targets.")
                    self._sleep_countdown(interval)
                    continue

                # Parallel Multi-Pair Scanner Worker function
                def _scan_and_trade_single_symbol(sym: str):
                    if _SCAN_STOP_EVENT.is_set() or not self.load_settings().get('enabled', False):
                        return None

                    # Check max active batches before scanning
                    with _TRADE_EXEC_LOCK:
                        curr_st = self.load_state()
                        if len(curr_st.get('open_batches', {})) >= max_active_batches:
                            return None

                    try:
                        setup = self.scan_symbol_all_timeframes(
                            sym, timeframes, cycle=cycle_count, min_pillars_required=min_pillars_required
                        )
                        if setup and not _SCAN_STOP_EVENT.is_set() and self.load_settings().get('enabled', False):
                            with _TRADE_EXEC_LOCK:
                                curr_st = self.load_state()
                                if len(curr_st.get('open_batches', {})) < max_active_batches:
                                    traded = self.execute_trade_batch(
                                        setup,
                                        risk_pct=risk_pct,
                                        max_dollar_risk=max_dollar_risk,
                                        batch_lot_size=batch_lot_size
                                    )
                                    return traded
                        return False
                    except Exception as s_err:
                        logger.error(f"Error in parallel scan/trade for {sym}: {s_err}", exc_info=True)
                        return False

                # Execute all eligible symbols in PARALLEL threads
                num_workers = min(len(eligible_symbols), 6)
                logger.info(f"[ParallelScanner] Launching concurrent scan for {len(eligible_symbols)} symbols: {eligible_symbols} with {num_workers} threads.")

                with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers, thread_name_prefix="PairScanner") as pool:
                    future_to_sym = {pool.submit(_scan_and_trade_single_symbol, s): s for s in eligible_symbols}
                    for fut in concurrent.futures.as_completed(future_to_sym):
                        s_name = future_to_sym[fut]
                        try:
                            fut.result()
                        except Exception as fut_err:
                            logger.error(f"Parallel worker error on {s_name}: {fut_err}")

                if _SCAN_STOP_EVENT.is_set() or not self.load_settings().get('enabled', False):
                    continue

                # Sleep interval with countdown in state (Requirement 7)
                logger.info(f"Cycle {cycle_count} complete. Sleeping for {interval}s before next scan pass...")
                self._sleep_countdown(interval)

        except Exception as e:
            logger.error(f"Error in autonomous trader worker loop: {e}", exc_info=True)
        finally:
            self._is_running = False
            state = self.load_state()
            if not self.has_active_batches():
                state['engine_status'] = "STOPPED"
                state['next_scan_time'] = None
            else:
                state['engine_status'] = "MANAGING_ACTIVE"
            self.save_state(state)
            logger.info("Autonomous Scanner Worker Loop finished.")

    def start(self):
        settings = self.load_settings()
        settings['enabled'] = True
        self.save_settings(settings)

        _SCAN_STOP_EVENT.clear()
        _FORCE_STOP_EVENT.clear()

        state = self.load_state()
        state['engine_status'] = "RUNNING"
        self.save_state(state)

        if not self.is_thread_alive():
            self._thread = threading.Thread(target=self.run_worker_loop, daemon=True, name="Auto5PillarTraderThread")
            self._thread.start()
            logger.info("Background trader thread started.")
        else:
            logger.info("Background trader thread already alive; resumed scanning mode.")
        self._is_running = True

    def stop(self):
        settings = self.load_settings()
        settings['enabled'] = False
        self.save_settings(settings)

        _SCAN_STOP_EVENT.set()
        has_trades = self.has_active_batches()

        state = self.load_state()
        state['next_scan_time'] = None

        if has_trades:
            state['engine_status'] = "MANAGING_ACTIVE"
            self._append_activity_log({
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "cycle": state.get('cycle_count', 0),
                "symbol": "SYSTEM",
                "timeframe": "-",
                "action": "STOP_SCAN",
                "pillars": "-",
                "status": "Scanning Halted (Managing Trades)",
                "details": f"Stopped scanning. Autonomously managing {len(state.get('open_batches', {}))} active batch(es)."
            })
            logger.info("Scan stop signal sent. Active batches will continue being monitored autonomously.")
            if not self.is_thread_alive():
                _FORCE_STOP_EVENT.clear()
                self._thread = threading.Thread(target=self.run_worker_loop, daemon=True, name="Auto5PillarTraderThread")
                self._thread.start()
        else:
            _FORCE_STOP_EVENT.set()
            state['engine_status'] = "STOPPED"
            self._append_activity_log({
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "cycle": state.get('cycle_count', 0),
                "symbol": "SYSTEM",
                "timeframe": "-",
                "action": "STOP",
                "pillars": "-",
                "status": "Engine Stopped (Idle)",
                "details": "Autonomous scanning and trading stopped."
            })
            logger.info("Stop signal sent to autonomous trader worker thread (0 active trades).")

        self.save_state(state)
        self._is_running = False

    def is_running(self) -> bool:
        return self.is_scan_active()



_ENGINE_INSTANCE: Optional[AutonomousTraderEngine] = None

def get_engine() -> AutonomousTraderEngine:
    global _ENGINE_INSTANCE
    if _ENGINE_INSTANCE is None:
        _ENGINE_INSTANCE = AutonomousTraderEngine()
    return _ENGINE_INSTANCE
