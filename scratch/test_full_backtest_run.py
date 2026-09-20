import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
from datetime import datetime, timezone, timedelta

from src.engine.backtest_engine import get_backtest_engine
from src.engine.autonomous_manager import AVAILABLE_STRATEGIES

def run_evaluation():
    print("=== MT5 Historical Multi-Strategy Performance Evaluation ===", flush=True)
    bt = get_backtest_engine()
    all_strats = list(AVAILABLE_STRATEGIES.keys())
    now = datetime.now(timezone.utc)
    
    # 1-Week Window (7 Days)
    date_from_1w = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    date_to_1w = now.strftime("%Y-%m-%d")

    cfg_1w = {
        "selected_symbols": ["BTC/USD", "EUR/USD", "XAU/USD"],
        "timeframes": ["15m", "1h"],
        "active_strategies": all_strats,
        "date_from": date_from_1w,
        "date_to": date_to_1w,
        "initial_balance": 10000.0,
        "batch_lot_size": 0.03,
        "max_active_batches": 10,
        "max_dollar_risk": 50.0,
        "min_pillars_required": 5,
        "allow_same_tf_trades": True,
        "allow_diff_strat_same_tf": True,
        "breakeven_mode": "tight",
        "active_sessions": ["London Session", "New York Session", "24/7 (Any Session)"],
        "htf_filter_enabled": True
    }

    t0 = time.time()
    print(f"Starting 1-Week Backtest ({date_from_1w} to {date_to_1w})...", flush=True)
    res_1w = bt.run_backtest(cfg_1w)
    elapsed = time.time() - t0
    print(f"1-Week Backtest completed in {elapsed:.1f}s!", flush=True)
    print(f"Total Trades: {res_1w.get('total_trades')}, Wins: {res_1w.get('wins')}, Losses: {res_1w.get('losses')}, Breakevens: {res_1w.get('breakevens')}", flush=True)
    print(f"Net Profit: ${res_1w.get('net_profit'):+,.2f} | Win Rate: {res_1w.get('win_rate'):.1f}%", flush=True)
    
    print("\n--- Strategy Leaderboard Breakdown (1-Week) ---", flush=True)
    for row in res_1w.get('leaderboard', []):
        sk = row.get('strategy_key')
        trades = row.get('total_trades', 0)
        pnl = row.get('net_pnl', 0.0)
        wr = row.get('win_rate', 0.0)
        w = row.get('wins', 0)
        l = row.get('losses', 0)
        be = row.get('breakevens', 0)
        print(f"[{sk:22}] Trades: {trades:3} | Wins: {w:2} | Losses: {l:2} | BE: {be:2} | Net PnL: ${pnl:+8.2f} | WR: {wr:5.1f}%", flush=True)

    print("\n--- Negative Strategy Diagnostics ---", flush=True)
    all_trades = res_1w.get('closed_batches', [])
    for row in res_1w.get('leaderboard', []):
        sk = row.get('strategy_key')
        if row.get('net_pnl', 0.0) < 0:
            st_trades = [t for t in all_trades if t.get('strategy_used') == sk]
            w_trades = [t for t in st_trades if t.get('profit', 0) > 0]
            l_trades = [t for t in st_trades if t.get('profit', 0) < 0]
            total_w = sum(t.get('profit', 0) for t in w_trades)
            total_l = sum(t.get('profit', 0) for t in l_trades)
            avg_w = total_w / max(1, len(w_trades))
            avg_l = total_l / max(1, len(l_trades))
            print(f"\n>> {sk}: Net ${row.get('net_pnl', 0.0):.2f} | Wins: {len(w_trades)} (Avg ${avg_w:.2f}) | Losses: {len(l_trades)} (Avg ${avg_l:.2f})", flush=True)
            for lt in l_trades[:5]: # show up to 5 losses
                print(f"   LOSS: {lt.get('symbol')} {lt.get('timeframe')} {lt.get('action')} | entry={lt.get('entry_price')} exit={lt.get('exit_price')} sl={lt.get('sl_price')} pnl=${lt.get('profit'):.2f} reason={lt.get('exit_reason')}", flush=True)

if __name__ == '__main__':
    run_evaluation()
