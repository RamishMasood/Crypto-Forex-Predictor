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
from src.engine.session_manager import SessionManager
from src.engine.htf_confluence import HTFConfluenceChecker
from src.engine.recommended_presets import RecommendedPresetsManager, RECOMMENDED_SYMBOL_PROFILES

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
            "batch_lot_size": 0.03,             # Customizable batch lot size (e.g. 0.03 -> 0.01, 0.01, 0.01)
            "allow_same_tf_trades": True,       # Customizable switch: Allow multiple trades on same timeframe
            "breakeven_mode": "tight",          # "tight" (immediate 0.38 ATR lock) | "loose" (2-stage runner breathing room)
            "active_sessions": ["London Session", "New York Session"], # Allowed trading sessions
            "htf_filter_enabled": True,         # Higher Timeframe Trend Confluence filter
            "recommended_mode": False           # Institutional Recommended Auto-Pilot (per-pair backtested optimum)
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
                # Write to temp file first
                tmp_file = STATE_FILE + ".tmp"
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2)
                # On Windows, os.replace can fail if target file is opened by another thread.
                # Retry replace up to 5 times.
                replaced = False
                for _ in range(5):
                    try:
                        os.replace(tmp_file, STATE_FILE)
                        replaced = True
                        break
                    except OSError:
                        time.sleep(0.05)
                if not replaced:
                    # Fallback: direct write
                    with open(STATE_FILE, 'w', encoding='utf-8') as f:
                        json.dump(state, f, indent=2)
                    if os.path.exists(tmp_file):
                        try:
                            os.remove(tmp_file)
                        except OSError:
                            pass
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
                "min_calibrated_prob": 82.0   # Bayesian AlphaSniper threshold (realistically reaches 82%+ in ELITE setups)
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
        if len(s) == 6 and not s.endswith("USD"):
            return f"{s[:3]}/{s[3:]}"
        if s in ["BTC", "BTCUSD"]:
            return "BTC/USD"
        if s in ["ETH", "ETHUSD"]:
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
                    "min_calibrated_prob": 82.0   # Bayesian AlphaSniper threshold
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
        req_prob = float(opt_adj.get('min_calibrated_prob', 82.0))

        p1_score = float(conf.get('confluence_score', 0))
        p1_prob = float(alpha.get('calibrated_win_probability_pct', conf.get('quality_index_pct', 50)))
        p1_ev = float(alpha.get('expected_value_r', alpha.get('trade_expectancy_r', 0.0)))
        p1_ok = False

        if is_chop:
            p1_ok = False
            p1_status = "CHOP CONSOLIDATION DETECTED"
            p1_desc = chop_gate.get('reason', 'Market dead sideways. Breakout expansion awaited.')
            p1_badge = "CHOP BLOCKED"
            p1_col = "#ef4444"
        elif not is_spread_pass:
            p1_ok = False
            p1_status = "SPREAD FILTER EXCEEDED"
            p1_desc = f"Spread eats {spread_guard.get('spread_to_target_pct', 0):.1f}% of TP1 target (> {spread_guard.get('max_allowed_pct', 18):.0f}%)"
            p1_badge = "SPREAD BLOCKED"
            p1_col = "#ef4444"
        elif (is_dir_buy or is_dir_sell) and p1_ev < 0.15:
            p1_ok = False
            p1_status = f"EV GATE: +{p1_ev:.2f}R < +0.15R"
            p1_desc = f"Expected Value (+{p1_ev:.2f}R) below +0.15R threshold. Sub-optimal expectancy."
            p1_badge = "LOW EV"
            p1_col = "#eab308"
        elif is_dir_buy and p1_score >= req_score and p1_prob >= req_prob:
            p1_ok = True
            p1_status = "GREEN LIGHT: BUY ALIGNED"
            p1_desc = f"Score: {p1_score:+.1f} | Calibrated Prob: {p1_prob:.1f}% | EV: +{p1_ev:.2f}R"
            p1_badge = "BUY READY"
            p1_col = "#00c853"
        elif is_dir_sell and p1_score <= -req_score and p1_prob >= req_prob:
            p1_ok = True
            p1_status = "RED LIGHT: SELL ALIGNED"
            p1_desc = f"Score: {p1_score:+.1f} | Calibrated Prob: {p1_prob:.1f}% | EV: +{p1_ev:.2f}R"
            p1_badge = "SELL READY"
            p1_col = "#ff1744"
        else:
            p1_ok = False
            p1_status = "GATE BLOCKED: INSUFFICIENT CONFLUENCE"
            p1_desc = f"Score: {p1_score:+.1f} (Req: ±{req_score:.0f}) | Probability: {p1_prob:.1f}% (Req: ≥{req_prob:.0f}%) | EV: +{p1_ev:.2f}R"
            p1_badge = "WAIT"
            p1_col = "#eab308"

        # Pillar 2: MTF Alignment
        s1 = mtf.get('screen1_macro', {}) if mtf else {}
        s2 = mtf.get('screen2_zone', {}) if mtf else {}
        s3 = mtf.get('screen3_trigger', {}) if mtf else {}
        s1_bias = s1.get('macro_bias', 'NEUTRAL')
        s1_200 = s1.get('close_vs_ema200', 'UNKNOWN')
        s2_zone = s2.get('zone_type', 'EQUILIBRIUM')
        s3_trig = s3.get('trigger_status', 'WAITING')
        p2_ok = False
        if is_dir_buy:
            if s1_bias in ['BULLISH', 'MILD_BULLISH'] and s1_200 == 'ABOVE_200_EMA':
                p2_ok = True
                p2_status = "ALIGNED FOR BUY"
                p2_desc = f"Macro: Above 200 EMA ({s1_bias}) | Zone: {s2_zone} | Trigger: {s3_trig}"
                p2_badge = "3/3 ALIGNED"
                p2_col = "#00c853"
            else:
                p2_ok = False
                p2_status = "MACRO CONFLICT (BUY FORBIDDEN)"
                p2_desc = f"Price is below 200 EMA or Macro is Bearish ({s1_bias}). Counter-trend long blocked."
                p2_badge = "MACRO CONFLICT"
                p2_col = "#ef4444"
        elif is_dir_sell:
            if s1_bias in ['BEARISH', 'MILD_BEARISH'] and s1_200 == 'BELOW_200_EMA':
                p2_ok = True
                p2_status = "ALIGNED FOR SELL"
                p2_desc = f"Macro: Below 200 EMA ({s1_bias}) | Zone: {s2_zone} | Trigger: {s3_trig}"
                p2_badge = "3/3 ALIGNED"
                p2_col = "#ff1744"
            else:
                p2_ok = False
                p2_status = "MACRO CONFLICT (SELL FORBIDDEN)"
                p2_desc = f"Price is above 200 EMA or Macro is Bullish ({s1_bias}). Counter-trend short blocked."
                p2_badge = "MACRO CONFLICT"
                p2_col = "#ef4444"
        else:
            p2_ok = False
            p2_status = "NEUTRAL / MONITORING"
            p2_desc = f"Screen 1: {s1_bias} ({s1_200}) | Screen 2: {s2_zone}"
            p2_badge = "NEUTRAL"
            p2_col = "#9ca3af"

        # Pillar 3: Economic News Guard
        is_news_blackout = bool(news.get('is_blackout', False)) if news else False
        next_news = news.get('next_high_impact_event', {}) if news else {}
        mins_to_event = news.get('minutes_to_next_event') if news else None
        p3_ok = not is_news_blackout
        if not is_news_blackout:
            p3_status = "CLEAR: SAFE TO TRADE"
            if next_news and mins_to_event is not None and mins_to_event < 180:
                p3_desc = f"No immediate red-folder event. Next: {next_news.get('title','')} in {int(mins_to_event)}m ({next_news.get('country','')})"
            else:
                p3_desc = "No high-impact central bank or CPI releases within blackout threshold."
            p3_badge = "CLEAR / SAFE"
            p3_col = "#00c853"
        else:
            p3_status = "🚨 DANGER: BLACKOUT ACTIVE"
            p3_desc = f"{news.get('blackout_reason', 'High-impact macroeconomic release window active.')} Do NOT trade."
            p3_badge = "DO NOT TRADE"
            p3_col = "#ef4444"

        # Pillar 4: Quantum Overextension Guard
        q_cvd = quantum.get('cvd_divergence', {}) if quantum else {}
        q_cvd_type = q_cvd.get('divergence_type', 'NONE')
        q_swp = quantum.get('liquidity_sweep', {}) if quantum else {}
        q_swp_type = q_swp.get('sweep_type', 'NONE')
        q_overext = quantum.get('overextension', {}) if quantum else {}
        is_overextended = bool(q_overext.get('is_overextended', False))
        overext_dir = q_overext.get('direction', 'BALANCED')
        dist_atr = float(q_overext.get('dist_atr', 0.0))

        chase_blocked = False
        if is_overextended:
            if is_dir_buy and (overext_dir == 'BULL_EXHAUSTION' or dist_atr > 0):
                chase_blocked = True
            elif is_dir_sell and (overext_dir == 'BEAR_EXHAUSTION' or dist_atr < 0):
                chase_blocked = True

        p4_ok = False
        if chase_blocked:
            p4_ok = False
            p4_status = "OVEREXTENDED (ANTI-CHASE ACTIVE)"
            p4_desc = f"Price extended {abs(dist_atr):.1f} ATR from EMA 20 ({overext_dir}). High mean-reversion exhaustion risk."
            p4_badge = "CHASE BLOCKED"
            p4_col = "#ef4444"
        elif is_dir_buy:
            if 'BULLISH' in q_cvd_type or 'BULLISH' in q_swp_type or 'BULL' in quantum.get('quantum_bias', ''):
                p4_ok = True
                p4_status = "ORDER FLOW BULLISH CONFIRMED"
                p4_desc = f"CVD: {q_cvd_type} | Judas Sweep: {q_swp_type} | Anti-Chase: SAFE"
                p4_badge = "BUY CONFIRMED"
                p4_col = "#00c853"
            else:
                p4_ok = True
                p4_status = "ORDER FLOW BALANCED"
                p4_desc = "No adverse order flow divergence against Buy setup. Anti-Chase: SAFE"
                p4_badge = "PASS"
                p4_col = "#38bdf8"
        elif is_dir_sell:
            if 'BEARISH' in q_cvd_type or 'BEARISH' in q_swp_type or 'BEAR' in quantum.get('quantum_bias', ''):
                p4_ok = True
                p4_status = "ORDER FLOW BEARISH CONFIRMED"
                p4_desc = f"CVD: {q_cvd_type} | Judas Sweep: {q_swp_type} | Anti-Chase: SAFE"
                p4_badge = "SELL CONFIRMED"
                p4_col = "#ff1744"
            else:
                p4_ok = True
                p4_status = "ORDER FLOW BALANCED"
                p4_desc = "No adverse order flow divergence against Sell setup. Anti-Chase: SAFE"
                p4_badge = "PASS"
                p4_col = "#38bdf8"
        else:
            p4_ok = False
            p4_status = "AWAITING DIRECTION"
            p4_desc = f"CVD: {q_cvd_type} | Sweeps: {q_swp_type} | Bias: {quantum.get('quantum_bias', 'NEUTRAL')}"
            p4_badge = "WAIT"
            p4_col = "#9ca3af"

        # Pillar 5: Whale Sentiment & Smart Money Gate (Crypto Futures, Forex & Gold, CME Proxy, Honest Labeling)
        cot = pred_res.get('cot_sentiment') or whale_gate.get('cot_sentiment')
        fut_signals = pred_res.get('futures_signals')
        cme = pred_res.get('cme_proxy_data') or {}
        has_futures = bool(fut_signals and fut_signals.get('funding_analysis'))
        has_cot = bool(cot and cot.get('available'))
        has_cme = bool(cme and cme.get('available'))
        p5_available = has_futures or has_cot or has_cme

        if has_futures:
            # Perpetual Futures: Squeeze & Funding Analysis
            # NOTE: p5_ok evaluates ONLY whale/futures signals independently.
            # Chop state is NOT factored here — is_fully_aligned at L617 uses is_trade_active as the
            # final safety net, so chop will still block actual trade execution even if p5 passes.
            w_passed = whale_gate.get('passed', True) if whale_gate else True
            w_unlocked = whale_gate.get('whale_gate_unlocked', False) if whale_gate else False
            w_reason = whale_gate.get('reason', 'Benign standard funding') if whale_gate else 'Benign funding'
            # is_counter_whale = TRUE means trade DIRECTLY opposes an active squeeze (fatal liquidation trap).
            # is_counter_whale = FALSE means just no extreme catalyst, but no dangerous opposing force either.
            w_is_counter = bool(whale_gate.get('is_counter_whale', False)) if whale_gate else False

            if w_unlocked and w_passed:
                # ELITE whale catalyst: extreme funding or OI squeeze confirmed aligned with trade direction
                p5_ok = True
                p5_status = "WHALE CATALYST UNLOCKED ⚡"
                p5_desc = f"{w_reason} — Squeeze energy supports explosive move."
                p5_badge = "WHALE CONFIRMED"
                p5_col = "#00c853" if is_dir_buy else "#ff1744"
            elif w_is_counter:
                # FATAL: Trade direction directly opposes an active squeeze → liquidation cascade risk
                p5_ok = False
                p5_status = "COUNTER-WHALE TRAP DANGER 🚨"
                p5_desc = f"{w_reason} — Trade opposes active squeeze. High liquidation cascade risk."
                p5_badge = "TRAP DANGER"
                p5_col = "#ef4444"
            elif not w_passed and not w_is_counter:
                # Insufficient squeeze catalyst for ELITE tier — but NO opposing force detected.
                # This is HIGH CONVICTION territory (84% cap in alpha_sniper), NOT a trap.
                # Pillar 5 passes — trade is safe, just not ELITE grade.
                p5_ok = True
                p5_status = "HIGH CONVICTION SAFE (No Extreme Squeeze)"
                p5_desc = f"No extreme funding or OI squeeze catalyst detected — but no counter-whale trap either. Trade at HIGH CONVICTION tier (84% cap). {w_reason}"
                p5_badge = "HIGH CONVICTION"
                p5_col = "#38bdf8"
            else:
                # Benign / no futures data issue = safe
                p5_ok = True
                p5_status = "BENIGN FUNDING (WHALE FLOW SAFE)"
                p5_desc = f"{w_reason} — No squeeze trap detected. Whale flow benign."
                p5_badge = "SAFE"
                p5_col = "#38bdf8"
        elif has_cot:
            # Forex & Gold: CFTC Commitments of Traders (COT) Smart Money & Retail Sentiment
            cot_bias = str(cot.get('smart_money_bias', 'NEUTRAL')).upper()
            cot_score = float(cot.get('sentiment_score', 0.0))
            cot_summary = cot.get('summary', 'CFTC COT Smart Money Active')

            # Multi-Timeframe Horizon Adaptation:
            # Scalp timeframes (1m, 3m, 5m, 15m) evaluate real-time order flow and broker volume.
            # Weekly macro COT lag (3-7 days old) acts as a macro boost when aligned, and permits
            # intraday scalps with forced TP1 (0.38*ATR) scalp bank & Auto-BE rather than an inappropriate binary block.
            # Macro timeframes (30m, 1h, 4h, 1d) strictly enforce weekly COT as a macro institutional gatekeeper.
            tf = pred_res.get('metadata', {}).get('timeframe') or pred_res.get('timeframe') or '1h'
            is_scalp_tf = str(tf).lower() in ['1m', '3m', '5m', '15m']

            if is_scalp_tf:
                # ─── SCALP HORIZON LOGIC (1m, 3m, 5m, 15m) ───
                # COT conflict on scalp TF → still permitted (intraday scalp vs weekly lag),
                # so p5_ok=True unless there is NO directional signal at all.
                if is_dir_buy:
                    if 'BULLISH' in cot_bias or cot_score >= 12.0:
                        p5_ok = True
                        p5_status = f"COT MACRO TAILWIND ({str(tf).upper()} SCALP BOOST)"
                        p5_desc = f"{cot_summary} — Weekly institutional smart money aligns with intraday scalp entry."
                        p5_badge = "COT MACRO BOOST"
                        p5_col = "#00c853"
                    elif 'BEARISH' in cot_bias or cot_score <= -15.0:
                        # COT opposes but scalp is still approved — Pillar 5 passes (with caution label).
                        # Enforce TP1 scalp bank & Auto-BE in trade execution.
                        p5_ok = True
                        p5_status = f"INTRADAY SCALP CONFIRMED ({str(tf).upper()} HORIZON)"
                        p5_desc = f"Intraday scalp approved on {tf}. Weekly COT opposes ({cot_bias}), strictly enforce TP1 (0.38*ATR) scalp bank & Auto-BE."
                        p5_badge = "INTRADAY SCALP"
                        p5_col = "#eab308"
                    else:
                        p5_ok = True
                        p5_status = f"SCALP PERMITTED (NEUTRAL COT, {str(tf).upper()})"
                        p5_desc = f"{cot_summary} — Real-time price action clear for intraday scalp execution."
                        p5_badge = "SCALP SAFE"
                        p5_col = "#00c853"
                elif is_dir_sell:
                    if 'BEARISH' in cot_bias or cot_score <= -12.0:
                        p5_ok = True
                        p5_status = f"COT MACRO TAILWIND ({str(tf).upper()} SCALP BOOST)"
                        p5_desc = f"{cot_summary} — Weekly institutional smart money aligns with intraday scalp entry."
                        p5_badge = "COT MACRO BOOST"
                        p5_col = "#ff1744"
                    elif 'BULLISH' in cot_bias or cot_score >= 15.0:
                        # COT opposes but scalp is still approved — Pillar 5 passes (with caution label).
                        p5_ok = True
                        p5_status = f"INTRADAY SCALP CONFIRMED ({str(tf).upper()} HORIZON)"
                        p5_desc = f"Intraday scalp approved on {tf}. Weekly COT opposes ({cot_bias}), strictly enforce TP1 (0.38*ATR) scalp bank & Auto-BE."
                        p5_badge = "INTRADAY SCALP"
                        p5_col = "#eab308"
                    else:
                        p5_ok = True
                        p5_status = f"SCALP PERMITTED (NEUTRAL COT, {str(tf).upper()})"
                        p5_desc = f"{cot_summary} — Real-time price action clear for intraday scalp execution."
                        p5_badge = "SCALP SAFE"
                        p5_col = "#00c853"
                else:
                    # No directional signal — monitoring only
                    p5_ok = False
                    p5_status = "COT SENTIMENT MONITORING"
                    p5_desc = cot_summary
                    p5_badge = "MONITORING"
                    p5_col = "#9ca3af"
            else:
                # ─── MACRO HORIZON LOGIC (30m, 1h, 4h, 1d) ───
                # COT CONFLICT at macro TF is a hard block (institutions opposing = high risk).
                # COT ALIGNED or NEUTRAL at macro TF = Pillar 5 clears independently.
                if is_dir_buy:
                    if 'BULLISH' in cot_bias or cot_score >= 12.0:
                        p5_ok = True
                        p5_status = "COT SMART MONEY BULLISH CONFIRMED"
                        p5_desc = f"{cot_summary} — Institutional smart money net long supports Buy."
                        p5_badge = "COT ALIGNED"
                        p5_col = "#00c853"
                    elif 'BEARISH' in cot_bias or cot_score <= -15.0:
                        p5_ok = False
                        p5_status = "COT SMART MONEY BEARISH CONFLICT"
                        p5_desc = f"{cot_summary} — Weekly CFTC institutional positioning opposes Macro Buy."
                        p5_badge = "COT CONFLICT"
                        p5_col = "#ef4444"
                    else:
                        # Neutral COT = no institutional conflict = Pillar 5 clears.
                        p5_ok = True
                        p5_status = "COT SENTIMENT BALANCED"
                        p5_desc = f"{cot_summary} — Neutral institutional positioning, no conflict detected."
                        p5_badge = "COT NEUTRAL"
                        p5_col = "#38bdf8"
                elif is_dir_sell:
                    if 'BEARISH' in cot_bias or cot_score <= -12.0:
                        p5_ok = True
                        p5_status = "COT SMART MONEY BEARISH CONFIRMED"
                        p5_desc = f"{cot_summary} — Institutional smart money net short supports Sell."
                        p5_badge = "COT ALIGNED"
                        p5_col = "#ff1744"
                    elif 'BULLISH' in cot_bias or cot_score >= 15.0:
                        p5_ok = False
                        p5_status = "COT SMART MONEY BULLISH CONFLICT"
                        p5_desc = f"{cot_summary} — Weekly CFTC institutional positioning opposes Macro Sell."
                        p5_badge = "COT CONFLICT"
                        p5_col = "#ef4444"
                    else:
                        # Neutral COT = no institutional conflict = Pillar 5 clears.
                        p5_ok = True
                        p5_status = "COT SENTIMENT BALANCED"
                        p5_desc = f"{cot_summary} — Neutral institutional positioning, no conflict detected."
                        p5_badge = "COT NEUTRAL"
                        p5_col = "#38bdf8"
                else:
                    # No directional signal — monitoring only
                    p5_ok = False
                    p5_status = "COT SENTIMENT MONITORING"
                    p5_desc = cot_summary
                    p5_badge = "MONITORING"
                    p5_col = "#9ca3af"
        elif has_cme:
            # CME Institutional Order Flow Proxy (Gold GC Futures & Commodities)
            cme_flow = float(cme.get('order_flow_score', 0.0))
            cme_bias = str(cme.get('bias', 'NEUTRAL')).upper()
            cme_summary = str(cme.get('summary', 'CME Gold Institutional Feed'))

            if is_dir_buy:
                if 'BULLISH' in cme_bias or cme_flow >= 15.0:
                    p5_ok = True
                    p5_status = "CME GOLD INSTITUTIONAL BUY ALIGNED"
                    p5_desc = f"{cme_summary} — CME Gold Futures institutional volume supports Buy."
                    p5_badge = "CME ALIGNED"
                    p5_col = "#00c853"
                elif 'BEARISH' in cme_bias or cme_flow <= -18.0:
                    p5_ok = False
                    p5_status = "CME GOLD INSTITUTIONAL CONFLICT"
                    p5_desc = f"{cme_summary} — CME Futures institutional selling opposes Buy."
                    p5_badge = "CME CONFLICT"
                    p5_col = "#ef4444"
                else:
                    p5_ok = True
                    p5_status = "CME GOLD NEUTRAL"
                    p5_desc = f"{cme_summary} — CME order flow neutral, no institutional conflict."
                    p5_badge = "CME NEUTRAL"
                    p5_col = "#38bdf8"
            elif is_dir_sell:
                if 'BEARISH' in cme_bias or cme_flow <= -15.0:
                    p5_ok = True
                    p5_status = "CME GOLD INSTITUTIONAL SELL ALIGNED"
                    p5_desc = f"{cme_summary} — CME Gold Futures institutional volume supports Sell."
                    p5_badge = "CME ALIGNED"
                    p5_col = "#ff1744"
                elif 'BULLISH' in cme_bias or cme_flow >= 18.0:
                    p5_ok = False
                    p5_status = "CME GOLD INSTITUTIONAL CONFLICT"
                    p5_desc = f"{cme_summary} — CME Futures institutional buying opposes Sell."
                    p5_badge = "CME CONFLICT"
                    p5_col = "#ef4444"
                else:
                    p5_ok = True
                    p5_status = "CME GOLD NEUTRAL"
                    p5_desc = f"{cme_summary} — CME order flow neutral, no institutional conflict."
                    p5_badge = "CME NEUTRAL"
                    p5_col = "#38bdf8"
            else:
                p5_ok = False
                p5_status = "CME MONITORING"
                p5_desc = cme_summary
                p5_badge = "MONITORING"
                p5_col = "#9ca3af"
        else:
            # Honest Labeling: Neither Futures, COT, nor CME available for this asset (Spot Altcoin)
            p5_available = False
            p5_ok = False
            p5_status = "WHALE FLOW N/A"
            p5_desc = "No institutional whale or derivatives order flow feed for this asset (Spot only)."
            p5_badge = "N/A"
            p5_col = "#6b7280"

        total_applicable = 5 if p5_available else 4
        aligned_count = sum([p1_ok, p2_ok, p3_ok, p4_ok, (p5_ok if p5_available else False)])
        is_fully_aligned = (aligned_count == total_applicable) and is_trade_active
        honest_label = f"{aligned_count}/{total_applicable} PILLARS ALIGNED" + (" (Whale Flow N/A)" if not p5_available else "")

        return {
            'is_fully_aligned': is_fully_aligned,
            'aligned_count': aligned_count,
            'total_applicable': total_applicable,
            'honest_label': honest_label,
            'is_trade_active': is_trade_active,
            'is_dir_buy': is_dir_buy,
            'is_dir_sell': is_dir_sell,
            'req_score': req_score,
            'req_prob': req_prob,
            'p1': {'ok': p1_ok, 'score': p1_score, 'prob': p1_prob, 'status': p1_status, 'desc': p1_desc, 'badge': p1_badge, 'col': p1_col},
            'p2': {'ok': p2_ok, 'bias': s1_bias, 'ema200': s1_200, 'status': p2_status, 'desc': p2_desc, 'badge': p2_badge, 'col': p2_col},
            'p3': {'ok': p3_ok, 'is_blackout': is_news_blackout, 'status': p3_status, 'desc': p3_desc, 'badge': p3_badge, 'col': p3_col},
            'p4': {'ok': p4_ok, 'is_overextended': is_overextended, 'status': p4_status, 'desc': p4_desc, 'badge': p4_badge, 'col': p4_col},
            'p5': {'available': p5_available, 'ok': p5_ok, 'status': p5_status, 'desc': p5_desc, 'badge': p5_badge, 'col': p5_col},
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

            # Auto breakeven check with institutional breakeven SL map & mode
            current_settings = self.load_settings()
            be_mode = current_settings.get('breakeven_mode', 'tight')
            be_map = {
                str(bid): float(binfo['breakeven_sl'])
                for bid, binfo in open_batches.items()
                if binfo.get('breakeven_sl')
            }
            be_results = self.executor.check_and_apply_auto_breakeven(
                batch_breakeven_sl_map=be_map,
                batch_info_map=open_batches,
                breakeven_mode=be_mode
            )
            if be_results:
                for b in be_results:
                    b_status = b.get('status', 'MOVED_TO_BREAKEVEN')
                    b_mode = b.get('mode', be_mode).upper()
                    logger.info(f"AUTO-BREAKEVEN ({b_mode}): Position #{b['ticket']} status: {b_status} -> New SL: {b['new_sl']}")

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
                    matched_deal_ids = set()
                    matched_deal_prices = []
                    broker_sym = str(trade.get('broker_sym', '')).lower()
                    batch_str_id = str(batch_id)

                    for d in deals:
                        if d.entry != 1:  # MT5 entry==1 indicates position exit/close deal
                            continue
                        deal_id = int(getattr(d, 'ticket', 0) or 0)
                        if deal_id in matched_deal_ids:
                            continue

                        deal_order = int(getattr(d, 'order', 0) or 0)
                        deal_pos_id = int(getattr(d, 'position_id', 0) or 0)
                        deal_comment = str(getattr(d, 'comment', ''))

                        # 1. Primary match: order ticket or position_id matches stored tickets (works for 1, 2, or 3 tickets)
                        direct_match = bool((deal_order and deal_order in batch_tickets) or (deal_pos_id and deal_pos_id in batch_tickets))
                        # 2. Comment tag match fallback: comment contains batch_id (e.g. QS_<batch_id>_)
                        comment_match = bool(f"_{batch_str_id}_" in deal_comment or f"QS_{batch_str_id}" in deal_comment)

                        if direct_match or comment_match:
                            # Full PnL accounting: profit + swap + commission
                            pnl_contrib = float(d.profit) + float(getattr(d, 'swap', 0.0) or 0.0) + float(getattr(d, 'commission', 0.0) or 0.0)
                            total_batch_profit += pnl_contrib
                            matched_deal_ids.add(deal_id)
                            matched_deal_prices.append(float(getattr(d, 'price', 0.0) or 0.0))

                    # Outcome Determination:
                    # Clear profit (> +$0.15) = WIN
                    # Breakeven SL triggered or minimal commission/spread friction (within +/- $0.60) = BREAKEVEN
                    # Otherwise = LOSS
                    be_sl = trade.get('breakeven_sl')
                    closed_near_be = False
                    if be_sl and be_sl > 0:
                        for d_p in matched_deal_prices:
                            if d_p > 0 and abs(d_p - be_sl) / be_sl < 0.002:  # within 0.2% of BE SL
                                closed_near_be = True
                                break

                    if total_batch_profit > 0.15:
                        outcome = 'WIN'
                    elif (abs(total_batch_profit) <= 0.60) or closed_near_be:
                        outcome = 'BREAKEVEN'
                    else:
                        outcome = 'LOSS'

                    logger.info(f"Batch #{batch_id} ({trade['symbol']}) Completed: {outcome} | PnL: ${total_batch_profit:+.2f} ({len(matched_deal_ids)} deals matched)")

                    # Global stats & Active Reinforcement Learning Loop
                    if outcome == 'WIN':
                        state['wins'] = state.get('wins', 0) + 1
                        # Adaptive reinforcement: On consistent wins, stabilize threshold towards Bayesian baseline 82%
                        opt = journal.get('optimal_adjustments', {})
                        if float(opt.get('min_calibrated_prob', 82.0)) > 82.0:
                            opt['min_calibrated_prob'] = round(max(72.0, float(opt.get('min_calibrated_prob', 82.0)) - 0.5), 1)
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
                        opt['min_calibrated_prob'] = round(min(92.0, float(opt.get('min_calibrated_prob', 82.0)) + 0.5), 1)
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

            # Historical deals are never injected into current live session stats.
            # Live session counters (wins/losses/symbol_stats) strictly reflect trades executed during this session.

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

        # Check Institutional Recommended Auto-Pilot Mode
        curr_settings = self.load_settings()
        is_rec_mode = bool(curr_settings.get('recommended_mode', False))
        rec_profile = RecommendedPresetsManager.get_profile_for_symbol(symbol) if is_rec_mode else None
        if is_rec_mode and not rec_profile:
            logger.info(f"Recommended Auto-Pilot: {symbol} is not in elite portfolio. Skipping scan.")
            return None

        found_setup = None
        open_batches = state.get('open_batches', {})

        # Recommended Auto-Pilot Strict Rule: Max 1 active batch per symbol across all timeframes
        if is_rec_mode:
            clean_sym = symbol.replace("/", "").replace("m", "").replace("M", "").upper()
            active_sym_batch = None
            for bid, binfo in open_batches.items():
                b_sym = binfo.get('symbol', '').replace("/", "").replace("m", "").replace("M", "").upper()
                b_broker = binfo.get('broker_sym', '').replace("/", "").replace("m", "").replace("M", "").upper()
                if b_sym == clean_sym or b_broker == clean_sym:
                    active_sym_batch = bid
                    break
            if active_sym_batch:
                logger.info(f"Recommended Auto-Pilot: Symbol {symbol} already has active batch #{active_sym_batch}. Skipping scan to prevent duplicate risk.")
                return None

        for tf in ordered_tfs:
            if is_rec_mode and rec_profile:
                # Silently skip timeframes that do not belong to this symbol's recommended profile
                if tf not in rec_profile.get('timeframes', []):
                    continue

            if _SCAN_STOP_EVENT.is_set() or not self.load_settings().get('enabled', False):
                logger.info(f"Stop signal detected. Aborting scan on {symbol}.")
                return None

            # Check duplicate position stacking on same (symbol, tf) unless allow_same_tf_trades is enabled
            allow_same_tf = False if is_rec_mode else bool(self.load_settings().get('allow_same_tf_trades', True))
            if not allow_same_tf:
                active_batch_id = None
                for bid, binfo in open_batches.items():
                    if binfo.get('symbol') == symbol and binfo.get('timeframe') == tf:
                        active_batch_id = bid
                        break

                if active_batch_id:
                    logger.info(f"Active batch #{active_batch_id} already running on {symbol} ({tf}). Advancing to next timeframe (same-TF stacking off).")
                    continue

            # Same-candle / execution cooldown guard (prevents rapid spam on the exact same candle)
            last_trade_times = state.get('last_trade_timestamps', {})
            last_t_iso = last_trade_times.get(f"{symbol}_{tf}")
            if last_t_iso:
                try:
                    last_t = datetime.fromisoformat(last_t_iso)
                    elapsed_sec = (datetime.now(timezone.utc) - last_t).total_seconds()
                    tf_sec_map = {'1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400}
                    min_cooldown = tf_sec_map.get(str(tf).lower(), 300)
                    if elapsed_sec < min_cooldown:
                        logger.info(f"Same-candle cooldown active for {symbol} ({tf}): {elapsed_sec:.0f}s elapsed < {min_cooldown}s required. Skipping.")
                        continue
                except Exception:
                    pass

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
                    market_mode='futures' if asset_type == 'crypto' else 'spot',
                    timeframe=tf,
                    preferred_exchange='Exness (MetaTrader 5)'
                )
                eval_res = self.evaluate_5_pillars(pred)
                p_cnt = eval_res['aligned_count']
                action = pred['confluence']['action']
                is_dir_buy = ('BUY' in action) and ('FILTER' not in action) and ('BLACKOUT' not in action) and ('CHOP' not in action)
                is_dir_sell = ('SELL' in action) and ('FILTER' not in action) and ('BLACKOUT' not in action) and ('CHOP' not in action)
                score = eval_res['p1']['score']
                prob = eval_res['p1']['prob']

                chop_gate = pred.get('chop_gate', {})
                is_chop = bool(chop_gate.get('is_chop', False))
                spread_guard = pred.get('spread_guard', {})
                is_spread_fail = bool(spread_guard and not spread_guard.get('passed', True))

                total_req = eval_res.get('total_applicable', 5)
                is_actionable = (is_dir_buy or is_dir_sell) and (not is_chop) and (not is_spread_fail)

                # 1. Market Session Filter (London / New York / Asian / 24-7)
                curr_settings = self.load_settings()
                if is_rec_mode and rec_profile:
                    active_sessions = rec_profile.get('active_sessions', ["London Session", "New York Session"])
                else:
                    active_sessions = curr_settings.get('active_sessions', ["London Session", "New York Session"])
                is_session_ok, session_desc = SessionManager.is_session_allowed(active_sessions)
                session_blocked = not is_session_ok
                if session_blocked:
                    is_actionable = False

                # 2. Higher Timeframe (HTF) Trend Confluence Filter
                htf_filter_enabled = bool(curr_settings.get('htf_filter_enabled', True))
                htf_conflict = False
                htf_detail = ""
                if htf_filter_enabled and is_actionable:
                    clean_dir = 'BUY' if 'BUY' in action else ('SELL' if 'SELL' in action else '')
                    if clean_dir:
                        is_htf_ok, htf_detail, _ = HTFConfluenceChecker.check_alignment(symbol, tf, clean_dir)
                        if not is_htf_ok:
                            htf_conflict = True
                            is_actionable = False

                # Micro Scalp (1m/3m/5m) Institutional Execution Gate:
                # 1. Macro Confirmation: Micro scalp must never contradict higher-timeframe 200 EMA bias (Pillar 2).
                # 2. Institutional Trigger on 1m/3m: Raw 1m/3m indicator entries are noise-dominated;
                #    require ICT Liquidity Sweep or FVG tap confirmation to prevent random walk entries.
                macro_conflict_scalp = False
                micro_noise_scalp = False
                if str(tf).lower() in ['1m', '3m', '5m']:
                    p2_info = eval_res.get('p2', {})
                    if not p2_info.get('ok', True) and 'CONFLICT' in str(p2_info.get('status', '')).upper():
                        macro_conflict_scalp = True
                        is_actionable = False

                    if str(tf).lower() in ['1m', '3m']:
                        quantum_data = pred.get('quantum_sniper', pred.get('alpha_sniper', {}).get('quantum_sniper', {}))
                        swp = quantum_data.get('liquidity_sweep', {})
                        swp_type = swp.get('sweep_type', 'NONE')
                        active_fvgs = pred.get('market_structure', {}).get('active_fvgs', []) or []
                        curr_p = float(pred.get('market_structure', {}).get('current_price', 0.0) or 0.0)
                        has_fvg_tap = any(float(f.get('bottom', 0)) <= curr_p <= float(f.get('top', 0)) for f in active_fvgs)
                        if swp_type == 'NONE' and not has_fvg_tap:
                            micro_noise_scalp = True
                            is_actionable = False

                # 4. Exhaustion & Anti-Falling-Knife Gate:
                # Do not SELL into deep oversold exhaustion (bear trap), do not BUY into blowoff tops (bull trap).
                ind_sum = pred.get('indicators_summary', {})
                rsi_val = float(ind_sum.get('rsi_14', 50.0))
                q_overext = pred.get('quantum_sniper', {}).get('overextension', {})
                is_q_over = bool(q_overext.get('is_overextended', False))
                q_dist_atr = float(q_overext.get('dist_atr', 0.0))

                exhaustion_conflict = False
                exhaustion_detail = ""
                if 'SELL' in action:
                    if rsi_val <= 30.0 and (is_q_over and q_dist_atr < -1.8):
                        exhaustion_conflict = True
                        exhaustion_detail = f"RSI oversold ({rsi_val:.1f}) & price {abs(q_dist_atr):.1f} ATR below EMA20 (Falling Knife / Bear Exhaustion)"
                        is_actionable = False
                elif 'BUY' in action:
                    if rsi_val >= 70.0 and (is_q_over and q_dist_atr > 1.8):
                        exhaustion_conflict = True
                        exhaustion_detail = f"RSI overbought ({rsi_val:.1f}) & price {q_dist_atr:.1f} ATR above EMA20 (Blowoff Top / Bull Exhaustion)"
                        is_actionable = False

                active_min_pillars = rec_profile.get('min_pillars', min_pillars_required) if (is_rec_mode and rec_profile) else min_pillars_required
                p1_info = eval_res.get('p1', {})
                p1_passed = bool(p1_info.get('ok', False))

                # Pillar 1 is the Non-Negotiable Master Alpha Gate: Must ALWAYS pass (Win Prob >= 80%, Confluence Score >= 35)
                # No trade can ever execute if Pillar 1 fails, regardless of other pillar counts.
                is_eligible = p1_passed and (p_cnt >= min(active_min_pillars, total_req)) and is_actionable

                pillar_str = f"{p_cnt}/{total_req}"

                if is_eligible:
                    status_lbl = f"🎯 {p_cnt}/{total_req} Aligned (Executing)"
                elif session_blocked:
                    status_lbl = "SKIPPED (Outside Trading Session)"
                elif htf_conflict:
                    status_lbl = "SKIPPED (HTF Trend Conflict)"
                elif not p1_passed and (is_dir_buy or is_dir_sell):
                    status_lbl = "SKIPPED (Pillar 1 Alpha Low Conviction)"
                elif macro_conflict_scalp:
                    status_lbl = "SKIPPED (Macro 200 EMA Conflict)"
                elif micro_noise_scalp:
                    status_lbl = "SKIPPED (No ICT Sweep / FVG)"
                elif exhaustion_conflict:
                    status_lbl = "SKIPPED (Exhaustion / Anti-Falling-Knife Gate)"
                elif is_chop:
                    status_lbl = "SKIPPED (Chop Gate)"
                elif is_spread_fail:
                    status_lbl = f"SKIPPED (Spread > {spread_guard.get('max_allowed_pct', 18):.0f}% TP1)"
                else:
                    status_lbl = f"No Trade (Waiting {min_pillars_required}/5)"

                detail_str = f"Score: {score:+.1f} | Win Prob: {prob:.0f}%"
                if session_blocked:
                    detail_str = f"SESSION FILTER: {session_desc}"
                elif htf_conflict:
                    detail_str = f"HTF FILTER: {htf_detail}"
                elif not p1_passed and (is_dir_buy or is_dir_sell):
                    detail_str = f"PILLAR 1 REJECTED: {p1_info.get('desc', 'Insufficient score or win probability')}"
                elif macro_conflict_scalp:
                    detail_str = f"MACRO CONFLICT: Scalp opposes 200 EMA trend"
                elif micro_noise_scalp:
                    detail_str = f"MICRO NOISE FILTER: 1m/3m entries strictly require ICT Liquidity Sweep or FVG tap"
                elif exhaustion_conflict:
                    detail_str = f"EXHAUSTION GATE: {exhaustion_detail}"
                elif is_chop:
                    detail_str = f"CHOP: {chop_gate.get('reason', '')[:45]}"
                elif is_spread_fail:
                    detail_str = f"Spread: ${spread_guard.get('spread_price')} ({spread_guard.get('spread_to_target_pct')}%) > {spread_guard.get('max_allowed_pct', 18):.0f}%"

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
                        'matched_pillars': p_cnt,
                        'recommended_profile': rec_profile if (is_rec_mode and rec_profile) else None
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

            soft_breakeven_sl = float(setup.get('soft_breakeven_sl') or 0.0)
            if soft_breakeven_sl <= 0:
                atr = float(pred.get('market_data', {}).get('atr') or (abs(entry_price - sl_price) / 1.8))
                if action == 'BUY':
                    soft_breakeven_sl = entry_price - (0.45 * atr)
                else:
                    soft_breakeven_sl = entry_price + (0.45 * atr)
            soft_breakeven_sl = round(soft_breakeven_sl, 5)

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

                if 'last_trade_timestamps' not in state:
                    state['last_trade_timestamps'] = {}
                state['last_trade_timestamps'][f"{symbol}_{tf}"] = datetime.now(timezone.utc).isoformat()

                rec_profile = setup_data.get('recommended_profile')
                active_be_mode = rec_profile.get('breakeven_mode') if rec_profile else self.load_settings().get('breakeven_mode', 'tight')
                active_sess_used = rec_profile.get('active_sessions') if rec_profile else self.load_settings().get('active_sessions', ["London Session", "New York Session"])

                state['open_batches'][str(batch_id)] = {
                    'batch_id': batch_id,
                    'symbol': symbol,
                    'broker_sym': broker_sym,
                    'timeframe': tf,
                    'action': action,
                    'entry_price': entry_price,
                    'sl_price': sl_price,
                    'breakeven_sl': breakeven_sl,
                    'soft_breakeven_sl': soft_breakeven_sl,
                    'breakeven_mode': active_be_mode,
                    'recommended_mode': bool(rec_profile is not None),
                    'active_sessions': active_sess_used,
                    'htf_confluence': bool(self.load_settings().get('htf_filter_enabled', True)),
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
