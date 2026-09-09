"""
High-Performance Quantitative Technical Indicators
Vectorized calculations for EMA Ribbon, SuperTrend, RSI, MACD, Bollinger Bands,
ATR, ADX, and Stochastic RSI.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any

class QuantitativeIndicators:
    """
    Computes professional-grade quantitative technical indicators on standardized OHLCV DataFrames.
    """

    @staticmethod
    def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates and appends all indicators to the OHLCV dataframe.
        """
        df = df.copy()
        
        # 1. EMAs (9, 20, 50, 200)
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=min(200, len(df)), adjust=False).mean()

        # Trend Bias based on EMA Alignment
        df['ema_trend'] = np.where(
            (df['ema_20'] > df['ema_50']) & (df['ema_50'] > df['ema_200']), 1,  # Strong Bullish
            np.where((df['ema_20'] < df['ema_50']) & (df['ema_50'] < df['ema_200']), -1, 0) # Strong Bearish
        )

        # 2. Average True Range (ATR 14)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr_14'] = tr.rolling(window=14, min_periods=1).mean()

        # 3. SuperTrend (Period 10, Multiplier 3.0)
        df = QuantitativeIndicators._calculate_supertrend(df, period=10, multiplier=3.0)

        # 4. Relative Strength Index (RSI 14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0.0)).rolling(window=14, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=1).mean()
        rs = gain / (loss.replace(0, np.nan))
        df['rsi_14'] = 100 - (100 / (1 + rs))
        df['rsi_14'] = df['rsi_14'].fillna(50.0)

        # 5. MACD (12, 26, 9)
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd_line'] = ema_12 - ema_26
        df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd_line'] - df['macd_signal']
        df['macd_hist_slope'] = df['macd_hist'].diff()

        # 6. Bollinger Bands (20, 2.0)
        df['bb_mid'] = df['close'].rolling(window=20, min_periods=1).mean()
        bb_std = df['close'].rolling(window=20, min_periods=1).std().fillna(0)
        df['bb_upper'] = df['bb_mid'] + (bb_std * 2.0)
        df['bb_lower'] = df['bb_mid'] - (bb_std * 2.0)
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid'].replace(0, np.nan)
        df['bb_pct_b'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower']).replace(0, np.nan)

        # 7. Bollinger Band Squeeze (Low bandwidth percentile)
        rolling_min_bw = df['bb_width'].rolling(window=50, min_periods=10).min()
        df['bb_squeeze'] = df['bb_width'] <= (rolling_min_bw * 1.15)

        # 8. ADX (Average Directional Index 14)
        df = QuantitativeIndicators._calculate_adx(df, period=14)

        # 9. Stochastic RSI (14, 14, 3, 3)
        min_rsi = df['rsi_14'].rolling(window=14, min_periods=1).min()
        max_rsi = df['rsi_14'].rolling(window=14, min_periods=1).max()
        stoch_raw = (df['rsi_14'] - min_rsi) / (max_rsi - min_rsi).replace(0, np.nan)
        df['stoch_rsi_k'] = stoch_raw.rolling(window=3, min_periods=1).mean() * 100
        df['stoch_rsi_d'] = df['stoch_rsi_k'].rolling(window=3, min_periods=1).mean()

        # 10. Volume Flow / Volatility metrics
        if 'volume' in df.columns and (df['volume'] > 0).any():
            df['vol_sma_20'] = df['volume'].rolling(window=20, min_periods=1).mean()
            df['vol_surge'] = df['volume'] > (df['vol_sma_20'] * 1.5)
        else:
            df['vol_sma_20'] = 1.0
            df['vol_surge'] = False

        # 11. Institutional Anchored/Rolling VWAP & Standard Deviation Bands
        df = QuantitativeIndicators._calculate_vwap(df)

        # 12. Cumulative Volume Delta (CVD) & Delta Flow
        df = QuantitativeIndicators._calculate_cvd(df)

        # 13. Choppiness Index & Hurst Exponent (AlphaRegime Analysis)
        df = QuantitativeIndicators._calculate_choppiness(df, period=14)
        df = QuantitativeIndicators._calculate_hurst(df, max_lag=20)

        return df

    @staticmethod
    def _calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
        hl2 = (df['high'] + df['low']) / 2.0
        atr = df['atr_14'] if 'atr_14' in df.columns else (df['high'] - df['low']).rolling(period).mean()

        basic_upper = hl2 + (multiplier * atr)
        basic_lower = hl2 - (multiplier * atr)

        n = len(df)
        final_upper = np.zeros(n)
        final_lower = np.zeros(n)
        supertrend = np.zeros(n)
        direction = np.zeros(n) # 1 = Bullish, -1 = Bearish

        close = df['close'].values
        bu = basic_upper.values
        bl = basic_lower.values

        for i in range(1, n):
            # Final Upper Band
            if bu[i] < final_upper[i-1] or close[i-1] > final_upper[i-1]:
                final_upper[i] = bu[i]
            else:
                final_upper[i] = final_upper[i-1]

            # Final Lower Band
            if bl[i] > final_lower[i-1] or close[i-1] < final_lower[i-1]:
                final_lower[i] = bl[i]
            else:
                final_lower[i] = final_lower[i-1]

            # Trend Direction
            if supertrend[i-1] == final_upper[i-1]:
                if close[i] > final_upper[i]:
                    direction[i] = 1
                    supertrend[i] = final_lower[i]
                else:
                    direction[i] = -1
                    supertrend[i] = final_upper[i]
            else:
                if close[i] < final_lower[i]:
                    direction[i] = -1
                    supertrend[i] = final_upper[i]
                else:
                    direction[i] = 1
                    supertrend[i] = final_lower[i]

        df['supertrend'] = supertrend
        df['supertrend_dir'] = direction
        return df

    @staticmethod
    def _calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        up_move = df['high'].diff()
        down_move = -df['low'].diff()

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        tr = df['atr_14'] * 14 if 'atr_14' in df.columns else (df['high'] - df['low'])
        tr_smooth = pd.Series(tr).rolling(window=period, min_periods=1).sum()

        plus_di = 100 * (pd.Series(plus_dm).rolling(window=period, min_periods=1).sum() / tr_smooth.replace(0, np.nan))
        minus_di = 100 * (pd.Series(minus_dm).rolling(window=period, min_periods=1).sum() / tr_smooth.replace(0, np.nan))

        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
        df['adx_14'] = dx.rolling(window=period, min_periods=1).mean().fillna(20.0)
        df['plus_di'] = plus_di.fillna(0.0)
        df['minus_di'] = minus_di.fillna(0.0)
        return df

    @staticmethod
    def _calculate_vwap(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates Institutional Volume-Weighted Average Price (VWAP)
        and +/- 1.0, 2.0 Standard Deviation Bands.
        """
        typical_price = (df['high'] + df['low'] + df['close']) / 3.0
        vol = df['volume'] if 'volume' in df.columns and (df['volume'] > 0).any() else pd.Series(1.0, index=df.index)

        # Cumulative Volume & Price*Volume
        cum_vol = vol.cumsum()
        cum_pv = (typical_price * vol).cumsum()
        vwap = cum_pv / cum_vol.replace(0, np.nan)
        df['vwap'] = vwap.fillna(typical_price)

        # Standard deviation bands
        cum_sq_dev = (vol * (typical_price - df['vwap'])**2).cumsum()
        vwap_variance = cum_sq_dev / cum_vol.replace(0, np.nan)
        vwap_std = np.sqrt(vwap_variance).fillna(0)

        df['vwap_upper_1'] = df['vwap'] + (1.0 * vwap_std)
        df['vwap_upper_2'] = df['vwap'] + (2.0 * vwap_std)
        df['vwap_lower_1'] = df['vwap'] - (1.0 * vwap_std)
        df['vwap_lower_2'] = df['vwap'] - (2.0 * vwap_std)

        # Status: ABOVE_VWAP (Bullish) vs BELOW_VWAP (Bearish)
        df['vwap_bias'] = np.where(df['close'] >= df['vwap'], 'BULLISH', 'BEARISH')
        return df

    @staticmethod
    def _calculate_cvd(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates Cumulative Volume Delta (CVD) and Delta Flow dynamics
        (Institutional buyer vs seller aggression).
        """
        vol = df['volume'] if 'volume' in df.columns and (df['volume'] > 0).any() else pd.Series(1.0, index=df.index)
        hl_range = (df['high'] - df['low']).replace(0, 1e-9)
        cl_loc = (df['close'] - df['low']) / hl_range
        # Delta factor between -1.0 (sellers pushed to low) and +1.0 (buyers pushed to high)
        delta_ratio = 2.0 * cl_loc - 1.0
        bar_delta = vol * delta_ratio

        df['bar_delta'] = bar_delta
        df['cvd'] = bar_delta.cumsum()
        df['cvd_ema_14'] = df['cvd'].ewm(span=14, adjust=False).mean()
        df['cvd_slope'] = df['cvd'].diff(3).fillna(0)

        # CVD divergence detection over rolling 10 bars
        price_low_10 = df['low'].rolling(window=10, min_periods=5).min()
        cvd_low_10 = df['cvd'].rolling(window=10, min_periods=5).min()
        price_high_10 = df['high'].rolling(window=10, min_periods=5).max()
        cvd_high_10 = df['cvd'].rolling(window=10, min_periods=5).max()

        # Bullish divergence: price near 10-bar low but CVD making higher value
        bull_div = (df['low'] <= price_low_10 * 1.002) & (df['cvd'] > cvd_low_10 * 1.05)
        bear_div = (df['high'] >= price_high_10 * 0.998) & (df['cvd'] < cvd_high_10 * 0.95)

        df['cvd_bull_div'] = bull_div
        df['cvd_bear_div'] = bear_div
        return df

    @staticmethod
    def _calculate_choppiness(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        Calculates Choppiness Index (CHOP).
        < 38.2 = Trending Market
        > 61.8 = Choppy / Consolidated Market
        """
        tr = df['atr_14'] if 'atr_14' in df.columns else (df['high'] - df['low'])
        atr_sum = tr.rolling(window=period, min_periods=1).sum()
        high_max = df['high'].rolling(window=period, min_periods=1).max()
        low_min = df['low'].rolling(window=period, min_periods=1).min()
        hl_diff = (high_max - low_min).replace(0, 1e-9)

        ratio = (atr_sum / hl_diff).replace(0, 1e-9)
        chop = 100.0 * np.log10(ratio) / np.log10(period)
        df['choppiness'] = chop.clip(0, 100).fillna(50.0)
        return df

    @staticmethod
    def _calculate_hurst(df: pd.DataFrame, max_lag: int = 20) -> pd.DataFrame:
        """
        Calculates rolling Hurst Exponent (H) for market memory & persistence.
        H > 0.55 = Strong Trending Persistence
        H < 0.45 = Strong Mean Reversion
        0.45 <= H <= 0.55 = Random Walk Noise (No statistical edge)
        """
        closes = df['close'].values
        n = len(closes)
        hurst_series = np.full(n, 0.50)

        # Vectorized lag evaluation on rolling window of 30 bars
        window = 30
        lags = range(2, min(max_lag, 15))
        log_lags = np.log(lags)

        for i in range(window, n):
            sub = closes[i-window:i]
            try:
                tau = [np.std(np.subtract(sub[lag:], sub[:-lag])) for lag in lags]
                # Avoid zero or nan
                tau = [max(t, 1e-9) for t in tau]
                poly = np.polyfit(log_lags, np.log(tau), 1)
                h = poly[0] * 2.0
                hurst_series[i] = np.clip(h, 0.1, 0.95)
            except Exception:
                hurst_series[i] = 0.50

        df['hurst_exponent'] = np.round(hurst_series, 3)

        # AlphaRegime Classification
        regimes = []
        for h, chop, c, e50 in zip(df['hurst_exponent'], df['choppiness'], df['close'], df.get('ema_50', df['close'])):
            if chop < 42.0 and h > 0.52:
                regimes.append('TRENDING_BULL' if c >= e50 else 'TRENDING_BEAR')
            elif chop > 58.0 or h < 0.45:
                regimes.append('MEAN_REVERTING')
            else:
                regimes.append('RANDOM_WALK_NOISE')

        df['alpha_regime'] = regimes
        return df
