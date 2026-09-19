"""
Unit tests for Tight vs Loose Breakeven Modes in Crypto Forex Predictor
"""

import unittest
from unittest.mock import MagicMock, patch
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine.risk_manager import RiskManager
from src.engine.autonomous_manager import AutonomousTraderEngine
from src.engine.mt5_executor import MT5TradeExecutor

class TestBreakevenModes(unittest.TestCase):

    def test_risk_manager_breakeven_fields(self):
        # 1. Long setup
        setup_buy = RiskManager.generate_trade_setup(
            current_price=2600.0,
            action='BUY',
            atr=10.0,
            account_size_usd=10000.0
        )
        self.assertEqual(setup_buy['action'], 'BUY')
        self.assertIn('breakeven_sl', setup_buy)
        self.assertIn('soft_breakeven_sl', setup_buy)
        self.assertIn('loose_be_trigger', setup_buy)
        self.assertIn('loose_be_trigger_dist', setup_buy)

        # In a BUY, entry=2600, atr=10
        # Hard breakeven = 2600 + (0.02 * 10) = 2600.2
        self.assertAlmostEqual(setup_buy['breakeven_sl'], 2600.2, places=2)
        # Soft breakeven buffer = 2600 - (0.45 * 10) = 2595.5 (0.45 ATR breathing room below entry)
        self.assertAlmostEqual(setup_buy['soft_breakeven_sl'], 2595.5, places=2)
        # Loose trigger = 2600 + (0.85 * 10) = 2608.5
        self.assertAlmostEqual(setup_buy['loose_be_trigger'], 2608.5, places=2)
        self.assertAlmostEqual(setup_buy['loose_be_trigger_dist'], 8.5, places=2)

        # 2. Short setup
        setup_sell = RiskManager.generate_trade_setup(
            current_price=2600.0,
            action='SELL',
            atr=10.0,
            account_size_usd=10000.0
        )
        self.assertEqual(setup_sell['action'], 'SELL')
        # In a SELL, entry=2600, atr=10
        # Hard breakeven = 2600 - (0.02 * 10) = 2599.8
        self.assertAlmostEqual(setup_sell['breakeven_sl'], 2599.8, places=2)
        # Soft breakeven buffer = 2600 + (0.45 * 10) = 2604.5 (0.45 ATR breathing room above entry)
        self.assertAlmostEqual(setup_sell['soft_breakeven_sl'], 2604.5, places=2)
        # Loose trigger = 2600 - (0.85 * 10) = 2591.5
        self.assertAlmostEqual(setup_sell['loose_be_trigger'], 2591.5, places=2)

    def test_autonomous_settings_breakeven_mode(self):
        settings = AutonomousTraderEngine.load_settings()
        self.assertIn('breakeven_mode', settings)
        self.assertIn(settings['breakeven_mode'], ['tight', 'loose'])

    def test_mt5_executor_tight_vs_loose_logic(self):
        executor = MT5TradeExecutor()

        # Mock connection and open positions
        with patch.object(executor, '_ensure_connection', return_value=True), \
             patch.object(executor, 'move_to_breakeven') as mock_move:
            
            mock_move.return_value = {'success': True, 'new_sl': 2600.2}

            # Scenario A: Tight mode on BUY position when TP1 is hit
            # Open price 2600, current price 2603 (0.3 ATR profit, retest zone)
            simulated_pos = [{
                'ticket': 111,
                'symbol': 'XAUUSDm',
                'type': 'BUY',
                'price_open': 2600.0,
                'price_current': 2603.0,
                'sl': 2582.0,  # wide initial stop (1.8 ATR)
                'tp': 2620.0,
                'magic': executor.MAGIC_NUMBER,
                'comment': 'QS_999001_TP2',
                'return_pct': 0.12
            }]

            batch_info_map = {
                '999001': {
                    'entry_price': 2600.0,
                    'sl_price': 2582.0,
                    'tp1_price': 2603.8,
                    'tp2_price': 2620.0,
                    'breakeven_sl': 2600.2,
                    'soft_breakeven_sl': 2595.5
                }
            }

            # In Tight Mode with TP1 deal closed in history
            with patch.object(executor, 'get_open_positions', return_value=simulated_pos):
                import MetaTrader5 as mt5
                mock_deal = MagicMock()
                mock_deal.profit = 2.5
                mock_deal.entry = 1
                mock_deal.comment = 'QS_999001_TP1'
                mock_deal.symbol = 'XAUUSDm'
                mock_deal.magic = executor.MAGIC_NUMBER

                with patch.object(mt5, 'history_deals_get', return_value=[mock_deal]):
                    # 1. Tight Mode: Snaps immediately to Hard Breakeven
                    res_tight = executor.check_and_apply_auto_breakeven(
                        batch_breakeven_sl_map={'999001': 2600.2},
                        batch_info_map=batch_info_map,
                        breakeven_mode='tight'
                    )
                    self.assertEqual(len(res_tight), 1)
                    self.assertEqual(res_tight[0]['mode'], 'TIGHT')
                    mock_move.assert_called_with(111, target_sl=2600.2)

                    # 2. Loose Mode: At 2603.0 (has not reached 0.85 ATR / 50% to TP2),
                    # moves to SOFT BUFFER (2595.5) preserving breathing room!
                    mock_move.reset_mock()
                    mock_move.return_value = {'success': True, 'new_sl': 2595.5}
                    res_loose_stage1 = executor.check_and_apply_auto_breakeven(
                        batch_breakeven_sl_map={'999001': 2600.2},
                        batch_info_map=batch_info_map,
                        breakeven_mode='loose'
                    )
                    self.assertEqual(len(res_loose_stage1), 1)
                    self.assertEqual(res_loose_stage1[0]['mode'], 'LOOSE_STAGE_1')
                    mock_move.assert_called_with(111, target_sl=2595.5)

                    # 3. Loose Mode Stage 2: When price expands to 2611.0 (>= 50% to TP2),
                    # advances to True Hard Breakeven (2600.2)
                    simulated_pos[0]['price_current'] = 2611.0
                    simulated_pos[0]['sl'] = 2595.5 # currently at soft buffer
                    mock_move.reset_mock()
                    mock_move.return_value = {'success': True, 'new_sl': 2600.2}
                    res_loose_stage2 = executor.check_and_apply_auto_breakeven(
                        batch_breakeven_sl_map={'999001': 2600.2},
                        batch_info_map=batch_info_map,
                        breakeven_mode='loose'
                    )
                    self.assertEqual(len(res_loose_stage2), 1)
                    self.assertEqual(res_loose_stage2[0]['mode'], 'LOOSE_STAGE_2')
                    mock_move.assert_called_with(111, target_sl=2600.2)

    def test_broker_deal_comment_overwrite_tight_and_loose(self):
        """
        Tests the real-world scenario where MT5 / Exness broker overwrites deal comment
        with '[tp 1.14575]' (stripping 'QS_...'), but ticket map & position_id correctly
        identify TP1 hit and trigger immediate breakeven in Tight mode, and soft buffer in Loose mode.
        """
        executor = MT5TradeExecutor()
        with patch.object(executor, '_ensure_connection', return_value=True), \
             patch.object(executor, 'move_to_breakeven') as mock_move:

            mock_move.return_value = {'success': True, 'new_sl': 1.14605}

            simulated_pos = [{
                'ticket': 1909954115,
                'symbol': 'EURUSDm',
                'type': 'SELL',
                'price_open': 1.14595,
                'price_current': 1.14580,  # in profit on SELL
                'sl': 1.14756,  # original SL
                'tp': 1.14435,
                'magic': executor.MAGIC_NUMBER,
                'comment': 'QS_731600_TP2',
                'return_pct': 0.013  # Forex scalp micro percentage
            }]

            batch_info_map = {
                '731600': {
                    'entry_price': 1.14595,
                    'sl_price': 1.14756,
                    'tp1_price': 1.14575,
                    'tp2_price': 1.14435,
                    'breakeven_sl': 1.14605,
                    'soft_breakeven_sl': 1.14644,
                    'breakeven_mode': 'tight',
                    'tickets': [1909954107, 1909954115, 1909954119]
                }
            }

            with patch.object(executor, 'get_open_positions', return_value=simulated_pos):
                import MetaTrader5 as mt5
                # Broker deal where comment has NO 'QS_' and is overwritten with '[tp 1.14575]'
                mock_deal = MagicMock()
                mock_deal.profit = 0.40
                mock_deal.entry = 1
                mock_deal.comment = '[tp 1.14575]'
                mock_deal.position_id = 1909954107  # matches TP1 ticket
                mock_deal.order = 0
                mock_deal.symbol = 'EURUSDm'
                mock_deal.magic = executor.MAGIC_NUMBER

                with patch.object(mt5, 'history_deals_get', return_value=[mock_deal]), \
                     patch.object(mt5, 'history_orders_get', return_value=[]):
                    # Tight mode check: Must detect TP1 via position_id map and snap to BE!
                    res_tight = executor.check_and_apply_auto_breakeven(
                        batch_breakeven_sl_map={'731600': 1.14605},
                        batch_info_map=batch_info_map,
                        breakeven_mode='tight'
                    )
                    self.assertEqual(len(res_tight), 1)
                    self.assertEqual(res_tight[0]['mode'], 'TIGHT')
                    self.assertEqual(res_tight[0]['new_sl'], 1.14605)
                    mock_move.assert_called_with(1909954115, target_sl=1.14605)

                    # Loose mode check on batch override
                    batch_info_map['731600']['breakeven_mode'] = 'loose'
                    mock_move.reset_mock()
                    mock_move.return_value = {'success': True, 'new_sl': 1.14644}
                    res_loose = executor.check_and_apply_auto_breakeven(
                        batch_breakeven_sl_map={'731600': 1.14605},
                        batch_info_map=batch_info_map,
                        breakeven_mode='loose'
                    )
                    self.assertEqual(len(res_loose), 1)
                    self.assertEqual(res_loose[0]['mode'], 'LOOSE_STAGE_1')
                    self.assertEqual(res_loose[0]['new_sl'], 1.14644)
                    mock_move.assert_called_with(1909954115, target_sl=1.14644)

if __name__ == '__main__':
    unittest.main()

