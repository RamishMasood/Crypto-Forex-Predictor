import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine.recommended_presets import RecommendedPresetsManager, RECOMMENDED_SYMBOL_PROFILES
from src.engine.autonomous_manager import AutonomousTraderEngine

class TestRecommendedMode(unittest.TestCase):

    def test_recommended_symbols_catalog(self):
        symbols = RecommendedPresetsManager.get_recommended_symbols()
        self.assertIn("CADJPY", symbols)
        self.assertIn("ETH/USD", symbols)
        self.assertIn("XAU/USD", symbols)
        self.assertIn("XAUUSD247", symbols)
        self.assertIn("BTC/USD", symbols)
        self.assertIn("EUR/USD", symbols)
        self.assertIn("XAG/USD", symbols)

    def test_xagusd_profile_tight_be(self):
        profile = RecommendedPresetsManager.get_profile_for_symbol("XAGUSDm")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["breakeven_mode"], "tight")
        self.assertEqual(profile["timeframes"], ["15m", "1h"])
        self.assertIn("London Session", profile["active_sessions"])
        self.assertIn("New York Session", profile["active_sessions"])

    def test_cadjpy_profile_loose_runners(self):
        profile = RecommendedPresetsManager.get_profile_for_symbol("CADJPYm")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["breakeven_mode"], "loose")
        self.assertEqual(profile["timeframes"], ["15m", "1h"])
        self.assertIn("London Session", profile["active_sessions"])

    def test_eth_profile_tight_vault(self):
        profile = RecommendedPresetsManager.get_profile_for_symbol("ETHUSDm")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["breakeven_mode"], "tight")
        self.assertEqual(profile["timeframes"], ["1h", "4h"])
        self.assertIn("24/7 (Any Session)", profile["active_sessions"])

    def test_btc_profile_excludes_micro_noise(self):
        profile = RecommendedPresetsManager.get_profile_for_symbol("BTC/USD")
        self.assertIsNotNone(profile)
        self.assertNotIn("1m", profile["timeframes"])
        self.assertNotIn("5m", profile["timeframes"])
        self.assertEqual(profile["timeframes"], ["1h", "4h"])
        self.assertEqual(profile["breakeven_mode"], "tight")

    def test_eurusd_profile_excludes_asian_chop(self):
        profile = RecommendedPresetsManager.get_profile_for_symbol("EUR/USD")
        self.assertIsNotNone(profile)
        self.assertNotIn("Asian Session", profile["active_sessions"])
        self.assertIn("London Session", profile["active_sessions"])
        self.assertEqual(profile["breakeven_mode"], "tight")

    def test_unknown_symbol_resolution(self):
        self.assertIsNone(RecommendedPresetsManager.get_profile_for_symbol("RANDOM_COIN_XYZ"))
        self.assertFalse(RecommendedPresetsManager.is_symbol_recommended("RANDOM_COIN_XYZ"))

    def test_autonomous_settings_schema(self):
        settings = AutonomousTraderEngine.load_settings()
        self.assertIn("recommended_mode", settings)
        self.assertIsInstance(settings["recommended_mode"], bool)

if __name__ == '__main__':
    unittest.main()
