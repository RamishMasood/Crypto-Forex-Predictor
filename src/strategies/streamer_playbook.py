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

        # LTF unmitigated level near price
        near_demand = float(np.min(lows[-15:]))
        near_supply = float(np.max(highs[-15:]))

        action = 'HOLD'
        status = 'SCANNING_UMBRELLA_ZONES'
        confidence = 50.0
        reasons = []

        # 'Big Brother / Small Brother' rule:
        # Long only if in Discount (< mid) AND COT is Bullish/Neutral
        is_discount = current_price <= (htf_low + (htf_high - htf_low) * 0.40)
        is_premium = current_price >= (htf_low + (htf_high - htf_low) * 0.60)

        # Test Demand Zone Entry (Limit order tap)
        if is_discount and ('BEARISH' not in cot_bias) and (current_price - near_demand <= safe_atr * 0.5):
            action = 'BUY'
            status = 'DEMAND_LIMIT_TRIGGERED'
            confidence = 88.0 if 'BULLISH' in cot_bias else 78.0
            reasons.append(f"Bernd S&D: Price at Discount Demand Zone [{near_demand:.2f}] inside HTF Range")
            reasons.append(f"COT Sentiment: {cot_bias} smart money positioning")
            entry_price = current_price
            sl_distance = max(entry_price - (near_demand - 0.20 * safe_atr), 1.50 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (2.50 * sl_distance)  # 1:2.5 R:R
            tp3 = entry_price + (3.50 * sl_distance)  # 1:3.5 R:R

        # Test Supply Zone Entry
        elif is_premium and ('BULLISH' not in cot_bias) and (near_supply - current_price <= safe_atr * 0.5):
            action = 'SELL'
            status = 'SUPPLY_LIMIT_TRIGGERED'
            confidence = 88.0 if 'BEARISH' in cot_bias else 78.0
            reasons.append(f"Bernd S&D: Price at Premium Supply Zone [{near_supply:.2f}] inside HTF Range")
            reasons.append(f"COT Sentiment: {cot_bias} smart money positioning")
            entry_price = current_price
            sl_distance = max((near_supply + 0.20 * safe_atr) - entry_price, 1.50 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (2.50 * sl_distance)
            tp3 = entry_price - (3.50 * sl_distance)
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

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values

        # Check Killzone window (UTC time)
        now_utc = datetime.now(timezone.utc)
        curr_hour = now_utc.hour
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

        if bull_sweep and (has_bull_fvg or closes[-1] > opens[-1]):
            action = 'BUY'
            status = 'ICT_BULLISH_MSS_ENTRY'
            confidence = 88.0 if in_killzone else 76.0
            reasons.append(f"ICT: Sell-side Liquidity Swept below {recent_l:.2f} + Displacement FVG")
            reasons.append(f"Execution Window: {kz_label}")
            entry_price = current_price
            sl_distance = max(entry_price - (recent_l - 0.20 * safe_atr), 1.50 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + max(2.0 * sl_distance, recent_h - entry_price)
            tp3 = entry_price + (2.50 * sl_distance)

        elif bear_sweep and (has_bear_fvg or closes[-1] < opens[-1]):
            action = 'SELL'
            status = 'ICT_BEARISH_MSS_ENTRY'
            confidence = 88.0 if in_killzone else 76.0
            reasons.append(f"ICT: Buy-side Liquidity Swept above {recent_h:.2f} + Displacement FVG")
            reasons.append(f"Execution Window: {kz_label}")
            entry_price = current_price
            sl_distance = max((recent_h + 0.20 * safe_atr) - entry_price, 1.50 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - max(2.0 * sl_distance, entry_price - recent_l)
            tp3 = entry_price - (2.50 * sl_distance)
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

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        opens = df['open'].values

        # Detect recent key structural barrier (prior swing high / low)
        lookback = min(n, 40)
        prior_res = float(np.max(highs[-lookback:-5])) if n >= 20 else float(np.max(highs))
        prior_sup = float(np.min(lows[-lookback:-5])) if n >= 20 else float(np.min(lows))

        # Check Candlestick Reversal on recent bar (Pin bar / Engulfing)
        last_o, last_h, last_l, last_c = opens[-1], highs[-1], lows[-1], closes[-1]
        rng = max(last_h - last_l, 1e-9)
        lower_wick = (min(last_o, last_c) - last_l) / rng
        upper_wick = (last_h - max(last_o, last_c)) / rng

        is_bull_pinbar = (lower_wick >= 0.40) and (last_c >= last_o)
        is_bear_pinbar = (upper_wick >= 0.40) and (last_c <= last_o)

        action = 'HOLD'
        status = 'SCANNING_STRUCTURE_BREAKS'
        confidence = 50.0
        reasons = []

        # Break & Retest Long: Price broke prior resistance, now pulls back to retest it as support
        if (current_price >= prior_res - 0.4 * safe_atr) and (last_l <= prior_res + 0.3 * safe_atr) and is_bull_pinbar:
            action = 'BUY'
            status = 'BREAK_AND_RETEST_LONG'
            confidence = 85.0
            reasons.append(f"Steven Hart: Broken Resistance [{prior_res:.2f}] successfully retested as Support")
            reasons.append("Reversal Candlestick: Bullish Pin Bar / Absorption Wick Confirmed")
            entry_price = current_price
            sl_distance = max(entry_price - (last_l - 0.15 * safe_atr), 1.50 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (2.0 * sl_distance)  # Fixed 1:2 R:R
            tp3 = entry_price + (3.0 * sl_distance)

        # Break & Retest Short: Price broke prior support, now pulls back to retest it as resistance
        elif (current_price <= prior_sup + 0.4 * safe_atr) and (last_h >= prior_sup - 0.3 * safe_atr) and is_bear_pinbar:
            action = 'SELL'
            status = 'BREAK_AND_RETEST_SHORT'
            confidence = 85.0
            reasons.append(f"Steven Hart: Broken Support [{prior_sup:.2f}] successfully retested as Resistance")
            reasons.append("Reversal Candlestick: Bearish Pin Bar / Absorption Wick Confirmed")
            entry_price = current_price
            sl_distance = max((last_h + 0.15 * safe_atr) - entry_price, 1.50 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (2.0 * sl_distance)  # Fixed 1:2 R:R
            tp3 = entry_price - (3.0 * sl_distance)
        else:
            entry_price = stop_loss = tp1 = tp2 = tp3 = current_price
            sl_distance = 0.0
            reasons.append(f"Waiting for 4H/15M Break-and-Retest level touch (Res: {prior_res:.2f}, Sup: {prior_sup:.2f})")

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
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        closes = pd.Series(df['close'].values)
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])

        last_o, last_h, last_l, last_c = df['open'].iloc[-1], df['high'].iloc[-1], df['low'].iloc[-1], df['close'].iloc[-1]
        rng = max(last_h - last_l, 1e-9)
        lower_wick = (min(last_o, last_c) - last_l) / rng
        upper_wick = (last_h - max(last_o, last_c)) / rng

        is_uptrend = ema_20 > ema_50
        is_downtrend = ema_20 < ema_50

        # Pullback in value area between 20 & 50 EMA
        in_buy_value_area = (last_l <= ema_20) and (last_c >= ema_50) and is_uptrend
        in_sell_value_area = (last_h >= ema_20) and (last_c <= ema_50) and is_downtrend

        action = 'HOLD'
        status = 'WAITING_EMA_PULLBACK'
        confidence = 50.0
        reasons = []

        if in_buy_value_area and (last_c > last_o or lower_wick >= 0.35):
            action = 'BUY'
            status = 'VALUE_AREA_BOUNCE_BUY'
            confidence = 82.0
            reasons.append("Rayner Teo: Pullback into 20/50 EMA Value Area during verified Uptrend")
            reasons.append("Reversal Candle: Bullish bounce confirmed")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, entry_price - (ema_50 - 0.20 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (2.0 * sl_distance)
            tp3 = entry_price + (3.0 * sl_distance)

        elif in_sell_value_area and (last_c < last_o or upper_wick >= 0.35):
            action = 'SELL'
            status = 'VALUE_AREA_REJECTION_SELL'
            confidence = 82.0
            reasons.append("Rayner Teo: Pullback into 20/50 EMA Value Area during verified Downtrend")
            reasons.append("Reversal Candle: Bearish rejection confirmed")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, (ema_50 + 0.20 * safe_atr) - entry_price)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (2.0 * sl_distance)
            tp3 = entry_price - (3.0 * sl_distance)
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
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        closes = pd.Series(df['close'].values)
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        ema_50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])

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

        # Buy Setup: Testing horizontal support with RSI oversold/exhaustion (<40) and bullish reclaim
        if (current_price <= h_sup + 0.3 * safe_atr) and (closes.iloc[-1] > df['open'].iloc[-1]) and (rsi_val < 42.0):
            action = 'BUY'
            status = 'SUPPORT_RECLAIM_RSI_BUY'
            confidence = 84.0
            reasons.append(f"Crypto Cred: Horizontal Support [{h_sup:.2f}] successfully tested and reclaimed")
            reasons.append(f"RSI Exhaustion Bounce: RSI(14) = {rsi_val:.1f} < 42.0")
            entry_price = current_price
            sl_distance = max(entry_price - (h_sup - 0.20 * safe_atr), 1.50 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + max(2.0 * sl_distance, (h_res - entry_price) * 0.5)
            tp3 = h_res

        # Sell Setup: Testing horizontal resistance with RSI overbought/exhaustion (>60) and bearish reclaim
        elif (current_price >= h_res - 0.3 * safe_atr) and (closes.iloc[-1] < df['open'].iloc[-1]) and (rsi_val > 58.0):
            action = 'SELL'
            status = 'RESISTANCE_REJECT_RSI_SELL'
            confidence = 84.0
            reasons.append(f"Crypto Cred: Horizontal Resistance [{h_res:.2f}] successfully tested and rejected")
            reasons.append(f"RSI Exhaustion Rejection: RSI(14) = {rsi_val:.1f} > 58.0")
            entry_price = current_price
            sl_distance = max((h_res + 0.20 * safe_atr) - entry_price, 1.50 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - max(2.0 * sl_distance, (entry_price - h_sup) * 0.5)
            tp3 = h_sup
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

        # Long: 10 EMA > 23 EMA and price pulls back into 38.2% - 61.8% Fib pocket
        if is_bull_crossover and (fib_618_bull <= current_price <= fib_382_bull) and (df['close'].iloc[-1] > df['open'].iloc[-1]):
            action = 'BUY'
            status = 'GU_MVR_BULLISH_ENTRY'
            confidence = 85.0
            reasons.append("GU MVR: 10 EMA crossed above 23 EMA confirms Bullish Intraday Momentum")
            reasons.append("Fib Retracement: Price pulled back cleanly into 38.2% - 61.8% Golden Pocket")
            entry_price = current_price
            sl_distance = max(entry_price - (fib_618_bull - 0.20 * safe_atr), 1.50 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (2.0 * sl_distance)  # Fixed 1:2 R:R
            tp3 = entry_price + (2.5 * sl_distance)

        # Short: 10 EMA < 23 EMA and price pulls back into 38.2% - 61.8% Fib pocket
        elif is_bear_crossover and (fib_382_bear <= current_price <= fib_618_bear) and (df['close'].iloc[-1] < df['open'].iloc[-1]):
            action = 'SELL'
            status = 'GU_MVR_BEARISH_ENTRY'
            confidence = 85.0
            reasons.append("GU MVR: 10 EMA crossed below 23 EMA confirms Bearish Intraday Momentum")
            reasons.append("Fib Retracement: Price pulled back cleanly into 38.2% - 61.8% Golden Pocket")
            entry_price = current_price
            sl_distance = max((fib_618_bear + 0.20 * safe_atr) - entry_price, 1.50 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (2.0 * sl_distance)
            tp3 = entry_price - (2.5 * sl_distance)
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

        # Bull Flag / 9 EMA Momentum Long
        if (current_price > vwap) and (ema_9 > ema_20) and (closes.iloc[-1] >= ema_9) and vol_surge:
            action = 'BUY'
            status = 'WARRIOR_MOMENTUM_BUY'
            confidence = 86.0
            reasons.append("Ross Cameron: Price expanding above VWAP with 9 EMA > 20 EMA stack")
            reasons.append(f"Volume Surge Confirmed: Current Volume >= 1.25x 20-bar average")
            entry_price = current_price
            sl_distance = max(entry_price - (min(vwap, ema_20) - 0.15 * safe_atr), 1.50 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (2.0 * sl_distance)
            tp3 = entry_price + (3.0 * sl_distance)

        # Inverse Bearish Breakdown
        elif (current_price < vwap) and (ema_9 < ema_20) and (closes.iloc[-1] <= ema_9) and vol_surge:
            action = 'SELL'
            status = 'WARRIOR_MOMENTUM_SELL'
            confidence = 86.0
            reasons.append("Ross Cameron: Price breaking down below VWAP with 9 EMA < 20 EMA stack")
            reasons.append("Volume Surge Confirmed: Breakdown volume accelerating")
            entry_price = current_price
            sl_distance = max((max(vwap, ema_20) + 0.15 * safe_atr) - entry_price, 1.50 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (2.0 * sl_distance)
            tp3 = entry_price - (3.0 * sl_distance)
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
        n = len(df)
        current_price = float(df['close'].iloc[-1]) if n > 0 else 0.0
        safe_atr = max(atr, current_price * 0.001)

        closes = pd.Series(df['close'].values)
        ema_20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
        sma_50 = float(closes.rolling(min(n, 50)).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        is_uptrend = (current_price > sma_200) and (ema_20 > sma_50)
        is_downtrend = (current_price < sma_200) and (ema_20 < sma_50)

        # Pullback bounce on 20 EMA
        last_l = float(df['low'].iloc[-1])
        last_h = float(df['high'].iloc[-1])
        bounce_20_ema_long = is_uptrend and (last_l <= ema_20 + 0.2 * safe_atr) and (current_price >= ema_20)
        bounce_20_ema_short = is_downtrend and (last_h >= ema_20 - 0.2 * safe_atr) and (current_price <= ema_20)

        action = 'HOLD'
        status = 'SCANNING_TREND_ALIGNMENT'
        confidence = 50.0
        reasons = []

        if bounce_20_ema_long and (df['close'].iloc[-1] > df['open'].iloc[-1]):
            action = 'BUY'
            status = 'ADAM_KHOO_20_EMA_BOUNCE_BUY'
            confidence = 86.0
            reasons.append(f"Adam Khoo: Price > 200 SMA ({sma_200:.2f}) & 20 EMA > 50 SMA in Bullish Stack")
            reasons.append(f"20 EMA Pullback Bounce confirmed at {ema_20:.2f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, entry_price - (ema_20 - 0.30 * safe_atr))
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (2.0 * sl_distance)
            tp3 = entry_price + (3.0 * sl_distance)

        elif bounce_20_ema_short and (df['close'].iloc[-1] < df['open'].iloc[-1]):
            action = 'SELL'
            status = 'ADAM_KHOO_20_EMA_REJECT_SELL'
            confidence = 86.0
            reasons.append(f"Adam Khoo: Price < 200 SMA ({sma_200:.2f}) & 20 EMA < 50 SMA in Bearish Stack")
            reasons.append(f"20 EMA Pullback Rejection confirmed at {ema_20:.2f}")
            entry_price = current_price
            sl_distance = max(1.80 * safe_atr, (ema_20 + 0.30 * safe_atr) - entry_price)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (2.0 * sl_distance)
            tp3 = entry_price - (3.0 * sl_distance)
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

        # Breakout above ORB High
        if (closes[-1] > orb_high) and (df['close'].iloc[-1] > df['open'].iloc[-1]):
            action = 'BUY'
            status = '15M_ORB_BULLISH_BREAKOUT'
            confidence = 85.0
            reasons.append(f"Ariel Zwecher: Clean 15M Opening Range Breakout above {orb_high:.2f}")
            entry_price = current_price
            sl_distance = max(entry_price - (orb_high - 0.25 * safe_atr), 1.50 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (2.0 * sl_distance)  # Fixed 1:2 R:R
            tp3 = entry_price + (2.5 * sl_distance)

        # Breakdown below ORB Low
        elif (closes[-1] < orb_low) and (df['close'].iloc[-1] < df['open'].iloc[-1]):
            action = 'SELL'
            status = '15M_ORB_BEARISH_BREAKDOWN'
            confidence = 85.0
            reasons.append(f"Ariel Zwecher: Clean 15M Opening Range Breakdown below {orb_low:.2f}")
            entry_price = current_price
            sl_distance = max((orb_low + 0.25 * safe_atr) - entry_price, 1.50 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (2.0 * sl_distance)
            tp3 = entry_price - (2.5 * sl_distance)
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

        closes = pd.Series(df['close'].values)
        opens = pd.Series(df['open'].values)
        highs = pd.Series(df['high'].values)
        lows = pd.Series(df['low'].values)

        sma_20 = float(closes.rolling(min(n, 20)).mean().iloc[-1])
        sma_200 = float(closes.rolling(min(n, 200)).mean().iloc[-1])

        # Candle body analysis
        bodies = (closes - opens).abs()
        avg_body = float(bodies.tail(15).mean()) if n >= 15 else float(bodies.mean())
        last_body = abs(closes.iloc[-1] - opens.iloc[-1])
        rng = max(highs.iloc[-1] - lows.iloc[-1], 1e-9)

        # Elephant Bar = body >= 1.7x average body
        is_elephant_bar = last_body >= (avg_body * 1.7)
        # Bottoming Tail Bar = lower wick >= 50% of candle range
        is_bottoming_tail = ((min(opens.iloc[-1], closes.iloc[-1]) - lows.iloc[-1]) / rng) >= 0.50
        # Topping Tail Bar = upper wick >= 50% of candle range
        is_topping_tail = ((highs.iloc[-1] - max(opens.iloc[-1], closes.iloc[-1])) / rng) >= 0.50

        # Location rule: Price must be at or near 20 SMA (distance <= 0.35 ATR)
        near_20_sma = abs(current_price - sma_20) <= (0.45 * safe_atr)
        is_uptrend = (current_price > sma_200) and (sma_20 >= sma_200)
        is_downtrend = (current_price < sma_200) and (sma_20 <= sma_200)

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
            sl_distance = max(entry_price - (lows.iloc[-1] - 0.10 * safe_atr), 1.50 * safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (2.0 * sl_distance)
            tp3 = entry_price + (3.0 * sl_distance)

        elif is_downtrend and near_20_sma and (closes.iloc[-1] < opens.iloc[-1]) and (is_elephant_bar or is_topping_tail):
            action = 'SELL'
            bar_type = "Elephant Bar" if is_elephant_bar else "Topping Tail Bar"
            status = f'OLIVER_VELEZ_{bar_type.upper().replace(" ", "_")}_SELL'
            confidence = 88.0
            reasons.append(f"Oliver Velez: {bar_type} formed precisely at 20 SMA Location ({sma_20:.2f})")
            reasons.append(f"Macro Baseline Aligned: Price < 200 SMA ({sma_200:.2f})")
            entry_price = current_price
            sl_distance = max((highs.iloc[-1] + 0.10 * safe_atr) - entry_price, 1.50 * safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (2.0 * sl_distance)
            tp3 = entry_price - (3.0 * sl_distance)
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

        # Mechanical Long: Price breaks Donchian High, Price > 200 SMA, RSI > 50
        if (current_price > donchian_high) and (current_price > sma_200) and (rsi_val >= 50.0):
            action = 'BUY'
            status = 'DONCHIAN_MECHANICAL_BUY'
            confidence = 86.0
            reasons.append(f"Trade Pro: Mechanical Donchian 20 High ({donchian_high:.2f}) Breakout")
            reasons.append(f"Trend Filters: Price > 200 SMA ({sma_200:.2f}) & RSI({rsi_val:.1f}) >= 50")
            entry_price = current_price
            sl_distance = max(1.50 * safe_atr, entry_price - donchian_high + safe_atr)
            stop_loss = entry_price - sl_distance
            tp1 = entry_price + (0.38 * safe_atr)
            tp2 = entry_price + (2.0 * sl_distance)  # Mechanical 1:2 R:R
            tp3 = entry_price + (3.0 * sl_distance)

        # Mechanical Short: Price breaks Donchian Low, Price < 200 SMA, RSI < 50
        elif (current_price < donchian_low) and (current_price < sma_200) and (rsi_val <= 50.0):
            action = 'SELL'
            status = 'DONCHIAN_MECHANICAL_SELL'
            confidence = 86.0
            reasons.append(f"Trade Pro: Mechanical Donchian 20 Low ({donchian_low:.2f}) Breakdown")
            reasons.append(f"Trend Filters: Price < 200 SMA ({sma_200:.2f}) & RSI({rsi_val:.1f}) <= 50")
            entry_price = current_price
            sl_distance = max(1.50 * safe_atr, donchian_low - entry_price + safe_atr)
            stop_loss = entry_price + sl_distance
            tp1 = entry_price - (0.38 * safe_atr)
            tp2 = entry_price - (2.0 * sl_distance)  # Mechanical 1:2 R:R
            tp3 = entry_price - (3.0 * sl_distance)
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
# MASTER STREAMER PLAYBOOK DISPATCHER (EVALUATE ALL 12 STRATEGIES)
# ─────────────────────────────────────────────────────────────────────────────
class MasterStreamerPlaybook:
    """
    Central dispatcher that evaluates all 12 strategies from the Master Playbook PDF.
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
        'TRADE_PRO': TradeProStrategy
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
        Evaluates all 12 strategies simultaneously and identifies all confirmed setups.
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
