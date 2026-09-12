"""
Master Confluence and Signal Synthesis Engine
Combines 5 Spot layers + 4 Futures-exclusive layers into a unified
probabilistic prediction for both Spot and Perpetual Futures markets.
"""

from typing import Dict, Any, List, Optional
import pandas as pd


class ConfluenceEngine:
    """
    Synthesizes multiple analytical dimensions into a unified probabilistic prediction.
    Supports both SPOT (5-layer) and FUTURES (9-layer) modes.
    """

    @classmethod
    def evaluate(
        cls,
        df_indicators: pd.DataFrame,
        smc_data: Dict[str, Any],
        ml_prediction: Dict[str, Any],
        orderbook_metrics: Dict[str, Any],
        futures_signals: Optional[Dict[str, Any]] = None,   # None = spot mode
        cme_proxy: Optional[Dict[str, Any]] = None,
        currency_strength: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes multi-strategy confluence scoring and signal generation.
        Pass futures_signals to activate 9-layer futures mode.
        """
        last_row = df_indicators.iloc[-1]
        score = 0.0
        reasons = []
        is_futures = futures_signals is not None

        # ==========================================
        # LAYER 1: MULTI-FACTOR TREND & MOMENTUM (Weight: 30%)
        # ==========================================
        trend_score = 0.0

        # SuperTrend
        st_dir = last_row.get('supertrend_dir', 0)
        if st_dir == 1:
            trend_score += 10.0
            reasons.append("Trend: SuperTrend is Bullish (+10)")
        elif st_dir == -1:
            trend_score -= 10.0
            reasons.append("Trend: SuperTrend is Bearish (-10)")

        # EMA Ribbon Alignment
        ema_trend = last_row.get('ema_trend', 0)
        if ema_trend == 1:
            trend_score += 10.0
            reasons.append("Trend: EMA Ribbon in Bullish Stack (20 > 50 > 200) (+10)")
        elif ema_trend == -1:
            trend_score -= 10.0
            reasons.append("Trend: EMA Ribbon in Bearish Stack (20 < 50 < 200) (-10)")

        # MACD Momentum
        macd_hist = last_row.get('macd_hist', 0.0)
        macd_slope = last_row.get('macd_hist_slope', 0.0)
        if macd_hist > 0 and macd_slope > 0:
            trend_score += 10.0
            reasons.append("Momentum: MACD Histogram positive and expanding (+10)")
        elif macd_hist < 0 and macd_slope < 0:
            trend_score -= 10.0
            reasons.append("Momentum: MACD Histogram negative and declining (-10)")

        # Kaufman Efficiency Ratio (KER) filter
        ker = last_row.get('kaufman_er', 0.30)
        if ker > 0.38:
            trend_score *= 1.20
            reasons.append(f"Efficiency: High signal-to-noise trending efficiency (KER={ker:.2f} > 0.38)")
        elif ker < 0.20:
            trend_score *= 0.80
            reasons.append(f"Efficiency: Market noise dominant — trend signals dampened (KER={ker:.2f} < 0.20)")

        # ADX Trend Filter
        adx = last_row.get('adx_14', 20.0)
        if adx > 25:
            trend_score *= 1.15
            reasons.append(f"Regime: Strong trending market (ADX={adx:.1f} > 25)")
        else:
            reasons.append(f"Regime: Low-trend / Choppy range market (ADX={adx:.1f} < 25)")

        score += trend_score

        # ==========================================
        # LAYER 2: SMART MONEY CONCEPTS & OTE (Weight: 25%)
        # ==========================================
        smc_score = 0.0
        struct_info = smc_data.get('structure', {})
        structure = struct_info.get('structure', 'NEUTRAL')
        market_zone = struct_info.get('market_zone', 'EQUILIBRIUM')
        in_bull_ote = struct_info.get('in_bull_ote', False)
        in_bear_ote = struct_info.get('in_bear_ote', False)

        if structure == 'BULLISH':
            smc_score += 12.0
            reasons.append("SMC: Bullish Break of Structure (BOS) detected (+12)")
        elif structure == 'BEARISH':
            smc_score -= 12.0
            reasons.append("SMC: Bearish Break of Structure (BOS) detected (-12)")

        # Institutional Fibonacci Golden Pocket (OTE: 61.8% - 78.6% retracement)
        if in_bull_ote and structure != 'BEARISH':
            smc_score += 10.0
            reasons.append("SMC: Price in Institutional Bullish OTE Golden Pocket (61.8% - 78.6% Fib) (+10)")
        elif in_bear_ote and structure != 'BULLISH':
            smc_score -= 10.0
            reasons.append("SMC: Price in Institutional Bearish OTE Golden Pocket (61.8% - 78.6% Fib) (-10)")
        elif market_zone == 'DISCOUNT' and structure == 'BULLISH':
            smc_score += 5.0
            reasons.append("SMC: Price in Discount Buying Zone (<50% range) (+5)")
        elif market_zone == 'PREMIUM' and structure == 'BEARISH':
            smc_score -= 5.0
            reasons.append("SMC: Price in Premium Selling Zone (>50% range) (-5)")

        fvgs = smc_data.get('fvgs', [])
        active_bull_fvgs = [f for f in fvgs if f['type'] == 'BULLISH_FVG' and not f['mitigated']]
        active_bear_fvgs = [f for f in fvgs if f['type'] == 'BEARISH_FVG' and not f['mitigated']]

        in_bull_fvg = any(f.get('in_zone', False) for f in active_bull_fvgs)
        in_bear_fvg = any(f.get('in_zone', False) for f in active_bear_fvgs)

        if in_bull_fvg:
            smc_score += 8.0
            reasons.append("SMC: Price retesting Bullish FVG Support zone (+8)")
        elif in_bear_fvg:
            smc_score -= 8.0
            reasons.append("SMC: Price retesting Bearish FVG Resistance zone (-8)")

        sweep = struct_info.get('liquidity_sweep', 'NONE')
        if sweep == 'BULLISH_SELL_SIDE_LIQUIDITY_SWEPT':
            smc_score += 8.0
            reasons.append("SMC: Sell-side liquidity swept — Bullish Fakeout (+8)")
        elif sweep == 'BEARISH_BUY_SIDE_LIQUIDITY_SWEPT':
            smc_score -= 8.0
            reasons.append("SMC: Buy-side liquidity swept — Bearish Fakeout (-8)")

        score += smc_score

        # ==========================================
        # LAYER 3: STATISTICAL MEAN REVERSION & CMO (Weight: 15%)
        # ==========================================
        stat_score = 0.0
        rsi = last_row.get('rsi_14', 50.0)
        stoch_k = last_row.get('stoch_rsi_k', 50.0)
        stoch_d = last_row.get('stoch_rsi_d', 50.0)
        cmo = last_row.get('cmo_14', 0.0)

        if rsi < 30 and stoch_k < 20 and stoch_k > stoch_d:
            stat_score += 15.0
            reasons.append(f"Mean Reversion: Extreme Oversold bounce (RSI={rsi:.1f}, Stoch Cross) (+15)")
        elif rsi > 70 and stoch_k > 80 and stoch_k < stoch_d:
            stat_score -= 15.0
            reasons.append(f"Mean Reversion: Extreme Overbought exhaustion (RSI={rsi:.1f}, Stoch Cross) (-15)")
        elif rsi < 40 and stoch_k > stoch_d:
            stat_score += 7.0
            reasons.append(f"Oscillators: Bullish momentum turning up (RSI={rsi:.1f}) (+7)")
        elif rsi > 60 and stoch_k < stoch_d:
            stat_score -= 7.0
            reasons.append(f"Oscillators: Bearish momentum turning down (RSI={rsi:.1f}) (-7)")

        # Chande Momentum Oscillator extreme velocity
        if cmo < -50.0:
            stat_score += 6.0
            reasons.append(f"Oscillators: Chande Momentum deeply oversold (CMO={cmo:.1f}) (+6)")
        elif cmo > 50.0:
            stat_score -= 6.0
            reasons.append(f"Oscillators: Chande Momentum deeply overbought (CMO={cmo:.1f}) (-6)")

        if last_row.get('bb_squeeze', False):
            reasons.append("Volatility: Bollinger Band Squeeze — explosive breakout imminent")

        score += stat_score

        # ==========================================
        # LAYER 4: MULTI-MODEL ML ENSEMBLE (Weight: 20%)
        # ==========================================
        ml_score = 0.0
        p_bull = ml_prediction.get('p_bullish', 0.33)
        p_bear = ml_prediction.get('p_bearish', 0.33)
        ml_conf = ml_prediction.get('confidence_pct', 0.0)

        if p_bull > p_bear and ml_conf > 15:
            ml_points = min(20.0, (p_bull - p_bear) * 40.0)
            ml_score += ml_points
            reasons.append(f"ML Ensemble: Bullish consensus P(Long)={p_bull*100:.1f}%, Conf={ml_conf:.1f}% (+{ml_points:.1f})")
        elif p_bear > p_bull and ml_conf > 15:
            ml_points = min(20.0, (p_bear - p_bull) * 40.0)
            ml_score -= ml_points
            reasons.append(f"ML Ensemble: Bearish consensus P(Short)={p_bear*100:.1f}%, Conf={ml_conf:.1f}% (-{ml_points:.1f})")
        else:
            reasons.append(f"ML Ensemble: Neutral distribution (P(Long)={p_bull*100:.1f}%, P(Short)={p_bear*100:.1f}%)")

        score += ml_score

        # ==========================================
        # LAYER 5: ORDER BOOK & DELTA FLOW (Weight: 10%)
        # ==========================================
        ob_score = 0.0
        if orderbook_metrics and orderbook_metrics.get('available'):
            imbalance = orderbook_metrics.get('imbalance_ratio', 0.0)
            if imbalance > 0.15:
                ob_score += 10.0
                reasons.append(f"Order Flow: Heavy Buyer dominance ({imbalance*100:+.1f}% depth) (+10)")
            elif imbalance < -0.15:
                ob_score -= 10.0
                reasons.append(f"Order Flow: Heavy Seller dominance ({imbalance*100:+.1f}% depth) (-10)")
            else:
                reasons.append(f"Order Flow: Balanced Bid/Ask depth ({imbalance*100:+.1f}%)")

        cvd_z = last_row.get('cvd_zscore', 0.0)
        if cvd_z > 1.8:
            ob_score += 6.0
            reasons.append(f"Delta Flow: Institutional Aggressive Absorption Buying (CVD Z-Score = {cvd_z:+.2f}) (+6)")
        elif cvd_z < -1.8:
            ob_score -= 6.0
            reasons.append(f"Delta Flow: Institutional Aggressive Absorption Selling (CVD Z-Score = {cvd_z:+.2f}) (-6)")

        score += ob_score

        # ==========================================
        # FUTURES LAYERS F1-F8 (only in futures mode)
        # ==========================================
        f1_score = 0.0
        f2_score = 0.0
        f3_score = 0.0
        f4_score = 0.0
        f5_score = 0.0
        f6_score = 0.0
        f7_score = 0.0
        f8_score = 0.0

        if is_futures and futures_signals:
            funding_analysis = futures_signals.get('funding_analysis', {})
            oi_analysis      = futures_signals.get('oi_analysis', {})
            squeeze_analysis = futures_signals.get('squeeze_analysis', {})
            basis_analysis   = futures_signals.get('basis_analysis', {})
            cvd_analysis     = futures_signals.get('cvd_analysis', {})
            vwap_analysis    = futures_signals.get('vwap_analysis', {})
            liq_analysis     = futures_signals.get('liq_analysis', {})
            scalp_analysis   = futures_signals.get('scalp_analysis', {})

            f1_score = funding_analysis.get('score', 0.0)
            reasons.extend(funding_analysis.get('reasons', []))

            f2_score = oi_analysis.get('score', 0.0)
            reasons.extend(oi_analysis.get('reasons', []))

            f3_score = squeeze_analysis.get('score', 0.0)
            reasons.extend(squeeze_analysis.get('reasons', []))

            f4_score = basis_analysis.get('score', 0.0)
            reasons.extend(basis_analysis.get('reasons', []))

            f5_score = cvd_analysis.get('score', 0.0)
            reasons.extend(cvd_analysis.get('reasons', []))

            f6_score = vwap_analysis.get('score', 0.0)
            reasons.extend(vwap_analysis.get('reasons', []))

            f7_score = liq_analysis.get('score', 0.0)
            reasons.extend(liq_analysis.get('reasons', []))

            f8_score = scalp_analysis.get('score', 0.0)
            reasons.extend(scalp_analysis.get('reasons', []))

            score += (f1_score + f2_score + f3_score + f4_score + f5_score + f6_score + f7_score + f8_score)

        # ==========================================
        # CME INSTITUTIONAL ORDER FLOW (Gold & Commodities)
        # ==========================================
        cme_score = 0.0
        if cme_proxy and cme_proxy.get('available'):
            raw_cme = float(cme_proxy.get('order_flow_score', 0.0))
            cme_score = round(raw_cme * 0.15, 1)
            score += cme_score
            reasons.append(f"CME Institutional Flow: {cme_proxy.get('flow_description', '')} ({cme_score:+.1f})")

        # ==========================================
        # CURRENCY STRENGTH METER (Forex pairs)
        # ==========================================
        csm_score = 0.0
        if currency_strength and currency_strength.get('available'):
            raw_csm = float(currency_strength.get('directional_score', currency_strength.get('score', 0.0)))
            csm_score = round(raw_csm * 0.6, 1)
            score += csm_score
            reasons.append(f"Currency Strength Meter: {currency_strength.get('reason', '')} ({csm_score:+.1f})")

        # ==========================================
        # FINAL SYNTHESIS
        # ==========================================
        score = max(-100.0, min(100.0, score))

        # Thresholds calibrated for high probability
        strong_threshold = 42.0 if is_futures else 45.0
        normal_threshold = 16.0 if is_futures else 18.0

        if score >= strong_threshold:
            action = 'STRONG BUY'
            sentiment = 'VERY_BULLISH'
        elif score >= normal_threshold:
            action = 'BUY'
            sentiment = 'BULLISH'
        elif score <= -strong_threshold:
            action = 'STRONG SELL'
            sentiment = 'VERY_BEARISH'
        elif score <= -normal_threshold:
            action = 'SELL'
            sentiment = 'BEARISH'
        else:
            action = 'NEUTRAL'
            sentiment = 'CONSOLIDATION'

        layer_scores = {
            'trend_momentum': round(trend_score, 1),
            'smart_money_smc': round(smc_score, 1),
            'mean_reversion_stat': round(stat_score, 1),
            'machine_learning': round(ml_score, 1),
            'orderbook_pressure': round(ob_score, 1),
        }
        if cme_proxy and cme_proxy.get('available'):
            layer_scores['cme_institutional_order_flow'] = cme_score
        if currency_strength and currency_strength.get('available'):
            layer_scores['currency_strength_flow'] = csm_score

        if is_futures:
            layer_scores.update({
                'f1_funding_rate': round(f1_score, 1),
                'f2_open_interest': round(f2_score, 1),
                'f3_squeeze_detection': round(f3_score, 1),
                'f4_basis_premium': round(f4_score, 1),
                'f5_cvd_delta_flow': round(f5_score, 1),
                'f6_vwap_bands': round(f6_score, 1),
                'f7_liquidation_magnets': round(f7_score, 1),
                'f8_scalp_micro_flow': round(f8_score, 1),
            })

        return {
            'action': action,
            'sentiment': sentiment,
            'confluence_score': round(score, 1),
            'quality_index_pct': round(abs(score), 1),
            'market_mode': 'FUTURES' if is_futures else 'SPOT',
            'layer_scores': layer_scores,
            'reasons': reasons
        }
