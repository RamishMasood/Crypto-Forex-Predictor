import json

with open('.backtest_engine_state.json', 'r') as f:
    data = json.load(f)

closed = data.get('closed_batches', [])
for s in ['ADAM_KHOO', 'OLIVER_VELEZ', 'STEVEN_HART', 'PAUL_FTMO', 'ARIEL_ZWECHER']:
    losses = [t for t in closed if t.get('strategy_used') == s and t.get('profit', 0) < -0.15]
    print(f"\n=================== {s} LOSSES ({len(losses)}) ===================")
    for l in losses:
        entry = l.get('entry_price')
        exit_p = l.get('exit_price')
        sl = l.get('sl_price')
        tp1 = l.get('tp1_price')
        tp2 = l.get('tp2_price')
        pnl = l.get('profit')
        risk = l.get('risk_usd')
        sym = l.get('symbol')
        tf = l.get('timeframe')
        act = l.get('action')
        tp1_hit = l.get('tp1_hit')
        ex_at = l.get('executed_at')
        cl_at = l.get('closed_at')
        print(f"{sym} {tf} {act} | {ex_at} -> {cl_at} | entry={entry} exit={exit_p} sl={sl} tp1={tp1} tp2={tp2} | pnl={pnl} risk={risk}")
