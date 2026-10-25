import os
import sys
import pickle
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.engine.backtest_engine import MT5BacktestEngine

CACHE_DIR = os.path.join(ROOT, 'scratch', 'cache_3year')
SYMBOLS = ['EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF', 'XAU/USD', 'BTC/USD', 'ETH/USD']
d_from = datetime.fromisoformat('2024-10-24').replace(tzinfo=timezone.utc)
d_to = datetime.fromisoformat('2025-10-24').replace(tzinfo=timezone.utc)

TARGET_STRATS = [
    'NICOLAS_DARVAS', 'NDEMAZEAH_GODLOVE', 'BERND_SKORUPINSKI',
    'ROSS_CAMERON', 'ICT', 'MARK_MINERVINI', 'TRADE_PRO', 'ADAM_KHOO'
]

losses = []

for sym in SYMBOLS:
    cache_file = os.path.join(CACHE_DIR, f"{sym.replace('/', '_')}.pkl")
    if not os.path.exists(cache_file):
        continue
    with open(cache_file, 'rb') as f:
        preloaded = pickle.load(f)
    sliced_sym = {}
    for tf, df in preloaded['data_feeds'].get(sym, {}).items():
        if df is None or len(df) == 0:
            continue
        sub = df[(df['timestamp'] >= d_from) & (df['timestamp'] <= d_to)].copy()
        if len(sub) >= 30:
            sub.attrs['symbol'] = sym
            sliced_sym[tf] = sub
    if not sliced_sym:
        continue
    sliced_preloaded = {
        'data_feeds': {sym: sliced_sym},
        'broker_symbols': preloaded['broker_symbols'],
        'spread_maps': preloaded['spread_maps']
    }
    cfg = {
        'selected_symbols': [sym],
        'timeframes': ['5m', '15m', '30m', '1h', '4h'],
        'active_strategies': TARGET_STRATS,
        'date_from': '2024-10-24',
        'date_to': '2025-10-24',
        'initial_balance': 1000.0,
        'batch_lot_size': 0.03,
        'max_dollar_risk': 20.0,
        'max_active_batches': 15,
        'target_trades_per_symbol': 3000,
        'scan_delay_mins': 0.25,
        'allow_same_tf_trades': False,
        'allow_diff_strat_same_tf': True,
        'breakeven_mode': 'smart_breathing_be',
        'active_sessions': ["24/7 (Any Session)"],
        'htf_filter_enabled': True,
        'smart_solution_enabled': True,
        'news_filter_enabled': True,
        'fail_fast_synthetic': True,
        'preloaded_feeds': sliced_preloaded
    }
    engine = MT5BacktestEngine()
    res = engine.run_backtest(cfg)
    for b in res.get('closed_batches', []):
        strat = b.get('strategy_used', b.get('strategy_key', 'DEFAULT'))
        pnl = float(b.get('accumulated_pnl', b.get('profit', 0.0)))
        status = b.get('status', '')
        if pnl < 0:
            tf = b.get('timeframe', '')
            entry_t = b.get('entry_time', '')
            exit_t = b.get('exit_time', '')
            reasons = b.get('reasons', [])
            losses.append((strat, sym, tf, pnl, status, entry_t, exit_t, reasons))

print(f"\n--- Total Losses in Stage 1 for Target Strategies: {len(losses)} ---")
losses.sort(key=lambda x: (x[0], x[3]))
for l in losses:
    print(f"[LOSS] {l[0]:<22} | {l[1]:<7} | {l[2]:<4} | PnL: ${l[3]:+6.2f} | Status: {l[4]:<15} | In: {l[5]} | Out: {l[6]}")
