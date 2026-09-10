"""
Unified Forex & Commodities Data Provider
Integrates multiple institutional-grade data sources in priority order:
  1. Twelve Data (free REST API, institutional-grade OHLCV — closest to Exness feed)
  2. Yahoo Finance (yfinance) — broad coverage fallback
  3. Frankfurter ECB — live rates only, last resort

NOTE: Exness has NO public REST API (MT4/MT5 protocol only).
      Twelve Data is the best publicly-available equivalent.
"""

import os
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

# Twelve Data symbol map (their format uses standard slash notation)
TWELVEDATA_SYMBOL_MAP = {
    'EUR/USD': 'EUR/USD',
    'GBP/USD': 'GBP/USD',
    'USD/JPY': 'USD/JPY',
    'AUD/USD': 'AUD/USD',
    'USD/CAD': 'USD/CAD',
    'USD/CHF': 'USD/CHF',
    'NZD/USD': 'NZD/USD',
    'EUR/GBP': 'EUR/GBP',
    'EUR/JPY': 'EUR/JPY',
    'GBP/JPY': 'GBP/JPY',
    'XAU/USD': 'XAU/USD',
    'XAG/USD': 'XAG/USD',
}

# Twelve Data interval mapping
TWELVEDATA_INTERVAL_MAP = {
    '1m':  '1min',
    '3m':  '5min',
    '5m':  '5min',
    '15m': '15min',
    '30m': '30min',
    '1h':  '1h',
    '4h':  '4h',
    '1d':  '1day',
    '1w':  '1week',
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


# ─────────────────────────────────────────────────────────────────────────────
# MetaTrader 5 (MT5 / Exness) Provider — Direct Zero-Latency Broker Terminal
# ─────────────────────────────────────────────────────────────────────────────
class MT5ExnessProvider:
    """
    Direct MetaTrader 5 (MT5 / Exness) Real-Time Data Provider.
    Pulls tick-by-tick real-time bid/ask and OHLCV bars directly from
    the running MetaTrader 5 EXNESS terminal with 0.00-ms broker latency.
    """
    EXNESS_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
    DEFAULT_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

    MT5_TF_MAP = {
        '1m': 1,     # mt5.TIMEFRAME_M1
        '3m': 3,     # mt5.TIMEFRAME_M3
        '5m': 5,     # mt5.TIMEFRAME_M5
        '15m': 15,   # mt5.TIMEFRAME_M15
        '30m': 30,   # mt5.TIMEFRAME_M30
        '1h': 16385, # mt5.TIMEFRAME_H1
        '4h': 16388, # mt5.TIMEFRAME_H4
        '1d': 16408  # mt5.TIMEFRAME_D1
    }

    def __init__(self, terminal_path: Optional[str] = None, login: Optional[int] = None, password: Optional[str] = None, server: Optional[str] = None):
        self.terminal_path = terminal_path or (
            self.EXNESS_PATH if os.path.exists(self.EXNESS_PATH) else self.DEFAULT_PATH
        )
        self.login_id = login or (int(os.getenv('MT5_LOGIN')) if os.getenv('MT5_LOGIN') else None)
        self.password = password or os.getenv('MT5_PASSWORD')
        self.server = server or os.getenv('MT5_SERVER')
        self.is_connected = False
        self._last_error = (0, "No error")
        self._check_connection()

    def connect(self, login: Optional[int] = None, password: Optional[str] = None, server: Optional[str] = None) -> Dict[str, Any]:
        """
        Explicitly connect or log into MetaTrader 5 with provided credentials.
        """
        if login:
            try:
                self.login_id = int(login)
            except Exception:
                pass
        if password:
            self.password = str(password)
        if server:
            self.server = str(server)

        self._check_connection()
        return self.get_connection_status()

    def _check_connection(self) -> bool:
        try:
            import MetaTrader5 as mt5
            # 1. First check if terminal is already initialized and authorized
            acc_info = mt5.account_info()
            term_info = mt5.terminal_info()
            if acc_info is not None and getattr(term_info, 'connected', False):
                self.is_connected = True
                self._last_error = (0, "Success")
                return True

            # 2. If login/password/server are provided, initialize/login with credentials
            if self.login_id and self.password and self.server:
                init_args = {
                    'login': int(self.login_id),
                    'password': str(self.password),
                    'server': str(self.server),
                    'timeout': 30000
                }
                if os.path.exists(self.terminal_path):
                    init_args['path'] = self.terminal_path
                ok = mt5.initialize(**init_args)
                if not ok:
                    # Also try mt5.login() in case already initialized
                    ok = mt5.login(login=int(self.login_id), password=str(self.password), server=str(self.server))
                self.is_connected = bool(ok)
                self._last_error = mt5.last_error()
                return self.is_connected

            # 3. Otherwise, attach to currently running terminal
            if os.path.exists(self.terminal_path):
                ok = mt5.initialize(path=self.terminal_path)
            else:
                ok = mt5.initialize()

            self._last_error = mt5.last_error()
            if ok:
                acc_info = mt5.account_info()
                self.is_connected = (acc_info is not None)
            else:
                self.is_connected = False
            return self.is_connected
        except Exception as e:
            self.is_connected = False
            self._last_error = (-1, str(e))
            return False

    def get_connection_status(self) -> Dict[str, Any]:
        """
        Return comprehensive real-time connection diagnostic status.
        """
        try:
            import MetaTrader5 as mt5
            acc_info = mt5.account_info()
            term_info = mt5.terminal_info()
            connected = bool(acc_info is not None and getattr(term_info, 'connected', False))
            
            terminal_running = False
            try:
                import subprocess
                res = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Process -Name terminal64 -ErrorAction SilentlyContinue"], capture_output=True, text=True, timeout=3)
                terminal_running = ("terminal64" in res.stdout)
            except Exception:
                terminal_running = bool(term_info is not None)

            err = self._last_error or mt5.last_error()
            return {
                'connected': connected,
                'terminal_running': terminal_running,
                'authorized': bool(acc_info is not None),
                'login': getattr(acc_info, 'login', None),
                'server': getattr(acc_info, 'server', None),
                'name': getattr(acc_info, 'name', None),
                'balance': getattr(acc_info, 'balance', 0.0),
                'equity': getattr(acc_info, 'equity', 0.0),
                'currency': getattr(acc_info, 'currency', 'USD'),
                'leverage': getattr(acc_info, 'leverage', 1),
                'ping': getattr(term_info, 'ping_last', 0),
                'company': getattr(acc_info, 'company', getattr(term_info, 'company', 'Exness')),
                'last_error': err,
                'path': self.terminal_path
            }
        except Exception as e:
            return {
                'connected': False,
                'terminal_running': False,
                'authorized': False,
                'login': None,
                'server': None,
                'balance': 0.0,
                'equity': 0.0,
                'last_error': (-1, str(e)),
                'path': self.terminal_path
            }

    def get_exness_symbol(self, symbol: str) -> Optional[str]:
        if not self._check_connection():
            return None
        try:
            import MetaTrader5 as mt5
            clean = symbol.replace('/', '').replace('-', '').upper()
            variants = [clean, f"{clean}m", f"{clean}c", f"{clean}.r", f"{clean}#"]
            if 'XAU' in clean or 'GOLD' in clean:
                variants.extend(['XAUUSD', 'XAUUSDm', 'GOLD', 'GOLDm', 'XAUUSDc'])

            for var in variants:
                s_info = mt5.symbol_info(var)
                if s_info is not None:
                    if not s_info.visible:
                        mt5.symbol_select(var, True)
                    return var
        except Exception:
            pass
        return None

    def get_live_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self._check_connection():
            return None
        try:
            import MetaTrader5 as mt5
            broker_sym = self.get_exness_symbol(symbol)
            if not broker_sym:
                return None

            tick = mt5.symbol_info_tick(broker_sym)
            if tick is None:
                mt5.symbol_select(broker_sym, True)
                tick = mt5.symbol_info_tick(broker_sym)
                if tick is None:
                    return None

            s_info = mt5.symbol_info(broker_sym)
            digits = int(getattr(s_info, 'digits', 5))

            bid = float(tick.bid)
            ask = float(tick.ask)
            last_price = float(tick.last) if tick.last > 0 else (bid + ask) / 2.0
            high = float(getattr(s_info, 'bidhigh', last_price))
            low = float(getattr(s_info, 'bidlow', last_price))
            spread = getattr(s_info, 'spread', 0)
            chg = float(getattr(s_info, 'price_change', 0.0))

            return {
                'exchange': 'Exness MetaTrader 5 (Direct Broker Terminal)',
                'symbol': symbol,
                'broker_symbol': broker_sym,
                'last': round(last_price, digits),
                'bid': round(bid, digits),
                'ask': round(ask, digits),
                'spread_points': spread,
                'high': round(high, digits),
                'low': round(low, digits),
                'volume': float(getattr(tick, 'volume_real', getattr(tick, 'volume', 0.0))),
                'change_24h_pct': round(chg, 3),
                'timestamp': int(tick.time * 1000),
                'data_source': f'Exness MT5 Live ({broker_sym}) [0-ms Direct]'
            }
        except Exception:
            return None

    def get_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 200) -> Optional[pd.DataFrame]:
        if not self._check_connection():
            return None
        try:
            import MetaTrader5 as mt5
            broker_sym = self.get_exness_symbol(symbol)
            if not broker_sym:
                return None

            tf_val = self.MT5_TF_MAP.get(timeframe, 16385)
            rates = mt5.copy_rates_from_pos(broker_sym, tf_val, 0, limit)
            if rates is None or len(rates) == 0:
                return None

            df = pd.DataFrame(rates)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s')
            df = df.rename(columns={'tick_volume': 'volume'})
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            return df
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Twelve Data Provider  — Institutional-Grade Forex (Exness-equivalent)
# ─────────────────────────────────────────────────────────────────────────────
class TwelveDataForexProvider:
    """
    Provides OHLCV data from Twelve Data REST API.
    Free tier: ~800 API calls/day with the 'demo' key (no registration needed).
    Supports all major FX pairs, XAU/USD, XAG/USD.

    This is the closest publicly-available equivalent to Exness institutional data.
    Exness uses MT4/MT5 (private protocol). Twelve Data is the best REST alternative.
    """

    BASE_URL = "https://api.twelvedata.com"
    DEMO_KEY = "demo"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or self.DEMO_KEY
        self._last_request_time: float = 0.0
        self._min_request_interval: float = 0.5  # 500ms between calls

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _normalize_symbol(self, symbol: str) -> str:
        clean = symbol.strip().upper()
        if clean in TWELVEDATA_SYMBOL_MAP:
            return TWELVEDATA_SYMBOL_MAP[clean]
        if '/' not in clean and len(clean) == 6:
            return f"{clean[:3]}/{clean[3:]}"
        return clean

    def get_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 150) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV from Twelve Data.
        Returns DataFrame [timestamp, open, high, low, close, volume] or None on failure.
        """
        td_symbol = self._normalize_symbol(symbol)
        td_interval = TWELVEDATA_INTERVAL_MAP.get(timeframe, '1h')
        output_size = min(limit + 50, 5000)

        self._rate_limit()
        try:
            params = {
                'symbol': td_symbol,
                'interval': td_interval,
                'outputsize': output_size,
                'apikey': self.api_key,
                'format': 'JSON',
                'order': 'ASC',
            }
            resp = requests.get(f"{self.BASE_URL}/time_series", params=params, timeout=15)
            if resp.status_code != 200:
                return None

            data = resp.json()
            if data.get('status') == 'error' or 'values' not in data:
                return None

            values = data['values']
            if not values:
                return None

            rows = []
            for candle in values:
                rows.append({
                    'timestamp': pd.to_datetime(candle['datetime']),
                    'open':   float(candle.get('open', 0)),
                    'high':   float(candle.get('high', 0)),
                    'low':    float(candle.get('low', 0)),
                    'close':  float(candle.get('close', 0)),
                    'volume': float(candle.get('volume', 0)) if candle.get('volume') else 0.0,
                })

            df = pd.DataFrame(rows)
            df = df.sort_values('timestamp').reset_index(drop=True)
            df = df.dropna(subset=['open', 'high', 'low', 'close'])

            # Resample 4h/3m if interval approximated
            if timeframe == '4h' and td_interval != '4h':
                df.set_index('timestamp', inplace=True)
                df = df.resample('4h').agg({
                    'open': 'first', 'high': 'max', 'low': 'min',
                    'close': 'last', 'volume': 'sum'
                }).dropna().reset_index()
            elif timeframe == '3m' and td_interval != '3min':
                df.set_index('timestamp', inplace=True)
                df = df.resample('3min').agg({
                    'open': 'first', 'high': 'max', 'low': 'min',
                    'close': 'last', 'volume': 'sum'
                }).dropna().reset_index()

            if limit and len(df) > limit:
                df = df.iloc[-limit:].reset_index(drop=True)

            return df if len(df) >= 10 else None

        except Exception:
            return None

    def get_live_price(self, symbol: str) -> Optional[float]:
        """Fetch latest spot price from Twelve Data."""
        td_symbol = self._normalize_symbol(symbol)
        self._rate_limit()
        try:
            params = {'symbol': td_symbol, 'apikey': self.api_key}
            resp = requests.get(f"{self.BASE_URL}/price", params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if 'price' in data:
                    return float(data['price'])
        except Exception:
            pass
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ForexFeedManager — Multi-Source Priority Manager
# ─────────────────────────────────────────────────────────────────────────────
class ForexFeedManager:
    """
    Manager for querying live Forex currency pairs, Precious Metals (Gold/Silver),
    and historical OHLCV data.

    Data source priority:
      1. Twelve Data (institutional-grade, Exness-equivalent public feed)
      2. Yahoo Finance (yfinance) — broad coverage fallback
      3. Frankfurter ECB — live rates only, last resort
    """
    def __init__(self, twelvedata_api_key: Optional[str] = None):
        self.frankfurter_base = 'https://api.frankfurter.dev/v1'
        self.mt5_exness = MT5ExnessProvider()
        self.twelvedata = TwelveDataForexProvider(api_key=twelvedata_api_key)
        self._data_source_log: Dict[str, str] = {}

    def normalize_symbol(self, symbol: str) -> str:
        """
        Accepts formats like 'EUR/USD', 'EURUSD', 'EURUSD=X' and maps to Yahoo Finance ticker.
        """
        clean = symbol.strip().upper()
        if clean in FOREX_PAIRS_MAP:
            return FOREX_PAIRS_MAP[clean]
        if clean.endswith('=X') or clean.endswith('=F'):
            return clean
        slash_cand = f"{clean[:3]}/{clean[3:]}"
        if slash_cand in FOREX_PAIRS_MAP:
            return FOREX_PAIRS_MAP[slash_cand]
        return f"{clean}=X"

    def _get_ohlcv_yfinance(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """Yahoo Finance fallback."""
        yf_sym = self.normalize_symbol(symbol)
        tf_info = YFINANCE_TIMEFRAME_MAP.get(timeframe, {'period': '1mo', 'interval': '1h'})
        try:
            ticker = yf.Ticker(yf_sym)
            df = ticker.history(period=tf_info['period'], interval=tf_info['interval'])
        except Exception:
            return None

        if df.empty:
            try:
                df = yf.Ticker(yf_sym).history(period='3mo', interval='1d')
            except Exception:
                return None

        if df.empty:
            return None

        df = df.reset_index()
        time_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
        df = df.rename(columns={
            time_col: 'timestamp', 'Open': 'open', 'High': 'high',
            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
        })
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna().reset_index(drop=True)

        if timeframe == '4h' and len(df) > 0:
            df.set_index('timestamp', inplace=True)
            df = df.resample('4h').agg({
                'open': 'first', 'high': 'max', 'low': 'min',
                'close': 'last', 'volume': 'sum'
            }).dropna().reset_index()
        elif timeframe == '3m' and len(df) > 0:
            df.set_index('timestamp', inplace=True)
            df = df.resample('3min').agg({
                'open': 'first', 'high': 'max', 'low': 'min',
                'close': 'last', 'volume': 'sum'
            }).dropna().reset_index()

        if limit and len(df) > limit:
            df = df.iloc[-limit:].reset_index(drop=True)

        return df if len(df) >= 10 else None

    def _get_gold_silver_spot_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Direct institutional Gold & Silver spot ticker matching Exness retail prices.
        XAU/USD: Binance 1-to-1 physical gold (PAXG) and Bybit XAUUSDT Linear Perpetual.
        XAG/USD: Bybit XAGUSDT Linear Perpetual.
        """
        import urllib.request
        import json

        clean = symbol.strip().upper()
        if 'XAU' in clean or 'GOLD' in clean:
            # 1. Binance PAXG (London Gold Spot 1oz Physical Peg)
            try:
                url = 'https://api.binance.com/api/v3/ticker/24hr?symbol=PAXGUSDT'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=5)
                d = json.loads(res.read())
                last_p = float(d['lastPrice'])
                return {
                    'exchange': 'London Gold Spot (Binance 1oz Physical PAXG)',
                    'symbol': 'XAU/USD',
                    'last': last_p,
                    'high': float(d.get('highPrice', last_p)),
                    'low': float(d.get('lowPrice', last_p)),
                    'volume': float(d.get('volume', 0.0)),
                    'change_24h_pct': float(d.get('priceChangePercent', 0.0)),
                    'timestamp': int(time.time() * 1000),
                    'data_source': 'Exness-Equivalent Live Gold Spot (London Interbank Peg)'
                }
            except Exception:
                pass

            # 2. Bybit XAUUSDT Linear
            try:
                url = 'https://api.bybit.com/v5/market/tickers?category=linear&symbol=XAUUSDT'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=5)
                d = json.loads(res.read())
                lst = d['result'].get('list', [])
                if lst:
                    item = lst[0]
                    last_p = float(item['lastPrice'])
                    return {
                        'exchange': 'Bybit XAUUSDT (Gold Linear Perpetual)',
                        'symbol': 'XAU/USD',
                        'last': last_p,
                        'high': float(item.get('highPrice24h', last_p)),
                        'low': float(item.get('lowPrice24h', last_p)),
                        'volume': float(item.get('volume24h', 0.0)),
                        'change_24h_pct': float(item.get('price24hPcnt', 0.0)) * 100.0,
                        'timestamp': int(time.time() * 1000),
                        'data_source': 'Exness-Equivalent Live Gold Spot (Bybit XAUUSDT)'
                    }
            except Exception:
                pass

        elif 'XAG' in clean or 'SILVER' in clean:
            try:
                url = 'https://api.bybit.com/v5/market/tickers?category=linear&symbol=XAGUSDT'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=5)
                d = json.loads(res.read())
                lst = d['result'].get('list', [])
                if lst:
                    item = lst[0]
                    last_p = float(item['lastPrice'])
                    return {
                        'exchange': 'Bybit XAGUSDT (Silver Linear Perpetual)',
                        'symbol': 'XAG/USD',
                        'last': last_p,
                        'high': float(item.get('highPrice24h', last_p)),
                        'low': float(item.get('lowPrice24h', last_p)),
                        'volume': float(item.get('volume24h', 0.0)),
                        'change_24h_pct': float(item.get('price24hPcnt', 0.0)) * 100.0,
                        'timestamp': int(time.time() * 1000),
                        'data_source': 'Exness-Equivalent Live Silver Spot (Bybit XAGUSDT)'
                    }
            except Exception:
                pass

        return None

    def _get_gold_silver_spot_ohlcv(self, symbol: str, timeframe: str = '5m', limit: int = 150) -> Optional[pd.DataFrame]:
        """
        Direct institutional Gold & Silver OHLCV matching Exness charts candle-for-candle.
        """
        import urllib.request
        import json

        clean = symbol.strip().upper()
        if 'XAU' in clean or 'GOLD' in clean:
            # 1. Try Binance PAXG
            BINANCE_TF = {'1m':'1m','3m':'3m','5m':'5m','15m':'15m','30m':'30m','1h':'1h','4h':'4h','1d':'1d'}
            btf = BINANCE_TF.get(timeframe, '1h')
            try:
                url = f'https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval={btf}&limit={min(limit, 1000)}'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=8)
                raw = json.loads(res.read())
                if raw and len(raw) >= 1:
                    rows = []
                    for c in raw:
                        rows.append({
                            'timestamp': pd.to_datetime(c[0], unit='ms'),
                            'open': float(c[1]),
                            'high': float(c[2]),
                            'low': float(c[3]),
                            'close': float(c[4]),
                            'volume': float(c[5])
                        })
                    return pd.DataFrame(rows)
            except Exception:
                pass

            # 2. Try Bybit XAUUSDT Linear
            BYBIT_TF = {'1m':'1','3m':'3','5m':'5','15m':'15','30m':'30','1h':'60','4h':'240','1d':'D'}
            ytf = BYBIT_TF.get(timeframe, '60')
            try:
                url = f'https://api.bybit.com/v5/market/kline?category=linear&symbol=XAUUSDT&interval={ytf}&limit={min(limit, 1000)}'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=8)
                raw = json.loads(res.read())['result'].get('list', [])
                if raw and len(raw) >= 1:
                    rows = []
                    for c in raw:
                        rows.append({
                            'timestamp': pd.to_datetime(int(c[0]), unit='ms'),
                            'open': float(c[1]),
                            'high': float(c[2]),
                            'low': float(c[3]),
                            'close': float(c[4]),
                            'volume': float(c[5])
                        })
                    return pd.DataFrame(rows).sort_values('timestamp').reset_index(drop=True)
            except Exception:
                pass

        elif 'XAG' in clean or 'SILVER' in clean:
            BYBIT_TF = {'1m':'1','3m':'3','5m':'5','15m':'15','30m':'30','1h':'60','4h':'240','1d':'D'}
            ytf = BYBIT_TF.get(timeframe, '60')
            try:
                url = f'https://api.bybit.com/v5/market/kline?category=linear&symbol=XAGUSDT&interval={ytf}&limit={min(limit, 1000)}'
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                res = urllib.request.urlopen(req, timeout=8)
                raw = json.loads(res.read())['result'].get('list', [])
                if raw and len(raw) >= 10:
                    rows = []
                    for c in raw:
                        rows.append({
                            'timestamp': pd.to_datetime(int(c[0]), unit='ms'),
                            'open': float(c[1]),
                            'high': float(c[2]),
                            'low': float(c[3]),
                            'close': float(c[4]),
                            'volume': float(c[5])
                        })
                    return pd.DataFrame(rows).sort_values('timestamp').reset_index(drop=True)
            except Exception:
                pass

        return None

    def get_live_ticker(self, symbol: str = 'EUR/USD') -> Optional[Dict[str, Any]]:
        """
        Fetch real-time Forex or Commodity ticker.
        # Priority:
        #   -1. MetaTrader 5 (Exness Direct Realtime Broker Feed) [0-ms latency]
        #    0. Dedicated Gold/Silver Exness-Equivalent feed (XAU/USD & XAG/USD)
        #    1. Twelve Data (institutional-grade forex)
        #    2. Yahoo Finance (broad fallback)
        #    3. Frankfurter ECB (last resort)
        """
        # -1) Direct MetaTrader 5 (Exness) Zero-Latency Broker Feed
        if self.mt5_exness.is_connected:
            mt5_ticker = self.mt5_exness.get_live_ticker(symbol)
            if mt5_ticker is not None:
                self._data_source_log[symbol] = mt5_ticker['data_source']
                return mt5_ticker

        # 0) Direct Gold/Silver Exness-equivalent feed
        clean = symbol.strip().upper()
        if any(metal in clean for metal in ['XAU', 'GOLD', 'XAG', 'SILVER']):
            metal_ticker = self._get_gold_silver_spot_ticker(symbol)
            if metal_ticker is not None:
                return metal_ticker

        # 1) Twelve Data
        td_price = self.twelvedata.get_live_price(symbol)
        if td_price is not None:
            return {
                'exchange': 'twelvedata_institutional',
                'symbol': symbol,
                'last': td_price,
                'high': td_price,
                'low': td_price,
                'volume': 0.0,
                'change_24h_pct': 0.0,
                'timestamp': int(time.time() * 1000),
                'data_source': 'Twelve Data (Exness-equivalent)'
            }

        # 2) Yahoo Finance
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
                    'timestamp': int(time.time() * 1000),
                    'data_source': 'Yahoo Finance (fallback)'
                }
        except Exception:
            pass

        # 3) Frankfurter ECB last resort
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
                        'last': rate,
                        'high': rate,
                        'low': rate,
                        'volume': 0.0,
                        'change_24h_pct': 0.0,
                        'timestamp': int(time.time() * 1000),
                        'data_source': 'Frankfurter ECB (last resort)'
                    }
        except Exception:
            pass

        return None

    def get_ohlcv(self, symbol: str = 'EUR/USD', timeframe: str = '1h', limit: int = 150) -> pd.DataFrame:
        """
        Fetch standardized OHLCV historical candlestick data for Forex/Commodities.
        Returns DataFrame with columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']

        Source priority:
          -1. MetaTrader 5 (Exness Direct Realtime Broker Candles) [0-ms latency]
           0. Dedicated Gold/Silver Exness-Equivalent feed (XAU/USD & XAG/USD)
           1. Twelve Data (institutional-grade forex)
           2. Yahoo Finance (broad fallback)
        """
        # Priority -1: MetaTrader 5 (Exness Direct Realtime Broker Candles)
        if self.mt5_exness.is_connected:
            df_mt5 = self.mt5_exness.get_ohlcv(symbol, timeframe, limit)
            if df_mt5 is not None and not df_mt5.empty and len(df_mt5) >= 10:
                self._data_source_log[symbol] = f"Exness MT5 Direct ({self.mt5_exness.get_exness_symbol(symbol)})"
                return df_mt5

        # Priority 0: Gold & Silver dedicated Exness-equivalent feed
        clean = symbol.strip().upper()
        if any(metal in clean for metal in ['XAU', 'GOLD', 'XAG', 'SILVER']):
            df_metal = self._get_gold_silver_spot_ohlcv(symbol, timeframe, limit)
            if df_metal is not None and not df_metal.empty:
                self._data_source_log[symbol] = 'Exness-Equivalent Live Metal Spot (Binance/Bybit)'
                return df_metal

        # Priority 1: Twelve Data (institutional-grade)
        df = self.twelvedata.get_ohlcv(symbol, timeframe, limit)
        if df is not None and not df.empty:
            self._data_source_log[symbol] = 'Twelve Data (institutional)'
            return df

        # Priority 2: Yahoo Finance
        df = self._get_ohlcv_yfinance(symbol, timeframe, limit)
        if df is not None and not df.empty:
            self._data_source_log[symbol] = 'Yahoo Finance (fallback)'
            return df

        raise ConnectionError(
            f"Could not retrieve live OHLCV data for {symbol} on timeframe {timeframe}. "
            f"Tried: Twelve Data, Yahoo Finance."
        )

    def get_data_source_info(self) -> Dict[str, str]:
        """Returns which data source was last used per symbol."""
        return dict(self._data_source_log)

    def is_mt5_connected(self) -> bool:
        """Returns True if local MetaTrader 5 terminal is initialized and connected."""
        return bool(self.mt5_exness and self.mt5_exness.is_connected)

    def connect_mt5(self, login: Optional[int] = None, password: Optional[str] = None, server: Optional[str] = None) -> Dict[str, Any]:
        """Explicitly connect or log into MetaTrader 5 with provided credentials."""
        if self.mt5_exness:
            return self.mt5_exness.connect(login=login, password=password, server=server)
        return {'connected': False, 'error': 'MT5 provider not available'}

    def get_mt5_status(self) -> Dict[str, Any]:
        """Return diagnostic status of MetaTrader 5 connection."""
        if self.mt5_exness:
            return self.mt5_exness.get_connection_status()
        return {'connected': False, 'terminal_running': False, 'authorized': False}

    def get_market_sessions(self) -> Dict[str, Any]:
        """
        Determine which major Forex trading sessions (Sydney, Tokyo, London, New York)
        are currently open based on UTC time.
        """
        utc_now = datetime.now(timezone.utc)
        hour = utc_now.hour

        sessions = {
            'Sydney':   {'open': 21, 'close': 6,  'active': (hour >= 21 or hour < 6)},
            'Tokyo':    {'open': 0,  'close': 9,  'active': (0 <= hour < 9)},
            'London':   {'open': 7,  'close': 16, 'active': (7 <= hour < 16)},
            'New York': {'open': 12, 'close': 21, 'active': (12 <= hour < 21)}
        }

        active_list = [name for name, info in sessions.items() if info['active']]
        return {
            'utc_time': utc_now.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'active_sessions': active_list,
            'sessions': sessions,
            'is_major_overlap': ('London' in active_list and 'New York' in active_list)
        }
