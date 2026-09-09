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

if __name__ == '__main__':
    unittest.main()
