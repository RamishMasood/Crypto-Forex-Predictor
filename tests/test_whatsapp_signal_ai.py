"""
Unit Tests for WhatsApp Signal AI Parser & Executor
Covers all real scenarios from Tradingpapa.com channel screenshots:
- Unconfirmed setup with TP1-TP5 & engulfed candle condition (Image 1)
- Single-word follow-up confirmation 'Entered' (Image 1)
- Risk advisories & sentiment commentary -> HOLD (Image 1, 3, 4, 5)
- Early cut level / SL tightening 'Cut the trade if it reach 4159' (Image 4)
- Full exit / cut signal in Roman Urdu 'Cut krdo yrr' (Image 5)
- Strict Zero-Hallucination Safety Gate
- Multi-pair independent lifecycle tracking
- Multimodal image attachment parsing
"""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine.whatsapp_signal_parser import WhatsAppSignalParser, SETUPS_CACHE_FILE
from src.engine.whatsapp_signal_executor import WhatsAppSignalExecutor, WHATSAPP_MAGIC_NUMBER

class TestWhatsAppSignalAI(unittest.TestCase):

    def setUp(self):
        self.parser = WhatsAppSignalParser()
        self.channel_name = "Tradingpapa.com forex (gold and silver)"
        # Backup setups cache and isolate per test
        self.orig_cache = {}
        if os.path.exists(SETUPS_CACHE_FILE):
            with open(SETUPS_CACHE_FILE, "r", encoding="utf-8") as f:
                self.orig_cache = json.load(f)
        self.parser.setups_cache = {}
        with open(SETUPS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

    def tearDown(self):
        # Restore setups cache
        with open(SETUPS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.orig_cache, f, indent=2)

    def test_scenario_1_unconfirmed_setup(self):
        """Image 1 (4:48 PM): Unconfirmed Setup message with TP1-TP5 and engulfed candle condition."""
        msg = (
            "Sell\n"
            "Best Entry Zones 4154.873\n"
            "TP1 4144.002\n"
            "TP2 4131.297\n"
            "TP3 4120.328\n"
            "TP4 4109.817\n"
            "TP5 4098.897\n"
            "max close on every TP\n"
            "Wait for confirmation otherwise don't enter skip this signal\n"
            "Sell after strong engulfed candle\n"
            "SL 4162.706"
        )
        res = self.parser._heuristic_fallback_parse(msg, channel_name=self.channel_name)

        self.assertEqual(res.get("action"), "SETUP_SAVED")
        self.assertTrue(res.get("confirmation_required"))
        self.assertEqual(res.get("symbol"), "XAUUSD")
        self.assertEqual(res.get("direction"), "SELL")
        self.assertEqual(res.get("entry_price"), 4154.873)
        self.assertEqual(res.get("stop_loss"), 4162.706)
        self.assertEqual(res.get("tp1"), 4144.002)
        self.assertEqual(res.get("tp2"), 4131.297)
        self.assertEqual(res.get("tp3"), 4120.328)
        self.assertEqual(res.get("tp4"), 4109.817)
        self.assertEqual(res.get("tp5"), 4098.897)

        # Verify persistent cache
        cached = self.parser.get_cached_setup("XAUUSD")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.get("status"), "PENDING_CONFIRMATION")
        self.assertEqual(cached.get("stop_loss"), 4162.706)

    def test_scenario_2_followup_confirmation_entered(self):
        """Image 1 (4:49 PM): Single-word follow-up 'Entered' correlates with pending setup."""
        # 1. Setup stored in memory
        self.parser.store_setup("XAUUSD", {
            "symbol": "XAUUSD",
            "action": "SELL",
            "entry": 4154.873,
            "stop_loss": 4162.706,
            "tp1": 4144.002,
            "tp2": 4131.297,
            "tp3": 4120.328,
            "tp4": 4109.817,
            "tp5": 4098.897,
            "status": "PENDING_CONFIRMATION",
            "raw_message": "Sell Best Entry Zones 4154..."
        })

        # 2. Admin sends just "Entered"
        res = self.parser._heuristic_fallback_parse("Entered", channel_name=self.channel_name)

        self.assertEqual(res.get("action"), "ENTER")
        self.assertEqual(res.get("symbol"), "XAUUSD")
        self.assertEqual(res.get("direction"), "SELL")
        self.assertEqual(res.get("stop_loss"), 4162.706)
        self.assertEqual(res.get("tp1"), 4144.002)
        self.assertTrue(res.get("safety_gate_passed"))

        # Simulate executor confirming trade execution on MT5
        self.parser.mark_setup_status("XAUUSD", "CONFIRMED_ACTIVE")
        cached = self.parser.get_cached_setup("XAUUSD")
        self.assertEqual(cached.get("status"), "CONFIRMED_ACTIVE")

    def test_scenario_3_risk_advisories_and_hold(self):
        """Image 1 (4:50 PM), Image 3 (5:00-5:06 PM), Image 5 (5:33 PM): Risk warnings -> HOLD."""
        advisories = [
            "Low risk",
            "Trade Zara risky haii low risk m rehna",
            "High risk alert",
            "Fear & Manipulation",
            "Drama bna rhi market",
            "Hold wohi kary Jo kr skta",
            "Previous NY Session Ki liquidity sweep ka wait kr rha Tha"
        ]
        for adv in advisories:
            res = self.parser._heuristic_fallback_parse(adv, channel_name=self.channel_name)
            self.assertEqual(res.get("action"), "HOLD", f"Failed for advisory: '{adv}'")

    def test_scenario_4_early_cut_sl_modification(self):
        """Image 4 (5:17 PM): 'Cut the trade if it reach 4159 or 4160...' -> MODIFY_SL."""
        msg = "Cut the trade if it reach 4159 or 4160 because market is not in good situation"
        open_trades = [{"ticket": 101, "symbol": "XAUUSDm", "type": "SELL", "price_open": 4155.22, "sl": 4162.706, "tp": 4144.002, "profit": 50.0}]

        res = self.parser._heuristic_fallback_parse(msg, open_trades=open_trades, channel_name=self.channel_name)

        self.assertEqual(res.get("action"), "MODIFY_SL")
        self.assertEqual(res.get("symbol"), "XAUUSD")
        self.assertEqual(res.get("stop_loss"), 4159.0)

    def test_scenario_5_full_cut_exit_signal(self):
        """Image 5 (5:33 PM): 'Cut krdo yrr' -> CLOSE_ALL."""
        msg = "Cut krdo yrr"
        open_trades = [{"ticket": 101, "symbol": "XAUUSDm", "type": "SELL", "price_open": 4155.22, "sl": 4159.0, "tp": 4144.002, "profit": 200.0}]

        res = self.parser._heuristic_fallback_parse(msg, open_trades=open_trades, channel_name=self.channel_name)

        self.assertEqual(res.get("action"), "CLOSE_ALL")
        self.assertEqual(res.get("symbol"), "XAUUSD")

    def test_scenario_6_strict_safety_gate(self):
        """Strict Zero-Hallucination Gate: If SL/TP are missing without cached setup, block trade."""
        # Clean cache
        if os.path.exists(SETUPS_CACHE_FILE):
            os.remove(SETUPS_CACHE_FILE)
        self.parser.setups_cache = {}

        res = self.parser._heuristic_fallback_parse("Buy BTC now", channel_name="Crypto Channel")
        # Should be blocked / held as entry trigger awaiting setup levels
        self.assertFalse(res.get("safety_gate_passed", False))
        self.assertIn(res.get("action"), ["BLOCKED", "ENTRY_TRIGGERED"])

    def test_scenario_7_multi_pair_independent_tracking(self):
        """Simultaneous setups for BTCUSD and XAUUSD are tracked independently."""
        self.parser.store_setup("BTCUSD", {
            "symbol": "BTCUSD",
            "action": "BUY",
            "entry": 65000.0,
            "stop_loss": 64000.0,
            "tp1": 66500.0,
            "status": "PENDING_CONFIRMATION"
        })
        self.parser.store_setup("XAUUSD", {
            "symbol": "XAUUSD",
            "action": "SELL",
            "entry": 4154.873,
            "stop_loss": 4162.706,
            "tp1": 4144.002,
            "status": "PENDING_CONFIRMATION"
        })

        # Explicit BTC exit
        res_btc = self.parser._heuristic_fallback_parse("All positions booked in BTC guys", channel_name="Tradingpapa")
        self.assertEqual(res_btc.get("action"), "CLOSE_ALL")
        self.assertEqual(res_btc.get("symbol"), "BTCUSD")

        # Explicit Gold SL move
        res_gold = self.parser._heuristic_fallback_parse("Move SL to BE in Gold", channel_name="Tradingpapa")
        self.assertEqual(res_gold.get("action"), "MODIFY_SL")
        self.assertEqual(res_gold.get("symbol"), "XAUUSD")

        # Both remain distinctly accessible in cache
        self.assertIsNotNone(self.parser.get_cached_setup("BTCUSD"))
        self.assertIsNotNone(self.parser.get_cached_setup("XAUUSD"))

    def test_scenario_8_multimodal_user_uploaded_screenshots(self):
        """Verify parser can ingest real uploaded screenshots from the channel."""
        img_paths = [
            "C:/Users/ramis/.gemini/antigravity/brain/52533407-f8ed-4001-8161-b93be1260d0a/.user_uploaded/media_1790699607860.png",
            "C:/Users/ramis/.gemini/antigravity/brain/52533407-f8ed-4001-8161-b93be1260d0a/.user_uploaded/media_1790699633545.png",
            "C:/Users/ramis/.gemini/antigravity/brain/52533407-f8ed-4001-8161-b93be1260d0a/.user_uploaded/media_1790699673949.png"
        ]
        for p in img_paths:
            if os.path.exists(p):
                res = self.parser.parse_message(
                    message_text="[Screenshot / Image Attachment]",
                    channel_name=self.channel_name,
                    image_path=p
                )
                self.assertIsNotNone(res)
                self.assertIn("action", res)

    def test_scenario_9_quoted_reply_confirmation(self):
        """Admin replies to an earlier setup message quoting it."""
        quote = (
            "Sell\n"
            "Best Entry Zones 4154.873\n"
            "TP1 4144.002\n"
            "SL 4162.706"
        )
        msg = "Active now guys, enter ho jao"
        res = self.parser._heuristic_fallback_parse(msg, quoted_text=quote, channel_name=self.channel_name)

        self.assertEqual(res.get("action"), "ENTER")
        self.assertEqual(res.get("symbol"), "XAUUSD")
        self.assertEqual(res.get("direction"), "SELL")
        self.assertEqual(res.get("stop_loss"), 4162.706)
        self.assertEqual(res.get("tp1"), 4144.002)
        self.assertTrue(res.get("safety_gate_passed"))

    def test_scenario_10_listener_process_message_now_lifecycle(self):
        """End-to-end integration via WhatsAppListenerEngine.process_message_now (with isolated mocked broker fills)."""
        from unittest.mock import patch, MagicMock
        from src.engine.whatsapp_listener import WhatsAppListenerEngine

        listener = WhatsAppListenerEngine()
        # Mock executor backend so tests never place live trades or block on terminal state
        listener.executor.executor.execute_multi_target_trade = MagicMock(return_value={"success": True, "tickets": [99901, 99902]})
        listener.executor.executor.move_to_breakeven = MagicMock(return_value={"success": True})
        listener.executor.executor.close_position = MagicMock(return_value={"success": True})

        # Step 1: Unconfirmed setup arrives
        setup_text = (
            "Sell\n"
            "Best Entry Zones 4154.873\n"
            "TP1 4144.002\n"
            "TP2 4131.297\n"
            "Wait for confirmation otherwise don't enter skip this signal\n"
            "SL 4162.706"
        )
        res1 = listener.process_message_now(setup_text)
        self.assertEqual(res1["parsed"].get("action"), "SETUP_SAVED")

        # Step 2: Confirmation follows up
        res2 = listener.process_message_now("Entered")
        self.assertEqual(res2["parsed"].get("action"), "ENTER")
        self.assertEqual(res2["parsed"].get("symbol"), "XAUUSD")
        self.assertEqual(res2["parsed"].get("stop_loss"), 4162.706)

        # Step 3: Risk advisory follows up
        res3 = listener.process_message_now("Trade Zara risky haii low risk m rehna")
        self.assertEqual(res3["parsed"].get("action"), "HOLD")

        # Step 4: Early cut level instruction
        res4 = listener.process_message_now("Cut the trade if it reach 4159")
        self.assertEqual(res4["parsed"].get("action"), "MODIFY_SL")
        self.assertEqual(res4["parsed"].get("stop_loss"), 4159.0)

        # Step 5: Full exit
        res5 = listener.process_message_now("Cut krdo yrr")
        self.assertEqual(res5["parsed"].get("action"), "CLOSE_ALL")
        self.assertEqual(res5["parsed"].get("symbol"), "XAUUSD")

    def test_scenario_11_roman_urdu_early_cut_and_breakeven(self):
        """Covers Roman Urdu variations for early cut price level and breakeven/cost commands."""
        # 1. Roman Urdu conditional early cut with price
        res_cut1 = self.parser._heuristic_fallback_parse("4159 pe cut kardo yrr", channel_name=self.channel_name)
        self.assertEqual(res_cut1.get("action"), "MODIFY_SL")
        self.assertEqual(res_cut1.get("stop_loss"), 4159.0)
        self.assertEqual(res_cut1.get("symbol"), "XAUUSD")

        res_cut2 = self.parser._heuristic_fallback_parse("agar 4159 touch kare to exit kar lena", channel_name=self.channel_name)
        self.assertEqual(res_cut2.get("action"), "MODIFY_SL")
        self.assertEqual(res_cut2.get("stop_loss"), 4159.0)

        # 2. Roman Urdu Breakeven / Cost / SL Band Kar Do
        res_be1 = self.parser._heuristic_fallback_parse("BTC USD ka SL band kar do", channel_name="Tradingpapa")
        self.assertEqual(res_be1.get("action"), "MODIFY_SL")
        self.assertEqual(res_be1.get("symbol"), "BTCUSD")
        self.assertIsNone(res_be1.get("stop_loss"))  # None signals move_to_breakeven()

        res_be2 = self.parser._heuristic_fallback_parse("SL cost pe le aao safe traders", channel_name=self.channel_name)
        self.assertEqual(res_be2.get("action"), "MODIFY_SL")
        self.assertEqual(res_be2.get("symbol"), "XAUUSD")
        self.assertIsNone(res_be2.get("stop_loss"))

    def test_scenario_12_partial_close_urdu_and_percentages(self):
        """Covers Roman Urdu partial profit booking commands."""
        # 1. Explicit percentage in Roman Urdu
        res_pct = self.parser._heuristic_fallback_parse("BTC USD ka 50% nikal lo TP mein se", channel_name="Tradingpapa")
        self.assertEqual(res_pct.get("action"), "PARTIAL_CLOSE")
        self.assertEqual(res_pct.get("symbol"), "BTCUSD")
        self.assertEqual(res_pct.get("volume_pct"), 50.0)

        # 2. TP close instruction
        res_tp = self.parser._heuristic_fallback_parse("Gold ka TP uska close kar do", channel_name=self.channel_name)
        self.assertEqual(res_tp.get("action"), "PARTIAL_CLOSE")
        self.assertEqual(res_tp.get("symbol"), "XAUUSD")
        self.assertEqual(res_tp.get("volume_pct"), 50.0)

    def test_scenario_13_multi_coin_instruction_in_single_message(self):
        """Covers single message containing instructions for two coins at once."""
        msg = "BTC USD ka SL band kar do aur Gold ka trade cut kar do"
        res = self.parser._heuristic_fallback_parse(msg, channel_name="Tradingpapa")

        self.assertEqual(res.get("action"), "MULTI_SIGNAL")
        signals = res.get("signals", [])
        self.assertEqual(len(signals), 2)

        btc_sig = next((s for s in signals if s.get("symbol") == "BTCUSD"), None)
        gold_sig = next((s for s in signals if s.get("symbol") == "XAUUSD"), None)

        self.assertIsNotNone(btc_sig)
        self.assertIsNotNone(gold_sig)
        self.assertEqual(btc_sig.get("action"), "MODIFY_SL")
        self.assertEqual(gold_sig.get("action"), "CLOSE_ALL")

        # Verify executor can execute multi-signal payload cleanly
        from unittest.mock import MagicMock
        executor = WhatsAppSignalExecutor()
        executor.execute_parsed_signal = MagicMock(return_value={"success": True})
        # Wrap real executor call with mock
        from src.engine.whatsapp_signal_executor import WhatsAppSignalExecutor as RealExec
        real_exec = RealExec()
        real_exec._get_whatsapp_positions = MagicMock(return_value=[])
        exec_res = real_exec.execute_parsed_signal(res, msg)
        self.assertEqual(exec_res.get("status"), "MULTI_SIGNAL_EXECUTED")
        self.assertTrue(exec_res.get("success"))

    def test_scenario_14_uncaptioned_image_advisory_hold(self):
        """Uncaptioned image (e.g. news screenshot or chart) defaults to HOLD advisory, never blind ENTER."""
        res = self.parser._heuristic_fallback_parse(
            text="[Screenshot / Image Attachment]",
            image_path="dummy.png",
            channel_name=self.channel_name
        )
        self.assertEqual(res.get("action"), "HOLD")
        self.assertEqual(res.get("symbol"), "XAUUSD")

    def test_scenario_15_executor_partial_close_volume_math(self):
        """Verify WhatsAppSignalExecutor.execute_parsed_signal calculates and closes partial lots."""
        from unittest.mock import MagicMock
        executor = WhatsAppSignalExecutor()
        executor.resolve_broker_symbol = MagicMock(return_value="XAUUSDm")

        # 2 WhatsApp positions with total 0.04 lots
        mock_positions = [
            {"ticket": 101, "symbol": "XAUUSDm", "volume": 0.02, "magic": WHATSAPP_MAGIC_NUMBER},
            {"ticket": 102, "symbol": "XAUUSDm", "volume": 0.02, "magic": WHATSAPP_MAGIC_NUMBER}
        ]
        executor._get_whatsapp_positions = MagicMock(return_value=mock_positions)
        executor.executor.close_position = MagicMock(return_value={"success": True})

        # Request 50% partial close (should close 0.02 lots total: ticket 101 full)
        res = executor.execute_parsed_signal({
            "action": "PARTIAL_CLOSE",
            "symbol": "XAUUSD",
            "volume_pct": 50.0
        }, "50% nikal lo")

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("status"), "PARTIAL_CLOSED")
        # Verify close_position was called for ticket 101
        executor.executor.close_position.assert_called_with(101)

    def test_scenario_16_two_step_entry_correlation_eurgbp(self):
        """User exact scenario: Admin says 'EURGBP mein enter ho jao sabhi long side' followed by setup card with 'Enter with confirmation'."""
        self.parser.clear_entry_trigger("EURGBP")
        if "EURGBP" in self.parser.setups_cache:
            del self.parser.setups_cache["EURGBP"]
            self.parser._save_setups_cache()

        # Step 1: Entry command arrives (without SL/TP)
        m1 = "EURGBP mein enter ho jao sabhi long side"
        res1 = self.parser._heuristic_fallback_parse(m1, channel_name=self.channel_name)
        self.assertEqual(res1.get("action"), "ENTRY_TRIGGERED")
        self.assertEqual(res1.get("symbol"), "EURGBP")
        self.assertEqual(res1.get("direction"), "BUY")
        self.assertFalse(res1.get("safety_gate_passed"))

        # Step 2: Setup card arrives shortly after with 'Enter with confirmation otherwise skip this signal'
        m2 = (
            "EURGBP\n"
            "Long\n"
            "Entry - 0.85435\n"
            "SL - 0.85412\n"
            "TP 1 0.85461\n"
            "TP 2 0.85486\n"
            "Enter with confirmation otherwise skip this signal"
        )
        res2 = self.parser._heuristic_fallback_parse(
            m2,
            recent_history=[{"time": "08:00", "text": m1}],
            channel_name=self.channel_name
        )
        self.assertEqual(res2.get("action"), "ENTER")
        self.assertEqual(res2.get("symbol"), "EURGBP")
        self.assertEqual(res2.get("direction"), "BUY")
        self.assertEqual(res2.get("stop_loss"), 0.85412)
        self.assertEqual(res2.get("tp1"), 0.85461)
        self.assertEqual(res2.get("tp2"), 0.85486)
        self.assertFalse(res2.get("confirmation_required"))
        self.assertTrue(res2.get("safety_gate_passed"))

    def test_scenario_17_standalone_setup_awaits_confirmation(self):
        """If admin sends setup with 'Enter with confirmation' WITHOUT a prior entry command, it remains SETUP_SAVED."""
        self.parser.clear_entry_trigger("EURGBP")
        # Remove EURGBP from persistent setups cache for a clean test
        if "EURGBP" in self.parser.setups_cache:
            del self.parser.setups_cache["EURGBP"]
            self.parser._save_setups_cache()

        m_standalone = (
            "EURGBP\n"
            "Long\n"
            "Entry - 0.85435\n"
            "SL - 0.85412\n"
            "TP 1 0.85461\n"
            "TP 2 0.85486\n"
            "Enter with confirmation otherwise skip this signal"
        )
        res = self.parser._heuristic_fallback_parse(m_standalone, recent_history=[], channel_name=self.channel_name)
        self.assertEqual(res.get("action"), "SETUP_SAVED")
        self.assertTrue(res.get("confirmation_required"))

    def test_scenario_18_duplicate_active_setup_suppressed(self):
        """Verify that an active running WhatsApp trade blocks duplicate entries until it closes."""
        executor = WhatsAppSignalExecutor(parser=self.parser)
        
        # Simulate active running WhatsApp trade for EURGBP
        executor.get_open_whatsapp_positions = lambda symbol=None: [
            {"ticket": 12345, "symbol": "EURGBP", "type": 0, "magic": WHATSAPP_MAGIC_NUMBER}
        ]
        state = executor.load_state()
        state["active_signal_trades"]["EURGBP"] = {
            "symbol": "EURGBP",
            "direction": "BUY",
            "sl": 0.85412,
            "tp1": 0.85461,
            "tickets": [12345]
        }
        executor.save_state(state)

        # Incoming duplicate ENTER signal for EURGBP
        dup_signal = {
            "action": "ENTER",
            "symbol": "EURGBP",
            "direction": "BUY",
            "stop_loss": 0.85412,
            "tp1": 0.85461,
            "tp2": 0.85486,
            "safety_gate_passed": True
        }
        res = executor.execute_parsed_signal(dup_signal, "EURGBP buy enter ho jao dubara")
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("status"), "DUPLICATE_ACTIVE_SETUP_SKIPPED")
        self.assertIn("Duplicate active setup suppressed", res.get("reason", ""))

        # Clean up test state
        state = executor.load_state()
        state["active_signal_trades"].pop("EURGBP", None)
        executor.save_state(state)


if __name__ == "__main__":
    unittest.main()
