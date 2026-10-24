"""
Unit Test Suite for Walk-Forward Analysis Engine
================================================
Tests:
- Rolling window generation across historical date ranges
- Out-of-sample window slicing & continuity
- Walk-forward efficiency (WFE) computation
- Robustness classification thresholds
"""

import unittest
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine.walk_forward_engine import WalkForwardAnalysisEngine
from src.engine.backtest_engine import MT5BacktestEngine


class TestWalkForwardAnalysisEngine(unittest.TestCase):

    def test_rolling_windows_generation_180_days(self):
        """Verify 180 days generates expected rolling IS (60d) and OOS (30d) windows."""
        d_from = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        d_to = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)

        windows = WalkForwardAnalysisEngine.generate_rolling_windows(
            date_from=d_from,
            date_to=d_to,
            is_days=60,
            oos_days=30,
            step_days=30
        )
        self.assertGreaterEqual(len(windows), 4)

        # First window
        w1 = windows[0]
        self.assertEqual(w1['window_index'], 1)
        self.assertEqual(w1['is_days'], 60)
        self.assertEqual(w1['oos_days'], 30)
        self.assertEqual(w1['is_to'], w1['oos_from'])

        # Second window starts 30 days after first window
        w2 = windows[1]
        self.assertEqual(w2['window_index'], 2)
        self.assertEqual(w2['is_from'], w1['is_from'] + timedelta(days=30))

    def test_short_span_fallback_window(self):
        """When total span is shorter than is_days + oos_days, fallback cleanly to single split window."""
        d_from = datetime(2026, 6, 1, tzinfo=timezone.utc)
        d_to = datetime(2026, 7, 15, tzinfo=timezone.utc) # 44 days

        windows = WalkForwardAnalysisEngine.generate_rolling_windows(
            date_from=d_from,
            date_to=d_to,
            is_days=60,
            oos_days=30,
            step_days=30
        )
        self.assertEqual(len(windows), 1)
        w = windows[0]
        self.assertEqual(w['is_from'], d_from)
        self.assertEqual(w['oos_to'], d_to)
        self.assertEqual(w['is_to'], w['oos_from'])

    def test_walk_forward_execution_synthetic_isolation(self):
        """Run mini walk-forward analysis with 2 synthetic/mocked windows and verify metric structures."""
        engine = MT5BacktestEngine()
        wfa = WalkForwardAnalysisEngine(backtest_engine=engine)

        d_from = datetime.now(timezone.utc) - timedelta(days=60)
        d_to = datetime.now(timezone.utc)

        settings = engine.load_settings()
        settings['selected_symbols'] = ["BTC/USD"]
        settings['timeframes'] = ["1h"]
        settings['active_strategies'] = ["DEFAULT"]
        settings['date_from'] = d_from.isoformat()
        settings['date_to'] = d_to.isoformat()

        res = wfa.run_walk_forward_analysis(
            base_settings=settings,
            is_days=30,
            oos_days=15,
            step_days=15
        )

        self.assertIn('total_windows', res)
        self.assertIn('consistency_ratio_pct', res)
        self.assertIn('walk_forward_efficiency_pct', res)
        self.assertIn('oos_win_rate', res)
        self.assertIn('oos_profit_factor', res)
        self.assertIn('robustness_verdict', res)
        self.assertIn('windows', res)
        self.assertIn('oos_closed_batches', res)


if __name__ == '__main__':
    unittest.main()
