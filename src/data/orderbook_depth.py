"""
Order Book Depth and Liquidity Pressure Analyzer
Fetches real orderbook data from public exchange APIs and calculates
order flow pressure, bid/ask depth imbalance, spread, and liquidity distribution.
"""

import requests
import ccxt
from typing import Dict, Any, Optional

BINANCE_DEPTH_ENDPOINTS = [
    'https://api.binance.com',
    'https://api1.binance.com',
    'https://api2.binance.com'
]

class OrderBookAnalyzer:
    """
    Analyzes live order books to measure institutional buying vs selling pressure.
    """
    def __init__(self):
        self.bybit = None
        try:
            self.bybit = ccxt.bybit({'enableRateLimit': True, 'timeout': 5000})
        except Exception:
            pass

    def fetch_binance_depth(self, symbol: str = 'BTC/USDT', limit: int = 20) -> Optional[Dict[str, Any]]:
        clean_symbol = symbol.replace('/', '').replace('-', '').upper()
        for base_url in BINANCE_DEPTH_ENDPOINTS:
            try:
                url = f"{base_url}/api/v3/depth?symbol={clean_symbol}&limit={limit}"
                resp = requests.get(url, timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    bids = [[float(p), float(q)] for p, q in data['bids']]
                    asks = [[float(p), float(q)] for p, q in data['asks']]
                    return {'bids': bids, 'asks': asks, 'exchange': 'binance'}
            except Exception:
                continue
        return None

    def fetch_bybit_depth(self, symbol: str = 'BTC/USDT', limit: int = 20) -> Optional[Dict[str, Any]]:
        if not self.bybit:
            return None
        try:
            book = self.bybit.fetch_order_book(symbol, limit=limit)
            return {
                'bids': [[float(p), float(q)] for p, q in book['bids'][:limit]],
                'asks': [[float(p), float(q)] for p, q in book['asks'][:limit]],
                'exchange': 'bybit'
            }
        except Exception:
            return None

    def get_order_book_metrics(self, symbol: str = 'BTC/USDT', exchange: str = 'binance', limit: int = 20) -> Dict[str, Any]:
        """
        Calculates depth imbalance, spread, and buyer/seller pressure.
        """
        raw_book = None
        if exchange.lower() == 'binance':
            raw_book = self.fetch_binance_depth(symbol, limit)
            if not raw_book:
                raw_book = self.fetch_bybit_depth(symbol, limit)
        else:
            raw_book = self.fetch_bybit_depth(symbol, limit)
            if not raw_book:
                raw_book = self.fetch_binance_depth(symbol, limit)

        if not raw_book or not raw_book['bids'] or not raw_book['asks']:
            return {
                'available': False,
                'exchange': exchange,
                'imbalance_ratio': 0.0,
                'spread': 0.0,
                'spread_pct': 0.0,
                'best_bid': 0.0,
                'best_ask': 0.0,
                'total_bid_depth': 0.0,
                'total_ask_depth': 0.0,
                'pressure_bias': 'NEUTRAL'
            }

        bids = raw_book['bids']
        asks = raw_book['asks']

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        spread = max(0.0, best_ask - best_bid)
        spread_pct = (spread / best_bid * 100.0) if best_bid > 0 else 0.0

        total_bid_vol = sum(q for p, q in bids)
        total_ask_vol = sum(q for p, q in asks)
        total_vol = total_bid_vol + total_ask_vol

        # Imbalance ratio ranges from -1.0 (100% sell depth) to +1.0 (100% buy depth)
        imbalance = ((total_bid_vol - total_ask_vol) / total_vol) if total_vol > 0 else 0.0

        if imbalance > 0.18:
            pressure = 'BULLISH_BUY_PRESSURE'
        elif imbalance < -0.18:
            pressure = 'BEARISH_SELL_PRESSURE'
        else:
            pressure = 'BALANCED'

        return {
            'available': True,
            'exchange': raw_book['exchange'],
            'best_bid': best_bid,
            'best_ask': best_ask,
            'spread': spread,
            'spread_pct': spread_pct,
            'total_bid_depth': total_bid_vol,
            'total_ask_depth': total_ask_vol,
            'imbalance_ratio': imbalance,
            'imbalance_pct': imbalance * 100.0,
            'pressure_bias': pressure,
            'top_bids': bids[:5],
            'top_asks': asks[:5]
        }
