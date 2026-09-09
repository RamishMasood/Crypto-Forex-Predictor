"""
Unified Forex & Commodities Data Provider
Integrates Yahoo Finance and Frankfurter ECB Open API for real-time FX rates,
commodities (Gold/Silver), and historical OHLCV candlestick data.
Requires zero private API keys.
"""

import time
import requests
import pandas as pd
import yfinance as yf
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

FOREX_PAIRS_MAP = {
    'EUR/USD': 'EURUSD=X',
    'GBP/USD': 'GBPUSD=X',
    'USD/JPY': 'USDJPY=X',
    'AUD/USD': 'AUDUSD=X',
    'USD/CAD': 'CAD=X',
    'USD/CHF': 'CHF=X',
    'NZD/USD': 'NZDUSD=X',
    'EUR/GBP': 'EURGBP=X',
    'EUR/JPY': 'EURJPY=X',
    'GBP/JPY': 'GBPJPY=X',
    'XAU/USD': 'GC=F',     # Gold Futures / Spot Proxy
    'XAG/USD': 'SI=F',     # Silver Futures / Spot Proxy
    'WTI/USD': 'CL=F'      # Crude Oil
}

# Reverse mapping for standard symbol inputs
REVERSE_MAP = {v: k for k, v in FOREX_PAIRS_MAP.items()}

YFINANCE_TIMEFRAME_MAP = {
    '1m': {'period': '5d', 'interval': '1m'},
    '3m': {'period': '5d', 'interval': '1m'}, # resample to 3m
    '5m': {'period': '1mo', 'interval': '5m'},
    '15m': {'period': '1mo', 'interval': '15m'},
    '30m': {'period': '1mo', 'interval': '30m'},
    '1h': {'period': '2y', 'interval': '1h'},
    '4h': {'period': '2y', 'interval': '1h'}, # can resample to 4h
    '1d': {'period': '2y', 'interval': '1d'}
}

class ForexFeedManager:
    """
    Manager for querying live Forex currency pairs, Precious Metals (Gold/Silver),
    and historical OHLCV data.
    """
    def __init__(self):
        self.frankfurter_base = 'https://api.frankfurter.dev/v1'

    def normalize_symbol(self, symbol: str) -> str:
        """
        Accepts formats like 'EUR/USD', 'EURUSD', 'EURUSD=X' and maps to Yahoo Finance ticker.
        """
        clean = symbol.strip().upper()
        if clean in FOREX_PAIRS_MAP:
            return FOREX_PAIRS_MAP[clean]
        
        # Check if already in Yahoo format
        if clean.endswith('=X') or clean.endswith('=F'):
            return clean
        
        # Check without slash: 'EURUSD' -> 'EURUSD=X'
        slash_cand = f"{clean[:3]}/{clean[3:]}"
        if slash_cand in FOREX_PAIRS_MAP:
            return FOREX_PAIRS_MAP[slash_cand]
        
        return f"{clean}=X"

    def get_live_ticker(self, symbol: str = 'EUR/USD') -> Optional[Dict[str, Any]]:
        """
        Fetch real-time Forex or Commodity ticker via Yahoo Finance.
        """
        yf_sym = self.normalize_symbol(symbol)
        try:
            ticker = yf.Ticker(yf_sym)
            df = ticker.history(period='2d', interval='1h')
            if df.empty:
                df = ticker.history(period='5d', interval='1d')
            
            if not df.empty:
                last_row = df.iloc[-1]
                prev_row = df.iloc[-2] if len(df) > 1 else last_row
                
                last_price = float(last_row['Close'])
                prev_price = float(prev_row['Close'])
                change_pct = ((last_price - prev_price) / prev_price) * 100.0 if prev_price else 0.0
                
                return {
                    'exchange': 'forex_interbank (Yahoo Finance)',
                    'symbol': symbol,
                    'yf_symbol': yf_sym,
                    'last': last_price,
                    'high': float(df['High'].max()),
                    'low': float(df['Low'].min()),
                    'volume': float(last_row.get('Volume', 0.0)),
                    'change_24h_pct': change_pct,
                    'timestamp': int(time.time() * 1000)
                }
        except Exception:
            pass

        # Fallback to Frankfurter API for major currency pairs
        try:
            parts = symbol.replace('=', '').replace('X', '').split('/')
            if len(parts) == 2:
                base, quote = parts[0].strip(), parts[1].strip()
                resp = requests.get(f"{self.frankfurter_base}/latest?from={base}&to={quote}", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    rate = float(data['rates'][quote])
                    return {
                        'exchange': 'ecb_frankfurter',
                        'symbol': symbol,
                        'yf_symbol': yf_sym,
                        'last': rate,
                        'high': rate,
                        'low': rate,
                        'volume': 0.0,
                        'change_24h_pct': 0.0,
                        'timestamp': int(time.time() * 1000)
                    }
        except Exception:
            pass

        return None

    def get_ohlcv(self, symbol: str = 'EUR/USD', timeframe: str = '1h', limit: int = 150) -> pd.DataFrame:
        """
        Fetch standardized OHLCV historical candlestick data for Forex/Commodities.
        Returns DataFrame with columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        """
        yf_sym = self.normalize_symbol(symbol)
        tf_info = YFINANCE_TIMEFRAME_MAP.get(timeframe, {'period': '1mo', 'interval': '1h'})
        
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(period=tf_info['period'], interval=tf_info['interval'])
        
        if df.empty:
            # Fallback to daily
            df = ticker.history(period='3mo', interval='1d')
            
        if df.empty:
            raise ConnectionError(f"Could not retrieve live OHLCV data for {symbol} ({yf_sym}) on timeframe {timeframe}.")

        df = df.reset_index()
        # Rename standard columns
        time_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
        df = df.rename(columns={
            time_col: 'timestamp',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        })
        
        # Keep essential columns and ensure clean datatypes
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df = df.dropna().reset_index(drop=True)
        
        # Resample if 4h or 3m was requested
        if timeframe == '4h' and len(df) > 0:
            df.set_index('timestamp', inplace=True)
            resampled = df.resample('4h').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna().reset_index()
            df = resampled
        elif timeframe == '3m' and len(df) > 0:
            df.set_index('timestamp', inplace=True)
            resampled = df.resample('3min').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna().reset_index()
            df = resampled

        if limit and len(df) > limit:
            df = df.iloc[-limit:].reset_index(drop=True)

        return df

    def get_market_sessions(self) -> Dict[str, Any]:
        """
        Determine which major Forex trading sessions (Sydney, Tokyo, London, New York)
        are currently open based on UTC time.
        """
        utc_now = datetime.now(timezone.utc)
        hour = utc_now.hour

        # Approximate UTC operating hours
        sessions = {
            'Sydney': {'open': 21, 'close': 6, 'active': (hour >= 21 or hour < 6)},
            'Tokyo': {'open': 0, 'close': 9, 'active': (0 <= hour < 9)},
            'London': {'open': 7, 'close': 16, 'active': (7 <= hour < 16)},
            'New York': {'open': 12, 'close': 21, 'active': (12 <= hour < 21)}
        }
        
        active_list = [name for name, info in sessions.items() if info['active']]
        return {
            'utc_time': utc_now.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'active_sessions': active_list,
            'sessions': sessions,
            'is_major_overlap': ('London' in active_list and 'New York' in active_list)
        }
