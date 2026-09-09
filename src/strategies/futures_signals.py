"""
Futures-Exclusive Signal Engine
Implements the 4 high-probability futures strategies researched from 2025/2026
institutional and quantitative trading practices:

  F1. Funding Rate Regime Analysis
  F2. Open Interest (OI) Flow Analysis
  F3. Long/Short Squeeze Detection
  F4. Spot-Futures Basis Premium Analysis
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

# ---- Funding Rate thresholds (industry standard 2025/2026) ----
FUNDING_EXTREME_LONG  = 0.0005   # >0.05%  per 8h = market dangerously overleveraged long
FUNDING_HIGH_LONG     = 0.0002   # >0.02%  per 8h = elevated long bias
FUNDING_NEUTRAL_HIGH  = 0.0001   # >0.01%
FUNDING_NEUTRAL_LOW   = -0.0001  # <-0.01%
FUNDING_HIGH_SHORT    = -0.0002  # <-0.02% per 8h = elevated short bias
FUNDING_EXTREME_SHORT = -0.0004  # <-0.04% per 8h = market dangerously overleveraged short


class FuturesSignalEngine:
    """
    Generates futures-specific signals from live derivatives data.
    All methods return score contributions and human-readable reasons.
    """

    @staticmethod
    def analyze_funding_rate(
        current_funding: float,
        funding_history: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        F1: Funding Rate Regime Analysis.
        Returns score (-30 to +30), regime label, and detailed reasons.
        """
        score = 0.0
        regime = 'NEUTRAL'
        reasons = []

        fr_pct = current_funding * 100.0
        fr_8h_annualized = current_funding * 3 * 365 * 100.0

        # Average funding over last 24h (3 periods at 8h each)
        avg_24h = 0.0
        if not funding_history.empty and len(funding_history) >= 3:
            avg_24h = float(funding_history['funding_rate'].iloc[-3:].mean())

        # Trend: is funding accelerating or decelerating?
        funding_trend = 'STABLE'
        if len(funding_history) >= 6:
            recent = float(funding_history['funding_rate'].iloc[-3:].mean())
            prior  = float(funding_history['funding_rate'].iloc[-6:-3].mean())
            delta  = recent - prior
            if abs(delta) > 0.00005:
                funding_trend = 'RISING' if delta > 0 else 'FALLING'

        # --- Score based on regime ---
        if current_funding >= FUNDING_EXTREME_LONG:
            # Extreme crowded long: fade setup, short bias
            score = -30.0
            regime = 'EXTREME_LONG_OVERCROWDED'
            reasons.append(f"F1-Funding: DANGER — Extreme positive funding {fr_pct:.4f}% (annualized {fr_8h_annualized:.1f}%). Market overleveraged long. Long Squeeze risk is HIGH. (-30)")
        elif current_funding >= FUNDING_HIGH_LONG:
            score = -15.0
            regime = 'HIGH_LONG_BIAS'
            reasons.append(f"F1-Funding: Elevated positive funding {fr_pct:.4f}%. Overcrowded longs — moderate short squeeze risk. (-15)")
        elif current_funding >= FUNDING_NEUTRAL_HIGH:
            score = -5.0
            regime = 'MILD_LONG_BIAS'
            reasons.append(f"F1-Funding: Mildly positive funding {fr_pct:.4f}%. Slight long bias, watch for fade. (-5)")
        elif current_funding <= FUNDING_EXTREME_SHORT:
            # Extreme crowded short: squeeze setup, long bias
            score = +30.0
            regime = 'EXTREME_SHORT_OVERCROWDED'
            reasons.append(f"F1-Funding: DANGER — Extreme negative funding {fr_pct:.4f}%. Market overleveraged short. SHORT SQUEEZE risk is HIGH. (+30)")
        elif current_funding <= FUNDING_HIGH_SHORT:
            score = +15.0
            regime = 'HIGH_SHORT_BIAS'
            reasons.append(f"F1-Funding: Elevated negative funding {fr_pct:.4f}%. Bears overcrowded — potential short squeeze setup. (+15)")
        elif current_funding <= FUNDING_NEUTRAL_LOW:
            score = +5.0
            regime = 'MILD_SHORT_BIAS'
            reasons.append(f"F1-Funding: Mildly negative funding {fr_pct:.4f}%. Slight short bias. (+5)")
        else:
            score = 0.0
            regime = 'NEUTRAL'
            reasons.append(f"F1-Funding: Neutral funding {fr_pct:.4f}%. Healthy trend environment. No squeeze risk.")

        # Acceleration bonus/penalty
        if funding_trend == 'RISING' and current_funding > 0:
            score -= 5.0
            reasons.append("F1-Funding Trend: Funding accelerating higher — increasing long squeeze risk. (-5)")
        elif funding_trend == 'FALLING' and current_funding < 0:
            score += 5.0
            reasons.append("F1-Funding Trend: Negative funding accelerating — increasing short squeeze probability. (+5)")

        return {
            'score': round(score, 2),
            'regime': regime,
            'current_funding_pct': round(fr_pct, 5),
            'annualized_pct': round(fr_8h_annualized, 2),
            'avg_24h_pct': round(avg_24h * 100.0, 5),
            'funding_trend': funding_trend,
            'reasons': reasons
        }

    @staticmethod
    def analyze_open_interest(
        oi_history: pd.DataFrame,
        current_price: float,
        current_oi: float
    ) -> Dict[str, Any]:
        """
        F2: Open Interest Flow Analysis.
        Measures whether capital is flowing in or out of the market.
        """
        score = 0.0
        reasons = []
        oi_flow = 'NEUTRAL'

        if oi_history.empty or len(oi_history) < 5:
            return {
                'score': 0.0, 'oi_flow': 'INSUFFICIENT_DATA',
                'oi_change_pct': 0.0, 'oi_at_extreme': False,
                'reasons': ["F2-OI: Insufficient historical OI data."]
            }

        # OI change over last 5 periods
        recent_oi = float(oi_history['open_interest'].iloc[-1])
        prev_oi   = float(oi_history['open_interest'].iloc[-5])
        oi_5p_change_pct = ((recent_oi - prev_oi) / max(prev_oi, 1)) * 100.0

        # OI at local high (last 50 periods)?
        max_oi_50 = float(oi_history['open_interest'].max())
        oi_at_extreme = recent_oi >= (max_oi_50 * 0.95)

        # Price trend (last 5 candles) — we look at sign only
        # We'll use OI change direction + sign from oi_history's oi_change
        oi_rising = oi_5p_change_pct > 1.5
        oi_falling = oi_5p_change_pct < -1.5

        # We need price trend — derive from current_price vs stored values
        # Use oi_change as proxy (direction only inferred from history)
        if oi_rising:
            # Rising OI — bullish or bearish depending on price action
            # Without price history here, use current funding context
            score = +10.0
            oi_flow = 'RISING_OI_TREND_FUEL'
            reasons.append(f"F2-OI: Open Interest rising +{oi_5p_change_pct:.1f}% — fresh capital entering market, trend has fuel. (+10)")
        elif oi_falling:
            score = -5.0
            oi_flow = 'FALLING_OI_CAPITULATION'
            reasons.append(f"F2-OI: Open Interest falling {oi_5p_change_pct:.1f}% — positions closing, trend losing momentum. (-5)")
        else:
            score = 0.0
            oi_flow = 'STABLE_OI'
            reasons.append(f"F2-OI: Open Interest stable ({oi_5p_change_pct:+.1f}%). No strong capital flow signal.")

        # Extreme OI warning
        if oi_at_extreme and oi_rising:
            score -= 8.0
            reasons.append(f"F2-OI: WARNING — OI near 50-period high. Extremely crowded market, high squeeze/reversal risk. (-8)")
        elif oi_at_extreme:
            reasons.append(f"F2-OI: OI near local highs — watch for liquidation cascade if price loses key support.")

        return {
            'score': round(score, 2),
            'oi_flow': oi_flow,
            'current_oi': current_oi,
            'oi_5p_change_pct': round(oi_5p_change_pct, 2),
            'oi_at_extreme': oi_at_extreme,
            'reasons': reasons
        }

    @staticmethod
    def detect_squeeze(
        current_funding: float,
        oi_analysis: Dict[str, Any],
        current_price: float,
        recent_swing_high: float,
        recent_swing_low: float,
        ls_ratio: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        F3: Long/Short Squeeze Detection.
        The most explosive setups in futures markets.
        """
        score = 0.0
        squeeze_type = 'NONE'
        reasons = []

        long_pct = ls_ratio.get('long_pct', 50.0)
        short_pct = ls_ratio.get('short_pct', 50.0)
        ls_bias = ls_ratio.get('bias', 'BALANCED')
        oi_at_extreme = oi_analysis.get('oi_at_extreme', False)
        oi_flow = oi_analysis.get('oi_flow', 'STABLE_OI')

        # Distance from key levels
        price_near_high = current_price >= (recent_swing_high * 0.995)
        price_near_low  = current_price <= (recent_swing_low  * 1.005)

        # --- SHORT SQUEEZE conditions ---
        short_squeeze_signals = 0
        if current_funding <= FUNDING_HIGH_SHORT:
            short_squeeze_signals += 1
        if ls_bias in ('CROWDED_SHORT',) or short_pct > 60:
            short_squeeze_signals += 1
        if 'RISING' in oi_flow and current_funding < 0:
            short_squeeze_signals += 1
        if price_near_low:
            short_squeeze_signals += 1

        # --- LONG SQUEEZE conditions ---
        long_squeeze_signals = 0
        if current_funding >= FUNDING_HIGH_LONG:
            long_squeeze_signals += 1
        if ls_bias in ('CROWDED_LONG',) or long_pct > 65:
            long_squeeze_signals += 1
        if oi_at_extreme and current_funding > 0:
            long_squeeze_signals += 1
        if price_near_high:
            long_squeeze_signals += 1

        # Evaluate
        if short_squeeze_signals >= 3:
            squeeze_type = 'SHORT_SQUEEZE_SETUP'
            score = +25.0
            reasons.append(f"F3-Squeeze: HIGH PROBABILITY SHORT SQUEEZE SETUP ({short_squeeze_signals}/4 signals). Bears overcrowded ({short_pct:.1f}%) with extreme negative funding. Explosive upside rally risk. (+25)")
        elif short_squeeze_signals == 2:
            squeeze_type = 'POTENTIAL_SHORT_SQUEEZE'
            score = +12.0
            reasons.append(f"F3-Squeeze: Potential short squeeze brewing ({short_squeeze_signals}/4 signals). Monitor for confirmation. (+12)")

        if long_squeeze_signals >= 3:
            squeeze_type = 'LONG_SQUEEZE_SETUP'
            score = -25.0
            reasons.append(f"F3-Squeeze: HIGH PROBABILITY LONG SQUEEZE SETUP ({long_squeeze_signals}/4 signals). Longs overcrowded ({long_pct:.1f}%) with extreme positive funding. Cascading sell-off risk. (-25)")
        elif long_squeeze_signals == 2 and score >= 0:
            squeeze_type = 'POTENTIAL_LONG_SQUEEZE'
            score = -12.0
            reasons.append(f"F3-Squeeze: Potential long squeeze building ({long_squeeze_signals}/4 signals). (-12)")

        if squeeze_type == 'NONE':
            reasons.append(f"F3-Squeeze: No squeeze setup detected. L/S Ratio: {long_pct:.1f}% / {short_pct:.1f}%.")

        return {
            'score': round(score, 2),
            'squeeze_type': squeeze_type,
            'long_pct': long_pct,
            'short_pct': short_pct,
            'short_squeeze_signals': short_squeeze_signals,
            'long_squeeze_signals': long_squeeze_signals,
            'reasons': reasons
        }

    @staticmethod
    def analyze_basis(basis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        F4: Spot-Futures Basis Premium Analysis.
        """
        score = 0.0
        reasons = []
        basis_pct = basis_data.get('basis_pct', 0.0)
        regime = basis_data.get('regime', 'UNKNOWN')

        if regime == 'HIGH_PREMIUM_BULLISH':
            score = -8.0  # Futures priced too high vs spot — fade premium risk
            reasons.append(f"F4-Basis: High futures premium of {basis_pct:+.3f}% above spot. Market bullishly leveraged — mean reversion risk. (-8)")
        elif regime == 'MILD_PREMIUM_BULLISH':
            score = +5.0  # Healthy bullish premium
            reasons.append(f"F4-Basis: Healthy futures premium of {basis_pct:+.3f}%. Bullish carry signal. (+5)")
        elif regime == 'DISCOUNT_BEARISH':
            score = +8.0  # Futures cheaper than spot — bearish fear priced in, potential reversal
            reasons.append(f"F4-Basis: Futures trading at {basis_pct:+.3f}% DISCOUNT to spot. Fear/bearishness fully priced — contrarian long setup. (+8)")
        elif regime == 'MILD_DISCOUNT':
            score = -3.0
            reasons.append(f"F4-Basis: Mild futures discount {basis_pct:+.3f}%. Slight bearish sentiment. (-3)")
        else:
            score = 0.0
            reasons.append(f"F4-Basis: Futures near parity with spot ({basis_pct:+.3f}%). Neutral leverage sentiment.")

        return {
            'score': round(score, 2),
            'basis_pct': basis_pct,
            'regime': regime,
            'reasons': reasons
        }

    @staticmethod
    def analyze_cvd(df_indicators: pd.DataFrame) -> Dict[str, Any]:
        """
        F5: Cumulative Volume Delta (CVD) & Delta Flow Engine.
        Detects aggressive market orders vs passive limit order absorption.
        """
        score = 0.0
        reasons = []
        regime = 'NEUTRAL'

        if 'cvd' not in df_indicators.columns or len(df_indicators) < 5:
            return {'score': 0.0, 'regime': 'INSUFFICIENT_DATA', 'reasons': ['F5-CVD: Insufficient tick/delta data.']}

        last_row = df_indicators.iloc[-1]
        cvd_val = float(last_row.get('cvd', 0))
        cvd_slope = float(last_row.get('cvd_slope', 0))
        bar_delta = float(last_row.get('bar_delta', 0))
        bull_div = bool(last_row.get('cvd_bull_div', False))
        bear_div = bool(last_row.get('cvd_bear_div', False))

        # Divergences (Highest Conviction Institutional Signal)
        if bull_div:
            score += 18.0
            regime = 'BULLISH_DELTA_ABSORPTION'
            reasons.append("F5-CVD: Institutional Absorption detected — Price testing lows while aggressive sellers absorbed by passive bids (CVD Bullish Divergence) (+18)")
        elif bear_div:
            score -= 18.0
            regime = 'BEARISH_DELTA_EXHAUSTION'
            reasons.append("F5-CVD: Buyer Exhaustion / Passive Selling — Price testing highs while aggressive buyers hitting institutional limit offers (CVD Bearish Divergence) (-18)")
        elif cvd_slope > 0 and bar_delta > 0:
            score += 8.0
            regime = 'AGGRESSIVE_BUY_FLOW'
            reasons.append("F5-CVD: Aggressive market buying pressure accelerating (+8)")
        elif cvd_slope < 0 and bar_delta < 0:
            score -= 8.0
            regime = 'AGGRESSIVE_SELL_FLOW'
            reasons.append("F5-CVD: Aggressive market selling pressure accelerating (-8)")
        else:
            reasons.append("F5-CVD: Order flow delta balanced between buyers and sellers.")

        return {
            'score': round(score, 2),
            'regime': regime,
            'current_cvd': round(cvd_val, 2),
            'bar_delta': round(bar_delta, 2),
            'cvd_slope': round(cvd_slope, 2),
            'bull_div': bull_div,
            'bear_div': bear_div,
            'reasons': reasons
        }

    @staticmethod
    def analyze_vwap(df_indicators: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        """
        F6: Institutional VWAP & Standard Deviation Bands Analysis.
        Benchmark for institutional fair-value and mean-reversion.
        """
        score = 0.0
        reasons = []
        status = 'AT_FAIR_VALUE'

        if 'vwap' not in df_indicators.columns or len(df_indicators) < 2:
            return {'score': 0.0, 'status': 'INSUFFICIENT_DATA', 'reasons': ['F6-VWAP: Insufficient volume data.']}

        last_row = df_indicators.iloc[-1]
        prev_row = df_indicators.iloc[-2]

        vwap = float(last_row.get('vwap', current_price))
        upper_1 = float(last_row.get('vwap_upper_1', current_price * 1.01))
        upper_2 = float(last_row.get('vwap_upper_2', current_price * 1.02))
        lower_1 = float(last_row.get('vwap_lower_1', current_price * 0.99))
        lower_2 = float(last_row.get('vwap_lower_2', current_price * 0.98))

        prev_close = float(prev_row.get('close', current_price))
        curr_close = float(last_row.get('close', current_price))

        # 1. VWAP Cross / Reclaim (Key institutional momentum trigger)
        if prev_close < vwap and curr_close >= vwap:
            score += 15.0
            status = 'BULLISH_VWAP_RECLAIM'
            reasons.append(f"F6-VWAP: Bullish VWAP Reclaim (${vwap:,.2f}) — Institutional buyers pushing price back above benchmark (+15)")
        elif prev_close > vwap and curr_close <= vwap:
            score -= 15.0
            status = 'BEARISH_VWAP_BREAKDOWN'
            reasons.append(f"F6-VWAP: Bearish VWAP Breakdown (${vwap:,.2f}) — Institutional sellers pushing price below benchmark (-15)")
        # 2. Standard deviation extremes
        elif curr_close >= upper_2:
            score -= 12.0
            status = 'OVERBOUGHT_UPPER_2_SIGMA'
            reasons.append(f"F6-VWAP: Extreme Stretch — Price at +2.0σ Upper Band (${upper_2:,.2f}). High mean-reversion pull risk (-12)")
        elif curr_close <= lower_2:
            score += 12.0
            status = 'OVERSOLD_LOWER_2_SIGMA'
            reasons.append(f"F6-VWAP: Extreme Discount — Price at -2.0σ Lower Band (${lower_2:,.2f}). High mean-reversion bounce opportunity (+12)")
        elif curr_close > vwap:
            score += 6.0
            status = 'ABOVE_VWAP_BULLISH'
            reasons.append(f"F6-VWAP: Price trading above VWAP (${vwap:,.2f}) — Bullish value acceptance (+6)")
        else:
            score -= 6.0
            status = 'BELOW_VWAP_BEARISH'
            reasons.append(f"F6-VWAP: Price trading below VWAP (${vwap:,.2f}) — Bearish value acceptance (-6)")

        dist_vwap_pct = ((curr_close - vwap) / vwap) * 100.0 if vwap else 0.0

        return {
            'score': round(score, 2),
            'status': status,
            'vwap': round(vwap, 4),
            'upper_1': round(upper_1, 4),
            'upper_2': round(upper_2, 4),
            'lower_1': round(lower_1, 4),
            'lower_2': round(lower_2, 4),
            'dist_vwap_pct': round(dist_vwap_pct, 3),
            'reasons': reasons
        }

    @staticmethod
    def calculate_liquidation_clusters(
        current_price: float,
        swing_high: float,
        swing_low: float,
        open_interest: float = 0.0
    ) -> Dict[str, Any]:
        """
        F7: Estimated Liquidation Cluster Engine.
        Calculates retail liquidation magnet pools for 10x, 25x, 50x, 100x leverage.
        """
        if current_price <= 0:
            return {'magnet': 'NONE', 'clusters': [], 'score': 0.0, 'reasons': []}

        # Model retail liquidation thresholds based on swing high/low entry reference points
        ref_high = max(swing_high, current_price)
        ref_low  = min(swing_low, current_price)

        long_liq_100x = round(ref_high * (1.0 - 0.008), 2)
        long_liq_50x  = round(ref_high * (1.0 - 0.018), 2)
        long_liq_25x  = round(ref_high * (1.0 - 0.038), 2)
        long_liq_10x  = round(ref_high * (1.0 - 0.095), 2)

        short_liq_100x = round(ref_low * (1.0 + 0.008), 2)
        short_liq_50x  = round(ref_low * (1.0 + 0.018), 2)
        short_liq_25x  = round(ref_low * (1.0 + 0.038), 2)
        short_liq_10x  = round(ref_low * (1.0 + 0.095), 2)

        clusters = [
            {'type': 'SHORT_LIQ', 'leverage': '100x', 'price': short_liq_100x, 'side': 'Buy Stop / Short Liq'},
            {'type': 'SHORT_LIQ', 'leverage': '50x',  'price': short_liq_50x,  'side': 'Buy Stop / Short Liq'},
            {'type': 'SHORT_LIQ', 'leverage': '25x',  'price': short_liq_25x,  'side': 'Buy Stop / Short Liq'},
            {'type': 'LONG_LIQ',  'leverage': '100x', 'price': long_liq_100x,  'side': 'Sell Stop / Long Liq'},
            {'type': 'LONG_LIQ',  'leverage': '50x',  'price': long_liq_50x,   'side': 'Sell Stop / Long Liq'},
            {'type': 'LONG_LIQ',  'leverage': '25x',  'price': long_liq_25x,   'side': 'Sell Stop / Long Liq'},
        ]

        # Find closest cluster to current price
        clusters.sort(key=lambda c: abs(c['price'] - current_price))
        closest = clusters[0]
        dist_pct = ((closest['price'] - current_price) / current_price) * 100.0

        score = 0.0
        reasons = []

        if abs(dist_pct) < 0.4:
            # Imminent liquidation sweep magnet
            if closest['type'] == 'SHORT_LIQ':
                score += 10.0
                reasons.append(f"F7-Liquidation: Price within {abs(dist_pct):.2f}% of Major {closest['leverage']} Short Liquidation Pool (${closest['price']:,.2f}) — Magnet pull upwards (+10)")
            else:
                score -= 10.0
                reasons.append(f"F7-Liquidation: Price within {abs(dist_pct):.2f}% of Major {closest['leverage']} Long Liquidation Pool (${closest['price']:,.2f}) — Magnet pull downwards (-10)")
        else:
            reasons.append(f"F7-Liquidation: Nearest cluster is {closest['type']} {closest['leverage']} at ${closest['price']:,.2f} ({dist_pct:+.2f}% away).")

        return {
            'score': round(score, 2),
            'nearest_magnet': closest,
            'dist_to_magnet_pct': round(dist_pct, 2),
            'clusters': clusters,
            'reasons': reasons
        }

    @staticmethod
    def analyze_scalping_signals(
        df_indicators: pd.DataFrame,
        timeframe: str
    ) -> Dict[str, Any]:
        """
        F8: 3m/5m High-Frequency Scalping Engine.
        Analyzes micro-rejections, wick absorption, and rapid EMA ribbon alignment.
        Active primarily for 3m, 5m, and 15m timeframes.
        """
        is_scalp_tf = timeframe in ('1m', '3m', '5m', '15m')
        if not is_scalp_tf or len(df_indicators) < 5:
            return {'score': 0.0, 'scalp_setup': 'INACTIVE_TIMEFRAME', 'reasons': []}

        last_row = df_indicators.iloc[-1]
        score = 0.0
        reasons = []
        scalp_setup = 'NEUTRAL'

        o, h, l, c = float(last_row['open']), float(last_row['high']), float(last_row['low']), float(last_row['close'])
        rng = max(h - l, 1e-9)
        upper_wick = (h - max(o, c)) / rng
        lower_wick = (min(o, c) - l) / rng
        vol_surge = bool(last_row.get('vol_surge', False))

        ema_9 = float(last_row.get('ema_9', c))
        ema_20 = float(last_row.get('ema_20', c))

        # Micro Bullish Pin / Absorption
        if lower_wick >= 0.45 and c >= o:
            pts = 12.0 if vol_surge else 8.0
            score += pts
            scalp_setup = 'BULLISH_PIN_ABSORPTION'
            reasons.append(f"F8-Scalp ({timeframe}): Bullish rejection wick ({lower_wick*100:.0f}%) {'with volume surge' if vol_surge else ''} (+{pts:.0f})")
        # Micro Bearish Pin / Exhaustion
        elif upper_wick >= 0.45 and c <= o:
            pts = 12.0 if vol_surge else 8.0
            score -= pts
            scalp_setup = 'BEARISH_PIN_EXHAUSTION'
            reasons.append(f"F8-Scalp ({timeframe}): Bearish rejection wick ({upper_wick*100:.0f}%) {'with volume surge' if vol_surge else ''} (-{pts:.0f})")

        # Scalp Micro-Trend (EMA 9 vs 20)
        if c > ema_9 and ema_9 > ema_20:
            score += 5.0
            reasons.append(f"F8-Scalp: Micro momentum bullish (Close > EMA9 > EMA20) (+5)")
        elif c < ema_9 and ema_9 < ema_20:
            score -= 5.0
            reasons.append(f"F8-Scalp: Micro momentum bearish (Close < EMA9 < EMA20) (-5)")

        return {
            'score': round(score, 2),
            'scalp_setup': scalp_setup,
            'is_scalp_tf': True,
            'upper_wick_pct': round(upper_wick * 100, 1),
            'lower_wick_pct': round(lower_wick * 100, 1),
            'reasons': reasons
        }

