import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
from src.engine.backtest_engine import get_backtest_engine

bt = get_backtest_engine()
now = datetime.now(timezone.utc)
d_from = now - timedelta(days=14)
d_to = now

df, broker_sym, sp = bt.fetch_mt5_data("EUR/USD", "15m", d_from, d_to)
print("EUR/USD 15m loaded:", len(df))

fail_counts = {
    'deep_discount': 0,
    'trend_up': 0,
    'inducement_buy': 0,
    'bos_buy': 0,
    'rsi_buy': 0,
    'deep_prem': 0,
    'trend_down': 0,
    'inducement_sell': 0,
    'bos_sell': 0,
    'rsi_sell': 0
}

for i in range(50, len(df)):
    sub = df.iloc[:i+1]
    n = len(sub)
    cur_p = float(sub['close'].iloc[-1])
    safe_atr = float(sub['atr'].iloc[-1]) if 'atr' in sub.columns else cur_p * 0.001
    highs = sub['high']
    lows = sub['low']
    closes = sub['close']
    opens = sub['open']

    htf_high = float(highs.iloc[-min(n, 60):].max())
    htf_low = float(lows.iloc[-min(n, 60):].min())
    cand_body = abs(cur_p - opens.iloc[-1])

    closes_s = pd.Series(closes.values)
    ema20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])
    trend_up = (ema20 >= ema50) and (cur_p >= ema20)
    trend_down = (ema20 <= ema50) and (cur_p <= ema20)

    is_deep_discount = cur_p <= (htf_low + (htf_high - htf_low) * 0.46)
    is_deep_premium = cur_p >= (htf_low + (htf_high - htf_low) * 0.54)

    ltf_lookback = min(n, 10)
    minor_low = float(lows.iloc[-ltf_lookback:-2].min())
    minor_high = float(highs.iloc[-ltf_lookback:-2].max())
    prev_swing_h = float(highs.iloc[-4:-1].max())
    prev_swing_l = float(lows.iloc[-4:-1].min())

    has_bullish_inducement = (float(lows.iloc[-2]) < minor_low or float(lows.iloc[-1]) < minor_low)
    has_bullish_bos = closes.iloc[-1] >= prev_swing_h and closes.iloc[-1] > opens.iloc[-1] and (cand_body >= 0.30 * safe_atr)

    has_bearish_inducement = (float(highs.iloc[-2]) > minor_high or float(highs.iloc[-1]) > minor_high)
    has_bearish_bos = closes.iloc[-1] <= prev_swing_l and closes.iloc[-1] < opens.iloc[-1] and (cand_body >= 0.30 * safe_atr)

    if is_deep_discount: fail_counts['deep_discount'] += 1
    if trend_up: fail_counts['trend_up'] += 1
    if has_bullish_inducement: fail_counts['inducement_buy'] += 1
    if has_bullish_bos: fail_counts['bos_buy'] += 1

    if is_deep_premium: fail_counts['deep_prem'] += 1
    if trend_down: fail_counts['trend_down'] += 1
    if has_bearish_inducement: fail_counts['inducement_sell'] += 1
    if has_bearish_bos: fail_counts['bos_sell'] += 1

    if is_deep_discount and trend_up and has_bullish_inducement:
        print(f"Bar {i} has deep_disc + trend_up + induc_buy! BOS={has_bullish_bos} (close={closes.iloc[-1]}, prev_swing_h={prev_swing_h}, body={cand_body:.5f}, 0.30atr={0.30*safe_atr:.5f})")

print("Fail counts summary:")
for k, v in fail_counts.items():
    print(f"  {k}: {v}")
