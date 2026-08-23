import json
import logging
import threading
from flask import Blueprint, request, jsonify
from intraday_backtest.config import get_db, init_db, TIMEFRAMES, MAX_DAYS_BACK
from intraday_backtest.data import download_bars, get_top_liquid_symbols, get_cached_bars, get_bar_dates
from intraday_backtest.backtest import run_backtest
from intraday_backtest.metrics import compute_all_metrics
from intraday_backtest.backtest import _sanitize_for_json

logger = logging.getLogger(__name__)

bp = Blueprint("intraday_backtest", __name__)

_progress_lock = threading.Lock()
_download_state = {"progress": 0, "status": "idle", "current_tf": "", "done_tfs": [], "total_bars": 0}
_backtest_state = {"progress": 0, "status": "idle", "result": None}


def _build_price_matrix(used_symbols, timestamps, timeframe):
    """Build price matrix from cached bars with forward-fill for gaps."""
    cached = get_cached_bars(used_symbols, timeframe)
    price_matrix = []
    final_syms = []
    for sym in used_symbols:
        if sym not in cached:
            continue
        sym_prices = {row[0]: row[1] for row in cached[sym]}
        col = [sym_prices.get(ts, 0) for ts in timestamps]
        if sum(1 for p in col if p > 0) >= len(col) * 0.9:
            last_good = 0
            for i, p in enumerate(col):
                if p > 0:
                    last_good = p
                elif last_good > 0:
                    col[i] = last_good
            if all(p > 0 for p in col):
                price_matrix.append(col)
                final_syms.append(sym)
    return price_matrix, final_syms


def _prepare_data(symbols, timeframe, days_back, progress_callback=None):
    """Prepare data: get timestamps, build price matrix. Returns (timestamps, syms, matrix) or raises."""
    max_d = MAX_DAYS_BACK.get(timeframe, 3650)
    days_back = min(days_back, max_d)

    if progress_callback:
        progress_callback(0.0, f"Getting bar dates ({days_back}d)...")

    timestamps, used_symbols = get_bar_dates(symbols, timeframe, days_back=days_back)

    min_needed = 280
    if timeframe in ("1Min", "1Day"):
        min_needed = 50

    if len(timestamps) < min_needed:
        # Auto-extend
        ratios = {"1Min": 2, "5Min": 1, "15Min": 4, "30Min": 8, "1Hour": 1, "1Day": 3}
        extra = max(0, min_needed - len(timestamps)) * ratios.get(timeframe, 1)
        if extra > 0:
            new_days = min(days_back + extra, max_d)
            if progress_callback:
                progress_callback(0.0, f"Extending to {new_days}d for {timeframe}...")
            timestamps, used_symbols = get_bar_dates(symbols, timeframe, days_back=new_days)

    if len(timestamps) < min_needed:
        raise ValueError(f"Only {len(timestamps)} timestamps for {timeframe}, need {min_needed}+")

    if progress_callback:
        progress_callback(0.05, f"Building price matrix ({len(timestamps)} candles, {len(used_symbols)} syms)...")

    price_matrix, final_syms = _build_price_matrix(used_symbols, timestamps, timeframe)

    if len(final_syms) < 10:
        raise ValueError(f"Only {len(final_syms)} symbols with complete data")

    import numpy as np
    price_matrix = np.array(price_matrix).T
    n_stocks = min(200, len(final_syms))
    final_syms = final_syms[:n_stocks]
    price_matrix = price_matrix[:, :n_stocks]

    valid_rows = np.all(price_matrix > 0, axis=1)
    timestamps = [timestamps[i] for i in range(len(timestamps)) if valid_rows[i]]
    price_matrix = price_matrix[valid_rows]

    return timestamps, final_syms, price_matrix


def _save_result(timeframe, n_stocks, n_batches, capital, margin, charges, days_back, result):
    """Save backtest result to saved_results table."""
    try:
        basic = result.get("basic", {})
        risk = result.get("risk", {})
        dist = result.get("distribution", {})
        conn = get_db()
        conn.execute(
            """INSERT INTO saved_results
               (timeframe, n_stocks, n_batches, capital, margin, charges, days_back,
                candles_processed, total_return_pct, sharpe_ratio, max_drawdown_pct,
                win_rate_pct, profit_factor, n_signals_avg, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timeframe, n_stocks, n_batches, capital, margin, int(charges), days_back,
             basic.get("candles_processed", 0),
             basic.get("total_return", 0),
             risk.get("sharpe_ratio", 0),
             risk.get("max_drawdown", 0),
             dist.get("win_rate", 0),
             dist.get("profit_factor", 0),
             result.get("n_signals_avg", 0),
             json.dumps(_sanitize_for_json(result)))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.exception("Failed to save result")


@bp.route("/api/intraday-backtest/times")
def api_times():
    return jsonify({"timeframes": TIMEFRAMES})


@bp.route("/api/intraday-backtest/download-status")
def api_download_status():
    with _progress_lock:
        return jsonify(_download_state)


@bp.route("/api/intraday-backtest/download-all", methods=["POST"])
def api_download_all():
    with _progress_lock:
        if _download_state["status"] == "running":
            return jsonify({"error": "Download already running"}), 409
        _download_state.update({"progress": 0, "status": "running", "current_tf": "", "done_tfs": [], "total_bars": 0})

    def _worker():
        try:
            init_db()
            symbols = get_top_liquid_symbols(200)
            logger.info(f"Download-all: {len(symbols)} symbols")

            from datetime import datetime, timedelta, timezone
            tf_starts = {
                "1Min": timedelta(days=28),
                "5Min": timedelta(days=10 * 365),
                "15Min": timedelta(days=10 * 365),
                "30Min": timedelta(days=10 * 365),
                "1Hour": timedelta(days=10 * 365),
                "1Day": timedelta(days=10 * 365),
            }

            total_tfs = len(TIMEFRAMES)
            all_bars = 0

            for i, tf in enumerate(TIMEFRAMES):
                with _progress_lock:
                    _download_state["current_tf"] = tf
                    _download_state["progress"] = i / total_tfs

                start = (datetime.now(timezone.utc) - tf_starts[tf]).strftime("%Y-%m-%dT00:00:00Z")
                logger.info(f"Downloading {tf} from {start}")

                def dl_progress(pct, msg):
                    overall = (i + pct) / total_tfs
                    with _progress_lock:
                        _download_state["progress"] = overall

                n = download_bars(symbols, tf, start, progress_callback=dl_progress)
                all_bars += n
                logger.info(f"{tf}: {n} bars written")

                with _progress_lock:
                    _download_state["done_tfs"].append(tf)
                    _download_state["total_bars"] = all_bars

            with _progress_lock:
                _download_state.update({"progress": 1.0, "status": "complete"})

        except Exception as e:
            logger.exception("Download-all failed")
            with _progress_lock:
                _download_state.update({"progress": 0, "status": f"error: {e}"})

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"})


@bp.route("/api/intraday-backtest/run", methods=["POST"])
def api_run():
    data = request.json or {}
    timeframe = data.get("timeframe", "15Min")
    n_batches = int(data.get("n_batches", 1_000_000))
    capital = float(data.get("capital", 10000))
    margin = int(data.get("margin", 1))
    charges = bool(data.get("charges", False))
    days_back = int(data.get("days_back", 3650))

    if timeframe not in TIMEFRAMES:
        return jsonify({"error": "Invalid timeframe"}), 400

    days_back = min(days_back, MAX_DAYS_BACK.get(timeframe, 3650))

    with _progress_lock:
        if _backtest_state["status"] == "running":
            return jsonify({"error": "Backtest already running"}), 409
        _backtest_state.update({"progress": 0, "status": "running", "result": None})

    def _run():
        try:
            init_db()
            symbols = get_top_liquid_symbols(200)

            def progress_cb(pct, msg):
                with _progress_lock:
                    _backtest_state["progress"] = pct
                    _backtest_state["status"] = msg

            timestamps, final_syms, price_matrix = _prepare_data(symbols, timeframe, days_back, progress_cb)

            with _progress_lock:
                _backtest_state["status"] = f"Running: {len(final_syms)} stocks, {len(timestamps)} candles, {n_batches} batches"
                _backtest_state["progress"] = 0.3

            def bt_progress(pct, msg):
                with _progress_lock:
                    _backtest_state["progress"] = 0.3 + pct * 0.7
                    _backtest_state["status"] = f"backtest: {msg}"

            result = run_backtest(
                symbols=final_syms,
                timestamps=timestamps,
                price_matrix=price_matrix,
                timeframe=timeframe,
                n_batches=n_batches,
                capital=capital,
                margin=margin,
                charges=charges,
                progress_callback=bt_progress,
            )

            with _progress_lock:
                _backtest_state["status"] = "Computing metrics..."
                _backtest_state["progress"] = 0.95

            metrics = compute_all_metrics(result, capital)
            result["metrics"] = metrics

            # Save to DB
            _save_result(timeframe, len(final_syms), n_batches, capital, margin, charges, days_back, result)

            with _progress_lock:
                _backtest_state.update({"progress": 1.0, "status": "complete", "result": metrics})

            logger.info(f"Backtest complete: {result.get('final_equity')}")

        except Exception as e:
            logger.exception("Backtest failed")
            with _progress_lock:
                _backtest_state.update({"progress": 0, "status": f"error: {e}"})

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@bp.route("/api/intraday-backtest/progress")
def api_progress():
    with _progress_lock:
        bt = dict(_backtest_state)
    return jsonify(bt)


@bp.route("/api/intraday-backtest/data-status")
def api_data_status():
    init_db()
    conn = get_db()
    try:
        info = {}
        for tf in TIMEFRAMES:
            row = conn.execute(
                "SELECT COUNT(DISTINCT symbol), COUNT(*) FROM bars WHERE timeframe=?", (tf,)
            ).fetchone()
            info[tf] = {"symbols": row[0], "bars": row[1]}
        return jsonify(info)
    finally:
        conn.close()


@bp.route("/api/intraday-backtest/saved-results")
def api_saved_results():
    """Get all saved backtest results grouped by timeframe."""
    init_db()
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, timeframe, created_at, n_stocks, n_batches, capital, margin, charges,
                      days_back, candles_processed, total_return_pct, sharpe_ratio,
                      max_drawdown_pct, win_rate_pct, profit_factor, n_signals_avg, result_json
               FROM saved_results ORDER BY timeframe, created_at DESC"""
        ).fetchall()
        results = {}
        for r in rows:
            tf = r[1]
            if tf not in results:
                results[tf] = []
            results[tf].append({
                "id": r[0], "timeframe": r[1], "created_at": r[2],
                "n_stocks": r[3], "n_batches": r[4], "capital": r[5],
                "margin": r[6], "charges": r[7], "days_back": r[8],
                "candles_processed": r[9], "total_return_pct": r[10],
                "sharpe_ratio": r[11], "max_drawdown_pct": r[12],
                "win_rate_pct": r[13], "profit_factor": r[14],
                "n_signals_avg": r[15], "result_json": r[16],
            })
        return jsonify(results)
    finally:
        conn.close()


@bp.route("/api/intraday-backtest/saved-results/<int:result_id>")
def api_saved_result_detail(result_id):
    """Get full detail of a saved result."""
    init_db()
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT result_json FROM saved_results WHERE id=?", (result_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(json.loads(row[0]))
    finally:
        conn.close()


@bp.route("/api/intraday-backtest/delete-result/<int:result_id>", methods=["DELETE"])
def api_delete_result(result_id):
    init_db()
    conn = get_db()
    try:
        conn.execute("DELETE FROM saved_results WHERE id=?", (result_id,))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()
