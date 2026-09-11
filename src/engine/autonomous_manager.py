import os
import sys
import time
import json
import logging
import threading
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

DEFAULT_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h"]
DEFAULT_SYMBOLS = ["XAU/USD", "BTC/USD"]

class AutonomousTraderEngine:
    def __init__(self):
        self.orch = PredictorOrchestrator()
        self.executor = MT5TradeExecutor()
        self._thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._is_running = False

    @staticmethod
    def load_settings() -> Dict[str, Any]:
        default_settings = {
            "enabled": False,
            "selected_symbols": DEFAULT_SYMBOLS,
            "timeframes": DEFAULT_TIMEFRAMES,
            "risk_pct": 1.0,
            "scan_interval_sec": 40,
            "target_trades_per_symbol": 10
        }
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
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

    @staticmethod
    def load_state() -> Dict[str, Any]:
        default_state = {
            "total_trades_taken": 0,
            "trades_by_symbol": {},
            "open_batches": {},
            "wins": 0,
            "losses": 0,
            "breakevens": 0,
            "last_scan_time": None,
            "last_scanned_symbol": None,
            "engine_status": "STOPPED"
        }
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    default_state.update(data)
            except Exception as e:
                logger.error(f"Error loading state: {e}")
        return default_state

    @staticmethod
    def save_state(state: Dict[str, Any]):
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

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

    def evaluate_5_pillars(self, pred_res: Dict[str, Any]) -> Dict[str, Any]:
        conf = pred_res['confluence']
        alpha = pred_res.get('alpha_sniper', {})
        mtf = pred_res.get('mtf_alignment', {})
        news = pred_res.get('economic_news', {})
        quantum = pred_res.get('quantum_sniper', alpha.get('quantum_sniper', {}))
        whale_gate = pred_res.get('whale_sentiment_gate', {})

        action = conf.get('action', '')
        is_dir_buy = ('BUY' in action) and ('FILTER' not in action) and ('BLACKOUT' not in action)
        is_dir_sell = ('SELL' in action) and ('FILTER' not in action) and ('BLACKOUT' not in action)
        is_trade_active = is_dir_buy or is_dir_sell

        # Pillar 1: Predictive Confluence & Alpha Sniper
        p1_score = float(conf.get('confluence_score', 0))
        p1_prob = float(alpha.get('calibrated_win_probability_pct', conf.get('quality_index_pct', 50)))
        p1_ok = False
        if is_dir_buy and p1_score >= 35.0 and p1_prob >= 80.0:
            p1_ok = True
        elif is_dir_sell and p1_score <= -35.0 and p1_prob >= 80.0:
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
            'p5': {'ok': p5_ok, 'status': p5_status}
        }

    def audit_active_trades_and_learn(self):
        state = self.load_state()
        journal = self.load_journal()
        try:
            # Auto breakeven check
            be_results = self.executor.check_and_apply_auto_breakeven()
            if be_results:
                for b in be_results:
                    logger.info(f"AUTO-BREAKEVEN: Position #{b['ticket']} SL shifted to BE {b['new_sl']}")

            import MetaTrader5 as mt5
            self.executor._ensure_connection()
            now_utc = datetime.now(timezone.utc)
            deals = mt5.history_deals_get(now_utc - timedelta(hours=48), now_utc)
            open_pos = mt5.positions_get()
            open_tickets = {p.ticket for p in open_pos} if open_pos else set()

            open_batches = dict(state.get('open_batches', {}))
            state_changed = False

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

                    if outcome == 'WIN':
                        state['wins'] = state.get('wins', 0) + 1
                    elif outcome == 'BREAKEVEN':
                        state['breakevens'] = state.get('breakevens', 0) + 1
                    else:
                        state['losses'] = state.get('losses', 0) + 1
                        lesson_txt = f"On {trade['symbol']} ({trade['timeframe']}): Stop loss triggered. Buffer refined to prevent liquidity hunt wicks."
                        journal['lessons_learned'].append(lesson_txt)
                        self.save_journal(journal)

                    del open_batches[batch_id]
                    state['open_batches'] = open_batches
                    state_changed = True

            # If metrics are still zero but historical deals exist, audit directly from MT5 deals
            if state.get('wins', 0) == 0 and state.get('losses', 0) == 0 and state.get('breakevens', 0) == 0 and deals:
                pos_pnl = {}
                for d in deals:
                    if d.entry == 1:
                        pid = getattr(d, 'position_id', 0)
                        pos_pnl[pid] = pos_pnl.get(pid, 0.0) + float(d.profit)
                if pos_pnl:
                    state['wins'] = sum(1 for pnl in pos_pnl.values() if pnl > 0.5)
                    state['breakevens'] = sum(1 for pnl in pos_pnl.values() if abs(pnl) <= 0.5)
                    state['losses'] = sum(1 for pnl in pos_pnl.values() if pnl < -0.5)
                    state_changed = True

            if state_changed:
                self.save_state(state)

        except Exception as e:
            logger.error(f"Error in audit and learning: {e}")

    def scan_symbol_all_timeframes(self, symbol: str, timeframes: List[str]) -> Optional[Dict[str, Any]]:
        asset_type = 'crypto' if any(c in symbol.upper() for c in ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']) else 'forex'
        logger.info(f"Scanning {symbol} across timeframes: {timeframes}")

        for tf in timeframes:
            if self._stop_requested.is_set():
                return None
            try:
                pred = self.orch.run_prediction(
                    symbol=symbol,
                    asset_type=asset_type,
                    market_mode='spot',
                    timeframe=tf,
                    preferred_exchange='Exness (MetaTrader 5)'
                )
                eval_res = self.evaluate_5_pillars(pred)
                p_cnt = eval_res['aligned_count']
                logger.info(f"  -> [{symbol} {tf}] Pillars: {p_cnt}/5 Aligned | Action: {pred['confluence']['action']}")

                if eval_res['is_fully_aligned']:
                    logger.info(f"TARGET 5/5 PILLARS ALIGNED! {symbol} on {tf}!")
                    return {
                        'symbol': symbol,
                        'timeframe': tf,
                        'asset_type': asset_type,
                        'prediction': pred,
                        'evaluation': eval_res
                    }
            except Exception as e:
                logger.error(f"Scan error for {symbol} ({tf}): {e}")
                time.sleep(1)

        return None

    def execute_trade_batch(self, setup_data: Dict[str, Any], risk_pct: float = 1.0) -> bool:
        symbol = setup_data['symbol']
        tf = setup_data['timeframe']
        pred = setup_data['prediction']
        eval_res = setup_data['evaluation']
        setup = pred['recommended_setup']
        conf = pred['confluence']

        logger.info(f"EXECUTING AUTONOMOUS 5/5 TRADE: {conf['action']} {symbol} ({tf})")
        exec_res = self.executor.execute_signal_setup(
            prediction_result=pred,
            broker_symbol=None,
            risk_pct=risk_pct
        )

        if exec_res.get('success'):
            logger.info(f"Executed Batch #{exec_res['batch_id']}: Tickets: {exec_res['tickets']}")
            state = self.load_state()
            state['total_trades_taken'] = state.get('total_trades_taken', 0) + 1
            by_sym = state.get('trades_by_symbol', {})
            by_sym[symbol] = by_sym.get(symbol, 0) + 1
            state['trades_by_symbol'] = by_sym

            if 'XAU' in symbol:
                state['xau_trades_taken'] = state.get('xau_trades_taken', 0) + 1
            elif 'BTC' in symbol:
                state['btc_trades_taken'] = state.get('btc_trades_taken', 0) + 1

            if 'open_batches' not in state:
                state['open_batches'] = {}

            state['open_batches'][exec_res['batch_id']] = {
                'batch_id': exec_res['batch_id'],
                'symbol': symbol,
                'broker_sym': exec_res.get('broker_symbol'),
                'timeframe': tf,
                'action': conf['action'],
                'entry_price': setup['recommended_entry'],
                'sl_price': setup['stop_loss'],
                'tp1_price': setup['tp1'],
                'tp2_price': setup['tp2'],
                'tp3_price': setup['tp3'],
                'lot_split': exec_res.get('lot_split'),
                'tickets': exec_res.get('tickets', []),
                'executed_at': datetime.now(timezone.utc).isoformat(),
                'status': 'OPEN',
                'p1_score': eval_res['p1']['score'],
                'p1_prob': eval_res['p1']['prob']
            }
            self.save_state(state)
            return True
        else:
            logger.error(f"Execution failed: {exec_res.get('error')}")
            return False

    def run_worker_loop(self):
        logger.info("Autonomous Scanner Worker Loop STARTED.")
        self._is_running = True

        while not self._stop_requested.is_set():
            settings = self.load_settings()
            if not settings.get('enabled', False):
                logger.info("Autonomous engine is disabled in settings. Worker loop exiting.")
                break

            symbols = settings.get('selected_symbols', DEFAULT_SYMBOLS)
            timeframes = settings.get('timeframes', DEFAULT_TIMEFRAMES)
            risk_pct = float(settings.get('risk_pct', 1.0))
            target_per_sym = int(settings.get('target_trades_per_symbol', 10))
            interval = int(settings.get('scan_interval_sec', 40))

            state = self.load_state()
            state['engine_status'] = "RUNNING"
            state['last_scan_time'] = datetime.now(timezone.utc).isoformat()
            self.save_state(state)

            self.audit_active_trades_and_learn()

            for sym in symbols:
                if self._stop_requested.is_set():
                    break

                state = self.load_state()
                by_sym = state.get('trades_by_symbol', {})
                current_sym_trades = by_sym.get(sym, 0)
                if 'XAU' in sym and 'xau_trades_taken' in state and state['xau_trades_taken'] > current_sym_trades:
                    current_sym_trades = state['xau_trades_taken']
                if 'BTC' in sym and 'btc_trades_taken' in state and state['btc_trades_taken'] > current_sym_trades:
                    current_sym_trades = state['btc_trades_taken']

                if current_sym_trades >= target_per_sym:
                    logger.info(f"Target of {target_per_sym} reached for {sym}. Skipping scan.")
                    continue

                state['last_scanned_symbol'] = sym
                self.save_state(state)

                setup = self.scan_symbol_all_timeframes(sym, timeframes)
                if setup:
                    self.execute_trade_batch(setup, risk_pct=risk_pct)
                    time.sleep(2)

            for _ in range(max(1, interval)):
                if self._stop_requested.is_set():
                    break
                time.sleep(1)

        self._is_running = False
        state = self.load_state()
        state['engine_status'] = "STOPPED"
        self.save_state(state)
        logger.info("Autonomous Scanner Worker Loop STOPPED.")

    def start(self):
        if self._is_running and self._thread and self._thread.is_alive():
            logger.info("Worker thread is already running.")
            return

        settings = self.load_settings()
        settings['enabled'] = True
        self.save_settings(settings)

        self._stop_requested.clear()
        self._thread = threading.Thread(target=self.run_worker_loop, daemon=True, name="Auto5PillarTraderThread")
        self._thread.start()
        logger.info("Background trader thread started.")

    def stop(self):
        settings = self.load_settings()
        settings['enabled'] = False
        self.save_settings(settings)

        self._stop_requested.set()
        logger.info("Stop signal sent to autonomous trader worker thread.")

    def is_running(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        settings = self.load_settings()
        return settings.get('enabled', False)

_ENGINE_INSTANCE: Optional[AutonomousTraderEngine] = None

def get_engine() -> AutonomousTraderEngine:
    global _ENGINE_INSTANCE
    if _ENGINE_INSTANCE is None:
        _ENGINE_INSTANCE = AutonomousTraderEngine()
    return _ENGINE_INSTANCE
