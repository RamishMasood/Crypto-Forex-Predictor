import json
from collections import defaultdict
from src.engine.backtest_engine import MT5BacktestEngine

state = json.load(open('.backtest_engine_state.json', encoding='utf-8'))
cfg = state.get('settings_used', {})
cfg['date_from'] = '2026-09-14'
cfg['date_to'] = '2026-09-21'

engine = MT5BacktestEngine()
res = engine.run_backtest(cfg)
trades = res.get('closed_batches', [])

strat_losses = defaultdict(list)
for t in trades:
    s = t.get('strategy_used', 'UNKNOWN')
    p = t.get('profit', 0.0)
    if p < -0.15:
        strat_losses[s].append(t)

print(f"Total Trades: {len(trades)}")
print(f"Total Losses: {sum(len(v) for v in strat_losses.values())}")
print("-" * 60)
for s, loss_list in sorted(strat_losses.items(), key=lambda x: len(x[1]), reverse=True):
    total_lost = sum(t.get('profit', 0.0) for t in loss_list)
    sym_counts = defaultdict(int)
    tf_counts = defaultdict(int)
    act_counts = defaultdict(int)
    for t in loss_list:
        sym_counts[t.get('symbol')] += 1
        tf_counts[t.get('timeframe')] += 1
        act_counts[t.get('action')] += 1
    print(f"\nStrategy: {s} | Total Lost: ${total_lost:.2f} | Loss Count: {len(loss_list)}")
    print(f"  Symbols: {dict(sym_counts)}")
    print(f"  Timeframes: {dict(tf_counts)}")
    print(f"  Actions: {dict(act_counts)}")
    sample = loss_list[0]
    print(f"  Sample Loss: {sample.get('symbol')} {sample.get('timeframe')} {sample.get('action')} @ {sample.get('entry_price')} SL: {sample.get('sl_price')} TP1: {sample.get('tp1_price')} TP2: {sample.get('tp2_price')} PnL: ${sample.get('profit')}")
