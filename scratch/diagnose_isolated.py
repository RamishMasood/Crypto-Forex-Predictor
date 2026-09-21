import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
from datetime import datetime, timezone, timedelta

from src.engine.backtest_engine import get_backtest_engine

def diagnose_strategy(target_sk):
    bt = get_backtest_engine()
    now = datetime.now(timezone.utc)
    date_from_2w = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    date_to_2w = now.strftime("%Y-%m-%d")

    cfg = {
        "selected_symbols": ["BTC/USD", "EUR/USD", "XAU/USD"],
        "timeframes": ["15m", "1h"],
        "active_strategies": [target_sk],
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

    res = bt.run_backtest(cfg)
    trades = res.get('closed_batches', [])
    wins = [t for t in trades if t.get('profit', 0) > 0]
    losses = [t for t in trades if t.get('profit', 0) < 0]
    net = sum(t.get('profit', 0) for t in trades)
    print(f"\n==========================================")
    print(f"Strategy: {target_sk} | Net: ${net:+.2f} | Trades: {len(trades)} | Wins: {len(wins)} | Losses: {len(losses)}")
    print(f"==========================================")
    for t in trades:
        p = t.get('profit', 0)
        tag = "WIN " if p > 0 else "LOSS"
        print(f"  [{tag}] {t.get('symbol')} {t.get('timeframe')} {t.get('action')} | entry={t.get('entry_price')} exit={t.get('exit_price')} sl={t.get('sl_price')} pnl=${p:+.2f} reason={t.get('exit_reason')}")

if __name__ == '__main__':
    targets = ["DEFAULT", "ADAM_KHOO", "ICT", "KRISTJAN_QULLAMAGGIE"]
    if len(sys.argv) > 1:
        targets = [sys.argv[1]]
    for t in targets:
        diagnose_strategy(t)
