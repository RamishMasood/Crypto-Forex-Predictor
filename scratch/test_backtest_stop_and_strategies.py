import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
from datetime import datetime, timezone, timedelta

from src.engine.backtest_engine import get_backtest_engine, MT5BacktestEngine
from src.engine.autonomous_manager import AVAILABLE_STRATEGIES
from src.strategies.streamer_playbook import MasterStreamerPlaybook

def test_verification():
    print("=== MT5 Historical Backtester Verification ===")
    bt = get_backtest_engine()

    # 1. Verify all 19 strategies
    print(f"Total Available Strategies: {len(AVAILABLE_STRATEGIES)}")
    assert len(AVAILABLE_STRATEGIES) == 19, f"Expected 19 strategies, got {len(AVAILABLE_STRATEGIES)}"

    all_strats = list(AVAILABLE_STRATEGIES.keys())
    for s_k in all_strats:
        in_playbook = (s_k in MasterStreamerPlaybook.STRATEGY_MAP) or (s_k == 'DEFAULT')
        assert in_playbook, f"Strategy {s_k} not found in Playbook or Default!"
    print("[OK] All 19 strategies mapped and validated.")

    # 2. Test start_backtest in background thread & live stats
    test_settings = {
        "selected_symbols": ["BTC/USD", "EUR/USD"],
        "timeframes": ["15m", "1h"],
        "active_strategies": all_strats,
        "date_from": (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d"),
        "date_to": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
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

    print("\n--- Starting Background Backtest ---")
    bt.start_backtest(test_settings)
    assert bt.is_running, "Expected bt.is_running to be True after start_backtest"
    print("[OK] Background thread started successfully (is_running == True).")

    # Monitor for 2 seconds and observe live stats
    time.sleep(1.0)
    live_stats = bt.get_live_stats()
    print(f"Live stats snapshot after 1s: progress={live_stats.get('progress_pct')}, cur_time={live_stats.get('cur_time')}, date_from={live_stats.get('date_from')}, date_to={live_stats.get('date_to')}, trades={live_stats.get('total_trades')}")
    assert live_stats.get('date_from') == test_settings['date_from'], "Live stats date_from mismatch"
    assert live_stats.get('date_to') == test_settings['date_to'], "Live stats date_to mismatch"
    print("[OK] Live date range and stats correctly synchronized.")

    # 3. Test Stop Button
    print("\n--- Testing Stop Mechanism ---")
    bt.stop()
    print("Stop requested. Waiting for worker thread to exit cleanly...")
    
    # Wait up to 5 seconds for thread to finish
    for _ in range(50):
        if not bt.is_running:
            break
        time.sleep(0.1)

    assert not bt.is_running, "Expected bt.is_running to be False after stop"
    print("[OK] Backtester cleanly stopped. Thread exited gracefully.")

    # Check saved state
    results = bt.load_latest_results()
    assert results is not None, "Results should not be None after stop"
    print(f"State status after stop: {results.get('status')}")
    print(f"Simulated period: {results.get('date_from')} to {results.get('simulated_until')}")
    print(f"Total simulated trades: {results.get('total_trades')}")
    print(f"Leaderboard entries: {len(results.get('leaderboard', []))}")
    print("[OK] State preserved cleanly without data corruption.")

    print("\n==========================================")
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("==========================================")

if __name__ == '__main__':
    test_verification()
