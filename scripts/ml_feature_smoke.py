#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from src.ml import features as mf

n = 80
np.random.seed(7)

close_series = 100 + np.cumsum(np.random.normal(0, 1, n))
df = pd.DataFrame({
    'timestamp': pd.date_range('2026-01-01', periods=n, freq='1h'),
    'open': close_series,
    'high': close_series + np.abs(np.random.normal(0.2, 0.2, n)),
    'low': close_series - np.abs(np.random.normal(0.2, 0.2, n)),
    'close': close_series,
    'volume': 1000 + np.random.normal(0, 1, n) * 100,
    'atr_14': 2.0 + np.random.normal(0, 0.3, n),
    'rsi_14': 50 + np.random.normal(0, 10, n),
    'macd_hist': np.random.normal(0, 1, n),
    'macd_hist_slope': np.random.normal(0, 0.2, n),
    'bb_pct_b': 0.5 + np.random.normal(0, 0.3, n),
    'bb_width': 0.2 + np.random.normal(0, 0.05, n),
    'adx_14': 25 + np.random.normal(0, 5, n),
    'supertrend_dir': np.sign(np.random.normal(0, 1, n)),
    'ema_trend': np.sign(np.random.normal(0, 1, n)),
    'kaufman_er': 0.3 + np.random.normal(0, 0.05, n),
    'cmo_14': np.random.normal(0, 10, n),
    'cvd_zscore': np.random.normal(0, 1, n),
    'hurst_exponent': 0.5 + np.random.normal(0, 0.1, n),
    'choppiness': 50 + np.random.normal(0, 10, n),
    'stoch_rsi_k': 0.5 + np.random.normal(0, 0.1, n),
    'stoch_rsi_d': 0.5 + np.random.normal(0, 0.1, n),
    'garman_klass_vol': 0.2 + np.random.normal(0, 0.05, n),
    'hma_slope': np.random.normal(0, 0.5, n),
    'recent_swing_high': close_series + 0.5 * np.abs(np.random.normal(0, 0.2, n)),
    'recent_swing_low': close_series - 0.5 * np.abs(np.random.normal(0, 0.2, n)),
})

feat = mf.FeatureEngineer.extract_features(df)

assert sorted(feat.columns.tolist()) == sorted(mf.FeatureEngineer.FEATURE_COLUMNS), 'feature columns mismatch'
assert len(feat) == len(df), 'row count mismatch'
assert not feat.isna().any().any(), 'unexpected NaN in features'

print('PASS feature smoke test')
print('rows:', len(feat), '| feature_count:', len(feat.columns))
print('has risk-proxy cols:', 'sl_atr_distance_prox' in feat.columns and 'entry_vs_proxy_swing_prox' in feat.columns)
print('risk-proxy sample (last 3):')
print(feat[['sl_atr_distance_prox', 'entry_vs_proxy_swing_prox']].tail(3).to_string())
