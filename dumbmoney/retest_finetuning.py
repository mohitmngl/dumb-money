"""Fine-tuning pipeline for retest model (PHASE 7-9).

Tries multiple hyperparameter configs, feature subsets, and threshold optimization.
"""
import logging
import json
import os
import sys
import time
from datetime import datetime
from itertools import product

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool

# Add project root
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

import dumbmoney.retest_config as cfg
from dumbmoney.retest_engine import fold_symbol, finalize_labels

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "breakout_body_atr", "breakout_close_location", "breakout_gap_atr",
    "breakout_volume_ratio", "breakout_consecutive_closes",
    "breakout_prior_close_rel", "breakout_retreat_within_3", "breakout_age_at",
    "retest_low_atr", "retest_depth_atr", "retest_touch_candles",
    "retest_closes_below_level", "retest_volume_ratio",
    "zone_prominence_atr", "zone_width_atr", "zone_reactions", "zone_false_breakouts",
    "age_band", "trend_higher_highs", "context_pivot_low_dist_atr",
    "sma20_slope_atr", "sma20_above_sma60", "median_traded_value_log",
    "entry", "signal_atr", "confirm_close_location",
    "target_atr", "stop_atr", "time_to_barrier",
]


def compute_atr_fast(high, low, close, period=14):
    n = len(close)
    if n < period + 1:
        return np.full(n, np.nan)
    prev_close = np.empty(n)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.full(n, np.nan)
    atr[period - 1] = tr[:period].mean()
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def extract_features(ev, zone_info=None):
    f = {}
    f["breakout_body_atr"] = float(ev.breakout_body_atr) if not np.isnan(ev.breakout_body_atr) else 0.0
    f["breakout_close_location"] = float(ev.breakout_close_location) if not np.isnan(ev.breakout_close_location) else 0.5
    f["breakout_gap_atr"] = float(ev.breakout_gap_atr) if not np.isnan(ev.breakout_gap_atr) else 0.0
    f["breakout_volume_ratio"] = float(ev.breakout_volume_ratio) if not np.isnan(ev.breakout_volume_ratio) else 1.0
    f["breakout_consecutive_closes"] = int(ev.breakout_consecutive_closes)
    f["breakout_prior_close_rel"] = float(ev.breakout_prior_close_rel) if not np.isnan(ev.breakout_prior_close_rel) else 0.0
    f["breakout_retreat_within_3"] = int(ev.breakout_retreat_within_3)
    f["breakout_age_at"] = float(ev.age_at_breakout)
    f["retest_low_atr"] = float(ev.retest_low_atr) if not np.isnan(ev.retest_low_atr) else 0.0
    f["retest_depth_atr"] = float(ev.retest_depth_atr) if not np.isnan(ev.retest_depth_atr) else 0.0
    f["retest_touch_candles"] = int(ev.retest_touch_candles)
    f["retest_closes_below_level"] = int(ev.retest_closes_below_level)
    f["retest_volume_ratio"] = float(ev.retest_volume_ratio) if not np.isnan(ev.retest_volume_ratio) else 1.0
    f["zone_prominence_atr"] = zone_info.get("prominence", 1.5) if zone_info else 1.5
    f["zone_width_atr"] = zone_info.get("width", 0.5) if zone_info else 0.5
    f["zone_reactions"] = zone_info.get("reactions", 0) if zone_info else 0
    f["zone_false_breakouts"] = zone_info.get("false_breakouts", 0) if zone_info else 0
    f["age_band"] = int(ev.age_band)
    f["trend_higher_highs"] = int(ev.trend_higher_highs)
    f["context_pivot_low_dist_atr"] = float(ev.context_pivot_low_dist_atr) if not np.isnan(ev.context_pivot_low_dist_atr) else 0.0
    f["sma20_slope_atr"] = float(ev.sma20_slope_atr) if not np.isnan(ev.sma20_slope_atr) else 0.0
    f["sma20_above_sma60"] = int(ev.sma20_above_sma60)
    f["median_traded_value_log"] = float(np.log1p(ev.median_traded_value)) if not np.isnan(ev.median_traded_value) else 0.0
    f["entry"] = float(ev.entry)
    f["signal_atr"] = float(ev.signal_atr)
    f["confirm_close_location"] = float(ev.confirm_close_location) if not np.isnan(ev.confirm_close_location) else 0.5
    f["target_atr"] = cfg.BARRIER_UP_ATR
    f["stop_atr"] = abs(cfg.BARRIER_DOWN_ATR)
    f["time_to_barrier"] = cfg.TIME_BARRIER
    return f


def load_training_data(max_symbols=None, db_path=None):
    """Load and prepare training data from DB."""
    import sqlite3
    if db_path is None:
        db_path = os.path.join(_project_root, "screener.db")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT DISTINCT symbol FROM stats ORDER BY symbol")
    symbols = [row[0] for row in c.fetchall()]
    if max_symbols:
        symbols = symbols[:max_symbols]

    logger.info(f"Loading {len(symbols)} symbols...")

    all_records = []
    for i, sym in enumerate(symbols):
        df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM bars "
            "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
            conn, params=(sym,)
        )
        if len(df) < 60:
            continue

        dates = df["date"].astype(str).tolist()
        o = df["open"].astype(float).values
        h = df["high"].astype(float).values
        l = df["low"].astype(float).values
        c = df["close"].astype(float).values
        v = df["volume"].astype(float).values

        try:
            result = fold_symbol(h, l, c, o, v, dates, "US", sym)
        except Exception:
            continue

        events = [e for e in result.events if e.confirm_idx >= 0 and e.signal_date]
        if not events:
            continue

        atr = compute_atr_fast(h, l, c)
        events = finalize_labels(events, h, l, c, atr)

        for ev in events:
            if ev.outcome is None:
                continue
            zone_info = None
            for z in result.zones:
                if z.id == ev.zone_id:
                    zone_info = {"prominence": z.prominence_atr, "width": z.width_atr,
                                 "reactions": z.reactions, "false_breakouts": z.false_breakouts}
                    break
            feat = extract_features(ev, zone_info)
            feat["symbol"] = sym
            feat["signal_date"] = ev.signal_date
            feat["outcome"] = ev.outcome
            feat["mfe5"] = getattr(ev, "mfe5", np.nan)
            feat["mae5"] = getattr(ev, "mae5", np.nan)
            feat["days_to_1atr"] = getattr(ev, "days_to_1atr", np.nan)
            all_records.append(feat)

        if (i + 1) % 500 == 0:
            logger.info(f"  {i+1}/{len(symbols)} symbols, {len(all_records)} events")

    conn.close()
    df = pd.DataFrame(all_records)
    logger.info(f"Total events: {len(df)}")
    return df


def prepare_splits(df, gap_days=30):
    """Create gap-enforced train/val/test split."""
    dates = pd.to_datetime(df["signal_date"], errors="coerce")
    valid = dates.dropna().sort_values()
    first_date = valid.iloc[0].date()
    last_date = valid.iloc[-1].date()
    total_days = (last_date - first_date).days

    train_end = pd.Timestamp(first_date) + pd.Timedelta(days=int(total_days * 0.70))
    val_end = pd.Timestamp(first_date) + pd.Timedelta(days=int(total_days * 0.85))
    gap = pd.Timedelta(days=gap_days)
    train_end = min(train_end + gap, val_end - gap)
    val_end = min(val_end + gap, pd.Timestamp(last_date))

    df["date_parsed"] = dates
    train_df = df[df["date_parsed"] <= train_end].copy()
    val_df = df[(df["date_parsed"] > train_end) & (df["date_parsed"] <= val_end)].copy()
    test_df = df[df["date_parsed"] > val_end].copy()
    df.drop(columns=["date_parsed"], inplace=True)

    # Filter censored
    train_df = train_df[train_df["outcome"] != cfg.OutcomeClass.TIMEOUT.value]
    val_df = val_df[val_df["outcome"] != cfg.OutcomeClass.TIMEOUT.value]
    test_df = test_df[test_df["outcome"] != cfg.OutcomeClass.TIMEOUT.value]

    return train_df, val_df, test_df, train_end, val_end


def train_and_evaluate(train_df, val_df, test_df, params, feature_cols, label="default"):
    """Train model and evaluate on test set."""
    # Prepare data
    X_train = train_df[feature_cols].fillna(train_df[feature_cols].median()).values
    y_train = (train_df["outcome"] == cfg.OutcomeClass.WIN.value).astype(int).values
    X_val = val_df[feature_cols].fillna(val_df[feature_cols].median()).values
    y_val = (val_df["outcome"] == cfg.OutcomeClass.WIN.value).astype(int).values
    X_test = test_df[feature_cols].fillna(test_df[feature_cols].median()).values
    y_test = (test_df["outcome"] == cfg.OutcomeClass.WIN.value).astype(int).values

    # Class weights
    pos = y_train.sum()
    neg = len(y_train) - pos
    spw = pos / max(1, neg)

    train_pool = Pool(X_train, y_train, feature_names=feature_cols)
    val_pool = Pool(X_val, y_val, feature_names=feature_cols)

    model = CatBoostClassifier(**params)
    model.fit(train_pool, eval_set=val_pool, use_best_model=True)

    # Evaluate
    probs = model.predict_proba(X_test)[:, 1]
    from sklearn.metrics import roc_auc_score, average_precision_score, confusion_matrix

    auc = roc_auc_score(y_test, probs)
    ap = average_precision_score(y_test, probs)

    # Find optimal threshold
    best_f1 = 0
    best_thresh = 0.5
    for thresh in np.arange(0.3, 0.7, 0.02):
        preds = (probs >= thresh).astype(int)
        tp = ((preds == 1) & (y_test == 1)).sum()
        fp = ((preds == 1) & (y_test == 0)).sum()
        fn = ((preds == 0) & (y_test == 1)).sum()
        prec = tp / max(1, tp + fp)
        rec = tp / max(1, tp + fn)
        f1 = 2 * prec * rec / max(0.001, prec + rec)
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh

    # Final metrics at optimal threshold
    preds = (probs >= best_thresh).astype(int)
    cm = confusion_matrix(y_test, preds)
    tp, fp, fn, tn = cm[1, 1], cm[0, 1], cm[1, 0], cm[0, 0]
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)

    logger.info(f"  {label}: AUC={auc:.4f}, AP={ap:.4f}, F1={best_f1:.4f} @ thresh={best_thresh:.2f}")
    logger.info(f"    Precision={precision:.4f}, Recall={recall:.4f}, Acc={(tp+tn)/len(y_test):.4f}")
    logger.info(f"    CM={cm.tolist()}")

    return {
        "params": params,
        "features": feature_cols,
        "auc": auc,
        "average_precision": ap,
        "best_threshold": best_thresh,
        "best_f1": best_f1,
        "precision": precision,
        "recall": recall,
        "accuracy": (tp + tn) / len(y_test),
        "confusion_matrix": cm.tolist(),
        "n_iterations": model.tree_count_,
    }


def run_finetuning(max_symbols=500, db_path=None):
    """Run hyperparameter tuning."""
    start = time.time()

    # Load data
    logger.info("Loading training data...")
    df = load_training_data(max_symbols=max_symbols, db_path=db_path)
    if df is None or len(df) == 0:
        logger.error("No data!")
        return None

    train_df, val_df, test_df, train_end, val_end = prepare_splits(df)
    logger.info(f"Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

    # Define hyperparameter grid
    param_grids = [
        {"loss_function": "Logloss", "eval_metric": "AUC", "random_seed": 42,
         "od_type": "Iter", "od_wait": 20, "verbose": 50},
        {"max_depth": 4, "learning_rate": 0.03, "n_estimators": 1000,
         "bootstrap_type": "Bayesian", "colsample_bylevel": 0.8, "bagging_temperature": 0.5},
        {"max_depth": 5, "learning_rate": 0.03, "n_estimators": 1000,
         "bootstrap_type": "Bayesian", "colsample_bylevel": 0.8, "bagging_temperature": 0.5},
        {"max_depth": 6, "learning_rate": 0.03, "n_estimators": 1000,
         "bootstrap_type": "Bayesian", "colsample_bylevel": 0.8, "bagging_temperature": 0.5},
        {"max_depth": 7, "learning_rate": 0.03, "n_estimators": 1000,
         "bootstrap_type": "Bayesian", "colsample_bylevel": 0.8, "bagging_temperature": 0.5},
    ]

    results = []

    # Test different feature subsets
    feature_configs = [
        ("all_features", FEATURE_COLUMNS),
        ("core_features", [c for c in FEATURE_COLUMNS if c not in ["target_atr", "stop_atr", "time_to_barrier"]]),
        ("engine_features", [c for c in FEATURE_COLUMNS if c not in ["entry", "signal_atr", "target_atr", "stop_atr", "time_to_barrier"]]),
    ]

    for feat_name, feat_cols in feature_configs:
        logger.info(f"\n=== Testing: {feat_name} ===")
        for depth in [4, 5, 6, 7]:
            params = {
                "loss_function": "Logloss",
                "eval_metric": "AUC",
                "random_seed": 42,
                "od_type": "Iter",
                "od_wait": 20,
                "verbose": 50,
                "max_depth": depth,
                "learning_rate": 0.03,
                "n_estimators": 1000,
                "bootstrap_type": "Bayesian",
                "colsample_bylevel": 0.8,
                "bagging_temperature": 0.5,
            }
            label = f"{feat_name}_depth{depth}"
            result = train_and_evaluate(train_df, val_df, test_df, params, feat_cols, label)
            result["config_name"] = label
            results.append(result)

    # Find best config
    best = max(results, key=lambda x: x["auc"])
    logger.info(f"\n=== BEST CONFIG ===")
    logger.info(f"Features: {best['config_name']}")
    logger.info(f"AUC: {best['auc']:.4f}, AP: {best['average_precision']:.4f}")
    logger.info(f"Threshold: {best['best_threshold']:.2f}, F1: {best['best_f1']:.4f}")

    elapsed = time.time() - start
    logger.info(f"Total tuning time: {elapsed/60:.1f} minutes")

    return {
        "best_config": best,
        "all_results": results,
        "train_size": len(train_df),
        "val_size": len(val_df),
        "test_size": len(test_df),
        "train_end": str(train_end),
        "val_end": str(val_end),
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-symbols", type=int, default=500)
    parser.add_argument("--db", type=str, default=None)
    args = parser.parse_args()

    base = _project_root
    db_path = args.db or os.path.join(base, "screener.db")
    result = run_finetuning(max_symbols=args.max_symbols, db_path=db_path)

    if result:
        out_dir = os.path.join(base, "models", "retest_v1")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "finetuning_results.json"), "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(f"Results saved to {out_dir}/finetuning_results.json")
