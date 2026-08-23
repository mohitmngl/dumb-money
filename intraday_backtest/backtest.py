import time
import json
import logging
import numpy as np
from intraday_backtest.config import (
    get_db, init_db, WA_TOTAL_CANDLES, ACCEL_LATEST_CANDLES,
    DEFAULT_CAPITAL, DEFAULT_N_STOCKS, DEFAULT_N_BATCHES
)
from intraday_backtest.batches import load_batches
from intraday_backtest.signals import accel_peak_signal
from intraday_backtest.weighted_alpha import weighted_alpha_batch

logger = logging.getLogger(__name__)


def _get_day_boundaries(timestamps):
    """Identify first and last candle of each trading day.
    Returns set of indices to skip (first and last of each day)."""
    skip = set()
    current_day = None
    day_start_idx = None

    for i, ts in enumerate(timestamps):
        day = ts[:10]  # YYYY-MM-DD
        if day != current_day:
            if current_day is not None and day_start_idx is not None:
                skip.add(i - 1)
            current_day = day
            day_start_idx = i
            skip.add(i)

    if len(timestamps) > 0:
        skip.add(len(timestamps) - 1)

    return skip


def run_backtest(
    symbols, timestamps, price_matrix,
    timeframe="15Min",
    n_batches=DEFAULT_N_BATCHES,
    capital=DEFAULT_CAPITAL,
    margin=1,
    charges=False,
    progress_callback=None,
    run_id=None,
):
    """Run the Intraday Agent backtest.

    Buffer layout: batch_buf is (n_batches, 276) — each row is one batch's
    rolling 276-candle price history. Column `buf_pos` is the latest candle.
    This avoids reading 276 × N_batches per candle; instead we row-slice
    only signaled batches (typically <1% of total).
    """
    init_db()
    N = len(symbols)
    T = len(timestamps)
    logger.info(f"Backtest: {N} stocks, {T} candles, {n_batches} batches, {timeframe}")

    if progress_callback:
        progress_callback(0.0, "Loading batch weights...")

    W_np = np.array(load_batches(n_batches, N, seed=42), dtype=np.float32)
    logger.info(f"Batch matrix: {W_np.shape}")

    if progress_callback:
        progress_callback(0.05, "Computing stock returns...")

    prices = np.array(price_matrix, dtype=np.float64)
    stock_returns = np.diff(prices, axis=0) / prices[:-1]
    stock_returns = np.nan_to_num(stock_returns, nan=0.0, posinf=0.0, neginf=0.0)

    skip_candles = _get_day_boundaries(timestamps)
    logger.info(f"Day boundaries: {len(skip_candles)} skip indices")

    equity_curve = []
    candle_returns = []
    trades_log = []

    equity = float(capital)
    gross_exposure = float(capital) * margin
    peak_equity = equity

    # Transposed buffer: (n_batches, buf_size) — each row = one batch's price history
    buf_size = min(WA_TOTAL_CANDLES, T)
    batch_buf = np.zeros((n_batches, buf_size), dtype=np.float32)
    buf_pos = 0
    buf_fill = 0

    # Precompute column indices for accel (last 20 columns) and WA (all buf_size)
    _accel_cols = np.arange(buf_size - min(ACCEL_LATEST_CANDLES, buf_size), buf_size, dtype=np.intp)
    _all_cols = np.arange(buf_size, dtype=np.intp)

    # Precompute float32 versions for fast BLAS matmul
    W_np_T = W_np.T  # (N, n_batches) float32

    t_start = time.time()
    n_candles_processed = 0

    for t in range(1, T):
        if progress_callback and t % 100 == 0:
            pct = t / T
            elapsed = time.time() - t_start
            rate = n_candles_processed / max(elapsed, 0.01)
            eta = (T - t) / max(rate, 0.001)
            progress_callback(pct, f"Candle {t}/{T} | {rate:.1f} c/s | ETA {eta:.0f}s")

        if t in skip_candles:
            continue

        candle_ret = stock_returns[t - 1].astype(np.float32)  # (N,) float32 — CRITICAL for BLAS speed

        # Batch returns: (n_batches,) — single matmul
        batch_ret = candle_ret @ W_np_T  # float32 @ float32 = fast

        # Write new column into transposed buffer
        if buf_fill < buf_size:
            if buf_fill == 0:
                batch_buf[:, 0] = 100.0
            else:
                prev_col = (buf_pos - 1) % buf_size
                batch_buf[:, buf_pos] = batch_buf[:, prev_col] * (1.0 + batch_ret)
            buf_pos = (buf_pos + 1) % buf_size
            buf_fill += 1
        else:
            prev_col = (buf_pos - 1) % buf_size
            batch_buf[:, buf_pos] = batch_buf[:, prev_col] * (1.0 + batch_ret)
            buf_pos = (buf_pos + 1) % buf_size

        if buf_fill < buf_size:
            equity_curve.append({
                "timestamp": timestamps[t],
                "equity": equity,
                "drawdown": 0.0
            })
            continue

        # === ACCEL PEAK SIGNAL ===
        # Read last 20 columns for ALL batches: (n_batches, 20) — contiguous
        bp_latest20 = batch_buf[:, _accel_cols].T  # (20, n_batches)
        signal = accel_peak_signal(bp_latest20)

        n_sig = int(np.sum(signal))
        if n_sig == 0:
            equity_curve.append({
                "timestamp": timestamps[t],
                "equity": equity,
                "drawdown": 0.0
            })
            continue

        # === WEIGHTED ALPHA — only for signaled batches ===
        # Row-slice first (cheap!), then read all 276 columns
        # This reads n_sig × 276 instead of n_batches × 276
        signal_batches = batch_buf[signal][:, _all_cols].T  # (276, n_sig)
        wa = weighted_alpha_batch(signal_batches)

        positive_mask = wa > 0
        n_eligible = int(np.sum(positive_mask))
        if n_eligible == 0:
            equity_curve.append({
                "timestamp": timestamps[t],
                "equity": equity,
                "drawdown": 0.0
            })
            continue

        # === ALLOCATION ===
        eligible_W = W_np[signal][positive_mask]
        eligible_wa = wa[positive_mask]

        A_TOTAL = gross_exposure
        batch_amounts = A_TOTAL * eligible_wa / float(np.sum(eligible_wa))

        stock_targets = eligible_W.T @ batch_amounts

        gross_notional = float(np.sum(np.abs(stock_targets)))
        if gross_notional > 0:
            scale = A_TOTAL / gross_notional
            stock_targets = stock_targets * scale
        else:
            equity_curve.append({
                "timestamp": timestamps[t],
                "equity": equity,
                "drawdown": 0.0
            })
            continue

        pnl = float(np.sum(stock_targets * candle_ret))

        if charges:
            turnover = float(np.sum(np.abs(stock_targets)))
            sec_fee = turnover * 8.10 / 1_000_000
            taf_fee = turnover * 0.000166
            pnl -= (sec_fee + taf_fee)

        equity += pnl
        peak_equity = max(peak_equity, equity)
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0

        equity_curve.append({
            "timestamp": timestamps[t],
            "equity": equity,
            "drawdown": dd
        })

        candle_ret_pct = pnl / (equity - pnl) if (equity - pnl) > 0 else 0
        candle_returns.append(candle_ret_pct)
        n_candles_processed += 1

        if n_candles_processed <= 10 or n_candles_processed % 100 == 0:
            trades_log.append({
                "timestamp": timestamps[t],
                "pnl": pnl,
                "equity": equity,
                "n_signals": n_sig,
                "n_eligible": n_eligible,
            })

    total_time = time.time() - t_start
    logger.info(f"Backtest: {n_candles_processed} candles in {total_time:.1f}s")

    eq_arr = np.array([e["equity"] for e in equity_curve]) if equity_curve else np.array([capital])

    result = {
        "timeframe": timeframe,
        "n_stocks": N,
        "n_batches": n_batches,
        "capital": capital,
        "margin": margin,
        "charges": charges,
        "candles_processed": n_candles_processed,
        "total_time_s": total_time,
        "final_equity": float(eq_arr[-1]) if len(eq_arr) > 0 else capital,
        "equity_curve": equity_curve,
        "candle_returns": candle_returns,
        "n_signals_avg": float(np.mean([t.get("n_signals", 0) for t in trades_log])) if trades_log else 0,
        "n_eligible_avg": float(np.mean([t.get("n_eligible", 0) for t in trades_log])) if trades_log else 0,
    }

    if progress_callback:
        progress_callback(1.0, "Backtest complete")

    return result


def _sanitize_for_json(obj):
    """Replace inf/nan with None for valid JSON."""
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        if obj == float('inf') or obj == float('-inf'):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def save_run(result, db=None):
    """Save backtest result to DB."""
    own_db = db is None
    if own_db:
        init_db()
        db = get_db()
    try:
        eq_json = json.dumps(_sanitize_for_json(result.get("equity_curve", [])))
        metrics = {k: v for k, v in result.items() if k != "equity_curve"}
        metrics_json = json.dumps(_sanitize_for_json(metrics))

        cursor = db.execute(
            "INSERT INTO backtest_runs (timeframe, n_stocks, n_batches, capital, margin, charges, "
            "status, progress, result_json, equity_json, metrics_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                result.get("timeframe"),
                result.get("n_stocks"),
                result.get("n_batches"),
                result.get("capital"),
                result.get("margin", 1),
                1 if result.get("charges") else 0,
                "complete",
                1.0,
                metrics_json,
                eq_json,
                metrics_json,
            )
        )
        db.commit()
        return cursor.lastrowid
    finally:
        if own_db:
            db.close()
