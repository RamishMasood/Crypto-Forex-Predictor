import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
from datetime import datetime, timezone, timedelta

from src.engine.backtest_engine import get_backtest_engine
from src.engine.autonomous_manager import AVAILABLE_STRATEGIES

def diagnose():
    bt = get_backtest_engine()
    now = datetime.now(timezone.utc)
    date_from_2w = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    date_to_2w = now.strftime("%Y-%m-%d")

    cfg = {
        "selected_symbols": ["BTC/USD", "EUR/USD", "XAU/USD"],
        "timeframes": ["15m", "1h"],
        "active_strategies": ["DEFAULT", "ADAM_KHOO", "ICT", "GCR", "KRISTJAN_QULLAMAGGIE"],
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
    print(f"Total Trades Evaluated: {len(trades)}")
    
    for sk in ["DEFAULT", "ADAM_KHOO", "ICT", "GCR", "KRISTJAN_QULLAMAGGIE"]:
        s_trades = [t for t in trades if t.get('strategy_used') == sk]
        wins = [t for t in s_trades if t.get('profit', 0) > 0]
        losses = [t for t in s_trades if t.get('profit', 0) < 0]
        net = sum(t.get('profit', 0) for t in s_trades)
        print(f"\n==========================================")
        print(f"Strategy: {sk} | Net: ${net:+.2f} | Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"==========================================")
        for t in s_trades:
            p = t.get('profit', 0)
            tag = "WIN" if p > 0 else "LOSS"
            print(f"  [{tag:4}] {t.get('symbol')} {t.get('timeframe')} {t.get('action')} | entry={t.get('entry_price')} sl={t.get('sl_price')} pnl=${p:+.2f} reason={t.get('exit_reason')}")

if __name__ == '__main__':
    diagnose()
