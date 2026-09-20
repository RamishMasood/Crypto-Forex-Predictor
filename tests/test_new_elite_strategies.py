"""
Unit Test Suite for 6 New Elite Trading Strategies
===================================================
Playbook PDF Strategies:
 1. Kristjan Qullamaggie (High ADR% + 10/20 EMA + 50 SMA + Vol Contraction ORB)
 2. GCR (@GiganticRebirth - Behavioral Sentiment & Counter-Cyclical Shorting)
 3. Waqar Zaka (Off-Exchange Capital Reserve & ATR Buffer Model)
 4. Waqar Asim (Forex 1M Supply & Demand Inducement Scalping Model)
 5. Eugene Ng Ah Sio (Relative Value Delta-Neutral Spreads)
 6. Paul (Record FTMO Leaderboard Trader - Macro-Fundamental & Divergence)

Tests:
 - Registration in MasterStreamerPlaybook (18 streamers total)
 - Registration in AVAILABLE_STRATEGIES (19 total with DEFAULT)
 - Evaluation with synthetic OHLCV data
 - Strategy-specific killzones & session execution windows
 - Leaderboard stats mapping and default profiles
 - Native breakeven mode definitions
"""

import unittest
import os
import sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.strategies.streamer_playbook import (
    MasterStreamerPlaybook,
    KristjanQullamaggieStrategy,
    GCRStrategy,
    WaqarZakaStrategy,
    WaqarAsimStrategy,
    EugeneNgAhSioStrategy,
    PaulFTMOStrategy
)
from src.engine.autonomous_manager import AutonomousTraderEngine, AVAILABLE_STRATEGIES
from src.engine.session_manager import SessionManager


class TestNewEliteStrategies(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        n = 120
        dates = pd.date_range('2026-09-01', periods=n, freq='15min')
        base = 60000.0 + np.cumsum(np.random.normal(5, 30, n))
        
        self.df = pd.DataFrame({
            'timestamp': dates,
            'open': base,
            'high': base + 50.0,
            'low': base - 50.0,
            'close': base + 10.0,
            'volume': [2500.0] * n
        })
        self.atr = 150.0

    def test_all_19_strategies_registered_in_available_strategies(self):
        """All 19 strategies (DEFAULT + 18 Streamers) must be registered."""
        self.assertEqual(len(AVAILABLE_STRATEGIES), 19)
        new_strats = [
            'KRISTJAN_QULLAMAGGIE',
            'GCR',
            'WAQAR_ZAKA',
            'WAQAR_ASIM',
            'EUGENE_NG_AH_SIO',
            'PAUL_FTMO'
        ]
        for s in new_strats:
            self.assertIn(s, AVAILABLE_STRATEGIES)

    def test_all_18_streamers_in_playbook_map(self):
        """MasterStreamerPlaybook.STRATEGY_MAP must contain all 18 streamers."""
        self.assertEqual(len(MasterStreamerPlaybook.STRATEGY_MAP), 18)
        new_strats = [
            'KRISTJAN_QULLAMAGGIE',
            'GCR',
            'WAQAR_ZAKA',
            'WAQAR_ASIM',
            'EUGENE_NG_AH_SIO',
            'PAUL_FTMO'
        ]
        for s in new_strats:
            self.assertIn(s, MasterStreamerPlaybook.STRATEGY_MAP)

    def test_evaluate_all_evaluates_18_streamers(self):
        """MasterStreamerPlaybook.evaluate_all evaluates all 18 streamers."""
        res = MasterStreamerPlaybook.evaluate_all(self.df, atr=self.atr, timeframe='15m')
        self.assertIn('all_strategies', res)
        strats = res['all_strategies']
        self.assertEqual(len(strats), 18)
        
        for k in ['KRISTJAN_QULLAMAGGIE', 'GCR', 'WAQAR_ZAKA', 'WAQAR_ASIM', 'EUGENE_NG_AH_SIO', 'PAUL_FTMO']:
            self.assertIn(k, strats)
            self.assertIn('action', strats[k])
            self.assertIn('confidence', strats[k])
            self.assertIn('strategy_name', strats[k])
            self.assertIn('breakeven_mode', strats[k])

    def test_qullamaggie_strategy_evaluation(self):
        """Test Kristjan Qullamaggie High ADR% Momentum Expansion evaluation."""
        res = KristjanQullamaggieStrategy.evaluate(self.df, atr=self.atr, timeframe='1h')
        self.assertIn(res['action'], ['BUY', 'SELL', 'WAIT', 'HOLD'])
        self.assertEqual(res['breakeven_mode'].lower(), 'qullamaggie_ema_trail')
        self.assertIn('ADR', str(res['reasons']))

    def test_gcr_sentiment_counter_shorting_evaluation(self):
        """Test GCR sentiment counter-cyclical shorting evaluation."""
        res = GCRStrategy.evaluate(self.df, atr=self.atr, timeframe='4h')
        self.assertIn(res['action'], ['BUY', 'SELL', 'WAIT', 'HOLD'])
        self.assertEqual(res['breakeven_mode'].lower(), 'gcr_cycle_be')
        self.assertTrue(any('retail' in r.lower() or 'gcr' in r.lower() for r in res['reasons']))

    def test_waqar_zaka_atr_buffer_evaluation(self):
        """Test Waqar Zaka off-exchange reserve & ATR buffer evaluation."""
        res = WaqarZakaStrategy.evaluate(self.df, atr=self.atr, timeframe='1h')
        self.assertIn(res['action'], ['BUY', 'SELL', 'WAIT', 'HOLD'])
        self.assertEqual(res['breakeven_mode'].lower(), 'atr_buffer_be')
        self.assertTrue(any('waqar' in r.lower() or 'atr buffer' in r.lower() for r in res['reasons']))

    def test_waqar_asim_scalp_evaluation(self):
        """Test Waqar Asim 1M S&D inducement scalping evaluation."""
        res = WaqarAsimStrategy.evaluate(self.df, atr=self.atr, timeframe='1m')
        self.assertIn(res['action'], ['BUY', 'SELL', 'WAIT', 'HOLD'])
        self.assertEqual(res['breakeven_mode'].lower(), 'waqar_asim_instant_be')
        self.assertIn('inducement', str(res['reasons']).lower())

    def test_eugene_ng_delta_neutral_spread_evaluation(self):
        """Test Eugene Ng Ah Sio relative value spread evaluation."""
        res = EugeneNgAhSioStrategy.evaluate(self.df, atr=self.atr, timeframe='1h')
        self.assertIn(res['action'], ['BUY', 'SELL', 'WAIT', 'HOLD'])
        self.assertEqual(res['breakeven_mode'].lower(), 'delta_neutral_spread_be')
        self.assertIn('relative', str(res['reasons']).lower())

    def test_paul_ftmo_divergence_evaluation(self):
        """Test Paul FTMO macro & divergence breakout evaluation."""
        res = PaulFTMOStrategy.evaluate(self.df, atr=self.atr, timeframe='15m')
        self.assertIn(res['action'], ['BUY', 'SELL', 'WAIT', 'HOLD'])
        self.assertEqual(res['breakeven_mode'].lower(), 'fib_extension_be')
        self.assertIn('divergence', str(res['reasons']).lower())

    def test_session_manager_killzone_rules_for_new_strategies(self):
        """Validate killzones from Playbook PDF: Waqar Asim, Paul FTMO, Qullamaggie, and 24/7 Crypto."""
        # 1. Waqar Asim: Active 07:00-09:00 UTC (8-9 AM London) & 13:00-15:00 UTC (2-3 PM London)
        dt_asim_active = datetime(2026, 9, 15, 8, 30, tzinfo=timezone.utc)
        dt_asim_inactive = datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc)
        
        ok_asim_1, _ = SessionManager.is_strategy_session_allowed('WAQAR_ASIM', dt=dt_asim_active)
        self.assertTrue(ok_asim_1)
        ok_asim_2, _ = SessionManager.is_strategy_session_allowed('WAQAR_ASIM', dt=dt_asim_inactive)
        self.assertFalse(ok_asim_2)

        # 2. Paul FTMO: Active 07:00-11:00 UTC (London Open Asian Breakout)
        dt_paul_active = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)
        dt_paul_inactive = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)
        
        ok_paul_1, _ = SessionManager.is_strategy_session_allowed('PAUL_FTMO', dt=dt_paul_active)
        self.assertTrue(ok_paul_1)
        ok_paul_2, _ = SessionManager.is_strategy_session_allowed('PAUL_FTMO', dt=dt_paul_inactive)
        self.assertFalse(ok_paul_2)

        # 3. GCR, Waqar Zaka, Eugene: Always active (24/7 crypto)
        dt_midnight = datetime(2026, 9, 15, 23, 30, tzinfo=timezone.utc)
        ok_gcr, _ = SessionManager.is_strategy_session_allowed('GCR', dt=dt_midnight, asset_type='crypto')
        self.assertTrue(ok_gcr)
        ok_zaka, _ = SessionManager.is_strategy_session_allowed('WAQAR_ZAKA', dt=dt_midnight, asset_type='crypto')
        self.assertTrue(ok_zaka)
        ok_eugene, _ = SessionManager.is_strategy_session_allowed('EUGENE_NG_AH_SIO', dt=dt_midnight, asset_type='crypto')
        self.assertTrue(ok_eugene)

    def test_leaderboard_contains_profiles_for_all_19_strategies(self):
        """Leaderboard computation must initialize and profile all 19 strategies."""
        lb = AutonomousTraderEngine.compute_strategy_leaderboard()
        self.assertEqual(len(lb), 19)
        
        keys_in_lb = [x['strategy_key'] for x in lb]
        for s in ['KRISTJAN_QULLAMAGGIE', 'GCR', 'WAQAR_ZAKA', 'WAQAR_ASIM', 'EUGENE_NG_AH_SIO', 'PAUL_FTMO']:
            self.assertIn(s, keys_in_lb)
            item = next(x for x in lb if x['strategy_key'] == s)
            self.assertIn('best_timeframes', item)
            self.assertIn('best_pairs', item)
            self.assertTrue(len(item['best_timeframes']) > 0)
            self.assertTrue(len(item['best_pairs']) > 0)


if __name__ == '__main__':
    unittest.main()
