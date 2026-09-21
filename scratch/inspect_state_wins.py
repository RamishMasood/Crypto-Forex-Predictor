import json

with open('.backtest_engine_state.json', 'r') as f:
    data = json.load(f)

closed = data.get('closed_batches', [])
for t in closed:
    strat = t.get('strategy_used')
    if strat in ['ADAM_KHOO', 'OLIVER_VELEZ', 'STEVEN_HART', 'PAUL_FTMO'] and t.get('profit', 0) > 0:
        print(f"{strat}: pnl={t.get('profit')}, tp1_hit={t.get('tp1_hit')}, tp2_hit={t.get('tp2_hit')}, entry={t.get('entry_price')}, exit={t.get('exit_price')}, sl={t.get('sl_price')}, tp1={t.get('tp1_price')}, reason={t.get('exit_reason')}")
