import json

d = json.load(open(".backtest_engine_state.json", encoding="utf-8"))
print("Net Profit:", d.get("net_profit"))
print("Win Rate:", d.get("win_rate"))
print("Total Trades:", d.get("total_trades"))
print("-" * 60)
for x in d.get("leaderboard", []):
    k = x.get("strategy_key", "")
    pnl = x.get("net_pnl", 0.0)
    w = x.get("wins", 0)
    l = x.get("losses", 0)
    be = x.get("breakevens", 0)
    tot = x.get("total_trades", 0)
    wr = x.get("win_rate", 0.0)
    print(f"{k:24}: PnL=${pnl:9.2f} | W:{w:3} L:{l:3} BE:{be:4} Tot:{tot:4} | WR:{wr:5.1f}%")

print("\n--- LOSING BATCHES FOR NEGATIVE STRATEGIES ---")
cb = d.get("closed_batches", [])
if cb:
    print("Keys in batch:", list(cb[0].keys()))
for b in cb:
    strat = b.get("strategy_used", "")
    if strat == "RICHARD_DENNIS":
        pnl = b.get("profit", 0.0)
        print(f"Strat: {strat:20} Sym: {b.get('symbol'):10} TF: {b.get('timeframe'):4} Action: {b.get('action'):5} PnL: ${pnl:7.2f} Exit: {b.get('exit_reason')}")








