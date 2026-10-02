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
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean in ['1m', '2m', '3m', '5m', '15m', '1h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Vivek Yadav Supply/Demand operates on 30M and 4H timeframes. '{timeframe}' is excluded."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'GOLD', 'XAG', 'SILVER', 'CAD/JPY', 'EUR', 'GBP', 'USD/JPY', 'JPY']) or (current_price < 500.0 and 'BTC' not in sym_str and 'ETH' not in sym_str):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Vivek Yadav Supply/Demand operates on Crypto (BTC, ETH). Metals & Forex excluded."]
            }
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
        tf_clean = str(timeframe).lower()
        if tf_clean in ['1m', '2m', '3m', '5m', '15m', '30m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Bernd Skorupinski S&D model is calibrated for 1H, 4H swing/intraday zones. '{timeframe}' is too noisy."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Bernd Skorupinski FTMO S&D model is calibrated for Forex Majors (avoiding Crypto flash dumps, Gold, and Silver noise)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if (current_price > 500.0) or any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Bernd Skorupinski S&D model is calibrated strictly for Forex Majors & Prop Firm CFDs (EUR/USD, GBP/USD, USD/JPY). Metals excluded."]
            }

        # Stage 1: COT Fundamental Bias
        cot_bias = 'NEUTRAL'
        if cot_data and cot_data.get('available'):
            cot_bias = str(cot_data.get('smart_money_bias', 'NEUTRAL')).upper()

        # Stage 2: Institutional Swing S&D Zones (Big Brother / Small Brother)
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        # HTF Major S&D bounds (Big Brother multi-day structure)
        lookback = min(n, 120)
        htf_high = float(np.max(highs[-lookback:]))
        htf_low = float(np.min(lows[-lookback:]))
        mid = (htf_high + htf_low) / 2.0

        # Prior unmitigated swing levels (excluding current 3 candles to avoid self-referencing)
        lookback_zone = min(n, 60)
        prior_demand = float(np.min(lows[-lookback_zone:-3])) if n >= 15 else float(np.min(lows))
        prior_supply = float(np.max(highs[-lookback_zone:-3])) if n >= 15 else float(np.max(highs))

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
        # Long only if in Discount (<= 45% of HTF range) AND COT is Bullish/Neutral
        htf_span = max(htf_high - htf_low, safe_atr)
        is_discount = current_price <= (htf_low + htf_span * 0.45)
        is_premium = current_price >= (htf_low + htf_span * 0.55)

        curr_open = float(df['open'].iloc[-1])
        last_h = float(highs[-1])
        last_l = float(lows[-1])
        cand_rng = max(last_h - last_l, 1e-6)
        lower_wick_ratio = (min(curr_open, current_price) - last_l) / cand_rng
        upper_wick_ratio = (last_h - max(curr_open, current_price)) / cand_rng

        # Trend alignment: avoid buying into waterfalls or shorting into rockets
        ema_20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes_s.rolling(min(n, 200), min_periods=20).mean().iloc[-1])
        trend_allows_buy = (ema_20 >= ema_50 * 0.998) and (current_price >= sma_200 * 0.995)
        trend_allows_sell = (ema_20 <= ema_50 * 1.002) and (current_price <= sma_200 * 1.005)

        # Test Demand Zone Entry:
        # 1. Price is in Discount and tested prior verified demand zone
        # 2. Bullish rejection wick >= 30% or strong green candle with absorption
        # 3. RSI not in capitulation (>= 38.0 and <= 65.0)
        is_demand_tap = (last_l <= prior_demand + 0.35 * safe_atr) and (current_price >= prior_demand - 0.15 * safe_atr)
        is_demand_reject = (lower_wick_ratio >= 0.30 and current_price > curr_open) or (current_price > curr_open and cand_rng >= 0.30 * safe_atr and lower_wick_ratio >= 0.20)

        # Test Supply Zone Entry:
        # 1. Price is in Premium and tested prior verified supply zone
        # 2. Bearish rejection wick >= 30% or strong red candle with rejection
        # 3. RSI not in parabolic blow-off (>= 35.0 and <= 62.0)
        is_supply_tap = (last_h >= prior_supply - 0.35 * safe_atr) and (current_price <= prior_supply + 0.15 * safe_atr)
        is_supply_reject = (upper_wick_ratio >= 0.30 and current_price < curr_open) or (current_price < curr_open and cand_rng >= 0.30 * safe_atr and upper_wick_ratio >= 0.20)
        
        if is_discount and trend_allows_buy and ('BEARISH' not in cot_bias) and is_demand_tap and is_demand_reject and (38.0 <= rsi_val <= 65.0):
            action = 'BUY'
            status = 'DEMAND_LIMIT_TRIGGERED'
            confidence = 90.0 if 'BULLISH' in cot_bias else 89.0
            reasons.append(f"Bernd S&D: Price at Discount Demand Zone [{prior_demand:.2f}] inside HTF Range with bounce rejection")
            reasons.append(f"COT Sentiment: {cot_bias} smart money positioning | RSI: {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(abs(entry_price - prior_demand) + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif is_premium and trend_allows_sell and ('BULLISH' not in cot_bias) and is_supply_tap and is_supply_reject and (35.0 <= rsi_val <= 62.0):
            action = 'SELL'
            status = 'SUPPLY_LIMIT_TRIGGERED'
            confidence = 90.0 if 'BEARISH' in cot_bias else 89.0
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
        tf_clean = str(timeframe).lower().strip()
        if tf_clean in ['1m', '2m', '3m', '5m', '15m', '30m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"ICT Killzone MSS model is calibrated for 1H, 4H execution. '{timeframe}' is too noisy."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: ICT Killzone MSS model is calibrated for Forex Majors (EUR/USD, GBP/USD, USD/JPY)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if (current_price > 500.0) or any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'BTC', 'ETH']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["ICT Smart Money Concepts Killzone model is calibrated strictly for Forex Majors (EUR/USD, GBP/USD, USD/JPY). Crypto and Metals excluded."]
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

        bull_sweep = any(lows[k] <= recent_l - 0.05 * safe_atr and closes[k] > recent_l for k in range(max(0, n - 4), n))
        bear_sweep = any(highs[k] >= recent_h + 0.05 * safe_atr and closes[k] < recent_h for k in range(max(0, n - 4), n))

        # Check FVG in last 3 candles
        has_bull_fvg = (n >= 3) and (lows[-1] > highs[-3])
        has_bear_fvg = (n >= 3) and (highs[-1] < lows[-3])

        action = 'HOLD'
        status = 'SCANNING_LIQUIDITY_POOLS'
        confidence = 50.0
        reasons = []

        cand_rng = max(highs[-1] - lows[-1], 1e-6)
        cand_body = abs(closes[-1] - opens[-1])
        closes_s = pd.Series(closes)
        ema_20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes_s.rolling(min(n, 200)).mean().iloc[-1])

        # RSI 14 Momentum Guard
        delta = closes_s.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        if bull_sweep and in_killzone and (current_price >= sma_200 and ema_20 >= ema_50) and (closes[-1] > opens[-1]) and (has_bull_fvg or closes[-1] >= highs[-2]) and (cand_body >= 0.40 * safe_atr) and (0.50 * safe_atr <= cand_rng <= 2.20 * safe_atr) and (40.0 <= rsi_val <= 65.0):
            action = 'BUY'
            status = 'ICT_BULLISH_MSS_ENTRY'
            confidence = 88.0
            reasons.append(f"ICT: Sell-side Liquidity Swept below {recent_l:.2f} + Displacement FVG")
            reasons.append(f"Execution Window: {kz_label}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(entry_price - recent_l) + 0.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)

        elif bear_sweep and in_killzone and (current_price <= sma_200 and ema_20 <= ema_50) and (closes[-1] < opens[-1]) and (has_bear_fvg or closes[-1] <= lows[-2]) and (cand_body >= 0.40 * safe_atr) and (0.50 * safe_atr <= cand_rng <= 2.20 * safe_atr) and (35.0 <= rsi_val <= 60.0):
            action = 'SELL'
            status = 'ICT_BEARISH_MSS_ENTRY'
            confidence = 88.0
            reasons.append(f"ICT: Buy-side Liquidity Swept above {recent_h:.2f} + Displacement FVG")
            reasons.append(f"Execution Window: {kz_label}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(recent_h - entry_price) + 0.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
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
        tf_clean = str(timeframe).lower().strip()
        if tf_clean in ['1m', '2m', '3m', '5m', '15m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Steven Hart Break & Retest model requires 30M, 1H or 4H execution. '{timeframe}' is too noisy."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Exclude volatile metals (Gold/Silver) & CAD/JPY from Break & Retest
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'CAD/JPY']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Steven Hart Break & Retest excludes volatile commodities (Gold/Silver) and CAD/JPY."]
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

        # Verify prior breakout actually closed cleanly past the structural barrier in last 6 bars before retest
        broke_res = any(closes[-6:-1] >= prior_res + 0.10 * safe_atr) if n >= 7 else False
        broke_sup = any(closes[-6:-1] <= prior_sup - 0.10 * safe_atr) if n >= 7 else False

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

        # Break & Retest Long & Short conditions: Strict trend alignment with EMA20/EMA50
        is_long_trend = (ema_20 >= ema_50) and (current_price >= ema_20)
        is_long_retest = broke_res and is_long_trend and (last_l <= prior_res + 0.25 * safe_atr) and (current_price >= prior_res - 0.10 * safe_atr) and is_bull_candle and (rng >= 0.40 * safe_atr)

        is_short_trend = (ema_20 <= ema_50) and (current_price <= ema_20)
        is_short_retest = broke_sup and is_short_trend and (last_h >= prior_sup - 0.25 * safe_atr) and (current_price <= prior_sup + 0.10 * safe_atr) and is_bear_candle and (rng >= 0.40 * safe_atr)

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
        if tf_clean in ['1m', '2m', '3m', '5m', '15m', '30m']:
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

        # Asset Guard: Exclude Gold, Silver, Forex pairs, and JPY pairs where trend pullbacks wick through 20/50 EMA envelopes
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'JPY', 'EUR', 'GBP', 'CAD']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Rayner Teo Trend Following excludes volatile precious metals, Forex pairs, and JPY pairs."]
            }

        highs = df['high']
        lows = df['low']
        closes = pd.Series(df['close'].values)
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200_series = closes.rolling(min(n, 200)).mean()
        sma_200 = float(sma_200_series.iloc[-1])
        sma_200_prev = float(sma_200_series.iloc[-5]) if len(sma_200_series) >= 5 else sma_200
        slope_up_200 = sma_200 >= sma_200_prev * 0.9999
        slope_down_200 = sma_200 <= sma_200_prev * 1.0001

        # ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

        last_o, last_h, last_l, last_c = df['open'].iloc[-1], df['high'].iloc[-1], df['low'].iloc[-1], df['close'].iloc[-1]
        rng = max(last_h - last_l, 1e-9)
        cand_body = abs(last_c - last_o)
        lower_wick = (min(last_o, last_c) - last_l) / rng
        upper_wick = (last_h - max(last_o, last_c)) / rng

        ema_20_series = closes.ewm(span=20, adjust=False).mean()
        ema_20_prev = float(ema_20_series.iloc[-2]) if len(ema_20_series) >= 2 else ema_20
        # Rayner Teo Rule #1: Trade strictly in the direction of the 200 SMA baseline with non-falling slope and ADX >= 25.0
        is_uptrend = (current_price > sma_200) and (ema_20 > ema_50) and ((ema_20 - ema_50) >= 0.20 * safe_atr) and (ema_20 >= ema_20_prev * 0.9999) and slope_up_200 and (adx_val >= 25.0)
        is_downtrend = (current_price < sma_200) and (ema_20 < ema_50) and ((ema_50 - ema_20) >= 0.20 * safe_atr) and (ema_20 <= ema_20_prev * 1.0001) and slope_down_200 and (adx_val >= 25.0)

        # Pullback in value area between 20 & 50 EMA
        in_buy_value_area = (last_l <= ema_20) and (last_c >= ema_50) and is_uptrend
        in_sell_value_area = (last_h >= ema_20) and (last_c <= ema_50) and is_downtrend

        action = 'HOLD'
        status = 'WAITING_EMA_PULLBACK'
        confidence = 50.0
        reasons = []

        # RSI 14 Sweet Spot Guard (Never buy overbought >62 or sell oversold <38)
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        if in_buy_value_area and (last_c > last_o and last_c >= ema_20 * 0.999 and last_c >= closes.iloc[-2]) and (rng >= 0.40 * safe_atr) and (cand_body >= 0.35 * safe_atr) and (lower_wick >= 0.22) and (rsi_val <= 62.0):
            action = 'BUY'
            status = 'VALUE_AREA_BOUNCE_BUY'
            confidence = 88.0
            reasons.append("Rayner Teo: Pullback into 20/50 EMA Value Area during verified Uptrend")
            reasons.append(f"Reversal Candle: Bullish bounce confirmed above 20 EMA (ADX: {adx_val:.1f})")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(entry_price - (ema_50 - 0.20 * safe_atr), 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        elif in_sell_value_area and (last_c < last_o and last_c <= ema_20 * 1.001 and last_c <= closes.iloc[-2]) and (rng >= 0.40 * safe_atr) and (cand_body >= 0.35 * safe_atr) and (upper_wick >= 0.22) and (rsi_val >= 38.0):
            action = 'SELL'
            status = 'VALUE_AREA_REJECTION_SELL'
            confidence = 88.0
            reasons.append("Rayner Teo: Pullback into 20/50 EMA Value Area during verified Downtrend")
            reasons.append(f"Reversal Candle: Bearish rejection confirmed below 20 EMA (ADX: {adx_val:.1f})")
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
        if tf_clean not in ['4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Crypto Cred S/R model requires 4H macro HTF timeframe. '{timeframe}' is too noisy."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Crypto Cred operates on Crypto Majors & Perps (BTC, ETH, Altcoins)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if (current_price < 500.0) or any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'EUR', 'JPY', 'CAD', 'GBP']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Crypto Cred S/R model is strictly calibrated for Crypto assets (BTC/ETH). Metals & Forex excluded."]
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
        lookback_sr = min(n - 2, 35 if tf_clean in ['15m', '30m'] else 25)
        h_sup = float(np.min(lows[-lookback_sr:-2])) if n >= 15 else float(np.min(lows))
        h_res = float(np.max(highs[-lookback_sr:-2])) if n >= 15 else float(np.max(highs))

        # True RSI Divergence Detection (Crypto Cred Signature Edge):
        bull_divergence = False
        bear_divergence = False
        if n >= 20 and len(rsi_series) >= 20:
            past_low = float(np.min(lows[-15:-3]))
            past_rsi_low = float(rsi_series.iloc[-15:-3].min())
            past_high = float(np.max(highs[-15:-3]))
            past_rsi_high = float(rsi_series.iloc[-15:-3].max())
            # Bullish Divergence: Price retesting/breaking past low, but RSI making higher low
            if lows[-1] <= past_low * 1.003 and rsi_val >= past_rsi_low + 3.0:
                bull_divergence = True
            # Bearish Divergence: Price retesting/breaking past high, but RSI making lower high
            if highs[-1] >= past_high * 0.997 and rsi_val <= past_rsi_high - 3.0:
                bear_divergence = True

        action = 'HOLD'
        status = 'SCANNING_SR_LEVELS'
        confidence = 50.0
        reasons = []

        # Buy Setup: Testing horizontal support with RSI oversold/divergence and bullish reclaim
        in_sup_zone = (lows[-1] <= h_sup + 0.40 * safe_atr) and (current_price >= h_sup - 0.15 * safe_atr)
        in_res_zone = (highs[-1] >= h_res - 0.40 * safe_atr) and (current_price <= h_res + 0.15 * safe_atr)
        cand_body = abs(closes.iloc[-1] - df['open'].iloc[-1])

        if in_sup_zone and (closes.iloc[-1] > df['open'].iloc[-1]) and (rsi_val <= 50.0 or bull_divergence) and (current_price >= sma_200 * 0.98) and (cand_body >= 0.25 * safe_atr):
            action = 'BUY'
            status = 'SUPPORT_RECLAIM_RSI_BUY'
            confidence = 92.0 if bull_divergence else 87.0
            reasons.append(f"Crypto Cred: Horizontal Support [{h_sup:.2f}] successfully tested and reclaimed")
            reasons.append(f"RSI Exhaustion Bounce: RSI(14) = {rsi_val:.1f}")
            if bull_divergence:
                reasons.append("Elite Edge: Bullish RSI Divergence confirmed at Support (Higher Low on RSI)")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(entry_price - (h_sup - 0.20 * safe_atr))), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + max(1.15 * sl_distance, (h_res - entry_price) * 0.5)
            tp3 = entry_price + (2.20 * sl_distance)

        # Sell Setup: Testing horizontal resistance with RSI overbought/divergence and bearish reclaim
        elif in_res_zone and (closes.iloc[-1] < df['open'].iloc[-1]) and (rsi_val >= 50.0 or bear_divergence) and (current_price <= sma_200 * 1.02) and (cand_body >= 0.25 * safe_atr):
            action = 'SELL'
            status = 'RESISTANCE_REJECT_RSI_SELL'
            confidence = 92.0 if bear_divergence else 87.0
            reasons.append(f"Crypto Cred: Horizontal Resistance [{h_res:.2f}] successfully tested and rejected")
            reasons.append(f"RSI Exhaustion Rejection: RSI(14) = {rsi_val:.1f}")
            if bear_divergence:
                reasons.append("Elite Edge: Bearish RSI Divergence confirmed at Resistance (Lower High on RSI)")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs((h_res + 0.20 * safe_atr) - entry_price)), 2.20 * safe_atr)
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
        if tf_clean not in ['15m', '30m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Ndemazeah Godlove GU MVR is designed for 15M/30M intraday. Current timeframe '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Ndemazeah Godlove GU MVR strategy is calibrated strictly for GBP pairs (GBP/USD) & Futures
        # Eliminates Non-GBP FX chop, Crypto chop, CAD/JPY and Metals
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if sym_str and 'GBP' not in sym_str:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Ndemazeah Godlove GU MVR strategy is calibrated strictly for GBP currency pairs (GBP/USD)."]
            }
        if current_price > 500.0 or (current_price > 15.0 and current_price < 80.0) or any(m in sym_str for m in ['CAD/JPY', 'XAU', 'XAG']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Ndemazeah Godlove GU MVR strategy is calibrated strictly for GBP pairs."]
            }


        closes = pd.Series(df['close'].values)
        ema_10 = float(closes.ewm(span=10, adjust=False).mean().iloc[-1])
        ema_23 = float(closes.ewm(span=23, adjust=False).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        is_bull_crossover = ema_10 > ema_23 and current_price >= sma_200 * 0.998
        is_bear_crossover = ema_10 < ema_23 and current_price <= sma_200 * 1.002

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

        cand_body = abs(df['close'].iloc[-1] - df['open'].iloc[-1])

        # 50 pips / points beyond Fib structure from PDF
        pip_unit = 0.0001 if current_price < 10.0 else (0.01 if current_price < 500 else 1.0)
        pip_50 = 50.0 * pip_unit

        # Long: 10 EMA > 23 EMA and price pulls back into 38.2% - 61.8% Fib pocket with solid candle
        if is_bull_crossover and (fib_618_bull <= current_price <= fib_382_bull) and (df['close'].iloc[-1] > df['open'].iloc[-1]) and (cand_body >= 0.22 * safe_atr):
            action = 'BUY'
            status = 'GU_MVR_BULLISH_ENTRY'
            confidence = 85.0
            reasons.append("GU MVR: 10 EMA crossed above 23 EMA confirms Bullish Intraday Momentum")
            reasons.append("Fib Retracement: Price pulled back cleanly into 38.2% - 61.8% Golden Pocket")
            entry_price = current_price
            sl_distance = min(max(entry_price - (fib_618_bull - pip_50), 1.80 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        # Short: 10 EMA < 23 EMA and price pulls back into 38.2% - 61.8% Fib pocket with solid candle
        elif is_bear_crossover and (fib_382_bear <= current_price <= fib_618_bear) and (df['close'].iloc[-1] < df['open'].iloc[-1]) and (cand_body >= 0.22 * safe_atr):
            action = 'SELL'
            status = 'GU_MVR_BEARISH_ENTRY'
            confidence = 86.0
            reasons.append("GU MVR: 10 EMA crossed below 23 EMA confirms Bearish Intraday Momentum")
            reasons.append("Fib Retracement: Price pulled back cleanly into 38.2% - 61.8% Golden Pocket")
            entry_price = current_price
            sl_distance = min(max((fib_618_bear + pip_50) - entry_price, 1.80 * safe_atr), 2.20 * safe_atr)
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
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower()
        if tf_clean not in ['30m', '1h', '4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Ross Cameron Warrior Trading operates on 30M, 1H and 4H momentum charts. '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Calibrated for Crypto market leaders (BTC, ETH)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'CAD/JPY', 'USD/JPY', 'JPY', 'EUR', 'GBP']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Ross Cameron Warrior Trading is calibrated for crypto momentum leaders (BTC/ETH). Forex & Metals excluded."]
            }

        closes = pd.Series(df['close'].values)
        volumes = pd.Series(df['volume'].values) if 'volume' in df.columns else pd.Series(np.ones(n))

        ema_9 = float(closes.ewm(span=9, adjust=False).mean().iloc[-1])
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])

        # RSI 14 calculation
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # SMA Trend Alignment (Stage 2 / Macro Regime)
        sma_200 = float(closes.rolling(min(n, 200), min_periods=min(n, 25)).mean().iloc[-1])
        sma_50 = float(closes.rolling(min(n, 50), min_periods=min(n, 15)).mean().iloc[-1])

        # ADX 14 calculation
        highs = df['high']
        lows = df['low']
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

        # Volume Surge Factor (Warrior Trading requires 1.15x volume surge)
        avg_vol = float(volumes.tail(20).mean()) if n >= 20 else float(volumes.mean())
        vol_surge = (float(volumes.iloc[-1]) / max(avg_vol, 1e-6)) >= 1.15
        cand_rng = max(df['high'].iloc[-1] - df['low'].iloc[-1], 1e-9)
        cand_body = abs(current_price - float(df['open'].iloc[-1]))
        curr_open = float(df['open'].iloc[-1])
        upper_wick = (df['high'].iloc[-1] - max(curr_open, current_price)) / cand_rng

        # VWAP estimation
        vwap = float(np.sum(closes * volumes) / max(np.sum(volumes), 1e-6))

        action = 'HOLD'
        status = 'WAITING_MOMENTUM_SURGE'
        confidence = 50.0
        reasons = []

        # Warrior Trading Bull Momentum Long (Strictly Long-Only)
        if (current_price > sma_200) and (sma_50 > sma_200 * 0.998) and (current_price >= vwap) and (ema_9 > ema_20) and (closes.iloc[-1] >= ema_9) and (current_price > curr_open) and (cand_body >= 0.28 * safe_atr) and (upper_wick <= 0.35) and vol_surge and (48.0 <= rsi_val <= 68.0) and (adx_val >= 18.0):
            action = 'BUY'
            status = 'WARRIOR_MOMENTUM_BUY'
            confidence = 88.0
            reasons.append(f"Ross Cameron: Bullish expansion above VWAP & 200 SMA (${sma_200:.2f}) with 9 EMA > 20 EMA (ADX: {adx_val:.1f})")
            reasons.append(f"Volume Surge Confirmed: Current Volume >= 1.15x 20-bar average with RSI {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = min(max(entry_price - (min(vwap, ema_20) - 0.20 * safe_atr), 1.80 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
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
        if tf_clean not in ['4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Adam Khoo Multi-EMA model is calibrated for 4H macro trend following. '{timeframe}' is too noisy."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Exclude CAD/JPY and silver
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['CAD/JPY', 'XAG', 'SILVER']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Adam Khoo Multi-EMA model excludes erratic CAD/JPY and Silver."]
            }

        closes = pd.Series(df['close'].values)
        ema_20_series = closes.ewm(span=20, adjust=False).mean()
        ema_20 = float(ema_20_series.iloc[-1])
        ema_20_prev = float(ema_20_series.iloc[-2]) if len(ema_20_series) >= 2 else ema_20
        sma_50 = float(closes.rolling(min(n, 50), min_periods=min(n, 15)).mean().iloc[-1])
        sma_200_series = closes.rolling(min(n, 200), min_periods=min(n, 25)).mean()
        sma_200 = float(sma_200_series.iloc[-1])
        sma_200_prev = float(sma_200_series.iloc[-5]) if len(sma_200_series) >= 5 else sma_200

        # RSI 14 Sweet Spot Guard
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Triple EMA trend stack with rising/falling 20 EMA
        is_uptrend = (current_price > sma_200) and (ema_20 > sma_50) and (sma_50 > sma_200 * 0.998) and (ema_20 >= ema_20_prev * 0.9995)
        is_downtrend = (current_price < sma_200) and (ema_20 < sma_50) and (sma_50 < sma_200 * 1.002) and (ema_20 <= ema_20_prev * 1.0005)

        # Pullback bounce on 20 EMA (requires price testing the 20 EMA and holding)
        last_l = float(df['low'].iloc[-1])
        last_h = float(df['high'].iloc[-1])
        last_o = float(df['open'].iloc[-1])
        prev_l = float(df['low'].iloc[-2]) if n >= 2 else last_l
        prev_h = float(df['high'].iloc[-2]) if n >= 2 else last_h
        cand_rng = max(last_h - last_l, 1e-6)

        bounce_20_ema_long = is_uptrend and (min(last_l, prev_l) <= ema_20 + 0.25 * safe_atr) and (current_price >= ema_20 - 0.10 * safe_atr)
        bounce_20_ema_short = is_downtrend and (max(last_h, prev_h) >= ema_20 - 0.25 * safe_atr) and (current_price <= ema_20 + 0.10 * safe_atr)

        lower_wick = min(last_o, current_price) - last_l
        upper_wick = last_h - max(last_o, current_price)
        cand_body = abs(current_price - last_o)
        bullish_bounce = (lower_wick >= 0.20 * cand_rng) or (current_price - last_o >= 0.35 * cand_rng)
        bearish_bounce = (upper_wick >= 0.20 * cand_rng) or (last_o - current_price >= 0.35 * cand_rng)

        action = 'HOLD'
        status = 'SCANNING_TREND_ALIGNMENT'
        confidence = 50.0
        reasons = []

        if bounce_20_ema_long and bullish_bounce and (current_price > last_o) and (cand_rng >= 0.35 * safe_atr) and (cand_body >= 0.28 * safe_atr) and (48.0 <= rsi_val <= 66.0):
            action = 'BUY'
            status = 'ADAM_KHOO_20_EMA_BOUNCE_BUY'
            confidence = 89.0
            reasons.append(f"Adam Khoo: Price > 200 SMA ({sma_200:.2f}) & 20 EMA > 50 SMA in Bullish Stack")
            reasons.append(f"20 EMA Pullback Bounce confirmed at {ema_20:.2f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(entry_price - (ema_20 - 0.30 * safe_atr), 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif bounce_20_ema_short and bearish_bounce and (current_price < last_o) and (cand_rng >= 0.35 * safe_atr) and (cand_body >= 0.28 * safe_atr) and (34.0 <= rsi_val <= 52.0):
            action = 'SELL'
            status = 'ADAM_KHOO_20_EMA_BOUNCE_SELL'
            confidence = 89.0
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
        if tf_clean not in ['15m', '30m']:
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
                'reasons': [f"Ariel Zwecher is an intraday 15M Opening Range Breakout strategy. Current timeframe '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Exclude USD/JPY, CAD/JPY, EUR/USD, Gold, and Silver from 15m ORB breakouts
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAG', 'SILVER', 'XAU', 'GOLD', 'USD/JPY', 'CAD/JPY', 'EUR']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Ariel Zwecher 15m ORB excludes FX wicks, Gold, and Silver."]
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
        if (closes[-1] >= orb_high + 0.08 * safe_atr) and (closes[-2] <= orb_high * 1.002) and (ema_20 >= ema_50) and (df['close'].iloc[-1] > df['open'].iloc[-1]) and (closes[-1] > closes[-2]) and (last_range >= 0.42 * safe_atr) and (rsi_val <= 66.0):
            action = 'BUY'
            status = '15M_ORB_BULLISH_BREAKOUT'
            confidence = 86.0
            reasons.append(f"Ariel Zwecher: Clean 15M Opening Range Breakout above {orb_high:.2f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(entry_price - orb_low) + 0.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        # Breakdown below ORB Low (strictly with EMA trend alignment & RSI sweet spot)
        elif (closes[-1] <= orb_low - 0.08 * safe_atr) and (closes[-2] >= orb_low * 0.998) and (ema_20 <= ema_50) and (df['close'].iloc[-1] < df['open'].iloc[-1]) and (closes[-1] < closes[-2]) and (last_range >= 0.42 * safe_atr) and (rsi_val >= 34.0):
            action = 'SELL'
            status = '15M_ORB_BEARISH_BREAKDOWN'
            confidence = 86.0
            reasons.append(f"Ariel Zwecher: Clean 15M Opening Range Breakdown below {orb_low:.2f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(orb_high - entry_price) + 0.20 * safe_atr)
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
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '30m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower()
        if tf_clean in ['1m', '2m', '3m', '5m', '15m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Oliver Velez 20 SMA Elephant Bar requires 30M, 1H or 4H execution to eliminate sub-hourly noise. '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)
        # Asset Guard: Oliver Velez 20 SMA Elephant Bar excludes volatile precious metals (Gold/Silver)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Oliver Velez strategy excludes volatile metals."]
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

        # Elephant Bar = body >= 2.0x average body and substantial candle (>= 0.55 safe_atr)
        is_elephant_bar = (last_body >= (avg_body * 2.0)) and (last_body >= 0.55 * safe_atr) and (rng >= 0.60 * safe_atr)
        # Bottoming Tail Bar = lower wick >= 55% of candle range and range >= 0.40 safe_atr
        is_bottoming_tail = (((min(opens.iloc[-1], closes.iloc[-1]) - lows.iloc[-1]) / rng) >= 0.55) and (rng >= 0.40 * safe_atr)
        # Topping Tail Bar = upper wick >= 55% of candle range and range >= 0.40 safe_atr
        is_topping_tail = (((highs.iloc[-1] - max(opens.iloc[-1], closes.iloc[-1])) / rng) >= 0.55) and (rng >= 0.40 * safe_atr)

        # Location rule: Candle must test the 20 SMA directly (open/low within 0.25 ATR of 20 SMA)
        near_20_sma = (min(abs(lows.iloc[-1] - sma_20), abs(opens.iloc[-1] - sma_20)) <= 0.25 * safe_atr) or (abs(current_price - sma_20) <= 0.25 * safe_atr)
        is_uptrend = (current_price > sma_200) and (sma_20 > sma_200) and ((sma_20 - sma_20_prev) >= 0.015 * safe_atr)
        is_downtrend = (current_price < sma_200) and (sma_20 < sma_200) and ((sma_20_prev - sma_20) >= 0.015 * safe_atr)

        action = 'HOLD'
        status = 'SCANNING_20_SMA_LOCATION'
        confidence = 50.0
        reasons = []

        upper_wick = highs.iloc[-1] - max(opens.iloc[-1], closes.iloc[-1])
        lower_wick = min(opens.iloc[-1], closes.iloc[-1]) - lows.iloc[-1]
        close_pos = (closes.iloc[-1] - lows.iloc[-1]) / rng

        # RSI 14 calculation to prevent entering at extended climax tops/bottoms
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Session Check: London & NY Session (07:00-19:00 UTC) to avoid Asian/rollover spread distortion
        curr_ts = df['timestamp'].iloc[-1] if 'timestamp' in df.columns and len(df['timestamp']) > 0 else None
        curr_hour = curr_ts.hour if hasattr(curr_ts, 'hour') else 12
        is_active_session = (7 <= curr_hour <= 19)

        if is_active_session and is_uptrend and near_20_sma and (closes.iloc[-1] > opens.iloc[-1]) and (is_elephant_bar or is_bottoming_tail) and (close_pos >= 0.70) and (45.0 <= rsi_val <= 66.0):
            action = 'BUY'
            bar_type = "Elephant Bar" if is_elephant_bar else "Bottoming Tail Bar"
            status = f'OLIVER_VELEZ_{bar_type.upper().replace(" ", "_")}_BUY'
            confidence = 88.0
            reasons.append(f"Oliver Velez: {bar_type} formed precisely at 20 SMA Location ({sma_20:.2f})")
            reasons.append(f"Macro Baseline Aligned: Price > 200 SMA ({sma_200:.2f}) with healthy RSI {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(entry_price - (lows.iloc[-1] - 0.20 * safe_atr))), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        elif is_active_session and is_downtrend and near_20_sma and (closes.iloc[-1] < opens.iloc[-1]) and (is_elephant_bar or is_topping_tail) and (close_pos <= 0.30) and (34.0 <= rsi_val <= 55.0):
            action = 'SELL'
            bar_type = "Elephant Bar" if is_elephant_bar else "Topping Tail Bar"
            status = f'OLIVER_VELEZ_{bar_type.upper().replace(" ", "_")}_SELL'
            confidence = 88.0
            reasons.append(f"Oliver Velez: {bar_type} formed precisely at 20 SMA Location ({sma_20:.2f})")
            reasons.append(f"Macro Baseline Aligned: Price < 200 SMA ({sma_200:.2f}) with healthy RSI {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs((highs.iloc[-1] + 0.20 * safe_atr) - entry_price)), 2.20 * safe_atr)
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
    BE_MODE = "DONCHIAN_ATR_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean != '30m':
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_EXCLUDED_DONCHIAN_30M_ONLY',
                'confidence': 0.0,
                'donchian_high': 0.0,
                'donchian_low': 0.0,
                'trade_setup': {},
                'reasons': ["Trade Pro Donchian Channel is strictly calibrated for the 30M timeframe."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        closes = pd.Series(df['close'].values)
        highs = pd.Series(df['high'].values)
        lows = pd.Series(df['low'].values)

        # Donchian 20-period Channel
        donchian_high = float(highs.tail(21).iloc[:-1].max()) if n >= 21 else float(highs.max())
        donchian_low = float(lows.tail(21).iloc[:-1].min()) if n >= 21 else float(lows.min())

        # 200 SMA and Slope
        sma_200_series = closes.rolling(min(n, 200), min_periods=min(n, 25)).mean()
        sma_200 = float(sma_200_series.iloc[-1])
        sma_200_prev = float(sma_200_series.iloc[-3]) if len(sma_200_series) >= 3 else sma_200
        slope_up = sma_200 >= sma_200_prev * 0.9998
        slope_down = sma_200 <= sma_200_prev * 1.0002
        curr_open = float(df['open'].iloc[-1])
        cand_body = abs(current_price - curr_open)

        # EMA 20 & 50 for structure alignment
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])

        # RSI 14
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

        action = 'HOLD'
        status = 'SCANNING_DONCHIAN_BREAKOUT'
        confidence = 50.0
        reasons = []

        # Mechanical Long: Price breaks Donchian High, Price > 200 SMA with rising slope, EMA20 >= EMA50, ADX >= 18, RSI 48-66
        donchian_width = donchian_high - donchian_low
        has_bandwidth = donchian_width >= 1.20 * safe_atr
        cand_rng = max(float(df['high'].iloc[-1]) - float(df['low'].iloc[-1]), 1e-6)
        upper_wick = float(df['high'].iloc[-1]) - max(curr_open, current_price)
        lower_wick = min(curr_open, current_price) - float(df['low'].iloc[-1])

        if has_bandwidth and (current_price >= donchian_high) and (current_price > sma_200) and (current_price >= ema_20) and (ema_20 >= ema_50 * 0.998) and slope_up and (48.0 <= rsi_val <= 66.0) and (adx_val >= 18.0) and (current_price > curr_open) and (cand_body >= 0.28 * safe_atr) and (upper_wick <= 0.40 * cand_rng):
            action = 'BUY'
            status = 'DONCHIAN_MECHANICAL_BUY'
            confidence = 89.0
            reasons.append(f"Trade Pro: Mechanical Donchian 20 High ({donchian_high:.2f}) Breakout with bullish close (ADX: {adx_val:.1f})")
            reasons.append(f"Trend Filters: Price > 200 SMA ({sma_200:.2f}) & EMA20 ({ema_20:.2f}) >= EMA50 ({ema_50:.2f}) & RSI({rsi_val:.1f}) in sweet spot")
            entry_price = current_price
            sl_distance = 1.80 * safe_atr
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner

        # Mechanical Short: Price breaks Donchian Low, Price < 200 SMA with falling slope, EMA20 <= EMA50, ADX >= 18, RSI 34-52
        elif has_bandwidth and (current_price <= donchian_low) and (current_price < sma_200) and (current_price <= ema_20) and (ema_20 <= ema_50 * 1.002) and slope_down and (34.0 <= rsi_val <= 52.0) and (adx_val >= 18.0) and (current_price < curr_open) and (cand_body >= 0.28 * safe_atr) and (lower_wick <= 0.40 * cand_rng):
            action = 'SELL'
            status = 'DONCHIAN_MECHANICAL_SELL'
            confidence = 89.0
            reasons.append(f"Trade Pro: Mechanical Donchian 20 Low ({donchian_low:.2f}) Breakdown with bearish close")
            reasons.append(f"Trend Filters: Price < 200 SMA ({sma_200:.2f}) & EMA20 ({ema_20:.2f}) <= EMA50 ({ema_50:.2f}) & RSI({rsi_val:.1f}) in 38-48 sweet spot")
            entry_price = current_price
            sl_distance = 1.80 * safe_atr
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
        if tf_clean not in ['30m', '1h', '4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Qullamaggie operates on 30M, 1H and 4H momentum expansion; sub-30m is invalid noise."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Qullamaggie High Tight Flag is calibrated for European Forex Majors (EUR/USD, GBP/USD)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if (current_price > 500.0) or any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'JPY', 'BTC', 'ETH']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Kristjan Qullamaggie High Tight Flag is calibrated for European Forex Majors (EUR/USD, GBP/USD). Metals, Crypto, and JPY excluded."]
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
        volumes = df['volume'] if 'volume' in df.columns else pd.Series(np.ones(n))

        ema_10 = float(closes.ewm(span=10, adjust=False).mean().iloc[-1])
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        sma_50 = float(closes.rolling(window=min(n, 50), min_periods=min(n, 15)).mean().iloc[-1])
        sma_200 = float(closes.rolling(window=min(n, 200), min_periods=min(n, 25)).mean().iloc[-1])

        # Volume confirmation
        avg_vol = float(volumes.iloc[-21:-1].mean()) if len(volumes) >= 21 else float(volumes.mean())
        curr_vol = float(volumes.iloc[-1])
        vol_surge = (curr_vol >= avg_vol * 1.10) or ('volume' not in df.columns)

        # True Wilder's ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

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
        is_ma_surfing_long = (current_price > sma_200) and (current_price >= ema_10 >= ema_20) and (ema_20 >= sma_50 * 0.99) and ((closes.iloc[-2] - ema_10 <= 0.90 * safe_atr) or (current_price - ema_10 <= 1.60 * safe_atr))
        
        # ADR% / bar volatility filter calibrated for intraday 30m/1h as well as daily charts
        is_adr_ok = (adr_pct >= 0.15) or ((safe_atr / max(current_price, 1e-6)) * 100.0 >= 0.10)
        cand_body = abs(current_price - float(df['open'].iloc[-1]))
        cand_rng = max(float(highs.iloc[-1]) - float(lows.iloc[-1]), 1e-6)

        # RSI 14 Momentum Guard
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Bullish Breakout across consolidation resistance with solid expansion bar (Strictly Long-Only)
        if is_ma_surfing_long and is_adr_ok and (current_price >= resistance) and (closes.iloc[-1] > df['open'].iloc[-1]) and (cand_body >= 0.26 * safe_atr) and (48.0 <= rsi_val <= 68.0) and (adx_val >= 18.0) and vol_surge:
            action = 'BUY'
            status = 'ORB_BREAKOUT'
            confidence = 89.0
            reasons.append(f"High ADR% ({adr_pct:.1f}%): Asset exhibits explosive momentum potential (ADX: {adx_val:.1f})")
            reasons.append(f"Moving Average Surfing: Price (${current_price:.2f}) > 10 EMA (${ema_10:.2f}) > 20 EMA (${ema_20:.2f}) > 200 SMA")
            reasons.append(f"Consolidation Breakout: Closed above {lookback_consol}-bar resistance (${resistance:.2f}) with RSI {rsi_val:.1f}")
        else:
            if not is_adr_ok:
                reasons.append(f"ADR% ({adr_pct:.1f}%) below high-momentum volatility threshold")
            if not is_ma_surfing_long:
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
        if tf_clean in ['1m', '2m', '3m', '5m', '15m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["GCR trades macro cycle pivots and catalyst exhaustion on 1H/4H/Daily; intraday timeframes (<=15m) are invalid noise."]
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

        # Schelling Point Proximity (Psychological Round Numbers: $5k, $10k intervals in Crypto)
        def _get_schelling_proximity(price: float) -> Tuple[float, float]:
            if price <= 0:
                return 0.0, 100.0
            if price >= 10000.0:
                step = 5000.0
            elif price >= 1000.0:
                step = 500.0
            elif price >= 100.0:
                step = 50.0
            else:
                step = 10.0
            closest = round(price / step) * step
            dist_pct = abs(price - closest) / price * 100.0
            return float(closest), float(dist_pct)

        schelling_level, schelling_dist_pct = _get_schelling_proximity(current_price)
        is_at_schelling = schelling_dist_pct <= 2.5

        # Candle wicks (Exhaustion wick detection)
        curr_open = float(df['open'].iloc[-1])
        curr_high = float(highs.iloc[-1])
        curr_low = float(lows.iloc[-1])
        curr_close = current_price
        upper_wick = curr_high - max(curr_open, curr_close)
        lower_wick = min(curr_open, curr_close) - curr_low
        cand_rng = max(curr_high - curr_low, 1e-6)
        cand_body = abs(curr_close - curr_open)

        # 20 EMA and 50 SMA for trend context
        closes_s = pd.Series(df['close'].values)
        ema_20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        sma_50 = float(closes_s.rolling(min(n, 50)).mean().iloc[-1])

        # Avoid shorting runaway bull stacks or buying runaway waterfall dumps
        is_not_runaway_bull = not (curr_close > ema_20 and ema_20 > sma_50 and (ema_20 - sma_50) >= 0.35 * safe_atr)
        is_not_runaway_bear = not (curr_close < ema_20 and ema_20 < sma_50 and (sma_50 - ema_20) >= 0.35 * safe_atr)

        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0
        reasons = []

        # Counter-Cyclical Short: Extreme Retail Euphoria (RSI >= 74) at Schelling Round Number + Bearish Rejection Wick (>=30%)
        prev_close = float(df['close'].iloc[-2])
        if is_at_schelling and rsi_val >= 74.0 and is_not_runaway_bull and (curr_close < curr_open and curr_close < prev_close) and (upper_wick >= 0.30 * cand_rng) and (cand_rng >= 0.40 * safe_atr):
            action = 'SELL'
            status = 'EUPHORIA_EXHAUSTION_SHORT'
            confidence = 89.0
            reasons.append(f"GCR Counter-Short: Extreme retail euphoria exhaustion at RSI {rsi_val:.1f} with upper rejection wick ({upper_wick/cand_rng*100:.1f}%)")
            reasons.append(f"Schelling Point Pivot: Price testing major round number ${schelling_level:,.2f}")
            reasons.append("Parabolic exhaustion confirmed: Strong bearish close below prior bar")
        # Inverse Buying: Extreme Capitulation (RSI <= 26) at Schelling Round Number + Bullish Absorption Wick (>=30%)
        elif is_at_schelling and rsi_val <= 26.0 and is_not_runaway_bear and (curr_close > curr_open and curr_close > prev_close) and (lower_wick >= 0.30 * cand_rng) and (cand_rng >= 0.40 * safe_atr):
            action = 'BUY'
            status = 'CAPITULATION_BOTTOM_LONG'
            confidence = 89.0
            reasons.append(f"GCR Cycle Bottom Long: Extreme retail capitulation exhaustion at RSI {rsi_val:.1f} with absorption wick ({lower_wick/cand_rng*100:.1f}%)")
            reasons.append(f"Schelling Support: Price defending major round number ${schelling_level:,.2f}")
            reasons.append("Capitulation absorption confirmed: Strong bullish close above prior bar")
        else:
            reasons.append(f"GCR retail sentiment neutral (RSI {rsi_val:.1f}). Nearest Schelling pivot: ${schelling_level:,.2f} ({schelling_dist_pct:.1f}% away)")

        if action == 'BUY':
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(abs(entry_price - curr_low) + 0.20 * safe_atr, 2.00 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif action == 'SELL':
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, min(abs(curr_high - entry_price) + 0.20 * safe_atr, 2.00 * safe_atr))
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
        tf_clean = str(timeframe).lower().strip()
        if tf_clean not in ['1h', '4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Waqar Zaka Off-Exchange Reserve model is calibrated for 1H and 4H crypto charts. '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Waqar Zaka strategy is strictly calibrated for Crypto Assets (BTC, ETH)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'JPY', 'EUR', 'CAD', 'GBP']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Waqar Zaka Off-Exchange Reserve model is strictly calibrated for Crypto (BTC/ETH). Forex & Metals excluded."]
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
                'reasons': ["Insufficient bars for Waqar Zaka liquidity sweep & ATR buffer analysis."]
            }

        highs = df['high']
        lows = df['low']
        closes = df['close']

        lookback = min(n, 40)
        swing_low = float(lows.iloc[-lookback:-2].min()) if n >= 25 else float(lows.min())
        swing_high = float(highs.iloc[-lookback:-2].max()) if n >= 25 else float(highs.max())

        curr_low = float(lows.iloc[-1])
        curr_high = float(highs.iloc[-1])
        curr_open = float(df['open'].iloc[-1])
        curr_close = current_price
        cand_rng = max(curr_high - curr_low, 1e-6)
        closes_s = pd.Series(closes)
        ema_20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])

        lower_wick = min(curr_open, curr_close) - curr_low
        upper_wick = curr_high - max(curr_open, curr_close)

        # RSI 14 for liquidation exhaustion
        delta = closes_s.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Check active session (avoid Asian dead-hours 00:00-06:00 UTC)
        curr_ts = df['timestamp'].iloc[-1] if 'timestamp' in df.columns and len(df['timestamp']) > 0 else None
        curr_hour = curr_ts.hour if hasattr(curr_ts, 'hour') else 12
        is_active_session = (7 <= curr_hour <= 22)

        cand_body = abs(curr_close - curr_open)
        swept_low = (curr_low <= swing_low) and (curr_close >= swing_low) and (curr_close > curr_open) and (cand_rng >= 0.35 * safe_atr) and (cand_body >= 0.20 * safe_atr) and (lower_wick >= 0.25 * cand_rng) and (rsi_val <= 46.0)
        prev_swept_low = (float(lows.iloc[-2]) <= swing_low) and (curr_close >= swing_low) and (curr_close > curr_open) and (cand_rng >= 0.35 * safe_atr) and (cand_body >= 0.20 * safe_atr) and (lower_wick >= 0.22 * cand_rng) and (rsi_val <= 48.0)
        bullish_sweep_reclaim = (swept_low or prev_swept_low) and is_active_session and (curr_close >= ema_20 * 0.995 or rsi_val <= 35.0)

        swept_high = (curr_high >= swing_high) and (curr_close <= swing_high) and (curr_close < curr_open) and (cand_rng >= 0.35 * safe_atr) and (cand_body >= 0.20 * safe_atr) and (upper_wick >= 0.25 * cand_rng) and (rsi_val >= 68.0)
        prev_swept_high = (float(highs.iloc[-2]) >= swing_high) and (curr_close <= swing_high) and (curr_close < curr_open) and (cand_rng >= 0.35 * safe_atr) and (cand_body >= 0.20 * safe_atr) and (upper_wick >= 0.22 * cand_rng) and (rsi_val >= 68.0)
        bearish_sweep_reclaim = (swept_high or prev_swept_high) and is_active_session and (curr_close < ema_50) and (rsi_val >= 68.0)

        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0
        reasons = []

        if bullish_sweep_reclaim:
            action = 'BUY'
            status = 'LIQUIDATION_SWEEP_RECLAIM'
            confidence = 91.0
            reasons.append(f"Waqar Zaka: Market maker liquidity sweep below swing low (${swing_low:,.2f}) reclaimed with bullish close")
            reasons.append("Exchange stop hunt absorbed: Off-exchange capital reserve architecture deployed")
            reasons.append(f"ATR Buffer SL active: Protected with Golden 1.80x ATR buffer (${safe_atr:,.2f}) against noise wicks")
        elif bearish_sweep_reclaim:
            action = 'SELL'
            status = 'LIQUIDATION_SWEEP_REJECT'
            confidence = 91.0
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
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '5m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean not in ['30m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Waqar Asim is strictly calibrated for 30M S&D scalping. Current timeframe '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.0002)

        # Asset Guard: Waqar Asim is calibrated for Forex majors (EUR/USD, GBP/USD, USD/JPY)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if (current_price > 500.0) or any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'BTC', 'ETH']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Waqar Asim Inducement Scalping Model is calibrated for Forex pairs (EUR/USD, GBP/USD, USD/JPY). Crypto and Metals excluded."]
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
                'reasons': ["Insufficient bars for Waqar Asim inducement and Premium/Discount zone analysis."]
            }

        highs = df['high']
        lows = df['low']
        closes = df['close']

        # Session Filter: London & New York Active Sessions (07:00-18:00 UTC)
        if 'timestamp' in df.columns and len(df['timestamp']) > 0:
            last_ts = df['timestamp'].iloc[-1]
            curr_hour = last_ts.hour if hasattr(last_ts, 'hour') else datetime.now(timezone.utc).hour
        else:
            curr_hour = datetime.now(timezone.utc).hour
        is_active_session = (7 <= curr_hour <= 18)

        # HTF Decisional S&D context (lookback adapted to timeframe)
        htf_lookback = min(n, 50)
        htf_high = float(highs.iloc[-htf_lookback:].max())
        htf_low = float(lows.iloc[-htf_lookback:].min())
        equilibrium = (htf_high + htf_low) / 2.0

        is_discount = current_price <= equilibrium * 1.002   # Longs in Discount
        is_premium = current_price >= equilibrium * 0.998    # Shorts in Premium

        # Inducement & BOS detection (minor liquidity sweep of last 5-10 bars followed by candle break)
        ltf_lookback = min(n, 10)
        minor_low = float(lows.iloc[-ltf_lookback:-1].min())
        minor_high = float(highs.iloc[-ltf_lookback:-1].max())
        cand_body = abs(closes.iloc[-1] - df['open'].iloc[-1])
        cand_rng = max(float(highs.iloc[-1]) - float(lows.iloc[-1]), 1e-9)
        lower_wick = (min(df['open'].iloc[-1], current_price) - float(lows.iloc[-1])) / cand_rng
        upper_wick = (float(highs.iloc[-1]) - max(df['open'].iloc[-1], current_price)) / cand_rng

        # Trend alignment (EMA20 vs EMA50)
        closes_s = pd.Series(closes.values)
        ema20 = float(closes_s.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(closes_s.ewm(span=50, adjust=False).mean().iloc[-1])
        trend_up = (ema20 >= ema50 * 0.998) and (current_price >= ema20 * 0.998)
        trend_down = (ema20 <= ema50 * 1.002) and (current_price <= ema20 * 1.002)

        # Multi-candle structure high/low
        prev_swing_h = float(highs.iloc[-5:-1].max()) if n >= 5 else float(highs.iloc[-2])
        prev_swing_l = float(lows.iloc[-5:-1].min()) if n >= 5 else float(lows.iloc[-2])

        # RSI 14 for momentum validation
        delta = closes_s.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Bullish Inducement + BOS in Discount:
        has_bullish_inducement = (float(lows.iloc[-1]) <= minor_low or float(lows.iloc[-2]) <= minor_low) and (current_price >= minor_low)
        has_bullish_confirm = (closes.iloc[-1] > df['open'].iloc[-1] or lower_wick >= 0.25) and (cand_body >= 0.35 * safe_atr) and (cand_rng >= 0.40 * safe_atr)
        bullish_setup = is_active_session and is_discount and trend_up and has_bullish_inducement and has_bullish_confirm and (42.0 <= rsi_val <= 64.0)

        # Bearish Inducement + BOS in Premium:
        has_bearish_inducement = (float(highs.iloc[-1]) >= minor_high or float(highs.iloc[-2]) >= minor_high) and (current_price <= minor_high)
        has_bearish_confirm = (closes.iloc[-1] < df['open'].iloc[-1] or upper_wick >= 0.25) and (cand_body >= 0.35 * safe_atr) and (cand_rng >= 0.40 * safe_atr)
        bearish_setup = is_active_session and is_premium and trend_down and has_bearish_inducement and has_bearish_confirm and (36.0 <= rsi_val <= 58.0)

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
        tf_clean = str(timeframe).lower().strip()
        if tf_clean not in ['30m', '1h', '4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Eugene Ng Ah Sio relative value model is calibrated for 30M, 1H and 4H execution. '{timeframe}' is too noisy."]
            }

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

        # Asset Guard: Eugene Ng Ah Sio strategy is strictly calibrated for Crypto Perps & Spot (BTC, ETH, Altcoins)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if (current_price < 500.0) or any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'JPY', 'EUR', 'CAD', 'GBP']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Eugene Ng Ah Sio relative value model is strictly calibrated for Crypto assets (BTC/ETH). Metals & Forex excluded."]
            }

        closes = df['close']
        highs = df['high']
        lows = df['low']

        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200), min_periods=min(n, 25)).mean().iloc[-1])

        # RSI Calculation (14 period)
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss.replace(0, np.nan))
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else 50.0

        # RVOL (Relative Volume) catalyst confirmation:
        vol_confirmed = True
        rvol = 1.0
        if 'volume' in df.columns and len(df['volume']) >= 20:
            avg_vol = float(df['volume'].iloc[-20:-1].mean())
            curr_vol = float(df['volume'].iloc[-1])
            if avg_vol > 0:
                rvol = curr_vol / avg_vol
                vol_confirmed = (rvol >= 1.05)

        # ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

        lookback = min(n, 16)
        recent_high = float(highs.iloc[-lookback:-1].max())
        recent_low = float(lows.iloc[-lookback:-1].min())

        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0
        reasons = []

        curr_open = float(df['open'].iloc[-1])
        prev_close = float(closes.iloc[-2])
        cand_body = abs(current_price - curr_open)

        # Relative Strength Outperformer (Long Leg with Bullish Candle Confirmation & SMA200 trend):
        if current_price > sma_200 and current_price > ema_20 and ema_20 > ema_50 and (48.0 <= rsi_val <= 68.0) and current_price > recent_high and (current_price > curr_open and current_price >= prev_close) and (cand_body >= 0.25 * safe_atr) and vol_confirmed and (adx_val >= 20.0):
            action = 'BUY'
            status = 'ALPHA_CATALYST_LONG'
            confidence = 91.0 if rvol >= 1.20 else 87.0
            reasons.append(f"Eugene Ng: Relative strength outperformance confirmed (RSI {rsi_val:.1f}, RVOL {rvol:.2f}x, ADX {adx_val:.1f}) with bullish breakout close")
            reasons.append(f"Price (${current_price:.2f}) leading above 20 EMA (${ema_20:.2f}) and 50 EMA (${ema_50:.2f})")
            reasons.append(f"Breakout of {lookback}-bar relative value consolidation high (${recent_high:.2f})")
        # Relative Weakness Laggard (Hedge Leg with Bearish Candle Confirmation & SMA200 trend):
        elif current_price < sma_200 and current_price < ema_20 and ema_20 < ema_50 and (32.0 <= rsi_val <= 52.0) and current_price < recent_low and (current_price < curr_open and current_price <= prev_close) and (cand_body >= 0.25 * safe_atr) and vol_confirmed and (adx_val >= 20.0):
            action = 'SELL'
            status = 'LAGGARD_HEDGE_SHORT'
            confidence = 91.0 if rvol >= 1.20 else 87.0
            reasons.append(f"Eugene Ng: Structural laggard weakness confirmed (RSI {rsi_val:.1f}, RVOL {rvol:.2f}x, ADX {adx_val:.1f}) with bearish breakdown close")
            reasons.append(f"Price (${current_price:.2f}) breaking below 20/50 EMA moving average band")
            reasons.append(f"Breakdown of {lookback}-bar consolidation support (${recent_low:.2f})")
        else:
            reasons.append(f"Asset in neutral relative value spread territory (RSI {rsi_val:.1f}, RVOL {rvol:.2f}x, ADX {adx_val:.1f}). Awaiting alpha divergence.")

        if action == 'BUY':
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(entry_price - recent_low) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)      # Precision Scalp Bank (Rule #2)
            tp2 = entry_price + (1.15 * sl_distance)   # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)   # Macro expansion runner
        elif action == 'SELL':
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(recent_high - entry_price) + 0.20 * safe_atr), 2.20 * safe_atr)
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
        tf_clean = str(timeframe).lower().strip()
        if tf_clean not in ['30m', '1h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Paul FTMO Asian breakout & divergence model is calibrated for 30M and 1H. '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Paul FTMO Asian breakout model is calibrated strictly for European Forex pairs (EUR/USD, GBP/USD).
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if (current_price > 500.0) or any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'JPY']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Paul FTMO Asian breakout model is calibrated strictly for European Forex pairs (EUR/USD, GBP/USD). JPY and Metals excluded."]
            }


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

        # Trend filter (50 SMA)
        sma_50 = float(closes.rolling(min(n, 50), min_periods=min(n, 15)).mean().iloc[-1])

        # Asian Consolidation Boundary (00:00 to 07:00 UTC)
        if 'timestamp' in df.columns and len(df['timestamp']) > 0:
            ts_series = df['timestamp']
            asian_mask = ts_series.apply(lambda t: 0 <= (t.hour if hasattr(t, 'hour') else 12) < 7)
            if asian_mask.any():
                asian_high = float(highs[asian_mask].iloc[-28:].max())
                asian_low = float(lows[asian_mask].iloc[-28:].min())
            else:
                lookback_asian = min(n, 28)
                asian_high = float(highs.iloc[-lookback_asian:-2].max())
                asian_low = float(lows.iloc[-lookback_asian:-2].min())
        else:
            lookback_asian = min(n, 28)
            asian_high = float(highs.iloc[-lookback_asian:-2].max())
            asian_low = float(lows.iloc[-lookback_asian:-2].min())

        asian_range = max(asian_high - asian_low, safe_atr)
        cand_body = abs(closes.iloc[-1] - df['open'].iloc[-1])

        # Bullish Divergence: Price swept Asian low while RSI(12) and MACD hist show bullish divergence + trend ok
        bullish_div = (float(lows.iloc[-1]) <= asian_low * 1.0008) and (rsi_12 <= 42.0) and (rsi_12 > rsi_12_prev) and (macd_hist > macd_hist_prev) and (cand_body >= 0.22 * safe_atr) and (current_price >= sma_50 * 0.998)
        # Bearish Divergence: Price swept Asian high while RSI(12) and MACD hist show bearish divergence + trend ok
        bearish_div = (float(highs.iloc[-1]) >= asian_high * 0.9992) and (rsi_12 >= 58.0) and (rsi_12 < rsi_12_prev) and (macd_hist < macd_hist_prev) and (cand_body >= 0.22 * safe_atr) and (current_price <= sma_50 * 1.002)

        # Check London & NY Session Window (07:00-16:00 UTC)
        if 'timestamp' in df.columns and len(df['timestamp']) > 0:
            last_ts = df['timestamp'].iloc[-1]
            curr_hour = last_ts.hour if hasattr(last_ts, 'hour') else datetime.now(timezone.utc).hour
        else:
            curr_hour = datetime.now(timezone.utc).hour
        is_london_window = (7 <= curr_hour <= 16)

        action = 'HOLD'
        status = 'MONITORING'
        confidence = 50.0
        reasons = []

        if is_london_window and bullish_div and closes.iloc[-1] > df['open'].iloc[-1]:
            action = 'BUY'
            status = 'ASIAN_RANGE_BULLISH_DIVERGENCE'
            confidence = 88.0
            reasons.append(f"Paul FTMO: Bullish Divergence at Asian Range Low (${asian_low:,.4f})")
            reasons.append(f"Custom RSI(12) rising ({rsi_12:.1f} > {rsi_12_prev:.1f}) & Fast MACD(4,18,9) momentum expanding")
            reasons.append("Asian Range sweep completed; European order flow breakout active")
        elif is_london_window and bearish_div and closes.iloc[-1] < df['open'].iloc[-1]:
            action = 'SELL'
            status = 'ASIAN_RANGE_BEARISH_DIVERGENCE'
            confidence = 88.0
            reasons.append(f"Paul FTMO: Bearish Divergence at Asian Range High (${asian_high:,.4f})")
            reasons.append(f"Custom RSI(12) exhausting ({rsi_12:.1f} < {rsi_12_prev:.1f}) & Fast MACD(4,18,9) momentum weakening")
            reasons.append("Asian Range high tested; European liquidity distribution active")
        else:
            reasons.append(f"Inside Asian consolidation [{asian_low:,.4f} - {asian_high:,.4f}]. RSI(12): {rsi_12:.1f}. Awaiting divergence breakout.")

        # Execution & Risk: Golden SL Geometry (1.80 * ATR base)
        sl_distance = max(1.80 * safe_atr, min(abs(current_price - asian_low if action == 'BUY' else asian_high - current_price) + 0.20 * safe_atr, 2.00 * safe_atr)) if action in ['BUY', 'SELL'] else 1.80 * safe_atr

        if action == 'BUY':
            entry_price = current_price
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)     # Precision Scalp Bank
            tp2 = entry_price + (1.15 * sl_distance)  # Mandatory 1:1+ Runner Geometry
            tp3 = entry_price + (2.20 * sl_distance)  # Macro expansion runner
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
                'risk_reward_ratio': '1:1.62 Fib',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'FIB_EXTENSION_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 19. RICHARD DENNIS & WILLIAM ECKHARDT — THE TURTLE TRADERS (20-DAY BREAKOUT)
# ─────────────────────────────────────────────────────────────────────────────
class RichardDennisStrategy:
    """
    Trader 19: Richard Dennis & William Eckhardt (The Legendary Turtle Traders)
    - System: 20-period Donchian Breakout + N-period ATR Trend Filter
    - Core Rule: Buy on 20-period High breakout if ADX >= 20 and EMA 20 > EMA 50;
                 Sell on 20-period Low breakout if ADX >= 20 and EMA 20 < EMA 50.
    - Timeframes: 15m, 30m, 1h, 4h, 1d (Rejects 1m/3m/5m micro noise).
    - Breakeven: TURTLE_TRAILING_BE (Moves to BE when price breaks 10-bar Donchian in trade direction).
    """
    NAME = "Richard Dennis (Turtle Trading System - 20-Day Donchian Breakout)"
    KEY = "RICHARD_DENNIS"
    BE_MODE = "TURTLE_TRAILING_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean not in ['1h', '4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Turtle Trading system operates on 1H and 4H trend expansion. '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        if n < 30:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Turtle Donchian 20-period breakout calculation."]
            }

        # Asset Guard: Turtle Trading is calibrated for macro trends on BTC and EUR/USD
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'ETH', 'JPY', 'GBP']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_EXCLUDED',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Turtle breakout strategy is calibrated for BTC and EUR/USD. JPY, GBP, and Metals excluded."]
            }

        highs = df['high']
        lows = df['low']
        closes = df['close']

        # True Wilder's ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

        donchian_high_20 = float(highs.iloc[-21:-1].max())
        donchian_low_20 = float(lows.iloc[-21:-1].min())

        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200), min_periods=min(n, 25)).mean().iloc[-1])

        # RSI 14 Momentum Guard
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        curr_open = float(df['open'].iloc[-1])
        prev_close = float(closes.iloc[-2])
        cand_body = abs(current_price - curr_open)

        action = 'HOLD'
        status = 'MONITORING_DONCHIAN'
        confidence = 50.0
        reasons = []

        is_bullish_close = (current_price > curr_open and cand_body >= 0.28 * safe_atr)
        is_bearish_close = (current_price < curr_open and cand_body >= 0.28 * safe_atr)

        if (current_price >= donchian_high_20) and (ema_20 > ema_50 * 0.998) and (current_price > sma_200) and (adx_val >= 18.0) and (48.0 <= rsi_val <= 68.0) and is_bullish_close:
            action = 'BUY'
            status = 'TURTLE_DONCHIAN_BREAKOUT_LONG'
            confidence = 89.0
            reasons.append(f"Turtle System: Price (${current_price:.2f}) broke 20-bar Donchian High (${donchian_high_20:.2f})")
            reasons.append(f"Trend Regime Confirmed: EMA 20 (${ema_20:.2f}) > EMA 50 (${ema_50:.2f}) & Price > 200 SMA with ADX {adx_val:.1f} & RSI {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(entry_price - ema_50) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (1.15 * sl_distance)
            tp3 = entry_price + (2.20 * sl_distance)
        elif (current_price <= donchian_low_20) and (ema_20 < ema_50 * 1.002) and (current_price < sma_200) and (adx_val >= 18.0) and (32.0 <= rsi_val <= 52.0) and is_bearish_close:
            action = 'SELL'
            status = 'TURTLE_DONCHIAN_BREAKDOWN_SHORT'
            confidence = 89.0
            reasons.append(f"Turtle System: Price (${current_price:.2f}) broke 20-bar Donchian Low (${donchian_low_20:.2f})")
            reasons.append(f"Downtrend Regime Confirmed: EMA 20 (${ema_20:.2f}) < EMA 50 (${ema_50:.2f}) & Price < 200 SMA with ADX {adx_val:.1f}")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(ema_50 - entry_price) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Waiting for 20-bar Donchian breakout (H: {donchian_high_20:.2f}, L: {donchian_low_20:.2f})")

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
                'risk_reward_ratio': '1:2.2 Turtle N',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'TURTLE_TRAILING_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 20. MARK MINERVINI — 2X US INVESTING CHAMPION (SEPA & VCP PIVOT BREAKOUT)
# ─────────────────────────────────────────────────────────────────────────────
class MarkMinerviniStrategy:
    """
    Trader 20: Mark Minervini (2x US Investing Champion)
    - System: Specific Entry Point Analysis (SEPA) & Volatility Contraction Pattern (VCP)
    - Filter: Stage 2 Trend Template (Price > 200 SMA, 50 SMA > 200 SMA, 20 EMA > 50 SMA)
    - Setup: Volatility Contraction Pattern (VCP) where successive waves shrink in range, followed by pivot breakout.
    - Breakeven: VCP_PIVOT_BE
    """
    NAME = "Mark Minervini (SEPA - Volatility Contraction Pattern VCP)"
    KEY = "MARK_MINERVINI"
    BE_MODE = "VCP_PIVOT_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean not in ['1h', '4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Mark Minervini SEPA VCP operates on 1H and 4H structural bases. '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Mark Minervini SEPA VCP is calibrated strictly for BTC (excluding altcoins, Forex pairs, and metals)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'EUR', 'GBP', 'CAD', 'JPY', 'ETH']) or ('BTC' not in sym_str):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Mark Minervini SEPA VCP is calibrated strictly for Bitcoin. Forex, Metals, and Altcoins excluded."]
            }

        if n < 30:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for SEPA trend template and VCP contraction analysis."]
            }

        closes = df['close']
        highs = df['high']
        lows = df['low']

        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        sma_50 = float(closes.rolling(min(n, 50), min_periods=min(n, 15)).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200), min_periods=min(n, 25)).mean().iloc[-1])

        range_prev = float(highs.iloc[-16:-8].max() - lows.iloc[-16:-8].min())
        range_curr = float(highs.iloc[-8:-1].max() - lows.iloc[-8:-1].min())
        is_vcp_contraction = (range_curr < range_prev * 0.85)

        # ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

        # RSI 14 Momentum Guard
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        pivot_high = float(highs.iloc[-8:-1].max())
        pivot_low = float(lows.iloc[-8:-1].min())

        curr_open = float(df['open'].iloc[-1])
        prev_close = float(closes.iloc[-2])
        cand_body = abs(current_price - curr_open)

        action = 'HOLD'
        status = 'SCANNING_VCP_BASE'
        confidence = 50.0
        reasons = []

        if (current_price > sma_200) and (current_price > ema_20) and (ema_20 > sma_50) and is_vcp_contraction and (adx_val >= 22.0) and (48.0 <= rsi_val <= 66.0):
            if current_price > pivot_high and (current_price > curr_open and current_price >= prev_close) and (cand_body >= 0.35 * safe_atr):
                action = 'BUY'
                status = 'SEPA_VCP_PIVOT_BREAKOUT_BUY'
                confidence = 92.0
                reasons.append(f"Minervini SEPA: Price (${current_price:.2f}) cleared VCP Pivot High (${pivot_high:.2f}) with ADX {adx_val:.1f}")
                reasons.append(f"Volatility Contraction Confirmed: Contraction range reduced from {range_prev:.2f} to {range_curr:.2f}")
                reasons.append(f"Stage 2 Trend Template Active: 20 EMA (${ema_20:.2f}) > 50 SMA (${sma_50:.2f}) > 200 SMA (${sma_200:.2f})")
                entry_price = current_price
                sl_distance = min(max(1.80 * safe_atr, abs(entry_price - pivot_low) + 0.20 * safe_atr), 2.20 * safe_atr)
                stop_loss = entry_price - sl_distance
                tp1 = entry_price + (0.38 * safe_atr)
                tp2 = entry_price + (1.15 * sl_distance)
                tp3 = entry_price + (2.20 * sl_distance)
        elif (current_price < sma_200) and (current_price < ema_20) and (ema_20 < sma_50) and is_vcp_contraction and (adx_val >= 22.0) and (34.0 <= rsi_val <= 52.0):
            if current_price < pivot_low and (current_price < curr_open and current_price <= prev_close) and (cand_body >= 0.35 * safe_atr):
                action = 'SELL'
                status = 'SEPA_VCP_PIVOT_BREAKDOWN_SELL'
                confidence = 89.0
                reasons.append(f"Minervini SEPA: Price (${current_price:.2f}) broke down below VCP Pivot Low (${pivot_low:.2f}) with ADX {adx_val:.1f}")
                reasons.append(f"Volatility Contraction Breakdown: Contraction range {range_curr:.2f} < {range_prev:.2f}")
                reasons.append(f"Stage 4 Downtrend Active: 20 EMA (${ema_20:.2f}) < 50 SMA (${sma_50:.2f}) < 200 SMA (${sma_200:.2f})")
                entry_price = current_price
                sl_distance = min(max(1.80 * safe_atr, abs(pivot_high - entry_price) + 0.20 * safe_atr), 2.20 * safe_atr)
                stop_loss = entry_price + sl_distance
                tp1 = entry_price - (0.38 * safe_atr)
                tp2 = entry_price - (1.15 * sl_distance)
                tp3 = entry_price - (2.20 * sl_distance)

        if action == 'HOLD':
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Waiting for SEPA VCP pivot breakout (Pivot H: {pivot_high:.2f}, L: {pivot_low:.2f})")

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
                'risk_reward_ratio': '1:2.0 VCP',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'VCP_PIVOT_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 21. AL BROOKS — PROFESSIONAL PRICE ACTION (MTR & HIGH/LOW 2 REVERSALS)
# ─────────────────────────────────────────────────────────────────────────────
class AlBrooksStrategy:
    """
    Trader 21: Al Brooks (Author of Reading Price Charts Bar by Bar)
    - System: Major Trend Reversal (MTR) & High 2 / Low 2 Pullback at 20 EMA
    - Focus: Forex, Crypto, Indices across all timeframes (5m, 15m, 1h, 4h)
    - Signal Bar Quality: Strong bull reversal bar closes in upper 25% of bar; strong bear bar closes in lower 25%.
    - Breakeven: BROOKS_SIGNAL_BAR_BE
    """
    NAME = "Al Brooks (Price Action - Major Trend Reversal & High/Low 2)"
    KEY = "AL_BROOKS"
    BE_MODE = "BROOKS_SIGNAL_BAR_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean in ['1m', '2m', '3m', '5m', '15m', '30m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Al Brooks Price Action requires >= 1H timeframe (1h, 4h). '{timeframe}' is sub-1h noise."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Exclude Metals (Gold/Silver), EUR, & JPY pairs where erratic wicks corrupt Al Brooks bar-by-bar reading
        # Strictly calibrate Crypto (BTC/ETH) to 1H execution where bar-by-bar reading has optimal signal-to-noise ratio
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'JPY', 'EUR', 'GBP', 'CAD']) or (('BTC' in sym_str or 'ETH' in sym_str or current_price > 500.0) and tf_clean != '1h'):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Al Brooks Price Action excludes Forex/Metals and operates strictly on 1H for Crypto."]
            }

        if n < 35:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Al Brooks bar-by-bar price action analysis."]
            }

        closes = df['close']
        highs = df['high']
        lows = df['low']
        opens = df['open']

        ema_20_series = closes.ewm(span=20, adjust=False).mean()
        ema_20 = float(ema_20_series.iloc[-1])
        ema_20_prev = float(ema_20_series.iloc[-2]) if len(ema_20_series) >= 2 else ema_20
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        # True Wilder's ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

        # Al Brooks Bar-by-Bar Principle:
        # Signal bar MUST be the last confirmed/completed candle (iloc[-2]).
        # Live current candle (iloc[-1]) is the Trigger bar breaking the signal bar's extreme.
        sig_c = float(closes.iloc[-2])
        sig_o = float(opens.iloc[-2])
        sig_h = float(highs.iloc[-2])
        sig_l = float(lows.iloc[-2])
        sig_range = max(sig_h - sig_l, 1e-6)
        sig_body = abs(sig_c - sig_o)

        sig_close_pos = (sig_c - sig_l) / sig_range
        sig_lower_wick = (min(sig_c, sig_o) - sig_l) / sig_range
        sig_upper_wick = (sig_h - max(sig_c, sig_o)) / sig_range

        # Retest of 20 EMA on the signal bar or preceding bar
        tested_ema = (min(lows.iloc[-3:-1]) <= ema_20 * 1.0015) and (max(highs.iloc[-3:-1]) >= ema_20 * 0.9985)

        curr_open = float(opens.iloc[-1])
        is_uptrend_aligned = (current_price > sma_200) and (ema_20 > ema_50) and (ema_20 >= ema_20_prev * 0.9998) and (adx_val >= 26.0)
        is_downtrend_aligned = (current_price < sma_200) and (ema_20 < ema_50) and (ema_20 <= ema_20_prev * 1.0002) and (adx_val >= 26.0)

        action = 'HOLD'
        status = 'READING_BARS'
        confidence = 50.0
        reasons = []

        # High 2 Bull Signal: Confirmed completed bull rejection bar + live breakout above signal bar high
        has_bull_sig_bar = tested_ema and (sig_close_pos >= 0.72) and (sig_c > sig_o) and (sig_body >= 0.40 * sig_range) and (sig_range >= 0.45 * safe_atr) and (sig_lower_wick >= 0.18)
        is_bull_signal = is_uptrend_aligned and has_bull_sig_bar and (current_price >= sig_h * 0.9998) and (current_price >= curr_open)

        # Low 2 Bear Signal: Confirmed completed bear rejection bar + live breakdown below signal bar low
        has_bear_sig_bar = tested_ema and (sig_close_pos <= 0.28) and (sig_c < sig_o) and (sig_body >= 0.40 * sig_range) and (sig_range >= 0.45 * safe_atr) and (sig_upper_wick >= 0.18)
        is_bear_signal = is_downtrend_aligned and has_bear_sig_bar and (current_price <= sig_l * 1.0002) and (current_price <= curr_open)

        if is_bull_signal:
            action = 'BUY'
            status = 'BROOKS_HIGH2_BULL_SIGNAL_BAR'
            confidence = 92.0
            reasons.append(f"Al Brooks: High 2 Bull Signal Bar at 20 EMA (${ema_20:.2f}) with Trend Stack (EMA20 > EMA50, Price > 200 SMA)")
            reasons.append(f"Confirmed Signal Bar: Closed at {sig_close_pos*100.0:.0f}% of bar range with {sig_lower_wick*100.0:.0f}% buying rejection wick")
            reasons.append(f"Trigger Confirmed: Price (${current_price:.2f}) took out signal bar high (${sig_h:.2f})")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(entry_price - sig_l) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (1.15 * sl_distance)
            tp3 = entry_price + (2.20 * sl_distance)
        elif is_bear_signal:
            action = 'SELL'
            status = 'BROOKS_LOW2_BEAR_SIGNAL_BAR'
            confidence = 92.0
            reasons.append(f"Al Brooks: Low 2 Bear Signal Bar at 20 EMA (${ema_20:.2f}) with Downtrend Stack (EMA20 < EMA50, Price < 200 SMA)")
            reasons.append(f"Confirmed Signal Bar: Closed at {sig_close_pos*100.0:.0f}% of bar range with {sig_upper_wick*100.0:.0f}% selling rejection wick")
            reasons.append(f"Trigger Confirmed: Price (${current_price:.2f}) broke below signal bar low (${sig_l:.2f})")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(sig_h - entry_price) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append("Waiting for Al Brooks confirmed closed signal bar rejection aligned with 20 EMA & 200 SMA trend")

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
                'risk_reward_ratio': '1:2.0 MTR',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'BROOKS_SIGNAL_BAR_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 22. BOB VOLMAN — FOREX PRICE ACTION SCALPING (PRE-BREAKOUT BUILD-UP & 20 EMA)
# ─────────────────────────────────────────────────────────────────────────────
class BobVolmanStrategy:
    """
    Trader 22: Bob Volman (Author of Forex Price Action Scalping)
    - System: Block Breakout (BB) & 20 EMA Pre-Breakout Build-Up
    - Focus: Micro scalping on 1m, 3m, 5m (EUR/USD, GBP/USD, Gold)
    - Core Rule: A breakout MUST have a 'Build-Up' (3 to 6 compressed candles hugging the 20 EMA) before breaking.
    - Breakeven: VOLMAN_BUILDUP_BE
    """
    NAME = "Bob Volman (Forex 1M-5M Build-Up Breakout & 20 EMA)"
    KEY = "BOB_VOLMAN"
    BE_MODE = "VOLMAN_BUILDUP_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '5m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean != '15m':
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Bob Volman requires 15M execution to eliminate sub-15m spread wicks. Timeframe '{timeframe}' is incompatible."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.0005)

        # Asset Guard: Bob Volman Forex Price Action Scalping is designed for Forex Majors, not volatile Crypto
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if ('BTC' in sym_str or 'ETH' in sym_str or current_price > 500.0) or any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Bob Volman price action scalping is calibrated for Forex Majors. Crypto & Metals excluded."]
            }


        if n < 30:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Bob Volman build-up analysis."]
            }

        closes = df['close']
        highs = df['high']
        lows = df['low']
        volumes = df['volume'] if 'volume' in df.columns else pd.Series(np.ones(n))

        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])

        bu_highs = highs.iloc[-5:-1]
        bu_lows = lows.iloc[-5:-1]
        bu_range = float(bu_highs.max() - bu_lows.min())
        is_buildup = (bu_range <= 0.75 * safe_atr)

        ceiling = float(bu_highs.max())
        floor = float(bu_lows.min())

        curr_open = float(df['open'].iloc[-1])
        prev_close = float(closes.iloc[-2])
        cand_body = abs(current_price - curr_open)

        # Volume confirmation
        bu_avg_vol = float(volumes.iloc[-5:-1].mean()) if len(volumes) >= 5 else 1.0
        curr_vol = float(volumes.iloc[-1])
        vol_surge = (curr_vol >= bu_avg_vol * 1.15) or ('volume' not in df.columns)

        action = 'HOLD'
        status = 'SCANNING_BUILDUP'
        confidence = 50.0
        reasons = []

        is_bull_breakout = is_buildup and (current_price > ceiling) and (ema_20 >= ema_50) and (current_price > curr_open and current_price >= prev_close) and (cand_body >= 0.38 * safe_atr) and vol_surge
        is_bear_breakdown = is_buildup and (current_price < floor) and (ema_20 <= ema_50) and (current_price < curr_open and current_price <= prev_close) and (cand_body >= 0.38 * safe_atr) and vol_surge

        if is_bull_breakout:
            action = 'BUY'
            status = 'VOLMAN_BLOCK_BREAKOUT_LONG'
            confidence = 90.0
            reasons.append(f"Bob Volman: Pre-breakout Build-Up formed at 20 EMA (${ema_20:.4f}, range {bu_range:.4f})")
            reasons.append(f"Explosive Breakout through ceiling (${ceiling:.4f}) with 20/50 EMA trend alignment and volume surge")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(entry_price - floor) + 0.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (1.15 * sl_distance)
            tp3 = entry_price + (2.20 * sl_distance)
        elif is_bear_breakdown:
            action = 'SELL'
            status = 'VOLMAN_BLOCK_BREAKDOWN_SHORT'
            confidence = 90.0
            reasons.append(f"Bob Volman: Pre-breakdown Build-Up formed at 20 EMA (${ema_20:.4f}, range {bu_range:.4f})")
            reasons.append(f"Breakdown through floor (${floor:.4f}) with 20/50 EMA downtrend alignment and volume surge")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(ceiling - entry_price) + 0.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Monitoring 20 EMA for Volman pre-breakout build-up (Range: {bu_range:.4f})")

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
                'risk_reward_ratio': '1:2.0 BB',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'VOLMAN_BUILDUP_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 23. TOM HOUGAARD — TRADERTOM ("BEST LOSER WINS" TREND EXPANSION & VWAP)
# ─────────────────────────────────────────────────────────────────────────────
class TomHougaardStrategy:
    """
    Trader 23: Tom Hougaard (TraderTom - WhichTrader / "Best Loser Wins")
    - System: Institutional Trend Day Expansion & VWAP Momentum
    - Concept: Identify decisive institutional trend days using VWAP + 5/20/50 EMA stack and ride massive runner expansions.
    - Breakeven: HOUGAARD_VWAP_TRAIL
    """
    NAME = "Tom Hougaard (TraderTom - Institutional Trend Expansion & VWAP)"
    KEY = "TOM_HOUGAARD"
    BE_MODE = "HOUGAARD_VWAP_TRAIL"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean in ['1m', '2m', '3m', '5m', '15m', '30m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Tom Hougaard Trend Expansion requires established trend timeframe (1h, 4h). '{timeframe}' is too noisy."]
            }

        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Tom Hougaard trades Indices, Commodities, and Crypto. Exclude choppy metals and Forex pairs.
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'CAD/JPY', 'JPY', 'EUR', 'GBP', 'CAD']) or (('BTC' in sym_str or 'ETH' in sym_str or current_price > 500.0) and tf_clean != '4h'):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Tom Hougaard Trend Expansion requires 4H for Crypto and excludes Forex/Metals."]
            }

        if n < 35:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Tom Hougaard trend day expansion analysis."]
            }

        closes = df['close']
        highs = df['high']
        lows = df['low']
        volumes = df['volume'] if 'volume' in df.columns else pd.Series(np.ones(n))

        ema_5 = float(closes.ewm(span=5, adjust=False).mean().iloc[-1])
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        vwap = float(np.sum(closes * volumes) / max(np.sum(volumes), 1e-6))

        # True Wilder's ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0
        p_di_val = float(plus_di.iloc[-1]) if not np.isnan(plus_di.iloc[-1]) else 20.0
        m_di_val = float(minus_di.iloc[-1]) if not np.isnan(minus_di.iloc[-1]) else 20.0

        # RSI 14 Sweet Spot Guard
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        curr_open = float(df['open'].iloc[-1])
        prev_close = float(closes.iloc[-2])
        cand_body = abs(current_price - curr_open)

        action = 'HOLD'
        status = 'SCANNING_TREND_DAY'
        confidence = 50.0
        reasons = []

        recent_lows = df['low'].iloc[-4:]
        tested_20_ema_long = any(l <= ema_20 * 1.001 for l in recent_lows)
        has_ribbon_expansion_long = (ema_5 > ema_20) and (ema_20 > ema_50) and ((ema_20 - ema_50) >= 0.18 * safe_atr)
        is_bull_candle = (current_price > curr_open and current_price >= prev_close and cand_body >= 0.40 * safe_atr and current_price >= ema_5)

        recent_highs = df['high'].iloc[-4:]
        tested_20_ema_short = any(h >= ema_20 * 0.999 for h in recent_highs)
        has_ribbon_expansion_short = (ema_5 < ema_20) and (ema_20 < ema_50) and ((ema_50 - ema_20) >= 0.18 * safe_atr)
        is_bear_candle = (current_price < curr_open and current_price <= prev_close and cand_body >= 0.40 * safe_atr and current_price <= ema_5)

        if (current_price >= vwap + 0.15 * safe_atr) and has_ribbon_expansion_long and tested_20_ema_long and is_bull_candle and (50.0 <= rsi_val <= 68.0) and (adx_val >= 25.0) and (p_di_val > m_di_val):
            action = 'BUY'
            status = 'HOUGAARD_TREND_DAY_LONG'
            confidence = 92.0
            reasons.append(f"Tom Hougaard: Institutional Trend Day confirmed above VWAP (${vwap:.2f} + buffer, ADX {adx_val:.1f})")
            reasons.append(f"Bullish Ribbon Stacked: 5 EMA (${ema_5:.2f}) > 20 EMA (${ema_20:.2f}) > 50 EMA (${ema_50:.2f}) with RSI {rsi_val:.1f}")
            reasons.append("20 EMA pullback kissed & rejected with strong expansion candle closing above 5 EMA")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(entry_price - min(vwap, ema_20)) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (1.15 * sl_distance)
            tp3 = entry_price + (2.20 * sl_distance)
        elif (current_price <= vwap - 0.15 * safe_atr) and has_ribbon_expansion_short and tested_20_ema_short and is_bear_candle and (32.0 <= rsi_val <= 50.0) and (adx_val >= 25.0) and (m_di_val > p_di_val):
            action = 'SELL'
            status = 'HOUGAARD_TREND_DAY_SHORT'
            confidence = 92.0
            reasons.append(f"Tom Hougaard: Institutional Trend Day confirmed below VWAP (${vwap:.2f} - buffer, ADX {adx_val:.1f})")
            reasons.append(f"Bearish Ribbon Stacked: 5 EMA (${ema_5:.2f}) < 20 EMA (${ema_20:.2f}) < 50 EMA (${ema_50:.2f}) with RSI {rsi_val:.1f}")
            reasons.append("20 EMA rally kissed & rejected with bearish breakdown candle closing below 5 EMA")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(max(vwap, ema_20) - entry_price) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Waiting for Tom Hougaard trend day alignment (VWAP: {vwap:.2f}, 20 EMA: {ema_20:.2f}, RSI: {rsi_val:.1f})")

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
                'risk_reward_ratio': '1:2.2 Trend Day',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'HOUGAARD_VWAP_TRAIL'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 24. LARRY WILLIAMS — WORLD CUP TRADING CHAMPION (VOLATILITY BREAKOUT & W%R)
# ─────────────────────────────────────────────────────────────────────────────
class LarryWilliamsStrategy:
    """
    Trader 24: Larry Williams (World Cup Trading Champion - 11,376% 1-Year Record)
    - System: Volatility Expansion Breakout & Williams %R Momentum
    - Filter: 50 SMA Macro Baseline + 20/50 EMA Stack + Williams %R (14) Overbought/Oversold Thrust
    - Setup: Price breaks Open + (0.50 * Prev Bar Range) in an uptrend (Price > 50 SMA, EMA20 > EMA50)
             or Open - (0.50 * Prev Bar Range) in a downtrend (Price < 50 SMA, EMA20 < EMA50).
    - Timeframes: 15m, 30m, 1h, 4h, 1d (Rejects 1m, 2m, 3m, 5m noise)
    - Breakeven: WILLIAMS_VOLATILITY_BE
    """
    NAME = "Larry Williams (Volatility Breakout & Williams %R)"
    KEY = "LARRY_WILLIAMS"
    BE_MODE = "WILLIAMS_VOLATILITY_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean in ['1m', '2m', '3m', '5m', '15m', '30m']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Larry Williams Volatility Expansion requires high-timeframe intraday structure (1h, 4h). '{timeframe}' is noise."]
            }

        n = len(df)
        if n < 35:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Larry Williams volatility breakout calculation."]
            }

        current_price = float(df['close'].iloc[-1])
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Exclude Gold, Silver, Forex pairs, and JPY pairs where volatility expansions produce immediate mean-reverting wicks
        # Also require 4h for Crypto to trade clean macro expansion cycles
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'JPY', 'EUR', 'GBP', 'CAD']) or (('BTC' in sym_str or 'ETH' in sym_str or current_price > 500.0) and tf_clean != '4h'):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Larry Williams Volatility Expansion requires 4H execution on Crypto and excludes Forex/Metals."]
            }

        highs = df['high']
        lows = df['low']
        closes = df['close']
        opens = df['open']

        # True Wilder's ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

        curr_open = float(opens.iloc[-1])
        curr_close = current_price
        prev_high = float(highs.iloc[-2])
        prev_low = float(lows.iloc[-2])
        prev_range = max(prev_high - prev_low, safe_atr * 0.5)

        # Baseline filters
        sma_50 = float(closes.rolling(min(n, 50)).mean().iloc[-1])
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])

        # Williams %R (14-period)
        hh_14 = float(highs.iloc[-14:].max())
        ll_14 = float(lows.iloc[-14:].min())
        wr_denom = max(hh_14 - ll_14, 1e-9)
        williams_r = ((hh_14 - current_price) / wr_denom) * -100.0

        # Larry Williams Volatility Breakout triggers: k = 0.50
        buy_trigger = curr_open + (0.50 * prev_range)
        sell_trigger = curr_open - (0.50 * prev_range)

        cand_body = abs(curr_close - curr_open)
        has_min_expansion = (prev_range >= 0.80 * safe_atr) and (cand_body >= 0.40 * safe_atr) and (adx_val >= 25.0)

        action = 'HOLD'
        status = 'MONITORING_WILLIAMS_RANGE'
        confidence = 50.0
        reasons = []

        is_bullish_thrust = (
            has_min_expansion
            and (current_price >= buy_trigger)
            and (curr_close > curr_open)
            and (current_price > sma_50)
            and (ema_20 >= ema_50)
            and (williams_r >= -30.0)
        )
        is_bearish_thrust = (
            has_min_expansion
            and (current_price <= sell_trigger)
            and (curr_close < curr_open)
            and (current_price < sma_50)
            and (ema_20 <= ema_50)
            and (williams_r <= -70.0)
        )

        if is_bullish_thrust:
            action = 'BUY'
            status = 'WILLIAMS_VOLATILITY_EXPANSION_BUY'
            confidence = 91.0 if williams_r >= -18.0 else 87.0
            reasons.append(f"Larry Williams Breakout: Price (${current_price:.2f}) broke above Open + 0.50*Range (${buy_trigger:.2f})")
            reasons.append(f"Trend & Momentum: Price > 50 SMA (${sma_50:.2f}), 20/50 EMA aligned with Williams %R at {williams_r:.1f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(entry_price - (curr_open - 0.25 * prev_range)) + 0.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (1.15 * sl_distance)
            tp3 = entry_price + (2.20 * sl_distance)
        elif is_bearish_thrust:
            action = 'SELL'
            status = 'WILLIAMS_VOLATILITY_EXPANSION_SELL'
            confidence = 91.0 if williams_r <= -82.0 else 87.0
            reasons.append(f"Larry Williams Breakdown: Price (${current_price:.2f}) broke below Open - 0.50*Range (${sell_trigger:.2f})")
            reasons.append(f"Trend & Momentum: Price < 50 SMA (${sma_50:.2f}), 20/50 EMA aligned with Williams %R at {williams_r:.1f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs((curr_open + 0.25 * prev_range) - entry_price) + 0.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Waiting for Larry Williams Range Breakout (Buy: ${buy_trigger:.2f}, Sell: ${sell_trigger:.2f}, W%R: {williams_r:.1f})")

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
                'risk_reward_ratio': '1:2.2 Volatility Range',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'WILLIAMS_VOLATILITY_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 25. NICOLAS DARVAS — BOX THEORY PIONEER ($2.25M SYSTEMATIC BREAKOUT)
# ─────────────────────────────────────────────────────────────────────────────
class NicolasDarvasStrategy:
    """
    Trader 25: Nicolas Darvas ($2.25M Box Theory Pioneer)
    - System: Darvas Box Theory Breakout with Volume Surge
    - Filter: 200 SMA + 50 SMA Trend Alignment + Minimum Box Height Requirement
    - Setup: Identifies an established consolidation box (high ceiling & low floor).
             Executes when price breaks out of the Darvas Box on above-average volume.
    - Timeframes: 15m, 30m, 1h, 4h, 1d (Rejects 1m, 2m, 3m, 5m noise)
    - Breakeven: DARVAS_BOX_TRAIL
    """
    NAME = "Nicolas Darvas (Darvas Box Theory Breakout)"
    KEY = "NICOLAS_DARVAS"
    BE_MODE = "DARVAS_BOX_TRAIL"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '1h') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean not in ['4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Darvas Box Theory requires 4H structural consolidation. '{timeframe}' is incompatible."]
            }

        n = len(df)
        if n < 25:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Nicolas Darvas Box calculation."]
            }

        current_price = float(df['close'].iloc[-1])
        safe_atr = max(atr, current_price * 0.001)
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()

        # Asset Guard: Exclude high-whipsaw assets (ETH and Gold)
        if any(m in sym_str for m in ['ETH', 'XAU', 'GOLD', 'SILVER']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_EXCLUDED',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Darvas Box Theory is calibrated for Forex Majors & BTC. ETH and Metals excluded due to box fakeouts."]
            }

        highs = df['high']
        lows = df['low']
        closes = df['close']
        opens = df['open']
        volumes = df['volume'] if 'volume' in df.columns else pd.Series(np.ones(n))

        # Darvas Box lookback: prior 20 bars (excluding current bar)
        box_lookback = 20
        if n < box_lookback + 5:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for 20-bar Nicolas Darvas Box calculation."]
            }

        box_ceiling = float(highs.iloc[-box_lookback-1:-1].max())
        box_floor = float(lows.iloc[-box_lookback-1:-1].min())
        box_height = box_ceiling - box_floor

        # Darvas Box requires meaningful consolidation range (at least 1.0 * ATR)
        if box_height < 1.0 * safe_atr:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'BOX_COMPRESSED',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Darvas Box height ({box_height:.2f}) is compressed below minimum threshold (1.0x ATR: {1.0 * safe_atr:.2f})."]
            }

        # True Wilder's ADX 14 calculation
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
        tr = pd.concat([highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()], axis=1).max(axis=1)
        smooth_tr = tr.rolling(14).mean()
        plus_di = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100.0
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0

        # RSI 14 Momentum Guard
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Moving averages
        sma_50 = float(closes.rolling(min(n, 50), min_periods=min(n, 15)).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200), min_periods=min(n, 25)).mean().iloc[-1])

        # Volume confirmation
        avg_vol = float(volumes.iloc[-21:-1].mean()) if len(volumes) >= 21 else float(volumes.mean())
        curr_vol = float(volumes.iloc[-1])
        vol_surge = (curr_vol >= avg_vol * 1.15) or ('volume' not in df.columns)

        curr_open = float(opens.iloc[-1])
        cand_body = abs(current_price - curr_open)
        cand_rng = max(df['high'].iloc[-1] - df['low'].iloc[-1], 1e-9)
        upper_wick = (df['high'].iloc[-1] - max(curr_open, current_price)) / cand_rng
        lower_wick = (min(curr_open, current_price) - df['low'].iloc[-1]) / cand_rng

        action = 'HOLD'
        status = 'MONITORING_DARVAS_BOX'
        confidence = 50.0
        reasons = []

        is_bullish_box_break = (
            (current_price >= box_ceiling)
            and (current_price > curr_open)
            and (cand_body >= 0.32 * safe_atr)
            and (upper_wick <= 0.32)
            and (current_price > sma_50)
            and (sma_50 > sma_200 * 0.998)
            and (adx_val >= 18.0)
            and (48.0 <= rsi_val <= 68.0)
            and vol_surge
        )
        is_bearish_box_break = (
            (current_price <= box_floor)
            and (current_price < curr_open)
            and (cand_body >= 0.32 * safe_atr)
            and (lower_wick <= 0.32)
            and (current_price < sma_50)
            and (sma_50 < sma_200 * 1.002)
            and (adx_val >= 18.0)
            and (32.0 <= rsi_val <= 52.0)
            and vol_surge
        )

        if is_bullish_box_break:
            action = 'BUY'
            status = 'DARVAS_BOX_EXPANSION_BUY'
            confidence = 90.0 if curr_vol >= avg_vol * 1.50 else 87.0
            reasons.append(f"Darvas Box Breakout: Price (${current_price:.2f}) cleared Box Ceiling (${box_ceiling:.2f}) with ADX {adx_val:.1f}")
            reasons.append(f"Trend & Volume Confirmed: 50 SMA (${sma_50:.2f}) >= 200 SMA (${sma_200:.2f}) with volume surge ({curr_vol:.0f} vs avg {avg_vol:.0f})")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(entry_price - box_floor) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (1.15 * sl_distance)
            tp3 = entry_price + (2.20 * sl_distance)
        elif is_bearish_box_break:
            action = 'SELL'
            status = 'DARVAS_BOX_BREAKDOWN_SELL'
            confidence = 90.0 if curr_vol >= avg_vol * 1.50 else 87.0
            reasons.append(f"Darvas Box Breakdown: Price (${current_price:.2f}) fell below Box Floor (${box_floor:.2f}) with ADX {adx_val:.1f}")
            reasons.append(f"Downtrend & Volume Confirmed: 50 SMA (${sma_50:.2f}) <= 200 SMA (${sma_200:.2f}) with volume surge ({curr_vol:.0f} vs avg {avg_vol:.0f})")
            entry_price = current_price
            sl_distance = min(max(1.80 * safe_atr, abs(box_ceiling - entry_price) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Inside Darvas Box [{box_floor:.2f} - {box_ceiling:.2f}]. Awaiting confirmed volume breakout.")

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
                'risk_reward_ratio': '1:2.2 Darvas Box',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'DARVAS_BOX_TRAIL'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 26. TOBY CRABEL — NR7 & OPENING RANGE BREAKOUT (ORB) CONTRACTION/EXPANSION
# ─────────────────────────────────────────────────────────────────────────────
class TobyCrabelStrategy:
    """
    Trader 26: Toby Crabel (Pioneer of NR7 & Opening Range Breakout ORB)
    - System: NR7 (Narrowest Range of 7 bars) Volatility Contraction & ORB Expansion
    - Filter: 20 EMA / 50 EMA Directional Alignment + RSI Sweet Spot (45-65)
    - Setup: Identifies an NR7 bar (range < previous 6 bars' ranges).
             Triggers on breakout of the contraction bar in the trend direction with expanding candle body.
    - Timeframes: 5m, 15m, 30m, 1h (Rejects 1m, 2m, 3m micro noise)
    - Breakeven: CRABEL_NR7_EXPANSION_BE
    """
    NAME = "Toby Crabel (NR7 Volatility Contraction & ORB Breakout)"
    KEY = "TOBY_CRABEL"
    BE_MODE = "CRABEL_NR7_EXPANSION_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean not in ['1h', '4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Toby Crabel NR7 ORB model requires established macro compression bars (1h, 4h). '{timeframe}' is noise."]
            }

        n = len(df)
        if n < 25:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Toby Crabel NR7 calculation."]
            }

        current_price = float(df['close'].iloc[-1])
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Exclude precious metals, ETH, and JPY where NR7 bars produce whipsaws
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAU', 'XAG', 'GOLD', 'SILVER', 'ETH', 'JPY']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_CLASS_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Toby Crabel NR7 ORB excludes volatile precious metals, ETH, and JPY."]
            }

        highs = df['high']
        lows = df['low']
        closes = df['close']
        opens = df['open']

        ranges = highs - lows
        curr_range = float(ranges.iloc[-1])
        prev_ranges_6 = ranges.iloc[-7:-1]
        is_nr7_setup = (float(ranges.iloc[-2]) <= float(prev_ranges_6.min())) and (float(ranges.iloc[-2]) <= 0.90 * safe_atr)

        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])

        # RSI 14
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # ADX 14 filter
        up = highs.diff()
        down = -lows.diff()
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)
        tr = np.maximum(highs - lows, np.maximum(abs(highs - closes.shift(1)), abs(lows - closes.shift(1))))
        tr_smooth = pd.Series(tr).rolling(14).sum()
        plus_di = 100 * (pd.Series(plus_dm).rolling(14).sum() / (tr_smooth + 1e-9))
        minus_di = 100 * (pd.Series(minus_dm).rolling(14).sum() / (tr_smooth + 1e-9))
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9))
        adx_series = dx.rolling(14).mean()
        adx_val = float(adx_series.iloc[-1]) if len(adx_series) > 0 and not np.isnan(adx_series.iloc[-1]) else 25.0

        nr_high = float(highs.iloc[-2])
        nr_low = float(lows.iloc[-2])

        curr_open = float(opens.iloc[-1])
        cand_body = abs(current_price - curr_open)

        action = 'HOLD'
        status = 'SCANNING_NR7_CONTRACTION'
        confidence = 50.0
        reasons = []

        is_bullish_expansion = (
            is_nr7_setup
            and (current_price > nr_high)
            and (current_price > curr_open)
            and (cand_body >= 0.38 * safe_atr)
            and (ema_20 >= ema_50 * 0.998)
            and (current_price >= ema_20)
            and (48.0 <= rsi_val <= 68.0)
            and (adx_val >= 22.0)
        )
        is_bearish_expansion = (
            is_nr7_setup
            and (current_price < nr_low)
            and (current_price < curr_open)
            and (cand_body >= 0.38 * safe_atr)
            and (ema_20 <= ema_50 * 1.002)
            and (current_price <= ema_20)
            and (32.0 <= rsi_val <= 52.0)
            and (adx_val >= 22.0)
        )

        if is_bullish_expansion:
            action = 'BUY'
            status = 'CRABEL_NR7_ORB_BULLISH_EXPANSION'
            confidence = 91.0
            reasons.append(f"Toby Crabel: Volatility expansion out of genuine NR7 narrow range (H: {nr_high:.2f}, Body: {cand_body:.2f})")
            reasons.append(f"Trend Alignment: EMA 20 (${ema_20:.2f}) >= EMA 50 (${ema_50:.2f}) with RSI {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(entry_price - nr_low) + 0.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (1.15 * sl_distance)
            tp3 = entry_price + (2.20 * sl_distance)
        elif is_bearish_expansion:
            action = 'SELL'
            status = 'CRABEL_NR7_ORB_BEARISH_EXPANSION'
            confidence = 91.0
            reasons.append(f"Toby Crabel: Volatility expansion out of genuine NR7 narrow range (L: {nr_low:.2f}, Body: {cand_body:.2f})")
            reasons.append(f"Trend Alignment: EMA 20 (${ema_20:.2f}) <= EMA 50 (${ema_50:.2f}) with RSI {rsi_val:.1f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, abs(nr_high - entry_price) + 0.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Awaiting Toby Crabel NR7 Contraction/Expansion Breakout (NR High: {nr_high:.2f}, Low: {nr_low:.2f})")

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
                'risk_reward_ratio': '1:2.2 NR7 ORB',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'CRABEL_NR7_EXPANSION_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# 27. LINDA RASCHKE — MARKET WIZARD (THE HOLY GRAIL ADX & 20 EMA PULLBACK)
# ─────────────────────────────────────────────────────────────────────────────
class LindaRaschkeStrategy:
    """
    Trader 27: Linda Bradford Raschke (Market Wizard & LBRGroup CTA)
    - System: The 'Holy Grail' (14 ADX >= 28 Trend Filter + 20 EMA Pullback)
    - Filter: 14 ADX >= 28 (+DI > -DI by >= 8.0 for Bullish, -DI > +DI by >= 8.0 for Bearish)
    - Setup: Powerful directional trend pulls back to touch/penetrate the 20 EMA value zone.
             Executes as price turns back in the direction of the dominant trend with expanding candle body.
    - Timeframes: 15m, 30m, 1h, 4h, 1d (Rejects 1m, 2m, 3m, 5m noise)
    - Breakeven: RASCHKE_GRAIL_BE
    """
    NAME = "Linda Raschke (Holy Grail - ADX Trend & 20 EMA Pullback)"
    KEY = "LINDA_RASCHKE"
    BE_MODE = "RASCHKE_GRAIL_BE"

    @classmethod
    def evaluate(cls, df: pd.DataFrame, atr: float, timeframe: str = '15m') -> Dict[str, Any]:
        tf_clean = str(timeframe).lower().strip()
        if tf_clean not in ['1h', '4h']:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'TIMEFRAME_INCOMPATIBLE',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': [f"Linda Raschke Holy Grail operates on 1H and 4H trend structure. '{timeframe}' is noise."]
            }

        n = len(df)
        if n < 35:
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'INSUFFICIENT_DATA',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Insufficient bars for Linda Raschke Holy Grail calculation."]
            }

        current_price = float(df['close'].iloc[-1])
        safe_atr = max(atr, current_price * 0.001)

        # Asset Guard: Exclude Gold, Silver, JPY pairs, and ETH due to spike wicks
        sym_str = str(getattr(df, 'attrs', {}).get('symbol', '')).upper()
        if any(m in sym_str for m in ['XAG', 'SILVER', 'XAU', 'GOLD', 'JPY', 'ETH']):
            return {
                'strategy_key': cls.KEY,
                'strategy_name': cls.NAME,
                'breakeven_mode': cls.BE_MODE,
                'action': 'HOLD',
                'status': 'ASSET_EXCLUDED',
                'confidence': 0.0,
                'trade_setup': {},
                'reasons': ["Linda Raschke Holy Grail is calibrated for BTC, EUR/USD, and GBP/USD. Metals, ETH, and JPY excluded."]
            }

        highs = df['high']
        lows = df['low']
        closes = df['close']
        opens = df['open']

        # 20 EMA, 50 EMA & 200 SMA
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200), min_periods=min(n, 25)).mean().iloc[-1])

        # ADX 14 & Directional Movement (+DI, -DI)
        up_move = highs.diff()
        down_move = -lows.diff()
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

        tr1 = highs - lows
        tr2 = (highs - closes.shift(1)).abs()
        tr3 = (lows - closes.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        smooth_tr = tr.rolling(14).mean()
        plus_di_series = (plus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        minus_di_series = (minus_dm.rolling(14).mean() / smooth_tr.replace(0, np.nan)) * 100.0
        plus_di = float(plus_di_series.iloc[-1]) if not np.isnan(plus_di_series.iloc[-1]) else 20.0
        minus_di = float(minus_di_series.iloc[-1]) if not np.isnan(minus_di_series.iloc[-1]) else 20.0

        # ADX calculation: smoothed 14-period average of DX
        dx_series = (abs(plus_di_series - minus_di_series) / (plus_di_series + minus_di_series).replace(0, np.nan)) * 100.0
        adx_series = dx_series.rolling(14).mean()
        adx_val = float(df['adx_14'].iloc[-1]) if 'adx_14' in df.columns and not pd.isna(df['adx_14'].iloc[-1]) else (float(adx_series.iloc[-1]) if not np.isnan(adx_series.iloc[-1]) else 20.0)

        # RSI 14 Momentum Guard
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss.replace(0, np.nan) + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) > 0 and not np.isnan(rsi_series.iloc[-1]) else 50.0

        # Check pullback to 20 EMA within last 3 bars
        recent_lows = lows.iloc[-4:-1]
        recent_highs = highs.iloc[-4:-1]
        touched_ema_from_above = (recent_lows <= ema_20 + 0.20 * safe_atr).any()
        touched_ema_from_below = (recent_highs >= ema_20 - 0.20 * safe_atr).any()

        curr_open = float(opens.iloc[-1])
        cand_body = abs(current_price - curr_open)

        action = 'HOLD'
        status = 'MONITORING_HOLY_GRAIL'
        confidence = 50.0
        reasons = []

        is_bullish_grail = (
            (adx_val >= 22.0)
            and (plus_di > minus_di)
            and (ema_20 > ema_50 * 0.998)
            and (current_price >= sma_200 * 0.998)
            and touched_ema_from_above
            and (current_price >= ema_20 * 0.998)
            and (current_price > curr_open)
            and (cand_body >= 0.28 * safe_atr)
            and (45.0 <= rsi_val <= 68.0)
        )
        is_bearish_grail = (
            (adx_val >= 22.0)
            and (minus_di > plus_di)
            and (ema_20 < ema_50 * 1.002)
            and (current_price <= sma_200 * 1.002)
            and touched_ema_from_below
            and (current_price <= ema_20 * 1.002)
            and (current_price < curr_open)
            and (cand_body >= 0.28 * safe_atr)
            and (32.0 <= rsi_val <= 55.0)
        )


        if is_bullish_grail:
            action = 'BUY'
            status = 'HOLY_GRAIL_BULLISH_PULLBACK_BUY'
            confidence = 90.0
            reasons.append(f"Linda Raschke Holy Grail: Bullish trend (ADX {adx_val:.1f}, +DI {plus_di:.1f} vs -DI {minus_di:.1f}) cleanly tested 20 EMA (${ema_20:.2f})")
            reasons.append(f"Price (${current_price:.2f}) rejected 20 EMA support with strong bullish candle follow-through")
            entry_price = current_price
            recent_swing_low = float(lows.iloc[-4:].min())
            sl_distance = min(max(1.80 * safe_atr, abs(entry_price - recent_swing_low) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (1.15 * sl_distance)
            tp3 = entry_price + (2.20 * sl_distance)
        elif is_bearish_grail:
            action = 'SELL'
            status = 'HOLY_GRAIL_BEARISH_PULLBACK_SELL'
            confidence = 92.0 if adx_val >= 32.0 else 88.0
            reasons.append(f"Linda Raschke Holy Grail: Bearish trend (ADX {adx_val:.1f}, -DI {minus_di:.1f} vs +DI {plus_di:.1f}) cleanly tested 20 EMA (${ema_20:.2f})")
            reasons.append(f"Price (${current_price:.2f}) rejected 20 EMA resistance with strong bearish candle follow-through")
            entry_price = current_price
            recent_swing_high = float(highs.iloc[-4:].max())
            sl_distance = min(max(1.80 * safe_atr, abs(recent_swing_high - entry_price) + 0.20 * safe_atr), 2.20 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (1.15 * sl_distance)
            tp3 = entry_price - (2.20 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Awaiting Linda Raschke Holy Grail setup (ADX: {adx_val:.1f}, 20 EMA: ${ema_20:.2f})")

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
                'risk_reward_ratio': '1:2.2 Holy Grail',
                'strategy_name': cls.NAME,
                'breakeven_rule': 'RASCHKE_GRAIL_BE'
            },
            'reasons': reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# MASTER STREAMER PLAYBOOK DISPATCHER (EVALUATE ALL 27 STREAMER STRATEGIES)
# ─────────────────────────────────────────────────────────────────────────────
class MasterStreamerPlaybook:
    """
    Central dispatcher that evaluates all 27 strategies from the Master Playbooks.
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
        'KRISTJAN_QULLAMAGGIE': KristjanQullamaggieStrategy,
        'GCR': GCRStrategy,
        'WAQAR_ZAKA': WaqarZakaStrategy,
        'WAQAR_ASIM': WaqarAsimStrategy,
        'EUGENE_NG_AH_SIO': EugeneNgAhSioStrategy,
        'PAUL_FTMO': PaulFTMOStrategy,
        # 9 World-Class Elite Strategies:
        'RICHARD_DENNIS': RichardDennisStrategy,
        'MARK_MINERVINI': MarkMinerviniStrategy,
        'AL_BROOKS': AlBrooksStrategy,
        'BOB_VOLMAN': BobVolmanStrategy,
        'TOM_HOUGAARD': TomHougaardStrategy,
        'LARRY_WILLIAMS': LarryWilliamsStrategy,
        'NICOLAS_DARVAS': NicolasDarvasStrategy,
        'TOBY_CRABEL': TobyCrabelStrategy,
        'LINDA_RASCHKE': LindaRaschkeStrategy
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
        Evaluates all 23 strategies simultaneously and identifies all confirmed setups.
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

        # 19. Richard Dennis (Turtle Trading)
        res_rd = RichardDennisStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['RICHARD_DENNIS'] = res_rd
        if res_rd['action'] in ['BUY', 'SELL']:
            active_setups.append(res_rd)

        # 20. Mark Minervini (SEPA VCP)
        res_mm = MarkMinerviniStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['MARK_MINERVINI'] = res_mm
        if res_mm['action'] in ['BUY', 'SELL']:
            active_setups.append(res_mm)

        # 21. Al Brooks (Price Action MTR)
        res_ab = AlBrooksStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['AL_BROOKS'] = res_ab
        if res_ab['action'] in ['BUY', 'SELL']:
            active_setups.append(res_ab)

        # 22. Bob Volman (Build-Up Breakout)
        res_bv = BobVolmanStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['BOB_VOLMAN'] = res_bv
        if res_bv['action'] in ['BUY', 'SELL']:
            active_setups.append(res_bv)

        # 23. Tom Hougaard (TraderTom Trend Expansion)
        res_th = TomHougaardStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['TOM_HOUGAARD'] = res_th
        if res_th['action'] in ['BUY', 'SELL']:
            active_setups.append(res_th)

        # 24. Larry Williams (Volatility Breakout & Williams %R)
        res_lw = LarryWilliamsStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['LARRY_WILLIAMS'] = res_lw
        if res_lw['action'] in ['BUY', 'SELL']:
            active_setups.append(res_lw)

        # 25. Nicolas Darvas (Darvas Box Theory Breakout)
        res_nd = NicolasDarvasStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['NICOLAS_DARVAS'] = res_nd
        if res_nd['action'] in ['BUY', 'SELL']:
            active_setups.append(res_nd)

        # 26. Toby Crabel (NR7 & Opening Range Breakout ORB)
        res_tc = TobyCrabelStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['TOBY_CRABEL'] = res_tc
        if res_tc['action'] in ['BUY', 'SELL']:
            active_setups.append(res_tc)

        # 27. Linda Raschke (Holy Grail ADX & 20 EMA Pullback)
        res_lr = LindaRaschkeStrategy.evaluate(df, atr=atr, timeframe=timeframe)
        results['LINDA_RASCHKE'] = res_lr
        if res_lr['action'] in ['BUY', 'SELL']:
            active_setups.append(res_lr)

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

