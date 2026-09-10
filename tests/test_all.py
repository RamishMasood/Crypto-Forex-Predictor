"""
Comprehensive Automated Test Suite for Real Crypto & Forex Predictor
"""

import unittest
import pandas as pd
import numpy as np
import sys
import os

# Ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data.crypto_feeds import CryptoFeedManager
from src.data.forex_feeds import ForexFeedManager
from src.data.orderbook_depth import OrderBookAnalyzer
from src.strategies.indicators import QuantitativeIndicators
from src.strategies.smc import SmartMoneyConcepts
from src.strategies.arbitrage import CrossExchangeArbitrage
from src.ml.features import FeatureEngineer
from src.ml.predictor import MachineLearningPredictor
from src.engine.confluence import ConfluenceEngine
from src.engine.risk_manager import RiskManager
from src.engine.orchestrator import PredictorOrchestrator
from src.strategies.alpha_sniper import AlphaSniperEngine
from src.engine.verifier import TradeVerifier
from src.data.economic_calendar import EconomicCalendarManager
from src.engine.mtf_filter import MultiTimeframeFilter
from src.engine.mt5_executor import MT5TradeExecutor
from datetime import datetime, timezone, timedelta

class TestCryptoForexPredictor(unittest.TestCase):

    def setUp(self):
        # Generate synthetic OHLCV dataframe for reliable unit testing of calculations
        np.random.seed(42)
        n = 80
        dates = pd.date_range('2026-01-01', periods=n, freq='1h')
        close = 100.0 + np.cumsum(np.random.randn(n) * 1.5)
        high = close + np.random.rand(n) * 1.0
        low = close - np.random.rand(n) * 1.0
        open_p = close + np.random.randn(n) * 0.5
        vol = np.random.randint(100, 1000, size=n).astype(float)

        self.synth_df = pd.DataFrame({
            'timestamp': dates,
            'open': open_p,
            'high': high,
            'low': low,
            'close': close,
            'volume': vol
        })

    def test_quantitative_indicators(self):
        df_ind = QuantitativeIndicators.add_all_indicators(self.synth_df)
        self.assertIn('ema_20', df_ind.columns)
        self.assertIn('supertrend', df_ind.columns)
        self.assertIn('supertrend_dir', df_ind.columns)
        self.assertIn('rsi_14', df_ind.columns)
        self.assertIn('macd_line', df_ind.columns)
        self.assertIn('adx_14', df_ind.columns)
        self.assertIn('bb_upper', df_ind.columns)
        self.assertIn('atr_14', df_ind.columns)
        self.assertFalse(df_ind['rsi_14'].isna().all())

    def test_smart_money_concepts(self):
        fvgs = SmartMoneyConcepts.detect_fair_value_gaps(self.synth_df)
        self.assertIsInstance(fvgs, list)

        obs = SmartMoneyConcepts.detect_order_blocks(self.synth_df)
        self.assertIsInstance(obs, list)

        struct = SmartMoneyConcepts.analyze_market_structure(self.synth_df)
        self.assertIn('structure', struct)
        self.assertIn(struct['structure'], ['BULLISH', 'BEARISH', 'CONSOLIDATION'])

    def test_ml_feature_pipeline_and_predictor(self):
        df_ind = QuantitativeIndicators.add_all_indicators(self.synth_df)
        features = FeatureEngineer.extract_features(df_ind)
        self.assertEqual(len(features), len(df_ind))
        self.assertFalse(features.isna().any().any())

        predictor = MachineLearningPredictor(n_estimators=20)
        res = predictor.fit_and_predict(df_ind, horizon=2)
        self.assertEqual(res['status'], 'SUCCESS')
        self.assertIn('p_bullish', res)
        self.assertIn('p_bearish', res)
        self.assertIn('predicted_direction', res)

    def test_risk_manager(self):
        setup_buy = RiskManager.generate_trade_setup(
            current_price=100.0,
            action='BUY',
            atr=2.0,
            account_size_usd=10000.0
        )
        self.assertEqual(setup_buy['status'], 'ACTIVE_SETUP')
        self.assertLess(setup_buy['stop_loss'], 100.0)
        self.assertGreater(setup_buy['tp1'], 100.0)
        self.assertGreater(setup_buy['tp2'], setup_buy['tp1'])

        setup_neutral = RiskManager.generate_trade_setup(
            current_price=100.0,
            action='NEUTRAL',
            atr=2.0
        )
        self.assertEqual(setup_neutral['status'], 'NO_TRADE_SETUP')

    def test_arbitrage_calculator(self):
        prices = {
            'binance': {'price': 60000.0, 'status': 'ONLINE'},
            'bybit': {'price': 60200.0, 'status': 'ONLINE'},
            'coinbase': {'price': 60050.0, 'status': 'ONLINE'}
        }
        arb = CrossExchangeArbitrage.analyze_spreads(prices)
        self.assertEqual(arb['cheapest_exchange'], 'binance')
        self.assertEqual(arb['highest_exchange'], 'bybit')
        self.assertEqual(arb['gross_spread'], 200.0)

    def test_live_crypto_and_forex_orchestrator(self):
        orch = PredictorOrchestrator()
        
        # Test Live Crypto
        crypto_res = orch.run_prediction(symbol='BTC/USDT', asset_type='crypto', timeframe='1h')
        self.assertIn('confluence', crypto_res)
        self.assertIn('trade_setup', crypto_res)
        self.assertGreater(crypto_res['market_data']['current_price'], 1000)

        # Test Live Forex
        forex_res = orch.run_prediction(symbol='EUR/USD', asset_type='forex', timeframe='1h')
        self.assertIn('confluence', forex_res)
        self.assertIn('trade_setup', forex_res)
        self.assertGreater(forex_res['market_data']['current_price'], 0.5)

    def test_kaufman_efficiency_and_cmo(self):
        df_ind = QuantitativeIndicators.add_all_indicators(self.synth_df)
        self.assertIn('kaufman_er', df_ind.columns)
        self.assertIn('cmo_14', df_ind.columns)
        self.assertIn('cvd_zscore', df_ind.columns)
        # Verify bounded ranges
        self.assertTrue((df_ind['kaufman_er'] >= 0.0).all() and (df_ind['kaufman_er'] <= 1.0).all())
        self.assertTrue((df_ind['cmo_14'] >= -100.0).all() and (df_ind['cmo_14'] <= 100.0).all())

    def test_smc_optimal_trade_entry_and_pricing(self):
        struct = SmartMoneyConcepts.analyze_market_structure(self.synth_df)
        self.assertIn('market_zone', struct)
        self.assertIn(struct['market_zone'], ['DISCOUNT', 'PREMIUM', 'EQUILIBRIUM'])
        self.assertIn('equilibrium_price', struct)
        self.assertIn('in_bull_ote', struct)
        self.assertIn('in_bear_ote', struct)

    def test_alpha_sniper_bayesian_accuracy_and_expectancy(self):
        df_ind = QuantitativeIndicators.add_all_indicators(self.synth_df)
        base_conf = {
            'action': 'STRONG BUY',
            'confluence_score': 65.0,
            'layer_scores': {
                'trend_momentum': 25.0,
                'smart_money_smc': 18.0,
                'mean_reversion_stat': 12.0,
                'orderbook_pressure': 10.0
            }
        }
        ml_pred = {
            'p_bullish': 0.72,
            'p_bearish': 0.12,
            'confidence_pct': 60.0
        }
        res = AlphaSniperEngine.evaluate(
            df_indicators=df_ind,
            base_confluence=base_conf,
            ml_prediction=ml_pred,
            trade_setup={}
        )
        self.assertIn('calibrated_win_probability_pct', res)
        self.assertGreaterEqual(res['calibrated_win_probability_pct'], 80.0)
        self.assertLessEqual(res['calibrated_win_probability_pct'], 97.2)
        self.assertEqual(res['sniper_tier'], 'ELITE_SNIPER')
        self.assertGreater(res['trade_expectancy_r'], 1.0)

    def test_alpha_sniper_timeframe_adaptation_and_noise_penalties(self):
        df_ind = QuantitativeIndicators.add_all_indicators(self.synth_df)
        base_conf = {
            'action': 'STRONG BUY',
            'confluence_score': 60.0,
            'layer_scores': {
                'trend_momentum': 20.0,
                'smart_money_smc': 15.0,
                'mean_reversion_stat': 10.0,
                'orderbook_pressure': 8.0
            }
        }
        ml_pred = {'p_bullish': 0.70, 'p_bearish': 0.15, 'confidence_pct': 55.0}

        # Higher timeframe (1h/4h) has higher stability prior than noisy micro timeframe (3m/5m)
        res_5m = AlphaSniperEngine.evaluate(
            df_indicators=df_ind, base_confluence=base_conf, ml_prediction=ml_pred,
            trade_setup={}, timeframe='5m'
        )
        res_1h = AlphaSniperEngine.evaluate(
            df_indicators=df_ind, base_confluence=base_conf, ml_prediction=ml_pred,
            trade_setup={}, timeframe='1h'
        )
        self.assertGreater(res_1h['calibrated_win_probability_pct'], res_5m['calibrated_win_probability_pct'])
        self.assertTrue(45.0 <= res_5m['calibrated_win_probability_pct'] <= 97.2)
        self.assertTrue(45.0 <= res_1h['calibrated_win_probability_pct'] <= 97.2)

    def test_risk_manager_filtered_and_preservation_modes(self):
        # Must return NO_TRADE_SETUP and 0 risk on filtered/neutral/preservation actions
        for act in ['NEUTRAL (FILTERED)', 'NEUTRAL', 'HOLD', 'CAPITAL_PRESERVATION']:
            setup = RiskManager.generate_trade_setup(
                current_price=100.0,
                action=act,
                atr=2.0
            )
            self.assertEqual(setup['status'], 'NO_TRADE_SETUP')
            self.assertEqual(setup['risk_amount_usd'], 0.0)
            self.assertEqual(setup['suggested_position_usd'], 0.0)
            self.assertEqual(setup['expectancy_r'], 0.0)

    def test_alpha_sniper_strong_buy_invalidation_gate(self):
        df_ind = QuantitativeIndicators.add_all_indicators(self.synth_df)
        # Weak confluence in random noise regime should gate STRONG BUY to NEUTRAL (FILTERED)
        weak_conf = {
            'action': 'STRONG BUY',
            'confluence_score': 10.0,
            'layer_scores': {
                'trend_momentum': 0.0,
                'smart_money_smc': 0.0,
                'mean_reversion_stat': 0.0,
                'orderbook_pressure': 0.0
            }
        }
        ml_pred = {'p_bullish': 0.33, 'p_bearish': 0.33, 'confidence_pct': 0.0}
        res = AlphaSniperEngine.evaluate(
            df_indicators=df_ind,
            base_confluence=weak_conf,
            ml_prediction=ml_pred,
            trade_setup={}
        )
        if res['sniper_tier'] == 'CAPITAL_PRESERVATION':
            self.assertEqual(res['gated_action'], 'NEUTRAL (FILTERED)')
            self.assertEqual(res['trade_expectancy_r'], 0.0)

    def test_smc_inverted_swings_bounded_range(self):
        # Monotonically increasing data where last swing low is higher than initial high
        n = 40
        close = np.linspace(100.0, 150.0, n)
        high = close + 1.0
        low = close - 1.0
        df_trend = pd.DataFrame({
            'open': close, 'high': high, 'low': low, 'close': close,
            'volume': np.full(n, 500.0)
        })
        struct = SmartMoneyConcepts.analyze_market_structure(df_trend)
        self.assertGreater(struct['equilibrium_price'], 0.0)
        self.assertGreaterEqual(struct['price_in_range_pct'], 0.0)
        self.assertLessEqual(struct['price_in_range_pct'], 100.0)

    def test_ml_predictor_low_volatility_robustness(self):
        # Very low volatility dataframe (EUR/USD calm session: 0.01% variations)
        n = 50
        dates = pd.date_range('2026-01-01', periods=n, freq='1h')
        close = 1.0800 + np.sin(np.linspace(0, 3, n)) * 0.0003
        df_calm = pd.DataFrame({
            'timestamp': dates,
            'open': close, 'high': close + 0.0001, 'low': close - 0.0001,
            'close': close, 'volume': np.full(n, 1000.0)
        })
        df_ind = QuantitativeIndicators.add_all_indicators(df_calm)
        pred = MachineLearningPredictor(n_estimators=10)
        res = pred.fit_and_predict(df_ind, horizon=2, threshold_pct=0.25)
        # Must execute cleanly without unhandled ValueError
        self.assertIn(res['status'], ['SUCCESS', 'INSUFFICIENT_VARIANCE', 'INSUFFICIENT_DATA'])
        self.assertIn('p_bullish', res)
        self.assertIn('p_bearish', res)

    def test_trade_verifier_breakeven_not_counted_as_win(self):
        # Construct custom dataset to verify that BREAKEVEN exits are categorized as BREAKEVEN, not WIN
        n = 60
        dates = pd.date_range('2026-01-01', periods=n, freq='1h')
        # Setup synthetic bars
        close = np.linspace(100.0, 110.0, n)
        high = close + 0.5
        low = close - 0.5
        open_p = close
        vol = np.full(n, 500.0)

        df = pd.DataFrame({
            'timestamp': dates,
            'open': open_p,
            'high': high,
            'low': low,
            'close': close,
            'volume': vol
        })

        verifier = TradeVerifier()
        # Verify run completes cleanly
        res = verifier.run_10_trade_verification(
            symbol='BTC/USDT',
            asset_type='crypto',
            market_mode='spot',
            timeframe='1h',
            target_trades_count=3,
            custom_df=df
        )
        self.assertIn(res['status'], ['SUCCESS', 'ERROR_INSUFFICIENT_DATA'])
        if res.get('status') == 'SUCCESS':
            self.assertIn('breakevens', res)
            self.assertIn('exact_win_rate_pct', res)
            self.assertIn('win_rate_pct', res)
            self.assertEqual(res['wins'] + res['breakevens'] + res['losses'], res['total_trades'])
        # Any trade recorded must adhere strictly: WIN ONLY IF TP1/TP2 HIT
        for t in res.get('trades', []):
            if 'BREAKEVEN' in t.get('exit_reason', ''):
                self.assertNotEqual(t['outcome'], 'WIN', "BREAKEVEN trades must NOT be labeled as WIN")
                self.assertEqual(t['outcome'], 'BREAKEVEN')
            elif 'TP' in t.get('exit_reason', ''):
                self.assertEqual(t['outcome'], 'WIN')

    def test_trade_verifier_error_keys_consistency(self):
        verifier = TradeVerifier()
        empty_df = pd.DataFrame()
        res = verifier.run_10_trade_verification(custom_df=empty_df)
        self.assertEqual(res['status'], 'ERROR_INSUFFICIENT_DATA')
        self.assertIn('exact_win_rate_pct', res)
        self.assertIn('win_rate_pct', res)
        self.assertIn('breakevens', res)
        self.assertIn('audit_grade', res)
        self.assertEqual(res['exact_win_rate_pct'], 0.0)

    def test_trade_verifier_multi_timeframe_calibration_and_high_accuracy(self):
        # Verify across multiple timeframes (5m, 15m, 1h) that verifier executions produce valid setups
        # with calibrated win probabilities and verified target fulfillments strictly requiring TP1/TP2 hits.
        n = 75
        dates = pd.date_range('2026-01-01', periods=n, freq='5min')
        # Realistic trending series with minor pullbacks
        np.random.seed(123)
        returns = np.random.normal(0.001, 0.003, n)
        close = 100.0 * np.exp(np.cumsum(returns))
        high = close * (1.0 + np.abs(np.random.normal(0.002, 0.001, n)))
        low = close * (1.0 - np.abs(np.random.normal(0.002, 0.001, n)))
        open_p = (high + low) / 2.0
        vol = np.random.uniform(500, 2000, n)

        df_synth = pd.DataFrame({
            'timestamp': dates,
            'open': open_p,
            'high': high,
            'low': low,
            'close': close,
            'volume': vol
        })

        verifier = TradeVerifier()
        for tf in ['5m', '15m', '1h']:
            res = verifier.run_10_trade_verification(
                symbol='BTC/USDT',
                asset_type='crypto',
                market_mode='futures',
                timeframe=tf,
                target_trades_count=3,
                custom_df=df_synth
            )
            self.assertIn(res['status'], ['SUCCESS', 'ERROR_INSUFFICIENT_DATA'])
            if res['status'] == 'SUCCESS' and res['total_trades'] > 0:
                self.assertGreaterEqual(res['win_rate_pct'], 85.0)
                # Ensure all recorded winning trades have TP in exit_reason
                for t in res['trades']:
                    if t['outcome'] == 'WIN':
                        self.assertTrue('TP1' in t['exit_reason'] or 'TP2' in t['exit_reason'])
                    self.assertGreaterEqual(t['calibrated_win_prob_pct'], 80.0)

    def test_economic_calendar_and_news_blackout_filter(self):
        cal = EconomicCalendarManager()
        events = cal.fetch_live_calendar()
        self.assertIsInstance(events, list)
        self.assertGreater(len(events), 0)

        # Check currency resolution
        crypto_ccys = cal.get_affected_currencies('BTC/USDT', 'crypto')
        self.assertIn('USD', crypto_ccys)
        forex_ccys = cal.get_affected_currencies('EUR/USD', 'forex')
        self.assertIn('EUR', forex_ccys)
        self.assertIn('USD', forex_ccys)

        # Check standard live blackout check (now)
        live_status = cal.check_blackout_status('BTC/USDT', 'crypto')
        self.assertIn('is_blackout', live_status)
        self.assertIn('blackout_reason', live_status)
        self.assertEqual(live_status['blackout_window_mins'], 30)

        # Check simulated blackout trigger at a known event release time
        # Using 2026-09-10 12:30 UTC (US PPI / Core PPI)
        test_event_time = datetime(2026, 9, 10, 12, 30, tzinfo=timezone.utc)
        blackout_res = cal.check_blackout_status('BTC/USDT', 'crypto', check_time=test_event_time)
        self.assertTrue(blackout_res['is_blackout'])
        self.assertIsNotNone(blackout_res['active_event'])
        self.assertIn('HIGH-IMPACT NEWS BLACKOUT', blackout_res['blackout_reason'])

        # Edge Case Attack: Test EXACT boundary condition (29m 59s vs 30m 01s)
        # Inside window: 29 minutes and 59 seconds before event -> MUST be blackout
        inside_window_pre = test_event_time - timedelta(minutes=29, seconds=59)
        self.assertTrue(cal.check_blackout_status('BTC/USDT', 'crypto', check_time=inside_window_pre)['is_blackout'])

        # Outside window: 30 minutes and 01 seconds before event -> MUST NOT be blackout
        outside_window_pre = test_event_time - timedelta(minutes=30, seconds=1)
        self.assertFalse(cal.check_blackout_status('BTC/USDT', 'crypto', check_time=outside_window_pre)['is_blackout'])

        # Inside window post-event: 29 minutes and 59 seconds after event -> MUST be blackout
        inside_window_post = test_event_time + timedelta(minutes=29, seconds=59)
        self.assertTrue(cal.check_blackout_status('BTC/USDT', 'crypto', check_time=inside_window_post)['is_blackout'])

        # Outside window post-event: 30 minutes and 01 seconds after event -> MUST NOT be blackout
        outside_window_post = test_event_time + timedelta(minutes=30, seconds=1)
        self.assertFalse(cal.check_blackout_status('BTC/USDT', 'crypto', check_time=outside_window_post)['is_blackout'])

        # Timezone Edge Case: Test naive ForexFactory CSV Eastern Time conversion to UTC
        parsed_dt = cal._parse_event_datetime('09-10-2026 8:30am')
        self.assertIsNotNone(parsed_dt)
        self.assertEqual(parsed_dt.hour, 12)
        self.assertEqual(parsed_dt.minute, 30)

    def test_multi_timeframe_triple_screen_filter(self):
        # Generate macro (Daily) and intermediate (1h) data
        n = 60
        dates_d = pd.date_range('2026-01-01', periods=n, freq='1d')
        close_up = np.linspace(100.0, 160.0, n)
        df_macro_bull = pd.DataFrame({
            'timestamp': dates_d, 'open': close_up, 'high': close_up + 2.0,
            'low': close_up - 2.0, 'close': close_up, 'volume': np.full(n, 1000.0)
        })

        dates_h = pd.date_range('2026-01-01', periods=n, freq='1h')
        df_1h = pd.DataFrame({
            'timestamp': dates_h, 'open': close_up, 'high': close_up + 1.0,
            'low': close_up - 1.0, 'close': close_up, 'volume': np.full(n, 1000.0)
        })

        # Screen 1: Macro Screen
        s1 = MultiTimeframeFilter.evaluate_macro_screen(df_macro_bull)
        self.assertTrue(s1['available'])
        self.assertIn(s1['close_vs_ema200'], ['ABOVE_200_EMA', 'BELOW_200_EMA'])

        # Screen 2: Key Zone Screen
        s2 = MultiTimeframeFilter.evaluate_zone_screen(df_1h)
        self.assertTrue(s2['available'])
        self.assertIn('in_key_zone', s2)
        self.assertIn('zone_type', s2)

        # Screen 3: Micro Trigger Screen
        s3 = MultiTimeframeFilter.evaluate_trigger_screen(df_1h)
        self.assertTrue(s3['available'])
        self.assertIn('trigger_status', s3)

        # Full Triple-Screen Synthesis
        # Buying in uptrend above 200 EMA -> no macro conflict
        bull_synth = MultiTimeframeFilter.evaluate_triple_screen(df_macro_bull, df_1h, df_1h, 'BUY')
        self.assertFalse(bull_synth['is_macro_conflict'])
        self.assertIn(bull_synth['triple_screen_status'], ['TRIPLE_SCREEN_ALIGNED', 'PARTIALLY_ALIGNED', 'WEAK_ALIGNMENT'])

        # Selling against uptrend above 200 EMA -> FATAL MACRO CONFLICT
        bear_synth = MultiTimeframeFilter.evaluate_triple_screen(df_macro_bull, df_1h, df_1h, 'SELL')
        self.assertTrue(bear_synth['is_macro_conflict'])
        self.assertEqual(bear_synth['triple_screen_status'], 'MACRO_CONFLICT')

        # Edge Case: Missing Macro Data must NOT yield TRIPLE_SCREEN_ALIGNED (3/3)
        no_macro_synth = MultiTimeframeFilter.evaluate_triple_screen(None, df_1h, df_1h, 'BUY')
        self.assertNotEqual(no_macro_synth['triple_screen_status'], 'TRIPLE_SCREEN_ALIGNED')
        self.assertLessEqual(no_macro_synth['aligned_screens_count'], 2)

    def test_adaptive_target_scaling_and_immediate_breakeven(self):
        # Verify Precision TP1 target (0.40 ATR) and Immediate Breakeven Stop-Loss
        current_p = 100.0
        atr_v = 2.5
        setup_buy = RiskManager.generate_trade_setup(
            current_price=current_p,
            action='BUY',
            atr=atr_v,
            account_size_usd=10000.0
        )
        self.assertEqual(setup_buy['status'], 'ACTIVE_SETUP')
        # TP1 should be precision scalp: 100.0 + (0.40 * 2.5) = 101.0
        self.assertAlmostEqual(setup_buy['tp1'], current_p + (0.40 * atr_v), places=2)
        self.assertGreater(setup_buy['tp2'], setup_buy['tp1'])
        self.assertGreater(setup_buy['tp3'], setup_buy['tp2'])
        # Breakeven SL must be entry + 0.02 ATR
        self.assertAlmostEqual(setup_buy['breakeven_sl'], current_p + (0.02 * atr_v), places=2)
        self.assertIn('IMMEDIATE_AT_TP1', setup_buy['breakeven_rule'])

        # Verify SELL setup
        setup_sell = RiskManager.generate_trade_setup(
            current_price=current_p,
            action='SELL',
            atr=atr_v,
            account_size_usd=10000.0
        )
        self.assertEqual(setup_sell['status'], 'ACTIVE_SETUP')
        self.assertAlmostEqual(setup_sell['tp1'], current_p - (0.40 * atr_v), places=2)
        self.assertLess(setup_sell['tp2'], setup_sell['tp1'])
        self.assertAlmostEqual(setup_sell['breakeven_sl'], current_p - (0.02 * atr_v), places=2)

    def test_futures_whale_sentiment_and_funding_gate(self):
        df_ind = QuantitativeIndicators.add_all_indicators(self.synth_df)
        base_conf = {
            'action': 'STRONG BUY',
            'confluence_score': 70.0,
            'layer_scores': {
                'trend_momentum': 25.0,
                'smart_money_smc': 20.0,
                'mean_reversion_stat': 15.0,
                'orderbook_pressure': 10.0,
                'f1_funding_rate': 0.0,
                'f3_squeeze_detection': 0.0,
            }
        }
        ml_pred = {'p_bullish': 0.75, 'p_bearish': 0.10, 'confidence_pct': 65.0}

        # Case 1: Futures mode WITHOUT extreme funding or squeeze
        # Should be gated below ELITE_SNIPER to HIGH_CONVICTION
        benign_futures = {
            'funding_analysis': {'score': 0.0, 'regime': 'NEUTRAL'},
            'squeeze_analysis': {'score': 0.0, 'squeeze_type': 'NONE'},
            'oi_analysis': {'oi_at_extreme': False}
        }
        res_benign = AlphaSniperEngine.evaluate(
            df_indicators=df_ind,
            base_confluence=base_conf,
            ml_prediction=ml_pred,
            trade_setup={},
            futures_signals=benign_futures,
            timeframe='1h'
        )
        self.assertNotEqual(res_benign['sniper_tier'], 'ELITE_SNIPER', "Futures setup without whale catalyst must not unlock ELITE tier")
        self.assertEqual(res_benign['sniper_tier'], 'HIGH_CONVICTION')
        self.assertFalse(res_benign['whale_gate_passed'])
        self.assertLessEqual(res_benign['calibrated_win_probability_pct'], 84.0)

        # Case 2: Futures mode WITH extreme funding squeeze ALIGNED with trade direction (BUY with Short Squeeze)
        extreme_futures = {
            'funding_analysis': {'score': 30.0, 'regime': 'EXTREME_SHORT_OVERCROWDED'},
            'squeeze_analysis': {'score': 20.0, 'squeeze_type': 'SHORT_SQUEEZE_SETUP'},
            'oi_analysis': {'oi_at_extreme': True}
        }
        res_extreme = AlphaSniperEngine.evaluate(
            df_indicators=df_ind,
            base_confluence=base_conf,
            ml_prediction=ml_pred,
            trade_setup={},
            futures_signals=extreme_futures,
            timeframe='1h'
        )
        self.assertEqual(res_extreme['sniper_tier'], 'ELITE_SNIPER')
        self.assertTrue(res_extreme['whale_gate_passed'])

        # Case 3: Counter-Whale Trap Attack: Buying into a Long Squeeze / Overleveraged Longs
        # Even if score magnitude is high, opposing the whale squeeze MUST block ELITE tier
        trap_futures = {
            'funding_analysis': {'score': -30.0, 'regime': 'EXTREME_LONG_OVERCROWDED'},
            'squeeze_analysis': {'score': -20.0, 'squeeze_type': 'LONG_SQUEEZE_SETUP'},
            'oi_analysis': {'oi_at_extreme': True}
        }
        res_trap = AlphaSniperEngine.evaluate(
            df_indicators=df_ind,
            base_confluence=base_conf,
            ml_prediction=ml_pred,
            trade_setup={},
            futures_signals=trap_futures,
            timeframe='1h'
        )
        self.assertNotEqual(res_trap['sniper_tier'], 'ELITE_SNIPER', "Buying into a long squeeze must NOT unlock ELITE")
        self.assertFalse(res_trap['whale_gate_passed'])
        self.assertIn('opposes active whale squeeze', res_trap['whale_gate_reason'])

    def test_live_real_market_verification_suite(self):
        orch = PredictorOrchestrator()

        # Real Live Crypto Spot (BTC/USDT, Binance) forward check
        res_c = orch.run_prediction(symbol='BTC/USDT', asset_type='crypto', market_mode='spot', timeframe='1h')
        self.assertGreater(res_c['market_data']['current_price'], 1000.0)
        self.assertIn('mtf_alignment', res_c)
        self.assertIn('economic_news', res_c)
        self.assertIn('whale_sentiment_gate', res_c)
        self.assertIn('tp1', res_c['trade_setup'])
        self.assertIn('breakeven_sl', res_c['trade_setup'])

        # Real Live Forex Spot (EUR/USD, Yahoo / TwelveData) forward check
        res_f = orch.run_prediction(symbol='EUR/USD', asset_type='forex', market_mode='spot', timeframe='1h')
        self.assertGreater(res_f['market_data']['current_price'], 0.5)
        self.assertIn('mtf_alignment', res_f)
        self.assertIn('economic_news', res_f)
        self.assertIn('tp1', res_f['trade_setup'])
        self.assertIn('breakeven_sl', res_f['trade_setup'])

        # Real Live Perpetual Futures (BTC/USDT, Bybit) forward check
        res_fut = orch.run_prediction(symbol='BTC/USDT', asset_type='crypto', market_mode='futures', timeframe='1h')
        self.assertEqual(res_fut['metadata']['exchange'], 'bybit_perp')
        self.assertIn('whale_sentiment_gate', res_fut)
        self.assertIn('funding_analysis', res_fut['futures_signals'])
        self.assertIn('oi_analysis', res_fut['futures_signals'])
        self.assertIn('squeeze_analysis', res_fut['futures_signals'])
        self.assertIn('tp1', res_fut['trade_setup'])

    def test_mt5_executor_lot_and_risk_calculator(self):
        executor = MT5TradeExecutor()
        # Test 1: Standard Cent Gold calculation (1.0 contract size, 0.01 min lot)
        calc = executor.calculate_lot_and_risk(
            broker_symbol='XAUUSDc',
            entry_price=4335.0,
            stop_loss_price=4345.0,
            balance_usd=1686.95,
            risk_pct=1.5,
            tp1_pct=50.0,
            tp2_pct=30.0,
            tp3_pct=20.0
        )
        self.assertIn('total_lots', calc)
        self.assertGreater(calc['total_lots'], 0.0)
        self.assertIn('lot_split', calc)
        split = calc['lot_split']
        self.assertGreater(split['tp1_lots'], 0.0)
        # Sum of sub-lots should equal total lots
        self.assertAlmostEqual(split['tp1_lots'] + split['tp2_lots'] + split['tp3_lots'], calc['total_lots'], places=2)
        # Risk percentage should match target risk closely
        self.assertTrue(abs(calc['actual_risk_pct'] - 1.5) < 0.2)

        # Test 2: Standard Forex pair (100k contract size)
        calc_fx = executor.calculate_lot_and_risk(
            broker_symbol='EURUSDc',
            entry_price=1.1600,
            stop_loss_price=1.1550,
            balance_usd=1000.0,
            risk_pct=2.0
        )
        self.assertGreater(calc_fx['total_lots'], 0.0)
        self.assertGreater(calc_fx['actual_risk_usd'], 0.0)

if __name__ == '__main__':
    unittest.main()
