import json
from collections import defaultdict

state = json.load(open(".autonomous_trader_state.json"))
closed = state.get("closed_batches", [])

print(f"==================================================")
print(f"TOTAL CLOSED BATCHES SINCE RESET: {len(closed)}")
print(f"STATE STATS: Wins: {state.get('wins', 0)} | Losses: {state.get('losses', 0)} | BE: {state.get('breakevens', 0)}")
if closed:
    wr = (state.get('wins', 0) / (state.get('wins', 0) + state.get('losses', 0))) * 100.0 if (state.get('wins', 0) + state.get('losses', 0)) > 0 else 0
    print(f"OVERALL WIN RATE: {wr:.1f}%")
print(f"==================================================\n")

strat_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "be": 0, "pnl": 0.0, "trades": []})

for b in closed:
    bid = b.get("batch_id")
    sym = b.get("symbol")
    tf = b.get("timeframe")
    pnl = float(b.get("profit", 0.0))
    status = b.get("status")
    strat = b.get("strategy_name") or b.get("strategy_used") or "Unknown"
    
    st = strat_stats[strat]
    st["pnl"] += pnl
    if status == "WIN":
        st["wins"] += 1
    elif status == "LOSS":
        st["losses"] += 1
    else:
        st["be"] += 1
    st["trades"].append((bid, sym, tf, pnl, status, b.get("closed_at")))

print("--- PERFORMANCE BY STRATEGY ---")
for strat, s in sorted(strat_stats.items(), key=lambda x: x[1]['pnl'], reverse=True):
    tot = s["wins"] + s["losses"] + s["be"]
    strat_wr = (s["wins"] / tot * 100.0) if tot > 0 else 0
    print(f"\nStrategy: {strat}")
    print(f"  Total: {tot} | Wins: {s['wins']} | Losses: {s['losses']} | BE: {s['be']} | WR: {strat_wr:.1f}% | Net PnL: ${s['pnl']:+.2f}")
    for t in s["trades"]:
        print(f"    Batch #{t[0]} | {t[1]} ({t[2]}) | PnL: ${t[3]:+.2f} | {t[4]} | {t[5]}")

print("\n--- SPECIFIC LOSSES AUDIT ---")
for b in closed:
    if b.get("status") == "LOSS":
        print(f"LOSS Batch #{b.get('batch_id')} | {b.get('symbol')} ({b.get('timeframe')}) | Strat: {b.get('strategy_name')} | PnL: ${b.get('profit')} | Reason: {b.get('reasons') or b.get('decision_metadata')}")
