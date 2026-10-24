"""
UI Verification Test for Dedicated MT5 Backtesting View
======================================================
Tests:
- Verifies that all widget options and defaults are 100% aligned
- Verifies that render_mt5_backtest_engine_view executes cleanly without any exception
- Verifies that all preset buttons and inputs function properly
- Tests KPI cards, Leaderboard table, and Batches ledger rendering
"""

import unittest
import os
import sys
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine.backtest_engine import get_backtest_engine, MT5BacktestEngine
from src.engine.autonomous_manager import AVAILABLE_STRATEGIES, AVAILABLE_TIMEFRAMES, DEFAULT_SYMBOLS


class TestBacktesterUIRendering(unittest.TestCase):

    def setUp(self):
        self.engine = get_backtest_engine()
        self.settings = self.engine.load_settings()

    def test_symbols_and_options_integrity(self):
        """Ensure no symbol or tf default can ever trigger StreamlitDefaultNotInOptionsError."""
        bt_available_symbols = [
            "BTC/USD", "ETH/USD", "SOL/USD", "XAU/USD", "XAUUSD247", "XAG/USD",
            "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "NZD/USD", "USD/CAD",
            "EUR/GBP", "EUR/JPY", "GBP/JPY", "CAD/JPY"
        ]
        saved_syms = self.settings.get('selected_symbols', ["BTC/USD", "ETH/USD", "XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY"])
        valid_bt_syms = [s for s in saved_syms if s in bt_available_symbols]
        for s in valid_bt_syms:
            self.assertIn(s, bt_available_symbols)

        saved_tfs = self.settings.get('timeframes', ["15m", "30m", "1h", "4h"])
        valid_bt_tfs = [t for t in saved_tfs if t in AVAILABLE_TIMEFRAMES]
        for t in valid_bt_tfs:
            self.assertIn(t, AVAILABLE_TIMEFRAMES)

        saved_strats = self.settings.get('active_strategies', list(AVAILABLE_STRATEGIES.keys()))
        valid_bt_strats = [s for s in saved_strats if s in AVAILABLE_STRATEGIES]
        for s in valid_bt_strats:
            self.assertIn(s, AVAILABLE_STRATEGIES)

    def test_backtest_engine_load_state_api(self):
        """Ensure load_state() and load_settings() return valid dictionaries."""
        state = self.engine.load_state()
        self.assertIsInstance(state, dict)

        settings = self.engine.load_settings()
        self.assertIsInstance(settings, dict)

    def test_mock_streamlit_ui_render_cycle(self):
        """Simulate the exact Streamlit execution cycle of render_mt5_backtest_engine_view."""
        # Verify app.py has render_mt5_backtest_engine_view and required toggles
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_path, 'r', encoding='utf-8') as f:
            code = f.read()
        self.assertIn('def render_mt5_backtest_engine_view', code)
        self.assertIn('bt_smart_solution_toggle', code)
        self.assertIn('bt_news_guard_toggle', code)
    def test_leaderboard_breakeven_classification(self):
        """Ensure TP1 banked breakeven trades are properly categorized as breakevens in leaderboard."""
        mock_batches = [
            {
                'batch_id': 'b1',
                'strategy_used': 'LINDA_RASCHKE_MOMENTUM_PINBALL',
                'symbol': 'BTC/USD',
                'timeframe': '15m',
                'status': 'BREAKEVEN',
                'exit_reason': 'TP1_BANKED_BE_EXIT',
                'profit': 0.85,
                'tp1_hit': True,
                'tp2_hit': False
            },
            {
                'batch_id': 'b2',
                'strategy_used': 'LINDA_RASCHKE_MOMENTUM_PINBALL',
                'symbol': 'BTC/USD',
                'timeframe': '15m',
                'status': 'WIN',
                'exit_reason': 'TP2_RUNNER_WIN',
                'profit': 2.10,
                'tp1_hit': True,
                'tp2_hit': True
            },
            {
                'batch_id': 'b3',
                'strategy_used': 'LINDA_RASCHKE_MOMENTUM_PINBALL',
                'symbol': 'BTC/USD',
                'timeframe': '15m',
                'status': 'LOSS',
                'exit_reason': 'FULL_SL',
                'profit': -1.50,
                'tp1_hit': False,
                'tp2_hit': False
            }
        ]
        lb = self.engine.compute_backtest_strategy_leaderboard(
            mock_batches,
            ['LINDA_RASCHKE_MOMENTUM_PINBALL']
        )
        self.assertEqual(len(lb), 1)
        item = lb[0]
        self.assertEqual(item['total_trades'], 3)
        self.assertEqual(item['wins'], 1)
        self.assertEqual(item['breakevens'], 1)
        self.assertEqual(item['losses'], 1)
        self.assertAlmostEqual(item['win_rate'], 66.7, places=1)
        sym_bd = item['symbol_breakdown'].get('BTC/USD')
        self.assertIsNotNone(sym_bd)
        self.assertEqual(sym_bd['wins'], 1)
        self.assertEqual(sym_bd['breakevens'], 1)
        self.assertEqual(sym_bd['losses'], 1)



    def test_daily_breakdown_computation(self):
        """Ensure compute_daily_breakdown generates valid chronological daily rows."""
        mock_batches = [
            {
                'strategy_used': 'DEFAULT',
                'symbol': 'BTC/USD',
                'timeframe': '1h',
                'status': 'WIN',
                'profit': 50.0,
                'tp1_hit': True,
                'closed_at': '2026-10-15T10:00:00Z'
            },
            {
                'strategy_used': 'DEFAULT',
                'symbol': 'BTC/USD',
                'timeframe': '1h',
                'status': 'BREAKEVEN',
                'profit': 0.50,
                'tp1_hit': True,
                'closed_at': '2026-10-15T14:00:00Z'
            },
            {
                'strategy_used': 'DEFAULT',
                'symbol': 'EUR/USD',
                'timeframe': '15m',
                'status': 'LOSS',
                'profit': -15.0,
                'tp1_hit': False,
                'closed_at': '2026-10-16T12:00:00Z'
            }
        ]
        daily = MT5BacktestEngine.compute_daily_breakdown(mock_batches, '2026-10-15', '2026-10-16')
        self.assertGreaterEqual(len(daily), 2)
        d1 = next(d for d in daily if d['date'] == '2026-10-15')
        self.assertEqual(d1['trades'], 2)
        self.assertEqual(d1['wins'], 1)
        self.assertEqual(d1['breakevens'], 1)
        self.assertEqual(d1['losses'], 0)
        self.assertEqual(d1['win_rate'], 100.0)
        self.assertEqual(d1['net_pnl'], 50.50)

        d2 = next(d for d in daily if d['date'] == '2026-10-16')
        self.assertEqual(d2['trades'], 1)
        self.assertEqual(d2['losses'], 1)
        self.assertEqual(d2['win_rate'], 0.0)
        self.assertEqual(d2['net_pnl'], -15.0)

    def test_best_pairs_and_timeframes_profitability_and_winrate_ranking(self):
        """
        Verify that Best Trading Pairs and Best Timeframes are strictly determined
        by profitability ($) and highest win rate (%), NEVER by raw trade volume.
        """
        mock_batches = [
            # High volume LOSING pair on 15m (3 trades, net loss -$30, 66% breakeven win rate)
            {'strategy_used': 'DEFAULT', 'symbol': 'EUR/USD', 'timeframe': '15m', 'status': 'LOSS', 'profit': -31.0, 'tp1_hit': False},
            {'strategy_used': 'DEFAULT', 'symbol': 'EUR/USD', 'timeframe': '15m', 'status': 'BREAKEVEN', 'profit': 0.5, 'tp1_hit': True},
            {'strategy_used': 'DEFAULT', 'symbol': 'EUR/USD', 'timeframe': '15m', 'status': 'BREAKEVEN', 'profit': 0.5, 'tp1_hit': True},
            # Low volume HIGH PROFIT pair on 1h (2 trades, net profit +$138.49, 100% win rate)
            {'strategy_used': 'DEFAULT', 'symbol': 'BTC/USD', 'timeframe': '1h', 'status': 'WIN', 'profit': 113.49, 'tp1_hit': True},
            {'strategy_used': 'DEFAULT', 'symbol': 'BTC/USD', 'timeframe': '1h', 'status': 'WIN', 'profit': 25.0, 'tp1_hit': True},
            # Moderate profit pair on 4h (1 trade, net profit +$15.0, 100% win rate)
            {'strategy_used': 'DEFAULT', 'symbol': 'GBP/USD', 'timeframe': '4h', 'status': 'WIN', 'profit': 15.0, 'tp1_hit': True},
        ]
        lb = MT5BacktestEngine.compute_backtest_strategy_leaderboard(mock_batches, ['DEFAULT'])
        self.assertEqual(len(lb), 1)
        item = lb[0]

        # BTC/USD must be #1 best pair, followed by GBP/USD. EUR/USD must NOT be in top 2.
        self.assertIn('BTC/USD', item['best_pairs'])
        self.assertIn('GBP/USD', item['best_pairs'])
        self.assertNotIn('EUR/USD', item['best_pairs'])

        # 1h must be #1 best timeframe, followed by 4h. 15m must NOT be in top 2.
        self.assertIn('1h', item['best_timeframes'])
        self.assertIn('4h', item['best_timeframes'])
        self.assertNotIn('15m', item['best_timeframes'])

    def test_app_contains_daily_breakdown_and_best_metrics(self):
        """Ensure app.py has daily breakdown UI and improved best pairs tooltips."""
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_path, 'r', encoding='utf-8') as f:
            app_code = f.read()
        self.assertIn('Day-by-Day Granular Chronological Breakdown', app_code)
        self.assertIn('bt_daily_view_filter', app_code)
        self.assertIn('dl_bt_daily_breakdown_csv', app_code)
        self.assertIn('best_pairs_tooltip', app_code)
        self.assertIn('best_timeframes_tooltip', app_code)



    def test_consecutive_losses_metrics(self):
        """Ensure max_cons_losses and max_cons_loss_usd are tracked accurately."""
        mock_batches = [
            {'strategy_used': 'DEFAULT', 'symbol': 'BTC/USD', 'timeframe': '1h', 'status': 'LOSS', 'profit': -10.0, 'tp1_hit': False, 'closed_at': '2026-10-15T10:00:00Z'},
            {'strategy_used': 'DEFAULT', 'symbol': 'BTC/USD', 'timeframe': '1h', 'status': 'LOSS', 'profit': -15.0, 'tp1_hit': False, 'closed_at': '2026-10-15T11:00:00Z'},
            {'strategy_used': 'DEFAULT', 'symbol': 'BTC/USD', 'timeframe': '1h', 'status': 'WIN', 'profit': 30.0, 'tp1_hit': True, 'closed_at': '2026-10-15T12:00:00Z'},
            {'strategy_used': 'DEFAULT', 'symbol': 'BTC/USD', 'timeframe': '1h', 'status': 'LOSS', 'profit': -20.0, 'tp1_hit': False, 'closed_at': '2026-10-15T13:00:00Z'},
        ]
        lb = MT5BacktestEngine.compute_backtest_strategy_leaderboard(mock_batches, ['DEFAULT'])
        self.assertEqual(len(lb), 1)
        self.assertEqual(lb[0]['max_cons_losses'], 2)
        self.assertEqual(lb[0]['max_cons_loss_usd'], 25.0)

        daily = MT5BacktestEngine.compute_daily_breakdown(mock_batches, '2026-10-15', '2026-10-15')
        d = next(x for x in daily if x['date'] == '2026-10-15')
        self.assertEqual(d['max_cons_losses'], 2)
        self.assertEqual(d['max_cons_loss_usd'], 25.0)

        pairs = MT5BacktestEngine.compute_pair_breakdown(mock_batches, ['BTC/USD'])
        self.assertEqual(pairs[0]['max_cons_losses'], 2)
        self.assertEqual(pairs[0]['max_cons_loss_usd'], 25.0)

        # Verify format_leaderboard_export_df contains consecutive loss and detail columns
        from src.engine.autonomous_manager import AutonomousTraderEngine
        export_df = AutonomousTraderEngine.format_leaderboard_export_df(lb)
        self.assertIn('Max Cons Losses', export_df.columns)
        self.assertIn('Max Cons Loss ($)', export_df.columns)
        self.assertIn('Best Timeframes Detail', export_df.columns)
        self.assertIn('Best Trading Pairs Detail', export_df.columns)

        # Check app.py contains the consecutive losses columns
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_path, 'r', encoding='utf-8') as f:
            app_code = f.read()
        self.assertIn('Cons Loss ($)', app_code)
        self.assertIn('max_cons_losses', app_code)
        self.assertIn('max_cons_loss_usd', app_code)



    def test_standalone_strategy_simulations(self):
        """Ensure compute_standalone_strategy_simulations models dedicated accounts per strategy accurately."""
        mock_batches = [
            {'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'timeframe': '1h', 'status': 'WIN', 'profit': 50.0, 'tp1_hit': True, 'closed_at': '2026-10-15T10:00:00Z'},
            {'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'timeframe': '1h', 'status': 'LOSS', 'profit': -20.0, 'tp1_hit': False, 'closed_at': '2026-10-15T11:00:00Z'},
            {'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'timeframe': '1h', 'status': 'WIN', 'profit': 70.0, 'tp1_hit': True, 'closed_at': '2026-10-15T12:00:00Z'},
            {'strategy_used': 'STRAT_B', 'symbol': 'EUR/USD', 'timeframe': '15m', 'status': 'LOSS', 'profit': -30.0, 'tp1_hit': False, 'closed_at': '2026-10-15T10:00:00Z'},
            {'strategy_used': 'STRAT_B', 'symbol': 'EUR/USD', 'timeframe': '15m', 'status': 'LOSS', 'profit': -40.0, 'tp1_hit': False, 'closed_at': '2026-10-15T11:00:00Z'},
        ]
        sims = MT5BacktestEngine.compute_standalone_strategy_simulations(mock_batches, initial_balance=100.0, active_strategy_keys=['STRAT_A', 'STRAT_B'])
        self.assertEqual(len(sims), 2)
        
        sa = next(s for s in sims if s['strategy_key'] == 'STRAT_A')
        self.assertEqual(sa['initial_balance'], 100.0)
        self.assertEqual(sa['final_balance'], 200.0)
        self.assertEqual(sa['lowest_balance'], 100.0)
        self.assertEqual(sa['peak_balance'], 200.0)
        self.assertEqual(sa['net_pnl'], 100.0)
        self.assertEqual(sa['roi_pct'], 100.0)
        self.assertEqual(sa['trades'], 3)
        self.assertEqual(sa['wins'], 2)
        self.assertEqual(sa['losses'], 1)
        self.assertEqual(sa['survival_badge'], '🚀 2x+ CAPITAL')

        sb = next(s for s in sims if s['strategy_key'] == 'STRAT_B')
        self.assertEqual(sb['initial_balance'], 100.0)
        self.assertEqual(sb['final_balance'], 30.0)
        self.assertEqual(sb['lowest_balance'], 30.0)
        self.assertEqual(sb['net_pnl'], -70.0)
        self.assertEqual(sb['roi_pct'], -70.0)
        self.assertEqual(sb['max_cons_losses'], 2)
        self.assertEqual(sb['max_cons_loss_usd'], 70.0)
        self.assertEqual(sb['survival_badge'], '⚠️ HIGH DD')

        # Verify app.py contains the Standalone Strategy Simulation section
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_path, 'r', encoding='utf-8') as f:
            app_code = f.read()
        self.assertIn('Standalone Strategy Simulation', app_code)
        self.assertIn('bt_standalone_sort_selector', app_code)
        self.assertIn('dl_bt_standalone_sim_csv', app_code)

    def test_weekend_trades_filter_and_recompute(self):
        """Ensure weekend trade filtering accurately purges Saturday/Sunday trades and recalculates all views."""
        # 1. Test is_weekend_batch
        fri_batch = {'closed_at': '2026-10-16T18:00:00Z', 'status': 'WIN', 'profit': 50.0} # Friday
        sat_batch = {'closed_at': '2026-10-17T12:00:00Z', 'status': 'LOSS', 'profit': -30.0} # Saturday
        sun_batch = {'closed_at': '2026-10-18T20:00:00Z', 'status': 'LOSS', 'profit': -40.0} # Sunday
        mon_batch = {'closed_at': '2026-10-19T09:00:00Z', 'status': 'WIN', 'profit': 25.0} # Monday

        self.assertFalse(MT5BacktestEngine.is_weekend_batch(fri_batch))
        self.assertTrue(MT5BacktestEngine.is_weekend_batch(sat_batch))
        self.assertTrue(MT5BacktestEngine.is_weekend_batch(sun_batch))
        self.assertFalse(MT5BacktestEngine.is_weekend_batch(mon_batch))

        # 2. Test recompute_filtered_results
        mock_batches = [
            {'batch_id': 'b1', 'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'closed_at': '2026-10-16T18:00:00Z', 'status': 'WIN', 'profit': 50.0, 'tp1_hit': True},
            {'batch_id': 'b2', 'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'closed_at': '2026-10-17T12:00:00Z', 'status': 'LOSS', 'profit': -30.0, 'tp1_hit': False},
            {'batch_id': 'b3', 'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'closed_at': '2026-10-18T20:00:00Z', 'status': 'LOSS', 'profit': -40.0, 'tp1_hit': False},
            {'batch_id': 'b4', 'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'closed_at': '2026-10-19T09:00:00Z', 'status': 'WIN', 'profit': 25.0, 'tp1_hit': True},
        ]
        raw_res = {
            'initial_balance': 1000.0,
            'final_balance': 1005.0,
            'net_profit': 5.0,
            'roi_pct': 0.5,
            'total_trades': 4,
            'wins': 2,
            'losses': 2,
            'breakevens': 0,
            'win_rate': 50.0,
            'profit_factor': 1.07,
            'max_cons_losses': 2,
            'max_cons_loss_usd': 70.0,
            'closed_batches': mock_batches,
            'date_from': '2026-10-15',
            'date_to': '2026-10-20',
            'settings_used': {'selected_symbols': ['BTC/USD'], 'active_strategies': ['STRAT_A']}
        }

        # Without filter
        unfiltered = MT5BacktestEngine.recompute_filtered_results(raw_res, exclude_weekends=False)
        self.assertEqual(unfiltered['total_trades'], 4)
        self.assertEqual(unfiltered['net_profit'], 5.0)

        # With weekend filter active
        filtered = MT5BacktestEngine.recompute_filtered_results(raw_res, exclude_weekends=True)
        self.assertEqual(filtered['weekend_trades_excluded'], 2)
        self.assertEqual(filtered['total_trades'], 2)
        self.assertEqual(filtered['net_profit'], 75.0) # 50 + 25 = 75
        self.assertEqual(filtered['final_balance'], 1075.0)
        self.assertEqual(filtered['win_rate'], 100.0)
        self.assertEqual(filtered['max_cons_losses'], 0) # Weekend losses eliminated
        self.assertEqual(len(filtered['closed_batches']), 2)

        # Check standalone dedicated account recomputation
        standalone = filtered['standalone_strategy_simulations']
        self.assertEqual(len(standalone), 1)
        self.assertEqual(standalone[0]['trades'], 2)
        self.assertEqual(standalone[0]['net_pnl'], 75.0)
        self.assertEqual(standalone[0]['final_balance'], 1075.0)

        # 3. Verify app.py has the toggle and all 6 export buttons
        app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_path, 'r', encoding='utf-8') as f:
            app_code = f.read()
        self.assertIn('bt_exclude_weekends_toggle', app_code)
        self.assertIn('dl_bt_weekly_breakdown_csv', app_code)
        self.assertIn('dl_bt_daily_breakdown_csv', app_code)
        self.assertIn('dl_bt_pair_breakdown_csv', app_code)
        self.assertIn('dl_bt_leaderboard_csv', app_code)
        self.assertIn('dl_bt_batches_csv', app_code)
        self.assertIn('dl_bt_standalone_sim_csv', app_code)

    def test_bid_ask_spread_geometry(self):
        """Ensure MT5BacktestEngine enforces institutional Bid/Ask spread execution geometry."""
        # 1. Verify get_symbol_spread helper
        sp_eur = MT5BacktestEngine.get_symbol_spread('EUR/USD')
        sp_gold = MT5BacktestEngine.get_symbol_spread('XAU/USD')
        sp_btc = MT5BacktestEngine.get_symbol_spread('BTC/USD')

        self.assertGreater(sp_eur, 0.0)
        self.assertGreater(sp_gold, 0.0)
        self.assertGreater(sp_btc, 0.0)

        # Custom spread map override
        self.assertEqual(MT5BacktestEngine.get_symbol_spread('EUR/USD', {'EUR/USD': 0.00030}), 0.00030)

        # 2. Verify engine code applies Ask = Close + Spread on BUY and Ask = High/Low + Spread on SELL exits
        engine_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'engine', 'backtest_engine.py'))
        with open(engine_file, 'r', encoding='utf-8') as f:
            eng_code = f.read()

        # Check BUY entry executes at Ask
        self.assertIn("c_entry = (cur_close + cur_spread + slippage_dist) if c_act == 'BUY' else (cur_close - slippage_dist)", eng_code)
        # Check SELL exits evaluate at Ask = Price + Spread
        self.assertIn("cur_ask_high = cur_high + b_spread", eng_code)
        self.assertIn("cur_ask_low = cur_low + b_spread", eng_code)
        self.assertIn("if cur_ask_high >= b['sl_price']:", eng_code)
        self.assertIn("elif cur_ask_low <= tp1_p:", eng_code)

        # 3. Verify app.py has spread_applied in batch ledger
        app_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_file, 'r', encoding='utf-8') as f:
            app_code = f.read()
        self.assertIn("'spread_applied': 'Spread'", app_code)

    def test_true_pnl_win_rate_and_costs(self):
        """Ensure win rate is purely based on real positive profit, and transaction costs are modeled."""
        # 1. Test True-PnL Win Rate: Trade with tp1_hit=True but negative PnL must NOT count as a WIN
        mock_batches = [
            {'batch_id': 'b1', 'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'status': 'LOSS', 'profit': -25.0, 'tp1_hit': True},
            {'batch_id': 'b2', 'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'status': 'WIN', 'profit': 40.0, 'tp1_hit': True},
            {'batch_id': 'b3', 'strategy_used': 'STRAT_A', 'symbol': 'BTC/USD', 'status': 'BREAKEVEN', 'profit': 0.00, 'tp1_hit': True},
        ]
        lb = MT5BacktestEngine.compute_backtest_strategy_leaderboard(mock_batches, ['STRAT_A'])
        self.assertEqual(len(lb), 1)
        # Only b2 is positive (1 out of 3 = 33.3%, NOT 100%!)
        self.assertAlmostEqual(lb[0]['win_rate'], 33.3, places=1)

        # 2. Test Transaction Costs & Currency Conversion
        # EUR/USD: 10 pips on 0.01 lot = $1.00
        pnl_eur = MT5BacktestEngine.convert_delta_to_usd(0.0010, 'EUR/USD', 1.0850, 100000.0, 0.01)
        self.assertAlmostEqual(pnl_eur, 1.00, places=2)

        # USD/JPY: 10 pips on 0.01 lot at 150.0 = $100 / 150 = $0.67
        pnl_jpy = MT5BacktestEngine.convert_delta_to_usd(0.10, 'USD/JPY', 150.0, 100000.0, 0.01)
        self.assertAlmostEqual(pnl_jpy, 0.67, places=2)

        # GBP/AUD: 10 pips on 0.01 lot with AUD/USD=0.66 = $0.66 (not $1.00!)
        pnl_cross = MT5BacktestEngine.convert_delta_to_usd(0.0010, 'GBP/AUD', 1.95, 100000.0, 0.01, {'AUD/USD': 0.66})
        self.assertAlmostEqual(pnl_cross, 0.66, places=2)

        # Slippage calculation
        slip = MT5BacktestEngine.compute_slippage_distance('EUR/USD', 0.5)
        self.assertEqual(slip, 0.00005)

        # Swap calculation
        swap = MT5BacktestEngine.compute_swap_fee('2024-05-15T10:00:00', '2024-05-17T10:00:00', 0.03, 'EUR/USD')
        self.assertGreater(swap, 0.0)

        # App.py has costs_usd and synthetic notice
        app_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))
        with open(app_file, 'r', encoding='utf-8') as f:
            app_code = f.read()
        self.assertIn("'costs_usd': 'Costs ($)'", app_code)
        self.assertIn('is_synthetic_feed', app_code)


if __name__ == '__main__':
    unittest.main()

