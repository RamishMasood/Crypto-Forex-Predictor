import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
from datetime import datetime, timezone, timedelta

from src.engine.backtest_engine import get_backtest_engine
from src.engine.autonomous_manager import AVAILABLE_STRATEGIES

def run_full_test():
    print("=== Testing Full Backtest Run on All 19 Strategies ===")
    bt = get_backtest_engine()
    all_strats = list(AVAILABLE_STRATEGIES.keys())

    test_settings = {
        "selected_symbols": ["BTC/USD", "EUR/USD", "XAU/USD"],
        "timeframes": ["15m", "1h"],
        "active_strategies": all_strats,
        "date_from": "2024-01-01",
        "date_to": "2024-01-15",
        "initial_balance": 10000.0,
        "batch_lot_size": 0.03,
        "max_active_batches": 5,
        "max_dollar_risk": 50.0,
        "min_pillars_required": 5,
        "allow_same_tf_trades": False,
        "allow_diff_strat_same_tf": True,
        "breakeven_mode": "tight",
        "active_sessions": ["London Session", "New York Session", "24/7 (Any Session)"],
        "htf_filter_enabled": True
    }

    res = bt.run_backtest(test_settings)
    print(f"Status: {res.get('status')}")
    print(f"Total simulated trades: {res.get('total_trades')}")
    print(f"Wins: {res.get('wins')} | Losses: {res.get('losses')} | Breakevens: {res.get('breakevens')}")
    print(f"Net Profit: ${res.get('net_profit')} | Win Rate: {res.get('win_rate')}%")
    print(f"Leaderboard ranks generated: {len(res.get('leaderboard', []))}")
    for item in res.get('leaderboard', [])[:5]:
        print(f"  {item.get('rank_display')} {item.get('strategy_name')}: {item.get('total_trades')} trades, Net PnL: ${item.get('net_pnl')}, WR: {item.get('win_rate')}%")

if __name__ == '__main__':
    run_full_test()
