"""
Unified Cryptocurrency Multi-Exchange Data Provider
Integrates real public APIs across Binance, Bybit, Coinbase, KuCoin, Gate.io, and CoinGecko.
Requires zero private API keys.
"""

import time
import requests
import pandas as pd
import ccxt
from typing import Dict, Any, List, Optional

SUPPORTED_CRYPTO_EXCHANGES = ['binance', 'bybit', 'coinbase', 'kucoin', 'gateio']

BINANCE_REST_ENDPOINTS = [
    'https://api.binance.com',
    'https://api1.binance.com',
    'https://api2.binance.com',
    'https://api3.binance.com',
]

TIMEFRAME_MAP = {
    '1m': '1m',
    '3m': '3m',
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1h',
    '4h': '4h',
    '1d': '1d'
}

class CryptoFeedManager:
    """
    Unified manager for querying real-time market data across multiple crypto exchanges
    using public APIs with zero API key dependencies.
    """
    def __init__(self):
        self.exchanges: Dict[str, Any] = {}
        self._init_ccxt_exchanges()

    def _init_ccxt_exchanges(self):
        for name, cls in [
            ('bybit', getattr(ccxt, 'bybit', None)),
            ('coinbase', getattr(ccxt, 'coinbase', None)),
            ('kucoin', getattr(ccxt, 'kucoin', None)),
            ('gateio', getattr(ccxt, 'gateio', getattr(ccxt, 'gate', None)))
        ]:
            if cls is None:
                continue
            try:
                self.exchanges[name] = cls({'enableRateLimit': True, 'timeout': 2500})
            except Exception:
                pass

    def _normalize_binance_symbol(self, symbol: str) -> str:
        # e.g., 'BTC/USDT' -> 'BTCUSDT'
        return symbol.replace('/', '').replace('-', '').upper()

    def _fetch_binance_ticker_direct(self, symbol: str) -> Optional[Dict[str, Any]]:
        clean_symbol = self._normalize_binance_symbol(symbol)
        for base_url in BINANCE_REST_ENDPOINTS:
            try:
                url = f"{base_url}/api/v3/ticker/24hr?symbol={clean_symbol}"
                resp = requests.get(url, timeout=4)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        'exchange': 'binance',
                        'symbol': symbol,
                        'last': float(data['lastPrice']),
                        'high': float(data['highPrice']),
                        'low': float(data['lowPrice']),
                        'volume': float(data['volume']),
                        'quote_volume': float(data['quoteVolume']),
                        'change_24h_pct': float(data['priceChangePercent']),
                        'timestamp': int(data['closeTime'])
                    }
            except Exception:
                continue
        return None

    def _fetch_binance_klines_direct(self, symbol: str, interval: str = '1h', limit: int = 150) -> Optional[pd.DataFrame]:
        clean_symbol = self._normalize_binance_symbol(symbol)
        for base_url in BINANCE_REST_ENDPOINTS:
            try:
                url = f"{base_url}/api/v3/klines?symbol={clean_symbol}&interval={interval}&limit={limit}"
                resp = requests.get(url, timeout=6)
                if resp.status_code == 200:
                    raw = resp.json()
                    rows = []
                    for k in raw:
                        rows.append({
                            'timestamp': pd.to_datetime(k[0], unit='ms'),
                            'open': float(k[1]),
                            'high': float(k[2]),
                            'low': float(k[3]),
                            'close': float(k[4]),
                            'volume': float(k[5]),
                        })
                    df = pd.DataFrame(rows)
                    return df
            except Exception:
                continue
        return None

    def get_live_ticker(self, symbol: str = 'BTC/USDT', exchange: str = 'binance') -> Optional[Dict[str, Any]]:
        """
        Fetch real-time ticker data for a specified symbol and exchange with automatic fallback.
        """
        exchange = exchange.lower()
        if exchange == 'binance':
            binance_res = self._fetch_binance_ticker_direct(symbol)
            if binance_res:
                return binance_res
            exchange = 'bybit'

        if exchange in self.exchanges:
            try:
                query_sym = symbol
                if exchange == 'coinbase' and symbol.endswith('/USDT'):
                    query_sym = symbol.replace('/USDT', '/USD')
                ticker = self.exchanges[exchange].fetch_ticker(query_sym)
                last_price = ticker.get('last') or ticker.get('close')
                if last_price is not None:
                    return {
                        'exchange': exchange,
                        'symbol': symbol,
                        'last': float(last_price),
                        'high': float(ticker.get('high') or last_price),
                        'low': float(ticker.get('low') or last_price),
                        'volume': float(ticker.get('baseVolume') or 0.0),
                        'quote_volume': float(ticker.get('quoteVolume') or 0.0),
                        'change_24h_pct': float(ticker.get('percentage') or 0.0),
                        'timestamp': ticker.get('timestamp') or int(time.time() * 1000)
                    }
            except Exception:
                pass

        # Try fallback to any available exchange
        for ex_name, ex_obj in self.exchanges.items():
            try:
                query_sym = symbol
                if ex_name == 'coinbase' and symbol.endswith('/USDT'):
                    query_sym = symbol.replace('/USDT', '/USD')
                ticker = ex_obj.fetch_ticker(query_sym)
                last_price = ticker.get('last') or ticker.get('close')
                if last_price:
                    return {
                        'exchange': ex_name,
                        'symbol': symbol,
                        'last': float(last_price),
                        'high': float(ticker.get('high') or last_price),
                        'low': float(ticker.get('low') or last_price),
                        'volume': float(ticker.get('baseVolume') or 0.0),
                        'quote_volume': float(ticker.get('quoteVolume') or 0.0),
                        'change_24h_pct': float(ticker.get('percentage') or 0.0),
                        'timestamp': ticker.get('timestamp') or int(time.time() * 1000)
                    }
            except Exception:
                continue

        return None

    def get_multi_exchange_prices(self, symbol: str = 'BTC/USDT') -> Dict[str, Dict[str, Any]]:
        """
        Fetch simultaneous quotes across all supported exchanges to compare prices, spreads, and liquidity.
        """
        results = {}
        # Binance Direct
        b_res = self._fetch_binance_ticker_direct(symbol)
        if b_res:
            results['binance'] = {
                'price': b_res['last'],
                'change_24h': b_res['change_24h_pct'],
                'volume': b_res['volume'],
                'status': 'ONLINE'
            }
        else:
            results['binance'] = {
                'price': None,
                'change_24h': None,
                'volume': None,
                'status': 'OFFLINE/TIMEOUT'
            }

        # Query CCXT exchanges
        for ex_name, ex_obj in self.exchanges.items():
            try:
                query_sym = symbol
                if ex_name == 'coinbase' and symbol.endswith('/USDT'):
                    query_sym = symbol.replace('/USDT', '/USD')
                
                ticker = ex_obj.fetch_ticker(query_sym)
                last_p = ticker.get('last') or ticker.get('close')
                if last_p is not None:
                    results[ex_name] = {
                        'price': float(last_p),
                        'change_24h': float(ticker.get('percentage') or 0.0),
                        'volume': float(ticker.get('baseVolume') or 0.0),
                        'status': 'ONLINE'
                    }
                else:
                    results[ex_name] = {
                        'price': None,
                        'change_24h': None,
                        'volume': None,
                        'status': 'NO DATA'
                    }
            except Exception:
                results[ex_name] = {
                    'price': None,
                    'change_24h': None,
                    'volume': None,
                    'status': 'UNAVAILABLE'
                }

        return results

    def get_ohlcv(self, symbol: str = 'BTC/USDT', timeframe: str = '1h', limit: int = 150, preferred_exchange: str = 'binance') -> pd.DataFrame:
        """
        Fetch standardized OHLCV historical candlestick data.
        Returns DataFrame with columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        """
        preferred_exchange = preferred_exchange.lower()
        if preferred_exchange == 'binance':
            df = self._fetch_binance_klines_direct(symbol, interval=timeframe, limit=limit)
            if df is not None and not df.empty:
                return df
            preferred_exchange = 'bybit'

        if preferred_exchange in self.exchanges:
            try:
                query_sym = symbol
                if preferred_exchange == 'coinbase' and symbol.endswith('/USDT'):
                    query_sym = symbol.replace('/USDT', '/USD')
                candles = self.exchanges[preferred_exchange].fetch_ohlcv(query_sym, timeframe=timeframe, limit=limit)
                if candles and len(candles) > 0:
                    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    return df
            except Exception:
                pass

        # Try fallback to any CCXT exchange
        for ex_name, ex_obj in self.exchanges.items():
            try:
                query_sym = symbol
                if ex_name == 'coinbase' and symbol.endswith('/USDT'):
                    query_sym = symbol.replace('/USDT', '/USD')
                candles = ex_obj.fetch_ohlcv(query_sym, timeframe=timeframe, limit=limit)
                if candles and len(candles) > 0:
                    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    return df
            except Exception:
                continue

        raise ConnectionError(f"Could not retrieve live OHLCV data for {symbol} on timeframe {timeframe} across available exchanges.")
