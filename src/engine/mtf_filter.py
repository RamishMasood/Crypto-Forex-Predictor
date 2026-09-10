"""
Strict Multi-Timeframe Alignment Engine (Triple-Screen Filter)
Implements Alexander Elder's Triple-Screen concept upgraded for modern institutional SMC & Order Flow:
  Screen 1 (Daily / 4h): Macro trend & 200 EMA + structure filter (Tide).
  Screen 2 (1h): Key zone — Golden Pocket 61.8%-78.6% Fib OTE or Unmitigated FVG / Order Block retest (Wave).
  Screen 3 (5m / 15m): Execution trigger — Liquidity sweep, CVD divergence, SuperTrend & HMA slope alignment (Ripple).
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from ..strategies.indicators import QuantitativeIndicators
from ..strategies.smc import SmartMoneyConcepts


class MultiTimeframeFilter:
    """
    Evaluates multi-timeframe triple-screen synergy to guarantee institutional alignment
    and eliminate low-probability counter-trend trades.
    """

    @classmethod
    def evaluate_macro_screen(cls, df_macro: pd.DataFrame) -> Dict[str, Any]:
        """
        Screen 1: Macro Trend & 200 EMA + Market Structure Filter (Daily / 4h).
        Determines the macroeconomic 'Tide'.
        """
        if df_macro is None or len(df_macro) < 20:
            return {
                'available': False,
                'macro_bias': 'NEUTRAL',
                'close_vs_ema200': 'UNKNOWN',
                'ema_ribbon': 'UNKNOWN',
                'macro_structure': 'NEUTRAL',
                'reasons': ['Macro data unavailable — defaulting to neutral macro filter.']
            }

        df_ind = QuantitativeIndicators.add_all_indicators(df_macro)
        last_row = df_ind.iloc[-1]
        close = float(last_row['close'])
        ema200 = float(last_row.get('ema_200', close))
        ema50  = float(last_row.get('ema_50', close))
        ema20  = float(last_row.get('ema_20', close))

        # 1. Close vs 200 EMA
        is_above_200 = close >= ema200
        close_vs_ema200 = 'ABOVE_200_EMA' if is_above_200 else 'BELOW_200_EMA'

        # 2. EMA Ribbon Alignment
        if ema20 > ema50 > ema200:
            ema_ribbon = 'BULLISH_STACK'
        elif ema20 < ema50 < ema200:
            ema_ribbon = 'BEARISH_STACK'
        else:
            ema_ribbon = 'COMPRESSED_OR_MIXED'

        # 3. Macro Market Structure (BOS / Swings)
        struct = SmartMoneyConcepts.analyze_market_structure(df_ind)
        structure_state = struct.get('structure', 'NEUTRAL')

        reasons = []
        if is_above_200 and (ema_ribbon == 'BULLISH_STACK' or structure_state == 'BULLISH'):
            macro_bias = 'BULLISH'
            reasons.append(f"Screen 1 (Macro): Strongly Bullish — Price above 200 EMA ({close:.2f} > {ema200:.2f}) with {structure_state} structure.")
        elif (not is_above_200) and (ema_ribbon == 'BEARISH_STACK' or structure_state == 'BEARISH'):
            macro_bias = 'BEARISH'
            reasons.append(f"Screen 1 (Macro): Strongly Bearish — Price below 200 EMA ({close:.2f} < {ema200:.2f}) with {structure_state} structure.")
        elif is_above_200:
            macro_bias = 'MILD_BULLISH'
            reasons.append(f"Screen 1 (Macro): Mildly Bullish — Price above 200 EMA but structure/stack mixed.")
        else:
            macro_bias = 'MILD_BEARISH'
            reasons.append(f"Screen 1 (Macro): Mildly Bearish — Price below 200 EMA but structure/stack mixed.")

        return {
            'available': True,
            'macro_bias': macro_bias,
            'close': round(close, 5),
            'ema_200': round(ema200, 5),
            'close_vs_ema200': close_vs_ema200,
            'ema_ribbon': ema_ribbon,
            'macro_structure': structure_state,
            'reasons': reasons
        }

    @classmethod
    def evaluate_zone_screen(cls, df_intermediate: pd.DataFrame) -> Dict[str, Any]:
        """
        Screen 2: Institutional Key Zone Filter (1h).
        Verifies if price is resting in Golden Pocket (Fib 61.8%-78.6% OTE)
        or retesting an Unmitigated Fair Value Gap (FVG) / Order Block.
        """
        if df_intermediate is None or len(df_intermediate) < 15:
            return {
                'available': False,
                'in_key_zone': False,
                'zone_type': 'NO_ZONE',
                'in_bull_ote': False,
                'in_bear_ote': False,
                'in_bull_fvg': False,
                'in_bear_fvg': False,
                'reasons': ['Intermediate 1h data unavailable.']
            }

        df_ind = QuantitativeIndicators.add_all_indicators(df_intermediate)
        struct = SmartMoneyConcepts.analyze_market_structure(df_ind)
        fvgs = SmartMoneyConcepts.detect_fair_value_gaps(df_ind)
        obs = SmartMoneyConcepts.detect_order_blocks(df_ind)

        in_bull_ote = struct.get('in_bull_ote', False)
        in_bear_ote = struct.get('in_bear_ote', False)
        market_zone = struct.get('market_zone', 'EQUILIBRIUM')

        # Check unmitigated FVGs currently being tested
        active_bull_fvgs = [f for f in fvgs if f['type'] == 'BULLISH_FVG' and not f['mitigated'] and f.get('in_zone', False)]
        active_bear_fvgs = [f for f in fvgs if f['type'] == 'BEARISH_FVG' and not f['mitigated'] and f.get('in_zone', False)]
        in_bull_fvg = len(active_bull_fvgs) > 0
        in_bear_fvg = len(active_bear_fvgs) > 0

        # Check unmitigated Order Blocks
        in_bull_ob = any(o['type'] == 'BULLISH_OB' and o.get('in_zone', False) for o in obs)
        in_bear_ob = any(o['type'] == 'BEARISH_OB' and o.get('in_zone', False) for o in obs)

        zone_reasons = []
        zone_type = 'EQUILIBRIUM'
        in_key_zone = False

        if in_bull_ote or in_bull_fvg or in_bull_ob:
            in_key_zone = True
            zone_type = 'BULLISH_KEY_ZONE'
            tags = []
            if in_bull_ote: tags.append("Golden Pocket 61.8%-78.6% Fib OTE")
            if in_bull_fvg: tags.append("Unmitigated Bullish FVG")
            if in_bull_ob: tags.append("Bullish Order Block")
            zone_reasons.append(f"Screen 2 (Zone): Price in Institutional Buying Zone ({', '.join(tags)}).")
        elif in_bear_ote or in_bear_fvg or in_bear_ob:
            in_key_zone = True
            zone_type = 'BEARISH_KEY_ZONE'
            tags = []
            if in_bear_ote: tags.append("Golden Pocket 61.8%-78.6% Fib OTE")
            if in_bear_fvg: tags.append("Unmitigated Bearish FVG")
            if in_bear_ob: tags.append("Bearish Order Block")
            zone_reasons.append(f"Screen 2 (Zone): Price in Institutional Selling Zone ({', '.join(tags)}).")
        elif market_zone == 'DISCOUNT':
            zone_type = 'DISCOUNT_ZONE'
            zone_reasons.append("Screen 2 (Zone): Price in structural Discount range (<50% swing).")
        elif market_zone == 'PREMIUM':
            zone_type = 'PREMIUM_ZONE'
            zone_reasons.append("Screen 2 (Zone): Price in structural Premium range (>50% swing).")
        else:
            zone_reasons.append("Screen 2 (Zone): Price currently at Equilibrium. Awaiting key zone test.")

        return {
            'available': True,
            'in_key_zone': in_key_zone,
            'zone_type': zone_type,
            'in_bull_ote': in_bull_ote,
            'in_bear_ote': in_bear_ote,
            'in_bull_fvg': in_bull_fvg,
            'in_bear_fvg': in_bear_fvg,
            'in_bull_ob': in_bull_ob,
            'in_bear_ob': in_bear_ob,
            'market_zone': market_zone,
            'reasons': zone_reasons
        }

    @classmethod
    def evaluate_trigger_screen(cls, df_micro: pd.DataFrame) -> Dict[str, Any]:
        """
        Screen 3: Execution Trigger Filter (5m / 15m).
        Validates micro triggers:
          - Liquidity sweep (spring / upthrust)
          - CVD divergence / Z-score absorption
          - SuperTrend & HMA slope alignment
        """
        if df_micro is None or len(df_micro) < 15:
            return {
                'available': False,
                'trigger_fired': False,
                'trigger_direction': 'NONE',
                'supertrend_dir': 0,
                'hma_slope': 0.0,
                'reasons': ['Micro execution data unavailable.']
            }

        df_ind = QuantitativeIndicators.add_all_indicators(df_micro)
        last_row = df_ind.iloc[-1]
        struct = SmartMoneyConcepts.analyze_market_structure(df_ind)

        st_dir = int(last_row.get('supertrend_dir', 0))
        hma_slope = float(last_row.get('hma_slope', 0.0))
        cvd_z = float(last_row.get('cvd_zscore', 0.0))
        sweep = struct.get('liquidity_sweep', 'NONE')

        bull_trigger_signals = 0
        bear_trigger_signals = 0
        reasons = []

        # 1. SuperTrend micro alignment
        if st_dir == 1:
            bull_trigger_signals += 1
            reasons.append("Screen 3 (Trigger): Micro SuperTrend is Bullish (+1)")
        elif st_dir == -1:
            bear_trigger_signals += 1
            reasons.append("Screen 3 (Trigger): Micro SuperTrend is Bearish (+1)")

        # 2. HMA Slope alignment
        if hma_slope > 0:
            bull_trigger_signals += 1
        elif hma_slope < 0:
            bear_trigger_signals += 1

        # 3. Liquidity Sweep Trigger
        if sweep == 'BULLISH_SELL_SIDE_LIQUIDITY_SWEPT':
            bull_trigger_signals += 2
            reasons.append("Screen 3 (Trigger): Sell-side liquidity swept — Bullish Reversal Trigger (+2)")
        elif sweep == 'BEARISH_BUY_SIDE_LIQUIDITY_SWEPT':
            bear_trigger_signals += 2
            reasons.append("Screen 3 (Trigger): Buy-side liquidity swept — Bearish Reversal Trigger (+2)")

        # 4. CVD Delta Absorption
        if cvd_z > 1.2:
            bull_trigger_signals += 1
            reasons.append(f"Screen 3 (Trigger): CVD Absorption Buying (Z={cvd_z:+.1f}) (+1)")
        elif cvd_z < -1.2:
            bear_trigger_signals += 1
            reasons.append(f"Screen 3 (Trigger): CVD Absorption Selling (Z={cvd_z:+.1f}) (+1)")

        if bull_trigger_signals >= 2 and bull_trigger_signals > bear_trigger_signals:
            trigger_status = 'FIRED_BULLISH'
            trigger_fired = True
        elif bear_trigger_signals >= 2 and bear_trigger_signals > bull_trigger_signals:
            trigger_status = 'FIRED_BEARISH'
            trigger_fired = True
        else:
            trigger_status = 'WAITING_TRIGGER'
            trigger_fired = False
            reasons.append("Screen 3 (Trigger): Micro execution indicators mixed — waiting for trigger alignment.")

        return {
            'available': True,
            'trigger_fired': trigger_fired,
            'trigger_status': trigger_status,
            'supertrend_dir': st_dir,
            'hma_slope': round(hma_slope, 4),
            'cvd_zscore': round(cvd_z, 2),
            'liquidity_sweep': sweep,
            'bull_signals': bull_trigger_signals,
            'bear_signals': bear_trigger_signals,
            'reasons': reasons
        }

    @classmethod
    def evaluate_triple_screen(
        cls,
        df_macro: Optional[pd.DataFrame],
        df_intermediate: pd.DataFrame,
        df_micro: Optional[pd.DataFrame],
        proposed_action: str
    ) -> Dict[str, Any]:
        """
        Synthesizes the Triple-Screen framework and gates trading setups.
        """
        clean_action = proposed_action.upper().strip()
        is_buy = 'BUY' in clean_action
        is_sell = 'SELL' in clean_action

        screen1 = cls.evaluate_macro_screen(df_macro) if df_macro is not None else {'available': False, 'macro_bias': 'NEUTRAL', 'reasons': []}
        screen2 = cls.evaluate_zone_screen(df_intermediate)
        screen3 = cls.evaluate_trigger_screen(df_micro) if df_micro is not None else {'available': False, 'trigger_fired': False, 'trigger_status': 'NO_MICRO_DATA', 'reasons': []}

        macro_bias = screen1.get('macro_bias', 'NEUTRAL')
        zone_type = screen2.get('zone_type', 'NO_ZONE')
        trigger_status = screen3.get('trigger_status', 'NO_TRIGGER')

        all_reasons = []
        all_reasons.extend(screen1.get('reasons', []))
        all_reasons.extend(screen2.get('reasons', []))
        all_reasons.extend(screen3.get('reasons', []))

        # Check for FATAL MACRO CONFLICT:
        # e.g., Buying when Macro is strictly Bearish or below 200 EMA
        is_macro_conflict = False
        if is_buy and (macro_bias in ['BEARISH', 'MILD_BEARISH'] or screen1.get('close_vs_ema200') == 'BELOW_200_EMA'):
            is_macro_conflict = True
            all_reasons.append("Triple-Screen FATAL CONFLICT: Attempting BUY against Daily/4h Macro Bearish Downtrend below 200 EMA.")
        elif is_sell and (macro_bias in ['BULLISH', 'MILD_BULLISH'] or screen1.get('close_vs_ema200') == 'ABOVE_200_EMA'):
            is_macro_conflict = True
            all_reasons.append("Triple-Screen FATAL CONFLICT: Attempting SELL against Daily/4h Macro Bullish Uptrend above 200 EMA.")

        # Check Triple-Screen Alignment Score (0 to 3 screens aligned)
        aligned_screens = 0
        if is_buy:
            if screen1.get('available', False) and macro_bias in ['BULLISH', 'MILD_BULLISH']:
                aligned_screens += 1
            if screen2.get('available', False) and screen2.get('in_key_zone') and zone_type in ['BULLISH_KEY_ZONE', 'DISCOUNT_ZONE']:
                aligned_screens += 1
            if screen3.get('available', False) and trigger_status == 'FIRED_BULLISH':
                aligned_screens += 1
        elif is_sell:
            if screen1.get('available', False) and macro_bias in ['BEARISH', 'MILD_BEARISH']:
                aligned_screens += 1
            if screen2.get('available', False) and screen2.get('in_key_zone') and zone_type in ['BEARISH_KEY_ZONE', 'PREMIUM_ZONE']:
                aligned_screens += 1
            if screen3.get('available', False) and trigger_status == 'FIRED_BEARISH':
                aligned_screens += 1

        if is_macro_conflict:
            triple_status = 'MACRO_CONFLICT'
            alignment_grade = 'FATAL_CONFLICT'
        elif aligned_screens == 3:
            triple_status = 'TRIPLE_SCREEN_ALIGNED'
            alignment_grade = 'PERFECT_3_SCREEN_ALIGNMENT'
            all_reasons.append("Triple-Screen Alignment: PERFECT 3/3 SYNERGY (Macro Tide + 1h Key Zone + Micro Trigger).")
        elif aligned_screens == 2:
            triple_status = 'PARTIALLY_ALIGNED'
            alignment_grade = 'HIGH_PROBABILITY_2_SCREEN'
        else:
            triple_status = 'WEAK_ALIGNMENT'
            alignment_grade = 'INSUFFICIENT_CONFLUENCE'

        return {
            'triple_screen_status': triple_status,
            'alignment_grade': alignment_grade,
            'aligned_screens_count': aligned_screens,
            'is_macro_conflict': is_macro_conflict,
            'screen1_macro': screen1,
            'screen2_zone': screen2,
            'screen3_trigger': screen3,
            'reasons': all_reasons
        }
