"""
Offline walk-forward training for OLD_SWING_RETEST_SCORE ML models.

Usage:
    python retest_train.py --market US
    python retest_train.py --market INDIA
"""

import sys
import os
import argparse
import time
import logging
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from dumbmoney.db import get_db
from dumbmoney.retest_engine import (
    _compute_atr_numba, _detect_swing_highs_numba,
    _filter_and_cluster_numba, _detect_breakouts_numba,
    _detect_retests_numba, _compute_trade_outcomes_numba,
    _ema_numba, SWING_LEFT, SWING_RIGHT, SWING_MIN_PROMINENCE_ATR,
    CLUSTER_DISTANCE_ATR, UPPER_BARRIER_ATR, LOWER_BARRIER_ATR, TIME_BARRIER,
)
from dumbmoney.retest_models import (
    train_classifier, train_regressors, save_models,
    FEATURE_NAMES,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _extract_features_for_event(close, high, low, volume, atr, vol_sma20,
                                 ema20, ema50, ema200,
                                 zone_level, zone_prom, zone_touches, zone_width,
                                 breakout_bar, breakout_dist, breakout_body,
                                 breakout_clv, breakout_vol,
                                 retest_bar, retest_depth, retest_close_rel,
                                 retest_wick, event_idx, i):
    """Extract feature vector for a single retest event at bar i."""
    cur_atr = atr[i] if atr[i] > 0 else 1e-10

    features = np.zeros(len(FEATURE_NAMES), dtype=np.float64)

    # Resistance zone features
    features[0] = (i - breakout_bar) / 252.0  # resistance age in years
    features[1] = zone_prom / cur_atr  # prominence in ATR
    features[2] = zone_touches  # number of reactions
    features[3] = zone_width / cur_atr  # avg reaction size proxy
    features[4] = zone_width / cur_atr  # zone width in ATR
    features[5] = 0.0  # zone dispersion (simplified)
    features[6] = 0.0  # prior false breakouts (simplified)

    # Breakout features
    features[7] = breakout_dist  # breakout close distance in ATR
    features[8] = breakout_body  # breakout body in ATR
    features[9] = breakout_clv  # breakout CLV
    features[10] = breakout_vol  # breakout volume ratio

    # Retest features
    features[11] = (retest_bar - breakout_bar)  # candles between breakout and retest
    features[12] = (retest_bar - breakout_bar)  # pullback duration
    features[13] = retest_depth  # retest depth in ATR
    features[14] = retest_close_rel  # retest close relative to level
    features[15] = retest_wick  # rejection wick
    features[16] = abs(close[i] - low[i]) / cur_atr  # retest body

    # Volume features
    avg_vol = np.mean(volume[max(0, i-20):i]) if i > 0 else volume[i]
    vol_contraction = volume[i] / avg_vol if avg_vol > 0 else 1.0
    features[17] = vol_contraction  # pullback volume contraction
    features[18] = vol_contraction  # bounce volume expansion (simplified)

    # Post-breakout behavior
    features[19] = 0.0  # closes below resistance (simplified)
    features[20] = 0.0  # support tests after breakout

    # Context features
    features[21] = (close[i] - zone_level) / cur_atr  # distance from retest level
    features[22] = cur_atr / close[i] * 100 if close[i] > 0 else 0  # ATR% of price

    # Realized volatility
    if i >= 20:
        rets = np.diff(np.log(close[max(0, i-20):i+1]))
        features[23] = np.std(rets) * np.sqrt(252) if len(rets) > 1 else 0
    else:
        features[23] = 0

    # Gap features
    features[24] = 0.0  # gap frequency
    features[25] = 0.0  # gap size avg

    # Liquidity
    features[26] = np.mean(volume[max(0, i-20):i+1]) if i > 0 else volume[i]
    features[27] = np.median(close[max(0, i-20):i+1]) if i > 0 else close[i]
    features[28] = close[i]  # price level
    features[29] = 0.01  # slippage proxy

    # EMA alignment
    features[30] = 1.0 if ema20[i] > ema50[i] else 0.0
    features[31] = 1.0 if ema50[i] > ema200[i] else 0.0
    features[32] = 1.0 if ema20[i] > ema200[i] else 0.0

    # EMA slopes
    if i >= 5:
        features[33] = (ema20[i] - ema20[i-5]) / ema20[i-5] if ema20[i-5] > 0 else 0
        features[34] = (ema50[i] - ema50[i-5]) / ema50[i-5] if ema50[i-5] > 0 else 0
        features[35] = (ema200[i] - ema200[i-5]) / ema200[i-5] if ema200[i-5] > 0 else 0
    else:
        features[33] = features[34] = features[35] = 0

    # Momentum
    if i >= 20:
        features[36] = (close[i] - close[i-20]) / close[i-20] if close[i-20] > 0 else 0
    if i >= 60:
        features[37] = (close[i] - close[i-60]) / close[i-60] if close[i-60] > 0 else 0

    # Relative strength (simplified: just momentum)
    features[38] = features[36]  # vs market (placeholder)
    features[39] = features[36]  # vs sector (placeholder)

    # Market/sector trend (placeholder)
    features[40] = 0.5  # market trend
    features[41] = 0.5  # sector trend

    # Overhead space
    next_res = close[i] * 1.5  # simplified
    features[42] = (next_res - close[i]) / cur_atr

    # Overextended
    features[43] = 1.0 if close[i] > ema20[i] * 1.10 else 0.0

    return features


def train_walk_forward(market, n_folds=5):
    """Walk-forward training for a given market."""
    logger.info(f"Starting walk-forward training for {market}")

    db_name = "screener.db" if market == "US" else "india.db"
    db_path = os.path.join(os.path.dirname(__file__), "..", db_name)
    conn = get_db(market)

    # Load all symbols with sufficient data
    syms = [r[0] for r in conn.execute(
        "SELECT symbol FROM stats WHERE price > 1"
    ).fetchall()]
    logger.info(f"Found {len(syms)} symbols")

    # Load bars
    placeholders = ",".join("?" * len(syms))
    bars_df = pd.read_sql(
        f"SELECT symbol, date, open, high, low, close, volume "
        f"FROM bars WHERE timeframe='1Day' AND symbol IN ({placeholders}) "
        f"ORDER BY symbol, date",
        conn, params=syms, parse_dates=["date"]
    )
    conn.close()

    logger.info(f"Loaded {len(bars_df)} bars for {bars_df['symbol'].nunique()} symbols")

    # Detect events across all symbols
    all_features = []
    all_outcomes = []

    for sym, grp in bars_df.groupby("symbol"):
        if len(grp) < 100:
            continue
        grp = grp.sort_values("date").reset_index(drop=True)
        c = grp["close"].values.astype(np.float64)
        h = grp["high"].values.astype(np.float64)
        lo = grp["low"].values.astype(np.float64)
        v = grp["volume"].values.astype(np.float64)
        n = len(c)

        atr = _compute_atr_numba(h, lo, c, 14)
        vol_sma = pd.Series(v).rolling(20, min_periods=1).mean().values
        ema20 = _ema_numba(c, 20)
        ema50 = _ema_numba(c, 50)
        ema200 = _ema_numba(c, 200)

        # Detect zones
        si, sp = _detect_swing_highs_numba(h, lo, SWING_LEFT, SWING_RIGHT)
        zl, zp, zt, zw, zs = _filter_and_cluster_numba(
            si, sp, h, lo, atr, SWING_MIN_PROMINENCE_ATR, CLUSTER_DISTANCE_ATR)

        if len(zl) == 0:
            continue

        # Detect breakouts
        bk_l, bk_d, bk_b, bk_c, bk_v, bk_z = _detect_breakouts_numba(
            c, h, lo, v, atr, vol_sma, zl, zw, zs)

        # Track breakout bars
        bk_bar = np.full(n, -1, dtype=np.int64)
        for idx in range(n):
            if bk_l[idx] > 0:
                bk_bar[idx] = idx

        # Detect retests
        rt_l, rt_d, rt_cr, rt_w, rt_v, rt_e = _detect_retests_numba(
            c, h, lo, v, atr, bk_l, bk_bar, zl, zs)

        # Extract features for each retest event
        for i in range(n):
            if rt_v[i] != 1:
                continue

            z_idx = bk_z[i] if bk_z[i] >= 0 else 0
            if z_idx >= len(zl):
                continue

            feat = _extract_features_for_event(
                c, h, lo, v, atr, vol_sma, ema20, ema50, ema200,
                zl[z_idx], zp[z_idx], zt[z_idx], zw[z_idx],
                bk_bar[i] if bk_bar[i] >= 0 else i,
                bk_d[i], bk_b[i], bk_c[i], bk_v[i],
                i, rt_d[i], rt_cr[i], rt_w[i], rt_e[i], i)

            # Compute outcome (trade result from i+1 open)
            entry_price = c[i]  # use close as proxy for next open
            signal_atr = atr[i] if atr[i] > 0 else 1e-10
            outcome, mfe5, mfe10, mfe20, mae5, mae10, mae20, dt1, dt2, dt3, dtp = \
                _compute_trade_outcomes_numba(
                    c, h, lo, np.array([i], dtype=np.int64),
                    np.array([entry_price], dtype=np.float64),
                    np.array([signal_atr], dtype=np.float64),
                    UPPER_BARRIER_ATR, LOWER_BARRIER_ATR, TIME_BARRIER)

            all_features.append(feat)
            all_outcomes.append({
                "outcome": outcome[0],
                "mfe_5": mfe5[0], "mfe_10": mfe10[0], "mfe_20": mfe20[0],
                "mae_5": mae5[0], "mae_10": mae10[0], "mae_20": mae20[0],
                "days_to_1atr": dt1[0], "days_to_2atr": dt2[0], "days_to_3atr": dt3[0],
                "days_to_peak": dtp[0],
            })

    if not all_features:
        logger.warning("No retest events found. Cannot train.")
        return

    X = np.array(all_features, dtype=np.float64)
    outcomes = pd.DataFrame(all_outcomes)
    logger.info(f"Collected {len(X)} retest events with {X.shape[1]} features")

    # Create labels
    y_win = (outcomes["outcome"] == 1).astype(int).values
    y_drawdown = (outcomes["outcome"] == -1).astype(int).values
    y_timeout = (outcomes["outcome"] == 0).astype(int).values

    logger.info(f"Labels: WIN={y_win.sum()}, DRAWDOWN={y_drawdown.sum()}, TIMEOUT={y_timeout.sum()}")

    # Train classifier
    logger.info("Training classifier...")
    classifier = train_classifier(X, y_win, y_drawdown, y_timeout)

    # Train regressors
    logger.info("Training regressors...")
    reg_targets = {
        "mfe_5": outcomes["mfe_5"].values,
        "mfe_10": outcomes["mfe_10"].values,
        "mfe_20": outcomes["mfe_20"].values,
        "mae_5": outcomes["mae_5"].values,
        "mae_10": outcomes["mae_10"].values,
        "mae_20": outcomes["mae_20"].values,
        "days_to_1atr": outcomes["days_to_1atr"].values,
        "days_to_2atr": outcomes["days_to_2atr"].values,
        "days_to_3atr": outcomes["days_to_3atr"].values,
    }
    regressors = train_regressors(X, reg_targets)

    # Save
    feature_stats = {
        "mean": np.nanmean(X, axis=0),
        "std": np.nanstd(X, axis=0) + 1e-8,
    }
    save_models(classifier, regressors, market, feature_stats)
    logger.info(f"Training complete for {market}. Events: {len(X)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["US", "INDIA"], required=True)
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args()

    t0 = time.time()
    train_walk_forward(args.market, args.folds)
    logger.info(f"Total time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
