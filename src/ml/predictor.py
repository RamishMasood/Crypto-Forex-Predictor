"""
Walk-Forward Machine Learning Predictor
Trains ensemble classification and regression models on real live OHLCV data
to predict directional probability, expected price change %, and confidence metrics.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score
from .features import FeatureEngineer

class MachineLearningPredictor:
    """
    Ensemble machine learning model for time-series directional prediction.
    """

    def __init__(self, n_estimators: int = 60, random_state: int = 42):
        self.clf = RandomForestClassifier(
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
        Trains model on historical candles and predicts directional distribution on latest live candle.
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

        # Time-series cross validation to evaluate model performance on out-of-sample data
        tscv = TimeSeriesSplit(n_splits=3)
        acc_scores = []
        for train_idx, val_idx in tscv.split(X):
            X_tr, y_tr = X.iloc[train_idx], y_class.iloc[train_idx]
            X_v, y_v = X.iloc[val_idx], y_class.iloc[val_idx]
            if len(np.unique(y_tr)) > 1:
                clf_eval = RandomForestClassifier(n_estimators=30, max_depth=5, random_state=42)
                clf_eval.fit(X_tr, y_tr)
                preds = clf_eval.predict(X_v)
                acc_scores.append(accuracy_score(y_v, preds))

        self.cv_accuracy = float(np.mean(acc_scores)) * 100.0 if acc_scores else 50.0

        # Fit full models on all historical labeled data
        self.clf.fit(X, y_class)
        self.reg.fit(X, y_reg)
        self.is_trained = True

        # Extract feature importances
        importances = self.clf.feature_importances_
        feature_names = FeatureEngineer.FEATURE_COLUMNS
        feat_imp = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
        self.top_features = [{'feature': name, 'weight': round(float(wt) * 100, 2)} for name, wt in feat_imp[:5]]

        # Prepare features for the latest LIVE candle
        all_features = FeatureEngineer.extract_features(df_with_indicators)
        latest_X = all_features.iloc[[-1]]

        # Predict probabilities: classes might be [-1, 0, 1] or a subset
        classes = list(self.clf.classes_)
        probas = self.clf.predict_proba(latest_X)[0]
        prob_dict = {c: p for c, p in zip(classes, probas)}

        p_bullish = float(prob_dict.get(1, 0.0))
        p_bearish = float(prob_dict.get(-1, 0.0))
        p_neutral = float(prob_dict.get(0, 0.0))

        # Expected return from regressor
        expected_ret = float(self.reg.predict(latest_X)[0])

        # Direction determination
        if p_bullish > p_bearish and p_bullish > 0.40:
            predicted_dir = 'BULLISH'
            confidence = (p_bullish - p_bearish) * 100.0
        elif p_bearish > p_bullish and p_bearish > 0.40:
            predicted_dir = 'BEARISH'
            confidence = (p_bearish - p_bullish) * 100.0
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
            'top_features': self.top_features
        }
