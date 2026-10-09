import json
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone

# 1. Check autonomous state
state = json.load(open(".autonomous_trader_state.json"))
print(f"Total trades taken in state: {state.get('total_trades_taken')}")
print(f"State Wins: {state.get('wins', 0)} | Losses: {state.get('losses', 0)} | Breakevens: {state.get('breakevens', 0)}")

closed = state.get("closed_batches", [])
print(f"\nTotal closed batches in state: {len(closed)}")
for b in closed[:10]:
    print(f"Batch #{b.get('batch_id')} | {b.get('symbol')} ({b.get('timeframe')}) | Profit: ${b.get('profit')} | Outcome: {b.get('status')} | ClosedAt: {b.get('closed_at')}")

# 2. Check MT5 deals
if mt5.initialize():
    from_date = datetime.now() - timedelta(hours=14)
    deals = mt5.history_deals_get(from_date, datetime.now())
    print(f"\nMT5 deals since last night ({from_date.strftime('%Y-%m-%d %H:%M')}): {len(deals) if deals else 0}")
    
    positions_map = {}
    if deals:
        for d in deals:
            if d.magic == 999888:
                if d.position_id not in positions_map:
                    positions_map[d.position_id] = []
                positions_map[d.position_id].append(d)
                
        print(f"Total unique autonomous positions in history: {len(positions_map)}")
        for pid, dlist in list(positions_map.items())[:15]:
            pnl = sum(d.profit + d.swap + d.commission for d in dlist)
            comments = [d.comment for d in dlist]
            types = [d.entry for d in dlist]
            print(f"Pos #{pid} | Net PnL: ${pnl:.2f} | Comments: {comments}")

    mt5.shutdown()
