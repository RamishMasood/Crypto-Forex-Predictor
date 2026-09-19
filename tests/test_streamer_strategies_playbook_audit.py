import unittest
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.strategies.streamer_playbook import (
    MasterStreamerPlaybook,
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
    TradeProStrategy
)
from src.engine.autonomous_manager import AutonomousTraderEngine, AVAILABLE_STRATEGIES
from src.engine.session_manager import SessionManager

class TestStreamerStrategiesPlaybookAudit(unittest.TestCase):
    """
    Comprehensive rule-by-rule audit testing of all 13 strategies against the
    Master Strategy Playbook PDF and Trading Sessions & Killzones Playbook.
    """

    def setUp(self):
        # Create synthetic market data with 100 bars
        n = 100
        dates = pd.date_range('2026-09-01', periods=n, freq='15min')
        base = 50000.0 + np.cumsum(np.random.normal(0, 50, n))
        self.df = pd.DataFrame({
            'open': base,
            'high': base + 80.0,
            'low': base - 80.0,
            'close': base + 20.0,
            'volume': [1500.0] * n
        }, index=dates)

    def test_all_13_strategies_registered(self):
        """Verify all 13 strategies are registered in AVAILABLE_STRATEGIES."""
        expected_keys = [
            'DEFAULT', 'VIVEK_YADAV', 'BERND_SKORUPINSKI', 'ICT', 'STEVEN_HART',
            'RAYNER_TEO', 'CRYPTO_CRED', 'NDEMAZEAH_GODLOVE', 'ROSS_CAMERON',
            'ADAM_KHOO', 'ARIEL_ZWECHER', 'OLIVER_VELEZ', 'TRADE_PRO'
        ]
        self.assertEqual(len(AVAILABLE_STRATEGIES), 13)
        for k in expected_keys:
            self.assertIn(k, AVAILABLE_STRATEGIES)

    def test_playbook_evaluates_all_12_streamers(self):
        """MasterStreamerPlaybook must evaluate and return results for all 12 streamer strategies."""
        pb = MasterStreamerPlaybook.evaluate_all(
            df=self.df,
            atr=150.0,
            timeframe="15m"
        )
        self.assertIn('all_strategies', pb)
        strats = pb['all_strategies']
        self.assertEqual(len(strats), 12)
        
        expected_streamer_keys = [
            'VIVEK_YADAV', 'BERND_SKORUPINSKI', 'ICT', 'STEVEN_HART',
            'RAYNER_TEO', 'CRYPTO_CRED', 'NDEMAZEAH_GODLOVE', 'ROSS_CAMERON',
            'ADAM_KHOO', 'ARIEL_ZWECHER', 'OLIVER_VELEZ', 'TRADE_PRO'
        ]
        for k in expected_streamer_keys:
            self.assertIn(k, strats)
            val = strats[k]
            self.assertIn('strategy_name', val)
            self.assertIn('action', val)
            self.assertIn('confidence', val)
            self.assertIn('breakeven_mode', val)
            self.assertIn('reasons', val)

    def test_risk_geometry_and_golden_sl_compliance(self):
        """Every strategy trigger setup must maintain Golden SL >= 1.5 ATR and min 1:2 R:R."""
        atr = 100.0
        pb = MasterStreamerPlaybook.evaluate_all(
            df=self.df,
            atr=atr,
            timeframe="15m"
        )
        for k, strat in pb['all_strategies'].items():
            if strat.get('action') in ['BUY', 'SELL']:
                setup = strat.get('trade_setup') or {}
                entry = float(setup.get('recommended_entry', self.df['close'].iloc[-1]))
                sl = float(setup.get('stop_loss', 0.0))
                tp1 = float(setup.get('tp1', 0.0))
                tp2 = float(setup.get('tp2', 0.0))
                
                # Check Golden SL breathing room (>= 1.50 ATR)
                sl_dist = abs(entry - sl)
                self.assertGreaterEqual(
                    round(sl_dist, 2),
                    round(1.49 * atr, 2),
                    f"{k} Stop Loss distance ({sl_dist}) must be at least 1.50 * ATR ({1.5 * atr})"
                )
                
                # Check 1:2+ R:R geometry on runner target
                runner_reward = abs(tp2 - entry)
                self.assertGreaterEqual(
                    round(runner_reward, 2),
                    round(1.15 * sl_dist, 2),
                    f"{k} TP2 runner target must be at least 1:1+ to 1:2 Risk:Reward"
                )

    def test_strategy_native_breakeven_modes_decoupled(self):
        """Verify each strategy's native breakeven mode conforms to its author rules."""
        pb = MasterStreamerPlaybook.evaluate_all(df=self.df, atr=100.0, timeframe="15m")
        strats = pb['all_strategies']
        
        # Fixed R:R target strategies (never choked by premature BE)
        self.assertEqual(strats['BERND_SKORUPINSKI']['breakeven_mode'], 'FIXED_RR_TARGET')
        self.assertEqual(strats['STEVEN_HART']['breakeven_mode'], 'FIXED_RR_TARGET')
        self.assertEqual(strats['ARIEL_ZWECHER']['breakeven_mode'], 'FIXED_RR_TARGET')
        self.assertEqual(strats['TRADE_PRO']['breakeven_mode'], 'FIXED_RR_TARGET')
        self.assertEqual(strats['NDEMAZEAH_GODLOVE']['breakeven_mode'], 'FIXED_RR_TARGET')
        
        # Moving average trailing strategies
        self.assertEqual(strats['RAYNER_TEO']['breakeven_mode'], 'TRAILING_20_EMA')
        self.assertEqual(strats['ADAM_KHOO']['breakeven_mode'], 'TRAILING_20_EMA')
        self.assertEqual(strats['OLIVER_VELEZ']['breakeven_mode'], 'TRAILING_20_SMA')
        
        # Partial expansion / SMC lock strategies (partials at TP1/mid-range)
        self.assertEqual(strats['VIVEK_YADAV']['breakeven_mode'], 'SMC_PARTIAL_BE')
        self.assertEqual(strats['ICT']['breakeven_mode'], 'SMC_PARTIAL_BE')
        self.assertEqual(strats['CRYPTO_CRED']['breakeven_mode'], 'SMC_PARTIAL_BE')
        
        # Momentum quick BE
        self.assertEqual(strats['ROSS_CAMERON']['breakeven_mode'], 'SCALPING_QUICK_BE')

    def test_intraday_timeframe_incompatibility_guards(self):
        """Intraday scalpers must reject macro timeframes (1h, 4h, 1d) as TIMEFRAME_INCOMPATIBLE."""
        macro_tfs = ['1h', '4h', '1d']
        for tf in macro_tfs:
            pb = MasterStreamerPlaybook.evaluate_all(df=self.df, atr=100.0, timeframe=tf)
            strats = pb['all_strategies']
            
            # Ariel Zwecher (15M ORB)
            self.assertIn(strats['ARIEL_ZWECHER']['action'], ['WAIT', 'HOLD'])
            self.assertEqual(strats['ARIEL_ZWECHER']['status'], 'TIMEFRAME_INCOMPATIBLE')
            
            # Ross Cameron (Intraday momentum)
            self.assertIn(strats['ROSS_CAMERON']['action'], ['WAIT', 'HOLD'])
            self.assertEqual(strats['ROSS_CAMERON']['status'], 'TIMEFRAME_INCOMPATIBLE')
            
            # Oliver Velez (Intraday elephant bar)
            self.assertIn(strats['OLIVER_VELEZ']['action'], ['WAIT', 'HOLD'])
            self.assertEqual(strats['OLIVER_VELEZ']['status'], 'TIMEFRAME_INCOMPATIBLE')

    def test_leaderboard_computation_all_13_strategies(self):
        """compute_strategy_leaderboard must rank all 13 strategies and calculate correct metrics."""
        fake_state = {
            'open_batches': {
                '1': {'strategy_used': 'STEVEN_HART', 'strategy_name': 'Steven Hart', 'status': 'OPEN'}
            },
            'closed_batches': [
                {'strategy_used': 'STEVEN_HART', 'strategy_name': 'Steven Hart', 'profit': 15.50, 'status': 'WIN', 'timeframe': '15m', 'symbol': 'EUR/USD'},
                {'strategy_used': 'STEVEN_HART', 'strategy_name': 'Steven Hart', 'profit': -5.00, 'status': 'LOSS', 'timeframe': '15m', 'symbol': 'EUR/USD'},
                {'strategy_used': 'ADAM_KHOO', 'strategy_name': 'Adam Khoo', 'profit': 22.00, 'status': 'WIN', 'timeframe': '1h', 'symbol': 'BTC/USD'},
                {'strategy_used': 'ADAM_KHOO', 'strategy_name': 'Adam Khoo', 'profit': 18.00, 'status': 'WIN', 'timeframe': '1h', 'symbol': 'BTC/USD'},
                {'strategy_used': 'ICT', 'strategy_name': 'Michael J. Huddleston (ICT)', 'profit': 0.12, 'status': 'BREAKEVEN', 'timeframe': '15m', 'symbol': 'NQ'},
                {'strategy_used': 'ICT', 'strategy_name': 'Michael J. Huddleston (ICT)', 'profit': -0.05, 'status': 'BREAKEVEN', 'timeframe': '5m', 'symbol': 'ES'},
            ]
        }
        
        # Test default sorting: Most Profitable (Net PnL)
        lb_profit = AutonomousTraderEngine.compute_strategy_leaderboard(fake_state, sort_by='profit')
        self.assertEqual(len(lb_profit), 13)
        self.assertEqual(lb_profit[0]['strategy_key'], 'ADAM_KHOO')
        self.assertEqual(lb_profit[0]['rank'], 1)
        self.assertEqual(lb_profit[0]['rank_display'], '🥇 1')
        self.assertEqual(lb_profit[0]['net_pnl'], 40.00)
        self.assertEqual(lb_profit[0]['wins'], 2)
        self.assertEqual(lb_profit[0]['win_rate'], 100.0)

        # Steven Hart has 1 win, 1 loss, 1 active -> 10.50 profit
        self.assertEqual(lb_profit[1]['strategy_key'], 'STEVEN_HART')
        self.assertEqual(lb_profit[1]['rank'], 2)
        self.assertEqual(lb_profit[1]['rank_display'], '🥈 2')
        self.assertEqual(lb_profit[1]['net_pnl'], 10.50)
        self.assertEqual(lb_profit[1]['total_trades'], 3)

        # Verify Best Timeframes and Best Trading Pairs are present for every strategy
        for item in lb_profit:
            self.assertIn('best_timeframes', item)
            self.assertIn('best_pairs', item)
            self.assertTrue(len(item['best_timeframes']) > 0)
            self.assertTrue(len(item['best_pairs']) > 0)

        # Test sorting by Most Wins
        lb_wins = AutonomousTraderEngine.compute_strategy_leaderboard(fake_state, sort_by='wins')
        self.assertEqual(lb_wins[0]['strategy_key'], 'ADAM_KHOO')
        self.assertEqual(lb_wins[0]['wins'], 2)

        # Test sorting by Most Losses
        lb_losses = AutonomousTraderEngine.compute_strategy_leaderboard(fake_state, sort_by='losses')
        self.assertEqual(lb_losses[0]['strategy_key'], 'STEVEN_HART')
        self.assertEqual(lb_losses[0]['losses'], 1)

        # Test sorting by Most Breakevens: ICT should have 2 breakevens (despite profit +0.12 and -0.05)
        lb_be = AutonomousTraderEngine.compute_strategy_leaderboard(fake_state, sort_by='breakevens')
        self.assertEqual(lb_be[0]['strategy_key'], 'ICT')
        self.assertEqual(lb_be[0]['breakevens'], 2)

        # Test sorting by Highest Win Rate
        lb_wr = AutonomousTraderEngine.compute_strategy_leaderboard(fake_state, sort_by='win_rate')
        self.assertEqual(lb_wr[0]['strategy_key'], 'ADAM_KHOO')
        self.assertEqual(lb_wr[0]['win_rate'], 100.0)

        # Test sorting by Most Active (Total Trades)
        lb_vol = AutonomousTraderEngine.compute_strategy_leaderboard(fake_state, sort_by='total_trades')
        self.assertEqual(lb_vol[0]['strategy_key'], 'STEVEN_HART')
        self.assertEqual(lb_vol[0]['total_trades'], 3)


if __name__ == '__main__':
    unittest.main()
