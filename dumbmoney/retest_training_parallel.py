"""Optimized full training pipeline using multiprocessing."""
import logging
import time
import os
import sys
import sqlite3
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
import numpy as np

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

import dumbmoney.retest_config as cfg
from dumbmoney.retest_engine import fold_symbol, finalize_labels
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import roc_auc_score, average_precision_score, confusion_matrix, precision_recall_curve

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


def process_single_symbol(args):
    """Process a single symbol and return events."""
    symbol, market, db_path = args
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM bars "
            "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
            conn, params=(symbol,)
        )
        conn.close()

        if len(df) < 60:
            return []

        dates = df["date"].astype(str).tolist()
        o = df["open"].astype(float).values
        h = df["high"].astype(float).values
        l = df["low"].astype(float).values
        c = df["close"].astype(float).values
        v = df["volume"].astype(float).values

        result = fold_symbol(h, l, c, o, v, dates, market, symbol)
        events = [e for e in result.events if e.confirm_idx >= 0 and e.signal_date]
        if not events:
            return []

        atr = compute_atr_fast(h, l, c)
        events = finalize_labels(events, h, l, c, atr)

        records = []
        for ev in events:
            if ev.outcome is None:
                continue

            zone_info = None
            for z in result.zones:
                if z.id == ev.zone_id:
                    zone_info = {
                        "prominence": z.prominence_atr,
                        "width": z.width_atr,
                        "reactions": z.reactions,
                        "false_breakouts": z.false_breakouts,
                    }
                    break

            feat = {}
            feat["breakout_body_atr"] = float(ev.breakout_body_atr) if not np.isnan(ev.breakout_body_atr) else 0.0
            feat["breakout_close_location"] = float(ev.breakout_close_location) if not np.isnan(ev.breakout_close_location) else 0.5
            feat["breakout_gap_atr"] = float(ev.breakout_gap_atr) if not np.isnan(ev.breakout_gap_atr) else 0.0
            feat["breakout_volume_ratio"] = float(ev.breakout_volume_ratio) if not np.isnan(ev.breakout_volume_ratio) else 1.0
            feat["breakout_consecutive_closes"] = int(ev.breakout_consecutive_closes)
            feat["breakout_prior_close_rel"] = float(ev.breakout_prior_close_rel) if not np.isnan(ev.breakout_prior_close_rel) else 0.0
            feat["breakout_retreat_within_3"] = int(ev.breakout_retreat_within_3)
            feat["breakout_age_at"] = float(ev.age_at_breakout)
            feat["retest_low_atr"] = float(ev.retest_low_atr) if not np.isnan(ev.retest_low_atr) else 0.0
            feat["retest_depth_atr"] = float(ev.retest_depth_atr) if not np.isnan(ev.retest_depth_atr) else 0.0
            feat["retest_touch_candles"] = int(ev.retest_touch_candles)
            feat["retest_closes_below_level"] = int(ev.retest_closes_below_level)
            feat["retest_volume_ratio"] = float(ev.retest_volume_ratio) if not np.isnan(ev.retest_volume_ratio) else 1.0
            feat["zone_prominence_atr"] = zone_info.get("prominence", 1.5) if zone_info else 1.5
            feat["zone_width_atr"] = zone_info.get("width", 0.5) if zone_info else 0.5
            feat["zone_reactions"] = zone_info.get("reactions", 0) if zone_info else 0
            feat["zone_false_breakouts"] = zone_info.get("false_breakouts", 0) if zone_info else 0
            feat["age_band"] = int(ev.age_band)
            feat["trend_higher_highs"] = int(ev.trend_higher_highs)
            feat["context_pivot_low_dist_atr"] = float(ev.context_pivot_low_dist_atr) if not np.isnan(ev.context_pivot_low_dist_atr) else 0.0
            feat["sma20_slope_atr"] = float(ev.sma20_slope_atr) if not np.isnan(ev.sma20_slope_atr) else 0.0
            feat["sma20_above_sma60"] = int(ev.sma20_above_sma60)
            feat["median_traded_value_log"] = float(np.log1p(ev.median_traded_value)) if not np.isnan(ev.median_traded_value) else 0.0
            feat["entry"] = float(ev.entry)
            feat["signal_atr"] = float(ev.signal_atr)
            feat["confirm_close_location"] = float(ev.confirm_close_location) if not np.isnan(ev.confirm_close_location) else 0.5
            feat["target_atr"] = cfg.BARRIER_UP_ATR
            feat["stop_atr"] = abs(cfg.BARRIER_DOWN_ATR)
            feat["time_to_barrier"] = cfg.TIME_BARRIER
            feat["symbol"] = symbol
            feat["signal_date"] = ev.signal_date
            feat["outcome"] = ev.outcome
            feat["mfe5"] = getattr(ev, "mfe5", np.nan)
            feat["mae5"] = getattr(ev, "mae5", np.nan)
            feat["mfe10"] = getattr(ev, "mfe10", np.nan)
            feat["mae10"] = getattr(ev, "mae10", np.nan)
            feat["mfe20"] = getattr(ev, "mfe20", np.nan)
            feat["mae20"] = getattr(ev, "mae20", np.nan)
            feat["days_to_1atr"] = getattr(ev, "days_to_1atr", np.nan)

            records.append(feat)

        return records
    except Exception as e:
        logger.warning(f"Error processing {symbol}: {e}")
        return []


def run_full_training(db_path, market="US", max_symbols=None, n_workers=4):
    """Run training with multiprocessing."""
    import json
    from datetime import datetime
    from sklearn.metrics import classification_report

    # Get symbols
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT DISTINCT symbol FROM stats ORDER BY symbol")
    symbols = [row[0] for row in c.fetchall()]
    conn.close()

    if max_symbols:
        symbols = symbols[:max_symbols]

    logger.info(f"Processing {len(symbols)} symbols with {n_workers} workers")

    # Process in parallel
    all_records = []
    args_list = [(sym, market, db_path) for sym in symbols]

    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(process_single_symbol, args): args[0] for args in args_list}
        completed = 0
        for future in as_completed(futures):
            records = future.result()
            all_records.extend(records)
            completed += 1
            if completed % 100 == 0:
                logger.info(f"  Progress: {completed}/{len(symbols)}, events: {len(all_records)}")

    if not all_records:
        logger.error("No events found!")
        return None

    df = pd.DataFrame(all_records)
    logger.info(f"Total events: {len(df)}")
    logger.info(f"Outcome distribution:\n{df['outcome'].value_counts()}")

    # Prepare labels
    OUTCOME_MAP = {cfg.OutcomeClass.WIN.value: 1, cfg.OutcomeClass.DEEP_DRAWDOWN.value: 0, cfg.OutcomeClass.TIMEOUT.value: -1}
    df["label"] = df["outcome"].map(OUTCOME_MAP)

    # Split with gap
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

    logger.info(f"Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

    # Class weights
    pos = (train_df["label"] == 1).sum()
    neg = (train_df["label"] == 0).sum()
    pos_weight = min((pos + neg) / (2 * pos), 5.0) if pos > 0 else 1.0
    neg_weight = min((pos + neg) / (2 * neg), 5.0) if neg > 0 else 1.0

    # Train model
    logger.info("Training CatBoost model...")
    train_df_filtered = train_df[train_df["label"] >= 0].copy()
    val_df_filtered = val_df[val_df["label"] >= 0].copy()

    train_X = train_df_filtered[FEATURE_COLUMNS].fillna(train_df_filtered[FEATURE_COLUMNS].median()).values
    train_y = train_df_filtered["label"].values
    val_X = val_df_filtered[FEATURE_COLUMNS].fillna(val_df_filtered[FEATURE_COLUMNS].median()).values
    val_y = val_df_filtered["label"].values

    train_pool = Pool(train_X, train_y, feature_names=FEATURE_COLUMNS)
    val_pool = Pool(val_X, val_y, feature_names=FEATURE_COLUMNS)

    params = {
        "loss_function": "Logloss",
        "eval_metric": "AUC",
        "verbose": 50,
        "random_seed": 42,
        "od_type": "Iter",
        "od_wait": 20,
        "max_depth": 6,
        "learning_rate": 0.03,
        "n_estimators": 1000,
        "bootstrap_type": "Bayesian",
        "colsample_bylevel": 0.8,
        "bagging_temperature": 0.5,
        "scale_pos_weight": pos_weight / neg_weight if neg_weight > 0 else 1.0,
    }

    model = CatBoostClassifier(**params)
    model.fit(train_pool, eval_set=val_pool, use_best_model=True)

    # Evaluate
    test_df_filtered = test_df[test_df["label"] >= 0].copy()
    test_X = test_df_filtered[FEATURE_COLUMNS].fillna(test_df_filtered[FEATURE_COLUMNS].median()).values
    test_y = test_df_filtered["label"].values

    probs = model.predict_proba(test_X)[:, 1]
    auc = roc_auc_score(test_y, probs)
    ap = average_precision_score(test_y, probs)
    cm = confusion_matrix(test_y, (probs >= 0.5).astype(int))

    logger.info(f"Test AUC: {auc:.4f}")
    logger.info(f"Test AP: {ap:.4f}")
    logger.info(f"Confusion matrix:\n{cm}")

    # Save
    output_dir = os.path.join(os.path.dirname(__file__), "..", "models", "retest_v1")
    os.makedirs(output_dir, exist_ok=True)
    model.save_model(os.path.join(output_dir, "model.cbm"))

    metadata = {
        "market": market,
        "total_events": len(df),
        "train_size": len(train_df),
        "val_size": len(val_df),
        "test_size": len(test_df),
        "train_end_date": str(train_end),
        "val_end_date": str(val_end),
        "class_weights": {"pos": pos_weight, "neg": neg_weight},
        "feature_columns": FEATURE_COLUMNS,
        "test_results": {"auc": auc, "average_precision": ap, "confusion_matrix": cm.tolist()},
        "outcome_distribution": df["outcome"].value_counts().to_dict(),
        "label_distribution": df["label"].value_counts().to_dict(),
        "timestamp": datetime.utcnow().isoformat(),
    }

    with open(os.path.join(output_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    return {"model": model, "metadata": metadata}


if __name__ == "__main__":
    base = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt"
    db_path = os.path.join(base, "screener.db")
    start = time.time()
    result = run_full_training(db_path, market="US", max_symbols=None, n_workers=4)
    elapsed = time.time() - start
    print(f"\nFull training done in {elapsed/60:.1f} minutes")
    if result:
        print(f"Test AUC: {result['metadata']['test_results']['auc']:.4f}")
        print(f"Test AP: {result['metadata']['test_results']['average_precision']:.4f}")
