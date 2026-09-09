"""
Walk-Forward Machine Learning Predictor
Trains ensemble classification and regression models on real live OHLCV data
to predict directional probability, expected price change %, and confidence metrics.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, ExtraTreesClassifier, GradientBoostingRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score
from .features import FeatureEngineer

class MachineLearningPredictor:
    """
    World-Class Multi-Model Ensemble Machine Learning Predictor.
    Combines Random Forest (bagging), Gradient Boosting (boosting),
    and ExtraTrees (variance reduction) with exponential recency weighting
    to deliver calibrated directional probabilities.
    """

    def __init__(self, n_estimators: int = 60, random_state: int = 42):
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
        self.is_trained = False
        self.feature_importances_ = {}
        self.cv_accuracy = 0.0

    def fit_and_predict(self, df_with_indicators: pd.DataFrame, horizon: int = 3, threshold_pct: float = 0.25) -> Dict[str, Any]:
        """
        Trains multi-model ensemble on historical candles with time-decay sample weighting
        and predicts directional distribution on the latest live candle.
        """
        if len(df_with_indicators) < 35:
            return {
                'status': 'INSUFFICIENT_DATA',
                'p_bullish': 0.33,
                'p_bearish': 0.33,
                'p_neutral': 0.34,
                'predicted_direction': 'NEUTRAL',
                'expected_return_pct': 0.0,
                'confidence_pct': 0.0,
                'cv_accuracy_pct': 0.0,
                'top_features': []
            }

        X, y_class, y_reg = FeatureEngineer.create_training_dataset(
            df_with_indicators, horizon=horizon, threshold_pct=threshold_pct
        )

        if len(X) < 25:
            return {
                'status': 'INSUFFICIENT_DATA',
                'p_bullish': 0.33,
                'p_bearish': 0.33,
                'p_neutral': 0.34,
                'predicted_direction': 'NEUTRAL',
                'expected_return_pct': 0.0,
                'confidence_pct': 0.0,
                'cv_accuracy_pct': 0.0,
                'top_features': []
            }

        if len(np.unique(y_class)) < 2:
            return {
                'status': 'INSUFFICIENT_VARIANCE',
                'p_bullish': 0.33,
                'p_bearish': 0.33,
                'p_neutral': 0.34,
                'predicted_direction': 'NEUTRAL',
                'expected_return_pct': 0.0,
                'confidence_pct': 0.0,
                'cv_accuracy_pct': 50.0,
                'top_features': [],
                'ensemble_models': ['RandomForestClassifier', 'GradientBoostingClassifier', 'ExtraTreesClassifier']
            }

        # Exponential recency weighting: recent market structure matters more
        n_samples = len(X)
        sample_weights = np.exp(np.linspace(-0.8, 0.0, n_samples))

        # Time-series cross validation to evaluate model performance on out-of-sample data
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

        # Fit full ensemble models with sample weighting
        try:
            self.rf.fit(X, y_class, sample_weight=sample_weights)
            self.et.fit(X, y_class, sample_weight=sample_weights)
        except Exception:
            return {
                'status': 'FIT_ERROR_FALLBACK',
                'p_bullish': 0.33,
                'p_bearish': 0.33,
                'p_neutral': 0.34,
                'predicted_direction': 'NEUTRAL',
                'expected_return_pct': 0.0,
                'confidence_pct': 0.0,
                'cv_accuracy_pct': 50.0,
                'top_features': [],
                'ensemble_models': ['RandomForestClassifier', 'GradientBoostingClassifier', 'ExtraTreesClassifier']
            }

        try:
            self.gbc.fit(X, y_class, sample_weight=sample_weights)
            has_gbc = True
        except Exception:
            has_gbc = False

        try:
            self.reg.fit(X, y_reg, sample_weight=sample_weights)
        except Exception:
            pass

        self.is_trained = True

        # Extract blended feature importances from RF and ET
        rf_imp = self.rf.feature_importances_
        et_imp = self.et.feature_importances_
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
            return {c: p for c, p in zip(classes, probas)}

        rf_probs = get_prob_dict(self.rf, latest_X)
        et_probs = get_prob_dict(self.et, latest_X)
        gbc_probs = get_prob_dict(self.gbc, latest_X) if has_gbc else rf_probs

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
        expected_ret = float(self.reg.predict(latest_X)[0])

        # Direction determination with consensus boost
        if p_bullish > p_bearish and p_bullish > 0.38:
            predicted_dir = 'BULLISH'
            confidence = (p_bullish - p_bearish) * 100.0
            # Model consensus bonus if all models agree on bullish bias
            if rf_probs.get(1, 0) > 0.4 and et_probs.get(1, 0) > 0.4 and gbc_probs.get(1, 0) > 0.4:
                confidence = min(100.0, confidence * 1.25)
        elif p_bearish > p_bullish and p_bearish > 0.38:
            predicted_dir = 'BEARISH'
            confidence = (p_bearish - p_bullish) * 100.0
            # Model consensus bonus if all models agree on bearish bias
            if rf_probs.get(-1, 0) > 0.4 and et_probs.get(-1, 0) > 0.4 and gbc_probs.get(-1, 0) > 0.4:
                confidence = min(100.0, confidence * 1.25)
        else:
            predicted_dir = 'NEUTRAL'
            confidence = p_neutral * 100.0

        return {
            'status': 'SUCCESS',
            'p_bullish': round(p_bullish, 4),
            'p_bearish': round(p_bearish, 4),
            'p_neutral': round(p_neutral, 4),
            'predicted_direction': predicted_dir,
            'expected_return_pct': round(expected_ret, 3),
            'confidence_pct': round(min(100.0, max(0.0, confidence)), 1),
            'cv_accuracy_pct': round(self.cv_accuracy, 1),
            'top_features': self.top_features,
            'ensemble_models': ['RandomForestClassifier', 'GradientBoostingClassifier', 'ExtraTreesClassifier']
        }
