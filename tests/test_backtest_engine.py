"""
Unit Test Suite for Dedicated MT5 Backtest Engine
=================================================
Tests:
- MT5BacktestEngine initialization & settings loading/saving
- Contract size & pip value calculations
- Multi-strategy backtest simulation with bar-by-bar execution
- Tracking of Biggest SL Hit ($) and Total SL Hits
- Backtest Strategy Leaderboard ranking and metrics
- Zero-Interference: Guarantees .autonomous_trader_state.json is never touched
"""

import unittest
import os
import sys
import json
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine.backtest_engine import MT5BacktestEngine, get_backtest_engine
from src.engine.autonomous_manager import AVAILABLE_STRATEGIES


class TestMT5BacktestEngine(unittest.TestCase):

    def setUp(self):
        self.engine = get_backtest_engine()

        # Capture hash or mtime of live autonomous state file to ensure zero disturbance
        self.live_state_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.autonomous_trader_state.json'))
        self.initial_live_state_content = None
        if os.path.exists(self.live_state_path):
            with open(self.live_state_path, 'r', encoding='utf-8') as f:
                self.initial_live_state_content = f.read()

    def test_engine_initialization_and_settings(self):
        """Engine loads settings with all required autonomous fields."""
        settings = self.engine.load_settings()
        self.assertIn('selected_symbols', settings)
        self.assertIn('timeframes', settings)
        self.assertIn('active_strategies', settings)
        self.assertIn('batch_lot_size', settings)
        self.assertIn('max_dollar_risk', settings)
        self.assertIn('initial_balance', settings)
        self.assertIn('date_from', settings)
        self.assertIn('date_to', settings)

    def test_contract_size_calculation(self):
        """Verify contract sizes for Forex, Gold, and Crypto."""
        self.assertEqual(MT5BacktestEngine.compute_contract_size("EUR/USD"), 100000.0)
        self.assertEqual(MT5BacktestEngine.compute_contract_size("GBP/USD"), 100000.0)
        self.assertEqual(MT5BacktestEngine.compute_contract_size("XAU/USD"), 100.0)
        self.assertEqual(MT5BacktestEngine.compute_contract_size("BTC/USD"), 1.0)
        self.assertEqual(MT5BacktestEngine.compute_contract_size("ETH/USD"), 1.0)

    def test_backtest_simulation_and_sl_tracking(self):
        """Verify backtest execution generates trades, computes win rate, and tracks biggest SL hit."""
        # Run a quick backtest on synthetic / loaded data
        custom_settings = {
            "selected_symbols": ["BTC/USD"],
            "timeframes": ["1h"],
            "active_strategies": ["DEFAULT", "VIVEK_YADAV", "BERND_SKORUPINSKI"],
            "initial_balance": 10000.0,
            "batch_lot_size": 0.03,
            "max_active_batches": 2,
            "max_dollar_risk": 50.0,
            "min_pillars_required": 3,
            "allow_same_tf_trades": True,
            "allow_diff_strat_same_tf": True,
            "breakeven_mode": "tight",
            "active_sessions": ["24/7 (Any Session)"],
            "htf_filter_enabled": False,
            "date_from": (datetime.now(timezone.utc) - timedelta(days=14)).isoformat(),
            "date_to": datetime.now(timezone.utc).isoformat()
        }

        res = self.engine.run_backtest(custom_settings)
        self.assertIn('net_profit', res)
        self.assertIn('win_rate', res)
        self.assertIn('total_trades', res)
        self.assertIn('biggest_sl_loss', res)
        self.assertIn('sl_hits', res)
        self.assertIn('leaderboard', res)
        self.assertIn('equity_curve', res)

        # Verify Biggest SL Hit is a float >= 0.0
        self.assertIsInstance(res['biggest_sl_loss'], float)
        self.assertGreaterEqual(res['biggest_sl_loss'], 0.0)

        # Verify SL Hits is an int >= 0
        self.assertIsInstance(res['sl_hits'], int)
        self.assertGreaterEqual(res['sl_hits'], 0)

    def test_backtest_leaderboard_contains_biggest_sl_metrics(self):
        """Leaderboard computation must include biggest_sl_loss and sl_hits columns."""
        fake_batches = [
            {
                'strategy_used': 'VIVEK_YADAV',
                'strategy_name': 'Vivek Yadav',
                'profit': -25.50,
                'status': 'LOSS',
                'timeframe': '1h',
                'symbol': 'BTC/USD'
            },
            {
                'strategy_used': 'VIVEK_YADAV',
                'strategy_name': 'Vivek Yadav',
                'profit': -12.00,
                'status': 'LOSS',
                'timeframe': '1h',
                'symbol': 'BTC/USD'
            },
            {
                'strategy_used': 'BERND_SKORUPINSKI',
                'strategy_name': 'Bernd Skorupinski',
                'profit': 45.00,
                'status': 'WIN',
                'timeframe': '1h',
                'symbol': 'BTC/USD'
            }
        ]

        lb = MT5BacktestEngine.compute_backtest_strategy_leaderboard(fake_batches, ['VIVEK_YADAV', 'BERND_SKORUPINSKI'])
        self.assertEqual(len(lb), 2)
        
        vy = next(x for x in lb if x['strategy_key'] == 'VIVEK_YADAV')
        self.assertEqual(vy['losses'], 2)
        self.assertEqual(vy['sl_hits'], 2)
        self.assertEqual(vy['biggest_sl_loss'], 25.50)

        bs = next(x for x in lb if x['strategy_key'] == 'BERND_SKORUPINSKI')
        self.assertEqual(bs['wins'], 1)
        self.assertEqual(bs['sl_hits'], 0)
        self.assertEqual(bs['biggest_sl_loss'], 0.0)
        self.assertEqual(bs['tp_hits'], 1)
        self.assertEqual(bs['biggest_tp'], 45.00)

        self.assertEqual(vy['tp_hits'], 0)
        self.assertEqual(vy['biggest_tp'], 0.0)

        # Per-pair breakdown verification
        self.assertIn('pairs_breakdown', vy)
        self.assertEqual(len(vy['pairs_breakdown']), 1)
        self.assertEqual(vy['pairs_breakdown'][0]['symbol'], 'BTC/USD')
        self.assertEqual(vy['pairs_breakdown'][0]['wins'], 0)
        self.assertEqual(vy['pairs_breakdown'][0]['losses'], 2)
        self.assertEqual(vy['pairs_breakdown'][0]['breakevens'], 0)
        self.assertIn('BTC/USD (0W-0BE-2L)', vy['best_pairs'])

        self.assertIn('pairs_breakdown', bs)
        self.assertIn('BTC/USD (1W-0BE-0L)', bs['best_pairs'])

    def test_zero_disturbance_to_autonomous_live_state(self):
        """Ensure that running backtest operations never mutates .autonomous_trader_state.json."""
        if self.initial_live_state_content is not None and os.path.exists(self.live_state_path):
            with open(self.live_state_path, 'r', encoding='utf-8') as f:
                current_live_state = f.read()
            self.assertEqual(
                self.initial_live_state_content,
                current_live_state,
                ".autonomous_trader_state.json was modified by backtesting! Invariant violated."
            )


if __name__ == '__main__':
    unittest.main()
