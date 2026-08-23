"""Training pipeline for OLD_SWING_RETEST_SCORE.

PHASE 4-6: Feature engineering, train/val/test split with gap enforcement,
and catboost model training using full historical data.
"""
from __future__ import annotations

import os
import sqlite3
import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score,
    precision_recall_curve, average_precision_score
)

import dumbmoney.retest_config as cfg
from dumbmoney.retest_engine import (
    fold_symbol, fold_symbol_frame, finalize_labels, current_status
)

logger = logging.getLogger(__name__)


# ==============================================================================
# FEATURE EXTRACTION
# ==============================================================================

@dataclass
class RetestFeature:
    """Feature vector for one confirmed retest event."""
    # Breakout features
    breakout_body_atr: float = 0.0
    breakout_close_location: float = 0.5
    breakout_gap_atr: float = 0.0
    breakout_volume_ratio: float = 1.0
    breakout_consecutive_closes: int = 0
    breakout_prior_close_rel: float = 0.0
    breakout_retreat_within_3: int = 0
    breakout_age_at: float = 0.0

    # Retest features
    retest_low_atr: float = 0.0
    retest_depth_atr: float = 0.0
    retest_touch_candles: int = 0
    retest_closes_below_level: int = 0
    retest_volume_ratio: float = 1.0

    # Zone features
    zone_prominence_atr: float = 1.5
    zone_width_atr: float = 0.5
    zone_reactions: int = 0
    zone_false_breakouts: int = 0

    # Age / context
    age_band: int = 0
    trend_higher_highs: int = 0
    context_pivot_low_dist_atr: float = 0.0
    sma20_slope_atr: float = 0.0
    sma20_above_sma60: int = 0
    median_traded_value_log: float = 0.0

    # Signal features
    entry: float = 0.0
    signal_atr: float = 0.0
    confirm_close_location: float = 0.5

    # Target/stop levels (in ATR units from entry)
    target_atr: float = cfg.BARRIER_UP_ATR
    stop_atr: float = abs(cfg.BARRIER_DOWN_ATR)
    time_to_barrier: int = cfg.TIME_BARRIER


def extract_features_from_event(event, h, l, c, dates=None):
    """Extract feature vector from a confirmed event cycle."""
    if event.confirm_idx < 0 or not event.signal_date:
        return None
    if np.isnan(event.entry) or np.isnan(event.signal_atr) or event.signal_atr <= 0:
        return None

    f = RetestFeature()

    # Breakout features
    f.breakout_body_atr = float(event.breakout_body_atr) if not np.isnan(event.breakout_body_atr) else 0.0
    f.breakout_close_location = float(event.breakout_close_location) if not np.isnan(event.breakout_close_location) else 0.5
    f.breakout_gap_atr = float(event.breakout_gap_atr) if not np.isnan(event.breakout_gap_atr) else 0.0
    f.breakout_volume_ratio = float(event.breakout_volume_ratio) if not np.isnan(event.breakout_volume_ratio) else 1.0
    f.breakout_consecutive_closes = int(event.breakout_consecutive_closes)
    f.breakout_prior_close_rel = float(event.breakout_prior_close_rel) if not np.isnan(event.breakout_prior_close_rel) else 0.0
    f.breakout_retreat_within_3 = int(event.breakout_retreat_within_3)
    f.breakout_age_at = float(event.age_at_breakout)

    # Retest features
    f.retest_low_atr = float(event.retest_low_atr) if not np.isnan(event.retest_low_atr) else 0.0
    f.retest_depth_atr = float(event.retest_depth_atr) if not np.isnan(event.retest_depth_atr) else 0.0
    f.retest_touch_candles = int(event.retest_touch_candles)
    f.retest_closes_below_level = int(event.retest_closes_below_level)
    f.retest_volume_ratio = float(event.retest_volume_ratio) if not np.isnan(event.retest_volume_ratio) else 1.0

    # We need zone info - it's in the engine state, not the event
    # For now, use defaults; zone features filled from engine later
    f.zone_prominence_atr = 1.5
    f.zone_width_atr = 0.5
    f.zone_reactions = 0
    f.zone_false_breakouts = 0

    # Age / context
    f.age_band = int(event.age_band)
    f.trend_higher_highs = int(event.trend_higher_highs)
    f.context_pivot_low_dist_atr = float(event.context_pivot_low_dist_atr) if not np.isnan(event.context_pivot_low_dist_atr) else 0.0
    f.sma20_slope_atr = float(event.sma20_slope_atr) if not np.isnan(event.sma20_slope_atr) else 0.0
    f.sma20_above_sma60 = int(event.sma20_above_sma60)
    f.median_traded_value_log = float(np.log1p(event.median_traded_value)) if not np.isnan(event.median_traded_value) else 0.0

    # Signal features
    f.entry = float(event.entry)
    f.signal_atr = float(event.signal_atr)
    f.confirm_close_location = float(event.confirm_close_location) if not np.isnan(event.confirm_close_location) else 0.5

    # Target/stop levels
    f.target_atr = cfg.BARRIER_UP_ATR  # 2.0
    f.stop_atr = abs(cfg.BARRIER_DOWN_ATR)  # 0.75
    f.time_to_barrier = cfg.TIME_BARRIER  # 20

    return f


def event_to_feature_dict(event, zone_info: Optional[dict] = None):
    """Convert event to feature dict with optional zone overrides."""
    f = extract_features_from_event(event, None, None, None)
    if f is None:
        return None

    d = {}
    d["breakout_body_atr"] = f.breakout_body_atr
    d["breakout_close_location"] = f.breakout_close_location
    d["breakout_gap_atr"] = f.breakout_gap_atr
    d["breakout_volume_ratio"] = f.breakout_volume_ratio
    d["breakout_consecutive_closes"] = f.breakout_consecutive_closes
    d["breakout_prior_close_rel"] = f.breakout_prior_close_rel
    d["breakout_retreat_within_3"] = f.breakout_retreat_within_3
    d["breakout_age_at"] = f.breakout_age_at
    d["retest_low_atr"] = f.retest_low_atr
    d["retest_depth_atr"] = f.retest_depth_atr
    d["retest_touch_candles"] = f.retest_touch_candles
    d["retest_closes_below_level"] = f.retest_closes_below_level
    d["retest_volume_ratio"] = f.retest_volume_ratio
    d["zone_prominence_atr"] = zone_info.get("prominence", 1.5) if zone_info else 1.5
    d["zone_width_atr"] = zone_info.get("width", 0.5) if zone_info else 0.5
    d["zone_reactions"] = zone_info.get("reactions", 0) if zone_info else 0
    d["zone_false_breakouts"] = zone_info.get("false_breakouts", 0) if zone_info else 0
    d["age_band"] = f.age_band
    d["trend_higher_highs"] = f.trend_higher_highs
    d["context_pivot_low_dist_atr"] = f.context_pivot_low_dist_atr
    d["sma20_slope_atr"] = f.sma20_slope_atr
    d["sma20_above_sma60"] = f.sma20_above_sma60
    d["median_traded_value_log"] = f.median_traded_value_log
    d["entry"] = f.entry
    d["signal_atr"] = f.signal_atr
    d["confirm_close_location"] = f.confirm_close_location
    d["target_atr"] = f.target_atr
    d["stop_atr"] = f.stop_atr
    d["time_to_barrier"] = f.time_to_barrier

    return d


# ==============================================================================
# DATA EXTRACTION FROM DB
# ==============================================================================

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

LABEL_COLUMNS = ["outcome", "mfe5", "mae5", "mfe10", "mae10", "mfe20", "mae20", "days_to_1atr"]


def get_symbol_bars(conn, symbol, timeframe="1Day"):
    """Get OHLCV bars for a symbol."""
    df = pd.read_sql(
        f"SELECT date, open, high, low, close, volume FROM bars "
        f"WHERE timeframe=? AND symbol=? ORDER BY date",
        conn, params=(timeframe, symbol)
    )
    if len(df) < 60:
        return None
    return df


def process_symbol_for_training(df, market, symbol):
    """Process a single symbol's bars and return labeled events."""
    dates = df["date"].astype(str).tolist()
    o = df["open"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    v = df["volume"].astype(float).values

    try:
        result = fold_symbol(h, l, c, o, v, dates, market, symbol)
    except Exception as e:
        logger.warning(f"Failed to fold {symbol}: {e}")
        return []

    # Extract confirmed events
    events = [e for e in result.events if e.confirm_idx >= 0 and e.signal_date]
    if not events:
        return []

    # Get ATR for labeling
    atr = _compute_atr_fast(h, l, c)

    # Finalize labels
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

        feat = event_to_feature_dict(ev, zone_info)
        if feat is None:
            continue

        feat["symbol"] = symbol
        feat["market"] = market
        feat["signal_date"] = ev.signal_date
        feat["confirm_idx"] = ev.confirm_idx
        feat["resolution_date"] = ev.resolution_date
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


def _compute_atr_fast(high, low, close, period=14):
    """Compute ATR using numpy (faster than pandas for bulk)."""
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


def extract_training_data(market, conn, min_bars=100, max_symbols=None):
    """Extract all labeled events from the database for training."""
    c = conn.cursor()
    c.execute("SELECT DISTINCT symbol FROM stats ORDER BY symbol")
    symbols = [row[0] for row in c.fetchall()]

    if max_symbols:
        symbols = symbols[:max_symbols]

    all_records = []
    total = len(symbols)
    processed = 0

    logger.info(f"Extracting training data from {market}: {total} symbols")

    for sym in symbols:
        df = get_symbol_bars(conn, sym)
        if df is None:
            continue
        records = process_symbol_for_training(df, market, sym)
        all_records.extend(records)
        processed += 1
        if processed % 100 == 0:
            logger.info(f"  Processed {processed}/{total} symbols, {len(all_records)} events so far")

    if not all_records:
        logger.error("No training events found!")
        return None

    df = pd.DataFrame(all_records)
    logger.info(f"Total events extracted: {len(df)}")
    return df


# ==============================================================================
# GAP-ENFORCED SPLIT
# ==============================================================================

def compute_dates_for_split(df, gap_days=30):
    """Compute train/validation/test split dates with gap enforcement."""
    dates = pd.to_datetime(df["signal_date"], errors="coerce")
    valid = dates.dropna().sort_values()
    if len(valid) < 100:
        return None, None, None

    n = len(valid)
    # Use calendar days for gap, not trading days
    first_date = valid.iloc[0].date()
    last_date = valid.iloc[-1].date()
    total_days = (last_date - first_date).days

    # 70% train, 15% val, 15% test with gap
    train_end = pd.Timestamp(first_date) + pd.Timedelta(days=int(total_days * 0.70))
    val_end = pd.Timestamp(first_date) + pd.Timedelta(days=int(total_days * 0.85))

    # Apply gap
    gap = pd.Timedelta(days=gap_days)
    train_end = min(train_end + gap, val_end - gap)
    val_end = min(val_end + gap, pd.Timestamp(last_date))

    return train_end, val_end, pd.Timestamp(last_date)


def split_data(df, train_end, val_end):
    """Split dataframe into train/val/test with gap enforcement."""
    dates = pd.to_datetime(df["signal_date"], errors="coerce")
    df["date_parsed"] = dates

    train = df[df["date_parsed"] <= train_end].copy()
    val = df[(df["date_parsed"] > train_end) & (df["date_parsed"] <= val_end)].copy()
    test = df[df["date_parsed"] > val_end].copy()

    df.drop(columns=["date_parsed"], inplace=True, errors="ignore")

    return train, val, test


# ==============================================================================
# LABEL PROCESSING
# ==============================================================================

OUTCOME_MAP = {
    cfg.OutcomeClass.WIN.value: 1,
    cfg.OutcomeClass.DEEP_DRAWDOWN.value: 0,
    cfg.OutcomeClass.TIMEOUT.value: -1,  # censored
}


def prepare_labels(df):
    """Prepare binary labels (1=WIN, 0=NOT_WIN, -1=censored)."""
    df["label"] = df["outcome"].map(OUTCOME_MAP)
    return df


def get_class_weights(df):
    """Compute class weights for imbalanced training."""
    pos = (df["label"] == 1).sum()
    neg = (df["label"] == 0).sum()
    cens = (df["label"] == -1).sum()
    total = pos + neg
    if total == 0:
        return {"pos": 1.0, "neg": 1.0}
    # Upweight positive class
    pos_weight = total / (2 * pos) if pos > 0 else 1.0
    neg_weight = total / (2 * neg) if neg > 0 else 1.0
    return {"pos": min(pos_weight, 5.0), "neg": min(neg_weight, 5.0)}


# ==============================================================================
# MODEL TRAINING
# ==============================================================================

def train_model(train_df, val_df, feature_cols, class_weights):
    """Train a CatBoost classifier."""
    # Filter out censored samples (-1)
    train_df = train_df[train_df["label"] >= 0].copy()
    val_df = val_df[val_df["label"] >= 0].copy()

    train_X = train_df[feature_cols].fillna(train_df[feature_cols].median()).values
    train_y = train_df["label"].values

    val_X = val_df[feature_cols].fillna(val_df[feature_cols].median()).values
    val_y = val_df["label"].values

    # Prepare CatBoost data
    train_pool = Pool(train_X, train_y, feature_names=feature_cols)
    val_pool = Pool(val_X, val_y, feature_names=feature_cols)

    # CatBoost params
    params = {
        "loss_function": "Logloss",
        "eval_metric": "AUC",
        "metric_period": 10,
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
        "scale_pos_weight": class_weights["pos"] / class_weights["neg"] if class_weights["neg"] > 0 else 1.0,
    }

    model = CatBoostClassifier(**params)
    model.fit(
        train_pool,
        eval_set=val_pool,
        use_best_model=True,
    )

    return model


def evaluate_model(model, test_df, feature_cols):
    """Evaluate model on test set."""
    # Filter out censored samples for evaluation
    test_df = test_df[test_df["label"] >= 0].copy()
    test_X = test_df[feature_cols].fillna(test_df[feature_cols].median()).values
    test_y = test_df["label"].values

    if len(test_y) == 0:
        return {}

    probs = model.predict_proba(test_X)[:, 1]

    results = {
        "test_samples": len(test_y),
        "auc": roc_auc_score(test_y, probs),
        "average_precision": average_precision_score(test_y, probs),
    }

    # Classification report for threshold=0.5
    preds = (probs >= 0.5).astype(int)
    results["precision"] = precision_recall_curve(test_y, probs)[1][-1] if len(probs) > 0 else 0
    results["recall"] = (preds == 1).sum() / max(1, (test_y == 1).sum())

    # Confusion matrix
    cm = confusion_matrix(test_y, preds)
    results["confusion_matrix"] = cm.tolist()

    return results


# ==============================================================================
# MAIN PIPELINE
# ==============================================================================

def run_training_pipeline(market="US", output_dir=None, max_symbols=None):
    """Run the full training pipeline."""
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "..", "models", "retest_v1")
    os.makedirs(output_dir, exist_ok=True)

    # Connect to DB
    db_path = os.path.join(os.path.dirname(__file__), "..", f"{market.lower()}.db")
    if market == "US":
        db_path = os.path.join(os.path.dirname(__file__), "..", "screener.db")
    elif market == "INDIA":
        db_path = os.path.join(os.path.dirname(__file__), "..", "india.db")

    if not os.path.exists(db_path):
        logger.error(f"DB not found: {db_path}")
        return None

    conn = sqlite3.connect(db_path)
    logger.info(f"Connected to {db_path}")

    # Step 1: Extract training data
    logger.info("Step 1: Extracting training data...")
    df = extract_training_data(market, conn, min_bars=100, max_symbols=max_symbols)
    conn.close()

    if df is None or len(df) == 0:
        logger.error("No training data extracted!")
        return None

    logger.info(f"Total events: {len(df)}")
    logger.info(f"Outcome distribution:\n{df['outcome'].value_counts()}")

    # Step 2: Prepare labels
    logger.info("Step 2: Preparing labels...")
    df = prepare_labels(df)
    logger.info(f"Label distribution:\n{df['label'].value_counts()}")

    # Step 3: Split with gap enforcement
    logger.info("Step 3: Computing gap-enforced split...")
    train_end, val_end, test_end = compute_dates_for_split(df, gap_days=30)
    logger.info(f"Train end: {train_end}, Val end: {val_end}, Test end: {test_end}")

    train_df, val_df, test_df = split_data(df, train_end, val_end)
    logger.info(f"Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

    # Step 4: Class weights
    class_weights = get_class_weights(train_df)
    logger.info(f"Class weights: {class_weights}")

    # Step 5: Train model
    logger.info("Step 5: Training CatBoost model...")
    model = train_model(train_df, val_df, FEATURE_COLUMNS, class_weights)

    # Step 6: Evaluate
    logger.info("Step 6: Evaluating on test set...")
    results = evaluate_model(model, test_df, FEATURE_COLUMNS)
    logger.info(f"Test results: {results}")

    # Step 7: Save model and metadata
    model_path = os.path.join(output_dir, "model.cbm")
    model.save_model(model_path)
    logger.info(f"Model saved to {model_path}")

    # Save metadata
    metadata = {
        "market": market,
        "total_events": len(df),
        "train_size": len(train_df),
        "val_size": len(val_df),
        "test_size": len(test_df),
        "train_end_date": str(train_end),
        "val_end_date": str(val_end),
        "test_end_date": str(test_end),
        "class_weights": class_weights,
        "feature_columns": FEATURE_COLUMNS,
        "test_results": results,
        "outcome_distribution": df["outcome"].value_counts().to_dict(),
        "label_distribution": df["label"].value_counts().to_dict(),
        "timestamp": datetime.utcnow().isoformat(),
    }

    import json
    meta_path = os.path.join(output_dir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    logger.info(f"Metadata saved to {meta_path}")

    return {
        "model": model,
        "metadata": metadata,
        "train_df": train_df,
        "val_df": val_df,
        "test_df": test_df,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_training_pipeline(market="US", max_symbols=None)
    if result:
        print(f"\nTraining complete!")
        print(f"Test AUC: {result['metadata']['test_results'].get('auc', 'N/A')}")
        print(f"Test Average Precision: {result['metadata']['test_results'].get('average_precision', 'N/A')}")
