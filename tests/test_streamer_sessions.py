import unittest
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine.session_manager import SessionManager

class TestStreamerSessions(unittest.TestCase):
    """
    Tests strategy-specific session gating and killzone compliance as defined in
    'TRADING SESSIONS & KILLZONES PLAYBOOK' (Pages 1-3).
    """

    def test_ict_killzones(self):
        # London Killzone (07:00 - 10:00 UTC) -> ALLOWED
        dt_london = datetime(2026, 9, 16, 8, 30, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("ICT", dt_london, generic_allowed_sessions=["Asian Session"])
        self.assertTrue(ok, f"ICT should be allowed during London Killzone: {reason}")
        self.assertIn("London Killzone", reason)

        # NY Killzone & Silver Bullet AM (12:00 - 16:00 UTC) -> ALLOWED
        dt_ny = datetime(2026, 9, 16, 13, 30, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("ICT", dt_ny, generic_allowed_sessions=["Asian Session"])
        self.assertTrue(ok, f"ICT should be allowed during NY Killzone: {reason}")

        # ICT Silver Bullet PM (19:00 - 20:00 UTC) -> ALLOWED
        dt_pm = datetime(2026, 9, 16, 19, 30, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("ICT", dt_pm, generic_allowed_sessions=["Asian Session"])
        self.assertTrue(ok, f"ICT should be allowed during PM Silver Bullet: {reason}")

        # Asian Session (03:00 UTC) -> BLOCKED (Liquidity target only, never entry)
        dt_asia = datetime(2026, 9, 16, 3, 0, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("ICT", dt_asia, generic_allowed_sessions=["24/7 (Any Session)"])
        self.assertFalse(ok, "ICT must be blocked during Asian session even if 24/7 selected in UI")
        self.assertIn("Outside ICT Killzone", reason)

    def test_vivek_yadav_sessions(self):
        # London Open Sweep (08:00 - 11:00 UTC) -> ALLOWED
        dt_london = datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("VIVEK_YADAV", dt_london, generic_allowed_sessions=["Asian Session"])
        self.assertTrue(ok, f"Vivek Yadav should be allowed during London Sweep: {reason}")

        # NY Open & CPI (13:00 - 16:00 UTC) -> ALLOWED
        dt_ny = datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("VIVEK_YADAV", dt_ny)
        self.assertTrue(ok)

        # Asian Session (02:00 UTC) -> BLOCKED (Strictly for heatmap liquidity accumulation)
        dt_asia = datetime(2026, 9, 16, 2, 0, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("VIVEK_YADAV", dt_asia, generic_allowed_sessions=["24/7 (Any Session)"])
        self.assertFalse(ok, "Vivek Yadav must be blocked during Asian session")
        self.assertIn("Outside VIVEK_YADAV Killzone", reason)

    def test_bernd_skorupinski_session_independent(self):
        # Bernd Skorupinski is a swing trader (HTF 'Set & Forget') -> Always ALLOWED 24/7
        dt_asia = datetime(2026, 9, 16, 4, 0, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("BERND_SKORUPINSKI", dt_asia, generic_allowed_sessions=["London Session"])
        self.assertTrue(ok)
        self.assertIn("Session-Independent", reason)

        dt_off = datetime(2026, 9, 16, 23, 0, tzinfo=timezone.utc)
        ok, _ = SessionManager.is_strategy_session_allowed("BERND_SKORUPINSKI", dt_off)
        self.assertTrue(ok)

    def test_ross_cameron_power_hour(self):
        # Pre-Market & NY Open Power Hour (12:00 - 15:30 UTC / 7:00 - 10:30 AM EST) -> ALLOWED
        dt_morning = datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("ROSS_CAMERON", dt_morning)
        self.assertTrue(ok)

        # After 10:30 AM EST (e.g. 16:30 UTC / 11:30 AM EST) -> BLOCKED (avoid midday chop)
        dt_afternoon = datetime(2026, 9, 16, 16, 30, tzinfo=timezone.utc)
        ok, reason = SessionManager.is_strategy_session_allowed("ROSS_CAMERON", dt_afternoon, generic_allowed_sessions=["24/7 (Any Session)"])
        self.assertFalse(ok)
        self.assertIn("Outside ROSS_CAMERON Killzone", reason)

    def test_ndemazeah_godlove(self):
        # Peak London & NY Overlap (07:00 - 16:30 UTC) -> ALLOWED
        dt_peak = datetime(2026, 9, 16, 11, 0, tzinfo=timezone.utc)
        ok, _ = SessionManager.is_strategy_session_allowed("NDEMAZEAH_GODLOVE", dt_peak)
        self.assertTrue(ok)

        # Off-hours -> BLOCKED
        dt_night = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)
        ok, _ = SessionManager.is_strategy_session_allowed("NDEMAZEAH_GODLOVE", dt_night)
        self.assertFalse(ok)

    def test_steven_hart_and_rayner_teo(self):
        # London & NY Peak Hours (08:00 - 17:00 UTC) -> ALLOWED
        dt_trade = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
        ok_sh, _ = SessionManager.is_strategy_session_allowed("STEVEN_HART", dt_trade)
        ok_rt, _ = SessionManager.is_strategy_session_allowed("RAYNER_TEO", dt_trade)
        self.assertTrue(ok_sh)
        self.assertTrue(ok_rt)

        # Asian Session (02:00 UTC) -> BLOCKED (Strictly avoided due to low volume/chop)
        dt_asia = datetime(2026, 9, 16, 2, 0, tzinfo=timezone.utc)
        ok_sh_asia, _ = SessionManager.is_strategy_session_allowed("STEVEN_HART", dt_asia)
        ok_rt_asia, _ = SessionManager.is_strategy_session_allowed("RAYNER_TEO", dt_asia)
        self.assertFalse(ok_sh_asia)
        self.assertFalse(ok_rt_asia)

    def test_unlisted_strategies_fallback_to_generic(self):
        # Strategies not in Sessions Playbook (CRYPTO_CRED, ADAM_KHOO, ARIEL_ZWECHER, OLIVER_VELEZ, TRADE_PRO, DEFAULT)
        # Must strictly respect generic_allowed_sessions selected by the user in UI
        unlisted = ["CRYPTO_CRED", "ADAM_KHOO", "ARIEL_ZWECHER", "OLIVER_VELEZ", "TRADE_PRO", "DEFAULT"]
        
        dt_london = datetime(2026, 9, 16, 8, 30, tzinfo=timezone.utc)
        dt_off = datetime(2026, 9, 16, 23, 0, tzinfo=timezone.utc)

        for strat in unlisted:
            # When UI allows London Session only
            ok_london, _ = SessionManager.is_strategy_session_allowed(strat, dt_london, generic_allowed_sessions=["London Session"])
            self.assertTrue(ok_london, f"{strat} should be allowed during London Session when London is selected")

            ok_off, _ = SessionManager.is_strategy_session_allowed(strat, dt_off, generic_allowed_sessions=["London Session"])
            self.assertFalse(ok_off, f"{strat} should be blocked during off-hours when London is selected")

            # When UI allows 24/7
            ok_247, _ = SessionManager.is_strategy_session_allowed(strat, dt_off, generic_allowed_sessions=["24/7 (Any Session)"])
            self.assertTrue(ok_247, f"{strat} should be allowed during 24/7 mode")

    def test_rollover_spread_guard(self):
        # 5 PM EST / 21:45 - 22:15 UTC is broker rollover spread spike window
        dt_rollover = datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc)

        # Non-crypto (Forex, Gold) -> BLOCKED
        ok_fx, reason_fx = SessionManager.is_strategy_session_allowed(
            "BERND_SKORUPINSKI", dt_rollover, asset_type='forex'
        )
        self.assertFalse(ok_fx, "Forex must be blocked during rollover window")
        self.assertIn("Spread Guard", reason_fx)

        # Crypto (BTC, ETH) -> NOT blocked by rollover (24/7 continuous crypto markets)
        ok_crypto, reason_crypto = SessionManager.is_strategy_session_allowed(
            "BERND_SKORUPINSKI", dt_rollover, asset_type='crypto'
        )
        self.assertTrue(ok_crypto, "Crypto should not be blocked by 5 PM EST Forex broker rollover")

if __name__ == '__main__':
    unittest.main()
