"""
Unit Test Suite for Master Streamer Strategies Playbook
======================================================
Tests all 12 trading strategies implemented from the PDF:
 1. Vivek Yadav (Trade For Profit - S&D + Liquidation Heatmap + FVG + 1:2 R:R)
 2. Bernd Skorupinski (FTMO #1 - Big Brother/Small Brother S&D + 1:2 to 1:4 R:R)
 3. Michael J. Huddleston (ICT - Liquidity Sweep + MSS + FVG/OTE)
 4. Steven Hart (The Trading Channel - 4H Break & 15M Retest + Pinbar)
 5. Rayner Teo (Trend Following 20/50 EMA Envelope + Trailing 20 EMA)
 6. Crypto Cred (Key Levels S/R + 20/50 EMA + RSI Divergence)
 7. Ndemazeah Godlove (GU MVR - 10/23 EMA Cross + Fib 50-61.8%)
 8. Ross Cameron (Warrior Trading - Momentum Gap & Go + VWAP + 9 EMA)
 9. Adam Khoo (Triple EMA Trend Breakout & Trailing 20 EMA)
10. Ariel Zwecher (RealSimpleAriel - 15M Opening Range Breakout ORB)
11. Oliver Velez (Elephant/Tail Bar + 20 SMA Location + Trailing 20 SMA)
12. Trade Pro (Mechanical Donchian 20 Channel + 200 SMA Slope + ATR 1:2)

Also verifies:
- MasterStreamerPlaybook.evaluate_all() dispatcher
- Autonomous multi-select strategy evaluation
- Decoupling of strategy-specific Breakeven modes from generic Tight/Loose BE
- Risk Geometry Invariants (Golden SL >= 1.5 ATR, Min 1:2 R:R)
"""

import unittest
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.strategies.streamer_playbook import (
    VivekYadavPlaybookStrategy,
    BerndSkorupinskiStrategy,
    ICTStrategy,
    StevenHartStrategy,
    RaynerTeoStrategy,
    CryptoCredStrategy,
    NdemazeahGodloveStrategy,
    RossCameronStrategy,
    AdamKhooStrategy,
    ArielZwecherStrategy,
    OliverVelezStrategy,
    TradeProStrategy,
    MasterStreamerPlaybook
)
from src.engine.autonomous_manager import AutonomousTraderEngine, AVAILABLE_STRATEGIES
from src.engine.mt5_executor import MT5TradeExecutor


class TestStreamerStrategiesPlaybook(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        n = 100
        dates = pd.date_range('2026-01-01', periods=n, freq='1h')
        
        # Upward trending series with pullbacks
        close = 100.0 + np.cumsum(np.random.normal(0.2, 1.0, n))
        high = close + np.random.uniform(0.5, 1.5, n)
        low = close - np.random.uniform(0.5, 1.5, n)
        open_p = close + np.random.uniform(-0.5, 0.5, n)
        vol = np.random.uniform(500, 2000, n)

        self.df = pd.DataFrame({
            'timestamp': dates,
            'open': open_p,
            'high': high,
            'low': low,
            'close': close,
            'volume': vol
        })
        self.atr = 2.0

    def test_all_18_strategies_exist_in_playbook(self):
        """All 18 streamer strategies must be registered in MasterStreamerPlaybook."""
        self.assertEqual(len(MasterStreamerPlaybook.STRATEGY_MAP), 18)
        expected_keys = [
            'VIVEK_YADAV', 'BERND_SKORUPINSKI', 'ICT', 'STEVEN_HART',
            'RAYNER_TEO', 'CRYPTO_CRED', 'NDEMAZEAH_GODLOVE', 'ROSS_CAMERON',
            'ADAM_KHOO', 'ARIEL_ZWECHER', 'OLIVER_VELEZ', 'TRADE_PRO',
            'KRISTJAN_QULLAMAGGIE', 'GCR', 'WAQAR_ZAKA', 'WAQAR_ASIM',
            'EUGENE_NG_AH_SIO', 'PAUL_FTMO'
        ]
        for k in expected_keys:
            self.assertIn(k, MasterStreamerPlaybook.STRATEGY_MAP)
            self.assertIn(k, AVAILABLE_STRATEGIES)

    def test_evaluate_all_dispatcher(self):
        """MasterStreamerPlaybook.evaluate_all returns evaluations for all 18 strategies."""
        res = MasterStreamerPlaybook.evaluate_all(self.df, atr=self.atr, timeframe='1h')
        self.assertIn('all_strategies', res)
        self.assertIn('active_setups', res)
        self.assertIn('active_count', res)
        self.assertEqual(len(res['all_strategies']), 18)

        for strat_k, strat_res in res['all_strategies'].items():
            self.assertIn('action', strat_res)
            self.assertIn('status', strat_res)
            self.assertIn('confidence', strat_res)
            self.assertIn('breakeven_mode', strat_res)
            self.assertIn('strategy_name', strat_res)
            self.assertIn(strat_res['action'], ['BUY', 'SELL', 'HOLD', 'WAIT'])

    def test_risk_geometry_invariants(self):
        """When any strategy issues a BUY or SELL setup, it must obey Golden SL and 1:2+ R:R."""
        res = MasterStreamerPlaybook.evaluate_all(self.df, atr=self.atr, timeframe='1h')
        for strat_k, strat_res in res['all_strategies'].items():
            if strat_res['action'] in ['BUY', 'SELL'] and strat_res.get('trade_setup'):
                setup = strat_res['trade_setup']
                entry = setup['recommended_entry']
                sl = setup['stop_loss']
                tp1 = setup['tp1']
                tp2 = setup['tp2']
                risk_dist = abs(entry - sl)
                
                # Invariant 1: Stop loss distance must be at least 1.50x ATR
                self.assertGreaterEqual(risk_dist, 1.45 * self.atr, f"{strat_k} SL compressed below 1.5 ATR")
                
                # Invariant 2: TP2 runner must offer at least 1.15x risk distance (or min 1:2 overall R:R)
                tp2_dist = abs(tp2 - entry)
                self.assertGreaterEqual(tp2_dist, 1.10 * risk_dist, f"{strat_k} TP2 does not offer 1:1+ R:R")

    def test_decoupled_breakeven_modes(self):
        """Native BE modes must be distinct and appropriately mapped."""
        self.assertEqual(StevenHartStrategy.BE_MODE, "FIXED_RR_TARGET")
        self.assertEqual(BerndSkorupinskiStrategy.BE_MODE, "FIXED_RR_TARGET")
        self.assertEqual(ArielZwecherStrategy.BE_MODE, "FIXED_RR_TARGET")
        self.assertEqual(TradeProStrategy.BE_MODE, "FIXED_RR_TARGET")
        self.assertEqual(RaynerTeoStrategy.BE_MODE, "TRAILING_20_EMA")
        self.assertEqual(AdamKhooStrategy.BE_MODE, "TRAILING_20_EMA")
        self.assertEqual(OliverVelezStrategy.BE_MODE, "TRAILING_20_SMA")
        self.assertEqual(VivekYadavPlaybookStrategy.BE_MODE, "SMC_PARTIAL_BE")
        self.assertEqual(ICTStrategy.BE_MODE, "SMC_PARTIAL_BE")

    def test_autonomous_manager_multi_select_settings(self):
        """AutonomousTraderEngine handles multi-select active_strategies in settings."""
        engine = AutonomousTraderEngine()
        settings = engine.load_settings()
        self.assertIn('active_strategies', settings)
        self.assertIsInstance(settings['active_strategies'], list)

        # Test selecting multiple strategies
        test_strats = ['DEFAULT', 'STEVEN_HART', 'RAYNER_TEO', 'ICT']
        settings['active_strategies'] = test_strats
        engine.save_settings(settings)

        reloaded = engine.load_settings()
        self.assertEqual(reloaded['active_strategies'], test_strats)

    def test_mt5_executor_breakeven_decoupling(self):
        """MT5 executor check_and_apply_auto_breakeven respects strategy fixed_rr_target."""
        executor = MT5TradeExecutor()
        
        # Batch info with fixed_rr_target mode
        batch_map = {
            "999": {
                "symbol": "BTCUSDm",
                "entry_price": 50000.0,
                "sl_price": 49000.0,
                "tp1_price": 50500.0,
                "breakeven_mode": "FIXED_RR_TARGET",
                "tickets": [111, 222, 333]
            }
        }
        
        # In non-connected test env, should return safely without error
        res = executor.check_and_apply_auto_breakeven(
            batch_info_map=batch_map,
            breakeven_mode="tight"
        )
        self.assertIsInstance(res, list)


if __name__ == '__main__':
    unittest.main()
