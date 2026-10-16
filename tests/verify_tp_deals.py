import json
import MetaTrader5 as mt5

if mt5.initialize():
    with open('.autonomous_trader_state.json', 'r', encoding='utf-8') as f:
        st = json.load(f)
    cbs = st.get('closed_batches', [])
    print(f"Total closed batches to verify: {len(cbs)}")
    for cb in cbs:
        bid = cb.get('batch_id')
        sym = cb.get('symbol')
        strat = cb.get('strategy_used')
        tkts = cb.get('tickets', [])
        pnl = cb.get('profit')
        tp1_p = cb.get('tp1_price')
        tp2_p = cb.get('tp2_price')
        print(f"\n--- Batch #{bid} ({sym}) {strat} | PnL: ${pnl} | TP1 Price: {tp1_p} | TP2 Price: {tp2_p} ---")
        for idx, t in enumerate(tkts):
            label = f"TP{idx+1}" if idx < 3 else "RUNNER"
            deals = mt5.history_deals_get(position=int(t))
            if deals:
                exit_deals = [d for d in deals if d.entry == 1]
                for ed in exit_deals:
                    d_pnl = round(float(ed.profit) + float(getattr(ed, 'swap', 0)) + float(getattr(ed, 'commission', 0)), 2)
                    d_comm = str(ed.comment)
                    d_price = float(ed.price)
                    print(f"  Ticket #{t} ({label}): Exit Price={d_price:.5f}, PnL=${d_pnl:+.2f}, Comment='{d_comm}'")
            else:
                print(f"  Ticket #{t} ({label}): No deals found in history")
    mt5.shutdown()
else:
    print("Failed to initialize MT5")
