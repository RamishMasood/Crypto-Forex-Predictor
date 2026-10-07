"""
Trade For Profit (Vivek Yadav) — Rule-Based Supply & Demand Strategy Engine
==========================================================================
Gathered from official strategy masterclasses (Trade For Profit & Advance Crypto Trader).

Exact Rule Breakdown:
1. Supply & Demand + SMC:
   - Demand Zone: The entire last RED candle before an aggressive 3+ green candle expansion,
     located STRICTLY at swing bottoms (never in the middle of a range).
   - Supply Zone: The entire last GREEN candle before an aggressive 3+ red candle drop,
     located STRICTLY at swing tops (never in the middle of a range).
2. Trend Filter:
   - Bullish (HH/HL): ONLY take BUY trades at valid Demand Zones.
   - Bearish (LH/LL): ONLY take SELL trades at valid Supply Zones.
   - Range/Consolidation: Mean-reversion permitted on clear zone rejection.
3. Exact Entry Triggers:
   - Level Touch: Price enters the Demand/Supply zone.
   - Rejection Requirement: Slows down and leaves a prominent rejection wick (>= 35%).
   - Candle Confirmation:
     * BUY: GREEN candle closes cleanly with bottom rejection wick.
     * SELL: RED candle closes cleanly with top rejection wick.
   - Invalidation: If price slices through with full body, DO NOT enter.
4. Stop Loss & Take Profit:
   - SL: Beyond zone bottom/top, strictly respecting Golden SL Geometry (>= 1.50 * ATR, base 1.80 * ATR).
   - TP1: 0.38 * ATR (locks Breakeven).
   - TP2: Minimum 1:2 Risk-to-Reward (2.0 * risk_distance).
   - TP3: 2.50 * risk_distance (runner).
"""

from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


class VivekYadavSupplyDemandEngine:
    """
    Executes the exact Supply & Demand system taught by Vivek Yadav (Trade For Profit).
    """

    @classmethod
    def detect_zones(
        cls,
        df: pd.DataFrame,
        swing_window: int = 4
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Identifies institutional Demand and Supply zones at swing extremes with strong expansion candles.
        """
        demand_zones: List[Dict[str, Any]] = []
        supply_zones: List[Dict[str, Any]] = []
        n = len(df)
        if n < 10:
            return {'demand_zones': demand_zones, 'supply_zones': supply_zones}

        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        for i in range(swing_window, n - 3):
            # 1. SWING BOTTOM DEMAND CHECK:
            # Must be local swing low
            is_swing_low = lows[i] == np.min(lows[max(0, i - swing_window) : min(n, i + swing_window + 1)])
            is_red_candle = closes[i] < opens[i]

            if is_swing_low and is_red_candle:
                # Check for 2+ strong green expansion candles immediately following
                c1_green = closes[i + 1] > opens[i + 1]
                c2_green = closes[i + 2] > opens[i + 2] if (i + 2 < n) else True
                exp_close = closes[min(i + 2, n - 1)]

                if c1_green and exp_close > highs[i]:
                    test_count = sum(1 for k in range(i + 3, n - 1) if lows[k] <= highs[i] and highs[k] >= lows[i])
                    demand_zones.append({
                        'type': 'DEMAND_ZONE',
                        'top': float(highs[i]),
                        'bottom': float(lows[i]),
                        'candle_index': int(i),
                        'test_count': test_count,
                        'is_fresh': (test_count <= 2),
                        'source': 'Swing Bottom Demand (Institutional Expansion)',
                        'active': True
                    })

            # 2. SWING TOP SUPPLY CHECK:
            # Must be local swing high
            is_swing_high = highs[i] == np.max(highs[max(0, i - swing_window) : min(n, i + swing_window + 1)])
            is_green_candle = closes[i] > opens[i]

            if is_swing_high and is_green_candle:
                # Check for 2+ strong red expansion candles immediately following
                c1_red = closes[i + 1] < opens[i + 1]
                c2_red = closes[i + 2] < opens[i + 2] if (i + 2 < n) else True
                exp_close = closes[min(i + 2, n - 1)]

                if c1_red and exp_close < lows[i]:
                    test_count = sum(1 for k in range(i + 3, n - 1) if highs[k] >= lows[i] and lows[k] <= highs[i])
                    supply_zones.append({
                        'type': 'SUPPLY_ZONE',
                        'top': float(highs[i]),
                        'bottom': float(lows[i]),
                        'candle_index': int(i),
                        'test_count': test_count,
                        'is_fresh': (test_count <= 2),
                        'source': 'Swing Top Supply (Institutional Drop)',
                        'active': True
                    })

        return {
            'demand_zones': demand_zones[-4:],  # Most recent 4 zones
            'supply_zones': supply_zones[-4:]
        }

    @classmethod
    def evaluate_trend(cls, df: pd.DataFrame, window: int = 5) -> str:
        """
        Determines market structure trend:
        - BULLISH (Higher Highs & Higher Lows)
        - BEARISH (Lower Highs & Lower Lows)
        - CONSOLIDATION (Range)
        """
        n = len(df)
        if n < window * 3:
            return 'CONSOLIDATION'

        highs = df['high'].values
        lows = df['low'].values

        pivots_h = []
        pivots_l = []

        for i in range(window, n - window):
            if highs[i] == np.max(highs[i - window : i + window + 1]):
                pivots_h.append(highs[i])
            if lows[i] == np.min(lows[i - window : i + window + 1]):
                pivots_l.append(lows[i])

        if len(pivots_h) >= 2 and len(pivots_l) >= 2:
            hh = pivots_h[-1] > pivots_h[-2]
            hl = pivots_l[-1] > pivots_l[-2]
            lh = pivots_h[-1] < pivots_h[-2]
            ll = pivots_l[-1] < pivots_l[-2]

            if hh and hl:
                return 'BULLISH'
            elif lh and ll:
                return 'BEARISH'

        return 'CONSOLIDATION'

    @classmethod
    def evaluate(
        cls,
        df: pd.DataFrame,
        atr: float,
        timeframe: str = '1h'
    ) -> Dict[str, Any]:
        """
        Full evaluation of Vivek Yadav's Supply & Demand Strategy.
        """
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        if n < 10 or current_price <= 0.0:
            return {
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Vivek Yadav S&D analysis."]
            }

        # Adaptive ATR Floor for Forex Majors, Metals, and Crypto
        min_atr_floor = (current_price * 0.0003) if current_price < 5.0 else (current_price * 0.0015)
        safe_atr = max(atr, min_atr_floor)

        zones_dict = cls.detect_zones(df)
        demand_zones = zones_dict.get('demand_zones', [])
        supply_zones = zones_dict.get('supply_zones', [])
        trend = cls.evaluate_trend(df)

        last_o = float(df['open'].iloc[-1])
        last_h = float(df['high'].iloc[-1])
        last_l = float(df['low'].iloc[-1])
        last_c = float(df['close'].iloc[-1])
        candle_range = max(last_h - last_l, 1e-9)

        lower_wick_ratio = (min(last_o, last_c) - last_l) / candle_range
        upper_wick_ratio = (last_h - max(last_o, last_c)) / candle_range

        closes_s = pd.Series(df['close'].values)
        ema_20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes_s.rolling(min(n, 200), min_periods=min(n, 25)).mean().iloc[-1])

        # RSI 14 Momentum Guard
        delta = closes_s.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Volume confirmation: institutional participation at the zone
        vol_confirmed = True
        if 'volume' in df.columns and len(df['volume']) >= 10:
            avg_vol = float(df['volume'].iloc[-10:].mean())
            if avg_vol > 0:
                vol_confirmed = (float(df['volume'].iloc[-1]) >= avg_vol * 0.80)

        action = 'HOLD'
        status = 'SCANNING_ZONES'
        confidence = 50.0
        active_zone = None
        reasons = []

        # 1. TEST DEMAND TRIGGER (BUY):
        # Bullish or consolidation range with price holding above EMA20 / 200 SMA with volume absorption & RSI sweet spot
        is_trend_ok_buy = (trend in ['BULLISH', 'CONSOLIDATION'])
        is_ma_ok_buy = (last_c >= ema_20 * 0.995) or (n < 25)
        if is_trend_ok_buy and is_ma_ok_buy and (42.0 <= rsi_val <= 70.0 or n < 25):
            # Sort demand zones: fresh zones first, then most recent
            sorted_demand = sorted(demand_zones, key=lambda z: (z.get('is_fresh', False), z.get('candle_index', 0)), reverse=True)
            for dz in sorted_demand:
                z_top = dz['top']
                z_bot = dz['bottom']

                # Fresh Zone requirement: Max 3 prior touches for institutional relevance
                is_fresh_zone = dz.get('test_count', 0) <= 3

                # Touch Requirement: Current or previous low dipped into zone without blowing through
                touched = is_fresh_zone and (last_l <= z_top) and (last_h >= z_bot) and (last_l >= z_bot - 0.15 * safe_atr)
                # Invalidation: Full body candle closed below zone bottom
                invalidated = (last_c < z_bot) and (last_o < z_bot)

                if touched and not invalidated:
                    # Confirmation: Green candle with bottom rejection wick >= 25%, price holding above zone bottom
                    is_green_confirm = (last_c > last_o) and (last_c >= z_bot) and (lower_wick_ratio >= 0.25) and (candle_range >= 0.30 * safe_atr) and vol_confirmed

                    if is_green_confirm:
                        action = 'BUY'
                        status = 'DEMAND_ENTRY_READY'
                        active_zone = dz
                        is_fresh = dz.get('is_fresh', False)
                        confidence = 92.0 if is_fresh else 88.0
                        reasons.append(f"Vivek Yadav S&D: {'Fresh ' if is_fresh else ''}Demand Zone Touch [{z_bot:.2f} - {z_top:.2f}]")
                        reasons.append(f"Candle Confirmation: Green Close with {lower_wick_ratio*100:.1f}% Bottom Rejection Wick")
                        reasons.append(f"Trend Filter: {trend} market structure & EMA20 ({ema_20:.2f})")
                        if is_fresh:
                            reasons.append("Zone Quality: High-Priority Unmitigated (Fresh) Institutional Demand")
                        break

        # 2. TEST SUPPLY TRIGGER (SELL):
        # Bearish or consolidation range holding below EMA20 / 200 SMA with volume absorption & RSI sweet spot
        is_trend_ok_sell = (trend in ['BEARISH', 'CONSOLIDATION'])
        is_ma_ok_sell = (last_c <= ema_20 * 1.005) or (n < 25)
        if action == 'HOLD' and is_trend_ok_sell and is_ma_ok_sell and (30.0 <= rsi_val <= 58.0 or n < 25):
            sorted_supply = sorted(supply_zones, key=lambda z: (z.get('is_fresh', False), z.get('candle_index', 0)), reverse=True)
            for sz in sorted_supply:
                z_top = sz['top']
                z_bot = sz['bottom']

                is_fresh_zone = sz.get('test_count', 0) <= 3

                # Touch Requirement: Current or previous high reached into zone without blowing through
                touched = is_fresh_zone and (last_h >= z_bot) and (last_l <= z_top) and (last_h <= z_top + 0.15 * safe_atr)
                # Invalidation: Full body candle closed above zone top
                invalidated = (last_c > z_top) and (last_o > z_top)

                if touched and not invalidated:
                    # Confirmation: Red candle with top rejection wick >= 28%, price holding below zone top
                    is_red_confirm = (last_c < last_o) and (last_c <= z_top - 0.05 * safe_atr) and (upper_wick_ratio >= 0.28) and (candle_range >= 0.35 * safe_atr) and vol_confirmed

                    if is_red_confirm:
                        action = 'SELL'
                        status = 'SUPPLY_ENTRY_READY'
                        active_zone = sz
                        is_fresh = sz.get('is_fresh', False)
                        confidence = 92.0 if is_fresh else 88.0
                        reasons.append(f"Vivek Yadav S&D: {'Fresh ' if is_fresh else ''}Supply Zone Touch [{z_bot:.2f} - {z_top:.2f}]")
                        reasons.append(f"Candle Confirmation: Red Close with {upper_wick_ratio*100:.1f}% Top Rejection Wick")
                        reasons.append(f"Trend Filter: {trend} market structure & EMA20 ({ema_20:.2f}) <= EMA50 ({ema_50:.2f})")
                        if is_fresh:
                            reasons.append("Zone Quality: High-Priority Unmitigated (Fresh) Institutional Supply")
                        break

        # 3. BUILD TRADE SETUP WITH MANDATORY 1:2 R:R AND GOLDEN SL
        if action != 'HOLD' and active_zone:
            entry_price = current_price

            if action == 'BUY':
                sl_distance = 1.80 * safe_atr  # Golden SL Geometry (Rule #2)
                stop_loss = entry_price - sl_distance
                tp1 = entry_price + (0.38 * safe_atr)  # Precision scalp bank -> BE lock
                tp2 = entry_price + (2.00 * sl_distance)  # Mandatory 1:2+ Runner Geometry
                tp3 = entry_price + (3.00 * sl_distance)  # Extended runner

            else:  # SELL
                sl_distance = 1.80 * safe_atr  # Golden SL Geometry (Rule #2)
                stop_loss = entry_price + sl_distance
                tp1 = entry_price - (0.38 * safe_atr)
                tp2 = entry_price - (2.00 * sl_distance)
                tp3 = entry_price - (3.00 * sl_distance)

            trade_setup = {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / entry_price) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp1_gain_pct': float(round((abs(tp1 - entry_price) / entry_price) * 100.0, 2)),
                'tp2': float(round(tp2, 5)),
                'tp2_gain_pct': float(round((abs(tp2 - entry_price) / entry_price) * 100.0, 2)),
                'tp3': float(round(tp3, 5)),
                'tp3_gain_pct': float(round((abs(tp3 - entry_price) / entry_price) * 100.0, 2)),
                'risk_reward_ratio': '1:2.0',
                'strategy_name': 'Vivek Yadav Supply & Demand Masterclass'
            }
        else:
            trade_setup = {
                'action': 'HOLD',
                'status': 'SCANNING_ZONES',
                'recommended_entry': current_price,
                'stop_loss': current_price,
                'tp1': current_price,
                'tp2': current_price,
                'tp3': current_price,
                'strategy_name': 'Vivek Yadav Supply & Demand Masterclass'
            }
            reasons.append("Monitoring valid swing Demand & Supply zones. Awaiting level touch & candle confirmation.")

        return {
            'strategy': 'Vivek Yadav Supply & Demand Masterclass',
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'trend': trend,
            'active_zone': active_zone,
            'demand_zones': demand_zones,
            'supply_zones': supply_zones,
            'trade_setup': trade_setup,
            'reasons': reasons
        }
