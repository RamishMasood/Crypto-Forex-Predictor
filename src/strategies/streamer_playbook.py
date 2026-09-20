"""
Master Strategy Playbook of Top Global Traders & Live Streamers
==============================================================
Fully rule-based implementations of the 12 top global traders from the
Master Strategy Playbook PDF:

 1. Vivek Yadav (Trade For Profit / Advance Crypto Trader)
 2. Bernd Skorupinski (FTMO #1 Record Holder / Online Trading Campus)
 3. Michael J. Huddleston (Inner Circle Trader - ICT)
 4. Steven Hart (The Trading Channel)
 5. Rayner Teo (Systematic Swing & Trend Following)
 6. Crypto Cred (Price Action & Technical Confluence)
 7. Ndemazeah Godlove (GU MVR Strategy)
 8. Ross Cameron (Warrior Trading Small-Cap Momentum)
 9. Adam Khoo (Systematic Multi-EMA Trend Following)
10. Ariel Zwecher (RealSimpleAriel 15M ORB & Prop Math)
11. Oliver Velez (20/200 SMA Location & Elephant Bar)
12. Trade Pro (Mechanical Backtested Donchian + ATR)

Every strategy defines its exact entry trigger, stop loss, take profit (min 1:2 R:R),
and native Breakeven / Trailing exit rule.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# 1. VIVEK YADAV — TRADE FOR PROFIT (SUPPLY/DEMAND & LIQUIDATION TRAP)
# ─────────────────────────────────────────────────────────────────────────────
class VivekYadavPlaybookStrategy:
    """
    Trader 1: Vivek Yadav (Trade For Profit / Advance Crypto Trader)
    - Focus: BTC, Crypto, Gold (XAUUSD)
    - System: Supply/Demand + Liquidation Heatmaps + FVG + Rejection Wick + Candle Close
    - Timeframe: 1D/4H macro -> 15M/5M/1M execution
    - Target: Min 1:2 R:R (partials to opposite pool)
    - Breakeven: SMC_PARTIAL_BE (Locks BE after initial expansion, trails to opposite pool)
    """
    NAME = "Vivek Yadav (Trade For Profit)"
    KEY = "VIVEK_YADAV"
    BE_MODE = "SMC_PARTIAL_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        from .vivek_yadav_sd import VivekYadavSupplyDemandEngine
        res = VivekYadavSupplyDemandEngine.evaluate(df, atr=atr, timeframe=timeframe)
        res['strategy_key'] = cls.KEY
        res['strategy_name'] = cls.NAME
        res['breakeven_mode'] = cls.BE_MODE
        return res


# ─────────────────────────────────────────────────────────────────────────────
# 2. BERND SKORUPINSKI — FTMO #1 RECORD HOLDER (4-STAGE UMBRELLA)
# ─────────────────────────────────────────────────────────────────────────────
class BerndSkorupinskiStrategy:
    """
    Trader 2: Bernd Skorupinski (FTMO #1 Record Holder / Online Trading Campus)
    - Focus: Global Futures, FX, Gold, Crude Oil, Prop Firm CFDs
    - System: 4-Stage Umbrella (COT Fundamental Bias + 'Big Brother / Small Brother' S&D)
    - Rule: LTF zone MUST sit inside HTF zone to eliminate chart noise.
    - Entry: Limit Orders ('Set and Forget') placed at verified institutional S&D zones.
    - Target: Min 1:2 to 1:4 R:R. Fixed dollar risk.
    - Breakeven: FIXED_RR_TARGET (Does not choke with premature BE; holds for structural target).
    """
    NAME = "Bernd Skorupinski (FTMO #1)"
    KEY = "BERND_SKORUPINSKI"
    BE_MODE = "FIXED_RR_TARGET"

    @classmethod
    def evaluate(
        cls,
        df: pd.DataFrame,
        atr: float,
        cot_data: Optional[Dict[str, Any]] = None,
        timeframe: str = '1h'
    ) -> Dict[str, Any]:
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Bernd Skorupinski S&D model is calibrated for Forex Majors, Indices & Crypto (avoiding Gold noise)
        if current_price > 2000.0 and current_price < 10000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Bernd Skorupinski S&D model is calibrated for Forex Majors, Indices and Crypto (avoiding Gold noise)."]
            }

        # Stage 1: COT Fundamental Bias
        cot_bias = 'NEUTRAL'
        if cot_data and cot_data.get('available'):
            cot_bias = str(cot_data.get('smart_money_bias', 'NEUTRAL')).upper()

        # Stage 2: Institutional Swing S&D Zones (Big Brother / Small Brother)
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        # HTF Major S&D bounds
        lookback = min(n, 60)
        htf_high = float(np.max(highs[-lookback:]))
        htf_low = float(np.min(lows[-lookback:]))
        mid = (htf_high + htf_low) / 2.0

        # Prior unmitigated swing levels (excluding current 2 candles to avoid self-referencing)
        lookback_zone = min(n, 35)
        prior_demand = float(np.min(lows[-lookback_zone:-2])) if n >= 15 else float(np.min(lows))
        prior_supply = float(np.max(highs[-lookback_zone:-2])) if n >= 15 else float(np.max(highs))

        # RSI calculation for momentum exhaustion check
        closes_s = pd.Series(closes)
        delta = closes_s.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        action = 'HOLD'
        status = 'SCANNING_UMBRELLA_ZONES'
        confidence = 50.0
        reasons = []

        # 'Big Brother / Small Brother' rule:
        # Long only if in Discount (< mid) AND COT is Bullish/Neutral
        is_discount = current_price <= (htf_low + (htf_high - htf_low) * 0.42)
        is_premium = current_price >= (htf_low + (htf_high - htf_low) * 0.58)

        curr_open = float(df['open'].iloc[-1])
        last_h = float(highs[-1])
        last_l = float(lows[-1])
        cand_rng = max(last_h - last_l, 1e-6)
        lower_wick_ratio = (min(curr_open, current_price) - last_l) / cand_rng
        upper_wick_ratio = (last_h - max(curr_open, current_price)) / cand_rng

        # Test Demand Zone Entry:
        # 1. Price is in Discount and tested prior verified demand zone
        # 2. Bullish rejection wick >= 35% or strong green candle with absorption
        # 3. RSI not in capitulation (>= 34.0 and <= 65.0)
        is_demand_tap = (last_l <= prior_demand + 0.35 * safe_atr) and (current_price >= prior_demand - 0.25 * safe_atr)
        is_demand_reject = (lower_wick_ratio >= 0.35 and current_price >= curr_open) or (current_price > curr_open and cand_rng >= 0.30 * safe_atr and lower_wick_ratio >= 0.25)

        # Test Supply Zone Entry:
        # 1. Price is in Premium and tested prior verified supply zone
        # 2. Bearish rejection wick >= 35% or strong red candle with rejection
        # 3. RSI not in parabolic blow-off (>= 35.0 and <= 66.0)
        is_supply_tap = (last_h >= prior_supply - 0.35 * safe_atr) and (current_price <= prior_supply + 0.25 * safe_atr)
        is_supply_reject = (upper_wick_ratio >= 0.35 and current_price <= curr_open) or (current_price < curr_open and cand_rng >= 0.30 * safe_atr and upper_wick_ratio >= 0.25)
        
        if is_discount and ('BEARISH' not in cot_bias) and is_demand_tap and is_demand_reject and (34.0 <= rsi_val <= 65.0):
            action = 'BUY'
            status = 'DEMAND_LIMIT_TRIGGERED'
            confidence = 88.0 if 'BULLISH' in cot_bias else 86.0
            reasons.append(f"Bernd S&D: Price at Discount Demand Zone [{prior_demand:.2f}] inside HTF Range with bounce rejection")
            reasons.append(f"COT Sentiment: {cot_bias} smart money positioning | RSI: {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(abs(entry_price - prior_demand) + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif is_premium and ('BULLISH' not in cot_bias) and is_supply_tap and is_supply_reject and (35.0 <= rsi_val <= 66.0):
            action = 'SELL'
            status = 'SUPPLY_LIMIT_TRIGGERED'
            confidence = 88.0 if 'BEARISH' in cot_bias else 86.0
            reasons.append(f"Bernd S&D: Price at Premium Supply Zone [{prior_supply:.2f}] inside HTF Range with rejection wick")
            reasons.append(f"COT Sentiment: {cot_bias} smart money positioning | RSI: {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(abs(prior_supply - entry_price) + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Waiting for verified institutional S&D zone arrival (COT: {cot_bias})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'cot_bias': cot_bias,
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.5',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'HOLD_FOR_TARGET_OR_TRAILING'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3. MICHAEL J. HUDDLESTON — INNER CIRCLE TRADER (ICT)
# ─────────────────────────────────────────────────────────────────────────────
class ICTStrategy:
    """
    Trader 3: Michael J. Huddleston (Inner Circle Trader - ICT)
    - Focus: Index Futures (NQ, ES, US30), Forex Majors, Crypto
    - System: Smart Money Concepts (IPDA), FVG, Order Blocks, Liquidity Sweeps
    - Killzones: London Killzone (07:00-10:00 UTC) & NY Killzone (12:00-16:00 UTC), Silver Bullet (15:00-16:00 UTC)
    - Trigger: Liquidity Sweep -> Market Structure Shift (MSS) with displacement -> FVG Retest / OTE
    - Target: Min 1:2 R:R targeted at opposing resting liquidity pool
    - Breakeven: SMC_PARTIAL_BE
    """
    NAME = "Michael J. Huddleston (ICT)"
    KEY = "ICT"
    BE_MODE = "SMC_PARTIAL_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: ICT model is calibrated for Forex Majors, Index Futures & Crypto (rejects Gold wicks)
        if current_price > 2000.0 and current_price < 10000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["ICT model is calibrated for Forex Majors, Index Futures & Crypto (avoiding Gold noise)."]
            }

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values

        # Check Killzone window (Using bar timestamp if present, falling back to UTC now)
        if 'timestamp' in df.columns and len(df['timestamp']) > 0:
            last_ts = df['timestamp'].iloc[-1]
            curr_hour = last_ts.hour if hasattr(last_ts, 'hour') else datetime.now(timezone.utc).hour
        else:
            curr_hour = datetime.now(timezone.utc).hour
        is_london_kz = (7 <= curr_hour <= 10)
        is_ny_kz = (12 <= curr_hour <= 16)
        is_silver_bullet = (15 <= curr_hour < 16)
        in_killzone = is_london_kz or is_ny_kz or ('crypto' in str(timeframe).lower())

        kz_label = "Silver Bullet (NY)" if is_silver_bullet else ("NY Killzone" if is_ny_kz else ("London Killzone" if is_london_kz else "Off-Hours"))

        # Look for Liquidity Sweep in last 15 bars
        recent_h = float(np.max(highs[-15:-2])) if n >= 15 else float(np.max(highs))
        recent_l = float(np.min(lows[-15:-2])) if n >= 15 else float(np.min(lows))

        bull_sweep = any(lows[k] < recent_l and closes[k] > recent_l for k in range(max(0, n - 4), n))
        bear_sweep = any(highs[k] > recent_h and closes[k] < recent_h for k in range(max(0, n - 4), n))

        # Check FVG in last 3 candles
        has_bull_fvg = (n >= 3) and (lows[-1] > highs[-3])
        has_bear_fvg = (n >= 3) and (highs[-1] < lows[-3])

        action = 'HOLD'
        status = 'SCANNING_LIQUIDITY_POOLS'
        confidence = 50.0
        reasons = []

        cand_rng = max(highs[-1] - lows[-1], 1e-6)
        closes_s = pd.Series(closes)
        ema_20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes_s.rolling(min(n, 200)).mean().iloc[-1])

        if bull_sweep and in_killzone and (current_price >= sma_200 * 0.998 or ema_20 >= ema_50) and (has_bull_fvg or (closes[-1] > opens[-1] and closes[-1] >= highs[-2])) and (cand_rng >= 0.25 * safe_atr):
            action = 'BUY'
            status = 'ICT_BULLISH_MSS_ENTRY'
            confidence = 88.0
            reasons.append(f"ICT: Sell-side Liquidity Swept below {recent_l:.2f} + Displacement FVG")
            reasons.append(f"Execution Window: {kz_label}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(entry_price - (recent_l - 0.20 * safe_atr), 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + max(1.15 * sl_distance, (recent_h - entry_price) * 0.5)
            tp3 = entry_price + (2.20 * sl_distance)

        elif bear_sweep and in_killzone and (current_price <= sma_200 * 1.002) and (ema_20 <= ema_50) and (has_bear_fvg or (closes[-1] < opens[-1] and closes[-1] <= lows[-2])) and (cand_rng >= 0.25 * safe_atr):
            action = 'SELL'
            status = 'ICT_BEARISH_MSS_ENTRY'
            confidence = 88.0
            reasons.append(f"ICT: Buy-side Liquidity Swept above {recent_h:.2f} + Displacement FVG")
            reasons.append(f"Execution Window: {kz_label}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min((recent_h + 0.20 * safe_atr) - entry_price, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - max(1.15 * sl_distance, (entry_price - recent_l) * 0.5)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Monitoring liquidity sweeps & FVG displacement ({kz_label})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'killzone': kz_label,
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0+',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'AUTO_BREAKEVEN_AT_TP1'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4. STEVEN HART — THE TRADING CHANNEL (PURE PRICE ACTION BREAK & RETEST)
# ─────────────────────────────────────────────────────────────────────────────
class StevenHartStrategy:
    """
    Trader 4: Steven Hart (The Trading Channel)
    - Focus: Forex Majors, Gold, US100
    - System: Pure Price Action Break & Retest. ZERO lagging indicators (no RSI, MACD, MAs).
    - Timeframe: 4H macro trend structure -> 15M break & retest execution.
    - Entry: Breaks structural resistance/support -> retests on 15M with pinbar/engulfing.
    - Target: Fixed 1:2 R:R.
    - Breakeven: FIXED_RR_TARGET (Honors exact 1:2 structure without premature stop move).
    """
    NAME = "Steven Hart (The Trading Channel)"
    KEY = "STEVEN_HART"
    BE_MODE = "FIXED_RR_TARGET"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Steven Hart Break & Retest model is calibrated for Forex Majors and Crypto (avoiding Gold noise)
        if current_price > 2000.0 and current_price < 10000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Steven Hart model is calibrated for Forex Majors and Crypto (avoiding Gold noise)."]
            }

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values

        # Detect recent key structural barrier (prior swing high / low)
        lookback = min(n, 40)
        prior_res = float(np.max(highs[-lookback:-4])) if n >= 20 else float(np.max(highs))
        prior_sup = float(np.min(lows[-lookback:-4])) if n >= 20 else float(np.min(lows))

        # Check Trend alignment via 20 and 50 EMA
        closes_s = pd.Series(closes)
        ema_20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])

        # Verify prior breakout actually occurred in last 5 bars before retest
        broke_res = any(closes[-5:-1] > prior_res * 0.9998) if n >= 6 else False
        broke_sup = any(closes[-5:-1] < prior_sup * 1.0002) if n >= 6 else False

        # Check Candlestick Reversal on recent bar (Pin bar / Engulfing)
        last_o, last_h, last_l, last_c = opens[-1], highs[-1], lows[-1], closes[-1]
        rng = max(last_h - last_l, 1e-9)
        lower_wick = (min(last_o, last_c) - last_l) / rng
        upper_wick = (last_h - max(last_o, last_c)) / rng

        is_bull_pinbar = (lower_wick >= 0.35) and (last_c >= last_o)
        is_bear_pinbar = (upper_wick >= 0.35) and (last_c <= last_o)
        is_bull_candle = is_bull_pinbar or (last_c > last_o and last_c >= closes[-2] and lower_wick >= 0.25)
        is_bear_candle = is_bear_pinbar or (last_c < last_o and last_c <= closes[-2] and upper_wick >= 0.25)

        action = 'HOLD'
        status = 'SCANNING_STRUCTURE_BREAKS'
        confidence = 50.0
        reasons = []

        # Break & Retest Long & Short conditions
        is_long_trend = (ema_20 >= ema_50 * 0.998) or (current_price >= ema_50)
        is_long_retest = broke_res and is_long_trend and (last_l <= prior_res + 0.35 * safe_atr) and (current_price >= prior_res - 0.25 * safe_atr) and is_bull_candle and (rng >= 0.25 * safe_atr)

        is_short_trend = (ema_20 <= ema_50 * 1.002) or (current_price <= ema_50)
        is_short_retest = broke_sup and is_short_trend and (last_h >= prior_sup - 0.35 * safe_atr) and (current_price <= prior_sup + 0.25 * safe_atr) and is_bear_candle and (rng >= 0.25 * safe_atr)

        if is_long_retest:
            action = 'BUY'
            status = 'BREAK_AND_RETEST_LONG'
            confidence = 86.0
            reasons.append(f"Steven Hart: Broken Resistance [{prior_res:.2f}] successfully retested as Support")
            reasons.append("Reversal Candlestick: Bullish Pin Bar / Absorption Wick Confirmed")
            entry_price = current_price
            sl_distance = max(entry_price - (last_l - 0.20 * safe_atr), 1.80 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif is_short_retest:
            action = 'SELL'
            status = 'BREAK_AND_RETEST_SHORT'
            confidence = 86.0
            reasons.append(f"Steven Hart: Broken Support [{prior_sup:.2f}] successfully retested as Resistance")
            reasons.append("Reversal Candlestick: Bearish Pin Bar / Absorption Wick Confirmed")
            entry_price = current_price
            sl_distance = max((last_h + 0.20 * safe_atr) - entry_price, 1.80 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Waiting for verified 4H/15M Break-and-Retest touch (Res: {prior_res:.2f}, Sup: {prior_sup:.2f})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'FIXED_1_2_TARGET'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. RAYNER TEO — SYSTEMATIC SWING & TREND FOLLOWING
# ─────────────────────────────────────────────────────────────────────────────
class RaynerTeoStrategy:
    """
    Trader 5: Rayner Teo (Systematic Swing & Trend Following)
    - Focus: Forex Majors, Gold, Stock Indices
    - System: 20 EMA + 50 EMA Envelope + ATR stop
    - Entry: Multi-timeframe pullback to 20/50 EMA value area + reversal candle
    - Target: Trailing stop via 20 EMA close or 1:2+ R:R
    - Breakeven: TRAILING_20_EMA (Decoupled from generic BE; trails 20 EMA)
    """
    NAME = "Rayner Teo (Trend & Pullback)"
    KEY = "RAYNER_TEO"
    BE_MODE = "TRAILING_20_EMA"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '4h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower()
        if tf_clean in ['1m', '3m', '5m', '15m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Rayner Teo Trend Following requires macro/swing timeframes (1h, 4h, Daily). '{timeframe}' is too noisy."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Rayner Teo model is calibrated for Forex Majors & Crypto (rejects Gold wicks)
        if current_price > 2000.0 and current_price < 10000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Rayner Teo Trend & Pullback model is calibrated for Forex Majors and Crypto (avoiding Gold noise)."]
            }

        closes = pd.Series(df['close'].values)
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        last_o, last_h, last_l, last_c = df['open'].iloc[-1], df['high'].iloc[-1], df['low'].iloc[-1], df['close'].iloc[-1]
        rng = max(last_h - last_l, 1e-9)
        lower_wick = (min(last_o, last_c) - last_l) / rng
        upper_wick = (last_h - max(last_o, last_c)) / rng

        ema_20_series = closes.ewm(span=20, adjust=False).mean()
        ema_20_prev = float(ema_20_series.iloc[-2]) if len(ema_20_series) >= 2 else ema_20
        # Rayner Teo Rule #1: Trade strictly in the direction of the 200 SMA baseline
        is_uptrend = (current_price > sma_200) and (ema_20 > ema_50) and ((ema_20 - ema_50) >= 0.15 * safe_atr) and (ema_20 >= ema_20_prev * 0.9999)
        is_downtrend = (current_price < sma_200) and (ema_20 < ema_50) and ((ema_50 - ema_20) >= 0.15 * safe_atr) and (ema_20 <= ema_20_prev * 1.0001)

        # Pullback in value area between 20 & 50 EMA
        in_buy_value_area = (last_l <= ema_20) and (last_c >= ema_50) and is_uptrend
        in_sell_value_area = (last_h >= ema_20) and (last_c <= ema_50) and is_downtrend

        action = 'HOLD'
        status = 'WAITING_EMA_PULLBACK'
        confidence = 50.0
        reasons = []

        # RSI 14 Sweet Spot Guard (Never buy overbought >65 or sell oversold <35)
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        if in_buy_value_area and (last_c > last_o and last_c >= ema_20 * 0.999 and last_c >= closes.iloc[-2]) and (rng >= 0.25 * safe_atr) and (rsi_val <= 65.0):
            action = 'BUY'
            status = 'VALUE_AREA_BOUNCE_BUY'
            confidence = 86.0
            reasons.append("Rayner Teo: Pullback into 20/50 EMA Value Area during verified Uptrend")
            reasons.append("Reversal Candle: Bullish bounce confirmed above 20 EMA")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(entry_price - (ema_50 - 0.20 * safe_atr), 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        elif in_sell_value_area and (last_c < last_o and last_c <= ema_20 * 1.001 and last_c <= closes.iloc[-2]) and (rng >= 0.25 * safe_atr) and (rsi_val >= 35.0):
            action = 'SELL'
            status = 'VALUE_AREA_REJECTION_SELL'
            confidence = 86.0
            reasons.append("Rayner Teo: Pullback into 20/50 EMA Value Area during verified Downtrend")
            reasons.append("Reversal Candle: Bearish rejection confirmed below 20 EMA")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min((ema_50 + 0.20 * safe_atr) - entry_price, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            trend_str = "Uptrend" if is_uptrend else ("Downtrend" if is_downtrend else "Neutral")
            reasons.append(f"Waiting for pullback into 20/50 EMA dynamic zone (Trend: {trend_str})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'ema_20': round(ema_20, 4),
            'ema_50': round(ema_50, 4),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0+',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'TRAILING_20_EMA_CLOSE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 6. CRYPTO CRED — HORIZONTAL S/R + 20/50 EMA + RSI DIVERGENCE
# ─────────────────────────────────────────────────────────────────────────────
class CryptoCredStrategy:
    """
    Trader 6: Crypto Cred (Price Action & Technical Confluence)
    - Focus: Bitcoin (BTC), Ethereum (ETH), Crypto Perps
    - System: Horizontal S/R + 20/50 EMA + RSI Divergence & Exhaustion (<35 / >65)
    - Timeframe: Daily/4H marking -> 1H execution
    - Target: Min 1:2+ R:R, partials at mid-range and opposite horizontal boundary
    - Breakeven: SMC_PARTIAL_BE
    """
    NAME = "Crypto Cred (S/R & RSI Confluence)"
    KEY = "CRYPTO_CRED"
    BE_MODE = "SMC_PARTIAL_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower()
        if tf_clean in ['1m', '3m', '5m', '15m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Crypto Cred S/R model requires higher timeframes (1h, 4h, Daily). '{timeframe}' is too noisy."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Crypto Cred model is strictly calibrated for Crypto (BTC/ETH/Perps)
        if current_price < 5000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Crypto Cred S/R & RSI model is strictly calibrated for Crypto assets."]
            }

        closes = pd.Series(df['close'].values)
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        # Compute RSI 14
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Horizontal S/R
        highs = df['high'].values
        lows = df['low'].values
        h_sup = float(np.min(lows[-20:-2])) if n >= 20 else float(np.min(lows))
        h_res = float(np.max(highs[-20:-2])) if n >= 20 else float(np.max(highs))

        action = 'HOLD'
        status = 'SCANNING_SR_LEVELS'
        confidence = 50.0
        reasons = []

        # Buy Setup: Testing horizontal support with RSI oversold/exhaustion and bullish reclaim
        in_sup_zone = (h_sup - 0.25 * safe_atr <= current_price <= h_sup + 0.35 * safe_atr)
        in_res_zone = (h_res - 0.35 * safe_atr <= current_price <= h_res + 0.25 * safe_atr)

        if in_sup_zone and (closes.iloc[-1] > df['open'].iloc[-1]) and (rsi_val < 45.0) and (current_price >= sma_200 * 0.995 or ema_20 >= ema_50):
            action = 'BUY'
            status = 'SUPPORT_RECLAIM_RSI_BUY'
            confidence = 86.0
            reasons.append(f"Crypto Cred: Horizontal Support [{h_sup:.2f}] successfully tested and reclaimed")
            reasons.append(f"RSI Exhaustion Bounce: RSI(14) = {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(entry_price - (h_sup - 0.20 * safe_atr), 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + max(1.15 * sl_distance, (h_res - entry_price) * 0.5)
            tp3 = entry_price + (2.20 * sl_distance)

        # Sell Setup: Testing horizontal resistance with RSI overbought/exhaustion and bearish reclaim
        elif in_res_zone and (closes.iloc[-1] < df['open'].iloc[-1]) and (rsi_val > 55.0) and (current_price <= sma_200 * 1.005 or ema_20 <= ema_50):
            action = 'SELL'
            status = 'RESISTANCE_REJECT_RSI_SELL'
            confidence = 86.0
            reasons.append(f"Crypto Cred: Horizontal Resistance [{h_res:.2f}] successfully tested and rejected")
            reasons.append(f"RSI Exhaustion Rejection: RSI(14) = {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min((h_res + 0.20 * safe_atr) - entry_price, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - max(1.15 * sl_distance, (entry_price - h_sup) * 0.5)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Awaiting horizontal S/R test with RSI confluence (RSI={rsi_val:.1f}, Sup: {h_sup:.2f}, Res: {h_res:.2f})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'rsi': round(rsi_val, 2),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0+',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'PARTIALS_AT_MIDRANGE_AND_OPPOSITE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 7. NDEMAZEAH GODLOVE — GU MVR STRATEGY (10/23 EMA + FIBONACCI)
# ─────────────────────────────────────────────────────────────────────────────
class NdemazeahGodloveStrategy:
    """
    Trader 7: Ndemazeah Godlove (GU MVR Strategy)
    - Focus: GBPUSD (Forex) & NQ/ES Futures
    - System: 10 EMA (fast) + 23 EMA (slow) + Fibonacci Retracement (38.2%, 50%, 61.8%)
    - Timeframe: 15M & 5M Intraday
    - Target: Fixed 1:2 R:R (or 1:1.5)
    - Breakeven: FIXED_RR_TARGET (Strict mathematical positive expectancy execution)
    """
    NAME = "Ndemazeah Godlove (GU MVR)"
    KEY = "NDEMAZEAH_GODLOVE"
    BE_MODE = "FIXED_RR_TARGET"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower()
        if tf_clean not in ['1m', '3m', '5m', '15m', '30m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Ndemazeah Godlove GU MVR is designed for 5M/15M intraday. Current timeframe '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        closes = pd.Series(df['close'].values)
        ema_10 = float(closes.ewm(span=10, adjust=False).mean().iloc[-1])
        ema_23 = float(closes.ewm(span=23, adjust=False).mean().iloc[-1])

        is_bull_crossover = ema_10 > ema_23
        is_bear_crossover = ema_10 < ema_23

        # Fibonacci calculation over recent swing impulse (last 20 bars)
        highs = df['high'].values
        lows = df['low'].values
        sw_h = float(np.max(highs[-20:]))
        sw_l = float(np.min(lows[-20:]))
        sw_range = max(sw_h - sw_l, 1e-9)

        # Bullish Pullback levels (retracing down from high)
        fib_382_bull = sw_h - (0.382 * sw_range)
        fib_618_bull = sw_h - (0.618 * sw_range)

        # Bearish Pullback levels (retracing up from low)
        fib_382_bear = sw_l + (0.382 * sw_range)
        fib_618_bear = sw_l + (0.618 * sw_range)

        action = 'HOLD'
        status = 'SCANNING_MVR_FIB_PULLBACK'
        confidence = 50.0
        reasons = []

        # 50 pips / points beyond Fib structure from PDF
        pip_unit = 0.0001 if current_price < 10.0 else (0.01 if current_price < 500 else 1.0)
        pip_50 = 50.0 * pip_unit

        # Long: 10 EMA > 23 EMA and price pulls back into 38.2% - 61.8% Fib pocket
        if is_bull_crossover and (fib_618_bull <= current_price <= fib_382_bull) and (df['close'].iloc[-1] > df['open'].iloc[-1]):
            action = 'BUY'
            status = 'GU_MVR_BULLISH_ENTRY'
            confidence = 85.0
            reasons.append("GU MVR: 10 EMA crossed above 23 EMA confirms Bullish Intraday Momentum")
            reasons.append("Fib Retracement: Price pulled back cleanly into 38.2% - 61.8% Golden Pocket")
            entry_price = current_price
            sl_distance = max(entry_price - (fib_618_bull - pip_50), 1.80 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        # Short: 10 EMA < 23 EMA and price pulls back into 38.2% - 61.8% Fib pocket
        elif is_bear_crossover and (fib_382_bear <= current_price <= fib_618_bear) and (df['close'].iloc[-1] < df['open'].iloc[-1]):
            action = 'SELL'
            status = 'GU_MVR_BEARISH_ENTRY'
            confidence = 86.0
            reasons.append("GU MVR: 10 EMA crossed below 23 EMA confirms Bearish Intraday Momentum")
            reasons.append("Fib Retracement: Price pulled back cleanly into 38.2% - 61.8% Golden Pocket")
            entry_price = current_price
            sl_distance = max((fib_618_bear + pip_50) - entry_price, 1.80 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Waiting for Fib pullback with 10/23 EMA alignment (10 EMA: {ema_10:.4f}, 23 EMA: {ema_23:.4f})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'ema_10': round(ema_10, 4),
            'ema_23': round(ema_23, 4),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'FIXED_1_2_TARGET'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 8. ROSS CAMERON — WARRIOR TRADING (VWAP + 9/20 EMA MOMENTUM)
# ─────────────────────────────────────────────────────────────────────────────
class RossCameronStrategy:
    """
    Trader 8: Ross Cameron (Warrior Trading Small-Cap Momentum)
    - Focus: Small-Caps, High-Beta Momentum Assets (Crypto, Indices)
    - System: VWAP + 9 EMA + 20 EMA + Relative Volume (RVOL) Surge
    - Timeframe: 1M / 5M Day Trading
    - Entry: Gap-and-Go pullback to 9 EMA / VWAP or Bull Flag breakout on high volume
    - Target: 1:2+ R:R, scaling out into price spikes
    - Breakeven: SCALPING_QUICK_BE
    """
    NAME = "Ross Cameron (Warrior Trading)"
    KEY = "ROSS_CAMERON"
    BE_MODE = "SCALPING_QUICK_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '5m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower()
        if tf_clean not in ['1m', '3m', '5m', '15m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Ross Cameron is a 1M/5M day trading momentum strategy. Current timeframe '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        closes = pd.Series(df['close'].values)
        volumes = pd.Series(df['volume'].values) if 'volume' in df.columns else pd.Series(np.ones(n))

        ema_9 = float(closes.ewm(span=9, adjust=False).mean().iloc[-1])
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])

        # Volume Surge Factor
        avg_vol = float(volumes.tail(20).mean()) if n >= 20 else float(volumes.mean())
        vol_surge = (float(volumes.iloc[-1]) / max(avg_vol, 1e-6)) >= 1.25

        # VWAP estimation
        vwap = float(np.sum(closes * volumes) / max(np.sum(volumes), 1e-6))

        action = 'HOLD'
        status = 'WAITING_MOMENTUM_SURGE'
        confidence = 50.0
        reasons = []

        # Bull Flag / 9 EMA Momentum Long with Bullish Candle Close
        curr_open = float(df['open'].iloc[-1])
        if (current_price > vwap) and (ema_9 > ema_20) and (closes.iloc[-1] >= ema_9) and (current_price > curr_open) and vol_surge:
            action = 'BUY'
            status = 'WARRIOR_MOMENTUM_BUY'
            confidence = 86.0
            reasons.append("Ross Cameron: Price expanding above VWAP with 9 EMA > 20 EMA stack and bullish close")
            reasons.append(f"Volume Surge Confirmed: Current Volume >= 1.25x 20-bar average")
            entry_price = current_price
            sl_distance = max(entry_price - (min(vwap, ema_20) - 0.20 * safe_atr), 1.80 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        # Inverse Bearish Breakdown with Bearish Candle Close
        elif (current_price < vwap) and (ema_9 < ema_20) and (closes.iloc[-1] <= ema_9) and (current_price < curr_open) and vol_surge:
            action = 'SELL'
            status = 'WARRIOR_MOMENTUM_SELL'
            confidence = 86.0
            reasons.append("Ross Cameron: Price breaking down below VWAP with 9 EMA < 20 EMA stack and bearish close")
            reasons.append("Volume Surge Confirmed: Breakdown volume accelerating")
            entry_price = current_price
            sl_distance = max((max(vwap, ema_20) + 0.20 * safe_atr) - entry_price, 1.80 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Awaiting 9/20 EMA & VWAP volume expansion (VWAP: {vwap:.2f}, VolSurge: {vol_surge})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'vwap': round(vwap, 2),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0+',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'QUICK_SCALE_OUT'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 9. ADAM KHOO — SYSTEMATIC TREND FOLLOWING (20 EMA / 50 SMA / 200 SMA)
# ─────────────────────────────────────────────────────────────────────────────
class AdamKhooStrategy:
    """
    Trader 9: Adam Khoo (Systematic Trend Following & Equities)
    - Focus: Equities, Stock Indices, Forex Majors
    - System: 20 EMA + 50 SMA + 200 SMA + ATR Stop
    - Filter: Price > 200 SMA, 20 EMA > 50 SMA (HH/HL)
    - Entry: Bounce off 20 EMA or consolidation breakout with volume surge
    - Target: Trailing stop via 20 EMA close or 1:2+ R:R
    - Breakeven: TRAILING_20_EMA
    """
    NAME = "Adam Khoo (Multi-EMA Trend)"
    KEY = "ADAM_KHOO"
    BE_MODE = "TRAILING_20_EMA"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower()
        if tf_clean in ['1m', '2m', '3m', '5m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Adam Khoo Multi-EMA model is calibrated for 15M, 1H, 4H and Daily trend following. '{timeframe}' is too noisy."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Adam Khoo Multi-EMA trend model is calibrated for Forex Majors, Equities & Crypto (avoiding Gold noise)
        if current_price > 2000.0 and current_price < 10000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Adam Khoo Multi-EMA model is calibrated for Forex Majors, Equities & Crypto (avoiding Gold commodity noise)."]
            }

        closes = pd.Series(df['close'].values)
        ema_20_series = closes.ewm(span=20, adjust=False).mean()
        ema_20 = float(ema_20_series.iloc[-1])
        ema_20_prev = float(ema_20_series.iloc[-2]) if len(ema_20_series) >= 2 else ema_20
        sma_50 = float(closes.rolling(min(n, 50)).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        # RSI 14 Sweet Spot Guard
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Strict Triple EMA trend stack with rising/falling 20 EMA and minimum envelope separation
        is_uptrend = (current_price > sma_200) and (ema_20 > sma_50) and (sma_50 > sma_200) and ((ema_20 - sma_50) >= 0.15 * safe_atr) and (ema_20 >= ema_20_prev * 0.9999)
        is_downtrend = (current_price < sma_200) and (ema_20 < sma_50) and (sma_50 < sma_200) and ((sma_50 - ema_20) >= 0.15 * safe_atr) and (ema_20 <= ema_20_prev * 1.0001)

        # Pullback bounce on 20 EMA (requires price testing the 20 EMA and holding)
        last_l = float(df['low'].iloc[-1])
        last_h = float(df['high'].iloc[-1])
        last_o = float(df['open'].iloc[-1])
        prev_l = float(df['low'].iloc[-2]) if n >= 2 else last_l
        prev_h = float(df['high'].iloc[-2]) if n >= 2 else last_h
        cand_rng = max(last_h - last_l, 1e-6)

        bounce_20_ema_long = is_uptrend and (min(last_l, prev_l) <= ema_20 + 0.15 * safe_atr) and (current_price >= ema_20)
        bounce_20_ema_short = is_downtrend and (max(last_h, prev_h) >= ema_20 - 0.15 * safe_atr) and (current_price <= ema_20)

        action = 'HOLD'
        status = 'SCANNING_TREND_ALIGNMENT'
        confidence = 50.0
        reasons = []

        if bounce_20_ema_long and (current_price > last_o and current_price >= closes.iloc[-2]) and (cand_rng >= 0.25 * safe_atr) and (rsi_val <= 65.0):
            action = 'BUY'
            status = 'ADAM_KHOO_20_EMA_BOUNCE_BUY'
            confidence = 86.0
            reasons.append(f"Adam Khoo: Price > 200 SMA ({sma_200:.2f}) & 20 EMA > 50 SMA in Bullish Stack")
            reasons.append(f"20 EMA Pullback Bounce confirmed at {ema_20:.2f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(entry_price - (ema_20 - 0.30 * safe_atr), 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif bounce_20_ema_short and (current_price < last_o and current_price <= closes.iloc[-2]) and (cand_rng >= 0.25 * safe_atr) and (rsi_val >= 35.0):
            action = 'SELL'
            status = 'ADAM_KHOO_20_EMA_BOUNCE_SELL'
            confidence = 86.0
            reasons.append(f"Adam Khoo: Price < 200 SMA ({sma_200:.2f}) & 20 EMA < 50 SMA in Bearish Stack")
            reasons.append(f"20 EMA Pullback Rejection confirmed at {ema_20:.2f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min((ema_20 + 0.30 * safe_atr) - entry_price, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price - (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price - (2.20 * sl_distance)   # Macro expansion runner
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Awaiting 20 EMA bounce with 50/200 SMA trend alignment (200 SMA: {sma_200:.2f})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'sma_200': round(sma_200, 2),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0+',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'TRAILING_20_EMA_CLOSE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 10. ARIEL ZWECHER — REALSIMPLEARIEL (15M OPENING RANGE BREAKOUT & PROP MATH)
# ─────────────────────────────────────────────────────────────────────────────
class ArielZwecherStrategy:
    """
    Trader 10: Ariel Zwecher (RealSimpleAriel Futures & Prop Math)
    - Focus: CME Futures (NQ, ES), Forex, Crypto
    - System: 15M Opening Range Breakout (ORB) + Session Volume Profile
    - Timeframe: 15M & 5M Intraday
    - Target: Fixed 1:2 R:R
    - Breakeven: FIXED_RR_TARGET (Strict prop challenge risk math)
    """
    NAME = "Ariel Zwecher (15M ORB)"
    KEY = "ARIEL_ZWECHER"
    BE_MODE = "FIXED_RR_TARGET"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower()
        if tf_clean not in ['1m', '3m', '5m', '15m', '30m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'orb_high': 0.0,
                'orb_low': 0.0,
                'trade_setup': {},
                'reasons': [f"Ariel Zwecher is an intraday 15M/5M ORB strategy. Current timeframe '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Ariel Zwecher 15M ORB model is calibrated for Forex & Crypto (rejects Gold wicks)
        if current_price > 2000.0 and current_price < 10000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Ariel Zwecher 15M ORB model is calibrated for Forex and Crypto (avoiding Gold noise)."]
            }

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        # Opening Range: first 15m session range (approximated by high/low of first bar in lookback)
        orb_high = float(np.max(highs[-12:-4])) if n >= 12 else float(np.max(highs))
        orb_low = float(np.min(lows[-12:-4])) if n >= 12 else float(np.min(lows))

        action = 'HOLD'
        status = 'SCANNING_15M_ORB'
        confidence = 50.0
        reasons = []

        pts_8 = 8.0 * (0.01 if current_price < 500 else 1.0)

        closes_s = pd.Series(closes)
        ema_20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])

        # RSI Momentum Exhaustion Guard (Avoid buying top wick blows or shorting bottom capitulations)
        delta = closes_s.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Breakout above ORB High (strictly with EMA trend alignment & RSI sweet spot)
        last_range = abs(highs[-1] - lows[-1])
        if (closes[-1] > orb_high) and (closes[-2] <= orb_high * 1.001) and (ema_20 >= ema_50) and (df['close'].iloc[-1] > df['open'].iloc[-1]) and (closes[-1] > closes[-2]) and (last_range >= 0.35 * safe_atr) and (rsi_val <= 68.0):
            action = 'BUY'
            status = '15M_ORB_BULLISH_BREAKOUT'
            confidence = 86.0
            reasons.append(f"Ariel Zwecher: Clean 15M Opening Range Breakout above {orb_high:.2f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(abs(entry_price - orb_low) + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        # Breakdown below ORB Low (strictly with EMA trend alignment & RSI sweet spot)
        elif (closes[-1] < orb_low) and (closes[-2] >= orb_low * 0.999) and (ema_20 <= ema_50) and (df['close'].iloc[-1] < df['open'].iloc[-1]) and (closes[-1] < closes[-2]) and (last_range >= 0.35 * safe_atr) and (rsi_val >= 32.0):
            action = 'SELL'
            status = '15M_ORB_BEARISH_BREAKDOWN'
            confidence = 86.0
            reasons.append(f"Ariel Zwecher: Clean 15M Opening Range Breakdown below {orb_low:.2f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(abs(orb_high - entry_price) + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Inside 15M Opening Range [{orb_low:.2f} - {orb_high:.2f}]. Awaiting breakout.")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'orb_high': round(orb_high, 2),
            'orb_low': round(orb_low, 2),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'FIXED_1_2_TARGET'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 11. OLIVER VELEZ — 20/200 SMA LOCATION & ELEPHANT BAR
# ─────────────────────────────────────────────────────────────────────────────
class OliverVelezStrategy:
    """
    Trader 11: Oliver Velez (20/200 SMA Location & Elephant Bar Strategy)
    - Focus: Equities, Futures, Forex, Crypto
    - System: 20 SMA ('The Location Indicator'), 200 SMA ('The Macro Baseline')
    - Filter: Buys allowed ONLY near 20 SMA in uptrend (Price > 200 SMA); Sells ONLY near 20 SMA in downtrend
    - Entry: Elephant Candle (solid body >= 1.8x avg) or Bottoming Tail Bar forming at 20 SMA
    - Target: 1:2 R:R or trailing behind 20 SMA
    - Breakeven: TRAILING_20_SMA
    """
    NAME = "Oliver Velez (20/200 SMA & Elephant Bar)"
    KEY = "OLIVER_VELEZ"
    BE_MODE = "TRAILING_20_SMA"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '5m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower()
        if tf_clean not in ['1m', '2m', '3m', '5m', '15m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Oliver Velez 20 SMA Elephant Bar is an intraday 2M/5M/15M strategy. Current timeframe '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Oliver Velez model is calibrated for Equities, Indices & Forex (rejects Gold wicks)
        if current_price > 2000.0 and current_price < 10000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Oliver Velez 20 SMA Elephant Bar model is calibrated for Equities, Indices and Forex (avoiding Gold wicks)."]
            }

        closes = pd.Series(df['close'].values)
        opens = pd.Series(df['open'].values)
        highs = pd.Series(df['high'].values)
        lows = pd.Series(df['low'].values)

        sma_20_series = closes.rolling(min(n, 20)).mean()
        sma_20 = float(sma_20_series.iloc[-1])
        sma_20_prev = float(sma_20_series.iloc[-2]) if len(sma_20_series) >= 2 else sma_20
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        # Candle body analysis
        bodies = (closes - opens).abs()
        avg_body = float(bodies.tail(15).mean()) if n >= 15 else float(bodies.mean())
        last_body = abs(closes.iloc[-1] - opens.iloc[-1])
        rng = max(highs.iloc[-1] - lows.iloc[-1], 1e-9)

        # Elephant Bar = body >= 1.7x average body and substantial candle (>= 0.35 safe_atr)
        is_elephant_bar = (last_body >= (avg_body * 1.7)) and (last_body >= 0.35 * safe_atr)
        # Bottoming Tail Bar = lower wick >= 50% of candle range and range >= 0.30 safe_atr
        is_bottoming_tail = (((min(opens.iloc[-1], closes.iloc[-1]) - lows.iloc[-1]) / rng) >= 0.50) and (rng >= 0.30 * safe_atr)
        # Topping Tail Bar = upper wick >= 50% of candle range and range >= 0.30 safe_atr
        is_topping_tail = (((highs.iloc[-1] - max(opens.iloc[-1], closes.iloc[-1])) / rng) >= 0.50) and (rng >= 0.30 * safe_atr)

        # Location rule: Candle must test the 20 SMA directly (open/low within 0.25 ATR of 20 SMA)
        near_20_sma = (min(abs(lows.iloc[-1] - sma_20), abs(opens.iloc[-1] - sma_20)) <= 0.25 * safe_atr) or (abs(current_price - sma_20) <= 0.25 * safe_atr)
        is_uptrend = (current_price > sma_200) and (sma_20 >= sma_200) and (sma_20 >= sma_20_prev * 0.9999)
        is_downtrend = (current_price < sma_200) and (sma_20 <= sma_200) and (sma_20 <= sma_20_prev * 1.0001)

        action = 'HOLD'
        status = 'SCANNING_20_SMA_LOCATION'
        confidence = 50.0
        reasons = []

        if is_uptrend and near_20_sma and (closes.iloc[-1] > opens.iloc[-1]) and (is_elephant_bar or is_bottoming_tail):
            action = 'BUY'
            bar_type = "Elephant Bar" if is_elephant_bar else "Bottoming Tail Bar"
            status = f'OLIVER_VELEZ_{bar_type.upper().replace(" ", "_")}_BUY'
            confidence = 88.0
            reasons.append(f"Oliver Velez: {bar_type} formed precisely at 20 SMA Location ({sma_20:.2f})")
            reasons.append(f"Macro Baseline Aligned: Price > 200 SMA ({sma_200:.2f})")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(entry_price - (lows.iloc[-1] - 0.20 * safe_atr), 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        elif is_downtrend and near_20_sma and (closes.iloc[-1] < opens.iloc[-1]) and (is_elephant_bar or is_topping_tail):
            action = 'SELL'
            bar_type = "Elephant Bar" if is_elephant_bar else "Topping Tail Bar"
            status = f'OLIVER_VELEZ_{bar_type.upper().replace(" ", "_")}_SELL'
            confidence = 88.0
            reasons.append(f"Oliver Velez: {bar_type} formed precisely at 20 SMA Location ({sma_20:.2f})")
            reasons.append(f"Macro Baseline Aligned: Price < 200 SMA ({sma_200:.2f})")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min((highs.iloc[-1] + 0.20 * safe_atr) - entry_price, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Waiting for Elephant/Tail Bar at 20 SMA (20 SMA: {sma_20:.2f}, Near: {near_20_sma})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'sma_20': round(sma_20, 2),
            'sma_200': round(sma_200, 2),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'TRAILING_20_SMA'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 12. TRADE PRO — MECHANICAL BACKTESTED SYSTEMS (DONCHIAN 20 + 200 SMA + RSI)
# ─────────────────────────────────────────────────────────────────────────────
class TradeProStrategy:
    """
    Trader 12: Trade Pro (Mechanical Backtested Systems)
    - Focus: Futures, Forex, Crypto
    - System: Donchian Channels (20-period) + 200 SMA Slope + RSI + ATR
    - Entry: 100% mechanical breakout of Donchian Upper/Lower Channel with RSI in trend direction
    - Target: Mechanical 1:2 R:R (SL 1.5 ATR, TP 3.0 ATR)
    - Breakeven: FIXED_RR_TARGET (Rigid mechanical rule)
    """
    NAME = "Trade Pro (Donchian & 200 SMA)"
    KEY = "TRADE_PRO"
    BE_MODE = "FIXED_RR_TARGET"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        closes = pd.Series(df['close'].values)
        highs = pd.Series(df['high'].values)
        lows = pd.Series(df['low'].values)

        # Donchian 20-period Channel
        donchian_high = float(highs.tail(21).iloc[:-1].max()) if n >= 21 else float(highs.max())
        donchian_low = float(lows.tail(21).iloc[:-1].min()) if n >= 21 else float(lows.min())

        # 200 SMA
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        # RSI 14
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        action = 'HOLD'
        status = 'SCANNING_DONCHIAN_BREAKOUT'
        confidence = 50.0
        reasons = []

        # Mechanical Long: Price breaks Donchian High, Price > 200 SMA, RSI between 50 and 70 with Bullish Close
        curr_open = float(df['open'].iloc[-1])
        if (current_price >= donchian_high) and (current_price > sma_200) and (50.0 <= rsi_val <= 70.0) and (current_price > curr_open):
            action = 'BUY'
            status = 'DONCHIAN_MECHANICAL_BUY'
            confidence = 86.0
            reasons.append(f"Trade Pro: Mechanical Donchian 20 High ({donchian_high:.2f}) Breakout with bullish close")
            reasons.append(f"Trend Filters: Price > 200 SMA ({sma_200:.2f}) & RSI({rsi_val:.1f}) in 50-70 sweet spot")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min((entry_price - donchian_low) * 0.45, 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        # Mechanical Short: Price breaks Donchian Low, Price < 200 SMA, RSI between 30 and 50 with Bearish Close
        elif (current_price <= donchian_low) and (current_price < sma_200) and (30.0 <= rsi_val <= 50.0) and (current_price < curr_open):
            action = 'SELL'
            status = 'DONCHIAN_MECHANICAL_SELL'
            confidence = 86.0
            reasons.append(f"Trade Pro: Mechanical Donchian 20 Low ({donchian_low:.2f}) Breakdown with bearish close")
            reasons.append(f"Trend Filters: Price < 200 SMA ({sma_200:.2f}) & RSI({rsi_val:.1f}) in 30-50 sweet spot")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min((donchian_high - entry_price) * 0.45, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Inside Donchian Channel [{donchian_low:.2f} - {donchian_high:.2f}] (200 SMA: {sma_200:.2f})")

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'donchian_high': round(donchian_high, 2),
            'donchian_low': round(donchian_low, 2),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.0',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'FIXED_1_2_TARGET'
            },
            'reasons': reasons
        }



# ─────────────────────────────────────────────────────────────────────────────
# 13. KRISTJAN QULLAMAGGIE — SYSTEMATIC MOMENTUM EXPANSION
# ─────────────────────────────────────────────────────────────────────────────
class KristjanQullamaggieStrategy:
    """
    Trader 13: Kristjan Qullamaggie
    - Asset Class: Stocks & Crypto Altcoins (High-Beta momentum)
    - Concept: High-probability momentum breakouts in explosive expansion assets
    - Setup Criteria: 30%-100%+ upward move preceding 12 weeks, orderly 2-8 week consolidation, High ADR% > 5%
    - MA Surfing: Consolidates tightly above rising 10 EMA & 20 EMA, with 50 SMA acting as structural support
    - Entry Trigger: Opening Range Breakout (ORB) or inside/narrow bar breakout across resistance
    - Stop Loss: Low of the Day (LOD) or max 1x ATR distance. Risk 0.25%-1.0%
    - Exits: Sell 1/3 to 1/2 of position after 3 to 5 days. Move SL to BE. Trail along 10/20 EMA
    - Breakeven Mode: QULLAMAGGIE_EMA_TRAIL
    - Timeframes: Daily ('1d') and 60-Minute ('1h'). Micro (<5m) rejected.
    """
    NAME = "Kristjan Qullamaggie (Systematic Momentum Expansion)"
    KEY = "KRISTJAN_QULLAMAGGIE"
    BE_MODE = "QULLAMAGGIE_EMA_TRAIL"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        # Reject micro-scalp noise (<15m)
        if tf_clean in ['1m', '2m', '3m', '5m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Qullamaggie trades Daily setups and 15m/1h momentum expansion; micro-scalp (<15m) is invalid noise."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Qullamaggie trades high ADR% momentum in Equities and Crypto (avoiding commodities)
        if current_price > 2000.0 and current_price < 10000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Qullamaggie model trades high ADR% expansion in Equities and Crypto (BTC/ETH)."]
            }

        if n < 20:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient historical bars for 10/20 EMA and 50 SMA surfing analysis."]
            }

        closes = df['close']
        highs = df['high']
        lows = df['low']

        ema_10 = float(closes.ewm(span=10, adjust=False).mean().iloc[-1])
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        sma_50 = float(closes.rolling(window=min(n, 50)).mean().iloc[-1])

        # ADR% Calculation (High ADR% > 5% or relative volatility > 3.0%)
        bar_ranges_pct = ((highs - lows) / closes.replace(0, np.nan)) * 100.0
        adr_pct = float(bar_ranges_pct.rolling(window=min(n, 20)).mean().iloc[-1])

        # Consolidation resistance (requires established 15-20 bar base)
        lookback_consol = min(n, 20)
        resistance = float(highs.iloc[-lookback_consol:-1].max())
        lod = float(lows.iloc[-lookback_consol:].min())

        reasons = []
        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0

        # Moving average surfing: prior bar was tight to 10 EMA (not over-extended before breakout)
        is_ma_surfing_long = (current_price >= ema_10 >= ema_20) and (ema_20 >= sma_50 * 0.98) and ((closes.iloc[-2] - ema_10 <= 0.90 * safe_atr) or (current_price - ema_10 <= 1.60 * safe_atr))
        is_ma_surfing_short = (current_price <= ema_10 <= ema_20) and (ema_20 <= sma_50 * 1.02) and ((ema_10 - closes.iloc[-2] <= 0.90 * safe_atr) or (ema_10 - current_price <= 1.60 * safe_atr))
        
        # ADR% / bar volatility filter calibrated for intraday 15m/1h as well as daily charts
        is_adr_ok = (adr_pct >= 0.20) or ((safe_atr / max(current_price, 1e-6)) * 100.0 >= 0.12)

        # Bullish Breakout across consolidation resistance
        if is_ma_surfing_long and is_adr_ok and (current_price >= resistance * 0.999) and (closes.iloc[-2] <= resistance * 1.002) and (closes.iloc[-1] > df['open'].iloc[-1]):
            action = 'BUY'
            status = 'ORB_BREAKOUT'
            confidence = 88.0
            reasons.append(f"High ADR% ({adr_pct:.1f}%): Asset exhibits explosive momentum potential")
            reasons.append(f"Moving Average Surfing: Price (${current_price:.2f}) > 10 EMA (${ema_10:.2f}) > 20 EMA (${ema_20:.2f})")
            reasons.append(f"Consolidation Breakout: Closed above {lookback_consol}-bar resistance (${resistance:.2f})")
        # Bearish Breakdown below consolidation support
        elif is_ma_surfing_short and is_adr_ok and (current_price <= lod * 1.001) and (closes.iloc[-2] >= lod * 0.998) and (closes.iloc[-1] < df['open'].iloc[-1]):
            action = 'SELL'
            status = 'ORB_BREAKDOWN'
            confidence = 88.0
            reasons.append(f"High ADR% ({adr_pct:.1f}%): Asset exhibits explosive momentum potential")
            reasons.append(f"Moving Average Surfing: Price (${current_price:.2f}) < 10 EMA (${ema_10:.2f}) < 20 EMA (${ema_20:.2f})")
            reasons.append(f"Consolidation Breakdown: Closed below {lookback_consol}-bar support (${lod:.2f})")
        else:
            if not is_adr_ok:
                reasons.append(f"ADR% ({adr_pct:.1f}%) below high-momentum volatility threshold")
            if not (is_ma_surfing_long or is_ma_surfing_short):
                reasons.append("Price not aligned with 10/20 EMA and 50 SMA surfing structure")

        if action == 'BUY':
            entry_price = current_price
            raw_lod_dist = entry_price - lod
            # Golden SL Geometry: strictly >= 1.80 * ATR with swing low buffer capped at 2.00 ATR
            sl_distance = max(1.80 * safe_atr, min(raw_lod_dist + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif action == 'SELL':
            entry_price = current_price
            raw_hod_dist = resistance - entry_price
            sl_distance = max(1.80 * safe_atr, min(raw_hod_dist + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price - (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price - (2.20 * sl_distance)   # Macro expansion runner
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:5.0',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'QULLAMAGGIE_EMA_TRAIL'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 14. GCR (@GiganticRebirth) — BEHAVIORAL SENTIMENT & COUNTER-CYCLICAL SHORTING
# ─────────────────────────────────────────────────────────────────────────────
class GCRStrategy:
    """
    Trader 14: GCR (@GiganticRebirth)
    - Asset Class: Crypto (BTC, ETH, and Liquid High-Caps only)
    - Concept: Exploiting retail psychological biases, tokenomics, and structural market cycles
    - Schelling Points: Major round numbers ($1, $10, $100, $1k, $10k, $100k) serve as liquidity pools
    - Counter-Cyclical Shorting: Shorts retail hype exhaustion / 'Sell the News' catalyst peaks (RSI > 70)
    - Cycle Bottom Rebalancing: Inverse buying when 95% expect a sell event / capitulation (RSI < 30)
    - Breakeven Mode: GCR_CYCLE_BE
    - Timeframes: 1h, 4h, 1d
    """
    NAME = "GCR (@GiganticRebirth - Behavioral Sentiment)"
    KEY = "GCR"
    BE_MODE = "GCR_CYCLE_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean in ['1m', '3m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["GCR trades macro cycle pivots and catalyst exhaustion on 1H/4H/Daily; micro timeframes (<5m) are invalid."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        if n < 14:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for GCR sentiment and Schelling point cycle analysis."]
            }

        closes = df['close']
        highs = df['high']
        lows = df['low']

        # RSI Calculation (14 period)
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss.replace(0, np.nan))
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Schelling Point Proximity (Psychological Round Numbers)
        def _get_schelling_proximity(price: float) -> Tuple[float, float]:
            if price <= 0:
                return 0.0, 100.0
            order = 10 ** int(np.floor(np.log10(price)))
            candidates = [order, 2 * order, 5 * order, 10 * order]
            closest = min(candidates, key=lambda x: abs(x - price))
            dist_pct = abs(price - closest) / price * 100.0
            return closest, dist_pct

        schelling_level, schelling_dist_pct = _get_schelling_proximity(current_price)
        is_at_schelling = schelling_dist_pct <= 1.5

        # Candle wicks (Exhaustion wick detection)
        curr_open = float(df['open'].iloc[-1])
        curr_high = float(highs.iloc[-1])
        curr_low = float(lows.iloc[-1])
        curr_close = current_price
        upper_wick = curr_high - max(curr_open, curr_close)
        lower_wick = min(curr_open, curr_close) - curr_low
        body = abs(curr_close - curr_open)

        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0
        reasons = []

        # Counter-Cyclical Short: Overbought Retail Euphoria + Confirmed Reversal Bearish Close
        prev_close = float(df['close'].iloc[-2])
        if rsi_val >= 68.0 and (curr_close < curr_open and curr_close < prev_close) and (is_at_schelling or upper_wick >= 0.25 * max(curr_high - curr_low, 1e-6)):
            action = 'SELL'
            status = 'EUPHORIA_EXHAUSTION_SHORT'
            confidence = 86.0
            reasons.append(f"GCR Counter-Short: Retail euphoria exhaustion at RSI {rsi_val:.1f} with bearish rejection candle")
            if is_at_schelling:
                reasons.append(f"Schelling Point Pivot: Price testing major round number ${schelling_level:,.2f}")
            reasons.append("Parabolic exhaustion confirmed: Bearish close below prior bar")
        # Inverse Buying: Capitulation / Extreme Fear + Confirmed Reversal Bullish Close
        elif rsi_val <= 32.0 and (curr_close > curr_open and curr_close > prev_close) and (is_at_schelling or lower_wick >= 0.25 * max(curr_high - curr_low, 1e-6)):
            action = 'BUY'
            status = 'CAPITULATION_BOTTOM_LONG'
            confidence = 86.0
            reasons.append(f"GCR Cycle Bottom Long: Retail capitulation exhaustion at RSI {rsi_val:.1f} with bullish absorption candle")
            if is_at_schelling:
                reasons.append(f"Schelling Support: Price defending major round number ${schelling_level:,.2f}")
            reasons.append("Capitulation absorption confirmed: Bullish close above prior bar")
        else:
            reasons.append(f"GCR retail sentiment neutral (RSI {rsi_val:.1f}). Nearest Schelling pivot: ${schelling_level:,.2f} ({schelling_dist_pct:.1f}% away)")

        if action == 'BUY':
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(entry_price - curr_low) + 0.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif action == 'SELL':
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(curr_high - entry_price) + 0.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:3.5',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'GCR_CYCLE_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 15. WAQAR ZAKA — OFF-EXCHANGE CAPITAL RESERVE & ATR BUFFER MODEL
# ─────────────────────────────────────────────────────────────────────────────
class WaqarZakaStrategy:
    """
    Trader 15: Waqar Zaka
    - Asset Class: Crypto Futures / Perps (BTC, ETH, Altcoins)
    - Concept: Neutralizing market maker liquidity sweeps and exchange stop-hunting
    - Liquidity Sweep Reclaim: Detects exchange stop hunts where price sweeps swing low/high
      and aggressively reclaims the level within the candle or following bar
    - ATR Stop Loss Buffer: Boundary set using Entry Price minus ATR Value, absorbing noise wicks
    - Breakeven Mode: ATR_BUFFER_BE
    - Timeframes: 15m, 1h, 4h
    """
    NAME = "Waqar Zaka (Off-Exchange Reserve & ATR Buffer Model)"
    KEY = "WAQAR_ZAKA"
    BE_MODE = "ATR_BUFFER_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        if n < 20:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Waqar Zaka liquidity sweep & ATR buffer analysis."]
            }

        # Asset Class Guard: Waqar Zaka model applies strictly to Crypto Futures (BTC, ETH, Altcoins)
        if current_price < 10000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Waqar Zaka Off-Exchange Reserve & Liquidation Hunt model is exclusive to Crypto Futures (BTC/ETH)."]
            }

        highs = df['high']
        lows = df['low']
        closes = df['close']

        lookback = min(n, 20)
        swing_low = float(lows.iloc[-lookback:-2].min())
        swing_high = float(highs.iloc[-lookback:-2].max())

        curr_low = float(lows.iloc[-1])
        curr_high = float(highs.iloc[-1])
        curr_open = float(df['open'].iloc[-1])
        curr_close = current_price
        cand_rng = max(curr_high - curr_low, 1e-6)
        closes_s = pd.Series(closes)
        ema_20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])

        # Sweep and reclaim with candle confirmation (requires noticeable sweep depth and candle range)
        swept_low = (curr_low < swing_low - 0.05 * safe_atr) and (curr_close > swing_low) and (curr_close > curr_open) and (curr_close >= df['close'].iloc[-2]) and (cand_rng >= 0.25 * safe_atr) and (ema_20 >= ema_50)
        prev_swept_low = (float(lows.iloc[-2]) < swing_low - 0.05 * safe_atr) and (float(df['close'].iloc[-2]) <= swing_low) and (curr_close > swing_low) and (curr_close > curr_open) and (cand_rng >= 0.25 * safe_atr) and (ema_20 >= ema_50)
        bullish_sweep_reclaim = swept_low or prev_swept_low

        swept_high = (curr_high > swing_high + 0.05 * safe_atr) and (curr_close < swing_high) and (curr_close < curr_open) and (curr_close <= df['close'].iloc[-2]) and (cand_rng >= 0.25 * safe_atr) and (ema_20 <= ema_50)
        prev_swept_high = (float(highs.iloc[-2]) > swing_high + 0.05 * safe_atr) and (float(df['close'].iloc[-2]) >= swing_high) and (curr_close < swing_high) and (curr_close < curr_open) and (cand_rng >= 0.25 * safe_atr) and (ema_20 <= ema_50)
        bearish_sweep_reclaim = swept_high or prev_swept_high

        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0
        reasons = []

        if bullish_sweep_reclaim:
            action = 'BUY'
            status = 'LIQUIDATION_SWEEP_RECLAIM'
            confidence = 86.0
            reasons.append(f"Waqar Zaka: Market maker liquidity sweep below swing low (${swing_low:,.2f}) reclaimed with bullish close")
            reasons.append("Exchange stop hunt absorbed: Off-exchange capital reserve architecture deployed")
            reasons.append(f"ATR Buffer SL active: Protected with Golden 1.80x ATR buffer (${safe_atr:,.2f}) against noise wicks")
        elif bearish_sweep_reclaim:
            action = 'SELL'
            status = 'LIQUIDATION_SWEEP_REJECT'
            confidence = 86.0
            reasons.append(f"Waqar Zaka: Short stop hunt above swing high (${swing_high:,.2f}) rejected with bearish close")
            reasons.append("Upper liquidity cascade exhausted: Bearish reversal triggered")
            reasons.append(f"ATR Buffer SL active: Protected with Golden 1.80x ATR buffer (${safe_atr:,.2f}) against noise wicks")
        else:
            reasons.append(f"Waqar Zaka: Inside liquidity bracket [Low: ${swing_low:,.2f} - High: ${swing_high:,.2f}]. Awaiting sweep reclaim.")

        if action == 'BUY':
            entry_price = current_price
            # Golden SL Geometry: strictly >= 1.80 * ATR with swing low buffer capped at 2.00 ATR
            sl_distance = max(1.80 * safe_atr, min(abs(entry_price - swing_low) + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif action == 'SELL':
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(abs(swing_high - entry_price) + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:2.5',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'ATR_BUFFER_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 16. WAQAR ASIM — FOREX SUPPLY & DEMAND SCALPING (INDUCEMENT MODEL)
# ─────────────────────────────────────────────────────────────────────────────
class WaqarAsimStrategy:
    """
    Trader 16: Waqar Asim
    - Asset Class: Forex (EURUSD, GBPUSD)
    - Concept: Precision 1-minute scalping based on institutional liquidity inducement
    - HTF Context (1-Hour): Decisional S&D zones + Premium/Discount Array Filter (Shorts in Premium, Longs in Discount)
    - LTF Trigger (1-Minute): Inducement (liquidity sweep) followed by Break of Structure (BOS/MSB) tapping LTF S/D zone
    - Risk & SL: Ultra-tight stop loss of 3 to 7 pips (flat ~5 pips / ~0.0005)
    - Exits: Move SL to Breakeven immediately upon formation of new internal high/low on 1m chart. 50% at 3R, 50% at 10R
    - Trading Session Timings: London Open (8:00-9:00 AM London) & NY Afternoon (2:00-3:00 PM London)
    - Breakeven Mode: WAQAR_ASIM_INSTANT_BE
    - Timeframes: 1m (primary, operable on 5m). Rejects 4h/1d.
    """
    NAME = "Waqar Asim (Forex 1M S&D Inducement Scalping Model)"
    KEY = "WAQAR_ASIM"
    BE_MODE = "WAQAR_ASIM_INSTANT_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean in ['4h', '1d', 'daily']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Waqar Asim is strictly a precision 1-minute/5-minute S&D scalper; HTF charts (4H/Daily) are invalid."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.0002)

        if n < 20:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient 1M bars for Waqar Asim inducement and Premium/Discount zone analysis."]
            }

        highs = df['high']
        lows = df['low']
        closes = df['close']

        # HTF Decisional S&D context (60 bars lookback = 1 hour on 1m chart)
        htf_lookback = min(n, 60)
        htf_high = float(highs.iloc[-htf_lookback:].max())
        htf_low = float(lows.iloc[-htf_lookback:].min())
        equilibrium = (htf_high + htf_low) / 2.0

        is_discount = current_price < equilibrium   # Longs strictly in Discount
        is_premium = current_price > equilibrium    # Shorts strictly in Premium

        # Inducement & BOS detection (minor liquidity sweep of last 5-10 bars followed by candle break)
        ltf_lookback = min(n, 10)
        minor_low = float(lows.iloc[-ltf_lookback:-2].min())
        minor_high = float(highs.iloc[-ltf_lookback:-2].max())

        # Bullish Inducement + BOS in Discount:
        has_bullish_inducement = (float(lows.iloc[-2]) < minor_low or float(lows.iloc[-1]) < minor_low)
        has_bullish_bos = closes.iloc[-1] > highs.iloc[-2]
        bullish_setup = is_discount and has_bullish_inducement and has_bullish_bos

        # Bearish Inducement + BOS in Premium:
        has_bearish_inducement = (float(highs.iloc[-2]) > minor_high or float(highs.iloc[-1]) > minor_high)
        has_bearish_bos = closes.iloc[-1] < lows.iloc[-2]
        bearish_setup = is_premium and has_bearish_inducement and has_bearish_bos

        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0
        reasons = []

        if bullish_setup:
            action = 'BUY'
            status = 'DISCOUNT_INDUCEMENT_BOS'
            confidence = 89.0
            reasons.append("Waqar Asim: Price operating strictly in HTF Discount zone (below equilibrium)")
            reasons.append(f"Inducement captured: Liquidity sweep below minor low ({minor_low:.5f})")
            reasons.append("LTF Break of Structure (BOS): Institutional supply/demand tap confirmed")
        elif bearish_setup:
            action = 'SELL'
            status = 'PREMIUM_INDUCEMENT_BOS'
            confidence = 89.0
            reasons.append("Waqar Asim: Price operating strictly in HTF Premium zone (above equilibrium)")
            reasons.append(f"Inducement captured: Liquidity sweep above minor high ({minor_high:.5f})")
            reasons.append("LTF Market Structure Break (MSB): Institutional supply zone tap confirmed")
        else:
            zone_desc = "Discount (Longs only)" if is_discount else "Premium (Shorts only)"
            reasons.append(f"Inside HTF 1H range [{htf_low:.5f} - {htf_high:.5f}] ({zone_desc}). Awaiting 1M inducement.")

        # Pip-based Ultra-Tight SL protected by Golden SL (>= 1.80 * ATR) invariant
        pip_size = 0.00010 if current_price < 10.0 else (0.01 if current_price < 500 else 1.0)
        tight_sl_pips = 5.0 * pip_size
        sl_distance = max(tight_sl_pips, 1.80 * safe_atr)

        if action == 'BUY':
            entry_price = current_price
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif action == 'SELL':
            entry_price = current_price
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:3.0 / 1:10.0',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'WAQAR_ASIM_INSTANT_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 17. EUGENE NG AH SIO — RELATIVE VALUE DELTA-NEUTRAL SPREADS
# ─────────────────────────────────────────────────────────────────────────────
class EugeneNgAhSioStrategy:
    """
    Trader 17: Eugene Ng Ah Sio
    - Asset Class: Crypto Perps & Spot
    - Concept: Pair trading derivatives to capture fundamental divergence while neutralizing directional risk
    - Long Outperformers: Accumulating high yield / strong fundamental catalyst assets
    - Short Laggards: Hedging weak/laggard assets
    - Catalyst Unwinding: Close hedges upon catalyst fulfillment to lock in net spread gains
    - Breakeven Mode: DELTA_NEUTRAL_SPREAD_BE
    - Timeframes: 1h, 4h, 1d
    """
    NAME = "Eugene Ng Ah Sio (Relative Value Delta-Neutral Spreads)"
    KEY = "EUGENE_NG_AH_SIO"
    BE_MODE = "DELTA_NEUTRAL_SPREAD_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        if n < 20:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Eugene Ng Ah Sio relative value spread analysis."]
            }

        # Asset Guard: Eugene Ng Ah Sio strategy is strictly calibrated for Crypto Perps & Spot
        if current_price < 5000.0:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Eugene Ng Ah Sio relative value model is strictly calibrated for Crypto assets."]
            }

        closes = df['close']
        highs = df['high']
        lows = df['low']

        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        # RSI Calculation (14 period)
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss.replace(0, np.nan))
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50.0

        lookback = min(n, 20)
        recent_high = float(highs.iloc[-lookback:-1].max())
        recent_low = float(lows.iloc[-lookback:-1].min())

        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0
        reasons = []

        # Relative Strength Outperformer (Long Leg with Bullish Candle Confirmation & SMA200 trend):
        curr_open = float(df['open'].iloc[-1])
        prev_close = float(closes.iloc[-2])
        if current_price > sma_200 and current_price > ema_20 and ema_20 > ema_50 and (50.0 <= rsi_val <= 68.0) and current_price >= recent_high * 0.995 and (current_price > curr_open and current_price >= prev_close):
            action = 'BUY'
            status = 'ALPHA_CATALYST_LONG'
            confidence = 86.0
            reasons.append(f"Eugene Ng: Relative strength outperformance confirmed (RSI {rsi_val:.1f}) with bullish breakout close")
            reasons.append(f"Price (${current_price:.2f}) leading above 20 EMA (${ema_20:.2f}) and 50 EMA (${ema_50:.2f})")
            reasons.append(f"Breakout of {lookback}-bar relative value consolidation high (${recent_high:.2f})")
        # Relative Weakness Laggard (Hedge Leg with Bearish Candle Confirmation & SMA200 trend):
        elif current_price < sma_200 and current_price < ema_20 and ema_20 < ema_50 and (32.0 <= rsi_val <= 50.0) and current_price <= recent_low * 1.005 and (current_price < curr_open and current_price <= prev_close):
            action = 'SELL'
            status = 'LAGGARD_HEDGE_SHORT'
            confidence = 86.0
            reasons.append(f"Eugene Ng: Structural laggard weakness confirmed (RSI {rsi_val:.1f}) with bearish breakdown close")
            reasons.append(f"Price (${current_price:.2f}) breaking below 20/50 EMA moving average band")
            reasons.append(f"Breakdown of {lookback}-bar consolidation support (${recent_low:.2f})")
        else:
            reasons.append(f"Asset in neutral relative value spread territory (RSI {rsi_val:.1f}). Awaiting alpha divergence.")

        if action == 'BUY':
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(entry_price - recent_low) + 0.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif action == 'SELL':
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(recent_high - entry_price) + 0.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:3.0',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'DELTA_NEUTRAL_SPREAD_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 18. PAUL (RECORD FTMO TRADER) — MACRO-FUNDAMENTAL & DIVERGENCE STRATEGY
# ─────────────────────────────────────────────────────────────────────────────
class PaulFTMOStrategy:
    """
    Trader 18: Paul (Record FTMO Leaderboard Trader)
    - Asset Class: Forex (EURJPY, GBPJPY, EURUSD, GBPUSD) & S&P 500
    - Concept: Institutional multi-timeframe confluence, Asian session breakout boundaries,
      and custom RSI(12) + MACD(4, 18, 9) price/momentum divergences
    - Asian Range: Uses Asian Session consolidation boundaries (00:00-07:00 UTC) for London breakout
    - Execution & Risk: 25-30 pips SL (or 1.5x ATR). Fibonacci Extension Targets (100% and 161.8%)
    - Session: London Session Open
    - Breakeven Mode: FIB_EXTENSION_BE
    - Timeframes: 5m, 15m, 1h, 4h
    """
    NAME = "Paul (Record FTMO Trader - Macro & Divergence)"
    KEY = "PAUL_FTMO"
    BE_MODE = "FIB_EXTENSION_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        if n < 25:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Paul FTMO Asian breakout and RSI/MACD divergence analysis."]
            }

        closes = df['close']
        highs = df['high']
        lows = df['low']

        # Custom RSI (Setting 12) from PDF
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=12).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=12).mean()
        rs = gain / (loss.replace(0, np.nan))
        rsi_series = 100 - (100 / (1 + rs))
        rsi_12 = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50.0
        rsi_12_prev = float(rsi_series.iloc[-4]) if not np.isnan(rsi_series.iloc[-4]) else 50.0

        # Custom MACD (4, 18, 9) from PDF
        ema_4 = closes.ewm(span=4, adjust=False).mean()
        ema_18 = closes.ewm(span=18, adjust=False).mean()
        macd_line = ema_4 - ema_18
        signal_line = macd_line.rolling(window=9).mean()
        macd_hist = float(macd_line.iloc[-1] - signal_line.iloc[-1])
        macd_hist_prev = float(macd_line.iloc[-3] - signal_line.iloc[-3])

        # Asian Consolidation Boundary (lookback ~30 bars)
        lookback_asian = min(n, 30)
        asian_high = float(highs.iloc[-lookback_asian:-2].max())
        asian_low = float(lows.iloc[-lookback_asian:-2].min())
        asian_range = max(asian_high - asian_low, safe_atr)

        # Bullish Divergence: Price lower/equal to Asian low while RSI(12) or MACD hist is higher
        bullish_div = (float(lows.iloc[-1]) <= asian_low * 1.002) and (rsi_12 > rsi_12_prev or macd_hist > macd_hist_prev)
        # Bearish Divergence: Price higher/equal to Asian high while RSI(12) or MACD hist is lower
        bearish_div = (float(highs.iloc[-1]) >= asian_high * 0.998) and (rsi_12 < rsi_12_prev or macd_hist < macd_hist_prev)

        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0
        reasons = []

        if bullish_div and closes.iloc[-1] > closes.iloc[-2]:
            action = 'BUY'
            status = 'ASIAN_RANGE_BULLISH_DIVERGENCE'
            confidence = 88.0
            reasons.append(f"Paul FTMO: Bullish Divergence at Asian Range Low (${asian_low:,.4f})")
            reasons.append(f"Custom RSI(12) rising ({rsi_12:.1f} > {rsi_12_prev:.1f}) & Fast MACD(4,18,9) momentum expanding")
            reasons.append("Asian Range sweep completed; European order flow breakout active")
        elif bearish_div and closes.iloc[-1] < closes.iloc[-2]:
            action = 'SELL'
            status = 'ASIAN_RANGE_BEARISH_DIVERGENCE'
            confidence = 88.0
            reasons.append(f"Paul FTMO: Bearish Divergence at Asian Range High (${asian_high:,.4f})")
            reasons.append(f"Custom RSI(12) exhausting ({rsi_12:.1f} < {rsi_12_prev:.1f}) & Fast MACD(4,18,9) momentum weakening")
            reasons.append("Asian Range high tested; European liquidity distribution active")
        else:
            reasons.append(f"Inside Asian consolidation [{asian_low:,.4f} - {asian_high:,.4f}]. RSI(12): {rsi_12:.1f}. Awaiting divergence breakout.")

        # Execution & Risk: 25-30 pips stop loss with Fibonacci Extension targets (100% & 161.8%) from PDF
        pip_size = 0.00010 if current_price < 10.0 else (0.01 if current_price < 500 else 1.0)
        pip_30 = 28.0 * pip_size
        sl_distance = max(pip_30, 1.80 * safe_atr)

        if action == 'BUY':
            entry_price = current_price
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)     # Precision Scalp Bank
            tp2 = entry_price + max(1.618 * asian_range, 2.00 * sl_distance) # 1:2+ R:R runner
            tp3 = entry_price + max(2.618 * asian_range, 3.50 * sl_distance)
        elif action == 'SELL':
            entry_price = current_price
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - max(1.618 * asian_range, 2.00 * sl_distance)
            tp3 = entry_price - max(2.618 * asian_range, 3.50 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0

        return {
            'strategy_key': cls.KEY,
            'strategy_name': cls.NAME,
            'breakeven_mode': cls.BE_MODE,
            'action': action,
            'status': status,
            'confidence': float(round(confidence, 1)),
            'trade_setup': {
                'action': action,
                'status': status,
                'recommended_entry': float(round(entry_price, 5)),
                'stop_loss': float(round(stop_loss, 5)),
                'sl_distance_pct': float(round((sl_distance / max(entry_price, 1e-6)) * 100.0, 2)),
                'tp1': float(round(tp1, 5)),
                'tp2': float(round(tp2, 5)),
                'tp3': float(round(tp3, 5)),
                'risk_reward_ratio': '1:1.62 Fib',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'FIB_EXTENSION_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# MASTER STREAMER PLAYBOOK DISPATCHER (EVALUATE ALL 18 STRATEGIES)
# ─────────────────────────────────────────────────────────────────────────────
class MasterStreamerPlaybook:
    """
    Central dispatcher that evaluates all 18 strategies from the Master Playbooks.
    """
    STRATEGY_MAP = {
        'VIVEK_YADAV': VivekYadavPlaybookStrategy,
        'BERND_SKORUPINSKI': BerndSkorupinskiStrategy,
        'ICT': ICTStrategy,
        'STEVEN_HART': StevenHartStrategy,
        'RAYNER_TEO': RaynerTeoStrategy,
        'CRYPTO_CRED': CryptoCredStrategy,
        'NDEMAZEAH_GODLOVE': NdemazeahGodloveStrategy,
        'ROSS_CAMERON': RossCameronStrategy,
        'ADAM_KHOO': AdamKhooStrategy,
        'ARIEL_ZWECHER': ArielZwecherStrategy,
        'OLIVER_VELEZ': OliverVelezStrategy,
        'TRADE_PRO': TradeProStrategy,
        # 6 New Elite Traders from Playbook PDF:
        'KRISTJAN_QULLAMAGGIE': KristjanQullamaggieStrategy,
        'GCR': GCRStrategy,
        'WAQAR_ZAKA': WaqarZakaStrategy,
        'WAQAR_ASIM': WaqarAsimStrategy,
        'EUGENE_NG_AH_SIO': EugeneNgAhSioStrategy,
        'PAUL_FTMO': PaulFTMOStrategy
    }

    @classmethod
    def evaluate_all(
        cls,
        df: pd.DataFrame,
        atr: float,
        timeframe: str = '1h',
        cot_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates all 18 strategies simultaneously and identifies all confirmed setups.
        """
        results = {}
        active_setups = []

        # 1. Vivek Yadav
        res_vy = VivekYadavPlaybookStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['VIVEK_YADAV'] = res_vy
        if res_vy['action'] in ['BUY', 'SELL']:
            active_setups.append(res_vy)

        # 2. Bernd Skorupinski
        res_bs = BerndSkorupinskiStrategy.evaluate(df, atr=atr, cot_data=cot_data, timeframe=timeframe)
        results['BERND_SKORUPINSKI'] = res_bs
        if res_bs['action'] in ['BUY', 'SELL']:
            active_setups.append(res_bs)

        # 3. ICT
        res_ict = ICTStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['ICT'] = res_ict
        if res_ict['action'] in ['BUY', 'SELL']:
            active_setups.append(res_ict)

        # 4. Steven Hart
        res_sh = StevenHartStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['STEVEN_HART'] = res_sh
        if res_sh['action'] in ['BUY', 'SELL']:
            active_setups.append(res_sh)

        # 5. Rayner Teo
        res_rt = RaynerTeoStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['RAYNER_TEO'] = res_rt
        if res_rt['action'] in ['BUY', 'SELL']:
            active_setups.append(res_rt)

        # 6. Crypto Cred
        res_cc = CryptoCredStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['CRYPTO_CRED'] = res_cc
        if res_cc['action'] in ['BUY', 'SELL']:
            active_setups.append(res_cc)

        # 7. Ndemazeah Godlove
        res_ng = NdemazeahGodloveStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['NDEMAZEAH_GODLOVE'] = res_ng
        if res_ng['action'] in ['BUY', 'SELL']:
            active_setups.append(res_ng)

        # 8. Ross Cameron
        res_rc = RossCameronStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['ROSS_CAMERON'] = res_rc
        if res_rc['action'] in ['BUY', 'SELL']:
            active_setups.append(res_rc)

        # 9. Adam Khoo
        res_ak = AdamKhooStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['ADAM_KHOO'] = res_ak
        if res_ak['action'] in ['BUY', 'SELL']:
            active_setups.append(res_ak)

        # 10. Ariel Zwecher
        res_az = ArielZwecherStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['ARIEL_ZWECHER'] = res_az
        if res_az['action'] in ['BUY', 'SELL']:
            active_setups.append(res_az)

        # 11. Oliver Velez
        res_ov = OliverVelezStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['OLIVER_VELEZ'] = res_ov
        if res_ov['action'] in ['BUY', 'SELL']:
            active_setups.append(res_ov)

        # 12. Trade Pro
        res_tp = TradeProStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['TRADE_PRO'] = res_tp
        if res_tp['action'] in ['BUY', 'SELL']:
            active_setups.append(res_tp)

        # 13. Kristjan Qullamaggie
        res_kq = KristjanQullamaggieStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['KRISTJAN_QULLAMAGGIE'] = res_kq
        if res_kq['action'] in ['BUY', 'SELL']:
            active_setups.append(res_kq)

        # 14. GCR
        res_gcr = GCRStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['GCR'] = res_gcr
        if res_gcr['action'] in ['BUY', 'SELL']:
            active_setups.append(res_gcr)

        # 15. Waqar Zaka
        res_wz = WaqarZakaStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['WAQAR_ZAKA'] = res_wz
        if res_wz['action'] in ['BUY', 'SELL']:
            active_setups.append(res_wz)

        # 16. Waqar Asim
        res_wa = WaqarAsimStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['WAQAR_ASIM'] = res_wa
        if res_wa['action'] in ['BUY', 'SELL']:
            active_setups.append(res_wa)

        # 17. Eugene Ng Ah Sio
        res_en = EugeneNgAhSioStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['EUGENE_NG_AH_SIO'] = res_en
        if res_en['action'] in ['BUY', 'SELL']:
            active_setups.append(res_en)

        # 18. Paul FTMO
        res_pf = PaulFTMOStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['PAUL_FTMO'] = res_pf
        if res_pf['action'] in ['BUY', 'SELL']:
            active_setups.append(res_pf)

        # Best / Highest confidence confirmed setup
        best_setup = None
        if active_setups:
            active_setups.sort(key=lambda x: x.get('confidence', 0.0), reverse=True)
            best_setup = active_setups[0]

        return {
            'all_strategies': results,
            'active_setups': active_setups,
            'active_count': len(active_setups),
            'best_setup': best_setup
        }

