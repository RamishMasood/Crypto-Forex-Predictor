#!/usr/bin/env python3
"""
Training smoke test for the optional SL-prox regression target.

Verifies that fit_and_predict works with:
  1. enable_sl_prox_target=False (default path — backward compatible, no SL keys, base model file)
  2. enable_sl_prox_target=True  (opt-in path — SL keys present, _slprox model file, reg_sl trained)
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd

from src.ml.predictor import MachineLearningPredictor
from src.strategies.indicators import QuantitativeIndicators

N = 260  # enough rows so sl-prox labeling (horizon=12) keeps >= 25 valid samples
np.random.seed(11)

# Defensive startup cleanup: a previously killed/timed-out run may have left
# smoke model files behind, which would corrupt these test cases.
for f in ('SMOKE_OFF_15m_model.joblib', 'SMOKE_ON_15m_model_slprox.joblib',
          'SMOKE_FB_15m_model_slprox.joblib', 'SMOKE_STALE_15m_model.joblib'):
    path = os.path.join('src', 'ml', 'models', f)
    if os.path.exists(path):
        os.remove(path)

close = 100 + np.cumsum(np.random.normal(0, 1.2, N))
df = pd.DataFrame({
    'timestamp': pd.date_range('2026-01-01', periods=N, freq='15min'),
    'open': close + np.random.normal(0, 0.1, N),
    'high': close + np.abs(np.random.normal(0.4, 0.3, N)),
    'low': close - np.abs(np.random.normal(0.4, 0.3, N)),
    'close': close,
    'volume': 1000 + np.abs(np.random.normal(0, 120, N)),
})
df_ind = QuantitativeIndicators.add_all_indicators(df)

# --- Case 1: default (flag OFF) — output shape must be unchanged ---
p_off = MachineLearningPredictor(n_estimators=20, enable_sl_prox_target=False)
res_off = p_off.fit_and_predict(df_ind, horizon=12, threshold_pct=0.15, symbol='SMOKE_OFF', timeframe='15m')
assert res_off['status'] == 'SUCCESS', f"default path failed: {res_off['status']}"
assert 'sl_prox_atr_distance_lower_bound' not in res_off, 'SL key leaked into default output'
assert not os.path.exists(p_off.get_model_path('SMOKE_OFF', '15m', include_sl_prox=True)), \
    'slprox model file must not exist when flag is off'
print('PASS default path (flag OFF):', res_off['status'], '| no SL keys | no slprox file')

# --- Case 2: opt-in (flag ON) — SL-prox target trained, keys present, _slprox file ---
p_on = MachineLearningPredictor(n_estimators=20, enable_sl_prox_target=True)
res_on = p_on.fit_and_predict(df_ind, horizon=12, threshold_pct=0.15, symbol='SMOKE_ON', timeframe='15m',
                              use_sl_prox_label=True, min_sl_lookahead=12)
assert res_on['status'] == 'SUCCESS', f"sl-prox path failed: {res_on['status']}"
assert p_on.reg_sl is not None, 'reg_sl was not trained with sl-prox enabled'
assert 'sl_prox_atr_distance_lower_bound' in res_on, 'missing SL-prox output key'
sl_val = res_on['sl_prox_atr_distance_lower_bound']
assert 1.0 <= sl_val <= 8.0, f'SL-prox value out of clip range: {sl_val}'
assert os.path.exists(p_on.get_model_path('SMOKE_ON', '15m', include_sl_prox=True)), \
    '_slprox model file was not saved'
assert not os.path.exists(p_on.get_model_path('SMOKE_ON', '15m', include_sl_prox=False)), \
    'base model file must not be written when sl-prox is active (suffix isolation)'

# --- Case 3: persistence round-trip — new instance loads the _slprox model ---
p_load = MachineLearningPredictor(n_estimators=20, enable_sl_prox_target=True)
assert p_load.load_model('SMOKE_ON', '15m', include_sl_prox=True), 'failed to load _slprox model'
assert p_load.reg_sl is not None, 'reg_sl missing after persistence round-trip'
live_res = p_load.predict_live(df_ind, symbol='SMOKE_ON', timeframe='15m')
assert live_res['status'] == 'SUCCESS', f"predict_live failed: {live_res['status']}"
assert live_res.get('is_cached_model') is True, 'predict_live did not use cached model'
assert 'sl_prox_atr_distance_lower_bound' in live_res, 'missing SL key in cached inference'
print('PASS persistence round-trip: cached inference | sl_prox =', live_res['sl_prox_atr_distance_lower_bound'])

# --- Case 4: untrained predict_live fallback (flag ON, no cached model) ---
# Exercises the internal fit_and_predict fallback with use_sl_prox_label=True
p_fb = MachineLearningPredictor(n_estimators=20, enable_sl_prox_target=True)
fb_res = p_fb.predict_live(df_ind, symbol='SMOKE_FB', timeframe='15m')
assert fb_res['status'] == 'SUCCESS', f"fallback path failed: {fb_res['status']}"
assert fb_res.get('is_cached_model') is False, 'fallback should not claim cached model'
assert 'sl_prox_atr_distance_lower_bound' in fb_res, 'missing SL key in fallback output'
print('PASS untrained fallback: status =', fb_res['status'], '| sl_prox =', fb_res['sl_prox_atr_distance_lower_bound'])

# --- Case 5: stale/legacy cache rejection (self-healing retrain trigger) ---
import joblib as _joblib

p_stale = MachineLearningPredictor(n_estimators=20, enable_sl_prox_target=False)
r5 = p_stale.fit_and_predict(df_ind, horizon=3, threshold_pct=0.15, symbol='SMOKE_STALE', timeframe='15m')
assert r5['status'] == 'SUCCESS', f"case 5 training failed: {r5['status']}"

tagged_path = p_stale.get_model_path('SMOKE_STALE', '15m', include_sl_prox=False)
payload = _joblib.load(tagged_path)
assert payload.get('feature_columns') is not None, 'saved model must carry a feature-schema tag'

# Simulate a legacy/stale cache (pre-schema-tag or old feature set): strip the tag
payload.pop('feature_columns', None)
_joblib.dump(payload, tagged_path, compress=3)

p_reload = MachineLearningPredictor(n_estimators=20)
assert not p_reload.load_model('SMOKE_STALE', '15m'), 'stale/legacy cache must be rejected'
assert not p_reload.is_trained, 'is_trained must remain False after rejecting stale cache'

# predict_live must transparently self-heal via the fit_and_predict fallback
stale_res = p_reload.predict_live(df_ind, symbol='SMOKE_STALE', timeframe='15m')
assert stale_res['status'] == 'SUCCESS', f"self-healing fallback failed: {stale_res['status']}"
print('PASS stale-cache rejection: load_model=False -> transparent retrain fallback')

# --- Cleanup smoke model files ---
for f in ('SMOKE_OFF_15m_model.joblib', 'SMOKE_ON_15m_model_slprox.joblib',
          'SMOKE_FB_15m_model_slprox.joblib', 'SMOKE_STALE_15m_model.joblib'):
    path = os.path.join('src', 'ml', 'models', f)
    if os.path.exists(path):
        os.remove(path)

print('PASS sl-prox training smoke test (all 5 cases)')