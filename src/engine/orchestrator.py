"""
Master Predictor Orchestrator
Coordinates live data ingestion, multi-exchange analysis, SMC detection,
quant indicators, ML predictions, futures signals, and institutional risk management.
Supports both SPOT and FUTURES market modes.
"""

from typing import Dict, Any, Optional
import pandas as pd

from ..data.crypto_feeds import CryptoFeedManager
from ..data.forex_feeds import ForexFeedManager
from ..data.futures_feeds import FuturesFeedManager
from ..data.orderbook_depth import OrderBookAnalyzer
from ..strategies.indicators import QuantitativeIndicators
from ..strategies.smc import SmartMoneyConcepts
from ..strategies.arbitrage import CrossExchangeArbitrage
from ..strategies.futures_signals import FuturesSignalEngine
from ..ml.predictor import MachineLearningPredictor
from ..engine.confluence import ConfluenceEngine
from ..engine.risk_manager import RiskManager
from ..strategies.alpha_sniper import AlphaSniperEngine


class PredictorOrchestrator:
    """
    Central pipeline for real Crypto, Forex, and Futures market prediction.
    """

    def __init__(self):
        self.crypto_feeds  = CryptoFeedManager()
        self.forex_feeds   = ForexFeedManager()
        self.futures_feeds = FuturesFeedManager()
        self.orderbook_analyzer = OrderBookAnalyzer()

    def run_prediction(
        self,
        symbol: str = 'BTC/USDT',
        asset_type: str = 'crypto',         # 'crypto' | 'forex'
        market_mode: str = 'spot',          # 'spot'   | 'futures'
        timeframe: str = '1h',
        preferred_exchange: str = 'binance',
        account_size_usd: float = 10000.0,
        risk_per_trade_pct: float = 1.5
    ) -> Dict[str, Any]:
        """
        Executes end-to-end multi-exchange real-time prediction and risk analysis.
        """
        asset_type  = asset_type.lower()
        market_mode = market_mode.lower()
        is_futures  = (market_mode == 'futures') and (asset_type == 'crypto')

        # ────────────────────────────────────────────────────
        # STEP 1: INGEST LIVE DATA
        # ────────────────────────────────────────────────────
        futures_raw_data: Optional[Dict] = None
        futures_signals_result: Optional[Dict] = None

        if is_futures:
            # Primary: Bybit Perp live data
            futures_raw_data = self.futures_feeds.get_all_futures_data(
                symbol=symbol, timeframe=timeframe, limit=150
            )
            df_ohlcv  = futures_raw_data['ohlcv']
            live_ticker = futures_raw_data['ticker']
            # Also get spot price for basis calculation
            spot_ticker = self.crypto_feeds.get_live_ticker(symbol, 'binance')
            spot_price  = spot_ticker['last'] if spot_ticker else 0.0

            # Recompute basis with real spot price
            if spot_price > 0 and live_ticker:
                futures_raw_data['basis'] = self.futures_feeds.compute_basis(
                    spot_price, live_ticker['last']
                )

            exchange_prices    = self.crypto_feeds.get_multi_exchange_prices(symbol)
            arbitrage_data     = CrossExchangeArbitrage.analyze_spreads(exchange_prices)
            orderbook_data     = self.orderbook_analyzer.get_order_book_metrics(symbol, 'bybit')
            forex_sessions     = None

        elif asset_type == 'crypto':
            live_ticker        = self.crypto_feeds.get_live_ticker(symbol, preferred_exchange)
            df_ohlcv           = self.crypto_feeds.get_ohlcv(symbol, timeframe=timeframe, limit=150, preferred_exchange=preferred_exchange)
            exchange_prices    = self.crypto_feeds.get_multi_exchange_prices(symbol)
            arbitrage_data     = CrossExchangeArbitrage.analyze_spreads(exchange_prices)
            orderbook_data     = self.orderbook_analyzer.get_order_book_metrics(symbol, preferred_exchange)
            forex_sessions     = None
        else:
            live_ticker        = self.forex_feeds.get_live_ticker(symbol)
            df_ohlcv           = self.forex_feeds.get_ohlcv(symbol, timeframe=timeframe, limit=150)
            exchange_prices    = {'forex_interbank': {'price': live_ticker['last'] if live_ticker else None, 'status': 'ONLINE'}}
            arbitrage_data     = {'arbitrage_available': False, 'reason': 'Unified interbank pricing'}
            orderbook_data     = {'available': False, 'pressure_bias': 'INTERBANK_LIQUIDITY'}
            forex_sessions     = self.forex_feeds.get_market_sessions()

        if df_ohlcv is None or df_ohlcv.empty:
            raise ConnectionError(f"No OHLCV data returned for {symbol}")

        current_price = float(live_ticker['last']) if live_ticker else float(df_ohlcv['close'].iloc[-1])

        # ────────────────────────────────────────────────────
        # STEP 2: QUANTITATIVE INDICATORS
        # ────────────────────────────────────────────────────
        df_indicators = QuantitativeIndicators.add_all_indicators(df_ohlcv)
        latest_ind    = df_indicators.iloc[-1]
        atr_val       = float(latest_ind.get('atr_14', current_price * 0.015))

        # ────────────────────────────────────────────────────
        # STEP 3: SMART MONEY CONCEPTS
        # ────────────────────────────────────────────────────
        fvgs             = SmartMoneyConcepts.detect_fair_value_gaps(df_indicators)
        order_blocks     = SmartMoneyConcepts.detect_order_blocks(df_indicators)
        market_structure = SmartMoneyConcepts.analyze_market_structure(df_indicators)
        smc_data         = {
            'fvgs': fvgs,
            'order_blocks': order_blocks,
            'structure': market_structure
        }

        # ────────────────────────────────────────────────────
        # STEP 4: MACHINE LEARNING
        # ────────────────────────────────────────────────────
        ml_model     = MachineLearningPredictor(n_estimators=50)
        ml_prediction = ml_model.fit_and_predict(df_indicators, horizon=3, threshold_pct=0.25)

        # ────────────────────────────────────────────────────
        # STEP 5: FUTURES-SPECIFIC SIGNALS (if futures mode)
        # ────────────────────────────────────────────────────
        if is_futures and futures_raw_data:
            current_funding  = futures_raw_data.get('current_funding_rate', 0.0)
            funding_history  = futures_raw_data.get('funding_history', pd.DataFrame())
            oi_history       = futures_raw_data.get('oi_history', pd.DataFrame())
            current_oi       = futures_raw_data.get('current_oi', 0.0)
            ls_ratio         = futures_raw_data.get('long_short_ratio', {'long_pct': 50, 'short_pct': 50, 'bias': 'BALANCED'})
            basis_data       = futures_raw_data.get('basis', {})

            f1_funding = FuturesSignalEngine.analyze_funding_rate(current_funding, funding_history)
            f2_oi      = FuturesSignalEngine.analyze_open_interest(oi_history, current_price, current_oi)
            f3_squeeze = FuturesSignalEngine.detect_squeeze(
                current_funding, f2_oi, current_price,
                market_structure.get('recent_swing_high', current_price * 1.02),
                market_structure.get('recent_swing_low',  current_price * 0.98),
                ls_ratio
            )
            f4_basis = FuturesSignalEngine.analyze_basis(basis_data)
            f5_cvd = FuturesSignalEngine.analyze_cvd(df_indicators)
            f6_vwap = FuturesSignalEngine.analyze_vwap(df_indicators, current_price)
            f7_liq = FuturesSignalEngine.calculate_liquidation_clusters(
                current_price,
                market_structure.get('recent_swing_high', current_price * 1.02),
                market_structure.get('recent_swing_low',  current_price * 0.98),
                current_oi
            )
            f8_scalp = FuturesSignalEngine.analyze_scalping_signals(df_indicators, timeframe)

            futures_signals_result = {
                'funding_analysis': f1_funding,
                'oi_analysis':      f2_oi,
                'squeeze_analysis': f3_squeeze,
                'basis_analysis':   f4_basis,
                'cvd_analysis':     f5_cvd,
                'vwap_analysis':    f6_vwap,
                'liq_analysis':     f7_liq,
                'scalp_analysis':   f8_scalp,
            }

        # ────────────────────────────────────────────────────
        # STEP 6: CONFLUENCE ENGINE
        # ────────────────────────────────────────────────────
        confluence = ConfluenceEngine.evaluate(
            df_indicators=df_indicators,
            smc_data=smc_data,
            ml_prediction=ml_prediction,
            orderbook_metrics=orderbook_data,
            futures_signals=futures_signals_result
        )

        # ────────────────────────────────────────────────────
        # STEP 7: PROPRIETARY ALPHASNIPER™ INTELLIGENCE & CONVICTION FILTER
        # ────────────────────────────────────────────────────
        alpha_sniper = AlphaSniperEngine.evaluate(
            df_indicators=df_indicators,
            base_confluence=confluence,
            ml_prediction=ml_prediction,
            trade_setup={'dummy': True},
            futures_signals=futures_signals_result
        )

        effective_action = alpha_sniper['gated_action'] if 'FILTERED' in alpha_sniper['gated_action'] else confluence['action']

        # ────────────────────────────────────────────────────
        # STEP 8: INSTITUTIONAL RISK MANAGEMENT
        # ────────────────────────────────────────────────────
        calibrated_win_rate = alpha_sniper['calibrated_win_probability_pct'] / 100.0
        trade_setup = RiskManager.generate_trade_setup(
            current_price=current_price,
            action=effective_action,
            atr=atr_val,
            recent_swing_high=market_structure.get('recent_swing_high'),
            recent_swing_low=market_structure.get('recent_swing_low'),
            account_size_usd=account_size_usd,
            risk_per_trade_pct=risk_per_trade_pct,
            win_probability=calibrated_win_rate
        )

        # ────────────────────────────────────────────────────
        # ASSEMBLE FULL RESULT
        # ────────────────────────────────────────────────────
        result = {
            'metadata': {
                'symbol': symbol,
                'asset_type': asset_type,
                'market_mode': market_mode,
                'timeframe': timeframe,
                'exchange': ('bybit_perp' if is_futures else preferred_exchange) if asset_type == 'crypto' else 'Interbank Forex',
                'timestamp': pd.Timestamp.now().isoformat()
            },
            'market_data': {
                'current_price': current_price,
                'ticker': live_ticker,
                'multi_exchange_prices': exchange_prices,
                'orderbook': orderbook_data,
                'forex_sessions': forex_sessions
            },
            'confluence': confluence,
            'alpha_sniper': alpha_sniper,
            'trade_setup': trade_setup,
            'ml_prediction': ml_prediction,
            'smc_analysis': {
                'structure': market_structure,
                'open_fvgs_count': len([f for f in fvgs if not f['mitigated']]),
                'order_blocks_count': len(order_blocks),
                'active_fvgs': [f for f in fvgs if not f['mitigated']][-4:],
                'active_order_blocks': order_blocks[-4:]
            },
            'arbitrage': arbitrage_data,
            'indicators_summary': {
                'rsi_14': round(float(latest_ind.get('rsi_14', 50)), 2),
                'adx_14': round(float(latest_ind.get('adx_14', 20)), 2),
                'supertrend_dir': 'BULLISH' if latest_ind.get('supertrend_dir', 0) == 1 else 'BEARISH',
                'supertrend_level': round(float(latest_ind.get('supertrend', current_price)), 4),
                'ema_20': round(float(latest_ind.get('ema_20', current_price)), 4),
                'ema_50': round(float(latest_ind.get('ema_50', current_price)), 4),
                'ema_200': round(float(latest_ind.get('ema_200', current_price)), 4),
                'vwap': round(float(latest_ind.get('vwap', current_price)), 4),
                'vwap_bias': str(latest_ind.get('vwap_bias', 'NEUTRAL')),
                'cvd': round(float(latest_ind.get('cvd', 0)), 2),
                'choppiness': round(float(latest_ind.get('choppiness', 50)), 2),
                'hurst_exponent': round(float(latest_ind.get('hurst_exponent', 0.5)), 3),
                'alpha_regime': str(latest_ind.get('alpha_regime', 'RANDOM_WALK_NOISE')),
                'atr_14': round(atr_val, 5),
                'bb_squeeze': bool(latest_ind.get('bb_squeeze', False)),
                'stoch_rsi_k': round(float(latest_ind.get('stoch_rsi_k', 50)), 2),
                'stoch_rsi_d': round(float(latest_ind.get('stoch_rsi_d', 50)), 2),
            },
            'df_chart': df_indicators,
            # Futures-specific data
            'futures_data': futures_raw_data if is_futures else None,
            'futures_signals': futures_signals_result
        }

        return result
