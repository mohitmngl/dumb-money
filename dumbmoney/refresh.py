import threading
import time
import logging
import json
import os

_perf_logger = logging.getLogger("refresh_perf")
try:
    _perf_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "refresh_perf.log",
    )
    _perf_h = logging.FileHandler(_perf_file, encoding="utf-8")
    _perf_h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _perf_logger.addHandler(_perf_h)
    _perf_logger.setLevel(logging.INFO)
    _perf_logger.propagate = False
except Exception:
    pass


class _timed:
    """Context manager: PERF|phase|seconds|k=v,... lines to refresh_perf log."""

    def __init__(self, phase, **tags):
        self.phase = phase
        self.tags = tags

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        dt = time.perf_counter() - self.t0
        tag = ",".join(f"{k}={v}" for k, v in self.tags.items())
        _perf_logger.info(f"PERF|{self.phase}|{dt:.2f}s|{tag}")
        return False
from datetime import datetime
from dumbmoney.db import get_db, init_all_dbs, ensure_schema, migrate_nulls
from dumbmoney.config import DB_PATHS
from dumbmoney.engine import (
    vectorized_stats_pass, update_asset_info, update_historical_screener,
)

logger = logging.getLogger(__name__)

STEPS = [
    {"name": "Sync universe", "weight": 0.03},
    {"name": "Download bars", "weight": 0.25},
    {"name": "Vectorized stats", "weight": 0.20},
    {"name": "Fundamentals/PrePost/AI", "weight": 0.27},
    {"name": "Historical screener", "weight": 0.25},
]

_refresh_threads = {}
_cancel_events = {}
_refresh_context = threading.local()
_refresh_lock = threading.Lock()


def _norm_market(market=None):
    return "INDIA" if str(market).upper() == "INDIA" else "US"


def _current_market():
    return _norm_market(getattr(_refresh_context, "market", "US"))


def _market_event(market=None):
    market = _norm_market(market or _current_market())
    if market not in _cancel_events:
        _cancel_events[market] = threading.Event()
    return _cancel_events[market]


def reset_stale_status():
    """Reset any persisted 'running'/'cancelling' status on startup (thread is dead)."""
    for market in DB_PATHS:
        try:
            status = get_refresh_status(market)
            if status.get("status") in ("running", "cancelling"):
                _persist_status({**status, "status": "idle", "phase": "Cancelled (server restart)"}, market)
        except Exception:
            pass


_last_persist_time = {}
_last_step_written = {}
_status_cache_lock = threading.Lock()

def _persist_status(status_dict, market=None, force=False):
    try:
        market = _norm_market(market or status_dict.get("market") or _current_market())
        status_dict["market"] = market
        now = time.time()
        is_terminal = status_dict.get("status") in ("complete", "error", "cancelled", "idle")
        is_step_change = status_dict.get("step_current") != _last_step_written.get(market)
        with _status_cache_lock:
            last_time = _last_persist_time.get(market, 0)
            if not force and not is_terminal and not is_step_change and (now - last_time) < 1.0:
                return
            _last_persist_time[market] = now
            if is_step_change:
                _last_step_written[market] = status_dict.get("step_current")
        conn = get_db(market)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('refresh_status', ?)",
            (json.dumps(status_dict),)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to persist refresh status: {e}")


def get_refresh_status(market="US"):
    market = _norm_market(market)
    try:
        conn = get_db(market)
        row = conn.execute("SELECT value FROM settings WHERE key='refresh_status'").fetchone()
        conn.close()
        if row and row[0]:
            return json.loads(row[0])
    except Exception:
        pass
    return {
        "status": "idle", "market": market, "step_current": 0, "step_total": len(STEPS),
        "step_name": "", "phase": "", "symbols_total": 0, "symbols_done": 0,
        "overall_pct": 0.0, "step_pct": 0.0, "current_symbol": "",
        "elapsed_sec": 0, "eta_sec": 0, "started_at": 0, "errors": [],
    }


def _update_status(**kwargs):
    market = _norm_market(kwargs.get("market") or _current_market())
    kwargs["market"] = market
    status = get_refresh_status(market)
    old_overall = status.get("overall_pct", 0)
    status.update(kwargs)
    now = time.time()
    started = status.get("started_at", 0)
    if started and now > started:
        elapsed = now - started
        status["elapsed_sec"] = int(elapsed)
        new_overall = status.get("overall_pct", 0)
        if new_overall > 1 and elapsed > 5:
            rate = new_overall / elapsed
            status["eta_sec"] = int((100 - new_overall) / max(rate, 0.001))
        step = status.get("step_current", 0)
        step_pct = status.get("step_pct", 0)
        status["step_detail"] = f"Step {step+1}/{len(STEPS)}: {STEPS[step]['name']} ({int(step_pct)}%)"
    _persist_status(status, market)
    return status


def _compute_overall_pct(status):
    total_weight = sum(s["weight"] for s in STEPS)
    pct = 0.0
    for i, step in enumerate(STEPS):
        if i < status["step_current"]:
            pct += step["weight"] * 100
        elif i == status["step_current"]:
            pct += step["weight"] * status["step_pct"]
    return round(pct / total_weight, 1)


def _check_cancel(market=None):
    market = _norm_market(market or _current_market())
    if _market_event(market).is_set():
        _update_status(status="cancelled", market=market)
        return True
    return False


def _market_date(market=None):
    """Return today's date in the market's local timezone (not IST)."""
    from datetime import datetime
    import pytz
    market = _norm_market(market)
    now = datetime.now(pytz.utc)
    if market == "US":
        return now.astimezone(pytz.timezone("US/Eastern")).date()
    else:
        return now.astimezone(pytz.timezone("Asia/Kolkata")).date()


def _last_weekday_cutoff(market=None, days_back=3):
    from datetime import date, timedelta
    d = _market_date(market) - timedelta(days=days_back)
    us_holidays = set()
    if _norm_market(market) == "US":
        try:
            from pandas.tseries.holiday import USFederalHolidayCalendar
            cal = USFederalHolidayCalendar()
            start = d.replace(month=1, day=1)
            end = d.replace(month=12, day=31)
            us_holidays = {ts.date() for ts in cal.holidays(start=start, end=end)}
        except Exception:
            us_holidays = set()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    while d in us_holidays:
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _normal_refresh_warmup_start(days=450, market=None):
    from datetime import timedelta
    return (_market_date(market) - timedelta(days=days)).strftime("%Y-%m-%d")


def _latest_expected_bar(market=None):
    """Most recent trading date that should have a finalized daily bar
    (walks back over weekends and, for US, federal holidays)."""
    return _last_weekday_cutoff(market, days_back=0)


def _market_is_open_now(market=None):
    """Check if market is currently in trading hours."""
    from datetime import datetime, time as dt_time
    import pytz
    now = datetime.now(pytz.utc)
    market = _norm_market(market)
    if market == "US":
        et = pytz.timezone("US/Eastern")
        local = now.astimezone(et)
        open_time = dt_time(9, 30)
        close_time = dt_time(16, 0)
    else:
        ist = pytz.timezone("Asia/Kolkata")
        local = now.astimezone(ist)
        open_time = dt_time(9, 0)
        close_time = dt_time(16, 0)
    if local.weekday() >= 5:
        return False
    return open_time <= local.time() <= close_time


def run_refresh(market="US"):
    global _refresh_threads, _cancel_events
    market = _norm_market(market)
    event = _market_event(market)

    with _refresh_lock:
        status = get_refresh_status(market)
        if status.get("status") == "running":
            event.set()
            thread = _refresh_threads.get(market)
            if thread and thread.is_alive():
                thread.join(timeout=5)
            event.clear()

        event.clear()
        _update_status(
            status="running", market=market, step_current=0, step_total=len(STEPS), overall_pct=0,
            started_at=time.time(), errors=[], step_name="Starting...",
            phase="Initializing...", symbols_total=0, symbols_done=0,
            step_pct=0, current_symbol="", elapsed_sec=0, eta_sec=0,
            new_stocks_count=0
        )
        _refresh_threads[market] = threading.Thread(target=_refresh_worker, args=(market,), daemon=True)
        _refresh_threads[market].start()
    return True


def cancel_refresh(market="US"):
    market = _norm_market(market)
    _market_event(market).set()
    _update_status(status="cancelled", market=market)
    return True


def _refresh_worker(market):
    _refresh_context.market = _norm_market(market)
    start_time = time.time()
    _refresh_t0 = time.perf_counter()
    step_errors = []

    try:
        if _check_cancel():
            return

        _update_status(status="running", step_current=0, step_name="Sync universe", phase="Syncing assets...", step_pct=0, overall_pct=0)
        if market == "US":
            from dumbmoney.data_us import sync_assets
            n = sync_assets()
            # Update US index composition snapshots
            for fn_name, label in [
                ("update_sp500_constituents", "S&P 500"),
                ("update_nasdaq100_constituents", "Nasdaq 100"),
                ("update_russell2000_constituents", "Russell 2000"),
                ("update_dow30_constituents", "Dow Jones 30"),
            ]:
                try:
                    from dumbmoney import data_us
                    fn = getattr(data_us, fn_name)
                    added, removed = fn()
                    if added >= 0:
                        logger.info(f"{label} snapshot: +{added}/-{removed}")
                except Exception as e:
                    logger.warning(f"{label} snapshot failed: {e}")
        else:
            from dumbmoney.data_india import sync_india_assets
            n = sync_india_assets()
            # Update Nifty 500 composition snapshot (additions/removals)
            try:
                from dumbmoney.data_india import update_nifty500_constituents
                n500_added, n500_removed = update_nifty500_constituents()
                if n500_added >= 0:
                    logger.info(f"Nifty 500 snapshot: +{n500_added}/-{n500_removed}")
            except Exception as e:
                logger.warning(f"Nifty 500 snapshot failed: {e}")
            # Update Nifty 50 composition snapshot
            try:
                from dumbmoney.data_india import update_nifty50_constituents
                n50_added, n50_removed = update_nifty50_constituents()
                if n50_added >= 0:
                    logger.info(f"Nifty 50 snapshot: +{n50_added}/-{n50_removed}")
            except Exception as e:
                logger.warning(f"Nifty 50 snapshot failed: {e}")
            # Update F&O stock composition snapshot
            try:
                from dumbmoney.data_india import update_fo_constituents
                fo_added, fo_removed = update_fo_constituents()
                if fo_added >= 0:
                    logger.info(f"F&O snapshot: +{fo_added}/-{fo_removed}")
            except Exception as e:
                logger.warning(f"F&O snapshot failed: {e}")
        s = _update_status(symbols_total=n, symbols_done=n, step_pct=100)
        s["overall_pct"] = _compute_overall_pct(s)
        _persist_status(s)

        if _check_cancel():
            return

        _update_status(step_current=1, step_name="Download bars", phase="Downloading daily bars...", step_pct=0, symbols_done=0)
        updated_symbols = []
        with _timed("download", market=market):
            if market == "US":
                updated_symbols = _download_us_bars_incremental(market)
            else:
                updated_symbols = _download_india_bars(market) or []
        _perf_logger.info(f"PERF|download_updated|symbols={len(updated_symbols)}")

        if _check_cancel():
            return

        if updated_symbols:
            stats_symbols = updated_symbols
            label = f"{len(updated_symbols)} updated"
        else:
            # No bars changed. Stats are already current from the run that
            # downloaded them — a no-change refresh must be a no-op (AGENTS.md /
            # SPEED.md contract). Full recompute only if stats never populated.
            try:
                from dumbmoney.db import get_db as _gdb
                _c = _gdb(market)
                stats_rows = _c.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
                _c.close()
            except Exception:
                stats_rows = 0
            stats_symbols = [] if stats_rows > 0 else None
            label = "no changes (no-op)" if stats_rows > 0 else "all (stats empty — full recompute)"

        # If most stats are stale (>1 day old), force full recompute
        if stats_symbols and market == "INDIA":
            try:
                conn = get_db(market)
                stale_count = conn.execute(
                    "SELECT COUNT(*) FROM stats WHERE last_updated < date('now', '-1 day')"
                ).fetchone()[0]
                total_count = conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
                if total_count > 0 and stale_count > total_count * 0.5:
                    stats_symbols = None
                    label = f"all (full recompute — {stale_count}/{total_count} stats stale)"
            except Exception:
                pass
        _update_status(step_current=2, step_name="Stats + Fundamentals (parallel)", phase="Running stats and fundamentals in parallel...", step_pct=0)

        from concurrent.futures import ThreadPoolExecutor, as_completed

        _stats_pct = {"val": 0}
        _fund_pct = {"val": 0}
        _prepost_pct = {"val": 0}
        _step_lock = threading.Lock()

        def _parallel_progress():
            with _step_lock:
                combined = (_stats_pct["val"] + _fund_pct["val"] + _prepost_pct["val"]) / 3.0
            s = _update_status(step_current=2, step_pct=round(combined, 1))
            s["overall_pct"] = _compute_overall_pct(s)
            _persist_status(s)

        def _run_stats():
            def _stats_progress(done, total):
                if _check_cancel():
                    return
                pct = round(done / total * 100, 1) if total else 100
                _stats_pct["val"] = pct
                _parallel_progress()
            try:
                with _timed("stats_pass", symbols=len(stats_symbols) if stats_symbols else 0):
                    n_stats = vectorized_stats_pass(market, only_symbols=stats_symbols, progress_callback=_stats_progress)
            except Exception as e:
                logger.error(f"Stats computation failed: {e}", exc_info=True)
                step_errors.append(f"Step 2 (stats): {e}")
                n_stats = 0
            _stats_pct["val"] = 100
            _parallel_progress()
            return n_stats

        def _run_fundamentals():
            def _asset_progress(pct, msg):
                if _check_cancel(market):
                    return
                _fund_pct["val"] = pct
                _parallel_progress()
            with _timed("asset_info", symbols=len(stats_symbols) if stats_symbols else 0):
                update_asset_info(market, progress_callback=_asset_progress, only_symbols=stats_symbols)
            _fund_pct["val"] = 100
            _parallel_progress()

        def _run_prepost():
            if market != "US":
                _prepost_pct["val"] = 100
                return
            from dumbmoney.data_us import update_pre_post_prices
            def _prepost_progress(pct, msg):
                if _check_cancel(market):
                    return
                _prepost_pct["val"] = pct
                _parallel_progress()
            with _timed("prepost", symbols=len(stats_symbols) if stats_symbols else 0):
                update_pre_post_prices(market, progress_callback=_prepost_progress, symbols=stats_symbols)
            _prepost_pct["val"] = 100
            _parallel_progress()

        def _run_ai():
            _profit_pct["val"] = 100
            _parallel_progress()

        futures = {}
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures[ex.submit(_run_stats)] = "stats"
            futures[ex.submit(_run_prepost)] = "prepost"
            for f in as_completed(futures):
                exc = f.exception()
                if exc:
                    logger.error(f"Parallel refresh step {futures[f]} failed: {exc}")
                    step_errors.append(f"Step 2 ({futures[f]}): {exc}")

        def _asset_progress(pct, msg):
            if _check_cancel(market):
                return
            s = _update_status(step_pct=round(pct * 0.5, 1), phase=f"Asset info: {msg}")
            s["overall_pct"] = _compute_overall_pct(s)
            _persist_status(s)
        with _timed("asset_info", symbols=len(stats_symbols) if stats_symbols else 0):
            update_asset_info(market, progress_callback=_asset_progress, only_symbols=stats_symbols)

        s = _update_status(step_pct=100)
        s["overall_pct"] = _compute_overall_pct(s)
        _persist_status(s)

        _update_status(status="running", step_current=4, step_name="Historical screener", phase="Filling history...", step_pct=0, overall_pct=80)

        def _bg_progress(pct, msg):
            if _check_cancel():
                return
            s = _update_status(step_pct=pct, phase=msg)
            s["overall_pct"] = _compute_overall_pct(s)
            _persist_status(s)

        hist_symbols = updated_symbols  # [] = deliberate no-op; never None
        if not hist_symbols:
            _bg_progress(5, "Historical screener: no symbols changed")
            _bg_progress(100, "History already current")
        else:
            _bg_progress(5, f"Historical screener: {len(hist_symbols)} symbols")
            try:
                with _timed("historical_update", symbols=len(hist_symbols)):
                    update_historical_screener(market, progress_callback=_bg_progress, only_symbols=hist_symbols, cancel_check=_check_cancel)
            except Exception as e:
                logger.error(f"Historical screener failed: {e}", exc_info=True)
                step_errors.append(f"Step 5 (historical screener): {e}")
            _bg_progress(100, "History updated")

        # Retest v2: too slow for refresh (2.4s/sym). Compute on demand only.
        _bg_progress(100, "Retest v2: skipped (compute on demand)")

        if step_errors:
            final_phase = f"Done with {len(step_errors)} warning(s)"
        elif not updated_symbols:
            final_phase = "No new bars — all symbols already current"
        else:
            final_phase = "All done!"
        has_critical = any("stats" in e.lower() or "fatal" in e.lower() for e in step_errors)
        final_status = "error" if has_critical else "complete"
        _perf_logger.info(f"PERF|refresh_total|{time.perf_counter() - _refresh_t0:.2f}s|market={market},status={final_status}")
        s = _update_status(step_pct=100, overall_pct=100, status=final_status,
                           step_name="Complete", phase=final_phase, errors=step_errors)
        _persist_status(s)

    except Exception as e:
        if _check_cancel():
            return
        logger.error(f"Refresh error: {e}", exc_info=True)
        try:
            _update_status(status="error", errors=step_errors + [str(e)], phase=f"Error: {e}")
        except Exception:
            logger.error(f"Failed to write error status: {e}", exc_info=True)
    except BaseException as e:
        logger.critical(f"Refresh fatal: {type(e).__name__}: {e}", exc_info=True)
        try:
            _update_status(status="error", errors=step_errors + [str(e)], phase=f"Fatal: {e}")
        except Exception:
            pass


def _record_new_ipos(conn, new_symbols):
    """Persist first-seen date for symbols that have no bars yet (new IPOs/listings).
    They are downloaded with a warm-up window now and re-checked on every refresh
    until their first bars appear."""
    if not new_symbols:
        return
    today = _market_date().strftime("%Y-%m-%d")
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ipos (
                 symbol TEXT PRIMARY KEY, first_seen TEXT, first_bar TEXT)"""
        )
        conn.executemany(
            "INSERT OR IGNORE INTO ipos (symbol, first_seen) VALUES (?, ?)",
            [(s, today) for s in new_symbols],
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to record IPOs: {e}")


def _mark_ipos_first_bar(conn, updated_symbols):
    """Stamp the first bar date for IPOs once their bars arrive."""
    if not updated_symbols:
        return
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ipos'"
        ).fetchone()
        if not row:
            return
        pending = conn.execute(
            "SELECT symbol FROM ipos WHERE first_bar IS NULL"
        ).fetchall()
        pending_set = {r[0] for r in pending} & set(updated_symbols)
        for sym in pending_set:
            first = conn.execute(
                "SELECT MIN(date) FROM bars WHERE symbol=? AND timeframe='1Day'", (sym,)
            ).fetchone()[0]
            if first:
                conn.execute(
                    "UPDATE ipos SET first_bar=? WHERE symbol=? AND first_bar IS NULL",
                    (first, sym),
                )
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to stamp IPO first bars: {e}")


def _next_download_start(last_bar, market_open):
    """Start date for the next incremental download of one symbol.

    Always re-fetch inclusively from the last stored bar so that:
    - a mid-market refresh's partial bar is replaced by the finalized bar later,
    - a next-day refresh picks up yesterday's final close plus today,
    - multiple same-day refreshes keep updating the current day's bar.
    """
    if not last_bar:
        return None
    return last_bar  # inclusive: re-download the last bar to correct partial data


def _download_us_bars_incremental(market, allow_backfill=False, symbols=None):
    from dumbmoney.db import get_db
    from dumbmoney.data_us import download_bars

    conn = get_db(market)
    explicit_symbols = symbols is not None
    if symbols is not None:
        symbols = sorted(set(symbols))
        if not symbols:
            _update_status(step_pct=100, symbols_total=0, symbols_done=0)
            return []
    else:
        symbols = [r[0] for r in conn.execute(
            """SELECT symbol FROM assets
               WHERE status='active' AND tradable=1 AND COALESCE(exchange, '') <> 'OTC'"""
        ).fetchall()]
    if not symbols:
        symbols = [r[0] for r in conn.execute(
            """WITH RECURSIVE s(sym) AS (
               SELECT (SELECT MIN(symbol) FROM bars WHERE timeframe='1Day')
               UNION ALL
               SELECT (SELECT MIN(symbol) FROM bars WHERE timeframe='1Day' AND symbol > s.sym)
               FROM s WHERE s.sym IS NOT NULL
             )
             SELECT sym FROM s WHERE sym IS NOT NULL"""
        ).fetchall()]

    # Per-asset indexed latest-bar lookup only (MIN() is backfill-only; skipping it
    # halves the planning scan on the huge bars table).
    oldest_select = ("(SELECT MIN(b.date) FROM bars b "
                     "WHERE b.symbol=a.symbol AND b.timeframe='1Day')"
                     if allow_backfill else "NULL")
    if explicit_symbols:
        placeholders = ",".join("?" * len(symbols))
        date_rows = conn.execute(
            f"""SELECT symbol, MAX(d), NULL FROM (
                    SELECT symbol, date AS d FROM bars
                    WHERE timeframe='1Day' AND symbol IN ({placeholders})
                ) GROUP BY symbol""",
            symbols,
        ).fetchall()
        date_map = {r[0]: (r[1], None) for r in date_rows}
        if allow_backfill:
            od_rows = conn.execute(
                f"SELECT symbol, MIN(date) FROM bars WHERE timeframe='1Day' AND symbol IN ({placeholders}) GROUP BY symbol",
                symbols,
            ).fetchall()
            for r in od_rows:
                if r[0] in date_map:
                    date_map[r[0]] = (date_map[r[0]][0], r[1])
    else:
        _update_status(phase="Planning: scanning stored dates...", symbols_total=len(symbols), symbols_done=0)
        asset_syms = [r[0] for r in conn.execute(
            "SELECT symbol FROM assets WHERE status='active' AND tradable=1 AND COALESCE(exchange, '') <> 'OTC'"
        ).fetchall()]
        date_map = {}
        chunk_size = 400
        for ci in range(0, len(asset_syms), chunk_size):
            if _check_cancel(market):
                conn.close()
                return []
            chunk = asset_syms[ci:ci + chunk_size]
            placeholders_a = ",".join("?" * len(chunk))
            date_rows = conn.execute(
                f"""SELECT a.symbol,
                          (SELECT MAX(b.date) FROM bars b
                           WHERE b.symbol=a.symbol AND b.timeframe='1Day'),
                          {oldest_select}
                   FROM assets a
                   WHERE a.symbol IN ({placeholders_a})""",
                chunk,
            ).fetchall()
            for r in date_rows:
                date_map[r[0]] = (r[1], r[2])
            done = min(ci + chunk_size, len(asset_syms))
            _update_status(
                phase=f"Planning: scanned {done}/{len(asset_syms)} symbols",
                step_pct=round(done / max(len(asset_syms), 1) * 3, 1),
                symbols_total=len(symbols), symbols_done=0,
            )

    if not symbols:
        _update_status(step_pct=100, symbols_total=0, symbols_done=0)
        # Must be [] (deliberate no-op), never None (None means full-market recompute).
        return []

    today_str = _market_date(market).strftime("%Y-%m-%d")
    market_open = _market_is_open_now(market)
    cutoff = _last_weekday_cutoff(market)
    warmup_start = _normal_refresh_warmup_start(450, market)
    BACKFILL_CUTOFF = "2016-01-01"

    # Group symbols by their own next-needed start date so a stale symbol never
    # drags the whole batch, and every symbol resumes exactly from its last bar.
    start_groups = {}
    new_stocks = []
    up_to_date = 0
    backfill_stocks = []
    # Skip only when the stored latest bar is already the newest expected bar:
    # market open -> today, market closed -> latest weekday. Computed once —
    # _latest_expected_bar walks the pandas US-holiday calendar and costs
    # ~100ms; per-symbol it added tens of minutes to every refresh.
    expected_latest = today_str if market_open else _latest_expected_bar(market)
    for sym in symbols:
        ld, od = date_map.get(sym, (None, None))
        if ld is None:
            # Never downloaded: seed from the warm-up window, not 1970.
            start_groups.setdefault(warmup_start, []).append(sym)
            new_stocks.append(sym)
            continue
        if ld >= expected_latest and not market_open:
            up_to_date += 1
            if allow_backfill and od and od > BACKFILL_CUTOFF:
                backfill_stocks.append(sym)
            continue
        start = _next_download_start(ld, market_open)
        start_groups.setdefault(start, []).append(sym)
        if allow_backfill and od and od > BACKFILL_CUTOFF:
            backfill_stocks.append(sym)

    if backfill_stocks:
        bf_set = set(backfill_stocks) - {s for g in start_groups.values() for s in g}
        if bf_set:
            start_groups.setdefault(BACKFILL_CUTOFF, []).extend(sorted(bf_set))

    _record_new_ipos(conn, new_stocks)

    total = sum(len(g) for g in start_groups.values())
    if total == 0:
        _update_status(symbols_total=len(symbols), symbols_done=len(symbols), step_pct=100,
                       phase=f"All {up_to_date} symbols up to date")
        conn.close()
        return []

    new_count = len(new_stocks)
    phase_msg = f"Downloading {total} symbols ({up_to_date} up to date"
    if new_count:
        phase_msg += f", {new_count} new IPOs"
    bf_count = total - sum(1 for g in start_groups.values() for s in g if s not in new_stocks)
    phase_msg += f", {len(start_groups)} date groups)"
    _update_status(symbols_total=total, symbols_done=0, phase=phase_msg, new_stocks_count=new_count)

    updated = []
    group_items = sorted(start_groups.items())
    done_so_far = 0
    for start, group_syms in group_items:
        if _check_cancel(market):
            break
        try:
            def _us_download_progress(done_batches, total_batches):
                pct = round((done_so_far + done_batches / max(total_batches, 1)) / total * 90, 1)
                s = _update_status(step_pct=pct, phase=f"Bars from {start}: batch {done_batches}/{total_batches}")
                s["overall_pct"] = _compute_overall_pct(s)
                _persist_status(s)
            download_bars(group_syms, start_date=start, timeframe="1Day", incremental=False,
                          progress_callback=_us_download_progress, cancel_check=lambda: _check_cancel(market))
            updated.extend(group_syms)
        except Exception as e:
            logger.warning(f"Download error (start={start}, {len(group_syms)} symbols): {e}")
        done_so_far += len(group_syms)
        _update_status(symbols_done=min(done_so_far, total))

    # Snapshot correction: only for symbols we just downloaded (finalizes the
    # current day's IEX bar faster than the bars endpoint).
    if updated:
        try:
            from dumbmoney.data_us import get_snapshots
            snaps = get_snapshots(updated)
            snap_updates = []
            for sym, snap in snaps.items():
                daily = snap.get("dailyBar")
                if not daily:
                    continue
                snap_date = daily.get("t", "")[:10]
                snap_vol = int(daily.get("v", 0))
                if snap_vol <= 0:
                    continue
                snap_updates.append((sym, snap_vol, daily["o"], daily["h"], daily["l"], daily["c"], snap_date))
            if snap_updates:
                corrected = 0
                for sym, snap_vol, so, sh, sl, sc, snap_date in snap_updates:
                    cur = conn.execute(
                        "SELECT volume FROM bars WHERE symbol=? AND timeframe='1Day' AND date=?",
                        (sym, snap_date)
                    ).fetchone()
                    if cur and cur[0] >= snap_vol:
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO bars (symbol, timeframe, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?,?)",
                        (sym, "1Day", snap_date, so, sh, sl, sc, snap_vol)
                    )
                    corrected += 1
                conn.commit()
                if corrected:
                    logger.info(f"Snapshot-corrected {corrected} bars")
        except Exception as e:
            logger.warning(f"Snapshot bar correction failed: {e}")

    _mark_ipos_first_bar(conn, updated)
    conn.close()

    s = _update_status(symbols_done=total, step_pct=100, phase=f"Downloaded {len(updated)} symbols")
    s["overall_pct"] = _compute_overall_pct(s)
    _persist_status(s)

    return updated


def _download_india_bars(market, allow_backfill=False, symbols=None):
    from dumbmoney.data_india import download_bars_india
    from dumbmoney.db import get_db

    conn = get_db(market)
    explicit_symbols = symbols is not None
    if symbols is not None:
        symbols = sorted(set(symbols))
        if not symbols:
            _update_status(step_pct=100, symbols_total=0, symbols_done=0)
            return []
    else:
        # Keep this filter aligned with the per-asset date lookup below: a symbol in
        # `symbols` but missing from `date_map` is treated as brand-new and gets a
        # full-history seed download on every refresh.
        symbols = [r[0] for r in conn.execute(
            "SELECT symbol FROM assets WHERE status='active'").fetchall()]
    if not symbols:
        symbols = [r[0] for r in conn.execute(
            """WITH RECURSIVE s(sym) AS (
               SELECT (SELECT MIN(symbol) FROM bars WHERE timeframe='1Day')
               UNION ALL
               SELECT (SELECT MIN(symbol) FROM bars WHERE timeframe='1Day' AND symbol > s.sym)
               FROM s WHERE s.sym IS NOT NULL
             )
             SELECT sym FROM s WHERE sym IS NOT NULL"""
        ).fetchall()]

    if explicit_symbols:
        placeholders = ",".join("?" * len(symbols))
        date_rows = conn.execute(
            f"""SELECT symbol, MAX(date), MIN(date) FROM bars
                WHERE timeframe='1Day' AND symbol IN ({placeholders})
                GROUP BY symbol""",
            symbols,
        ).fetchall()
        date_map = {row[0]: (row[1], row[2]) for row in date_rows}
    else:
        # oldest-date lookup is only needed for backfill planning; skipping the MIN()
        # correlated subquery halves the planning scan on the huge bars table.
        oldest_select = ("(SELECT MIN(b.date) FROM bars b "
                         "WHERE b.symbol=a.symbol AND b.timeframe='1Day')"
                         if allow_backfill else "NULL")
        _update_status(phase="Planning: scanning stored dates...", symbols_total=len(symbols), symbols_done=0)
        asset_syms = [r[0] for r in conn.execute(
            "SELECT symbol FROM assets WHERE status='active'"
        ).fetchall()]
        date_map = {}
        chunk_size = 400
        for ci in range(0, len(asset_syms), chunk_size):
            if _check_cancel(market):
                conn.close()
                return []
            chunk = asset_syms[ci:ci + chunk_size]
            placeholders_a = ",".join("?" * len(chunk))
            date_rows = conn.execute(
                f"""SELECT a.symbol,
                          (SELECT MAX(b.date) FROM bars b
                           WHERE b.symbol=a.symbol AND b.timeframe='1Day'),
                          {oldest_select}
                   FROM assets a
                   WHERE a.symbol IN ({placeholders_a})""",
                chunk,
            ).fetchall()
            for row in date_rows:
                date_map[row[0]] = (row[1], row[2])
            done = min(ci + chunk_size, len(asset_syms))
            _update_status(
                phase=f"Planning: scanned {done}/{len(asset_syms)} symbols",
                step_pct=round(done / max(len(asset_syms), 1) * 3, 1),
                symbols_total=len(symbols), symbols_done=0,
            )

    if not symbols:
        _update_status(step_pct=100, symbols_total=0, symbols_done=0)
        conn.close()
        return []

    today_str = _market_date(market).strftime("%Y-%m-%d")
    market_open = _market_is_open_now(market)
    BACKFILL_CUTOFF = "2016-01-01"
    NEW_SEED_START = "1970-01-01"  # Yahoo path maps this to range=10y

    # Group by each symbol's own next-needed start date: new symbols get a full
    # seed, current symbols resume inclusively from their own last bar. A new
    # listing must never force the whole batch into a 10-year re-download.
    start_groups = {}
    new_stocks = []
    up_to_date = 0
    backfill_stocks = []
    # Same hoist as the US path: _latest_expected_bar is calendar-walk expensive
    # and symbol-independent.
    expected_latest = today_str if market_open else _latest_expected_bar(market)
    for sym in symbols:
        ld, od = date_map.get(sym, (None, None))
        if ld is None:
            # Never downloaded — full seed (Yahoo range=10y)
            start_groups.setdefault(NEW_SEED_START, []).append(sym)
            new_stocks.append(sym)
            continue
        if ld >= expected_latest and not market_open:
            up_to_date += 1
            if allow_backfill and od and od > BACKFILL_CUTOFF:
                backfill_stocks.append(sym)
            continue
        start_groups.setdefault(ld, []).append(sym)
        if allow_backfill and od and od > BACKFILL_CUTOFF:
            backfill_stocks.append(sym)

    if backfill_stocks:
        bf_set = set(backfill_stocks) - {s for g in start_groups.values() for s in g}
        if bf_set:
            start_groups.setdefault(BACKFILL_CUTOFF, []).extend(sorted(bf_set))

    _record_new_ipos(conn, new_stocks)

    total = sum(len(g) for g in start_groups.values())
    if total == 0:
        _update_status(symbols_total=len(symbols), symbols_done=len(symbols), step_pct=100,
                       phase=f"All {up_to_date} symbols up to date")
        conn.close()
        return []

    new_count = len(new_stocks)
    phase_msg = f"Downloading {total} symbols ({up_to_date} up to date"
    if new_count:
        phase_msg += f", {new_count} new"
    phase_msg += f", {len(start_groups)} date groups)"
    _update_status(symbols_total=total, symbols_done=0, phase=phase_msg, new_stocks_count=new_count)

    updated = []
    group_items = sorted(start_groups.items())
    done_so_far = 0
    for start, group_syms in group_items:
        if _check_cancel(market):
            break
        try:
            def _india_progress(done, total_syms):
                pct = round((done_so_far + done) / total * 100, 1)
                s = _update_status(step_pct=pct, symbols_done=min(done_so_far + done, total))
                s["overall_pct"] = _compute_overall_pct(s)
                _persist_status(s)
            download_bars_india(group_syms, start_date=start,
                                cancel_check=lambda: _check_cancel(market),
                                progress_callback=_india_progress)
            updated.extend(group_syms)
        except Exception as e:
            logger.warning(f"India download error (start={start}, {len(group_syms)} symbols): {e}")
        done_so_far += len(group_syms)

    # Fill gaps from NSE bhavcopy (catches Yahoo misses on recent trading days)
    # Yfinance is primary; bhavcopy fills EQ+BE gaps where Yahoo returned nothing.
    try:
        from dumbmoney.data_india import fill_gaps_from_bhavcopy, backfill_new_bhavcopy_symbols
        def _bhav_progress(msg):
            s = _update_status(phase=msg)
            s["overall_pct"] = _compute_overall_pct(s)
            _persist_status(s)
        dates_filled, bars_added, bhav_symbols = fill_gaps_from_bhavcopy(
            series=['EQ', 'BE'], coverage_threshold=0.95,
            cancel_check=lambda: _check_cancel(market), progress_callback=_bhav_progress)
        if bars_added > 0:
            logger.info(f"Bhavcopy filled {bars_added} bars across {dates_filled} dates")
            s = _update_status(phase=f"Bhavcopy filled {bars_added} bars")
            s["overall_pct"] = _compute_overall_pct(s)
            _persist_status(s)
            # Add bhavcopy symbols to updated list so stats get computed
            if bhav_symbols:
                updated = list(set(updated) | set(bhav_symbols))

        # Backfill new symbols that have very few bars (e.g. 1-day bhavcopy only)
        backfilled_syms = backfill_new_bhavcopy_symbols(
            max_bars_threshold=50, cancel_check=lambda: _check_cancel(market),
            progress_callback=_bhav_progress, return_symbols=True)
        if backfilled_syms:
            s = _update_status(phase=f"Backfilled {len(backfilled_syms)} new symbols via NSE")
            s["overall_pct"] = _compute_overall_pct(s)
            _persist_status(s)
            # Add backfilled symbols so stats/history pick them up this same run
            updated = list(set(updated) | set(backfilled_syms))
    except Exception as e:
        logger.warning(f"Bhavcopy gap-fill error: {e}")

    _mark_ipos_first_bar(conn, updated)
    conn.close()

    s = _update_status(symbols_done=total, step_pct=100, phase=f"Downloaded {len(updated)} symbols")
    s["overall_pct"] = _compute_overall_pct(s)
    _persist_status(s)

    return updated


def start_background_daemon(market="US"):
    """Removed: scheduled background refresh is intentionally not supported.
    Refresh runs only when explicitly requested via POST /api/refresh."""
    logger.warning("start_background_daemon called but background refresh is disabled")
    return None
