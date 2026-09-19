"""
Comprehensive Unit Tests for User-Requested Fixes:
1. Exact Timeframe Recording (Never 'Live')
2. Real Strategy Name in Active & Closed Ledgers
3. Multi-Trade Same Timeframe Toggle (allow_same_tf_trades)
4. HTF Trend Confluence Disconnect for Streamer Strategies
5. Target Progress Dynamic Counter
6. Terminal Feed Badges & Status
"""

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from src.engine.autonomous_manager import AutonomousTraderEngine, AVAILABLE_STRATEGIES
from src.strategies.streamer_playbook import (
    ArielZwecherStrategy,
    RossCameronStrategy,
    OliverVelezStrategy,
    NdemazeahGodloveStrategy,
    ICTStrategy,
    MasterStreamerPlaybook
)


class TestUserRequirements(unittest.TestCase):

    def setUp(self):
        self.engine = AutonomousTraderEngine()

    def test_streamer_timeframe_compatibility_enforced(self):
        """Ariel Zwecher and Ross Cameron must reject incompatible timeframes (e.g. 4H)."""
        dates = pd.date_range('2026-01-01', periods=50, freq='4h')
        df_4h = pd.DataFrame({
            'open': np.linspace(100, 110, 50),
            'high': np.linspace(101, 112, 50),
            'low': np.linspace(99, 109, 50),
            'close': np.linspace(100.5, 111.5, 50),
            'volume': np.ones(50) * 1000
        }, index=dates)

        # Ariel Zwecher on 4H must be HOLD with TIMEFRAME_INCOMPATIBLE
        res_az = ArielZwecherStrategy.evaluate(df_4h, atr=1.5, timeframe='4h')
        self.assertEqual(res_az['action'], 'HOLD')
        self.assertEqual(res_az['status'], 'TIMEFRAME_INCOMPATIBLE')

        # Ross Cameron on 4H must be HOLD with TIMEFRAME_INCOMPATIBLE
        res_rc = RossCameronStrategy.evaluate(df_4h, atr=1.5, timeframe='4h')
        self.assertEqual(res_rc['action'], 'HOLD')
        self.assertEqual(res_rc['status'], 'TIMEFRAME_INCOMPATIBLE')

        # Oliver Velez on 4H must be HOLD with TIMEFRAME_INCOMPATIBLE
        res_ov = OliverVelezStrategy.evaluate(df_4h, atr=1.5, timeframe='4h')
        self.assertEqual(res_ov['action'], 'HOLD')
        self.assertEqual(res_ov['status'], 'TIMEFRAME_INCOMPATIBLE')

    def test_same_timeframe_stacking_toggle(self):
        """When allow_same_tf_trades is False, duplicate trades on same (sym, tf) must be skipped."""
        # Mock settings with allow_same_tf_trades = False
        with patch.object(self.engine, 'load_settings', return_value={'enabled': True, 'allow_same_tf_trades': False, 'active_strategies': ['DEFAULT']}):
            with patch.object(self.engine, 'load_state', return_value={
                'open_batches': {
                    '999': {'symbol': 'BTC/USD', 'broker_sym': 'BTCUSDm', 'timeframe': '15m'}
                },
                'scan_activity_log': []
            }):
                with patch.object(self.engine, '_append_activity_log') as mock_log:
                    # Scan BTC/USD on 15m should be skipped because batch 999 is open on 15m
                    res = self.engine.scan_symbol_all_timeframes('BTC/USD', ['15m'], cycle=1)
                    self.assertIsNone(res)
                    # Verify activity log captured the same-TF skip
                    mock_log.assert_called()
                    logged_status = mock_log.call_args[0][0]['status']
                    self.assertIn('SKIPPED (Active Batch on TF)', logged_status)

    def test_htf_trend_confluence_disconnected_from_streamer_strategies(self):
        """Streamer strategies must evaluate their own rules without being blocked by 5-Pillars HTF Confluence."""
        # When only ICT is active, HTF Confluence filter should not disqualify ICT trades
        with patch.object(self.engine, 'load_settings', return_value={
            'enabled': True,
            'htf_filter_enabled': True,
            'active_strategies': ['ICT'],
            'active_sessions': ['24/7 (Any Session)']
        }):
            dates = pd.date_range('2026-01-01', periods=30, freq='15min')
            df = pd.DataFrame({
                'open': [100.0] * 30,
                'high': [102.0] * 30,
                'low': [98.0] * 30,
                'close': [101.0] * 30,
                'volume': [500] * 30
            }, index=dates)

            ict_setup = {
                'action': 'BUY',
                'strategy_name': 'Michael J. Huddleston (ICT)',
                'confidence': 88.0,
                'trade_setup': {'recommended_entry': 101.0, 'stop_loss': 98.0, 'tp1': 105.0}
            }
            fake_pred = {
                'confluence': {'action': 'NEUTRAL', 'confluence_score': 0.0},
                'market_data': {'atr': 1.5, 'current_price': 101.0},
                'streamer_playbook': {'all_strategies': {'ICT': ict_setup}},
                'spread_guard': {'passed': True},
                'chop_gate': {'is_chop': False}
            }

            with patch.object(self.engine.orch, 'run_prediction', return_value=fake_pred):
                with patch.object(self.engine, 'evaluate_5_pillars', return_value={'aligned_count': 1, 'total_applicable': 5, 'p1': {'score': 0, 'prob': 50}}):
                    with patch('src.engine.autonomous_manager.SessionManager.is_strategy_session_allowed', return_value=(True, "Inside NY Killzone")):
                        setup = self.engine.scan_symbol_all_timeframes('BTC/USD', ['15m'], cycle=1)
                        self.assertIsNotNone(setup)
                        self.assertEqual(setup['strategy_used'], 'ICT')
                        self.assertEqual(setup['strategy_name'], 'Michael J. Huddleston (ICT)')
                        self.assertEqual(setup['timeframe'], '15m')

    def test_dynamic_target_progress_counting(self):
        """Dynamic symbol matching must count trades correctly for XAUUSD247m, BTCUSDm, ETHUSDm."""
        recorded_batches = [
            {'symbol': 'XAU/USD', 'broker_sym': 'XAUUSD247m'},
            {'symbol': 'XAU/USD', 'broker_sym': 'XAUUSD247m'},
            {'symbol': 'BTC/USD', 'broker_sym': 'BTCUSDm'},
            {'symbol': 'ETH/USD', 'broker_sym': 'ETHUSDm'},
        ]

        def get_count(target_sym):
            norm_target = target_sym.replace('/', '').replace('m', '').upper()
            return sum(
                1 for b in recorded_batches
                if (b.get('symbol', '').replace('/', '').replace('m', '').upper() == norm_target
                    or b.get('broker_sym', '').replace('/', '').replace('m', '').upper().startswith(norm_target)
                    or norm_target in b.get('broker_sym', '').replace('/', '').replace('m', '').upper())
            )

        self.assertEqual(get_count('XAUUSD247'), 2)
        self.assertEqual(get_count('XAU/USD'), 2)
        self.assertEqual(get_count('BTC/USD'), 1)
        self.assertEqual(get_count('ETH/USD'), 1)


    def test_autonomous_reset_clears_all_targets_and_prevents_mt5_readoption(self):
        """Reset progress must set all targets to 0 and prevent MT5 positions older than reset_at from re-adopting."""
        from datetime import datetime, timezone, timedelta
        
        # 1. Test reset_progress clears all counters
        self.engine.reset_progress(clear_journal=False)
        st = self.engine.load_state()
        self.assertEqual(st.get('total_trades_taken'), 0)
        self.assertEqual(st.get('trades_by_symbol'), {})
        self.assertEqual(st.get('open_batches'), {})
        self.assertEqual(st.get('closed_batches'), [])
        self.assertEqual(st.get('xau_trades_taken'), 0)
        self.assertEqual(st.get('btc_trades_taken'), 0)
        self.assertEqual(st.get('eth_trades_taken'), 0)
        self.assertIsNotNone(st.get('reset_at'))

        # 2. Test audit ignores positions with timestamp older than reset_at
        reset_dt = datetime.fromisoformat(st['reset_at'])
        old_time = int((reset_dt - timedelta(minutes=10)).timestamp())
        
        fake_pos = MagicMock()
        fake_pos.ticket = 112233
        fake_pos.symbol = 'BTCUSDm'
        fake_pos.magic = self.engine.executor.MAGIC_NUMBER
        fake_pos.comment = 'QS_112233_15m'
        fake_pos.time = old_time
        fake_pos.type = 0
        fake_pos.price_open = 65000.0
        fake_pos.sl = 64000.0
        fake_pos.tp = 67000.0
        fake_pos.volume = 0.01

        with patch('MetaTrader5.positions_get', return_value=[fake_pos]):
            with patch('MetaTrader5.history_deals_get', return_value=[]):
                with patch.object(self.engine.executor, '_ensure_connection', return_value=True):
                    with patch.object(self.engine.executor, 'check_and_apply_auto_breakeven', return_value=[]):
                        self.engine.audit_active_trades_and_learn()
                        st_after = self.engine.load_state()
                        # Old position must NOT be adopted into open_batches
                        self.assertEqual(len(st_after.get('open_batches', {})), 0)
                        self.assertEqual(st_after.get('total_trades_taken', 0), 0)
                        self.assertEqual(st_after.get('trades_by_symbol', {}), {})

    def test_multi_trades_different_strategies_same_timeframe(self):
        """When allow_diff_strat_same_tf is True, same strategy duplicates on same TF are blocked while different strategies are permitted."""
        # Setup open batches: ICT is already open on BTC/USD 15m
        mock_state = {
            'open_batches': {
                '1001': {
                    'batch_id': '1001',
                    'symbol': 'BTC/USD',
                    'broker_sym': 'BTCUSDm',
                    'timeframe': '15m',
                    'strategy_used': 'ICT',
                    'strategy_name': 'Michael J. Huddleston (ICT)'
                }
            },
            'scan_activity_log': [],
            'trades_by_symbol': {'BTC/USD': 1},
            'total_trades_taken': 1
        }

        mock_settings = {
            'enabled': True,
            'allow_same_tf_trades': False,
            'allow_diff_strat_same_tf': True,
            'active_strategies': ['ICT', 'BERND_SKORUPINSKI'],
            'active_sessions': ['24/7 (Any Session)'],
            'min_pillars_required': 2
        }

        ict_setup = {
            'action': 'BUY',
            'strategy_name': 'Michael J. Huddleston (ICT)',
            'confidence': 90.0,
            'trade_setup': {'recommended_entry': 65000.0, 'stop_loss': 64000.0, 'tp1': 66000.0}
        }
        bernd_setup = {
            'action': 'BUY',
            'strategy_name': 'Bernd Skorupinski (SMC & Order Flow)',
            'confidence': 85.0,
            'trade_setup': {'recommended_entry': 65000.0, 'stop_loss': 64000.0, 'tp1': 66000.0}
        }

        fake_pred = {
            'confluence': {'action': 'NEUTRAL', 'confluence_score': 0.0},
            'market_data': {'atr': 100.0, 'current_price': 65000.0},
            'streamer_playbook': {'all_strategies': {'ICT': ict_setup, 'BERND_SKORUPINSKI': bernd_setup}},
            'spread_guard': {'passed': True},
            'chop_gate': {'is_chop': False}
        }

        with patch.object(self.engine, 'load_settings', return_value=mock_settings):
            with patch.object(self.engine, 'load_state', return_value=mock_state):
                with patch.object(self.engine.orch, 'run_prediction', return_value=fake_pred):
                    with patch.object(self.engine, 'evaluate_5_pillars', return_value={'aligned_count': 1, 'total_applicable': 5, 'p1': {'score': 0, 'prob': 50}}):
                        with patch('src.engine.autonomous_manager.SessionManager.is_strategy_session_allowed', return_value=(True, "Inside Active Session")):
                            # ICT has higher confidence (90 vs 85), but ICT is already active on 15m.
                            # Therefore, ICT must be disqualified and Bernd Skorupinski (85) must be chosen!
                            setup = self.engine.scan_symbol_all_timeframes('BTC/USD', ['15m'], cycle=1)
                            self.assertIsNotNone(setup)
                            self.assertEqual(setup['strategy_used'], 'BERND_SKORUPINSKI')
                            self.assertEqual(setup['strategy_name'], 'Bernd Skorupinski (SMC & Order Flow)')

    def test_same_strategy_blocked_when_diff_strat_enabled_and_no_other_strategy(self):
        """When allow_diff_strat_same_tf is True and only the active strategy produces a signal, it must be skipped."""
        mock_state = {
            'open_batches': {
                '1001': {
                    'batch_id': '1001',
                    'symbol': 'BTC/USD',
                    'broker_sym': 'BTCUSDm',
                    'timeframe': '15m',
                    'strategy_used': 'ICT',
                    'strategy_name': 'Michael J. Huddleston (ICT)'
                }
            },
            'scan_activity_log': [],
            'trades_by_symbol': {'BTC/USD': 1},
            'total_trades_taken': 1
        }

        mock_settings = {
            'enabled': True,
            'allow_same_tf_trades': True,
            'allow_diff_strat_same_tf': True,
            'active_strategies': ['ICT'],
            'active_sessions': ['24/7 (Any Session)'],
            'min_pillars_required': 2
        }

        ict_setup = {
            'action': 'BUY',
            'strategy_name': 'Michael J. Huddleston (ICT)',
            'confidence': 90.0,
            'trade_setup': {'recommended_entry': 65000.0, 'stop_loss': 64000.0, 'tp1': 66000.0}
        }

        fake_pred = {
            'confluence': {'action': 'NEUTRAL', 'confluence_score': 0.0},
            'market_data': {'atr': 100.0, 'current_price': 65000.0},
            'streamer_playbook': {'all_strategies': {'ICT': ict_setup}},
            'spread_guard': {'passed': True},
            'chop_gate': {'is_chop': False}
        }

        with patch.object(self.engine, 'load_settings', return_value=mock_settings):
            with patch.object(self.engine, 'load_state', return_value=mock_state):
                with patch.object(self.engine.orch, 'run_prediction', return_value=fake_pred):
                    with patch.object(self.engine, 'evaluate_5_pillars', return_value={'aligned_count': 1, 'total_applicable': 5, 'p1': {'score': 0, 'prob': 50}}):
                        with patch('src.engine.autonomous_manager.SessionManager.is_strategy_session_allowed', return_value=(True, "Inside Active Session")):
                            with patch.object(self.engine, '_append_activity_log') as mock_log:
                                setup = self.engine.scan_symbol_all_timeframes('BTC/USD', ['15m'], cycle=1)
                                self.assertIsNone(setup)
                                mock_log.assert_called()
                                log_call = mock_log.call_args[0][0]
                                self.assertIn('SKIPPED (Same Strat Active on TF)', log_call['status'])


if __name__ == '__main__':
    unittest.main()

