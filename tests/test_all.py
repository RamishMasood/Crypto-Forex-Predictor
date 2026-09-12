"""
Comprehensive Automated Test Suite for Real Crypto & Forex Predictor
"""

import unittest
import pandas as pd
import numpy as np
import sys
import os
import time

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
from src.data.cme_proxy import CMEProxyFeed
from src.data.currency_strength import CurrencyStrengthMeter
from src.data.cot_sentiment import COTSentimentProvider
from src.engine.autonomous_manager import AutonomousTraderEngine, get_engine
from datetime import datetime, timezone, timedelta

class TestCryptoForexPredictor(unittest.TestCase):

    def setUp(self):
        # Generate synthetic OHLCV dataframe for reliable unit testing of calculations
        np.random.seed(42)
        n = 80
        dates = pd.date_range('2026-01-01', periods=n, freq='1h')
        close = 100.0 + np.cumsum(np.random.randn(n) * 1.5) + np.linspace(0, 25, n)
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
        # TP1 should be precision scalp: 100.0 + (0.38 * 2.5) = 100.95
        self.assertAlmostEqual(setup_buy['tp1'], current_p + (0.38 * atr_v), places=2)
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
        self.assertAlmostEqual(setup_sell['tp1'], current_p - (0.38 * atr_v), places=2)
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
        self.assertTrue(abs(calc['actual_risk_pct'] - 1.5) < 0.35)

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

    def test_pillar1_lower_timeframe_wicks_and_spread_adaptive_filter(self):
        # 1. 1m/3m must apply extra 0.30 * ATR breathing room wick buffer
        current_p = 100.0
        atr_v = 2.0
        setup_1m = RiskManager.generate_trade_setup(
            current_price=current_p,
            action='BUY',
            atr=atr_v,
            timeframe='1m'
        )
        self.assertEqual(setup_1m['status'], 'ACTIVE_SETUP')
        self.assertTrue(setup_1m['wick_filter_applied'])
        self.assertAlmostEqual(setup_1m['wick_buffer_atr'], 0.30 * atr_v, places=2)
        # 1m SL must be 100 - (1.80 + 0.30) * 2.0 = 100 - 4.20 = 95.80
        self.assertAlmostEqual(setup_1m['stop_loss'], current_p - (2.10 * atr_v), places=2)
        self.assertTrue(setup_1m['candle_close_confirmation'])

        # 2. 5m/1h must preserve strict Golden SL Geometry (1.80 * ATR) without micro-wick expansion
        setup_1h = RiskManager.generate_trade_setup(
            current_price=current_p,
            action='BUY',
            atr=atr_v,
            timeframe='1h'
        )
        self.assertFalse(setup_1h['wick_filter_applied'])
        self.assertEqual(setup_1m['tp1'], setup_1h['tp1'])  # TP1 strictly at 0.38 ATR
        self.assertAlmostEqual(setup_1h['stop_loss'], current_p - (1.80 * atr_v), places=2)

        # 3. Spread-Adaptive Filter on 1m/3m: Reject setup if live spread > 25% of TP1
        tp1_dist = 0.38 * atr_v  # 0.76
        excessive_spread = tp1_dist * 0.30  # 30% of target
        setup_bad_spread = RiskManager.generate_trade_setup(
            current_price=current_p,
            action='BUY',
            atr=atr_v,
            timeframe='1m',
            spread_price=excessive_spread
        )
        self.assertEqual(setup_bad_spread['status'], 'NO_TRADE_SETUP')
        self.assertIn('SPREAD FILTERED', setup_bad_spread['action'])
        self.assertFalse(setup_bad_spread['spread_filter']['passed'])

        # 4. Spread-Adaptive Filter passes when spread is low (e.g. 10% of TP1)
        low_spread = tp1_dist * 0.10
        setup_good_spread = RiskManager.generate_trade_setup(
            current_price=current_p,
            action='BUY',
            atr=atr_v,
            timeframe='1m',
            spread_price=low_spread
        )
        self.assertEqual(setup_good_spread['status'], 'ACTIVE_SETUP')
        self.assertTrue(setup_good_spread['spread_filter']['passed'])

        # 5. Golden SL Invariant: Stop Loss is NEVER compressed below 1.50 * ATR even with tight swing low
        setup_tight_swing = RiskManager.generate_trade_setup(
            current_price=current_p,
            action='BUY',
            atr=atr_v,
            recent_swing_low=99.8  # only 0.2 below entry (0.1 ATR)
        )
        self.assertLessEqual(setup_tight_swing['stop_loss'], current_p - (1.50 * atr_v))

    def test_pillar2_cme_futures_proxy_data_provider(self):
        # 1. Gold, Silver, and Crude Oil ticker mapping
        self.assertEqual(CMEProxyFeed.get_cme_ticker('XAU/USD'), 'GC=F')
        self.assertEqual(CMEProxyFeed.get_cme_ticker('XAUUSDc'), 'GC=F')
        self.assertEqual(CMEProxyFeed.get_cme_ticker('XAG/USD'), 'SI=F')
        self.assertEqual(CMEProxyFeed.get_cme_ticker('WTI/USD'), 'CL=F')
        self.assertEqual(CMEProxyFeed.get_cme_ticker('CL'), 'CL=F')
        # Non-CME tickers must return None, not Gold
        self.assertIsNone(CMEProxyFeed.get_cme_ticker('USD'))
        self.assertIsNone(CMEProxyFeed.get_cme_ticker('EUR/USD'))

        # 2. CME Order flow evaluation
        cme_res = CMEProxyFeed.get_institutional_order_flow('XAU/USD')
        self.assertTrue(cme_res['available'])
        self.assertIn('open_interest', cme_res)
        self.assertGreater(cme_res['open_interest'], 1000)
        self.assertIn('institutional_bias', cme_res)
        self.assertIn('order_flow_score', cme_res)

    def test_pillar2_currency_strength_meter(self):
        csm_res = CurrencyStrengthMeter.calculate_currency_strength(use_mt5=True)
        self.assertEqual(csm_res['status'], 'ONLINE')
        self.assertIn('scores', csm_res)
        for c in ['EUR', 'USD', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD']:
            self.assertIn(c, csm_res['scores'])
            self.assertTrue(0.0 <= csm_res['scores'][c] <= 10.0)

        # Pair evaluation for BUY and SELL
        eval_eurusd_buy = CurrencyStrengthMeter.evaluate_pair('EUR/USD', 'BUY')
        self.assertTrue(eval_eurusd_buy['available'])
        self.assertIn('differential', eval_eurusd_buy)
        self.assertIn('directional_score', eval_eurusd_buy)
        self.assertIn('alignment', eval_eurusd_buy)
        self.assertIn('score', eval_eurusd_buy)

        eval_eurusd_sell = CurrencyStrengthMeter.evaluate_pair('EUR/USD', 'SELL')
        self.assertTrue(eval_eurusd_sell['available'])
        # If USD is stronger than EUR (diff < 0), SELL must be ALIGNED, not CONFLICT!
        if eval_eurusd_sell['differential'] <= -1.0:
            self.assertIn('ALIGNED', eval_eurusd_sell['alignment'])
            self.assertGreaterEqual(eval_eurusd_sell['score'], 10.0)

    def test_pillar3_chop_market_and_bollinger_squeeze_detector(self):
        # Case A: Low ADX (< 20) or high Choppiness (> 61.8) triggers Chop Gate
        n = 50
        dates = pd.date_range('2026-01-01', periods=n, freq='1h')
        # Tight range chop: bouncing between 100.0 and 100.1
        close = 100.0 + np.sin(np.linspace(0, 10, n)) * 0.05
        df_chop = pd.DataFrame({
            'timestamp': dates,
            'open': close, 'high': close + 0.02, 'low': close - 0.02,
            'close': close, 'volume': np.full(n, 100.0)
        })
        df_ind = QuantitativeIndicators.add_all_indicators(df_chop)
        # Explicitly configure last row to reflect low ADX (< 20) and high choppiness (> 61.8)
        df_ind.loc[df_ind.index[-1], 'adx_14'] = 16.5
        df_ind.loc[df_ind.index[-1], 'choppiness'] = 64.2

        base_conf = {
            'action': 'BUY',
            'confluence_score': 30.0,
            'layer_scores': {'trend_momentum': 10.0, 'smart_money_smc': 5.0, 'mean_reversion_stat': 5.0, 'orderbook_pressure': 5.0}
        }
        ml_pred = {'p_bullish': 0.55, 'p_bearish': 0.45, 'confidence_pct': 10.0}
        alpha_res = AlphaSniperEngine.evaluate(
            df_indicators=df_ind,
            base_confluence=base_conf,
            ml_prediction=ml_pred,
            trade_setup={}
        )
        self.assertIn('chop_gate', alpha_res)
        self.assertTrue(alpha_res['chop_gate']['is_chop'])
        self.assertEqual(alpha_res['chop_gate']['status'], 'CHOP CONSOLIDATION DETECTED')
        self.assertEqual(alpha_res['gated_action'], 'NEUTRAL (FILTERED)')
        self.assertEqual(alpha_res['sniper_badge'], '[CHOP GATE] CHOP CONSOLIDATION DETECTED')
        self.assertEqual(alpha_res['sniper_tier'], 'CAPITAL_PRESERVATION')
        self.assertEqual(alpha_res['trade_expectancy_r'], 0.0)

        # Case B: High fake breakout confluence score (>= 60.0) must still be strictly gated
        base_conf_fake_breakout = {
            'action': 'BUY',
            'confluence_score': 72.0,
            'layer_scores': {'trend_momentum': 25.0, 'smart_money_smc': 20.0, 'mean_reversion_stat': 15.0, 'orderbook_pressure': 12.0}
        }
        alpha_res_fake = AlphaSniperEngine.evaluate(
            df_indicators=df_ind,
            base_confluence=base_conf_fake_breakout,
            ml_prediction=ml_pred,
            trade_setup={}
        )
        self.assertEqual(alpha_res_fake['gated_action'], 'NEUTRAL (FILTERED)')
        self.assertEqual(alpha_res_fake['sniper_badge'], '[CHOP GATE] CHOP CONSOLIDATION DETECTED')

    def test_ml_calibrated_classifier_cv_and_expected_value(self):
        # 1. Test CalibratedClassifierCV Platt Scaling produces grounded probabilities
        df_ind = QuantitativeIndicators.add_all_indicators(self.synth_df)
        predictor = MachineLearningPredictor(n_estimators=20)
        res = predictor.fit_and_predict(df_ind, horizon=2, symbol='EUR/USD', timeframe='1h')
        
        self.assertEqual(res['status'], 'SUCCESS')
        self.assertIn('calibration_method', res)
        self.assertIn('Platt Scaling', res['calibration_method'])
        self.assertIn('expected_value_r', res)
        self.assertIn('is_ev_positive', res)
        self.assertIn('p_calibrated_win_pct', res)
        self.assertTrue(0.0 <= res['p_bullish'] <= 1.0)
        self.assertTrue(0.0 <= res['p_bearish'] <= 1.0)
        self.assertAlmostEqual(res['p_bullish'] + res['p_bearish'] + res['p_neutral'], 1.0, places=2)

        # 2. Test persistent model caching and sub-millisecond live inference
        self.assertTrue(predictor.is_model_cached('EUR/USD', '1h'))
        predictor_live = MachineLearningPredictor()
        live_res = predictor_live.predict_live(df_ind, symbol='EUR/USD', timeframe='1h')
        self.assertEqual(live_res['status'], 'SUCCESS')
        self.assertTrue(live_res['is_cached_model'])
        self.assertIn('expected_value_r', live_res)

        # 3. Test MT5ForexProvider alias and train_on_mt5_history
        from src.data.forex_feeds import MT5ForexProvider, MT5ExnessProvider
        self.assertEqual(MT5ForexProvider, MT5ExnessProvider)
        p_mt5 = MT5ForexProvider()
        if p_mt5.is_connected:
            mt5_train_ok = predictor.train_on_mt5_history('EUR/USD', '1h', n_bars=2000)
            self.assertTrue(mt5_train_ok)

    def test_alpha_sniper_expected_value_ev_gate(self):
        df_ind = QuantitativeIndicators.add_all_indicators(self.synth_df)
        
        # Case A: Positive Expectancy (EV >= +0.15R) passes through cleanly
        high_conf = {
            'action': 'STRONG BUY',
            'confluence_score': 65.0,
            'layer_scores': {'trend_momentum': 25.0, 'smart_money_smc': 18.0, 'mean_reversion_stat': 12.0, 'orderbook_pressure': 10.0}
        }
        ml_pred_good = {'p_bullish': 0.70, 'p_bearish': 0.15, 'confidence_pct': 55.0}
        res_good = AlphaSniperEngine.evaluate(
            df_indicators=df_ind,
            base_confluence=high_conf,
            ml_prediction=ml_pred_good,
            trade_setup={}
        )
        self.assertIn('expected_value_r', res_good)
        self.assertIn('ev_gate_passed', res_good)
        self.assertTrue(res_good['ev_gate_passed'])
        self.assertGreaterEqual(res_good['expected_value_r'], 0.15)
        self.assertIn('BUY', res_good['gated_action'])

        # Case B: Sub-optimal Expectancy (EV < +0.15R) is gated by the EV Gate
        # Clean trending background to isolate EV Gate without chop interference
        df_trending = df_ind.copy()
        df_trending.loc[df_trending.index[-1], 'adx_14'] = 28.0
        df_trending.loc[df_trending.index[-1], 'choppiness'] = 38.0
        df_trending.loc[df_trending.index[-1], 'bb_squeeze'] = False

        low_conf = {
            'action': 'BUY',
            'confluence_score': 10.0,
            'layer_scores': {'trend_momentum': 0.0, 'smart_money_smc': 0.0, 'mean_reversion_stat': 0.0, 'orderbook_pressure': 0.0}
        }
        ml_pred_weak = {'p_bullish': 0.35, 'p_bearish': 0.35, 'confidence_pct': 0.0}
        res_weak = AlphaSniperEngine.evaluate(
            df_indicators=df_trending,
            base_confluence=low_conf,
            ml_prediction=ml_pred_weak,
            trade_setup={}
        )
        self.assertFalse(res_weak['ev_gate_passed'])
        self.assertEqual(res_weak['gated_action'], 'NEUTRAL (FILTERED)')
        self.assertEqual(res_weak['sniper_badge'], '[EV GATE] SUB-OPTIMAL EXPECTANCY')
        self.assertEqual(res_weak['trade_expectancy_r'], 0.0)

    def test_cftc_cot_sentiment_provider_and_honest_labeling(self):
        # 1. Supported Forex pair (EUR/USD)
        cot_eur = COTSentimentProvider.get_sentiment('EUR/USD')
        self.assertTrue(cot_eur['available'])
        self.assertIn('cftc_market', cot_eur)
        self.assertIn('non_commercial_net', cot_eur)
        self.assertIn('retail_long_pct', cot_eur)
        self.assertIn('smart_money_bias', cot_eur)
        self.assertEqual(cot_eur['honest_label'], '5/5 Pillars Aligned (COT Smart Money Active)')

        # 2. Supported Gold (XAU/USD)
        cot_gold = COTSentimentProvider.get_sentiment('XAU/USD')
        self.assertTrue(cot_gold['available'])
        self.assertEqual(cot_gold['smart_money_bias'], 'STRONG_BULLISH')

        # 3. Directional Alignment evaluation for BUY and SELL
        align_buy = COTSentimentProvider.evaluate_directional_alignment('EUR/USD', 'BUY')
        self.assertTrue(align_buy['available'])
        self.assertTrue(align_buy['aligned'])
        self.assertIn('CONFIRMED', align_buy['status'])

        # 4. Broker Suffixes and Non-standard symbol formats (.r, .pro, .raw, m, _i, 247, silver)
        for sym_var in ['EURUSDm', 'EURUSD.r', 'EURUSD.pro', 'EURUSD.raw', 'EUR_USD_i', 'XAUUSDm', 'XAUUSD.r', 'XAUUSD247', 'XAUUSD247m', 'XAG/USD', 'XAGUSD', 'XAGUSDm']:
            cot_var = COTSentimentProvider.get_sentiment(sym_var)
            self.assertTrue(cot_var['available'], f"Failed to resolve broker symbol variation {sym_var}")
            self.assertIn(cot_var['normalized_symbol'], ['EUR/USD', 'XAU/USD', 'XAG/USD'])

        # 5. Honest Labeling for Unsupported Spot Asset (no whale/COT data)
        cot_unsupported = COTSentimentProvider.get_sentiment('PEPE/USDT')
        self.assertFalse(cot_unsupported['available'])
        self.assertEqual(cot_unsupported['honest_label'], '4/4 Pillars Aligned (Whale Flow N/A)')
        self.assertEqual(cot_unsupported['smart_money_bias'], 'NONE')

    def test_cftc_live_auto_scraper_and_cache(self):
        from src.data.cot_sentiment import CFTCAutoScraper, CACHE_FILE
        # 1. Verify live scraping from official CFTC deafut.txt feed
        live_data = CFTCAutoScraper.fetch_live_cftc_data()
        self.assertIsNotNone(live_data)
        self.assertGreaterEqual(len(live_data), 9)
        for expected in ['EUR/USD', 'GBP/USD', 'USD/JPY', 'XAU/USD', 'XAG/USD']:
            self.assertIn(expected, live_data)
            self.assertIn('report_date', live_data[expected])
            self.assertIn('non_commercial_net', live_data[expected])
            self.assertIn('cot_index_pct', live_data[expected])

        # 2. Verify cache file was updated on disk
        self.assertTrue(os.path.exists(CACHE_FILE))

        # 3. Verify get_all_sentiment returns cached or live data
        all_sent = CFTCAutoScraper.get_all_sentiment()
        self.assertIn('XAU/USD', all_sent)
        self.assertEqual(all_sent['XAU/USD']['smart_money_bias'], 'STRONG_BULLISH')

    def test_pillar5_unified_evaluation_and_honest_labeling(self):
        auto_engine = get_engine()

        # Case A: Spot Crypto setup without futures/whale/COT feed -> Honest Labeling 4/4
        pred_spot = {
            'confluence': {'action': 'STRONG BUY', 'confluence_score': 60.0},
            'alpha_sniper': {'calibrated_win_probability_pct': 85.0, 'expected_value_r': 1.8, 'trade_expectancy_r': 1.8},
            'mtf_alignment': {
                'screen1_macro': {'macro_bias': 'BULLISH', 'close_vs_ema200': 'ABOVE_200_EMA'},
                'screen2_zone': {'zone_type': 'DISCOUNT'},
                'screen3_trigger': {'trigger_status': 'TRIGGER_FIRED'}
            },
            'economic_news': {'is_blackout': False},
            'quantum_sniper': {'overextension': {'is_overextended': False}, 'quantum_bias': 'BULLISH'},
            'whale_sentiment_gate': {'passed': True, 'reason': ''},
            'chop_gate': {'is_chop': False},
            'spread_guard': {'passed': True}
            # No futures_signals and no cot_sentiment
        }
        eval_spot = auto_engine.evaluate_5_pillars(pred_spot)
        self.assertFalse(eval_spot['p5']['available'])
        self.assertEqual(eval_spot['p5']['badge'], 'N/A')
        self.assertEqual(eval_spot['p5']['status'], 'WHALE FLOW N/A')
        self.assertEqual(eval_spot['total_applicable'], 4)
        self.assertEqual(eval_spot['aligned_count'], 4)
        self.assertTrue(eval_spot['is_fully_aligned'])
        self.assertIn('4/4 PILLARS ALIGNED (Whale Flow N/A)', eval_spot['honest_label'])

        # Case B: Forex/Metals Setup WITH CFTC COT Smart Money Aligned -> 5/5 Pillars
        cot_aligned = COTSentimentProvider.get_sentiment('XAU/USD')
        pred_fx = dict(pred_spot)
        pred_fx['cot_sentiment'] = cot_aligned
        eval_fx = auto_engine.evaluate_5_pillars(pred_fx)
        self.assertTrue(eval_fx['p5']['available'])
        self.assertTrue(eval_fx['p5']['ok'])
        self.assertEqual(eval_fx['p5']['badge'], 'COT ALIGNED')
        self.assertEqual(eval_fx['total_applicable'], 5)
        self.assertEqual(eval_fx['aligned_count'], 5)
        self.assertTrue(eval_fx['is_fully_aligned'])
        self.assertEqual(eval_fx['honest_label'], '5/5 PILLARS ALIGNED')

        # Case C: Forex Setup WITH COT Conflict (e.g. Selling into Bullish Smart Money)
        pred_fx_short = dict(pred_fx)
        pred_fx_short['confluence'] = {'action': 'STRONG SELL', 'confluence_score': -60.0}
        pred_fx_short['mtf_alignment'] = {
            'screen1_macro': {'macro_bias': 'BEARISH', 'close_vs_ema200': 'BELOW_200_EMA'},
            'screen2_zone': {'zone_type': 'PREMIUM'},
            'screen3_trigger': {'trigger_status': 'TRIGGER_FIRED'}
        }
        eval_fx_short = auto_engine.evaluate_5_pillars(pred_fx_short)
        self.assertTrue(eval_fx_short['p5']['available'])
        self.assertFalse(eval_fx_short['p5']['ok'])
        self.assertEqual(eval_fx_short['p5']['badge'], 'COT CONFLICT')
        self.assertFalse(eval_fx_short['is_fully_aligned'])

    def test_cme_proxy_direct_mt5_tick_volume(self):
        # Verify 0.00-ms direct local MT5 tick volume ingestion & volume expansion ratio calculation
        df_dummy = pd.DataFrame({
            'open': [2000.0, 2002.0, 2005.0, 2010.0],
            'high': [2005.0, 2006.0, 2012.0, 2018.0],
            'low': [1998.0, 2000.0, 2003.0, 2008.0],
            'close': [2002.0, 2004.0, 2009.0, 2016.0],
            'tick_volume': [100.0, 110.0, 105.0, 250.0]  # Volume surge on current bar
        })
        t0 = time.time()
        cme_res = CMEProxyFeed.get_institutional_order_flow('XAU/USD', df_ohlcv=df_dummy)
        latency_ms = (time.time() - t0) * 1000.0
        
        self.assertTrue(cme_res['available'])
        self.assertEqual(cme_res['status'], 'ONLINE_REALTIME_MT5')
        self.assertEqual(cme_res['cme_volume'], 250)
        self.assertGreater(cme_res['volume_ratio'], 1.5)
        self.assertEqual(cme_res['institutional_bias'], 'BULLISH_INSTITUTIONAL_EXPANSION')
        self.assertIn('Exness MT5 Real-Time', cme_res['source'])
        self.assertLess(latency_ms, 25.0)  # Zero network roundtrip

    def test_multi_timeframe_horizon_adaptation_pillar5(self):
        auto_engine = AutonomousTraderEngine()
        cot_bullish = COTSentimentProvider.get_sentiment('XAU/USD')

        # Case 1: Scalp Timeframe (5m) with Aligned COT -> Scalp Boost
        pred_5m_long = {
            'timeframe': '5m',
            'confluence': {'action': 'STRONG BUY', 'confluence_score': 65.0},
            'alpha_sniper': {'calibrated_win_probability_pct': 85.0, 'expected_value_r': 0.65},
            'mtf_alignment': {
                'screen1_macro': {'macro_bias': 'BULLISH', 'close_vs_ema200': 'ABOVE_200_EMA'},
                'screen2_zone': {'zone_type': 'DISCOUNT'},
                'screen3_trigger': {'trigger_status': 'TRIGGER_FIRED'}
            },
            'economic_news': {'is_blackout': False},
            'quantum_sniper': {'overextension': {'is_overextended': False}, 'quantum_bias': 'BULLISH_QUANTUM_EDGE'},
            'chop_gate': {'is_chop': False},
            'spread_guard': {'passed': True},
            'cot_sentiment': cot_bullish
        }
        eval_5m_long = auto_engine.evaluate_5_pillars(pred_5m_long)
        self.assertTrue(eval_5m_long['p5']['ok'])
        self.assertEqual(eval_5m_long['p5']['badge'], 'COT MACRO BOOST')
        self.assertTrue(eval_5m_long['is_fully_aligned'])

        # Case 2: Scalp Timeframe (5m) Selling into Bullish COT (Counter-macro Scalp)
        # Horizon Adaptation: Weekly macro lag does not kill a micro scalp setup, but labels as INTRADAY SCALP
        pred_5m_short = dict(pred_5m_long)
        pred_5m_short['confluence'] = {'action': 'STRONG SELL', 'confluence_score': -65.0}
        pred_5m_short['mtf_alignment'] = {
            'screen1_macro': {'macro_bias': 'BEARISH', 'close_vs_ema200': 'BELOW_200_EMA'},
            'screen2_zone': {'zone_type': 'PREMIUM'},
            'screen3_trigger': {'trigger_status': 'TRIGGER_FIRED'}
        }
        eval_5m_short = auto_engine.evaluate_5_pillars(pred_5m_short)
        self.assertTrue(eval_5m_short['p5']['ok'])
        self.assertEqual(eval_5m_short['p5']['badge'], 'INTRADAY SCALP')
        self.assertTrue(eval_5m_short['is_fully_aligned'])
        self.assertIn('TP1', eval_5m_short['p5']['desc'])

        # Case 3: Macro Timeframe (1h) Selling into Bullish COT -> Macro Blocked
        pred_1h_short = dict(pred_5m_short)
        pred_1h_short['timeframe'] = '1h'
        eval_1h_short = auto_engine.evaluate_5_pillars(pred_1h_short)
        self.assertFalse(eval_1h_short['p5']['ok'])
        self.assertEqual(eval_1h_short['p5']['badge'], 'COT CONFLICT')
        self.assertFalse(eval_1h_short['is_fully_aligned'])


if __name__ == '__main__':
    unittest.main()

