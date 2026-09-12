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
from ..data.economic_calendar import EconomicCalendarManager
from ..engine.mtf_filter import MultiTimeframeFilter
from ..data.cme_proxy import CMEProxyFeed
from ..data.currency_strength import CurrencyStrengthMeter
from ..data.cot_sentiment import COTSentimentProvider


class PredictorOrchestrator:
    """
    Central pipeline for real Crypto, Forex, and Futures market prediction.
    """

    def __init__(self):
        self.crypto_feeds  = CryptoFeedManager()
        self.forex_feeds   = ForexFeedManager()
        self.futures_feeds = FuturesFeedManager()
        self.orderbook_analyzer = OrderBookAnalyzer()
        self.economic_calendar = EconomicCalendarManager()
        self.mtf_filter = MultiTimeframeFilter()

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
        is_crypto   = (asset_type == 'crypto') or any(c in symbol.upper() for c in ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'TON', 'BNB', 'ADA'])
        is_futures  = (market_mode == 'futures') and is_crypto

        # ────────────────────────────────────────────────────
        # STEP 1: INGEST LIVE DATA
        # ────────────────────────────────────────────────────
        futures_raw_data: Optional[Dict] = None
        futures_signals_result: Optional[Dict] = None

        use_mt5 = ('Exness' in str(preferred_exchange) or 'MT5' in str(preferred_exchange))
        has_mt5_symbol = False
        if use_mt5 and self.forex_feeds.is_mt5_connected() and getattr(self.forex_feeds, 'mt5_exness', None):
            has_mt5_symbol = bool(self.forex_feeds.mt5_exness.get_exness_symbol(symbol))

        if has_mt5_symbol:
            live_ticker        = self.forex_feeds.get_live_ticker(symbol)
            df_ohlcv           = self.forex_feeds.get_ohlcv(symbol, timeframe=timeframe, limit=150)
            exchange_prices    = {'exness_mt5': {'price': live_ticker['last'] if live_ticker else None, 'status': 'ONLINE'}}
            arbitrage_data     = {'arbitrage_available': False, 'reason': 'Direct Exness MT5 execution'}
            orderbook_data     = self.orderbook_analyzer.get_order_book_metrics(symbol, 'bybit') if is_crypto else {'available': False, 'pressure_bias': 'INTERBANK_LIQUIDITY'}
            forex_sessions     = self.forex_feeds.get_market_sessions() if not is_crypto else None

            # For crypto on MT5, also ingest Bybit derivatives metrics in background for Whale Gate
            if is_crypto:
                try:
                    futures_raw_data = self.futures_feeds.get_all_futures_data(
                        symbol=symbol, timeframe=timeframe, limit=150
                    )
                except Exception:
                    pass

        elif is_futures:
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
            if not use_mt5 and self.forex_feeds.is_mt5_connected():
                self.forex_feeds.disconnect_mt5()
            live_ticker        = self.forex_feeds.get_live_ticker(symbol)
            df_ohlcv           = self.forex_feeds.get_ohlcv(symbol, timeframe=timeframe, limit=150)
            exchange_prices    = {'forex_interbank': {'price': live_ticker['last'] if live_ticker else None, 'status': 'ONLINE'}}
            arbitrage_data     = {'arbitrage_available': False, 'reason': 'Unified interbank pricing'}
            orderbook_data     = {'available': False, 'pressure_bias': 'INTERBANK_LIQUIDITY'}
            forex_sessions     = self.forex_feeds.get_market_sessions()

        if df_ohlcv is None or df_ohlcv.empty:
            raise ConnectionError(f"No OHLCV data returned for {symbol}")

        current_price = float(live_ticker['last']) if live_ticker else float(df_ohlcv['close'].iloc[-1])

        # Compute live spread price if available
        live_spread = 0.0
        if live_ticker and live_ticker.get('ask') and live_ticker.get('bid'):
            try:
                ask_p = float(live_ticker['ask'])
                bid_p = float(live_ticker['bid'])
                if ask_p >= bid_p:
                    live_spread = round(ask_p - bid_p, 6)
            except Exception:
                pass

        # Institutional Decentralized Feeds (CME Proxy, Currency Strength, and CFTC COT Sentiment)
        cme_proxy_data = None
        csm_data = None
        is_gold_or_commodity = any(m in symbol.upper() for m in ['XAU', 'GOLD', 'XAG', 'SILVER', 'WTI', 'OIL', 'CL'])
        if is_gold_or_commodity:
            cme_proxy_data = CMEProxyFeed.get_institutional_order_flow(symbol, df_ohlcv=df_ohlcv)

        if asset_type == 'forex' and not is_gold_or_commodity and not is_crypto:
            csm_data = CurrencyStrengthMeter.evaluate_pair(symbol, 'NEUTRAL')

        cot_data = COTSentimentProvider.get_sentiment(symbol) if not is_crypto else None

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
        # STEP 4: MACHINE LEARNING (Persistent Pre-Trained Weights & MT5 2,000-5,000 Candles)
        # ────────────────────────────────────────────────────
        ml_model = MachineLearningPredictor(n_estimators=50)
        if ml_model.is_model_cached(symbol, timeframe):
            ml_prediction = ml_model.predict_live(df_indicators, symbol=symbol, timeframe=timeframe)
        else:
            mt5_trained = False
            if self.forex_feeds.is_mt5_connected():
                mt5_trained = ml_model.train_on_mt5_history(symbol=symbol, timeframe=timeframe, n_bars=3000)
            if mt5_trained:
                ml_prediction = ml_model.predict_live(df_indicators, symbol=symbol, timeframe=timeframe)
            else:
                ml_prediction = ml_model.fit_and_predict(df_indicators, horizon=3, threshold_pct=0.25, symbol=symbol, timeframe=timeframe)

        # ────────────────────────────────────────────────────
        # STEP 5: FUTURES-SPECIFIC SIGNALS (if futures mode or crypto on MT5)
        # ────────────────────────────────────────────────────
        if (is_futures or (is_crypto and futures_raw_data)) and futures_raw_data:
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
            futures_signals=futures_signals_result,
            cme_proxy=cme_proxy_data,
            currency_strength=csm_data
        )

        # ────────────────────────────────────────────────────
        # STEP 7: MULTI-TIMEFRAME (TRIPLE-SCREEN) & ECONOMIC BLACKOUT
        # ────────────────────────────────────────────────────
        # 1. Economic News & High-Impact Event Blackout Filter
        news_blackout = self.economic_calendar.check_blackout_status(
            symbol=symbol, asset_type=asset_type
        )

        # 2. Ingest Macro (Daily/4h), Intermediate (1h), & Micro (5m/15m) Feeds
        df_macro = None
        df_intermediate = None
        df_micro = None
        try:
            macro_tf = '1d' if timeframe not in ['1d', '1w'] else '1w'
            micro_tf = '5m' if timeframe not in ['1m', '3m', '5m'] else '1m'
            macro_limit = 220  # Minimum bars required to calculate a true 200 EMA
            if asset_type == 'crypto':
                df_macro = self.crypto_feeds.get_ohlcv(symbol, timeframe=macro_tf, limit=macro_limit, preferred_exchange=preferred_exchange)
                if timeframe == '1h':
                    df_intermediate = df_indicators
                else:
                    df_intermediate = self.crypto_feeds.get_ohlcv(symbol, timeframe='1h', limit=80, preferred_exchange=preferred_exchange)
                df_micro = self.crypto_feeds.get_ohlcv(symbol, timeframe=micro_tf, limit=60, preferred_exchange=preferred_exchange)
            else:
                df_macro = self.forex_feeds.get_ohlcv(symbol, timeframe=macro_tf, limit=macro_limit)
                if timeframe == '1h':
                    df_intermediate = df_indicators
                else:
                    df_intermediate = self.forex_feeds.get_ohlcv(symbol, timeframe='1h', limit=80)
                df_micro = self.forex_feeds.get_ohlcv(symbol, timeframe=micro_tf, limit=60)
        except Exception:
            pass

        if df_intermediate is None:
            df_intermediate = df_indicators

        # 3. Triple-Screen Synthesis
        mtf_alignment = self.mtf_filter.evaluate_triple_screen(
            df_macro=df_macro,
            df_intermediate=df_intermediate,
            df_micro=df_micro,
            proposed_action=confluence['action']
        )

        # ────────────────────────────────────────────────────
        # STEP 8: PROPRIETARY ALPHASNIPER™ & QUANTUMSNIPER™ INTELLIGENCE
        # ────────────────────────────────────────────────────
        if csm_data and any(d in str(confluence.get('action', '')).upper() for d in ['BUY', 'SELL']):
            csm_data = CurrencyStrengthMeter.evaluate_pair(symbol, confluence['action'])

        alpha_sniper = AlphaSniperEngine.evaluate(
            df_indicators=df_indicators,
            base_confluence=confluence,
            ml_prediction=ml_prediction,
            trade_setup={'dummy': True},
            futures_signals=futures_signals_result,
            market_structure=market_structure,
            quantum_sniper=None,
            timeframe=timeframe,
            news_blackout=news_blackout,
            mtf_alignment=mtf_alignment,
            cme_proxy=cme_proxy_data,
            currency_strength=csm_data,
            cot_sentiment=cot_data
        )
        quantum_sniper = alpha_sniper.get('quantum_sniper', {})

        is_gated = ('FILTERED' in alpha_sniper['gated_action'] or 'BLACKOUT' in alpha_sniper['gated_action'] or 'CHOP' in alpha_sniper['gated_action'])
        effective_action = alpha_sniper['gated_action'] if is_gated else confluence['action']
        confluence['unfiltered_action'] = confluence.get('action')
        confluence['action'] = effective_action

        # ────────────────────────────────────────────────────
        # STEP 9: INSTITUTIONAL RISK MANAGEMENT
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
            win_probability=calibrated_win_rate,
            timeframe=timeframe,
            spread_price=live_spread
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
                'spread_price': live_spread,
                'multi_exchange_prices': exchange_prices,
                'orderbook': orderbook_data,
                'forex_sessions': forex_sessions
            },
            'confluence': confluence,
            'alpha_sniper': alpha_sniper,
            'quantum_sniper': quantum_sniper,
            'mtf_alignment': mtf_alignment,
            'economic_news': news_blackout,
            'whale_sentiment_gate': {
                'passed': alpha_sniper.get('whale_gate_passed', True),
                'market_mode': market_mode,
                'reason': alpha_sniper.get('whale_gate_reason', ''),
                'cot_sentiment': cot_data
            },
            'trade_setup': trade_setup,
            'cme_proxy_data': cme_proxy_data,
            'currency_strength': csm_data,
            'cot_sentiment': cot_data,
            'chop_gate': alpha_sniper.get('chop_gate', {}),
            'spread_guard': trade_setup.get('spread_filter', {}),
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
                'cvd_zscore': round(float(latest_ind.get('cvd_zscore', 0)), 2),
                'choppiness': round(float(latest_ind.get('choppiness', 50)), 2),
                'hurst_exponent': round(float(latest_ind.get('hurst_exponent', 0.5)), 3),
                'kaufman_er': round(float(latest_ind.get('kaufman_er', 0.3)), 3),
                'cmo_14': round(float(latest_ind.get('cmo_14', 0.0)), 2),
                'alpha_regime': str(latest_ind.get('alpha_regime', 'RANDOM_WALK_NOISE')),
                'market_zone': str(market_structure.get('market_zone', 'EQUILIBRIUM')),
                'in_ote': bool(market_structure.get('in_bull_ote', False) or market_structure.get('in_bear_ote', False)),
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
