"""
Futures Market Data Provider - Bybit Perpetual V5 Public API
Fetches OHLCV candles, live funding rate, historical open interest,
current OI, long/short ratio, and spot-futures basis spread.
Requires ZERO private API keys.
"""

import requests
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List

BYBIT_V5_BASE = "https://api.bybit.com"

# Bybit interval map: our TF -> Bybit interval param
BYBIT_INTERVAL_MAP = {
    '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
    '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
    '1d': 'D', '1w': 'W'
}

BINANCE_FUTURES_ENDPOINTS = [
    'https://fapi.binance.com',
]

class FuturesFeedManager:
    """
    Live perpetual futures data provider using public APIs.
    Primary: Bybit V5 Linear Perpetuals
    Fallback: Binance USD-M Futures (where reachable)
    """

    def _bybit_get(self, path: str, params: dict) -> Optional[dict]:
        try:
            r = requests.get(f"{BYBIT_V5_BASE}{path}", params=params, timeout=6)
            data = r.json()
            if data.get('retCode') == 0:
                return data['result']
        except Exception:
            pass
        return None

    def normalize_symbol(self, symbol: str) -> str:
        """Convert 'BTC/USDT', 'BTC/USD', 'BTCUSDm' -> 'BTCUSDT', 'ETH/BTC' -> 'ETHBTC'"""
        clean = symbol.replace('/', '').replace('-', '').replace('_', '').upper()
        # Strip broker suffixes: 'm', '.r', 'pro', 'raw', 'c' (only when attached to standard pair)
        # Note: Do not strip 'C' if it's part of a 6-character currency pair like ETHBTC
        for suf in ['PRO', 'RAW', '.R', 'M']:
            if clean.endswith(suf) and len(clean) > len(suf) + 2:
                clean = clean[:-len(suf)]
                break
        else:
            if clean.endswith('C') and not clean.endswith('BTC') and len(clean) > 4:
                clean = clean[:-1]

        if clean.endswith('USD') and not clean.endswith('USDT'):
            clean = clean + 'T'
        return clean

    def get_futures_ticker(self, symbol: str = 'BTC/USDT') -> Optional[Dict[str, Any]]:
        """
        Fetch live perpetual futures ticker including mark price,
        index price, funding rate, and 24h statistics.
        """
        clean = self.normalize_symbol(symbol)
        result = self._bybit_get('/v5/market/tickers', {'category': 'linear', 'symbol': clean})
        if result and result.get('list'):
            t = result['list'][0]
            return {
                'exchange': 'bybit_perp',
                'symbol': symbol,
                'last': float(t.get('lastPrice', 0)),
                'mark_price': float(t.get('markPrice', 0)),
                'index_price': float(t.get('indexPrice', 0)),
                'funding_rate': float(t.get('fundingRate', 0)),
                'next_funding_time': t.get('nextFundingTime'),
                'high_24h': float(t.get('highPrice24h', 0)),
                'low_24h': float(t.get('lowPrice24h', 0)),
                'volume_24h': float(t.get('volume24h', 0)),
                'turnover_24h': float(t.get('turnover24h', 0)),
                'open_interest': float(t.get('openInterest', 0)),
                'open_interest_value': float(t.get('openInterestValue', 0)),
                'change_24h_pct': float(t.get('price24hPcnt', 0)) * 100.0,
                'bid': float(t.get('bid1Price', 0)),
                'ask': float(t.get('ask1Price', 0)),
            }
        # Fallback: Binance USD-M futures ticker
        for base in BINANCE_FUTURES_ENDPOINTS:
            try:
                r1 = requests.get(f"{base}/fapi/v1/ticker/24hr", params={'symbol': clean}, timeout=5)
                r2 = requests.get(f"{base}/fapi/v1/premiumIndex", params={'symbol': clean}, timeout=5)
                if r1.status_code == 200:
                    t1 = r1.json()
                    t2 = r2.json() if r2.status_code == 200 else {}
                    last_p = float(t1.get('lastPrice', 0))
                    return {
                        'exchange': 'binance_perp',
                        'symbol': symbol,
                        'last': last_p,
                        'mark_price': float(t2.get('markPrice', last_p)),
                        'index_price': float(t2.get('indexPrice', last_p)),
                        'funding_rate': float(t2.get('lastFundingRate', 0)),
                        'next_funding_time': t2.get('nextFundingTime'),
                        'high_24h': float(t1.get('highPrice', 0)),
                        'low_24h': float(t1.get('lowPrice', 0)),
                        'volume_24h': float(t1.get('volume', 0)),
                        'turnover_24h': float(t1.get('quoteVolume', 0)),
                        'open_interest': 0.0,
                        'open_interest_value': 0.0,
                        'change_24h_pct': float(t1.get('priceChangePercent', 0)),
                        'bid': last_p,
                        'ask': last_p,
                    }
            except Exception:
                continue
        return None

    def get_ohlcv(self, symbol: str = 'BTC/USDT', timeframe: str = '1h', limit: int = 150) -> pd.DataFrame:
        """
        Fetch perpetual futures OHLCV candles via Bybit V5.
        Falls back to Binance USD-M futures.
        """
        clean = self.normalize_symbol(symbol)
        interval = BYBIT_INTERVAL_MAP.get(timeframe, '60')

        result = self._bybit_get('/v5/market/kline', {
            'category': 'linear',
            'symbol': clean,
            'interval': interval,
            'limit': limit
        })
        if result and result.get('list'):
            rows = []
            for candle in reversed(result['list']):  # Bybit returns newest first
                rows.append({
                    'timestamp': pd.to_datetime(int(candle[0]), unit='ms'),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5]),
                })
            df = pd.DataFrame(rows)
            return df

        # Fallback: Binance USD-M futures
        for base in BINANCE_FUTURES_ENDPOINTS:
            try:
                r = requests.get(
                    f"{base}/fapi/v1/klines",
                    params={'symbol': clean, 'interval': timeframe, 'limit': limit},
                    timeout=6
                )
                if r.status_code == 200:
                    raw = r.json()
                    rows = [{
                        'timestamp': pd.to_datetime(k[0], unit='ms'),
                        'open': float(k[1]), 'high': float(k[2]),
                        'low': float(k[3]), 'close': float(k[4]),
                        'volume': float(k[5])
                    } for k in raw]
                    return pd.DataFrame(rows)
            except Exception:
                continue

        raise ConnectionError(f"Cannot fetch futures OHLCV for {symbol}")

    def get_funding_rate_history(self, symbol: str = 'BTC/USDT', limit: int = 96) -> pd.DataFrame:
        """
        Fetch recent funding rate history (default 96 periods = 32 days at 8h intervals).
        Returns DataFrame with [timestamp, funding_rate, funding_rate_pct].
        """
        clean = self.normalize_symbol(symbol)
        result = self._bybit_get('/v5/market/funding/history', {
            'category': 'linear',
            'symbol': clean,
            'limit': min(limit, 200)
        })
        if result and result.get('list'):
            rows = []
            for item in reversed(result['list']):
                rate = float(item.get('fundingRate', 0))
                rows.append({
                    'timestamp': pd.to_datetime(int(item['fundingRateTimestamp']), unit='ms'),
                    'funding_rate': rate,
                    'funding_rate_pct': rate * 100.0,
                    'annualized_pct': rate * 3 * 365 * 100.0  # 3 settlements/day * 365
                })
            return pd.DataFrame(rows)

        # Binance fallback
        for base in BINANCE_FUTURES_ENDPOINTS:
            try:
                r = requests.get(
                    f"{base}/fapi/v1/fundingRate",
                    params={'symbol': clean, 'limit': limit},
                    timeout=6
                )
                if r.status_code == 200:
                    raw = r.json()
                    rows = [{
                        'timestamp': pd.to_datetime(item['fundingTime'], unit='ms'),
                        'funding_rate': float(item['fundingRate']),
                        'funding_rate_pct': float(item['fundingRate']) * 100.0,
                        'annualized_pct': float(item['fundingRate']) * 3 * 365 * 100.0
                    } for item in raw]
                    return pd.DataFrame(rows)
            except Exception:
                continue

        return pd.DataFrame(columns=['timestamp', 'funding_rate', 'funding_rate_pct', 'annualized_pct'])

    def get_open_interest_history(self, symbol: str = 'BTC/USDT', timeframe: str = '1h', limit: int = 50) -> pd.DataFrame:
        """
        Fetch historical open interest data.
        """
        clean = self.normalize_symbol(symbol)
        interval_map = {'5m': '5min', '15m': '15min', '30m': '30min',
                        '1h': '1h', '4h': '4h', '1d': '1d'}
        oi_interval = interval_map.get(timeframe, '1h')

        result = self._bybit_get('/v5/market/open-interest', {
            'category': 'linear',
            'symbol': clean,
            'intervalTime': oi_interval,
            'limit': limit
        })
        if result and result.get('list'):
            rows = []
            for item in reversed(result['list']):
                rows.append({
                    'timestamp': pd.to_datetime(int(item['timestamp']), unit='ms'),
                    'open_interest': float(item['openInterest']),
                })
            df = pd.DataFrame(rows)
            df['oi_change'] = df['open_interest'].diff()
            df['oi_change_pct'] = df['open_interest'].pct_change() * 100.0
            return df

        return pd.DataFrame(columns=['timestamp', 'open_interest', 'oi_change', 'oi_change_pct'])

    def get_long_short_ratio(self, symbol: str = 'BTC/USDT', timeframe: str = '1h', limit: int = 48) -> Optional[Dict[str, Any]]:
        """
        Fetch top trader long/short position ratio from Bybit.
        """
        clean = self.normalize_symbol(symbol)
        result = self._bybit_get('/v5/market/account-ratio', {
            'category': 'linear',
            'symbol': clean,
            'period': '1h' if '1h' in timeframe else '4h',
            'limit': limit
        })
        if result and result.get('list'):
            latest = result['list'][0]
            buy_ratio = float(latest.get('buyRatio', 0.5))
            sell_ratio = float(latest.get('sellRatio', 0.5))
            return {
                'long_pct': round(buy_ratio * 100, 2),
                'short_pct': round(sell_ratio * 100, 2),
                'long_short_ratio': round(buy_ratio / max(sell_ratio, 0.001), 3),
                'bias': 'CROWDED_LONG' if buy_ratio > 0.65 else ('CROWDED_SHORT' if buy_ratio < 0.35 else 'BALANCED'),
                'history': result['list'][:10]
            }
        # Simple fallback if not available
        return {
            'long_pct': 50.0, 'short_pct': 50.0,
            'long_short_ratio': 1.0, 'bias': 'UNKNOWN'
        }

    def compute_basis(self, spot_price: float, futures_price: float) -> Dict[str, Any]:
        """
        Calculate spot-futures basis (premium or discount).
        Positive basis = futures trading above spot (bullish sentiment).
        """
        if spot_price <= 0:
            return {'basis': 0.0, 'basis_pct': 0.0, 'regime': 'UNKNOWN'}

        basis = futures_price - spot_price
        basis_pct = (basis / spot_price) * 100.0

        if basis_pct > 0.3:
            regime = 'HIGH_PREMIUM_BULLISH'
        elif basis_pct > 0.1:
            regime = 'MILD_PREMIUM_BULLISH'
        elif basis_pct < -0.2:
            regime = 'DISCOUNT_BEARISH'
        elif basis_pct < -0.05:
            regime = 'MILD_DISCOUNT'
        else:
            regime = 'NEAR_PARITY'

        return {
            'spot_price': round(spot_price, 4),
            'futures_price': round(futures_price, 4),
            'basis': round(basis, 4),
            'basis_pct': round(basis_pct, 4),
            'regime': regime
        }

    def get_all_futures_data(self, symbol: str = 'BTC/USDT', timeframe: str = '1h',
                             limit: int = 150, spot_price: float = 0.0) -> Dict[str, Any]:
        """
        Single call to fetch all derivatives market data needed for analysis.
        """
        ticker = self.get_futures_ticker(symbol)
        ohlcv = self.get_ohlcv(symbol, timeframe, limit)
        funding_history = self.get_funding_rate_history(symbol, limit=48)
        oi_history = self.get_open_interest_history(symbol, timeframe, limit=50)
        ls_ratio = self.get_long_short_ratio(symbol, timeframe)

        futures_price = ticker['last'] if ticker else 0.0
        current_funding = ticker['funding_rate'] if ticker else 0.0
        current_oi = ticker['open_interest'] if ticker else 0.0

        basis = self.compute_basis(spot_price if spot_price > 0 else futures_price, futures_price)

        return {
            'ticker': ticker,
            'ohlcv': ohlcv,
            'funding_history': funding_history,
            'oi_history': oi_history,
            'long_short_ratio': ls_ratio,
            'basis': basis,
            'current_funding_rate': current_funding,
            'current_funding_rate_pct': current_funding * 100.0,
            'current_oi': current_oi,
            'mark_price': ticker['mark_price'] if ticker else futures_price,
            'index_price': ticker['index_price'] if ticker else futures_price,
        }
