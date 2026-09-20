import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timezone, timedelta
from src.engine.backtest_engine import MT5BacktestEngine

now = datetime.now(timezone.utc)
d_from = now - timedelta(days=7)
print(f"Testing MT5 fetch from {d_from} to {now}...")
for sym in ["BTC/USD", "EUR/USD", "XAU/USD"]:
    df, broker_sym, spread = MT5BacktestEngine.fetch_mt5_data(sym, "1h", d_from, now)
    if df is not None:
        print(f"[{sym}] SUCCESS: broker_sym={broker_sym}, rows={len(df)}, spread={spread}")
    else:
        print(f"[{sym}] FAILED to fetch from MT5")
