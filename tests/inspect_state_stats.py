import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('.autonomous_trader_state.json', encoding='utf-8') as f:
    st = json.load(f)

closed = st.get('closed_batches', [])
print(f"Total Closed Batches in State: {len(closed)}")

stats = {}
for b in closed:
    strat = b.get('strategy_name', 'Unknown')
    if strat not in stats:
        stats[strat] = {'trades': 0, 'wins': 0, 'losses': 0, 'be': 0, 'tp2': 0, 'pnl': 0.0}
    s = stats[strat]
    s['trades'] += 1
    pnl = float(b.get('profit', 0.0))
    s['pnl'] += pnl
    status = b.get('status', '').upper()
    if status == 'WIN':
        s['wins'] += 1
    elif status == 'LOSS':
        s['losses'] += 1
    else:
        s['be'] += 1
    if b.get('tp2_hit') or b.get('has_tp2'):
        s['tp2'] += 1

print("\n--- Current UI Leaderboard State (Since Reset) ---")
total_w = sum(s['wins'] for s in stats.values())
total_t = sum(s['trades'] for s in stats.values())
total_pnl = sum(s['pnl'] for s in stats.values())
total_tp2 = sum(s['tp2'] for s in stats.values())

for strat, s in sorted(stats.items(), key=lambda x: x[1]['pnl'], reverse=True):
    wr = round((s['wins'] / s['trades']) * 100.0, 1) if s['trades'] > 0 else 0.0
    print(f"* {strat}:\n  Trades: {s['trades']} | Wins: {s['wins']} | Losses: {s['losses']} | Win Rate: {wr}% | TP2 Hits: {s['tp2']} | Net PnL: ${s['pnl']:+.2f}")

print(f"\nOVERALL: Trades: {total_t} | Wins: {total_w} | Win Rate: {round(total_w/total_t*100, 1)}% | Real TP2: {total_tp2} | Net PnL: ${total_pnl:+.2f}")
