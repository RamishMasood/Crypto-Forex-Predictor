"""
Walk-Forward Machine Learning Predictor
Trains ensemble classification and regression models on live OHLCV data
with Scikit-Learn CalibratedClassifierCV (Platt Scaling) and Expected Value (EV) Gate.
Supports model persistence/caching (.joblib) and MT5 2,000-5,000 candle walk-forward training.
"""

import os
import sys
import time
import logging
from typing import Dict, Any, Tuple, Optional, List
import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, ExtraTreesClassifier, GradientBoostingRegressor
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score
from .features import FeatureEngineer

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _SafeStreamHandler(logging.StreamHandler):
    """Stream handler that never crashes on non-encodable characters (Windows consoles)."""
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg.encode('ascii', 'backslashreplace').decode('ascii') + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


logger = logging.getLogger("MachineLearningPredictor")
if not logger.handlers:
    # Mirror the AutonomousManager logging setup so INFO lines (e.g. "Persistent model
    # saved to ...") are actually emitted. Without handlers, Python's lastResort fallback
    # only shows WARNING+ messages as bare, unformatted lines and swallows all INFO logs.
    logger.setLevel(logging.INFO)
    _sh = _SafeStreamHandler(sys.stdout)
    _fh = logging.FileHandler(os.path.join(_ROOT_DIR, "ml_predictor.log"), encoding="utf-8")
    _fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    _sh.setFormatter(_fmt)
    _fh.setFormatter(_fmt)
    logger.addHandler(_sh)
    logger.addHandler(_fh)

MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')
try:
    os.makedirs(MODELS_DIR, exist_ok=True)
except OSError:
    pass


class MachineLearningPredictor:
    """
    World-Class Multi-Model Ensemble Machine Learning Predictor.
    Combines Random Forest (bagging), Gradient Boosting (boosting),
    and ExtraTrees (variance reduction) with exponential recency weighting,
    Scikit-Learn CalibratedClassifierCV (Platt Scaling), and Expected Value (EV) evaluation.
    Supports persistent disk caching to avoid retraining on small 50-100 bar noisy samples.
    """

    def __init__(self, n_estimators: int = 60, random_state: int = 42, cache_ttl_hours: float = 8.0, enable_sl_prox_target: bool = False):
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.cache_ttl_hours = cache_ttl_hours
        self.enable_sl_prox_target = enable_sl_prox_target

        self.rf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=6,
            min_samples_split=4,
            class_weight='balanced',
            random_state=random_state
        )
        self.gbc = GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=4,
            learning_rate=0.05,
            random_state=random_state
        )
        self.et = ExtraTreesClassifier(
            n_estimators=n_estimators,
            max_depth=6,
            min_samples_split=4,
            class_weight='balanced',
            random_state=random_state
        )
        self.reg = GradientBoostingRegressor(
            n_estimators=n_estimators,
            max_depth=4,
            learning_rate=0.05,
            random_state=random_state
        )
        # Optional SL-proxy regressor (predicts normalized SL distance in ATR units)
        self.reg_sl: Optional[GradientBoostingRegressor] = None

        self.calibrated_rf: Optional[Any] = None
        self.calibrated_et: Optional[Any] = None
        self.calibrated_gbc: Optional[Any] = None

        self.is_trained = False
        self.feature_importances_ = {}
        self.cv_accuracy = 0.0
        self.top_features: List[Dict[str, Any]] = []
        self.last_trained_timestamp = 0.0
        self.training_samples_count = 0

    @classmethod
    def _clean_symbol(cls, symbol: str) -> str:
        s = str(symbol).upper().replace('/', '_').replace(' ', '').replace(':', '_')
        for suf in ['.RAW', 'RAW', '#', 'M', 'C']:
            if s.endswith(suf):
                s = s[:-len(suf)]
                break
        return s

    @classmethod
    def get_model_path(cls, symbol: str, timeframe: str, include_sl_prox: bool = False) -> str:
        clean_s = cls._clean_symbol(symbol)
        clean_tf = str(timeframe).lower().strip()
        suffix = "_slprox" if include_sl_prox else ""
        filename = f"{clean_s}_{clean_tf}_model{suffix}.joblib"
        return os.path.join(MODELS_DIR, filename)

    @classmethod
    def is_model_cached(cls, symbol: str, timeframe: str, max_age_hours: float = 8.0) -> bool:
        path = cls.get_model_path(symbol, timeframe)
        if not os.path.exists(path):
            return False
        try:
            mtime = os.path.getmtime(path)
            age_hours = (time.time() - mtime) / 3600.0
            if age_hours >= max_age_hours:
                return False
            # Schema-aware freshness: a cache trained with a different (e.g. legacy)
            # feature set is treated as not-cached so the caller retrains instead of
            # hitting sklearn feature-name mismatch errors during inference.
            probe = joblib.load(path)
            cached_cols = probe.get('feature_columns') if isinstance(probe, dict) else None
            if cached_cols is None or list(cached_cols) != list(FeatureEngineer.FEATURE_COLUMNS):
                logger.warning(
                    f"Cached model {path} has outdated/legacy feature schema; treating as not-cached (will retrain)."
                )
                return False
            return True
        except Exception:
            return False

    def save_model(self, symbol: str, timeframe: str, n_samples: int = 0, include_sl_prox: bool = False) -> str:
        path = self.get_model_path(symbol, timeframe, include_sl_prox=include_sl_prox)
        payload = {
            'feature_columns': list(FeatureEngineer.FEATURE_COLUMNS),
            'calibrated_rf': self.calibrated_rf or self.rf,
            'calibrated_et': self.calibrated_et or self.et,
            'calibrated_gbc': self.calibrated_gbc or self.gbc,
            'reg': self.reg,
            'reg_sl': self.reg_sl,
            'cv_accuracy': self.cv_accuracy,
            'top_features': self.top_features,
            'trained_at': time.time(),
            'n_samples': n_samples or self.training_samples_count,
            'symbol': symbol,
            'timeframe': timeframe,
            'include_sl_prox': include_sl_prox
        }
        try:
            joblib.dump(payload, path, compress=3)
            logger.info(f"Persistent model saved to {path} ({n_samples} training bars)")
            return path
        except Exception as e:
            logger.warning(f"Failed to save model to {path}: {e}")
            return ""

    def load_model(self, symbol: str, timeframe: str, include_sl_prox: bool = False) -> bool:
        path = self.get_model_path(symbol, timeframe, include_sl_prox=include_sl_prox)
        if not os.path.exists(path):
            return False
        try:
            payload = joblib.load(path)

            # Feature-schema guard: reject caches trained with a different/legacy feature set.
            # Prevents sklearn "feature names should match those passed during fit" errors and
            # makes the app self-heal via the fit_and_predict fallback (which re-tags on save).
            cached_cols = payload.get('feature_columns')
            if cached_cols is None or list(cached_cols) != list(FeatureEngineer.FEATURE_COLUMNS):
                logger.warning(
                    f"Cached model {path} has outdated/legacy feature schema; rejecting cache to retrain."
                )
                return False

            self.calibrated_rf = payload.get('calibrated_rf')
            self.calibrated_et = payload.get('calibrated_et')
            self.calibrated_gbc = payload.get('calibrated_gbc')
            self.reg = payload.get('reg')
            self.reg_sl = payload.get('reg_sl')
            self.cv_accuracy = float(payload.get('cv_accuracy', 55.0))
            self.top_features = payload.get('top_features', [])
            self.last_trained_timestamp = float(payload.get('trained_at', 0.0))
            self.training_samples_count = int(payload.get('n_samples', 0))
            self.is_trained = True
            return True
        except Exception as e:
            logger.warning(f"Failed to load persistent model from {path}: {e}")
            return False

    def predict_live(self, df_with_indicators: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        Executes fast sub-millisecond inference using the cached/persistent trained model
        without retraining on small noisy live windows.
        """
        if not self.is_trained:
            loaded = self.load_model(symbol, timeframe, include_sl_prox=self.enable_sl_prox_target)
            if not loaded:
                return self.fit_and_predict(df_with_indicators, symbol=symbol, timeframe=timeframe,
                                            use_sl_prox_label=self.enable_sl_prox_target)

        if len(df_with_indicators) < 5:
            return self._empty_result('INSUFFICIENT_DATA', include_sl_prox=self.enable_sl_prox_target)

        try:
            all_features = FeatureEngineer.extract_features(df_with_indicators)
            latest_X = all_features.iloc[[-1]]

            # Belt-and-braces schema check: if a loaded model still expects a different
            # feature count, fail fast into the retraining fallback instead of letting
            # sklearn raise a confusing feature-name mismatch mid-inference.
            rf_check = self.calibrated_rf or self.rf
            n_expected = getattr(rf_check, 'n_features_in_', None)
            if n_expected is not None and n_expected != latest_X.shape[1]:
                raise ValueError(
                    f"Loaded model expects {n_expected} features but extract_features produced {latest_X.shape[1]}"
                )

            rf_model = self.calibrated_rf or self.rf
            et_model = self.calibrated_et or self.et
            gbc_model = self.calibrated_gbc or self.gbc

            def get_prob_dict(model, X_input):
                classes = list(model.classes_)
                probas = model.predict_proba(X_input)[0]
                return {c: float(p) for c, p in zip(classes, probas)}

            rf_probs = get_prob_dict(rf_model, latest_X)
            et_probs = get_prob_dict(et_model, latest_X)
            gbc_probs = get_prob_dict(gbc_model, latest_X) if gbc_model else rf_probs

            all_classes = set(list(rf_probs.keys()) + list(et_probs.keys()) + list(gbc_probs.keys()))
            blended_probs = {}
            for c in all_classes:
                p_rf = rf_probs.get(c, 0.0)
                p_et = et_probs.get(c, 0.0)
                p_gbc = gbc_probs.get(c, 0.0)
                # Weighted soft voting: 40% GBC, 35% RF, 25% ET
                blended_probs[c] = (0.40 * p_gbc) + (0.35 * p_rf) + (0.25 * p_et)

            total_p = sum(blended_probs.values()) or 1.0
            blended_probs = {c: p / total_p for c, p in blended_probs.items()}

            p_bullish = float(blended_probs.get(1, 0.0))
            p_bearish = float(blended_probs.get(-1, 0.0))
            p_neutral = float(blended_probs.get(0, 0.0))

            expected_ret = float(self.reg.predict(latest_X)[0]) if self.reg else 0.0

            # Direction determination
            if p_bullish > p_bearish and p_bullish > 0.38:
                predicted_dir = 'BULLISH'
                confidence = (p_bullish - p_bearish) * 100.0
                if rf_probs.get(1, 0) > 0.4 and et_probs.get(1, 0) > 0.4 and gbc_probs.get(1, 0) > 0.4:
                    confidence = min(100.0, confidence * 1.25)
            elif p_bearish > p_bullish and p_bearish > 0.38:
                predicted_dir = 'BEARISH'
                confidence = (p_bearish - p_bullish) * 100.0
                if rf_probs.get(-1, 0) > 0.4 and et_probs.get(-1, 0) > 0.4 and gbc_probs.get(-1, 0) > 0.4:
                    confidence = min(100.0, confidence * 1.25)
            else:
                predicted_dir = 'NEUTRAL'
                confidence = p_neutral * 100.0

            # Mathematical Expected Value (EV)
            if predicted_dir == 'BULLISH':
                dir_denom = (p_bullish + p_bearish) if (p_bullish + p_bearish) > 0 else 1.0
                p_win = p_bullish / dir_denom
            elif predicted_dir == 'BEARISH':
                dir_denom = (p_bullish + p_bearish) if (p_bullish + p_bearish) > 0 else 1.0
                p_win = p_bearish / dir_denom
            else:
                # For NEUTRAL: use max directional probability as a conservative signal
                # This gives a meaningful Platt% instead of a hardcoded 33% placeholder
                dir_denom = (p_bullish + p_bearish) if (p_bullish + p_bearish) > 0 else 1.0
                p_win = max(p_bullish, p_bearish) / dir_denom if dir_denom > 0 else 0.50
                p_win = max(0.42, min(0.58, p_win))  # Clamp NEUTRAL range: 42%–58%

            p_loss = 1.0 - p_win
            avg_reward_r = 2.0
            avg_risk_r = 1.0
            expected_value_r = round((p_win * avg_reward_r) - (p_loss * avg_risk_r), 2)
            is_ev_positive = bool(expected_value_r >= 0.15)

            res = {
                'status': 'SUCCESS',
                'p_bullish': round(p_bullish, 4),
                'p_bearish': round(p_bearish, 4),
                'p_neutral': round(p_neutral, 4),
                'predicted_direction': predicted_dir,
                'expected_return_pct': round(expected_ret, 3),
                'confidence_pct': round(min(100.0, max(0.0, confidence)), 1),
                'cv_accuracy_pct': round(self.cv_accuracy, 1),
                'top_features': self.top_features,
                'ensemble_models': ['RandomForestClassifier', 'GradientBoostingClassifier', 'ExtraTreesClassifier'],
                'calibration_method': 'Platt Scaling (CalibratedClassifierCV)',
                'expected_value_r': expected_value_r,
                'is_ev_positive': is_ev_positive,
                'p_calibrated_win_pct': round(p_win * 100.0, 1),
                'is_cached_model': True,
                'training_samples': self.training_samples_count
            }

            # Optional SL-proxy regression output (opt-in only to avoid breaking callers)
            if self.enable_sl_prox_target:
                try:
                    sl_prox_pred = float(self.reg_sl.predict(latest_X)[0]) if self.reg_sl else 0.0
                    res['sl_prox_atr_distance_lower_bound'] = round(max(1.0, sl_prox_pred), 3)
                    res['training_samples'] = self.training_samples_count
                except Exception:
                    pass

            return res
        except Exception as e:
            logger.warning(f"Error in predict_live, falling back to fit_and_predict: {e}")
            return self.fit_and_predict(df_with_indicators, symbol=symbol, timeframe=timeframe,
                                        use_sl_prox_label=self.enable_sl_prox_target)

    def _empty_result(self, status: str, include_sl_prox: bool = False) -> Dict[str, Any]:
        res = {
            'status': status,
            'p_bullish': 0.33,
            'p_bearish': 0.33,
            'p_neutral': 0.34,
            'predicted_direction': 'NEUTRAL',
            'expected_return_pct': 0.0,
            'confidence_pct': 0.0,
            'cv_accuracy_pct': 0.0,
            'top_features': [],
            'ensemble_models': ['RandomForestClassifier', 'GradientBoostingClassifier', 'ExtraTreesClassifier'],
            'calibration_method': 'Platt Scaling (CalibratedClassifierCV)',
            'expected_value_r': 0.0,
            'is_ev_positive': False,
            'p_calibrated_win_pct': None,   # None → lets app.py fallback to AlphaSniper Bayesian prob
            'is_cached_model': False
        }
        if include_sl_prox:
            res['sl_prox_atr_distance_lower_bound'] = 1.0
        return res

    def fit_and_predict(
        self,
        df_with_indicators: pd.DataFrame,
        horizon: int = 3,
        threshold_pct: float = 0.25,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        save_cache: bool = True,
        use_sl_prox_label: bool = False,
        min_sl_lookahead: int = 12
    ) -> Dict[str, Any]:
        """
        Trains multi-model ensemble on historical candles with time-decay sample weighting,
        applies Scikit-Learn CalibratedClassifierCV (Platt Scaling) for realistic directional
        probabilities (52%-68%), computes mathematical Expected Value (EV), and saves model.

        Optional:
        - use_sl_prox_label: use TP/SL-aware ternary labels when horizon >= min_sl_lookahead.
        - min_sl_lookahead: minimum bars required before attempting SL-proxy labeling.
        """
        sl_prox_active = self.enable_sl_prox_target and use_sl_prox_label

        if len(df_with_indicators) < 35:
            return self._empty_result('INSUFFICIENT_DATA', include_sl_prox=sl_prox_active)

        X, y_class, y_reg = FeatureEngineer.create_training_dataset(
            df_with_indicators, horizon=horizon, threshold_pct=threshold_pct,
            use_sl_prox_label=sl_prox_active, min_sl_lookahead=min_sl_lookahead
        )

        if len(X) < 25:
            return self._empty_result('INSUFFICIENT_DATA', include_sl_prox=sl_prox_active)

        if len(np.unique(y_class)) < 2:
            res = self._empty_result('INSUFFICIENT_VARIANCE', include_sl_prox=sl_prox_active)
            res['cv_accuracy_pct'] = 50.0
            return res

        # Exponential recency weighting: recent market structure matters more
        n_samples = len(X)
        self.training_samples_count = n_samples
        sample_weights = np.exp(np.linspace(-0.8, 0.0, n_samples))

        # Time-series cross validation
        tscv = TimeSeriesSplit(n_splits=3)
        acc_scores = []
        for train_idx, val_idx in tscv.split(X):
            X_tr, y_tr = X.iloc[train_idx], y_class.iloc[train_idx]
            X_v, y_v = X.iloc[val_idx], y_class.iloc[val_idx]
            if len(np.unique(y_tr)) > 1 and len(np.unique(y_v)) > 0:
                try:
                    clf_eval = RandomForestClassifier(n_estimators=30, max_depth=5, random_state=42)
                    clf_eval.fit(X_tr, y_tr)
                    preds = clf_eval.predict(X_v)
                    acc_scores.append(accuracy_score(y_v, preds))
                except Exception:
                    pass

        self.cv_accuracy = float(np.mean(acc_scores)) * 100.0 if acc_scores else 50.0

        # Determine safe CV fold count for CalibratedClassifierCV
        min_class_count = int(pd.Series(y_class).value_counts().min())
        use_cv_splits = min(3, min_class_count)

        # 1. Fit Base Random Forest and Calibrate via Platt Scaling
        try:
            self.rf.fit(X, y_class, sample_weight=sample_weights)
            self.et.fit(X, y_class, sample_weight=sample_weights)
        except Exception:
            return self._empty_result('FIT_ERROR_FALLBACK', include_sl_prox=sl_prox_active)

        # Calibrate Random Forest
        if use_cv_splits >= 2:
            try:
                self.calibrated_rf = CalibratedClassifierCV(estimator=self.rf, method='sigmoid', cv=use_cv_splits)
                self.calibrated_rf.fit(X, y_class, sample_weight=sample_weights)
            except Exception:
                self.calibrated_rf = self.rf
        else:
            self.calibrated_rf = self.rf

        # Calibrate Extra Trees
        if use_cv_splits >= 2:
            try:
                self.calibrated_et = CalibratedClassifierCV(estimator=self.et, method='sigmoid', cv=use_cv_splits)
                self.calibrated_et.fit(X, y_class, sample_weight=sample_weights)
            except Exception:
                self.calibrated_et = self.et
        else:
            self.calibrated_et = self.et

        # 2. Fit and Calibrate Gradient Boosting Classifier
        has_gbc = False
        try:
            self.gbc.fit(X, y_class, sample_weight=sample_weights)
            if use_cv_splits >= 2:
                try:
                    self.calibrated_gbc = CalibratedClassifierCV(estimator=self.gbc, method='sigmoid', cv=use_cv_splits)
                    self.calibrated_gbc.fit(X, y_class, sample_weight=sample_weights)
                except Exception:
                    self.calibrated_gbc = self.gbc
            else:
                self.calibrated_gbc = self.gbc
            has_gbc = True
        except Exception:
            self.calibrated_gbc = self.calibrated_rf

        try:
            self.reg.fit(X, y_reg, sample_weight=sample_weights)
        except Exception:
            pass

        # Optional SL-proxy regressor: predict normalized SL distance (ATR units) for risk-awareness
        self.reg_sl = None
        if sl_prox_active:
            try:
                self.reg_sl = GradientBoostingRegressor(
                    n_estimators=40, max_depth=3, learning_rate=0.05, random_state=self.random_state
                )
                self.reg_sl.fit(X, y_reg, sample_weight=sample_weights)
            except Exception:
                self.reg_sl = None

        self.is_trained = True

        # Extract blended feature importances from RF and ET
        rf_imp = getattr(self.rf, 'feature_importances_', np.zeros(len(FeatureEngineer.FEATURE_COLUMNS)))
        et_imp = getattr(self.et, 'feature_importances_', np.zeros(len(FeatureEngineer.FEATURE_COLUMNS)))
        importances = (rf_imp + et_imp) / 2.0
        feature_names = FeatureEngineer.FEATURE_COLUMNS
        feat_imp = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
        self.top_features = [{'feature': name, 'weight': round(float(wt) * 100, 2)} for name, wt in feat_imp[:5]]

        # Prepare features for the latest LIVE candle
        all_features = FeatureEngineer.extract_features(df_with_indicators)
        latest_X = all_features.iloc[[-1]]

        # Helper function to get class probabilities
        def get_prob_dict(model, X_input):
            classes = list(model.classes_)
            probas = model.predict_proba(X_input)[0]
            return {c: float(p) for c, p in zip(classes, probas)}

        rf_probs = get_prob_dict(self.calibrated_rf or self.rf, latest_X)
        et_probs = get_prob_dict(self.calibrated_et or self.et, latest_X)
        gbc_probs = get_prob_dict(self.calibrated_gbc or self.gbc, latest_X) if has_gbc else rf_probs

        all_classes = set(list(rf_probs.keys()) + list(et_probs.keys()) + list(gbc_probs.keys()))
        blended_probs = {}
        for c in all_classes:
            p_rf = rf_probs.get(c, 0.0)
            p_et = et_probs.get(c, 0.0)
            p_gbc = gbc_probs.get(c, 0.0)
            # Weighted soft voting: 40% GBC, 35% RF, 25% ET
            blended_probs[c] = (0.40 * p_gbc) + (0.35 * p_rf) + (0.25 * p_et)

        # Normalize probabilities
        total_p = sum(blended_probs.values()) or 1.0
        blended_probs = {c: p / total_p for c, p in blended_probs.items()}

        p_bullish = float(blended_probs.get(1, 0.0))
        p_bearish = float(blended_probs.get(-1, 0.0))
        p_neutral = float(blended_probs.get(0, 0.0))

        # Expected return from regressor
        try:
            expected_ret = float(self.reg.predict(latest_X)[0]) if hasattr(self.reg, 'predict') else 0.0
        except Exception:
            expected_ret = 0.0

        # Direction determination with consensus boost
        if p_bullish > p_bearish and p_bullish > 0.38:
            predicted_dir = 'BULLISH'
            confidence = (p_bullish - p_bearish) * 100.0
            if rf_probs.get(1, 0) > 0.4 and et_probs.get(1, 0) > 0.4 and gbc_probs.get(1, 0) > 0.4:
                confidence = min(100.0, confidence * 1.25)
        elif p_bearish > p_bullish and p_bearish > 0.38:
            predicted_dir = 'BEARISH'
            confidence = (p_bearish - p_bullish) * 100.0
            if rf_probs.get(-1, 0) > 0.4 and et_probs.get(-1, 0) > 0.4 and gbc_probs.get(-1, 0) > 0.4:
                confidence = min(100.0, confidence * 1.25)
        else:
            predicted_dir = 'NEUTRAL'
            confidence = p_neutral * 100.0

        # Mathematical Expected Value (EV) Gate
        if predicted_dir == 'BULLISH':
            dir_denom = (p_bullish + p_bearish) if (p_bullish + p_bearish) > 0 else 1.0
            p_win = p_bullish / dir_denom
        elif predicted_dir == 'BEARISH':
            dir_denom = (p_bullish + p_bearish) if (p_bullish + p_bearish) > 0 else 1.0
            p_win = p_bearish / dir_denom
        else:
            # For NEUTRAL: use max directional probability as a conservative signal
            dir_denom = (p_bullish + p_bearish) if (p_bullish + p_bearish) > 0 else 1.0
            p_win = max(p_bullish, p_bearish) / dir_denom if dir_denom > 0 else 0.50
            p_win = max(0.42, min(0.58, p_win))  # Clamp NEUTRAL range: 42%–58%

        p_loss = 1.0 - p_win
        avg_reward_r = 2.0
        avg_risk_r = 1.0
        expected_value_r = round((p_win * avg_reward_r) - (p_loss * avg_risk_r), 2)
        is_ev_positive = bool(expected_value_r >= 0.15)

        # Save to disk cache if symbol and timeframe are provided
        if symbol and timeframe and save_cache:
            self.save_model(symbol, timeframe, n_samples=n_samples, include_sl_prox=sl_prox_active)

        result = {
            'status': 'SUCCESS',
            'p_bullish': round(p_bullish, 4),
            'p_bearish': round(p_bearish, 4),
            'p_neutral': round(p_neutral, 4),
            'predicted_direction': predicted_dir,
            'expected_return_pct': round(expected_ret, 3),
            'confidence_pct': round(min(100.0, max(0.0, confidence)), 1),
            'cv_accuracy_pct': round(self.cv_accuracy, 1),
            'top_features': self.top_features,
            'ensemble_models': ['RandomForestClassifier', 'GradientBoostingClassifier', 'ExtraTreesClassifier'],
            'calibration_method': 'Platt Scaling (CalibratedClassifierCV)',
            'expected_value_r': expected_value_r,
            'is_ev_positive': is_ev_positive,
            'p_calibrated_win_pct': round(p_win * 100.0, 1),
            'is_cached_model': False,
            'training_samples': n_samples
        }

        # Optional SL-proxy inference output (only present when the flag is enabled)
        if sl_prox_active:
            try:
                sl_prox_pred = float(self.reg_sl.predict(latest_X)[0]) if self.reg_sl else 1.0
                result['sl_prox_atr_distance_lower_bound'] = round(float(np.clip(sl_prox_pred, 1.0, 8.0)), 3)
            except Exception:
                result['sl_prox_atr_distance_lower_bound'] = 1.0

        return result

    def train_on_mt5_history(self, symbol: str, timeframe: str = '1h', n_bars: int = 3000) -> bool:
        """
        Leverages copy_rates_from_pos when MetaTrader 5 is connected to fetch
        2,000 to 5,000 historical bars for robust walk-forward training.
        Persists calibrated model weights to disk.
        """
        try:
            import MetaTrader5 as mt5
            from ..data.forex_feeds import MT5ExnessProvider
            from ..strategies.indicators import QuantitativeIndicators

            provider = MT5ExnessProvider()
            if not provider.is_connected:
                provider.connect()
            if not provider.is_connected:
                return False

            broker_sym = provider.get_exness_symbol(symbol)
            if not broker_sym:
                return False

            tf_val = provider.MT5_TF_MAP.get(timeframe, 16385)
            # Fetch 2,000 - 5,000 bars
            n_bars = max(2000, min(5000, int(n_bars)))
            rates = mt5.copy_rates_from_pos(broker_sym, tf_val, 0, n_bars)
            if rates is None or len(rates) < 100:
                return False

            df = pd.DataFrame(rates)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s')
            df = df.rename(columns={'tick_volume': 'volume'})
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

            df_ind = QuantitativeIndicators.add_all_indicators(df)
            res = self.fit_and_predict(df_ind, horizon=3, threshold_pct=0.25, symbol=symbol, timeframe=timeframe, save_cache=True)
            return res.get('status') == 'SUCCESS'
        except Exception as e:
            logger.warning(f"Error in train_on_mt5_history for {symbol} ({timeframe}): {e}")
            return False
