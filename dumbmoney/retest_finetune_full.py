"""Full fine-tuning on all data with aggressive hyperparameter search."""
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
from sklearn.metrics import roc_auc_score, average_precision_score, confusion_matrix

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


def load_data(db_path, max_symbols=None):
    import sqlite3
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
        close = df["close"].astype(float).values
        v = df["volume"].astype(float).values

        try:
            result = fold_symbol(h, l, close, o, v, dates, "US", sym)
        except Exception:
            continue

        events = [e for e in result.events if e.confirm_idx >= 0 and e.signal_date]
        if not events:
            continue

        atr = compute_atr_fast(h, l, close)
        events = finalize_labels(events, h, l, close, atr)

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
            all_records.append(feat)

        if (i + 1) % 500 == 0:
            logger.info(f"  {i+1}/{len(symbols)} symbols, {len(all_records)} events")

    conn.close()
    df = pd.DataFrame(all_records)
    logger.info(f"Total events: {len(df)}")
    return df


def prepare_splits(df):
    dates = pd.to_datetime(df["signal_date"], errors="coerce")
    valid = dates.dropna().sort_values()
    first_date = valid.iloc[0].date()
    last_date = valid.iloc[-1].date()
    total_days = (last_date - first_date).days

    train_end = pd.Timestamp(first_date) + pd.Timedelta(days=int(total_days * 0.70))
    val_end = pd.Timestamp(first_date) + pd.Timedelta(days=int(total_days * 0.85))
    gap = pd.Timedelta(days=30)
    train_end = min(train_end + gap, val_end - gap)
    val_end = min(val_end + gap, pd.Timestamp(last_date))

    df["date_parsed"] = dates
    train_df = df[df["date_parsed"] <= train_end].copy()
    val_df = df[(df["date_parsed"] > train_end) & (df["date_parsed"] <= val_end)].copy()
    test_df = df[df["date_parsed"] > val_end].copy()
    df.drop(columns=["date_parsed"], inplace=True)

    # Filter TIMEOUT
    for df in [train_df, val_df, test_df]:
        df = df[df["outcome"] != cfg.OutcomeClass.TIMEOUT.value]

    return train_df, val_df, test_df, train_end, val_end


def train_eval(train_df, val_df, test_df, params, feat_cols, label=""):
    X_train = train_df[feat_cols].fillna(train_df[feat_cols].median()).values
    y_train = (train_df["outcome"] == cfg.OutcomeClass.WIN.value).astype(int).values
    X_val = val_df[feat_cols].fillna(val_df[feat_cols].median()).values
    y_val = (val_df["outcome"] == cfg.OutcomeClass.WIN.value).astype(int).values
    X_test = test_df[feat_cols].fillna(test_df[feat_cols].median()).values
    y_test = (test_df["outcome"] == cfg.OutcomeClass.WIN.value).astype(int).values

    pos = y_train.sum()
    neg = len(y_train) - pos
    spw = pos / max(1, neg)

    train_pool = Pool(X_train, y_train, feature_names=feat_cols)
    val_pool = Pool(X_val, y_val, feature_names=feat_cols)

    model = CatBoostClassifier(**params)
    model.fit(train_pool, eval_set=val_pool, use_best_model=True)

    probs = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, probs)
    ap = average_precision_score(y_test, probs)

    # Optimize threshold
    best_f1, best_thresh = 0, 0.5
    for thresh in np.arange(0.2, 0.8, 0.02):
        preds = (probs >= thresh).astype(int)
        tp = ((preds == 1) & (y_test == 1)).sum()
        fp = ((preds == 1) & (y_test == 0)).sum()
        fn = ((preds == 0) & (y_test == 1)).sum()
        prec = tp / max(1, tp + fp)
        rec = tp / max(1, tp + fn)
        f1 = 2 * prec * rec / max(0.001, prec + rec)
        if f1 > best_f1:
            best_f1, best_thresh = f1, thresh

    preds = (probs >= best_thresh).astype(int)
    cm = confusion_matrix(y_test, preds)
    tp, fp, fn, tn = cm[1, 1], cm[0, 1], cm[1, 0], cm[0, 0]
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)

    logger.info(f"  {label}: AUC={auc:.4f}, AP={ap:.4f}, F1={best_f1:.4f} @ t={best_thresh:.2f}, P={precision:.3f}, R={recall:.3f}")
    return {"params": params, "label": label, "auc": auc, "ap": ap, "f1": best_f1,
            "threshold": best_thresh, "precision": precision, "recall": recall,
            "cm": cm.tolist(), "n_iters": model.tree_count_}


def run_full_finetune(db_path, n_iterations=20, max_symbols=None):
    """Run hyperparameter search with random sampling."""
    start = time.time()

    logger.info("Loading data...")
    df = load_data(db_path, max_symbols=max_symbols)
    if df is None or len(df) == 0:
        return None

    train_df, val_df, test_df, train_end, val_end = prepare_splits(df)
    logger.info(f"Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

    # Define search space
    param_configs = [
        {"loss_function": "Logloss", "eval_metric": "AUC", "random_seed": 42,
         "od_type": "Iter", "od_wait": 20, "verbose": 0},
    ]

    depth_options = [4, 5, 6, 7]
    lr_options = [0.01, 0.03, 0.05]
    subsample_options = [0.6, 0.7, 0.8, 0.9]
    colsample_options = [0.6, 0.7, 0.8, 0.9]

    results = []

    logger.info("Starting hyperparameter search...")
    import random
    random.seed(42)

    for i in range(n_iterations):
        depth = random.choice(depth_options)
        lr = random.choice(lr_options)
        subsample = random.choice(subsample_options)
        colsample = random.choice(colsample_options)
        n_est = random.choice([500, 800, 1000, 1500])

        params = {
            **param_configs[0],
            "max_depth": depth,
            "learning_rate": lr,
            "n_estimators": n_est,
            "bootstrap_type": "Bayesian",
            "colsample_bylevel": colsample,
            "bagging_temperature": 0.5,
        }

        label = f"iter{i+1}:d{depth}_lr{lr}_sub{subsample}_col{colsample}"
        result = train_eval(train_df, val_df, test_df, params, FEATURE_COLUMNS, label)
        results.append(result)

        # Track best
        best_so_far = max(results, key=lambda x: x["auc"])
        logger.info(f"  Best so far: AUC={best_so_far['auc']:.4f} ({best_so_far['label']})")

    elapsed = time.time() - start
    logger.info(f"\nTotal time: {elapsed/60:.1f} minutes")

    # Find best
    best = max(results, key=lambda x: x["auc"])
    logger.info(f"\n=== BEST CONFIG ===")
    logger.info(f"Label: {best['label']}")
    logger.info(f"AUC: {best['auc']:.4f}, AP: {best['ap']:.4f}")
    logger.info(f"F1: {best['f1']:.4f}, Threshold: {best['threshold']:.2f}")
    logger.info(f"Precision: {best['precision']:.4f}, Recall: {best['recall']:.4f}")

    return {
        "best": best,
        "all_results": results,
        "train_size": len(train_df),
        "val_size": len(val_df),
        "test_size": len(test_df),
        "elapsed_minutes": elapsed / 60,
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--db", type=str, default=None)
    args = parser.parse_args()

    base = _project_root
    db_path = args.db or os.path.join(base, "screener.db")
    result = run_full_finetune(db_path, n_iterations=args.iterations, max_symbols=getattr(args, 'max_symbols', None))

    if result:
        out_dir = os.path.join(base, "models", "retest_v1")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "finetuning_full.json"), "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(f"Results saved to {out_dir}/finetuning_full.json")
