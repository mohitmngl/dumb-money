"""Backtest the trained retest model against historical data."""
import logging
import json
import os
import sys
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
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
    """Extract feature vector from event."""
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


def run_backtest(db_path, model_path, threshold=0.5, max_symbols=None):
    """Run backtest using trained model."""
    model = CatBoostClassifier()
    model.load_model(model_path)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT DISTINCT symbol FROM stats ORDER BY symbol")
    symbols = [row[0] for row in c.fetchall()]

    if max_symbols:
        symbols = symbols[:max_symbols]

    logger.info(f"Backtesting {len(symbols)} symbols")

    all_results = []
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
                    zone_info = {
                        "prominence": z.prominence_atr,
                        "width": z.width_atr,
                        "reactions": z.reactions,
                        "false_breakouts": z.false_breakouts,
                    }
                    break

            feat = extract_features(ev, zone_info)
            X = np.array([feat[col] for col in FEATURE_COLUMNS]).reshape(1, -1)
            prob = model.predict_proba(X)[0, 1]

            all_results.append({
                "symbol": sym,
                "signal_date": ev.signal_date,
                "outcome": ev.outcome,
                "model_prob": prob,
                "predicted_win": prob >= threshold,
                "actual_win": ev.outcome == cfg.OutcomeClass.WIN.value,
                "mfe5": getattr(ev, "mfe5", np.nan),
                "mae5": getattr(ev, "mae5", np.nan),
                "days_to_1atr": getattr(ev, "days_to_1atr", np.nan),
            })

        if (i + 1) % 500 == 0:
            logger.info(f"  Processed {i+1}/{len(symbols)} symbols")

    conn.close()

    if not all_results:
        logger.error("No backtest results!")
        return None

    df = pd.DataFrame(all_results)
    logger.info(f"Total events: {len(df)}")
    logger.info(f"Outcome distribution:\n{df['outcome'].value_counts()}")

    # Performance metrics
    actual_wins = (df["outcome"] == cfg.OutcomeClass.WIN.value).sum()
    actual_losses = (df["outcome"] == cfg.OutcomeClass.DEEP_DRAWDOWN.value).sum()
    df["predicted_win"] = df["model_prob"] >= threshold
    tp = ((df["predicted_win"]) & (df["actual_win"])).sum()
    fp = ((df["predicted_win"]) & (~df["actual_win"])).sum()
    tn = ((~df["predicted_win"]) & (~df["actual_win"])).sum()
    fn = ((~df["predicted_win"]) & (df["actual_win"])).sum()

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    accuracy = (tp + tn) / max(1, len(df))

    logger.info(f"Threshold: {threshold}")
    logger.info(f"TP={tp}, FP={fp}, TN={tn}, FN={fn}")
    logger.info(f"Precision: {precision:.4f}")
    logger.info(f"Recall: {recall:.4f}")
    logger.info(f"Accuracy: {accuracy:.4f}")

    # Performance by predicted win vs actual
    win_when_predicted = df[df["predicted_win"]]["outcome"].value_counts()
    lose_when_predicted = df[~df["predicted_win"]]["outcome"].value_counts()

    logger.info(f"\nWhen predicted WIN (prob >= {threshold}):")
    logger.info(f"  {win_when_predicted.get(cfg.OutcomeClass.WIN.value, 0)} WIN")
    logger.info(f"  {win_when_predicted.get(cfg.OutcomeClass.DEEP_DRAWDOWN.value, 0)} DEEP_DRAWDOWN")
    logger.info(f"  {win_when_predicted.get(cfg.OutcomeClass.TIMEOUT.value, 0)} TIMEOUT")

    logger.info(f"\nWhen predicted NOT WIN (prob < {threshold}):")
    logger.info(f"  {lose_when_predicted.get(cfg.OutcomeClass.WIN.value, 0)} WIN")
    logger.info(f"  {lose_when_predicted.get(cfg.OutcomeClass.DEEP_DRAWDOWN.value, 0)} DEEP_DRAWDOWN")
    logger.info(f"  {lose_when_predicted.get(cfg.OutcomeClass.TIMEOUT.value, 0)} TIMEOUT")

    return df


if __name__ == "__main__":
    base = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt"
    db_path = os.path.join(base, "screener.db")
    model_path = os.path.join(base, "models", "retest_v1", "model.cbm")

    df = run_backtest(db_path, model_path, threshold=0.5, max_symbols=200)
    if df is not None:
        df.to_csv(os.path.join(base, "models", "retest_v1", "backtest_results.csv"), index=False)
        print(f"\nBacktest results saved to models/retest_v1/backtest_results.csv")
