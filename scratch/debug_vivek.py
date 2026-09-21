import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timezone, timedelta
import pandas as pd
from src.engine.backtest_engine import get_backtest_engine
from src.strategies.vivek_yadav_sd import VivekYadavSupplyDemandEngine

bt = get_backtest_engine()
now = datetime.now(timezone.utc)
d_from = now - timedelta(days=14)
d_to = now

for sym in ["BTC/USD", "XAU/USD"]:
    for tf in ["15m", "1h"]:
        df, broker_sym, sp = bt.fetch_mt5_data(sym, tf, d_from, d_to)
        print(f"=== {sym} {tf} (len: {len(df) if df is not None else 0}) ===")
        if df is not None and len(df) > 0:
            zones = VivekYadavSupplyDemandEngine.detect_zones(df)
            print("  Demand zones:", len(zones.get('demand_zones', [])))
            print("  Supply zones:", len(zones.get('supply_zones', [])))
            for z in zones.get('demand_zones', []):
                print("    DZ:", z['candle_index'], f"[{z['bottom']:.2f} - {z['top']:.2f}]", z['source'])
            for z in zones.get('supply_zones', []):
                print("    SZ:", z['candle_index'], f"[{z['bottom']:.2f} - {z['top']:.2f}]", z['source'])
            
            # Count triggers
            triggers = []
            for i in range(50, len(df)):
                sub = df.iloc[:i]
                atr = float(sub['atr'].iloc[-1]) if 'atr' in sub.columns else 0.0
                res = VivekYadavSupplyDemandEngine.evaluate(sub, atr=atr, timeframe=tf)
                if res.get('action') in ['BUY', 'SELL']:
                    triggers.append((i, res.get('action'), float(sub['close'].iloc[-1]), res.get('reasons')))
            print(f"  Triggers: {len(triggers)}")
            for t in triggers[:5]:
                print("   ", t)
