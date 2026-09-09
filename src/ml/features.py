"""
Feature Engineering Pipeline for Quantitative Machine Learning
Converts raw candlestick data and technical indicators into stationary,
normalized feature matrices for classification and regression.
"""

import numpy as np
import pandas as pd
from typing import Tuple, List

class FeatureEngineer:
    """
    Extracts statistical, momentum, and volatility features for ML models.
    """

    FEATURE_COLUMNS = [
        'ret_1', 'ret_3', 'ret_5', 'ret_10', 'ret_20',
        'volatility_10', 'volatility_20',
        'hl_range_ratio', 'body_wick_ratio',
        'dist_ema_9', 'dist_ema_20', 'dist_ema_50', 'dist_ema_200',
        'rsi_norm', 'macd_norm', 'macd_slope_norm',
        'bb_pct_b', 'bb_width', 'atr_ratio',
        'adx_norm', 'supertrend_dir', 'ema_trend',
        'vol_ratio',
        'kaufman_er', 'cmo_norm', 'cvd_zscore',
        'hurst_norm', 'chop_norm', 'stoch_rsi_diff'
    ]

    @classmethod
    def extract_features(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extracts stationary feature set from indicator-enhanced OHLCV dataframe.
        """
        feat = pd.DataFrame(index=df.index)
        close = df['close']
        high = df['high']
        low = df['low']
        open_p = df['open']

        # 1. Multi-Period Returns
        feat['ret_1'] = close.pct_change(1)
        feat['ret_3'] = close.pct_change(3)
        feat['ret_5'] = close.pct_change(5)
        feat['ret_10'] = close.pct_change(10)
        feat['ret_20'] = close.pct_change(20)

        # 2. Rolling Volatility
        feat['volatility_10'] = feat['ret_1'].rolling(10, min_periods=1).std().fillna(0)
        feat['volatility_20'] = feat['ret_1'].rolling(20, min_periods=1).std().fillna(0)

        # 3. Price Action Candle Geometry
        candle_range = (high - low).replace(0, 1e-8)
        feat['hl_range_ratio'] = candle_range / close
        feat['body_wick_ratio'] = (close - open_p).abs() / candle_range

        # 4. Normalized Distance to EMAs
        for span in [9, 20, 50, 200]:
            col = f'ema_{span}'
            if col in df.columns:
                feat[f'dist_{col}'] = (close - df[col]) / df[col].replace(0, 1e-8)
            else:
                feat[f'dist_{col}'] = 0.0

        # 5. Normalized Oscillators
        feat['rsi_norm'] = (df['rsi_14'] - 50.0) / 50.0 if 'rsi_14' in df.columns else 0.0
        feat['macd_norm'] = df['macd_hist'] / close if 'macd_hist' in df.columns else 0.0
        feat['macd_slope_norm'] = df['macd_hist_slope'] / close if 'macd_hist_slope' in df.columns else 0.0

        # 6. Bollinger & ATR Volatility
        feat['bb_pct_b'] = df['bb_pct_b'].clip(-0.5, 1.5) if 'bb_pct_b' in df.columns else 0.5
        feat['bb_width'] = df['bb_width'] if 'bb_width' in df.columns else 0.0
        feat['atr_ratio'] = df['atr_14'] / close if 'atr_14' in df.columns else 0.01

        # 7. Trend Regime Flags
        feat['adx_norm'] = df['adx_14'] / 100.0 if 'adx_14' in df.columns else 0.25
        feat['supertrend_dir'] = df['supertrend_dir'] if 'supertrend_dir' in df.columns else 0.0
        feat['ema_trend'] = df['ema_trend'] if 'ema_trend' in df.columns else 0.0

        # 8. Volume Flow
        if 'volume' in df.columns and (df['volume'] > 0).any():
            vol_sma = df['volume'].rolling(20, min_periods=1).mean().replace(0, 1e-8)
            feat['vol_ratio'] = (df['volume'] / vol_sma).clip(0, 5.0)
        else:
            feat['vol_ratio'] = 1.0

        # 9. Advanced Quantitative Signals (KER, CMO, CVD Z-score, Hurst, Choppiness)
        feat['kaufman_er'] = df['kaufman_er'] if 'kaufman_er' in df.columns else 0.30
        feat['cmo_norm'] = (df['cmo_14'] / 100.0) if 'cmo_14' in df.columns else 0.0
        feat['cvd_zscore'] = (df['cvd_zscore'] / 3.0).clip(-1.5, 1.5) if 'cvd_zscore' in df.columns else 0.0
        feat['hurst_norm'] = ((df['hurst_exponent'] - 0.50) * 2.0).clip(-1.0, 1.0) if 'hurst_exponent' in df.columns else 0.0
        feat['chop_norm'] = ((df['choppiness'] - 50.0) / 50.0).clip(-1.0, 1.0) if 'choppiness' in df.columns else 0.0

        if 'stoch_rsi_k' in df.columns and 'stoch_rsi_d' in df.columns:
            feat['stoch_rsi_diff'] = ((df['stoch_rsi_k'] - df['stoch_rsi_d']) / 50.0).clip(-1.0, 1.0)
        else:
            feat['stoch_rsi_diff'] = 0.0

        return feat[cls.FEATURE_COLUMNS].fillna(0.0)

    @classmethod
    def create_training_dataset(cls, df: pd.DataFrame, horizon: int = 3, threshold_pct: float = 0.25) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
        """
        Creates feature matrix X, classification target y_class (-1, 0, 1), and regression target y_reg (forward return %).
        Adaptive thresholding adjusts to asset volatility (crypto vs forex).
        """
        X = cls.extract_features(df)
        
        # Forward return calculation
        forward_close = df['close'].shift(-horizon)
        forward_return = ((forward_close - df['close']) / df['close']) * 100.0

        # Adaptive threshold based on historical volatility
        ret_std = float(df['close'].pct_change().std() * 100.0) if len(df) > 5 else threshold_pct
        adaptive_thresh = max(0.03, min(threshold_pct, ret_std * 0.45))

        # Class labels: 1 = Bullish, -1 = Bearish, 0 = Neutral
        y_class = pd.Series(0, index=df.index)
        y_class[forward_return > adaptive_thresh] = 1
        y_class[forward_return < -adaptive_thresh] = -1

        valid_mask = ~forward_return.isna()
        valid_ret = forward_return[valid_mask]

        # If low volatility or flat prices resulted in < 2 unique classes, apply quantile ternary split
        if len(valid_ret) >= 15:
            classes_in_valid = np.unique(y_class[valid_mask])
            if len(classes_in_valid) < 2:
                q_low = float(valid_ret.quantile(0.33))
                q_high = float(valid_ret.quantile(0.67))
                if q_high > q_low:
                    y_class[valid_mask & (forward_return >= q_high)] = 1
                    y_class[valid_mask & (forward_return <= q_low)] = -1

        return X[valid_mask], y_class[valid_mask], forward_return[valid_mask]
