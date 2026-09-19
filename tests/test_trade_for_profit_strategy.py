"""
Unit Test Suite for Trade For Profit (SMC Liquidation Heatmap & Trap Trading Engine)
===================================================================================
Tests:
- Liquidity Heatmap generation (EQH, EQL, 50x leverage bands)
- Bear Trap detection (Sell-side sweep + wick absorption)
- Bull Trap detection (Buy-side sweep + wick absorption)
- Strict compliance with Golden SL Geometry (>= 1.50x ATR, base 1.80x ATR)
- Precision TP1 Scalp Bank (0.38x ATR) and TP2 Runner (>= 1.15x risk distance)
- ConfluenceEngine integration
"""

import unittest
import numpy as np
import pandas as pd
import sys
import os

# Ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.strategies.trade_for_profit_trap import (
    LiquidityHeatmapEngine,
    TrapSweepDetector,
    TradeForProfitEngine
)
from src.engine.confluence import ConfluenceEngine


class TestTradeForProfitStrategy(unittest.TestCase):

    def setUp(self):
        np.random.seed(123)
        n = 60
        dates = pd.date_range('2026-01-01', periods=n, freq='1h')
        base_price = 100.0
        # Create a range-bound market structure
        close = base_price + np.sin(np.linspace(0, 10, n)) * 4.0
        high = close + np.random.uniform(0.5, 1.5, n)
        low = close - np.random.uniform(0.5, 1.5, n)
        open_p = close + np.random.uniform(-0.5, 0.5, n)
        vol = np.random.uniform(100, 500, n)

        self.df = pd.DataFrame({
            'timestamp': dates,
            'open': open_p,
            'high': high,
            'low': low,
            'close': close,
            'volume': vol
        })

    def test_heatmap_generation(self):
        heatmap = LiquidityHeatmapEngine.build_liquidation_heatmap(self.df)
        self.assertIn('upper_pools', heatmap)
        self.assertIn('lower_pools', heatmap)
        self.assertIn('dominant_magnet', heatmap)
        # Should have detected some pools
        total_pools = len(heatmap['upper_pools']) + len(heatmap['lower_pools'])
        self.assertGreater(total_pools, 0, "Heatmap should generate upper or lower liquidity pools")

    def test_bullish_bear_trap_detection(self):
        """
        Create a scenario where price sweeps below a lower swing low with a huge bottom wick
        and closes firmly back above it (Sell-Side Liquidity Swept / Bear Trap).
        """
        df_trap = self.df.copy()
        # Find the lowest low in recent bars
        recent_low = float(df_trap['low'].iloc[-10:-1].min())
        
        # Craft the final candle:
        # Opens above recent_low, wicks deeply below recent_low, closes near high of candle
        candle_open = recent_low + 0.5
        candle_low = recent_low - 2.0  # deep sweep below swing low
        candle_high = recent_low + 1.5
        candle_close = recent_low + 1.2 # strong close back inside!
        
        df_trap.iloc[-1, df_trap.columns.get_loc('open')] = candle_open
        df_trap.iloc[-1, df_trap.columns.get_loc('high')] = candle_high
        df_trap.iloc[-1, df_trap.columns.get_loc('low')] = candle_low
        df_trap.iloc[-1, df_trap.columns.get_loc('close')] = candle_close
        df_trap.iloc[-1, df_trap.columns.get_loc('volume')] = 2000.0  # surge

        heatmap = LiquidityHeatmapEngine.build_liquidation_heatmap(df_trap)
        # Ensure a lower pool exists at or near recent_low
        heatmap['lower_pools'].append({
            'price': recent_low,
            'distance_pct': 1.0,
            'density': 'HIGH',
            'type': 'SWING_LOW_SSL',
            'source': 'Swing Pivot Low'
        })

        atr = 1.5
        trap_result = TrapSweepDetector.detect_trap_and_sweep(df_trap, heatmap, atr)
        self.assertTrue(trap_result['trap_detected'], "Bear Trap should be detected")
        self.assertEqual(trap_result['trap_type'], 'BULLISH_BEAR_TRAP')
        self.assertEqual(trap_result['bias'], 'BUY')
        self.assertGreaterEqual(trap_result['rejection_wick_ratio'], 0.35)

    def test_bearish_bull_trap_detection(self):
        """
        Create a scenario where price sweeps above an upper swing high with a huge top wick
        and closes firmly back below it (Buy-Side Liquidity Swept / Bull Trap).
        """
        df_trap = self.df.copy()
        recent_high = float(df_trap['high'].iloc[-10:-1].max())

        candle_open = recent_high - 0.5
        candle_high = recent_high + 2.5  # deep sweep above swing high
        candle_low = recent_high - 1.5
        candle_close = recent_high - 1.2 # strong close back inside!

        df_trap.iloc[-1, df_trap.columns.get_loc('open')] = candle_open
        df_trap.iloc[-1, df_trap.columns.get_loc('high')] = candle_high
        df_trap.iloc[-1, df_trap.columns.get_loc('low')] = candle_low
        df_trap.iloc[-1, df_trap.columns.get_loc('close')] = candle_close
        df_trap.iloc[-1, df_trap.columns.get_loc('volume')] = 2500.0

        heatmap = LiquidityHeatmapEngine.build_liquidation_heatmap(df_trap)
        heatmap['upper_pools'].append({
            'price': recent_high,
            'distance_pct': 1.0,
            'density': 'HIGH',
            'type': 'SWING_HIGH_BSL',
            'source': 'Swing Pivot High'
        })

        atr = 1.5
        trap_result = TrapSweepDetector.detect_trap_and_sweep(df_trap, heatmap, atr)
        self.assertTrue(trap_result['trap_detected'], "Bull Trap should be detected")
        self.assertEqual(trap_result['trap_type'], 'BEARISH_BULL_TRAP')
        self.assertEqual(trap_result['bias'], 'SELL')
        self.assertGreaterEqual(trap_result['rejection_wick_ratio'], 0.35)

    def test_golden_risk_and_target_geometry_invariants(self):
        """
        Test that TradeForProfitEngine adheres strictly to the Golden Invariants:
        1. Base SL is >= 1.50 * ATR (Base 1.80 * ATR with swing buffer)
        2. TP1 is 0.38 * ATR
        3. TP2 is >= 1.15 * risk_distance
        4. TP3 is 2.20 * risk_distance
        """
        df_trap = self.df.copy()
        recent_low = float(df_trap['low'].iloc[-10:-1].min())
        
        df_trap.iloc[-1, df_trap.columns.get_loc('open')] = recent_low + 0.2
        df_trap.iloc[-1, df_trap.columns.get_loc('high')] = recent_low + 1.0
        df_trap.iloc[-1, df_trap.columns.get_loc('low')] = recent_low - 1.5
        df_trap.iloc[-1, df_trap.columns.get_loc('close')] = recent_low + 0.8
        df_trap.iloc[-1, df_trap.columns.get_loc('volume')] = 3000.0

        atr = 2.0
        result = TradeForProfitEngine.evaluate(df_trap, atr=atr)

        if result['setup_grade'] in ['A+_SUPER_CONFLUENCE', 'A_HIGH_CONVICTION', 'B_DEVELOPING']:
            setup = result['trade_setup']
            entry = setup['recommended_entry']
            sl = setup['stop_loss']
            tp1 = setup['tp1']
            tp2 = setup['tp2']
            tp3 = setup['tp3']

            risk_dist = abs(entry - sl)
            # Invariant 1: SL distance >= 1.50 * ATR
            self.assertGreaterEqual(risk_dist, 1.50 * atr - 1e-5, f"SL distance ({risk_dist}) must be >= 1.50 * ATR ({1.50 * atr})")

            # Invariant 2: TP1 distance is ~0.38 * ATR
            tp1_dist = abs(tp1 - entry)
            self.assertAlmostEqual(tp1_dist, 0.38 * atr, delta=0.05, msg="TP1 distance must match 0.38 * ATR")

            # Invariant 3: TP2 distance >= 1.15 * risk_distance
            tp2_dist = abs(tp2 - entry)
            self.assertGreaterEqual(tp2_dist, 1.15 * risk_dist - 1e-5, "TP2 must provide at least 1:1.15 R:R")

            # Invariant 4: TP3 distance == 2.20 * risk_distance
            tp3_dist = abs(tp3 - entry)
            self.assertAlmostEqual(tp3_dist, 2.20 * risk_dist, delta=0.1, msg="TP3 must equal 2.20 * risk_distance")

    def test_confluence_integration(self):
        """
        Verify that passing trade_for_profit into ConfluenceEngine updates score and layer_scores.
        """
        mock_tfp_bull = {
            'setup_grade': 'A+_SUPER_CONFLUENCE',
            'trap_details': {
                'trap_detected': True,
                'bias': 'BUY',
                'description': 'Sell-Side Swept (Bear Trap)',
                'swept_pool': {'source': '50x Long Leverage Cluster'}
            }
        }

        # Indicators row with neutral indicators
        df_ind = pd.DataFrame([{
            'supertrend_dir': 0, 'ema_trend': 0, 'macd_hist': 0.0, 'macd_hist_slope': 0.0,
            'kaufman_er': 0.30, 'adx_14': 20.0, 'rsi_14': 50.0, 'stoch_rsi_k': 50.0,
            'stoch_rsi_d': 50.0, 'cmo_14': 0.0, 'bb_squeeze': False, 'cvd_zscore': 0.0
        }])

        smc_data = {'structure': {'structure': 'NEUTRAL', 'market_zone': 'EQUILIBRIUM'}, 'fvgs': []}
        ml_prediction = {'p_bullish': 0.33, 'p_bearish': 0.33, 'confidence_pct': 0.0}
        orderbook = {'available': False}

        # Baseline evaluation without TFP
        res_base = ConfluenceEngine.evaluate(
            df_indicators=df_ind, smc_data=smc_data, ml_prediction=ml_prediction,
            orderbook_metrics=orderbook, trade_for_profit=None
        )

        # Evaluation with TFP Bullish Trap
        res_tfp = ConfluenceEngine.evaluate(
            df_indicators=df_ind, smc_data=smc_data, ml_prediction=ml_prediction,
            orderbook_metrics=orderbook, trade_for_profit=mock_tfp_bull
        )

        self.assertGreater(res_tfp['confluence_score'], res_base['confluence_score'], "TFP Bullish trap must boost confluence score")
        self.assertIn('trade_for_profit_trap', res_tfp['layer_scores'])
        self.assertGreater(res_tfp['layer_scores']['trade_for_profit_trap'], 0.0)


if __name__ == '__main__':
    unittest.main()
