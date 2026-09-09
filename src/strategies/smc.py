"""
Smart Money Concepts (SMC) & Price Action Detector
Identifies Fair Value Gaps (FVG), Institutional Order Blocks (OB),
Liquidity Sweeps, and Market Structure Shifts (BOS / MSS).
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional

class SmartMoneyConcepts:
    """
    Detects institutional footprint and market structure anomalies.
    """

    @staticmethod
    def detect_fair_value_gaps(df: pd.DataFrame, min_gap_pct: float = 0.05) -> List[Dict[str, Any]]:
        """
        Detects 3-candle Fair Value Gaps (FVGs) and checks if they remain unmitigated.
        """
        fvgs = []
        n = len(df)
        if n < 3:
            return fvgs

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        timestamps = df['timestamp'].values if 'timestamp' in df.columns else np.arange(n)
        current_price = closes[-1]

        for i in range(2, n):
            # Bullish FVG: Low of candle i > High of candle i-2
            if lows[i] > highs[i - 2]:
                gap_size = lows[i] - highs[i - 2]
                gap_pct = (gap_size / highs[i - 2]) * 100.0
                if gap_pct >= min_gap_pct:
                    # Check if mitigated by subsequent candles
                    is_mitigated = any(lows[k] <= highs[i - 2] for k in range(i + 1, n)) if i + 1 < n else False
                    fvgs.append({
                        'type': 'BULLISH_FVG',
                        'top': float(lows[i]),
                        'bottom': float(highs[i - 2]),
                        'size': float(gap_size),
                        'size_pct': float(gap_pct),
                        'index': int(i - 1),
                        'timestamp': str(timestamps[i - 1]),
                        'mitigated': is_mitigated,
                        'in_zone': (highs[i - 2] <= current_price <= lows[i])
                    })

            # Bearish FVG: High of candle i < Low of candle i-2
            elif highs[i] < lows[i - 2]:
                gap_size = lows[i - 2] - highs[i]
                gap_pct = (gap_size / lows[i - 2]) * 100.0
                if gap_pct >= min_gap_pct:
                    is_mitigated = any(highs[k] >= lows[i - 2] for k in range(i + 1, n)) if i + 1 < n else False
                    fvgs.append({
                        'type': 'BEARISH_FVG',
                        'top': float(lows[i - 2]),
                        'bottom': float(highs[i]),
                        'size': float(gap_size),
                        'size_pct': float(gap_pct),
                        'index': int(i - 1),
                        'timestamp': str(timestamps[i - 1]),
                        'mitigated': is_mitigated,
                        'in_zone': (highs[i] <= current_price <= lows[i - 2])
                    })

        return fvgs

    @staticmethod
    def detect_order_blocks(df: pd.DataFrame, lookback: int = 50) -> List[Dict[str, Any]]:
        """
        Identifies high-probability institutional Order Blocks (OB).
        """
        obs = []
        n = len(df)
        if n < 10:
            return obs

        sub_df = df.iloc[-lookback:] if n > lookback else df
        opens = sub_df['open'].values
        closes = sub_df['close'].values
        highs = sub_df['high'].values
        lows = sub_df['low'].values
        current_price = closes[-1]
        timestamps = sub_df['timestamp'].values if 'timestamp' in sub_df.columns else np.arange(len(sub_df))

        for i in range(2, len(sub_df) - 2):
            # Bullish Order Block: Bearish candle followed by strong bullish breakout
            if closes[i] < opens[i]: # Down candle
                # Subsequent 2 candles show strong upside expansion
                subsequent_gain = closes[min(i + 2, len(sub_df) - 1)] - opens[i]
                if subsequent_gain > (highs[i] - lows[i]) * 1.5:
                    disp = subsequent_gain / max(highs[i] - lows[i], 1e-8)
                    obs.append({
                        'type': 'BULLISH_OB',
                        'top': float(highs[i]),
                        'bottom': float(lows[i]),
                        'candle_index': int(i),
                        'timestamp': str(timestamps[i]),
                        'displacement_ratio': float(round(disp, 2)),
                        'quality': 'INSTITUTIONAL_PRIME' if disp >= 2.2 else 'STANDARD',
                        'in_zone': (lows[i] <= current_price <= highs[i]),
                        'tested': any(lows[k] <= highs[i] for k in range(min(i + 3, len(sub_df)), len(sub_df))) if i + 3 < len(sub_df) else False
                    })

            # Bearish Order Block: Bullish candle followed by strong bearish dump
            elif closes[i] > opens[i]: # Up candle
                subsequent_drop = opens[i] - closes[min(i + 2, len(sub_df) - 1)]
                if subsequent_drop > (highs[i] - lows[i]) * 1.5:
                    disp = subsequent_drop / max(highs[i] - lows[i], 1e-8)
                    obs.append({
                        'type': 'BEARISH_OB',
                        'top': float(highs[i]),
                        'bottom': float(lows[i]),
                        'candle_index': int(i),
                        'timestamp': str(timestamps[i]),
                        'displacement_ratio': float(round(disp, 2)),
                        'quality': 'INSTITUTIONAL_PRIME' if disp >= 2.2 else 'STANDARD',
                        'in_zone': (lows[i] <= current_price <= highs[i]),
                        'tested': any(highs[k] >= lows[i] for k in range(min(i + 3, len(sub_df)), len(sub_df))) if i + 3 < len(sub_df) else False
                    })

        return obs

    @staticmethod
    def analyze_market_structure(df: pd.DataFrame, window: int = 5) -> Dict[str, Any]:
        """
        Detects Swing Highs, Swing Lows, Market Structure Shifts (MSS),
        and Liquidity Sweeps.
        """
        n = len(df)
        if n < window * 2 + 1:
            return {'structure': 'INSUFFICIENT_DATA', 'bias': 'NEUTRAL', 'swing_high': 0.0, 'swing_low': 0.0}

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        swing_highs = []
        swing_lows = []

        for i in range(window, n - window):
            # Swing High: Highest in local window
            if highs[i] == np.max(highs[i - window : i + window + 1]):
                swing_highs.append((i, highs[i]))
            # Swing Low: Lowest in local window
            if lows[i] == np.min(lows[i - window : i + window + 1]):
                swing_lows.append((i, lows[i]))

        current_close = closes[-1]
        last_high = swing_highs[-1][1] if swing_highs else current_close
        last_low = swing_lows[-1][1] if swing_lows else current_close

        # Check BOS (Break of Structure)
        is_bullish_bos = current_close > last_high
        is_bearish_bos = current_close < last_low

        # Check Liquidity Sweep (High breached by wick but closed below)
        liquidity_sweep = 'NONE'
        if highs[-1] > last_high and current_close < last_high:
            liquidity_sweep = 'BEARISH_BUY_SIDE_LIQUIDITY_SWEPT'
        elif lows[-1] < last_low and current_close > last_low:
            liquidity_sweep = 'BULLISH_SELL_SIDE_LIQUIDITY_SWEPT'

        structure_bias = 'BULLISH' if is_bullish_bos else ('BEARISH' if is_bearish_bos else 'CONSOLIDATION')

        # Institutional Premium vs Discount Pricing & OTE (Optimal Trade Entry: 61.8% - 78.6% Fib)
        range_high = max(last_high, last_low)
        range_low = min(last_high, last_low)
        if range_high == range_low:
            recent_h = float(np.max(highs[-min(n, window * 2):]))
            recent_l = float(np.min(lows[-min(n, window * 2):]))
            range_high = max(range_high, recent_h)
            range_low = min(range_low, recent_l)

        swing_range = max(range_high - range_low, current_close * 0.002, 1e-8)
        equilibrium_price = (range_high + range_low) / 2.0
        price_in_range_pct = float(np.clip(((current_close - range_low) / swing_range) * 100.0, 0.0, 100.0))

        if current_close < equilibrium_price:
            market_zone = 'DISCOUNT'  # Smart Money buying zone
        elif current_close > equilibrium_price:
            market_zone = 'PREMIUM'   # Smart Money distribution zone
        else:
            market_zone = 'EQUILIBRIUM'

        # Institutional Fibonacci Golden Pocket (OTE: 61.8% - 78.6% retracement)
        bull_ote_top = range_high - (0.618 * swing_range)
        bull_ote_bottom = range_high - (0.786 * swing_range)
        bear_ote_bottom = range_low + (0.618 * swing_range)
        bear_ote_top = range_low + (0.786 * swing_range)

        in_bull_ote = (bull_ote_bottom <= current_close <= bull_ote_top)
        in_bear_ote = (bear_ote_bottom <= current_close <= bear_ote_top)

        return {
            'structure': structure_bias,
            'recent_swing_high': float(range_high),
            'recent_swing_low': float(range_low),
            'equilibrium_price': float(round(equilibrium_price, 5)),
            'market_zone': market_zone,
            'price_in_range_pct': float(round(price_in_range_pct, 1)),
            'in_bull_ote': bool(in_bull_ote),
            'in_bear_ote': bool(in_bear_ote),
            'bull_ote_zone': [float(round(bull_ote_bottom, 5)), float(round(bull_ote_top, 5))],
            'bear_ote_zone': [float(round(bear_ote_bottom, 5)), float(round(bear_ote_top, 5))],
            'distance_to_high_pct': float(((range_high - current_close) / current_close) * 100.0),
            'distance_to_low_pct': float(((current_close - range_low) / current_close) * 100.0),
            'liquidity_sweep': liquidity_sweep,
            'swing_highs_count': len(swing_highs),
            'swing_lows_count': len(swing_lows)
        }
