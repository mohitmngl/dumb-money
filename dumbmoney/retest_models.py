"""
OLD_SWING_RETEST_SCORE ML Models

CatBoost classifier for P_WIN/P_DEEP_DRAWDOWN/P_TIMEOUT and regressors
for MFE/MAE predictions. Walk-forward training with calibration.
"""

import numpy as np
import pandas as pd
import logging
import os
import json
import pickle
from datetime import datetime

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "retest")
VERSION = "v1"

FEATURE_NAMES = [
    "resistance_age", "swing_prominence_atr", "num_reactions",
    "avg_reaction_size_atr", "zone_width_atr", "zone_dispersion",
    "num_false_breakouts",
    "breakout_close_dist_atr", "breakout_body_atr", "breakout_clv",
    "breakout_vol_ratio",
    "candles_breakout_to_retest", "pullback_duration",
    "retest_depth_atr", "retest_close_rel", "retest_wick",
    "retest_body_atr",
    "pullback_vol_contraction", "bounce_vol_expansion",
    "closes_below_resistance", "support_tests_after_breakout",
    "current_dist_from_retest_atr",
    "atr_pct_price", "realized_vol_20d", "gap_frequency", "gap_size_avg",
    "liquidity", "median_traded_value", "price_level", "slippage_proxy",
    "ema20_above_ema50", "ema50_above_ema200", "ema20_aligned",
    "ema20_slope", "ema50_slope", "ema200_slope",
    "momentum_20d", "momentum_60d",
    "rs_vs_market", "rs_vs_sector",
    "market_trend", "sector_trend",
    "overhead_space_atr", "is_overextended",
]


def _get_model_path(market, model_type="classifier"):
    """Get path for saved model artifacts."""
    d = os.path.join(MODEL_DIR, market)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{model_type}_{VERSION}.cbm")


def _get_calibrator_path(market, model_type="classifier"):
    """Get path for calibration artifacts."""
    d = os.path.join(MODEL_DIR, market)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"calibrator_{model_type}_{VERSION}.pkl")


def _get_feature_stats_path(market):
    """Get path for feature normalization stats."""
    d = os.path.join(MODEL_DIR, market)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"feature_stats_{VERSION}.pkl")


def train_classifier(X, y_win, y_drawdown, y_timeout, cat_features=None):
    """Train CatBoost three-class classifier.

    Args:
        X: feature matrix (n_samples, n_features)
        y_win: binary array (1 if WIN)
        y_drawdown: binary array (1 if DEEP_DRAWDOWN)
        y_timeout: binary array (1 if TIMEOUT)
        cat_features: list of categorical feature indices

    Returns:
        trained CatBoost Pool + model
    """
    from catboost import CatBoost, Pool

    # Create class labels: 0=TIMEOUT, 1=WIN, 2=DEEP_DRAWDOWN
    y = np.where(y_win == 1, 1, np.where(y_drawdown == 1, 2, 0))

    n = len(y)
    train_idx = np.arange(int(n * 0.8))
    val_idx = np.arange(int(n * 0.8), n)

    train_pool = Pool(X[train_idx], y[train_idx], cat_features=cat_features)
    val_pool = Pool(X[val_idx], y[val_idx], cat_features=cat_features)

    model = CatBoost({
        "iterations": 500,
        "depth": 6,
        "learning_rate": 0.05,
        "loss_function": "MultiClass",
        "eval_metric": "MultiClass",
        "classes_count": 3,
        "random_seed": 42,
        "verbose": 100,
        "early_stopping_rounds": 50,
        "thread_count": 4,
    })

    model.fit(train_pool, eval_set=val_pool, use_best_model=True)
    return model


def train_regressors(X, targets, quantiles=None):
    """Train CatBoost regressors for MFE/MAE/days-to-target.

    Args:
        X: feature matrix
        targets: dict of {target_name: values_array}
        quantiles: dict of {target_name: list_of_quantiles}

    Returns:
        dict of {target_name: trained_model}
    """
    from catboost import CatBoost, Pool

    models = {}
    for name, values in targets.items():
        if np.all(np.isnan(values)):
            continue
        mask = ~np.isnan(values)
        if mask.sum() < 50:
            continue

        X_clean = X[mask]
        y_clean = values[mask]

        n = len(y_clean)
        split = int(n * 0.8)

        if np.std(y_clean[:split]) < 1e-10 or np.std(y_clean[split:]) < 1e-10:
            continue

        train_pool = Pool(X_clean[:split], y_clean[:split])
        val_pool = Pool(X_clean[split:], y_clean[split:])

        model = CatBoost({
            "iterations": 300,
            "depth": 5,
            "learning_rate": 0.05,
            "loss_function": "RMSE",
            "eval_metric": "RMSE",
            "random_seed": 42,
            "verbose": 50,
            "early_stopping_rounds": 30,
            "thread_count": 4,
        })

        model.fit(train_pool, eval_set=val_pool, use_best_model=True)
        models[name] = model

    return models


def predict_classifier(model, X):
    """Predict class probabilities.

    Returns: (p_win, p_deep_drawdown, p_timeout)
    """
    from catboost import Pool
    pool = Pool(X)
    preds = model.predict(pool, prediction_type="Probability")
    # CatBoost returns (n_samples, n_classes) for MultiClass
    # Classes: 0=TIMEOUT, 1=WIN, 2=DEEP_DRAWDOWN
    p_timeout = preds[:, 0]
    p_win = preds[:, 1]
    p_drawdown = preds[:, 2]

    # Ensure coherence (sum ≈ 1)
    total = p_timeout + p_win + p_drawdown
    p_win /= total
    p_drawdown /= total
    p_timeout /= total

    return p_win, p_drawdown, p_timeout


def predict_regressors(models, X):
    """Predict MFE/MAE/days-to-target values.

    Returns dict of {target_name: predictions_array}
    """
    from catboost import Pool
    results = {}
    for name, model in models.items():
        pool = Pool(X)
        results[name] = model.predict(pool)
    return results


def save_models(classifier, regressors, market, feature_stats=None):
    """Save trained models to disk."""
    classifier.save_model(_get_model_path(market, "classifier"))
    for name, model in regressors.items():
        model.save_model(_get_model_path(market, f"regressor_{name}"))
    if feature_stats is not None:
        with open(_get_feature_stats_path(market), "wb") as f:
            pickle.dump(feature_stats, f)
    logger.info(f"Saved retest models for {market}")


def load_models(market):
    """Load trained models from disk. Returns (classifier, regressors) or (None, None)."""
    clf_path = _get_model_path(market, "classifier")
    if not os.path.exists(clf_path):
        return None, {}

    from catboost import CatBoost
    classifier = CatBoost()
    classifier.load_model(clf_path)

    regressors = {}
    reg_dir = os.path.join(MODEL_DIR, market)
    for fn in os.listdir(reg_dir):
        if fn.startswith("regressor_") and fn.endswith(f"_{VERSION}.cbm"):
            name = fn.replace("regressor_", "").replace(f"_{VERSION}.cbm", "")
            model = CatBoost()
            model.load_model(os.path.join(reg_dir, fn))
            regressors[name] = model

    return classifier, regressors


def load_feature_stats(market):
    """Load feature normalization stats."""
    path = _get_feature_stats_path(market)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def is_model_available(market):
    """Check if trained models exist for a market."""
    return os.path.exists(_get_model_path(market, "classifier"))
