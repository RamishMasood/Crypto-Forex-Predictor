import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
import json
from src.engine.autonomous_manager import AutonomousTraderEngine

with open('.autonomous_trader_state.json', encoding='utf-8') as f:
    st = json.load(f)

closed = st.get('closed_batches', [])
lb = AutonomousTraderEngine.compute_strategy_leaderboard(closed_batches=closed, active_sort='Net Profit ($)')
print(f"Total Closed Batches in State: {len(closed)}")
for item in lb:
    print(f"#{item['rank']} | {item['strategy_name']} | Trades: {item['total_trades']} | Wins: {item['wins']} | Losses: {item['losses']} | WR: {item['win_rate']}% | TP2 Hits: {item.get('tp2_hits', 0)} | Net PnL: ${item['net_pnl']:.2f}")
