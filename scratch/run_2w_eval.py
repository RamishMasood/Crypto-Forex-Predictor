import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
from datetime import datetime, timezone, timedelta

from src.engine.backtest_engine import get_backtest_engine
from src.engine.autonomous_manager import AVAILABLE_STRATEGIES

def run_2w_eval():
    print("=== MT5 Historical Multi-Strategy 2-Week Performance Evaluation ===", flush=True)
    bt = get_backtest_engine()
    all_strats = list(AVAILABLE_STRATEGIES.keys())
    now = datetime.now(timezone.utc)
    
    # Exactly 2 Weeks (14 Days)
    date_from_2w = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    date_to_2w = now.strftime("%Y-%m-%d")

    # Multi-asset test: BTC/USD, EUR/USD, XAU/USD
    cfg = {
        "selected_symbols": ["BTC/USD", "EUR/USD", "XAU/USD"],
        "timeframes": ["15m", "1h"],
        "active_strategies": all_strats,
        "date_from": date_from_2w,
        "date_to": date_to_2w,
        "initial_balance": 10000.0,
        "batch_lot_size": 0.03,
        "max_active_batches": 15,
        "max_dollar_risk": 50.0,
        "min_pillars_required": 5,
        "allow_same_tf_trades": True,
        "allow_diff_strat_same_tf": True,
        "breakeven_mode": "tight",
        "active_sessions": ["London Session", "New York Session", "24/7 (Any Session)", "Tokyo Session"],
        "htf_filter_enabled": True
    }

    t0 = time.time()
    print(f"Starting 2-Week Backtest ({date_from_2w} to {date_to_2w}) across {len(all_strats)} strategies...", flush=True)
    res = bt.run_backtest(cfg)
    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.1f}s!", flush=True)
    print(f"Total Trades: {res.get('total_trades')}, Wins: {res.get('wins')}, Losses: {res.get('losses')}, Breakevens: {res.get('breakevens')}", flush=True)
    print(f"Net Profit: ${res.get('net_profit'):+,.2f} | Win Rate: {res.get('win_rate'):.1f}%", flush=True)
    
    print("\n--- Strategy Leaderboard Breakdown (2-Weeks) ---", flush=True)
    lb = res.get('leaderboard', [])
    lb_sorted = sorted(lb, key=lambda x: x.get('net_pnl', 0.0), reverse=True)
    unprofitable = []
    zero_trades = []
    
    for row in lb_sorted:
        sk = row.get('strategy_key')
        trades = row.get('total_trades', 0)
        pnl = row.get('net_pnl', 0.0)
        wr = row.get('win_rate', 0.0)
        w = row.get('wins', 0)
        l = row.get('losses', 0)
        be = row.get('breakevens', 0)
        status_flag = "[PROFIT]" if pnl > 0 else ("[LOSS]" if pnl < 0 else "[ZERO]")
        print(f"{status_flag:8} [{sk:22}] Trades: {trades:3} | Wins: {w:2} | Losses: {l:2} | BE: {be:2} | Net PnL: ${pnl:+8.2f} | WR: {wr:5.1f}%", flush=True)
        if pnl < 0:
            unprofitable.append(sk)
        elif trades == 0:
            zero_trades.append(sk)

    print(f"\nSummary: {len(lb) - len(unprofitable) - len(zero_trades)} Profitable, {len(unprofitable)} In Loss, {len(zero_trades)} Zero Trades out of {len(lb)} strategies.")
    if unprofitable:
        print(f"Unprofitable Strategies: {unprofitable}")
    if zero_trades:
        print(f"Zero Trades Strategies: {zero_trades}")

if __name__ == '__main__':
    run_2w_eval()
