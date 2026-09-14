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
        'hurst_norm', 'chop_norm', 'stoch_rsi_diff',
        'garman_klass_norm', 'hma_slope_norm',
        # ML-aware risk-proxy features (added cautiously) — still proxy, not executed target
        'sl_atr_distance_prox', 'entry_vs_proxy_swing_prox',
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

        # 10. Garman-Klass Volatility & HMA Slope Norm
        feat['garman_klass_norm'] = (df['garman_klass_vol'] * 10.0).clip(0.0, 5.0) if 'garman_klass_vol' in df.columns else 0.1
        feat['hma_slope_norm'] = (df['hma_slope'] / close * 100.0).clip(-3.0, 3.0) if 'hma_slope' in df.columns else 0.0

        # 11. ML-aware risk-proxy features (cautious, structural proxies only)
        atr_val = df['atr_14'].replace(0, 1e-8) if 'atr_14' in df.columns else pd.Series(0.25, index=df.index)

        # Proxy stop distance in ATR units (based on a fixed ATR multiple + swing proxy).
        # We use 1.80 * ATR as a baseline proxy for a "typical golden stop" and add
        # a structural swing buffer proxy if a recent swing proxy exists.
        if 'recent_swing_high' in df.columns and 'recent_swing_low' in df.columns:
            swing_high = df['recent_swing_high'].replace(0, 1e-8)
            swing_low = df['recent_swing_low'].replace(0, 1e-8)
            # proxy swing distance away from price in ATR units (split by direction later in pipeline)
            swing_proxy = (close - swing_low).abs() / atr_val
        else:
            swing_proxy = pd.Series(0.0, index=df.index)
        feat['sl_atr_distance_prox'] = (1.80 + swing_proxy.clip(0.0, 2.0)) * (atr_val / close)
        feat['entry_vs_proxy_swing_prox'] = swing_proxy.clip(-3.0, 3.0).fillna(0.0)

        return feat[cls.FEATURE_COLUMNS].fillna(0.0)

    @classmethod
    def create_training_dataset(cls, df: pd.DataFrame, horizon: int = 3, threshold_pct: float = 0.25,
                                use_sl_prox_label: bool = False, min_sl_lookahead: int = 12) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
        """
        Creates feature matrix X, classification target y_class (-1, 0, 1), and regression target y_reg (forward return %).
        Adaptive thresholding adjusts to asset volatility (crypto vs forex).

        Optional SL-prox labeling (opt-in via use_sl_prox_label=True):
            y_class = +1 if TP1 (0.38*ATR) is hit before SL-prox (1.80*ATR + swing buffer) within horizon bars,
                      -1 if SL-prox is hit before TP1,
                       0 if neither / both ambiguous / insufficient forward data.
            y_reg   = normalized SL distance in ATR units (proxy) for that bar (clipped to 1.0-8.0).
        """
        X = cls.extract_features(df)

        if use_sl_prox_label and horizon >= min_sl_lookahead and 'high' in df.columns and 'low' in df.columns:
            # --- SL/TP-aware labeling path (proxy only; does not touch RiskManager SL geometry) ---
            atr = df['atr_14'].replace(0, 1e-8) if 'atr_14' in df.columns else \
                (df['high'] - df['low']).rolling(14, min_periods=1).mean().replace(0, 1e-8)

            # Swing buffer proxy (ATR units), default 0.2; min distance to recent swing low/high
            swing_buffer = pd.Series(0.2, index=df.index)
            if 'recent_swing_low' in df.columns and 'recent_swing_high' in df.columns:
                dist_to_low = (df['close'] - df['recent_swing_low']).abs()
                dist_to_high = (df['recent_swing_high'] - df['close']).abs()
                swing_buffer = pd.concat([dist_to_low, dist_to_high], axis=1).min(axis=1) / atr
                swing_buffer = swing_buffer.clip(lower=0.2).fillna(0.2)

            sl_price = df['close'] - (1.80 + swing_buffer) * atr
            tp_price = df['close'] + 0.38 * atr  # TP1 scalp

            highs = df['high'].values
            lows = df['low'].values
            sl_vals = sl_price.values
            tp_vals = tp_price.values

            y_class_list = []
            y_reg_list = []
            for i in range(len(df)):
                if i + horizon >= len(df):
                    y_class_list.append(0)
                    y_reg_list.append(np.nan)
                    continue
                fh = highs[i + 1:i + 1 + horizon]
                fl = lows[i + 1:i + 1 + horizon]
                tp_hit = bool(np.any(fh >= tp_vals[i]))
                sl_hit = bool(np.any(fl <= sl_vals[i]))
                if tp_hit and not sl_hit:
                    y_class_list.append(1)
                elif sl_hit and not tp_hit:
                    y_class_list.append(-1)
                else:
                    y_class_list.append(0)
                y_reg_list.append(float(np.clip(1.80 + swing_buffer.iloc[i], 1.0, 8.0)))

            y_class = pd.Series(y_class_list, index=df.index)
            y_reg = pd.Series(y_reg_list, index=df.index)
            valid_mask = ~y_reg.isna()
            return X[valid_mask], y_class[valid_mask], y_reg[valid_mask]

        # --- Original forward-return labeling path (default, fully backward compatible) ---
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
