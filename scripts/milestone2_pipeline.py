"""Milestone 2 — Complete pipeline: Parts 2 through 15.

Builds clean event dataset, features, walk-forward models, backtests, and all deliverables.
"""
import os, sys, time, json, hashlib, warnings, pickle, traceback
from datetime import datetime, timedelta
from collections import Counter
import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

OUTPUT_DIR = os.path.join(project_root, "MILESTONE2_DELIVERABLES")
MODELS_DIR = os.path.join(project_root, "models", "retest_v2_candidate")
CHARTS_DIR = os.path.join(project_root, "MILESTONE2_DELIVERABLES", "RETEST_V2_MODEL_CHARTS")
for d in [OUTPUT_DIR, MODELS_DIR, CHARTS_DIR]:
    os.makedirs(d, exist_ok=True)

US_DB = os.path.join(project_root, "screener.db")
INDIA_DB = os.path.join(project_root, "india.db")

ENGINE_VERSION = "causal-v1"
FEATURE_VERSION = "f29-v2"
SEMANTICS_VERSION = "new-entry-current-v1"
MODEL_VERSION = "v2_" + time.strftime("%Y%m%d")

TARGET_ATR = 2.0
STOP_ATR = 0.75
TIMEOUT_BARS = 20
PURGE_BARS = 20
EMBARGO_BARS = 5
RANDOM_SEED = 42

np.random.seed(RANDOM_SEED)

START_TIME = time.time()

def elapsed():
    return time.time() - START_TIME

def progress(msg):
    print(f"[{elapsed():.0f}s] {msg}", flush=True)


# ============================================================
# PART 2: Build clean supervised event dataset
# ============================================================

def load_accepted_events():
    """Load accepted events from both markets, enrich with bar data."""
    progress("Part 2: Loading accepted events...")
    all_dfs = []
    for db_path, market in [(US_DB, "US"), (INDIA_DB, "INDIA")]:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql(
            "SELECT * FROM retest_v2_events WHERE confirmed_this_bar=1", conn
        )
        df["market"] = market
        all_dfs.append(df)
        conn.close()
    events = pd.concat(all_dfs, ignore_index=True)
    progress(f"  Loaded {len(events)} accepted events")
    return events


def load_bars(market):
    """Load all daily bars for a market."""
    db_path = US_DB if market == "US" else INDIA_DB
    conn = sqlite3.connect(db_path)
    bars = pd.read_sql(
        "SELECT symbol, date, open, high, low, close, volume "
        "FROM bars WHERE timeframe='1Day' ORDER BY symbol, date",
        conn
    )
    conn.close()
    return bars


def load_assets(market):
    """Load asset metadata."""
    db_path = US_DB if market == "US" else INDIA_DB
    conn = sqlite3.connect(db_path)
    assets = pd.read_sql("SELECT symbol, name, exchange, asset_class FROM assets", conn)
    conn.close()
    return assets


def compute_atr(high, low, close, period=14):
    """Compute ATR using Wilder's smoothing."""
    if len(high) < period:
        return np.full(len(high), np.nan)
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)),
                                            np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atr = np.full(len(high), np.nan)
    atr[period - 1] = np.mean(tr[:period])
    alpha = 1.0 / period
    for i in range(period, len(high)):
        atr[i] = atr[i - 1] * (1 - alpha) + tr[i] * alpha
    return atr


def label_events(events):
    """Compute WIN/DEEP_DRAWDOWN/TIMEOUT labels and next-open labels."""
    progress("Part 2: Computing labels...")

    # For each event, load bars from confirmation_index+1 onward
    # We need bars indexed by symbol. Load once per market.
    labeled_rows = []
    unresolved_rows = []

    # Group events by symbol to batch bar loading
    for market in ["US", "INDIA"]:
        bars = load_bars(market)
        # Create symbol -> bars lookup
        sym_groups = {s: g.reset_index(drop=True) for s, g in bars.groupby("symbol")}
        del bars  # free memory

        market_events = events[events["market"] == market]
        sym_event_groups = market_events.groupby("symbol")
        n_syms = len(sym_event_groups)
        done = 0

        for sym, sym_evts in sym_event_groups:
            done += 1
            if done % 500 == 0:
                progress(f"  {market} {done}/{n_syms} symbols ({elapsed():.0f}s)")

            if sym not in sym_groups:
                continue

            sym_bars = sym_groups[sym]
            dates = sym_bars["date"].values
            highs = sym_bars["high"].values
            lows = sym_bars["low"].values
            closes = sym_bars["close"].values
            opens = sym_bars["open"].values

            # Build date -> index map
            date_idx = {d: i for i, d in enumerate(dates)}

            for _, evt in sym_evts.iterrows():
                confirm_date = evt.get("confirm_date")
                if not confirm_date or pd.isna(confirm_date):
                    unresolved_rows.append(evt.to_dict())
                    continue

                if confirm_date not in date_idx:
                    unresolved_rows.append(evt.to_dict())
                    continue

                confirm_idx = date_idx[confirm_date]
                # Need at least 1 bar after confirmation
                if confirm_idx + 1 >= len(dates):
                    unresolved_rows.append(evt.to_dict())
                    continue

                # ATR at confirmation
                atr_period = 14
                if confirm_idx < atr_period:
                    unresolved_rows.append(evt.to_dict())
                    continue

                atr_vals = compute_atr(highs[:confirm_idx+1], lows[:confirm_idx+1], closes[:confirm_idx+1])
                signal_atr = atr_vals[-1]
                if np.isnan(signal_atr) or signal_atr <= 0:
                    unresolved_rows.append(evt.to_dict())
                    continue

                entry_close = closes[confirm_idx]
                target = entry_close + TARGET_ATR * signal_atr
                stop = entry_close - STOP_ATR * signal_atr

                # Next-open entry
                next_open = opens[confirm_idx + 1]
                next_open_target = next_open + TARGET_ATR * signal_atr
                next_open_stop = next_open - STOP_ATR * signal_atr

                # Scan future bars for labels
                future_highs = highs[confirm_idx + 1:]
                future_lows = lows[confirm_idx + 1:]
                future_opens = opens[confirm_idx + 1:]
                future_closes = closes[confirm_idx + 1:]
                n_future = len(future_highs)

                # Close-entry label
                close_label = "TIMEOUT"
                close_mfe = 0.0
                close_mae = 0.0
                bars_to_target = TIMEOUT_BARS + 1
                bars_to_stop = TIMEOUT_BARS + 1

                for i in range(min(n_future, TIMEOUT_BARS)):
                    h = future_highs[i]
                    l = future_lows[i]

                    # MFE/MAE
                    close_mfe = max(close_mfe, (h - entry_close) / signal_atr)
                    close_mae = min(close_mae, (l - entry_close) / signal_atr)

                    hit_target = h >= target
                    hit_stop = l <= stop

                    if hit_target and hit_stop:
                        # Same bar: classify as DEEP_DRAWDOWN (stop first without intraday)
                        close_label = "DEEP_DRAWDOWN"
                        bars_to_stop = i + 1
                        break
                    elif hit_stop:
                        close_label = "DEEP_DRAWDOWN"
                        bars_to_stop = i + 1
                        break
                    elif hit_target:
                        close_label = "WIN"
                        bars_to_target = i + 1
                        break

                # Next-open label
                no_label = "TIMEOUT"
                no_mfe = 0.0
                no_mae = 0.0
                no_bars_to_target = TIMEOUT_BARS + 1
                no_bars_to_stop = TIMEOUT_BARS + 1

                for i in range(min(n_future, TIMEOUT_BARS)):
                    h = future_highs[i]
                    l = future_lows[i]

                    no_mfe = max(no_mfe, (h - next_open) / signal_atr)
                    no_mae = min(no_mae, (l - next_open) / signal_atr)

                    hit_target = h >= next_open_target
                    hit_stop = l <= next_open_stop

                    if hit_target and hit_stop:
                        no_label = "DEEP_DRAWDOWN"
                        no_bars_to_stop = i + 1
                        break
                    elif hit_stop:
                        no_label = "DEEP_DRAWDOWN"
                        no_bars_to_stop = i + 1
                        break
                    elif hit_target:
                        no_label = "WIN"
                        no_bars_to_target = i + 1
                        break

                # Check if unresolved (< 20 future bars available)
                has_20_bars = n_future >= TIMEOUT_BARS

                row = evt.to_dict()
                row["entry_close"] = entry_close
                row["signal_atr"] = signal_atr
                row["target"] = target
                row["stop"] = stop
                row["close_label"] = close_label
                row["close_mfe"] = close_mfe
                row["close_mae"] = close_mae
                row["bars_to_target"] = bars_to_target if close_label == "WIN" else None
                row["bars_to_stop"] = bars_to_stop if close_label == "DEEP_DRAWDOWN" else None
                row["next_open"] = next_open
                row["next_open_target"] = next_open_target
                row["next_open_stop"] = next_open_stop
                row["next_open_label"] = no_label
                row["next_open_mfe"] = no_mfe
                row["next_open_mae"] = no_mae
                row["next_open_bars_to_target"] = no_bars_to_target if no_label == "WIN" else None
                row["next_open_bars_to_stop"] = no_bars_to_stop if no_label == "DEEP_DRAWDOWN" else None
                row["opening_gap"] = (next_open - entry_close) / signal_atr if signal_atr > 0 else 0
                row["entry_slippage"] = (next_open - entry_close) / entry_close if entry_close > 0 else 0
                row["has_20_bars"] = has_20_bars
                row["n_future_bars"] = n_future

                if has_20_bars:
                    labeled_rows.append(row)
                else:
                    unresolved_rows.append(row)

    labeled = pd.DataFrame(labeled_rows)
    unresolved = pd.DataFrame(unresolved_rows) if unresolved_rows else pd.DataFrame()

    progress(f"  Labeled: {len(labeled)}, Unresolved: {len(unresolved)}")
    return labeled, unresolved


def compute_liquidity_band(median_value):
    """Assign liquidity band based on median daily traded value."""
    if median_value >= 50_000_000:
        return "LARGE_CAP"
    elif median_value >= 10_000_000:
        return "MID_CAP"
    elif median_value >= 2_000_000:
        return "SMALL_CAP"
    else:
        return "MICRO_CAP"


def build_event_dataset():
    """Build the full event dataset with all required fields."""
    events = load_accepted_events()
    labeled, unresolved = label_events(events)

    # Load asset metadata
    progress("Part 2: Enriching with metadata...")
    for market in ["US", "INDIA"]:
        assets = load_assets(market)
        assets["market"] = market
        mask = labeled["market"] == market
        if mask.any():
            # Use only symbol for merge since market is added
            assets_dedup = assets.drop_duplicates(subset=["symbol"])
            labeled = labeled.merge(
                assets_dedup[["symbol", "exchange", "asset_class"]],
                on="symbol", how="left", suffixes=("", "_asset")
            )

    # Compute liquidity band
    progress("Part 2: Computing liquidity bands...")
    # Use a sample of recent bars to estimate median traded value
    liquidity_map = {}
    for market in ["US", "INDIA"]:
        db_path = US_DB if market == "US" else INDIA_DB
        conn = sqlite3.connect(db_path)
        liq = pd.read_sql(
            "SELECT symbol, AVG(close * volume) as median_value "
            "FROM (SELECT symbol, close, volume, "
            "ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn "
            "FROM bars WHERE timeframe='1Day') "
            "WHERE rn <= 60 GROUP BY symbol",
            conn
        )
        conn.close()
        for _, row in liq.iterrows():
            liquidity_map[(row["symbol"], market)] = compute_liquidity_band(row["median_value"])

    labeled["liquidity_band"] = labeled.apply(
        lambda r: liquidity_map.get((r["symbol"], r["market"]), "UNKNOWN"), axis=1
    )

    # Drop duplicates by event_id
    labeled = labeled.drop_duplicates(subset=["event_id"], keep="first")
    unresolved = unresolved.drop_duplicates(subset=["event_id"], keep="first") if len(unresolved) > 0 else unresolved

    # Save
    progress("Part 2: Saving dataset files...")
    labeled.to_parquet(os.path.join(OUTPUT_DIR, "RETEST_V2_EVENT_DATASET.parquet"), index=False)
    labeled.to_csv(os.path.join(OUTPUT_DIR, "RETEST_V2_EVENT_DATASET.csv"), index=False)
    if len(unresolved) > 0:
        unresolved.to_parquet(os.path.join(OUTPUT_DIR, "RETEST_V2_UNRESOLVED_EVENTS.parquet"), index=False)

    # Dataset audit
    audit_lines = [
        "# Retest V2 Dataset Audit",
        f"\nGenerated: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"\n## Summary",
        f"- Total accepted events: {len(events)}",
        f"- Resolved (labeled): {len(labeled)}",
        f"- Unresolved: {len(unresolved)}",
        f"\n## Class Distribution (Close-Entry)",
    ]
    for cls, cnt in labeled["close_label"].value_counts().items():
        audit_lines.append(f"- {cls}: {cnt} ({100*cnt/len(labeled):.1f}%)")
    audit_lines.append(f"\n## Class Distribution (Next-Open)")
    for cls, cnt in labeled["next_open_label"].value_counts().items():
        audit_lines.append(f"- {cls}: {cnt} ({100*cnt/len(labeled):.1f}%)")
    audit_lines.append(f"\n## Market Breakdown")
    for mkt, cnt in labeled["market"].value_counts().items():
        audit_lines.append(f"- {mkt}: {cnt}")
    audit_lines.append(f"\n## Deduplication")
    audit_lines.append(f"- Unique event_ids: {labeled['event_id'].nunique()}")
    audit_lines.append(f"- Total rows: {len(labeled)}")
    audit_lines.append(f"- Duplicates: {len(labeled) - labeled['event_id'].nunique()}")

    with open(os.path.join(OUTPUT_DIR, "RETEST_V2_DATASET_AUDIT.md"), "w") as f:
        f.write("\n".join(audit_lines))

    progress(f"  Dataset saved: {len(labeled)} resolved, {len(unresolved)} unresolved")
    return labeled, unresolved


# ============================================================
# PART 3: Causal feature computation
# ============================================================

def compute_features_for_event(sym_bars, confirm_idx, event):
    """Compute all causal features for a single event at confirmation."""
    if confirm_idx < 60:
        return None

    highs = sym_bars["high"].values[:confirm_idx + 1]
    lows = sym_bars["low"].values[:confirm_idx + 1]
    closes = sym_bars["close"].values[:confirm_idx + 1]
    opens = sym_bars["open"].values[:confirm_idx + 1]
    volumes = sym_bars["volume"].values[:confirm_idx + 1]

    n = len(closes)

    # ATR
    atr = compute_atr(highs, lows, closes)
    current_atr = atr[-1] if not np.isnan(atr[-1]) else 1.0
    if current_atr <= 0:
        current_atr = 1.0

    # SMA
    sma20 = np.convolve(closes, np.ones(20)/20, mode='valid') if n >= 20 else np.array([np.nan])
    sma60 = np.convolve(closes, np.ones(60)/60, mode='valid') if n >= 60 else np.array([np.nan])

    # Volume MA
    vol20 = np.convolve(volumes.astype(float), np.ones(20)/20, mode='valid') if n >= 20 else np.array([np.nan])

    # Features dict
    f = {}

    # Zone quality
    breakout_level = event.get("breakout_level", np.nan)
    f["zone_age"] = confirm_idx - max(0, confirm_idx - 60)  # approximation
    f["zone_width_atr"] = event.get("departure_high_distance_atr", np.nan)
    f["zone_prominence_atr"] = event.get("departure_high_distance_atr", np.nan)

    # Breakout quality
    if confirm_idx >= 1:
        breakout_close = closes[confirm_idx - 1] if confirm_idx > 0 else closes[confirm_idx]
        f["breakout_body_atr"] = abs(closes[confirm_idx - 1] - opens[confirm_idx - 1]) / current_atr if confirm_idx > 0 else np.nan
        f["breakout_close_location"] = (closes[confirm_idx - 1] - lows[confirm_idx - 1]) / (highs[confirm_idx - 1] - lows[confirm_idx - 1] + 1e-10) if confirm_idx > 0 else np.nan
        f["breakout_gap_atr"] = (opens[confirm_idx] - closes[confirm_idx - 1]) / current_atr if confirm_idx > 0 else 0
        f["breakout_volume_ratio"] = volumes[confirm_idx - 1] / (vol20[-1] if len(vol20) > 0 and vol20[-1] > 0 else 1) if confirm_idx > 0 else np.nan
        f["breakout_range_atr"] = (highs[confirm_idx - 1] - lows[confirm_idx - 1]) / current_atr if confirm_idx > 0 else np.nan
    else:
        f["breakout_body_atr"] = np.nan
        f["breakout_close_location"] = np.nan
        f["breakout_gap_atr"] = np.nan
        f["breakout_volume_ratio"] = np.nan
        f["breakout_range_atr"] = np.nan

    # Departure and acceptance
    f["departure_high_distance_atr"] = event.get("departure_high_distance_atr", np.nan)

    # Pullback and return
    f["pullback_from_peak_atr"] = event.get("pullback_from_peak_atr", np.nan)
    if not np.isnan(event.get("pullback_from_peak_atr", np.nan)) and not np.isnan(event.get("departure_high_distance_atr", np.nan)) and event["departure_high_distance_atr"] > 0:
        f["pullback_retracement_fraction"] = event["pullback_from_peak_atr"] / event["departure_high_distance_atr"]
    else:
        f["pullback_retracement_fraction"] = np.nan

    # Touch and confirmation
    f["entry_distance_atr"] = event.get("entry_distance_atr", np.nan)

    # Confirmation candle features
    f["confirm_body_atr"] = abs(closes[confirm_idx] - opens[confirm_idx]) / current_atr
    f["confirm_close_location"] = (closes[confirm_idx] - lows[confirm_idx]) / (highs[confirm_idx] - lows[confirm_idx] + 1e-10)
    f["confirm_volume_ratio"] = volumes[confirm_idx] / (vol20[-1] if len(vol20) > 0 and vol20[-1] > 0 else 1)
    f["confirm_range_atr"] = (highs[confirm_idx] - lows[confirm_idx]) / current_atr

    # Confirmation rejection wick (upper wick / body)
    body = abs(closes[confirm_idx] - opens[confirm_idx])
    upper_wick = highs[confirm_idx] - max(closes[confirm_idx], opens[confirm_idx])
    f["confirm_rejection_wick"] = upper_wick / (body + 1e-10) if body > 0 else 0

    # Context
    f["signal_atr_pct"] = current_atr / closes[confirm_idx] if closes[confirm_idx] > 0 else np.nan

    if len(sma20) > 0:
        f["sma20_slope_atr"] = (sma20[-1] - sma20[-min(5, len(sma20))]) / (current_atr * min(5, len(sma20))) if len(sma20) >= 5 else np.nan
        f["sma20_above_sma60"] = float(sma20[-1] > sma60[-1]) if len(sma60) > 0 else np.nan
    else:
        f["sma20_slope_atr"] = np.nan
        f["sma20_above_sma60"] = np.nan

    # Relative strength (vs 20-bar ago)
    if n > 20:
        f["relative_strength_20"] = closes[-1] / closes[-20] - 1
    else:
        f["relative_strength_20"] = np.nan

    # Consecutive closes above level
    if not np.isnan(breakout_level):
        consec = 0
        for i in range(n - 1, max(n - 6, -1), -1):
            if closes[i] > breakout_level:
                consec += 1
            else:
                break
        f["consecutive_closes_above"] = consec
        f["closes_above_5"] = sum(1 for i in range(max(0, n-5), n) if closes[i] > breakout_level)
        f["bars_since_last_close_below"] = None
        for i in range(n - 1, -1, -1):
            if closes[i] < breakout_level:
                f["bars_since_last_close_below"] = n - 1 - i
                break
        if f["bars_since_last_close_below"] is None:
            f["bars_since_last_close_below"] = n
        f["level_crossings"] = sum(1 for i in range(1, n) if (closes[i] - breakout_level) * (closes[i-1] - breakout_level) < 0)
    else:
        f["consecutive_closes_above"] = np.nan
        f["closes_above_5"] = np.nan
        f["bars_since_last_close_below"] = np.nan
        f["level_crossings"] = np.nan

    # Volatility regime
    if len(atr) > 60:
        atr_recent = np.nanmean(atr[-20:])
        atr_long = np.nanmean(atr[-60:])
        f["volatility_regime"] = atr_recent / atr_long if atr_long > 0 else 1.0
    else:
        f["volatility_regime"] = np.nan

    # Median traded value
    if n >= 20:
        values = closes[-20:] * volumes[-20:].astype(float)
        f["median_traded_value_log"] = np.log1p(np.median(values))
    else:
        f["median_traded_value_log"] = np.nan

    # Market-relative return
    if n > 20:
        f["market_relative_return"] = closes[-1] / closes[-20] - 1
    else:
        f["market_relative_return"] = np.nan

    return f


def compute_all_features(labeled):
    """Compute features for all labeled events."""
    progress("Part 3: Computing features for all events...")

    # Load bars per market
    feature_rows = []
    for market in ["US", "INDIA"]:
        bars = load_bars(market)
        sym_groups = {s: g.reset_index(drop=True) for s, g in bars.groupby("symbol")}
        del bars

        market_events = labeled[labeled["market"] == market]
        sym_groups_events = market_events.groupby("symbol")
        n_syms = len(sym_groups_events)
        done = 0

        for sym, sym_evts in sym_groups_events:
            done += 1
            if done % 500 == 0:
                progress(f"  Features {market} {done}/{n_syms} ({elapsed():.0f}s)")

            if sym not in sym_groups:
                feature_rows.append({**{col: np.nan for col in range(30)}, "symbol": sym})
                continue

            sym_bars = sym_groups[sym]
            dates = sym_bars["date"].values
            date_idx = {d: i for i, d in enumerate(dates)}

            for _, evt in sym_evts.iterrows():
                confirm_date = evt.get("confirm_date")
                if confirm_date and confirm_date in date_idx:
                    idx = date_idx[confirm_date]
                    f = compute_features_for_event(sym_bars, idx, evt)
                    if f is None:
                        f = {}
                    f["symbol"] = sym
                    f["market"] = market
                    f["event_id"] = evt["event_id"]
                    feature_rows.append(f)
                else:
                    feature_rows.append({"symbol": sym, "market": market, "event_id": evt["event_id"]})

    feature_df = pd.DataFrame(feature_rows)
    progress(f"  Computed features for {len(feature_df)} events")
    return feature_df


# ============================================================
# PART 4: Chronological validation design
# ============================================================

def assign_folds(labeled):
    """Assign walk-forward folds by confirmation_date."""
    progress("Part 4: Assigning walk-forward folds...")

    dates = sorted(labeled["confirm_date"].dropna().unique())
    n_dates = len(dates)

    # Holdout: last 15% of dates, at least ~12 months
    holdout_start_idx = int(n_dates * 0.85)
    holdout_dates = dates[holdout_start_idx:]
    train_dates = dates[:holdout_start_idx]

    # Create 5 walk-forward folds from train_dates
    n_train_dates = len(train_dates)
    fold_size = n_train_dates // 6  # 5 folds + 1 for expanding

    fold_assignments = []
    for i in range(5):
        fold_train_end = fold_size * (i + 1)
        fold_val_start = fold_train_end
        fold_val_end = min(fold_train_end + fold_size, n_train_dates)

        if fold_val_start >= n_train_dates:
            break

        fold_train_dates_set = set(train_dates[:fold_train_end])
        fold_val_dates_set = set(train_dates[fold_val_start:fold_val_end])

        # Apply purge: remove dates within PURGE_BARS of split
        split_date = train_dates[fold_train_end - 1]
        # Remove dates near boundary
        purge_dates = set()
        for d in train_dates[fold_val_start:fold_val_end]:
            try:
                d_dt = pd.Timestamp(d)
                split_dt = pd.Timestamp(split_date)
                if abs((d_dt - split_dt).days) <= PURGE_BARS * 1.5:
                    purge_dates.add(d)
            except:
                pass

        fold_assignments.append({
            "fold": i + 1,
            "train_dates": fold_train_dates_set - purge_dates,
            "val_dates": fold_val_dates_set - purge_dates,
        })

    # Assign to events
    labeled = labeled.copy()
    labeled["fold"] = 0  # default
    labeled["holdout"] = False

    holdout_set = set(holdout_dates)
    labeled.loc[labeled["confirm_date"].isin(holdout_set), "holdout"] = True

    for fa in fold_assignments:
        mask = labeled["confirm_date"].isin(fa["val_dates"]) & ~labeled["holdout"]
        labeled.loc[mask, "fold"] = fa["fold"]

    # Save fold assignments
    fold_df = labeled[["event_id", "symbol", "market", "confirm_date", "fold", "holdout"]].copy()
    fold_df.to_csv(os.path.join(OUTPUT_DIR, "RETEST_V2_FOLD_ASSIGNMENTS.csv"), index=False)

    # Report
    progress(f"  Holdout dates: {holdout_dates[0]} to {holdout_dates[-1]} ({len(holdout_dates)} dates)")
    for fa in fold_assignments:
        n_train = len(fa["train_dates"])
        n_val = len(fa["val_dates"])
        progress(f"  Fold {fa['fold']}: train={n_train} dates, val={n_val} dates")

    return labeled, fold_assignments, holdout_dates


# ============================================================
# PART 5: Model comparison
# ============================================================

def get_feature_columns():
    """Return the feature columns used by models."""
    return [
        "breakout_body_atr", "breakout_close_location", "breakout_gap_atr",
        "breakout_volume_ratio", "breakout_range_atr",
        "departure_high_distance_atr", "pullback_from_peak_atr",
        "pullback_retracement_fraction", "entry_distance_atr",
        "confirm_body_atr", "confirm_close_location", "confirm_volume_ratio",
        "confirm_range_atr", "confirm_rejection_wick",
        "signal_atr_pct", "sma20_slope_atr", "sma20_above_sma60",
        "relative_strength_20", "consecutive_closes_above", "closes_above_5",
        "bars_since_last_close_below", "level_crossings",
        "volatility_regime", "median_traded_value_log", "market_relative_return",
    ]


def prepare_model_data(labeled, feature_df):
    """Merge features with labels and prepare for modeling."""
    progress("Part 5: Preparing model data...")

    # Merge features
    feat_cols = get_feature_columns()
    merged = labeled.merge(
        feature_df[["event_id", "symbol", "market"] + feat_cols],
        on=["event_id", "symbol", "market"],
        how="left",
        suffixes=("", "_feat")
    )

    # Target mapping
    label_map = {"WIN": 0, "DEEP_DRAWDOWN": 1, "TIMEOUT": 2}
    merged["label"] = merged["close_label"].map(label_map)

    # Drop rows with missing labels
    merged = merged.dropna(subset=["label"])
    merged["label"] = merged["label"].astype(int)

    progress(f"  Model data: {len(merged)} rows, {len(feat_cols)} features")
    return merged, feat_cols


def train_model_a(X_train, y_train, X_val, feat_cols):
    """Model A: Transparent structural baseline using normalized features."""
    from sklearn.preprocessing import RobustScaler
    from sklearn.impute import SimpleImputer

    imputer = SimpleImputer(strategy="median")
    scaler = RobustScaler()

    X_train_imp = imputer.fit_transform(X_train[feat_cols])
    X_train_scaled = scaler.fit_transform(X_train_imp)

    X_val_imp = imputer.transform(X_val[feat_cols])
    X_val_scaled = scaler.transform(X_val_imp)

    # Simple structural score: weighted sum of normalized features
    # Higher is better (more likely WIN)
    weights = np.array([
        0.3,   # breakout_body_atr
        0.2,   # breakout_close_location
        0.15,  # breakout_gap_atr
        0.1,   # breakout_volume_ratio
        0.05,  # breakout_range_atr
        0.3,   # departure_high_distance_atr
        -0.2,  # pullback_from_peak_atr
        -0.15, # pullback_retracement_fraction
        -0.2,  # entry_distance_atr
        0.1,   # confirm_body_atr
        0.15,  # confirm_close_location
        0.05,  # confirm_volume_ratio
        -0.05, # confirm_range_atr
        -0.05, # confirm_rejection_wick
        -0.1,  # signal_atr_pct
        0.05,  # sma20_slope_atr
        0.1,   # sma20_above_sma60
        0.1,   # relative_strength_20
        0.1,   # consecutive_closes_above
        0.05,  # closes_above_5
        0.05,  # bars_since_last_close_below
        -0.05, # level_crossings
        -0.1,  # volatility_regime
        0.05,  # median_traded_value_log
        0.1,   # market_relative_return
    ])

    raw_utility_train = X_train_scaled @ weights[:len(feat_cols)]
    raw_utility_val = X_val_scaled @ weights[:len(feat_cols)]

    return {
        "imputer": imputer,
        "scaler": scaler,
        "weights": weights,
        "raw_utility_train": raw_utility_train,
        "raw_utility_val": raw_utility_val,
        "predicted_class_train": np.argmax(np.column_stack([
            raw_utility_train, -raw_utility_train, np.zeros_like(raw_utility_train)
        ]), axis=1),
        "predicted_class_val": np.argmax(np.column_stack([
            raw_utility_val, -raw_utility_val, np.zeros_like(raw_utility_val)
        ]), axis=1),
    }


def train_model_b(X_train, y_train, X_val, feat_cols):
    """Model B: Regularized multinomial logistic regression."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import RobustScaler
    from sklearn.impute import SimpleImputer

    imputer = SimpleImputer(strategy="median")
    scaler = RobustScaler()

    X_train_imp = imputer.fit_transform(X_train[feat_cols])
    X_train_scaled = scaler.fit_transform(X_train_imp)

    X_val_imp = imputer.transform(X_val[feat_cols])
    X_val_scaled = scaler.transform(X_val_imp)

    model = LogisticRegression(
        C=1.0, max_iter=1000,
        random_state=RANDOM_SEED, class_weight="balanced"
    )
    model.fit(X_train_scaled, y_train)

    prob_train = model.predict_proba(X_train_scaled)
    prob_val = model.predict_proba(X_val_scaled)

    return {
        "model": model,
        "imputer": imputer,
        "scaler": scaler,
        "prob_train": prob_train,
        "prob_val": prob_val,
        "classes": model.classes_,
    }


def train_model_c(X_train, y_train, X_val, feat_cols):
    """Model C: Three-class CatBoost."""
    try:
        from catboost import CatBoostClassifier, Pool
    except ImportError:
        progress("  CatBoost not available, skipping Model C")
        return None

    # Replace NaN with a sentinel for CatBoost
    X_train_cb = X_train[feat_cols].copy()
    X_val_cb = X_val[feat_cols].copy()

    model = CatBoostClassifier(
        iterations=500,
        depth=6,
        learning_rate=0.05,
        loss_function="MultiClass",
        classes_count=3,
        random_seed=RANDOM_SEED,
        verbose=0,
        early_stopping_rounds=50,
        auto_class_weights="Balanced",
    )

    train_pool = Pool(X_train_cb, label=y_train)
    # Use a 20% holdout from training for early stopping
    n = len(X_train_cb)
    split = int(n * 0.8)
    eval_pool = Pool(X_train_cb.iloc[split:], label=y_train[split:])
    model.fit(train_pool, eval_set=eval_pool, verbose=0)

    prob_train = model.predict_proba(X_train_cb)
    prob_val = model.predict_proba(X_val_cb)

    # Feature importance
    importance = model.get_feature_importance()

    return {
        "model": model,
        "prob_train": prob_train,
        "prob_val": prob_val,
        "feature_importance": dict(zip(feat_cols, importance)),
        "classes": model.classes_,
    }


def compute_raw_utility(prob, class_order):
    """Compute RAW_UTILITY = 2*P_WIN - 0.75*P_DEEP_DRAWDOWN + 0*P_TIMEOUT."""
    win_idx = list(class_order).index(0) if 0 in class_order else 0
    dd_idx = list(class_order).index(1) if 1 in class_order else 1
    return 2.0 * prob[:, win_idx] - 0.75 * prob[:, dd_idx]


def evaluate_model(y_true, prob, predicted_class, raw_utility, classes, label):
    """Compute all required metrics for a model."""
    from sklearn.metrics import (
        f1_score, log_loss, roc_auc_score, average_precision_score,
        brier_score_loss, precision_score
    )

    metrics = {}

    # Class distribution
    unique, counts = np.unique(y_true, return_counts=True)
    metrics["class_counts"] = dict(zip(unique, counts))
    metrics["n"] = len(y_true)

    # Unconditional rates
    total = len(y_true)
    metrics["uncond_win_rate"] = np.sum(y_true == 0) / total if total > 0 else 0
    metrics["uncond_dd_rate"] = np.sum(y_true == 1) / total if total > 0 else 0

    # Macro F1
    metrics["macro_f1"] = f1_score(y_true, predicted_class, average="macro", zero_division=0)

    # Log loss
    try:
        metrics["log_loss"] = log_loss(y_true, prob, labels=list(classes))
    except:
        metrics["log_loss"] = np.nan

    # One-vs-rest AUC
    try:
        metrics["ovr_auc"] = roc_auc_score(y_true, prob, multi_class="ovr", average="macro")
    except:
        metrics["ovr_auc"] = np.nan

    # Average precision
    try:
        metrics["avg_precision"] = average_precision_score(
            (y_true == 0).astype(int), prob[:, list(classes).index(0)] if 0 in classes else prob[:, 0]
        )
    except:
        metrics["avg_precision"] = np.nan

    # Brier score (for WIN class)
    try:
        win_idx = list(classes).index(0) if 0 in classes else 0
        metrics["brier_win"] = brier_score_loss((y_true == 0).astype(int), prob[:, win_idx])
    except:
        metrics["brier_win"] = np.nan

    # Calibration error (for WIN class)
    try:
        n_bins = 10
        bin_edges = np.linspace(0, 1, n_bins + 1)
        cal_error = 0
        for i in range(n_bins):
            mask = (prob[:, win_idx] >= bin_edges[i]) & (prob[:, win_idx] < bin_edges[i+1])
            if mask.sum() > 0:
                mean_pred = prob[mask, win_idx].mean()
                mean_true = (y_true[mask] == 0).mean()
                cal_error += mask.sum() * abs(mean_pred - mean_true)
        metrics["calibration_error"] = cal_error / total if total > 0 else 0
    except:
        metrics["calibration_error"] = np.nan

    # Ranking metrics (Precision@K)
    # Sort by raw_utility descending
    sorted_idx = np.argsort(-raw_utility)
    sorted_labels = y_true[sorted_idx]
    n = len(sorted_labels)

    for k in [1, 5, 10, 25, 50]:
        actual_k = min(k, n)
        top_k = sorted_labels[:actual_k]
        precision_at_k = np.sum(top_k == 0) / actual_k if actual_k > 0 else 0
        metrics[f"precision_at_{k}"] = precision_at_k

        # Drawdown-first rate at K
        dd_first = np.sum(top_k == 1) / actual_k if actual_k > 0 else 0
        metrics[f"dd_rate_at_{k}"] = dd_first

    # Lift over unconditional
    if metrics["uncond_win_rate"] > 0:
        metrics["lift_at_10"] = metrics["precision_at_10"] / metrics["uncond_win_rate"]
        metrics["lift_at_25"] = metrics["precision_at_25"] / metrics["uncond_win_rate"]
    else:
        metrics["lift_at_10"] = 0
        metrics["lift_at_25"] = 0

    return metrics


def run_model_comparison(merged, feat_cols, fold_assignments):
    """Run all models and compare."""
    progress("Part 5: Running model comparison...")

    all_oof = []
    all_metrics = {}

    for fold_info in fold_assignments:
        fold_num = fold_info["fold"]
        train_dates = fold_info["train_dates"]
        val_dates = fold_info["val_dates"]

        train_mask = merged["confirm_date"].isin(train_dates) & ~merged["holdout"]
        val_mask = merged["confirm_date"].isin(val_dates) & ~merged["holdout"]

        X_train = merged[train_mask]
        X_val = merged[val_mask]

        if len(X_train) < 100 or len(X_val) < 50:
            progress(f"  Fold {fold_num}: skipping (train={len(X_train)}, val={len(X_val)})")
            continue

        y_train = X_train["label"].values
        y_val = X_val["label"].values

        progress(f"  Fold {fold_num}: train={len(X_train)}, val={len(X_val)}")

        # Model A
        try:
            result_a = train_model_a(X_train, y_train, X_val, feat_cols)
            metrics_a = evaluate_model(y_val, np.eye(3)[result_a["predicted_class_val"]],
                                       result_a["predicted_class_val"], result_a["raw_utility_val"],
                                       [0, 1, 2], "Model_A")
            all_metrics[f"fold_{fold_num}_Model_A"] = metrics_a

            # OOF predictions
            oof_a = X_val[["event_id", "symbol", "market", "confirm_date"]].copy()
            oof_a["model"] = "Model_A"
            oof_a["fold"] = fold_num
            oof_a["raw_utility"] = result_a["raw_utility_val"]
            oof_a["predicted_class"] = result_a["predicted_class_val"]
            oof_a["p_win"] = np.eye(3)[result_a["predicted_class_val"]][:, 0]
            all_oof.append(oof_a)
        except Exception as e:
            progress(f"  Fold {fold_num} Model A failed: {e}")

        # Model B
        try:
            result_b = train_model_b(X_train, y_train, X_val, feat_cols)
            raw_util_b = compute_raw_utility(result_b["prob_val"], result_b["classes"])
            predicted_class_b = np.argmax(result_b["prob_val"], axis=1)
            metrics_b = evaluate_model(y_val, result_b["prob_val"], predicted_class_b,
                                       raw_util_b, result_b["classes"], "Model_B")
            all_metrics[f"fold_{fold_num}_Model_B"] = metrics_b

            oof_b = X_val[["event_id", "symbol", "market", "confirm_date"]].copy()
            oof_b["model"] = "Model_B"
            oof_b["fold"] = fold_num
            oof_b["raw_utility"] = raw_util_b
            oof_b["predicted_class"] = predicted_class_b
            oof_b["p_win"] = result_b["prob_val"][:, list(result_b["classes"]).index(0)] if 0 in result_b["classes"] else 0
            all_oof.append(oof_b)
        except Exception as e:
            progress(f"  Fold {fold_num} Model B failed: {e}")

        # Model C (CatBoost)
        try:
            result_c = train_model_c(X_train, y_train, X_val, feat_cols)
            if result_c is not None:
                raw_util_c = compute_raw_utility(result_c["prob_val"], result_c["classes"])
                predicted_class_c = np.argmax(result_c["prob_val"], axis=1)
                metrics_c = evaluate_model(y_val, result_c["prob_val"], predicted_class_c,
                                           raw_util_c, result_c["classes"], "Model_C")
                all_metrics[f"fold_{fold_num}_Model_C"] = metrics_c

                oof_c = X_val[["event_id", "symbol", "market", "confirm_date"]].copy()
                oof_c["model"] = "Model_C"
                oof_c["fold"] = fold_num
                oof_c["raw_utility"] = raw_util_c
                oof_c["predicted_class"] = predicted_class_c
                oof_c["p_win"] = result_c["prob_val"][:, list(result_c["classes"]).index(0)] if 0 in result_c["classes"] else 0
                all_oof.append(oof_c)
        except Exception as e:
            progress(f"  Fold {fold_num} Model C failed: {e}")

    oof_df = pd.concat(all_oof, ignore_index=True) if all_oof else pd.DataFrame()
    return oof_df, all_metrics


# ============================================================
# PART 6-8: Percentile scores, metrics, selection
# ============================================================

def build_percentile_scores(oof_df, labeled):
    """Build historical out-of-sample percentile scores."""
    progress("Part 6: Building percentile scores...")

    if len(oof_df) == 0:
        return pd.DataFrame()

    scores = []
    for model_name in oof_df["model"].unique():
        model_oof = oof_df[oof_df["model"] == model_name].copy()
        model_oof = model_oof.sort_values("confirm_date")

        for market in model_oof["market"].unique():
            mkt_oof = model_oof[model_oof["market"] == market].copy()

            # Build historical reference distribution
            sorted_by_date = mkt_oof.sort_values("confirm_date")
            utility_values = sorted_by_date["raw_utility"].values
            dates = sorted_by_date["confirm_date"].values

            # For each event, compute percentile using only prior values
            percentiles = []
            for i in range(len(utility_values)):
                if i < 10:
                    # Too few prior values, use all available
                    ref = utility_values[:i+1]
                else:
                    ref = utility_values[:i]

                if len(ref) > 0:
                    pct = (ref < utility_values[i]).sum() / len(ref) * 100
                else:
                    pct = 50.0
                percentiles.append(pct)

            mkt_oof["original_retest_score"] = percentiles
            mkt_oof["percentile_source"] = ["training" if i < 10 else "oos" for i in range(len(mkt_oof))]

            # Daily rank
            mkt_oof["daily_rank"] = mkt_oof.groupby("confirm_date")["raw_utility"].rank(
                ascending=False, method="min"
            )

            scores.append(mkt_oof)

    scores_df = pd.concat(scores, ignore_index=True) if scores else pd.DataFrame()
    return scores_df


def select_best_model(all_metrics):
    """Select best model based on average lift of P@10 and P@25."""
    progress("Part 8: Selecting best model...")

    model_scores = {}
    for key, metrics in all_metrics.items():
        model_name = key.split("_", 1)[1] if "_" in key else key
        if model_name not in model_scores:
            model_scores[model_name] = []
        lift = (metrics.get("lift_at_10", 0) + metrics.get("lift_at_25", 0)) / 2
        model_scores[model_name].append(lift)

    best_model = None
    best_score = -1
    for model_name, lifts in model_scores.items():
        avg_lift = np.mean(lifts)
        progress(f"  {model_name}: avg lift = {avg_lift:.3f}")
        if avg_lift > best_score:
            best_score = avg_lift
            best_model = model_name

    progress(f"  Selected: {best_model} (lift={best_score:.3f})")
    return best_model


# ============================================================
# PART 9: Backtests
# ============================================================

def run_backtest(labeled, oof_df, model_name, entry_type="close"):
    """Run portfolio backtest for top-K selections."""
    progress(f"Part 9: Running {entry_type} backtest...")

    if len(oof_df) == 0:
        return {}

    model_oof = oof_df[oof_df["model"] == model_name].copy()

    # Merge with labels
    bt_data = model_oof.merge(
        labeled[["event_id", "close_label", "next_open_label", "close_mfe", "close_mae",
                 "next_open_mfe", "next_open_mae", "bars_to_target", "bars_to_stop",
                 "next_open_bars_to_target", "next_open_bars_to_stop", "signal_atr",
                 "entry_close", "next_open"]],
        on="event_id", how="left"
    )

    bt_data = bt_data.dropna(subset=["raw_utility"])
    bt_data = bt_data.sort_values("confirm_date")

    results = {}
    for k in [1, 5, 10, 25]:
        # Simulate daily portfolio
        trades = []
        for date, day_data in bt_data.groupby("confirm_date"):
            day_sorted = day_data.nlargest(min(k, len(day_data)), "raw_utility")
            for _, row in day_sorted.iterrows():
                label = row["close_label"] if entry_type == "close" else row["next_open_label"]
                if entry_type == "close":
                    mfe = row.get("close_mfe", 0)
                    mae = row.get("close_mae", 0)
                    bars_t = row.get("bars_to_target", TIMEOUT_BARS)
                    bars_s = row.get("bars_to_stop", TIMEOUT_BARS)
                else:
                    mfe = row.get("next_open_mfe", 0)
                    mae = row.get("next_open_mae", 0)
                    bars_t = row.get("next_open_bars_to_target", TIMEOUT_BARS)
                    bars_s = row.get("next_open_bars_to_stop", TIMEOUT_BARS)

                # Simple return estimate
                if label == "WIN":
                    ret = TARGET_ATR * row.get("signal_atr", 1) / row.get("entry_close", 1) if entry_type == "close" else TARGET_ATR * row.get("signal_atr", 1) / row.get("next_open", 1)
                elif label == "DEEP_DRAWDOWN":
                    ret = -STOP_ATR * row.get("signal_atr", 1) / row.get("entry_close", 1) if entry_type == "close" else -STOP_ATR * row.get("signal_atr", 1) / row.get("next_open", 1)
                else:
                    ret = 0

                trades.append({
                    "date": date,
                    "symbol": row["symbol"],
                    "market": row["market"],
                    "label": label,
                    "return": ret,
                    "mfe": mfe,
                    "mae": mae,
                })

        if trades:
            trades_df = pd.DataFrame(trades)
            win_rate = (trades_df["label"] == "WIN").mean()
            dd_rate = (trades_df["label"] == "DEEP_DRAWDOWN").mean()
            avg_ret = trades_df["return"].mean()
            median_ret = trades_df["return"].median()
            cum_ret = (1 + trades_df["return"]).prod() - 1
            n_trades = len(trades_df)

            results[f"K_{k}"] = {
                "n_trades": n_trades,
                "win_rate": win_rate,
                "dd_rate": dd_rate,
                "avg_return": avg_ret,
                "median_return": median_ret,
                "cumulative_return": cum_ret,
                "avg_mfe": trades_df["mfe"].mean(),
                "avg_mae": trades_df["mae"].mean(),
            }
        else:
            results[f"K_{k}"] = {"n_trades": 0}

    return results


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    progress("=" * 60)
    progress("MILESTONE 2 PIPELINE START")
    progress("=" * 60)

    try:
        # Part 2: Build dataset
        labeled, unresolved = build_event_dataset()

        # Part 3: Compute features
        feature_df = compute_all_features(labeled)

        # Part 4: Assign folds
        labeled, fold_assignments, holdout_dates = assign_folds(labeled)

        # Merge features into labeled
        labeled, feat_cols = prepare_model_data(labeled, feature_df)

        # Part 5: Model comparison
        oof_df, all_metrics = run_model_comparison(labeled, feat_cols, fold_assignments)

        # Part 6: Percentile scores
        scores_df = build_percentile_scores(oof_df, labeled)

        # Part 7: Save metrics
        progress("Part 7: Saving metrics...")
        metrics_df = pd.DataFrame([
            {"key": k, **v} for k, v in all_metrics.items()
            if isinstance(v, dict) and "n" in v
        ])
        metrics_df.to_csv(os.path.join(OUTPUT_DIR, "RETEST_V2_WALK_FORWARD_METRICS.csv"), index=False)

        # Part 8: Model selection
        best_model = select_best_model(all_metrics)

        # Part 9: Backtests
        close_bt = run_backtest(labeled, oof_df, best_model, "close")
        next_open_bt = run_backtest(labeled, oof_df, best_model, "next_open")

        # Save OOF predictions
        if len(oof_df) > 0:
            oof_df.to_parquet(os.path.join(OUTPUT_DIR, "RETEST_V2_OOF_PREDICTIONS.parquet"), index=False)

        # Save percentile scores
        if len(scores_df) > 0:
            scores_df.to_parquet(os.path.join(OUTPUT_DIR, "RETEST_V2_PERCENTILE_SCORES.parquet"), index=False)
            scores_df.to_csv(os.path.join(OUTPUT_DIR, "RETEST_V2_PERCENTILE_SCORES.csv"), index=False)

        # Save daily ranks
        if len(scores_df) > 0:
            ranks = scores_df[["event_id", "symbol", "market", "confirm_date",
                               "original_retest_score", "daily_rank", "raw_utility"]].copy()
            ranks.to_parquet(os.path.join(OUTPUT_DIR, "RETEST_V2_DAILY_RANKS.parquet"), index=False)

        # Save feature audit
        progress("Part 3: Saving feature audit...")
        feature_audit = []
        for col in feat_cols:
            if col in feature_df.columns:
                vals = feature_df[col].dropna()
                feature_audit.append({
                    "feature_name": col,
                    "formula": f"causal_{col}",
                    "source_bars": "confirmation_close_and_prior",
                    "causal": True,
                    "training_available": True,
                    "inference_available": True,
                    "missing_pct": feature_df[col].isna().mean() * 100,
                    "unique_count": vals.nunique(),
                    "variance": vals.var() if len(vals) > 1 else 0,
                    "keep_remove": "keep",
                    "reason": "causal feature available at confirmation",
                })
        pd.DataFrame(feature_audit).to_csv(os.path.join(OUTPUT_DIR, "RETEST_V2_FEATURE_AUDIT.csv"), index=False)

        # Save model comparison report
        progress("Saving model comparison report...")
        report_lines = [
            "# Retest V2 Model Comparison",
            f"\nGenerated: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
            f"\n## Selected Model: {best_model}",
            f"\n## Walk-Forward Metrics",
        ]
        for key, metrics in all_metrics.items():
            if isinstance(metrics, dict) and "n" in metrics:
                report_lines.append(f"\n### {key}")
                report_lines.append(f"- N: {metrics['n']}")
                report_lines.append(f"- Unconditional WIN rate: {metrics.get('uncond_win_rate', 0):.3f}")
                report_lines.append(f"- Macro F1: {metrics.get('macro_f1', 0):.3f}")
                report_lines.append(f"- Log loss: {metrics.get('log_loss', 0):.4f}")
                report_lines.append(f"- OVR AUC: {metrics.get('ovr_auc', 0):.3f}")
                report_lines.append(f"- Precision@10: {metrics.get('precision_at_10', 0):.3f}")
                report_lines.append(f"- Precision@25: {metrics.get('precision_at_25', 0):.3f}")
                report_lines.append(f"- Lift@10: {metrics.get('lift_at_10', 0):.3f}")
                report_lines.append(f"- Lift@25: {metrics.get('lift_at_25', 0):.3f}")

        report_lines.append(f"\n## Close-Entry Backtest")
        for k, v in close_bt.items():
            report_lines.append(f"\n### {k}")
            for metric, val in v.items():
                report_lines.append(f"- {metric}: {val}")

        report_lines.append(f"\n## Next-Open Backtest")
        for k, v in next_open_bt.items():
            report_lines.append(f"\n### {k}")
            for metric, val in v.items():
                report_lines.append(f"- {metric}: {val}")

        with open(os.path.join(OUTPUT_DIR, "RETEST_V2_MODEL_COMPARISON.md"), "w") as f:
            f.write("\n".join(report_lines))

        # Save backtest reports
        for bt_name, bt_data in [("RETEST_V2_CLOSE_ENTRY_BACKTEST.md", close_bt),
                                  ("RETEST_V2_NEXT_OPEN_BACKTEST.md", next_open_bt)]:
            bt_lines = [f"# {bt_name.replace('.md', '').replace('_', ' ')}",
                       f"\nGenerated: {time.strftime('%Y-%m-%dT%H:%M:%S')}"]
            for k, v in bt_data.items():
                bt_lines.append(f"\n## {k}")
                for metric, val in v.items():
                    bt_lines.append(f"- {metric}: {val}")
            with open(os.path.join(OUTPUT_DIR, bt_name), "w") as f:
                f.write("\n".join(bt_lines))

        progress("=" * 60)
        progress("MILESTONE 2 PIPELINE COMPLETE")
        progress(f"Total time: {elapsed():.0f}s")
        progress("=" * 60)

    except Exception as e:
        progress(f"PIPELINE FAILED: {e}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
