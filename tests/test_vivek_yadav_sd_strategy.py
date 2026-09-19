"""
Unit Tests for Vivek Yadav Supply & Demand Strategy and Autonomous Multi-Strategy Dispatcher
=============================================================================================
"""

import unittest
import numpy as np
import pandas as pd
import sys
import os

# Ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.strategies.vivek_yadav_sd import VivekYadavSupplyDemandEngine
from src.engine.autonomous_manager import AutonomousTraderEngine


class TestVivekYadavStrategy(unittest.TestCase):

    def test_demand_zone_and_buy_trigger(self):
        """
        Build price action:
        1. Swing low red candle followed by 3 strong green candles (Demand Zone formed).
        2. Price pulls back into the Demand Zone.
        3. A green confirmation candle closes with a prominent bottom rejection wick (>= 35%).
        """
        data = []
        # Initial candles
        base = 100.0
        for i in range(6):
            data.append({'open': base, 'high': base + 1, 'low': base - 1, 'close': base + 0.2, 'volume': 100})
            base += 0.5

        # Red candle at swing low
        swing_low = 95.0
        data.append({'open': 98.0, 'high': 98.5, 'low': swing_low, 'close': 95.5, 'volume': 200})

        # 3 Strong green expansion candles
        data.append({'open': 95.8, 'high': 99.0, 'low': 95.5, 'close': 98.5, 'volume': 300})
        data.append({'open': 98.6, 'high': 101.0, 'low': 98.5, 'close': 100.5, 'volume': 350})
        data.append({'open': 100.6, 'high': 104.0, 'low': 100.5, 'close': 103.5, 'volume': 400})

        # Pullback towards demand zone [95.0 - 98.5]
        data.append({'open': 103.0, 'high': 103.2, 'low': 99.0, 'close': 99.5, 'volume': 150})
        data.append({'open': 99.2, 'high': 99.5, 'low': 97.0, 'close': 97.5, 'volume': 150})

        # Final candle: touches zone at 96.0, forms prominent lower rejection wick, closes GREEN at 98.0!
        candle_open = 96.8
        candle_low = 95.8  # touched inside demand zone
        candle_high = 98.2
        candle_close = 98.0  # green close!
        data.append({'open': candle_open, 'high': candle_high, 'low': candle_low, 'close': candle_close, 'volume': 500})

        df = pd.DataFrame(data)
        atr = 1.5
        res = VivekYadavSupplyDemandEngine.evaluate(df, atr=atr)

        self.assertIn('demand_zones', res)
        self.assertGreater(len(res['demand_zones']), 0, "Demand zone should be detected at swing bottom")
        
        # Verify trigger
        self.assertEqual(res['action'], 'BUY')
        self.assertEqual(res['status'], 'DEMAND_ENTRY_READY')

        setup = res['trade_setup']
        entry = setup['recommended_entry']
        sl = setup['stop_loss']
        risk_dist = abs(entry - sl)

        # Verify Golden Invariants & 1:2 R:R
        self.assertGreaterEqual(risk_dist, 1.50 * atr - 1e-5, "SL must be >= 1.50 * ATR")
        self.assertAlmostEqual(abs(setup['tp1'] - entry), 0.38 * atr, delta=0.05, msg="TP1 must match 0.38 * ATR")
        self.assertGreaterEqual(abs(setup['tp2'] - entry), 2.0 * risk_dist - 1e-5, "TP2 must provide at least 1:2 R:R")

    def test_supply_zone_and_sell_trigger(self):
        """
        Build price action:
        1. Swing high green candle followed by 3 strong red candles (Supply Zone formed).
        2. Price pulls back up into the Supply Zone.
        3. A red confirmation candle closes with a prominent top rejection wick (>= 35%).
        """
        data = []
        base = 100.0
        for i in range(6):
            data.append({'open': base, 'high': base + 1, 'low': base - 1, 'close': base - 0.2, 'volume': 100})
            base -= 0.5

        # Green candle at swing high
        swing_high = 110.0
        data.append({'open': 105.0, 'high': swing_high, 'low': 104.5, 'close': 108.5, 'volume': 200})

        # 3 Strong red drop candles
        data.append({'open': 108.0, 'high': 108.2, 'low': 103.5, 'close': 104.0, 'volume': 300})
        data.append({'open': 103.8, 'high': 104.0, 'low': 100.5, 'close': 101.0, 'volume': 350})
        data.append({'open': 100.8, 'high': 101.0, 'low': 97.5, 'close': 98.0, 'volume': 400})

        # Pullback up towards supply zone [104.5 - 110.0]
        data.append({'open': 98.5, 'high': 102.0, 'low': 98.0, 'close': 101.5, 'volume': 150})
        data.append({'open': 101.8, 'high': 105.0, 'low': 101.5, 'close': 104.5, 'volume': 150})

        # Final candle: touches zone at 107.5, forms prominent upper rejection wick, closes RED at 105.2!
        candle_open = 106.5
        candle_high = 108.0  # touched inside supply zone
        candle_low = 104.8
        candle_close = 105.2  # red close!
        data.append({'open': candle_open, 'high': candle_high, 'low': candle_low, 'close': candle_close, 'volume': 500})

        df = pd.DataFrame(data)
        atr = 1.5
        res = VivekYadavSupplyDemandEngine.evaluate(df, atr=atr)

        self.assertIn('supply_zones', res)
        self.assertGreater(len(res['supply_zones']), 0, "Supply zone should be detected at swing top")
        self.assertEqual(res['action'], 'SELL')
        self.assertEqual(res['status'], 'SUPPLY_ENTRY_READY')

        setup = res['trade_setup']
        entry = setup['recommended_entry']
        sl = setup['stop_loss']
        risk_dist = abs(entry - sl)
        self.assertGreaterEqual(risk_dist, 1.50 * atr - 1e-5, "SL must be >= 1.50 * ATR")
        self.assertGreaterEqual(abs(setup['tp2'] - entry), 2.0 * risk_dist - 1e-5, "TP2 must provide at least 1:2 R:R")

    def test_autonomous_strategy_settings_modes(self):
        """
        Verify settings loading and persistence for all 5 strategy modes:
        DEFAULT, TFP_LIQUIDATION_TRAP, VIVEK_YADAV_SD, BOTH_TFP, ALL_STRATEGIES
        """
        settings = AutonomousTraderEngine.load_settings()
        self.assertIn('active_strategy_mode', settings)

        for mode in ['DEFAULT', 'TFP_LIQUIDATION_TRAP', 'VIVEK_YADAV_SD', 'BOTH_TFP', 'ALL_STRATEGIES']:
            settings['active_strategy_mode'] = mode
            AutonomousTraderEngine.save_settings(settings)
            reloaded = AutonomousTraderEngine.load_settings()
            self.assertEqual(reloaded['active_strategy_mode'], mode)


if __name__ == '__main__':
    unittest.main()
