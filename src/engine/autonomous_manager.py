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

AVAILABLE_STRATEGIES = {
    "DEFAULT": "🏛️ Institutional Core (5-Pillars Confluence & AlphaSniper)",
    "VIVEK_YADAV": "🎯 Vivek Yadav (Trade For Profit - S&D + Liquidation)",
    "BERND_SKORUPINSKI": "🏆 Bernd Skorupinski (FTMO #1 - Multi-Timeframe S&D)",
    "ICT": "⚡ Michael J. Huddleston (ICT - Liquidity Sweep + MSS + FVG/OTE)",
    "STEVEN_HART": "📐 Steven Hart (The Trading Channel - 4H Break & 15M Retest)",
    "RAYNER_TEO": "🌊 Rayner Teo (Trend Following 20/50 EMA Envelope + 20 EMA Trailing)",
    "CRYPTO_CRED": "📊 Crypto Cred (Key Levels S/R + 20/50 EMA + RSI Divergence)",
    "NDEMAZEAH_GODLOVE": "🎯 Ndemazeah Godlove (GU MVR - 10/23 EMA Cross + Fib 50-61.8%)",
    "ROSS_CAMERON": "🚀 Ross Cameron (Warrior Trading Momentum & VWAP)",
    "ADAM_KHOO": "📈 Adam Khoo (Triple EMA Trend Breakout & 20 EMA Trailing)",
    "ARIEL_ZWECHER": "⏰ Ariel Zwecher (RealSimpleAriel - 15M ORB & Prop Math)",
    "OLIVER_VELEZ": "🐘 Oliver Velez (Elephant/Tail Bar + 20 SMA Location + 200 SMA Baseline)",
    "TRADE_PRO": "🤖 Trade Pro (Mechanical Donchian 20 Channel + 200 SMA Slope + ATR 1:2)",
    # 6 New Elite Traders from Playbook PDF:
    "KRISTJAN_QULLAMAGGIE": "🌪️ Kristjan Qullamaggie (Systematic Momentum Expansion & High ADR%)",
    "GCR": "🧠 GCR (@GiganticRebirth - Behavioral Sentiment & Counter-Shorting)",
    "WAQAR_ZAKA": "🛡️ Waqar Zaka (Off-Exchange Capital Reserve & ATR Buffer Model)",
    "WAQAR_ASIM": "🎯 Waqar Asim (Forex 1M S&D Inducement Scalping Model)",
    "EUGENE_NG_AH_SIO": "⚖️ Eugene Ng Ah Sio (Relative Value Delta-Neutral Spreads)",
    "PAUL_FTMO": "👑 Paul (Record FTMO Leaderboard Trader - Macro & Divergence)"
}

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
    def _is_strat_session_allowed(strategy_key: str, generic_allowed_sessions: Optional[List[str]] = None, asset_type: str = 'forex'):
        global SessionManager
        if not hasattr(SessionManager, 'is_strategy_session_allowed'):
            try:
                import importlib
                import src.engine.session_manager
                importlib.reload(src.engine.session_manager)
                from src.engine.session_manager import SessionManager as _SM
                SessionManager = _SM
            except Exception:
                pass
        if hasattr(SessionManager, 'is_strategy_session_allowed'):
            return SessionManager.is_strategy_session_allowed(
                strategy_key=strategy_key,
                generic_allowed_sessions=generic_allowed_sessions,
                asset_type=asset_type
            )
        return SessionManager.is_session_allowed(generic_allowed_sessions or ["24/7 (Any Session)"])

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
            "allow_diff_strat_same_tf": False,  # Allow multi-trades on same TF ONLY from DIFFERENT strategies (same strategy cannot duplicate)
            "breakeven_mode": "tight",          # "tight" (immediate 0.38 ATR lock) | "loose" (2-stage runner breathing room)
            "active_sessions": ["London Session", "New York Session"], # Allowed trading sessions
            "htf_filter_enabled": True,         # Higher Timeframe Trend Confluence filter
            "recommended_mode": False,          # Institutional Recommended Auto-Pilot (per-pair backtested optimum)
            "active_strategy_mode": "DEFAULT",  # Legacy single-choice fallback
            "active_strategies": ["DEFAULT"]    # Multi-Select Strategy List
        }
        with _STATE_LOCK:
            if os.path.exists(SETTINGS_FILE):
                try:
                    with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Migrate legacy active_strategy_mode if active_strategies not set
                        if 'active_strategies' not in data or not data['active_strategies']:
                            old_m = str(data.get('active_strategy_mode', 'DEFAULT')).upper().strip()
                            if old_m in ['TFP_LIQUIDATION_TRAP', 'VIVEK_YADAV_SD', 'BOTH_TFP']:
                                data['active_strategies'] = ['VIVEK_YADAV']
                            elif old_m == 'ALL_STRATEGIES':
                                data['active_strategies'] = list(AVAILABLE_STRATEGIES.keys())
                            else:
                                data['active_strategies'] = ['DEFAULT']
                        elif set(data.get('active_strategies', [])) == {
                            "DEFAULT", "STEVEN_HART", "RAYNER_TEO", "ICT", "BERND_SKORUPINSKI",
                            "VIVEK_YADAV", "CRYPTO_CRED", "NDEMAZEAH_GODLOVE", "ROSS_CAMERON",
                            "ADAM_KHOO", "ARIEL_ZWECHER", "OLIVER_VELEZ", "TRADE_PRO"
                        }:
                            data['active_strategies'] = list(AVAILABLE_STRATEGIES.keys())
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

    @classmethod
    def compute_strategy_leaderboard(
        cls,
        state: Optional[Dict[str, Any]] = None,
        sort_by: str = 'profit'
    ) -> List[Dict[str, Any]]:
        """
        Computes performance metrics and dynamic ranking for all 13 strategies
        (Institutional Core DEFAULT + 12 Streamers) across closed and open batches.

        sort_by options:
        - 'profit' / 'pnl': Net PnL ($) descending
        - 'wins': Total wins descending
        - 'losses': Total losses descending
        - 'breakevens': Total breakevens descending
        - 'win_rate': Win Rate (%) descending
        - 'total_trades': Total volume (trades taken) descending
        """
        if state is None:
            state = cls.load_state()

        closed_batches = state.get('closed_batches', [])
        open_batches = list(state.get('open_batches', {}).values())

        reset_at_str = state.get('reset_at')
        if reset_at_str:
            try:
                reset_dt = datetime.fromisoformat(reset_at_str)
                closed_batches = [
                    b for b in closed_batches
                    if b.get('executed_at') and datetime.fromisoformat(b.get('executed_at')) >= reset_dt
                ]
                open_batches = [
                    b for b in open_batches
                    if b.get('executed_at') and datetime.fromisoformat(b.get('executed_at')) >= reset_dt
                ]
            except Exception:
                pass

        # Strategy Playbook Native Profiles (from Complete Rule-Based Playbook PDF)
        playbook_profiles = {
            'DEFAULT': {'default_tfs': '15m, 30m, 1h', 'default_pairs': 'XAU/USD, BTC/USD'},
            'VIVEK_YADAV': {'default_tfs': '15m, 5m, 1m', 'default_pairs': 'BTC/USD, ETH/USD, Gold'},
            'BERND_SKORUPINSKI': {'default_tfs': '4h, 1h, 15m', 'default_pairs': 'EUR/USD, GBP/USD, Gold'},
            'ICT': {'default_tfs': '15m, 5m, 1m', 'default_pairs': 'NQ, ES, EUR/USD, BTC'},
            'STEVEN_HART': {'default_tfs': '15m, 1h, 4h', 'default_pairs': 'EUR/USD, GBP/USD, Gold'},
            'RAYNER_TEO': {'default_tfs': '4h, 1h, Daily', 'default_pairs': 'Forex, Gold, Indices'},
            'CRYPTO_CRED': {'default_tfs': '1h, 4h, 15m', 'default_pairs': 'BTC/USD, ETH/USD'},
            'NDEMAZEAH_GODLOVE': {'default_tfs': '15m, 5m', 'default_pairs': 'GBP/USD, NQ, ES'},
            'ROSS_CAMERON': {'default_tfs': '1m, 5m', 'default_pairs': 'BTC/USD, High-Beta'},
            'ADAM_KHOO': {'default_tfs': '1h, 4h, 15m', 'default_pairs': 'BTC/USD, Forex, Equities'},
            'ARIEL_ZWECHER': {'default_tfs': '15m, 5m', 'default_pairs': 'BTC/USD, CME Futures'},
            'OLIVER_VELEZ': {'default_tfs': '2m, 5m, 15m', 'default_pairs': 'Crypto, Futures, Equities'},
            'TRADE_PRO': {'default_tfs': '1h, 4h, 15m', 'default_pairs': 'Forex Majors, Crypto'},
            'KRISTJAN_QULLAMAGGIE': {'default_tfs': 'Daily, 1h', 'default_pairs': 'Crypto, Altcoins, Stocks'},
            'GCR': {'default_tfs': '1h, 4h, Daily', 'default_pairs': 'BTC/USD, ETH/USD, High-Caps'},
            'WAQAR_ZAKA': {'default_tfs': '15m, 1h, 4h', 'default_pairs': 'BTC/USD, ETH/USD, Perps'},
            'WAQAR_ASIM': {'default_tfs': '1m, 1h', 'default_pairs': 'EUR/USD, GBP/USD'},
            'EUGENE_NG_AH_SIO': {'default_tfs': '1h, 4h, Daily', 'default_pairs': 'Crypto Spot & Perps'},
            'PAUL_FTMO': {'default_tfs': '15m, 5m, 1h, 4h', 'default_pairs': 'EUR/JPY, GBP/JPY, EUR/USD, S&P 500'}
        }

        # Initialize stats bucket for each of the strategies
        stats_map: Dict[str, Dict[str, Any]] = {}
        strat_tfs: Dict[str, Dict[str, Dict[str, Any]]] = {k: {} for k in AVAILABLE_STRATEGIES}
        strat_pairs: Dict[str, Dict[str, Dict[str, Any]]] = {k: {} for k in AVAILABLE_STRATEGIES}

        for strat_key, strat_full_name in AVAILABLE_STRATEGIES.items():
            stats_map[strat_key] = {
                'strategy_key': strat_key,
                'strategy_name': strat_full_name,
                'name': strat_full_name,
                'total_trades': 0,
                'closed_trades': 0,
                'active_trades': 0,
                'wins': 0,
                'losses': 0,
                'breakevens': 0,
                'win_rate': 0.0,
                'net_pnl': 0.0,
                'net_loss': 0.0,
                'gross_profit': 0.0,
                'gross_loss': 0.0,
                'profit_factor': 0.0,
                'biggest_sl_loss': 0.0,
                'sl_hits': 0,
                'tp_hits': 0,
                'biggest_tp': 0.0,
                'status_badge': '💤 NO TRADES',
                'best_timeframes': playbook_profiles.get(strat_key, {}).get('default_tfs', '15m, 1h'),
                'best_pairs': playbook_profiles.get(strat_key, {}).get('default_pairs', 'BTC/USD, Gold')
            }

        # Build batch-to-strategy lookup from scan_activity_log for recovered sync batches
        log_strategy_map = {}
        for entry in state.get('scan_activity_log', []):
            det = str(entry.get('details', ''))
            stt = str(entry.get('status', ''))
            if 'Batch #' in stt:
                try:
                    bid = str(stt.split('Batch #')[1].split(')')[0].strip())
                    for k, fname in AVAILABLE_STRATEGIES.items():
                        clean_fn = fname.split('(')[0].replace('🏛️', '').replace('🎯', '').replace('🏆', '').replace('⚡', '').replace('📐', '').replace('🌊', '').replace('📊', '').replace('🚀', '').replace('📈', '').replace('⏰', '').replace('🐘', '').replace('🤖', '').replace('🌪️', '').replace('🧠', '').replace('🛡️', '').replace('⚖️', '').replace('👑', '').strip().upper()
                        if k in det.upper() or (len(clean_fn) > 3 and clean_fn in det.upper()):
                            log_strategy_map[bid] = k
                            break
                except Exception:
                    pass

        def match_strategy_key(batch: Dict[str, Any]) -> str:
            bid = str(batch.get('batch_id', '')).strip()
            if bid in log_strategy_map:
                return log_strategy_map[bid]

            raw_k = str(batch.get('strategy_used', '')).upper()
            raw_n = str(batch.get('strategy_name', '')).upper()

            # Exact match on key
            if raw_k in stats_map:
                return raw_k

            # Heuristics for name or aliases
            for k in AVAILABLE_STRATEGIES:
                if k in raw_k or k in raw_n:
                    return k

            if 'PAUL' in raw_k or 'PAUL' in raw_n:
                return 'PAUL_FTMO'
            if 'VIVEK' in raw_k or 'VIVEK' in raw_n or 'TFP' in raw_k or 'TFP' in raw_n:
                return 'VIVEK_YADAV'
            if 'BERND' in raw_k or 'BERND' in raw_n or 'SKORUPINSKI' in raw_n:
                return 'BERND_SKORUPINSKI'
            if 'HUDDLESTON' in raw_n or 'ICT' in raw_k or 'ICT' in raw_n:
                return 'ICT'
            if 'STEVEN' in raw_k or 'STEVEN' in raw_n:
                return 'STEVEN_HART'
            if 'RAYNER' in raw_k or 'RAYNER' in raw_n:
                return 'RAYNER_TEO'
            if 'CRED' in raw_k or 'CRED' in raw_n:
                return 'CRYPTO_CRED'
            if 'NDEMAZEAH' in raw_k or 'NDEMAZEAH' in raw_n or 'MVR' in raw_n:
                return 'NDEMAZEAH_GODLOVE'
            if 'ROSS' in raw_k or 'ROSS' in raw_n or 'WARRIOR' in raw_n:
                return 'ROSS_CAMERON'
            if 'ADAM' in raw_k or 'ADAM' in raw_n or 'KHOO' in raw_n:
                return 'ADAM_KHOO'
            if 'ARIEL' in raw_k or 'ARIEL' in raw_n or 'ORB' in raw_n:
                return 'ARIEL_ZWECHER'
            if 'VELEZ' in raw_k or 'VELEZ' in raw_n:
                return 'OLIVER_VELEZ'
            if 'PRO' in raw_k or 'PRO' in raw_n or 'DONCHIAN' in raw_n:
                return 'TRADE_PRO'
            if 'QULLAMAGGIE' in raw_k or 'QULLAMAGGIE' in raw_n or 'KRISTJAN' in raw_k or 'KRISTJAN' in raw_n:
                return 'KRISTJAN_QULLAMAGGIE'
            if 'GCR' in raw_k or 'GCR' in raw_n or 'GIGANTICREBIRTH' in raw_n:
                return 'GCR'
            if 'ZAKA' in raw_k or 'ZAKA' in raw_n:
                return 'WAQAR_ZAKA'
            if 'ASIM' in raw_k or 'ASIM' in raw_n:
                return 'WAQAR_ASIM'
            if 'EUGENE' in raw_k or 'EUGENE' in raw_n or 'AH SIO' in raw_n or 'DELTA_NEUTRAL' in raw_n:
                return 'EUGENE_NG_AH_SIO'
            
            return 'DEFAULT'

        # Helper to normalize symbol string
        def normalize_sym_str(s: str) -> str:
            raw = str(s or '').strip()
            if not raw or raw in ['-', 'none', 'None']:
                return ''
            if '/' in raw:
                return raw
            if raw.endswith('m') and len(raw) in [7, 8]:
                raw = raw[:-1]
            if len(raw) == 6:
                return f"{raw[:3]}/{raw[3:]}"
            return raw

        # Process Closed Batches
        for b in closed_batches:
            k = match_strategy_key(b)
            pnl = float(b.get('profit', 0.0))
            status = str(b.get('status', '')).upper()
            tf = str(b.get('timeframe', '')).strip().lower()
            sym = normalize_sym_str(b.get('symbol', ''))
            exit_r = str(b.get('exit_reason', '')).upper()

            stats_map[k]['total_trades'] += 1
            stats_map[k]['closed_trades'] += 1
            stats_map[k]['net_pnl'] += pnl

            # Prioritize BREAKEVEN check: status marked BREAKEVEN, 'BE', or minor commission/spread slip
            is_be = (
                'BREAKEVEN' in status or 
                status == 'BE' or 
                b.get('is_breakeven', False) or 
                (abs(pnl) <= 0.15 and status not in ['WIN', 'LOSS'])
            )

            if is_be:
                stats_map[k]['breakevens'] += 1
                if pnl > 0:
                    stats_map[k]['gross_profit'] += pnl
                elif pnl < 0:
                    stats_map[k]['gross_loss'] += abs(pnl)
            elif status == 'WIN' or pnl > 0.15:
                stats_map[k]['wins'] += 1
                stats_map[k]['gross_profit'] += pnl
                # Track TP hits from exit_reason
                if 'TP' in exit_r:
                    stats_map[k]['tp_hits'] += 1
                # Biggest TP win
                if pnl > stats_map[k]['biggest_tp']:
                    stats_map[k]['biggest_tp'] = round(pnl, 2)
            elif status == 'LOSS' or pnl < -0.15:
                stats_map[k]['losses'] += 1
                stats_map[k]['sl_hits'] += 1
                stats_map[k]['gross_loss'] += abs(pnl)
                stats_map[k]['net_loss'] += pnl  # negative value
                loss_amt = abs(pnl)
                if loss_amt > stats_map[k]['biggest_sl_loss']:
                    stats_map[k]['biggest_sl_loss'] = round(loss_amt, 2)
            else:
                stats_map[k]['breakevens'] += 1

            # Track per-timeframe metrics
            if tf and tf not in ['-', 'live', 'none']:
                if tf not in strat_tfs[k]:
                    strat_tfs[k][tf] = {'trades': 0, 'wins': 0, 'pnl': 0.0}
                strat_tfs[k][tf]['trades'] += 1
                strat_tfs[k][tf]['pnl'] += pnl
                if status == 'WIN' or pnl > 0.15:
                    strat_tfs[k][tf]['wins'] += 1

            # Track per-symbol metrics
            if sym:
                if sym not in strat_pairs[k]:
                    strat_pairs[k][sym] = {'trades': 0, 'wins': 0, 'pnl': 0.0}
                strat_pairs[k][sym]['trades'] += 1
                strat_pairs[k][sym]['pnl'] += pnl
                if status == 'WIN' or pnl > 0.15:
                    strat_pairs[k][sym]['wins'] += 1

        # Process Open Batches
        for b in open_batches:
            k = match_strategy_key(b)
            tf = str(b.get('timeframe', '')).strip().lower()
            sym = normalize_sym_str(b.get('symbol', ''))

            stats_map[k]['total_trades'] += 1
            stats_map[k]['active_trades'] += 1

            if tf and tf not in ['-', 'live', 'none']:
                if tf not in strat_tfs[k]:
                    strat_tfs[k][tf] = {'trades': 0, 'wins': 0, 'pnl': 0.0}
                strat_tfs[k][tf]['trades'] += 1

            if sym:
                if sym not in strat_pairs[k]:
                    strat_pairs[k][sym] = {'trades': 0, 'wins': 0, 'pnl': 0.0}
                strat_pairs[k][sym]['trades'] += 1

        # Calculate Derived Metrics & Health Status
        leaderboard = []
        for k, item in stats_map.items():
            wins = item['wins']
            losses = item['losses']
            bes = item['breakevens']
            closed = item['closed_trades']
            net_pnl = round(item['net_pnl'], 2)
            item['net_pnl'] = net_pnl
            item['net_loss'] = round(item['net_loss'], 2)
            item['biggest_tp'] = round(item['biggest_tp'], 2)
            item['tp_hits'] = int(item['tp_hits'])

            # Win Rate Calculation (decisive trades + capital protection)
            decisive_trades = wins + losses
            if decisive_trades > 0:
                item['win_rate'] = round((wins / decisive_trades) * 100.0, 1)
            elif closed > 0 and bes > 0:
                item['win_rate'] = 50.0  # 100% Breakeven capital preserved
            else:
                item['win_rate'] = 0.0

            # Profit Factor Calculation
            gross_loss = item['gross_loss']
            if gross_loss > 0:
                item['profit_factor'] = round(item['gross_profit'] / gross_loss, 2)
            elif item['gross_profit'] > 0:
                item['profit_factor'] = 99.9  # Undefeated infinite PF
            else:
                item['profit_factor'] = 0.0

            # Synthesize Best Timeframes
            pb_entry = playbook_profiles.get(k, {})
            t_items = sorted(
                strat_tfs[k].items(),
                key=lambda x: (x[1]['wins'], x[1]['pnl'], x[1]['trades']),
                reverse=True
            )
            if t_items:
                top_tfs = [t[0] for t in t_items[:2]]
                item['best_timeframes'] = ', '.join(top_tfs)
            else:
                item['best_timeframes'] = pb_entry.get('default_tfs', '15m, 1h')

            # Synthesize Best Trading Pairs
            p_items = sorted(
                strat_pairs[k].items(),
                key=lambda x: (x[1]['wins'], x[1]['pnl'], x[1]['trades']),
                reverse=True
            )
            if p_items:
                top_pairs = [p[0] for p in p_items[:2]]
                item['best_pairs'] = ', '.join(top_pairs)
            else:
                item['best_pairs'] = pb_entry.get('default_pairs', 'BTC/USD, Gold')

            # Dynamic Status Badge
            if item['total_trades'] == 0:
                item['status_badge'] = '💤 Awaiting Fills'
            elif net_pnl > 0 and item['win_rate'] >= 75.0:
                item['status_badge'] = '🔥 Elite Performer'
            elif net_pnl > 0:
                item['status_badge'] = '🟢 Profitable'
            elif bes > 0 and losses == 0:
                item['status_badge'] = f'🛡️ Capital Guard ({bes} BE)'
            elif net_pnl < 0:
                item['status_badge'] = '🔴 Drawdown'
            else:
                item['status_badge'] = '⚖️ Neutral'

            leaderboard.append(item)

        # Sorting Logic
        sort_key = str(sort_by).lower().strip()
        if sort_key in ['wins', 'most_wins']:
            leaderboard.sort(key=lambda x: (x['wins'], x['win_rate'], x['net_pnl']), reverse=True)
        elif sort_key in ['losses', 'most_losses']:
            leaderboard.sort(key=lambda x: (x['losses'], -x['win_rate']), reverse=True)
        elif sort_key in ['breakevens', 'most_breakevens', 'be']:
            leaderboard.sort(key=lambda x: (x['breakevens'], x['total_trades']), reverse=True)
        elif sort_key in ['win_rate', 'highest_win_rate', 'winrate']:
            leaderboard.sort(key=lambda x: (x['win_rate'], x['wins'], x['net_pnl']), reverse=True)
        elif sort_key in ['total_trades', 'most_active', 'volume']:
            leaderboard.sort(key=lambda x: (x['total_trades'], x['net_pnl']), reverse=True)
        elif sort_key in ['biggest_sl_loss', 'biggest_sl', 'max_loss']:
            leaderboard.sort(key=lambda x: (x['biggest_sl_loss'], x['losses']), reverse=True)
        elif sort_key in ['sl_hits', 'most_sl_hits']:
            leaderboard.sort(key=lambda x: (x['sl_hits'], x['biggest_sl_loss']), reverse=True)
        elif sort_key in ['tp_hits', 'most_tp_hits']:
            leaderboard.sort(key=lambda x: (x['tp_hits'], x['biggest_tp']), reverse=True)
        elif sort_key in ['biggest_tp', 'max_tp']:
            leaderboard.sort(key=lambda x: (x['biggest_tp'], x['tp_hits']), reverse=True)
        else: # Default: 'profit' / Most Profitable
            leaderboard.sort(key=lambda x: (x['net_pnl'], x['win_rate'], x['wins']), reverse=True)

        # Assign Dynamic Ranks 1 to 13
        for idx, item in enumerate(leaderboard, start=1):
            item['rank'] = idx
            if idx == 1:
                item['rank_display'] = '🥇 1'
            elif idx == 2:
                item['rank_display'] = '🥈 2'
            elif idx == 3:
                item['rank_display'] = '🥉 3'
            else:
                item['rank_display'] = f'#{idx}'

        return leaderboard


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
        state["eth_trades_taken"] = 0
        for k in list(state.keys()):
            if k.endswith('_trades_taken'):
                state[k] = 0
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
        p4_ok = False
        if is_overextended:
            p4_ok = False
            p4_status = "OVEREXTENDED (ANTI-CHASE ACTIVE)"
            p4_desc = "Price extended >2.2 ATR from EMA 20. High mean-reversion exhaustion risk."
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

            reset_at_ts = None
            if reset_at:
                try:
                    reset_at_ts = datetime.fromisoformat(reset_at).timestamp()
                except Exception:
                    pass

            # Self-healing: Adopt any unlinked MT5 positions into open_batches so they are never orphaned
            if open_pos:
                for p in open_pos:
                    # Ignore positions opened before the latest system reset
                    if reset_at_ts is not None and getattr(p, 'time', 0) < reset_at_ts:
                        continue
                    if getattr(p, 'magic', 0) == self.executor.MAGIC_NUMBER or 'QS_' in str(getattr(p, 'comment', '')):
                        cmt = str(getattr(p, 'comment', ''))
                        pos_batch = None
                        pos_tf = None
                        pos_strat_code = None

                        if 'QS_' in cmt:
                            parts = cmt.split('_')
                            if len(parts) >= 2:
                                pos_batch = parts[1]
                            if len(parts) >= 3 and any(t in parts[2].lower() for t in ['m', 'h', 'd']):
                                pos_tf = parts[2].lower()

                        if not pos_batch:
                            pos_batch = str(p.ticket)

                        if str(pos_batch) not in open_batches:
                            p_type = 'BUY' if p.type == 0 else 'SELL'
                            norm_s = self.normalize_symbol(p.symbol)

                            # Recover timeframe from recent activity feed if not in comment
                            if not pos_tf:
                                for entry in state.get('scan_activity_log', []):
                                    e_sym = self.normalize_symbol(entry.get('symbol', ''))
                                    e_tf = entry.get('timeframe')
                                    if e_sym == norm_s and e_tf and e_tf not in ['-', 'Live']:
                                        pos_tf = e_tf
                                        break
                            if not pos_tf:
                                pos_tf = "15m"  # Standard default execution timeframe

                            # Recover strategy name from activity feed
                            resolved_strat_name = "Streamer Strategy (MT5 Sync)"
                            resolved_strat_key = "STREAMER"
                            for entry in state.get('scan_activity_log', []):
                                e_sym = self.normalize_symbol(entry.get('symbol', ''))
                                det = str(entry.get('details', ''))
                                if e_sym == norm_s and 'Strategy:' in det:
                                    try:
                                        resolved_strat_name = det.split('Strategy:')[1].split('|')[0].strip()
                                        resolved_strat_key = entry.get('status', '').replace('🎯 Executing (', '').replace(')', '').strip() or 'STREAMER'
                                        break
                                    except Exception:
                                        pass

                            open_batches[str(pos_batch)] = {
                                'batch_id': pos_batch,
                                'symbol': norm_s,
                                'broker_sym': p.symbol,
                                'timeframe': pos_tf,
                                'action': p_type,
                                'entry_price': float(p.price_open),
                                'sl_price': float(p.sl),
                                'breakeven_sl': float(p.price_open),
                                'soft_breakeven_sl': float(p.sl),
                                'breakeven_mode': be_mode,
                                'recommended_mode': False,
                                'active_sessions': current_settings.get('active_sessions', []),
                                'htf_confluence': True,
                                'tp1_price': float(p.tp),
                                'tp2_price': float(p.tp),
                                'tp3_price': float(p.tp),
                                'matched_pillars': 5,
                                'lot_split': {'tp1_lots': float(p.volume)},
                                'risk_usd': 0.0,
                                'tickets': [int(p.ticket)],
                                'executed_at': datetime.now(timezone.utc).isoformat(),
                                'status': 'OPEN',
                                'p1_score': 0.0,
                                'p1_prob': 85.0,
                                'strategy_used': resolved_strat_key,
                                'strategy_name': resolved_strat_name
                            }

                            # Update symbol trade counts
                            if 'trades_by_symbol' not in state:
                                state['trades_by_symbol'] = {}
                            state['trades_by_symbol'][norm_s] = state['trades_by_symbol'].get(norm_s, 0) + 1
                            if p.symbol != norm_s:
                                state['trades_by_symbol'][p.symbol] = state['trades_by_symbol'].get(p.symbol, 0) + 1
                            state['total_trades_taken'] = state.get('total_trades_taken', 0) + 1
                            state_changed = True
                        else:
                            tkts = open_batches[str(pos_batch)].get('tickets', [])
                            if int(p.ticket) not in tkts:
                                tkts.append(int(p.ticket))
                                open_batches[str(pos_batch)]['tickets'] = tkts
                                state_changed = True

            # Check open batches for completion
            for batch_id, trade in list(open_batches.items()):
                batch_tickets = set(trade.get('tickets', []))
                active_in_batch = batch_tickets.intersection(open_tickets)
                if not active_in_batch and deals:
                    total_batch_profit = 0.0
                    matched_deal_ids = set()
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

                    # Dynamic outcome classification:
                    # Clear profit (> +$0.15) = WIN
                    # Clear loss (< -$0.15) = LOSS
                    # Minimal dust/scratch (within +/- $0.15) = BREAKEVEN
                    if total_batch_profit > 0.15:
                        outcome = 'WIN'
                    elif total_batch_profit < -0.15:
                        outcome = 'LOSS'
                    else:
                        outcome = 'BREAKEVEN'

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
                        'p1_prob': trade.get('p1_prob'),
                        'strategy_used': trade.get('strategy_used', 'DEFAULT_CONFLUENCE'),
                        'strategy_name': trade.get('strategy_name', 'Default Confluence (5-Pillars)')
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
                state['open_batches'] = open_batches
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

        for tf in ordered_tfs:
            if is_rec_mode and rec_profile:
                # Silently skip timeframes that do not belong to this symbol's recommended profile
                if tf not in rec_profile.get('timeframes', []):
                    continue

            if _SCAN_STOP_EVENT.is_set() or not self.load_settings().get('enabled', False):
                logger.info(f"Stop signal detected. Aborting scan on {symbol}.")
                return None

            # Check duplicate position stacking on same (symbol, tf)
            allow_same_tf = bool(curr_settings.get('allow_same_tf_trades', True))
            allow_diff_strat = bool(curr_settings.get('allow_diff_strat_same_tf', False))

            norm_sym = self.normalize_symbol(symbol)
            running_strats_on_tf = set()
            active_batch_ids_on_tf = []
            for bid, binfo in open_batches.items():
                b_sym = self.normalize_symbol(binfo.get('symbol', ''))
                b_tf = str(binfo.get('timeframe', '')).lower()
                if (b_sym == norm_sym or norm_sym.replace('/', '') in str(binfo.get('broker_sym', '')).replace('/', '')) and b_tf == str(tf).lower():
                    running_strats_on_tf.add(binfo.get('strategy_used', 'DEFAULT'))
                    active_batch_ids_on_tf.append(bid)

            # If multi-trades on same TF are completely disabled (both allow_same_tf and allow_diff_strat are False)
            if not allow_same_tf and not allow_diff_strat:
                if active_batch_ids_on_tf:
                    logger.info(f"Active batch #{active_batch_ids_on_tf[0]} already running on {symbol} ({tf}). Advancing to next timeframe (same-TF trades disabled).")
                    self._append_activity_log({
                        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                        "cycle": cycle,
                        "symbol": symbol,
                        "timeframe": tf,
                        "action": "HOLD",
                        "pillars": "-",
                        "status": "SKIPPED (Active Batch on TF)",
                        "details": f"Batch #{active_batch_ids_on_tf[0]} already open on {symbol} ({tf}) (Same-TF trades disabled)"
                    })
                    continue

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
                score = eval_res['p1']['score']
                prob = eval_res['p1']['prob']

                chop_gate = pred.get('chop_gate', {})
                is_chop = bool(chop_gate.get('is_chop', False))
                spread_guard = pred.get('spread_guard', {})
                is_spread_fail = bool(spread_guard and not spread_guard.get('passed', True))

                total_req = eval_res.get('total_applicable', 5)
                is_actionable = ('BUY' in action or 'SELL' in action) and ('FILTER' not in action) and ('BLACKOUT' not in action) and ('CHOP' not in action) and (not is_chop) and (not is_spread_fail)

                # 1. Market Session Filter (London / New York / Asian / 24-7)
                curr_settings = self.load_settings()
                # Resolve active strategies list (multi-select)
                active_strats = curr_settings.get('active_strategies')
                if not active_strats:
                    old_m = str(curr_settings.get('active_strategy_mode', 'DEFAULT')).upper().strip()
                    if old_m in ['TFP_LIQUIDATION_TRAP', 'VIVEK_YADAV_SD', 'BOTH_TFP']:
                        active_strats = ['VIVEK_YADAV']
                    elif old_m == 'ALL_STRATEGIES':
                        active_strats = list(AVAILABLE_STRATEGIES.keys())
                    else:
                        active_strats = ['DEFAULT']

                if is_rec_mode and rec_profile:
                    active_sessions = rec_profile.get('active_sessions', ["London Session", "New York Session"])
                else:
                    active_sessions = curr_settings.get('active_sessions', ["London Session", "New York Session"])
                is_session_ok, session_desc = SessionManager.is_session_allowed(active_sessions)
                session_blocked = not is_session_ok
                if session_blocked:
                    is_actionable = False

                # 2. Higher Timeframe (HTF) Trend Confluence Filter (Applied ONLY to Institutional Core 5-Pillars DEFAULT)
                htf_filter_enabled = bool(curr_settings.get('htf_filter_enabled', True))
                htf_conflict = False
                htf_detail = ""
                if htf_filter_enabled and ('DEFAULT' in active_strats) and is_actionable:
                    clean_dir = 'BUY' if 'BUY' in action else ('SELL' if 'SELL' in action else '')
                    if clean_dir:
                        is_htf_ok, htf_detail, _ = HTFConfluenceChecker.check_alignment(symbol, tf, clean_dir)
                        if not is_htf_ok:
                            htf_conflict = True
                            is_actionable = False

                # Micro Scalp (1m/3m/5m) Institutional Execution Gate (Strictly for DEFAULT):
                macro_conflict_scalp = False
                micro_noise_scalp = False
                if ('DEFAULT' in active_strats) and str(tf).lower() in ['1m', '3m', '5m']:
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

                active_min_pillars = rec_profile.get('min_pillars', min_pillars_required) if (is_rec_mode and rec_profile) else min_pillars_required
                is_default_eligible = (p_cnt >= min(active_min_pillars, total_req)) and is_actionable

                # ─────────────────────────────────────────────────────────────
                # MULTI-STRATEGY EVALUATION (13 STRATEGIES: DEFAULT + 12 STREAMERS)
                # ─────────────────────────────────────────────────────────────
                news_info = eval_res.get('p3', {})
                is_news_blackout = bool(news_info.get('is_blackout', False))
                playbook = pred.get('streamer_playbook', {})
                all_pb = playbook.get('all_strategies', {})

                candidates = []
                session_blocked_strategies = []

                # 1. Evaluate DEFAULT (5-Pillars Core) if selected
                is_default_session_ok, default_session_desc = self._is_strat_session_allowed(
                    strategy_key='DEFAULT',
                    generic_allowed_sessions=active_sessions,
                    asset_type=asset_type
                )
                if 'DEFAULT' in active_strats and is_default_eligible:
                    if is_default_session_ok:
                        candidates.append({
                            'strategy_key': 'DEFAULT',
                            'strategy_name': 'Institutional Core (5-Pillars)',
                            'action': action,
                            'confidence': float(prob),
                            'trade_setup': pred.get('trade_setup') or {},
                            'breakeven_mode': curr_settings.get('breakeven_mode', 'tight'),
                            'session_used': default_session_desc
                        })
                    else:
                        session_blocked_strategies.append(('DEFAULT', default_session_desc))

                # 2. Evaluate Selected Streamer Strategies
                for strat_key in active_strats:
                    if strat_key == 'DEFAULT':
                        continue

                    # Strategy evaluation from MasterStreamerPlaybook
                    st_res = all_pb.get(strat_key)
                    if not st_res:
                        # Fallback for VIVEK_YADAV to check TFP Liquidation Heatmap Trap directly
                        if strat_key == 'VIVEK_YADAV':
                            tfp_trap_data = pred.get('trade_for_profit', {})
                            tfp_trap_grade = str(tfp_trap_data.get('setup_grade', ''))
                            tfp_trap_act = str(tfp_trap_data.get('action', ''))
                            if (tfp_trap_grade in ['A+_SUPER_CONFLUENCE', 'A_HIGH_CONVICTION', 'B_DEVELOPING']
                                and tfp_trap_act in ['BUY', 'SELL']):
                                st_res = {
                                    'strategy_key': 'VIVEK_YADAV',
                                    'strategy_name': 'Vivek Yadav (TFP Liquidation Trap)',
                                    'action': tfp_trap_act,
                                    'confidence': float(tfp_trap_data.get('confidence', 75.0)),
                                    'trade_setup': tfp_trap_data.get('trade_setup') or {},
                                    'breakeven_mode': 'SMC_PARTIAL_BE'
                                }

                    if not st_res:
                        continue

                    st_act = str(st_res.get('action', '')).upper()
                    st_setup = st_res.get('trade_setup') or {}
                    st_conf = float(st_res.get('confidence', 70.0))

                    if st_act in ['BUY', 'SELL']:
                        # Enforce Strategy-Specific Execution Window from Sessions & Killzones Playbook
                        is_st_session_ok, st_session_desc = self._is_strat_session_allowed(
                            strategy_key=strat_key,
                            generic_allowed_sessions=active_sessions,
                            asset_type=asset_type
                        )

                        if not is_st_session_ok:
                            session_blocked_strategies.append((strat_key, st_session_desc))
                            continue

                        # Standard execution safety guards (news spikes, high spread)
                        # WAQAR_ZAKA is explicitly designed to trade High-Volatility News Events & Liquidation Sweeps (Playbook PDF)
                        is_news_blocked = is_news_blackout and (strat_key != 'WAQAR_ZAKA')
                        if not is_spread_fail and not is_news_blocked:
                            candidates.append({
                                'strategy_key': strat_key,
                                'strategy_name': st_res.get('strategy_name', AVAILABLE_STRATEGIES.get(strat_key, strat_key)),
                                'action': st_act,
                                'confidence': st_conf,
                                'trade_setup': st_setup,
                                'breakeven_mode': st_res.get('breakeven_mode', 'FIXED_RR_TARGET'),
                                'session_used': st_session_desc
                            })

                # If allow_diff_strat_same_tf is enabled, disallow duplicate trades from the SAME strategy on the same timeframe
                if allow_diff_strat and running_strats_on_tf and candidates:
                    orig_candidates = list(candidates)
                    candidates = [c for c in candidates if c['strategy_key'] not in running_strats_on_tf]
                    if not candidates and orig_candidates:
                        blocked_names = ", ".join([c['strategy_key'] for c in orig_candidates])
                        logger.info(f"All candidate strategies ({blocked_names}) already active on {symbol} ({tf}). Disallowing same-strategy duplicate on same TF.")
                        self._append_activity_log({
                            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                            "cycle": cycle,
                            "symbol": symbol,
                            "timeframe": tf,
                            "action": "HOLD",
                            "pillars": "-",
                            "status": "SKIPPED (Same Strat Active on TF)",
                            "details": f"Strategy {blocked_names} already active on {symbol} ({tf}). (Diff Strats Only Mode)"
                        })
                        continue

                # Selection: Rank eligible candidates by confidence & choose the best
                chosen_strategy_key = None
                chosen_strategy_name = None
                chosen_trade_setup = None
                chosen_action = None

                if candidates:
                    candidates.sort(key=lambda c: c['confidence'], reverse=True)
                    best = candidates[0]
                    chosen_strategy_key = best['strategy_key']
                    chosen_strategy_name = best['strategy_name']
                    chosen_action = best['action']
                    chosen_trade_setup = best['trade_setup']

                is_eligible = (chosen_strategy_key is not None)
                pillar_str = "5/5" if chosen_strategy_key == 'DEFAULT' else ("STRAT" if chosen_strategy_key else f"{p_cnt}/{total_req}")

                if is_eligible:
                    status_lbl = f"EXECUTING ({chosen_strategy_key})"
                    detail_str = f"Strategy: {chosen_strategy_name} | Action: {chosen_action}"
                elif session_blocked_strategies:
                    first_b_key, first_b_desc = session_blocked_strategies[0]
                    status_lbl = f"SKIPPED (Outside {first_b_key} Session)"
                    detail_str = first_b_desc
                elif session_blocked and ('DEFAULT' in active_strats):
                    status_lbl = "SKIPPED (Outside Trading Session)"
                    detail_str = f"SESSION FILTER: {session_desc}"
                elif is_news_blackout:
                    status_lbl = "SKIPPED (Economic News Blackout)"
                    detail_str = f"NEWS FILTER: {news_info.get('desc', 'High-impact economic event')}"
                elif htf_conflict and ('DEFAULT' in active_strats):
                    status_lbl = "SKIPPED (HTF Trend Conflict)"
                    detail_str = f"HTF FILTER: {htf_detail}"
                elif macro_conflict_scalp and ('DEFAULT' in active_strats):
                    status_lbl = "SKIPPED (Macro 200 EMA Conflict)"
                    detail_str = f"MACRO CONFLICT: Scalp opposes 200 EMA trend"
                elif micro_noise_scalp and ('DEFAULT' in active_strats):
                    status_lbl = "SKIPPED (No ICT Sweep / FVG)"
                    detail_str = f"MICRO NOISE FILTER: 1m/3m entries strictly require ICT Liquidity Sweep or FVG tap"
                elif is_chop:
                    status_lbl = "SKIPPED (Chop Gate)"
                    detail_str = f"CHOP: {chop_gate.get('reason', '')[:45]}"
                elif is_spread_fail:
                    status_lbl = f"SKIPPED (Spread > {spread_guard.get('max_allowed_pct', 18):.0f}% TP1)"
                    detail_str = f"Spread: ${spread_guard.get('spread_price')} ({spread_guard.get('spread_to_target_pct')}%) > {spread_guard.get('max_allowed_pct', 18):.0f}%"
                else:
                    active_lbls = ", ".join(active_strats[:3]) + (f" +{len(active_strats)-3} more" if len(active_strats) > 3 else "")
                    status_lbl = "No Trade (Waiting Setup)"
                    detail_str = f"Active: [{active_lbls}] | Monitoring price action for valid trigger"

                self._append_activity_log({
                    "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                    "cycle": cycle,
                    "symbol": symbol,
                    "timeframe": tf,
                    "action": chosen_action or action,
                    "pillars": pillar_str,
                    "status": status_lbl,
                    "details": detail_str
                })

                if is_eligible:
                    logger.info(f"TARGET SETUP CONFIRMED ({chosen_strategy_key}: {chosen_strategy_name})! {symbol} on {tf} ({chosen_action})!")
                    
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
                        'recommended_profile': rec_profile if (is_rec_mode and rec_profile) else None,
                        'strategy_used': chosen_strategy_key,
                        'strategy_name': chosen_strategy_name or chosen_strategy_key,
                        'trade_setup': chosen_trade_setup,
                        'action': chosen_action
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
            eval_res = setup_data.get('evaluation') or {}
            setup = setup_data.get('trade_setup') or pred.get('trade_setup') or pred.get('recommended_setup') or {}
            conf = pred.get('confluence', {})
            cycle = setup_data.get('cycle', 0)
            strategy_used = setup_data.get('strategy_used', 'DEFAULT')
            strategy_name = setup_data.get('strategy_name') or setup.get('strategy_name', strategy_used)

            entry_price = float(setup.get('recommended_entry') or pred.get('market_data', {}).get('current_price', 0.0))
            sl_price = float(setup.get('stop_loss', 0.0))
            tp1_price = float(setup.get('tp1', 0.0))
            tp2_price = float(setup.get('tp2', 0.0))
            tp3_price = float(setup.get('tp3', 0.0))
            raw_action = str(setup_data.get('action') or setup.get('action') or conf.get('action', 'BUY')).upper()
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

            # 4. Check Dollar Risk Cap (Requirement 9 & Dynamic Lot Scaling)
            if max_dollar_risk > 0 and actual_risk_usd > max_dollar_risk:
                # Attempt to scale down lot size to fit strictly within max_dollar_risk cap
                if total_lots > 0 and actual_risk_usd > 0:
                    risk_per_unit_lot = actual_risk_usd / total_lots
                    allowed_lots = max_dollar_risk / risk_per_unit_lot
                    scaled_lots = max(0.01, round(int(allowed_lots / 0.01) * 0.01, 2))
                    if scaled_lots < active_lot_size:
                        recalc = self.executor.calculate_lot_and_risk(
                            broker_symbol=broker_sym,
                            balance_usd=balance_usd,
                            entry_price=entry_price,
                            stop_loss_price=sl_price,
                            risk_pct=risk_pct,
                            tp1_price=tp1_price,
                            tp2_price=tp2_price,
                            tp3_price=tp3_price,
                            total_volume_lots=scaled_lots
                        )
                        recalc_risk = float(recalc.get('actual_risk_usd', 0.0))
                        if recalc_risk <= max_dollar_risk and recalc.get('total_lots', 0.0) > 0:
                            lot_sizing = recalc
                            actual_risk_usd = recalc_risk
                            lot_split = recalc.get('lot_split', {})
                            total_lots = recalc.get('total_lots', 0.0)
                            active_lot_size = scaled_lots
                            logger.info(f"Scaled lot size to {scaled_lots} to strictly honor Max Dollar Risk cap (${actual_risk_usd:.2f} <= ${max_dollar_risk:.2f})")

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

            logger.info(f"EXECUTING AUTONOMOUS TRADE ({strategy_name}): {action} {symbol} ({tf}) on {broker_sym} | Total Lots: {total_lots} {lot_split}")
            exec_res = self.executor.execute_multi_target_trade(
                broker_symbol=broker_sym,
                action=action,
                sl_price=sl_price,
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                tp3_price=tp3_price,
                lot_split=lot_split,
                timeframe=tf,
                strategy_tag=strategy_used
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
                if broker_sym != symbol:
                    by_sym[broker_sym] = by_sym.get(broker_sym, 0) + 1
                norm_s = self.normalize_symbol(symbol)
                if norm_s not in [symbol, broker_sym]:
                    by_sym[norm_s] = by_sym.get(norm_s, 0) + 1
                state['trades_by_symbol'] = by_sym

                if 'open_batches' not in state:
                    state['open_batches'] = {}

                rec_profile = setup_data.get('recommended_profile')
                strategy_be_mode = setup.get('breakeven_mode')
                active_be_mode = strategy_be_mode or (rec_profile.get('breakeven_mode') if rec_profile else self.load_settings().get('breakeven_mode', 'tight'))
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
                    'p1_score': (eval_res.get('p1', {}).get('score', 0.0) if isinstance(eval_res, dict) else 0.0),
                    'p1_prob': (eval_res.get('p1', {}).get('prob', 0.0) if isinstance(eval_res, dict) else 0.0),
                    'strategy_used': strategy_used,
                    'strategy_name': strategy_name
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
                    "pillars": "5/5" if strategy_used == 'DEFAULT' else "STRAT",
                    "status": f"EXECUTED (Batch #{batch_id})",
                    "details": f"[{strategy_name}] Entry: {entry_price} | SL: {sl_price} | Lots: {lot_split.get('tp1_lots', 0)}/{lot_split.get('tp2_lots', 0)}/{lot_split.get('tp3_lots', 0)}{adj_note}"
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
