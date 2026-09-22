import json
from src.engine.backtest_engine import MT5BacktestEngine, BACKTEST_STATE_FILE

st = json.load(open(BACKTEST_STATE_FILE))
sets = json.load(open('.backtest_engine_settings.json'))
lb = MT5BacktestEngine.compute_backtest_strategy_leaderboard(st.get('closed_batches', []), sets.get('active_strategies', []))

print("=" * 85)
print(f"{'Strategy Key':24} | {'Net PnL':10} | {'W':3} {'L':3} {'BE':3} | {'WinRate':7} | {'PF':5} | {'SL Hits':7}")
print("=" * 85)
for x in lb:
    print(f"{x['strategy_key']:24} | ${x['net_pnl']:+9.2f} | {x['wins']:3} {x['losses']:3} {x['breakevens']:3} | {x['win_rate']:6.1f}% | {x['profit_factor']:5.2f} | {x['sl_hits']:7}")
print("=" * 85)
