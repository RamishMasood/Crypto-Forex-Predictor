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

class TestCryptoForexPredictor(unittest.TestCase):

    def setUp(self):
        # Generate synthetic OHLCV dataframe for reliable unit testing of calculations
        np.random.seed(42)
        n = 80
        dates = pd.date_range('2026-01-01', periods=n, freq='1H')
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

if __name__ == '__main__':
    unittest.main()
