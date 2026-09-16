import unittest
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine.session_manager import SessionManager
from src.engine.htf_confluence import HTFConfluenceChecker
from src.engine.autonomous_manager import AutonomousTraderEngine

class TestSessionAndHTF(unittest.TestCase):

    def test_session_manager_windows(self):
        # 08:00 UTC -> London is active (07:00 - 16:00)
        dt_london = datetime(2026, 9, 16, 8, 30, tzinfo=timezone.utc)
        active = SessionManager.get_active_market_sessions(dt_london)
        self.assertIn("London Session", active)

        # 14:00 UTC -> London and New York overlap (12:00 - 16:00)
        dt_overlap = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)
        active_overlap = SessionManager.get_active_market_sessions(dt_overlap)
        self.assertIn("London Session", active_overlap)
        self.assertIn("New York Session", active_overlap)

        # 03:00 UTC -> Asian session (00:00 - 09:00)
        dt_asian = datetime(2026, 9, 16, 3, 0, tzinfo=timezone.utc)
        active_asian = SessionManager.get_active_market_sessions(dt_asian)
        self.assertIn("Asian Session", active_asian)

        # 22:00 UTC -> Off-hours (no major session)
        dt_off = datetime(2026, 9, 16, 22, 30, tzinfo=timezone.utc)
        active_off = SessionManager.get_active_market_sessions(dt_off)
        self.assertEqual(len(active_off), 0)

    def test_session_manager_permission(self):
        # Test allowed
        dt_london = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)
        ok, _ = SessionManager.is_session_allowed(["London Session"], dt_london)
        self.assertTrue(ok)

        # Test rejected when only NY allowed
        ok_ny, reason = SessionManager.is_session_allowed(["New York Session"], dt_london)
        self.assertFalse(ok_ny)
        self.assertIn("not in selected", reason)

        # Test 24/7 always passes
        dt_off = datetime(2026, 9, 16, 22, 30, tzinfo=timezone.utc)
        ok_247, _ = SessionManager.is_session_allowed(["24/7 (Any Session)"], dt_off)
        self.assertTrue(ok_247)

    def test_htf_confluence_mapping(self):
        self.assertEqual(HTFConfluenceChecker.get_htf_timeframe("15m"), "1h")
        self.assertEqual(HTFConfluenceChecker.get_htf_timeframe("30m"), "4h")
        self.assertEqual(HTFConfluenceChecker.get_htf_timeframe("1h"), "4h")
        self.assertEqual(HTFConfluenceChecker.get_htf_timeframe("4h"), "1d")

    def test_htf_confluence_alignment_bullish(self):
        # Construct synthetic uptrend dataframe (prices rising steadily)
        closes = np.linspace(100.0, 150.0, 50)
        df_htf = pd.DataFrame({"close": closes})

        # BUY on uptrend should be ALIGNED
        ok, reason, details = HTFConfluenceChecker.check_alignment(
            symbol="EURUSD",
            current_tf="15m",
            direction="BUY",
            df_htf=df_htf
        )
        self.assertTrue(ok)
        self.assertIn("Confirmed", reason)
        self.assertTrue(details["is_bullish"])

        # SELL on uptrend should CONFLICT
        ok_sell, reason_sell, _ = HTFConfluenceChecker.check_alignment(
            symbol="EURUSD",
            current_tf="15m",
            direction="SELL",
            df_htf=df_htf
        )
        self.assertFalse(ok_sell)
        self.assertIn("Conflict", reason_sell)

    def test_htf_confluence_alignment_bearish(self):
        # Construct synthetic downtrend dataframe (prices falling steadily)
        closes = np.linspace(150.0, 100.0, 50)
        df_htf = pd.DataFrame({"close": closes})

        # SELL on downtrend should be ALIGNED
        ok_sell, reason_sell, details = HTFConfluenceChecker.check_alignment(
            symbol="EURUSD",
            current_tf="15m",
            direction="SELL",
            df_htf=df_htf
        )
        self.assertTrue(ok_sell)
        self.assertIn("Confirmed", reason_sell)
        self.assertTrue(details["is_bearish"])

        # BUY on downtrend should CONFLICT
        ok_buy, reason_buy, _ = HTFConfluenceChecker.check_alignment(
            symbol="EURUSD",
            current_tf="15m",
            direction="BUY",
            df_htf=df_htf
        )
        self.assertFalse(ok_buy)
        self.assertIn("Conflict", reason_buy)

    def test_htf_confluence_short_history_no_bypass(self):
        # 40 bars in an uptrend (len < 50) must NOT allow SELL
        closes = np.linspace(100.0, 150.0, 40)
        df_htf = pd.DataFrame({"close": closes})

        ok_sell, reason_sell, details = HTFConfluenceChecker.check_alignment(
            symbol="XAUUSD",
            current_tf="15m",
            direction="SELL",
            df_htf=df_htf
        )
        self.assertFalse(ok_sell)
        self.assertIn("Conflict", reason_sell)

    def test_autonomous_settings_session_and_htf(self):
        settings = AutonomousTraderEngine.load_settings()
        self.assertIn("active_sessions", settings)
        self.assertIn("htf_filter_enabled", settings)
        self.assertIsInstance(settings["active_sessions"], list)
        self.assertIsInstance(settings["htf_filter_enabled"], bool)

if __name__ == '__main__':
    unittest.main()
