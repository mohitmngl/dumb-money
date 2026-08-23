import threading
import time
import logging
import json
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
        if market == "US":
            updated_symbols = _download_us_bars_incremental(market)
        else:
            updated_symbols = _download_india_bars(market) or []

        if _check_cancel():
            return

        if updated_symbols:
            stats_symbols = updated_symbols
            label = f"{len(updated_symbols)} updated"
        else:
            stats_symbols = None  # None = full market recompute (keeps stats fresh)
            label = "all (full recompute)"

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
                update_historical_screener(market, progress_callback=_bg_progress, only_symbols=hist_symbols, cancel_check=_check_cancel)
            except Exception as e:
                logger.error(f"Historical screener failed: {e}", exc_info=True)
                step_errors.append(f"Step 5 (historical screener): {e}")
            _bg_progress(100, "History updated")

        # Retest v2: too slow for refresh (2.4s/sym). Compute on demand only.
        _bg_progress(100, "Retest v2: skipped (compute on demand)")

        final_phase = "All done!" if not step_errors else f"Done with {len(step_errors)} warning(s)"
        has_critical = any("stats" in e.lower() or "fatal" in e.lower() for e in step_errors)
        final_status = "error" if has_critical else "complete"
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

    date_map = {}
    if explicit_symbols:
        placeholders = ",".join("?" * len(symbols))
        date_rows = conn.execute(
            f"""SELECT symbol, MAX(date), MIN(date) FROM bars
                WHERE timeframe='1Day' AND symbol IN ({placeholders})
                GROUP BY symbol""",
            symbols,
        )
    else:
        # oldest-date lookup is only needed for backfill planning; skipping the MIN()
        # correlated subquery halves the planning scan on the huge bars table.
        oldest_select = ("(SELECT MIN(b.date) FROM bars b "
                         "WHERE b.symbol=a.symbol AND b.timeframe='1Day')"
                         if allow_backfill else "NULL")
        date_rows = conn.execute(
            f"""SELECT a.symbol,
                      (SELECT MAX(b.date) FROM bars b
                       WHERE b.symbol=a.symbol AND b.timeframe='1Day'),
                      {oldest_select}
               FROM assets a
               WHERE a.status='active' AND a.tradable=1 AND COALESCE(a.exchange, '') <> 'OTC'"""
        )
    for row in date_rows:
        date_map[row[0]] = (row[1], row[2])
    conn.close()

    last_dates = {s: v[0] for s, v in date_map.items()}
    oldest_dates = {s: v[1] for s, v in date_map.items()}

    if not symbols:
        _update_status(step_pct=100, symbols_total=0, symbols_done=0)
        # Must be [] (deliberate no-op), never None (None means full-market recompute).
        return []

    from datetime import date, timedelta
    cutoff = _last_weekday_cutoff(market)
    today_str = _market_date(market).strftime("%Y-%m-%d")
    market_open = _market_is_open_now(market)
    BACKFILL_CUTOFF = "2016-01-01"

    symbols_to_download = []
    up_to_date = 0
    new_stocks = []
    backfill_stocks = []
    for sym in symbols:
        ld = last_dates.get(sym)
        od = oldest_dates.get(sym)
        if ld is None:
            # Never downloaded — always include (backfill from warmup window)
            symbols_to_download.append(sym)
            new_stocks.append(sym)
        elif ld >= cutoff:
            if market_open:
                # Market open: ALWAYS re-download (supports multiple refreshes per day)
                symbols_to_download.append(sym)
            elif ld < today_str:
                # Market closed: download if bar is stale
                symbols_to_download.append(sym)
            else:
                up_to_date += 1
        else:
            symbols_to_download.append(sym)

        if allow_backfill and od and od > BACKFILL_CUTOFF and ld:
            backfill_stocks.append(sym)

    backfill_set = set(backfill_stocks) - set(symbols_to_download)
    symbols_to_download.extend(sorted(backfill_set))

    total = len(symbols_to_download)
    if total == 0:
        _update_status(symbols_total=len(symbols), symbols_done=len(symbols), step_pct=100,
                       phase=f"All {up_to_date} symbols up to date")
        return []

    new_count = len(new_stocks)
    backfill_count = len(backfill_set)
    phase_msg = f"Downloading {total} symbols ({up_to_date} up to date"
    if new_count:
        phase_msg += f", {new_count} new IPOs"
    if backfill_count:
        phase_msg += f", {backfill_count} backfilling"
    phase_msg += ")"
    _update_status(symbols_total=total, symbols_done=0, phase=phase_msg, new_stocks_count=new_count)

    updated = []
    is_incremental = not backfill_set and total > 0

    if symbols_to_download:
        try:
            def _us_download_progress(done_batches, total_batches):
                pct = round(done_batches / total_batches * 90, 1) if total_batches else 90
                s = _update_status(step_pct=pct, phase=f"Downloading bars: batch {done_batches}/{total_batches}")
                s["overall_pct"] = _compute_overall_pct(s)
                _persist_status(s)
            _update_status(phase=f"Downloading bars for {total} symbols...")
            download_bars(symbols_to_download, start_date=cutoff, timeframe="1Day", incremental=False, progress_callback=_us_download_progress)
            _update_status(step_pct=90, phase=f"Downloaded bars for {total} symbols")
            updated = symbols_to_download
        except Exception as e:
            logger.warning(f"Download error: {e}")
            _update_status(phase=f"Download error: {e}")

    # Snapshot bar correction: Alpaca IEX bars endpoint can return stale mid-day
    # snapshots for the current day even after market close. Snapshots finalize
    # faster. Run on ALL symbols (not just downloaded) to catch skipped ones too.
    try:
        from dumbmoney.data_us import get_snapshots
        snaps = get_snapshots(symbols)
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
            from dumbmoney.db import get_db as _get_db
            _conn2 = _get_db(market)
            corrected = 0
            for sym, snap_vol, so, sh, sl, sc, snap_date in snap_updates:
                cur = _conn2.execute(
                    "SELECT volume FROM bars WHERE symbol=? AND timeframe='1Day' AND date=?",
                    (sym, snap_date)
                ).fetchone()
                if cur and cur[0] >= snap_vol:
                    continue
                _conn2.execute(
                    "INSERT OR REPLACE INTO bars (symbol, timeframe, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?,?)",
                    (sym, "1Day", snap_date, so, sh, sl, sc, snap_vol)
                )
                corrected += 1
            _conn2.commit()
            _conn2.close()
            if corrected:
                logger.info(f"Snapshot-corrected {corrected} bars")
    except Exception as e:
        logger.warning(f"Snapshot bar correction failed: {e}")

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
        # `symbols` but missing from `last_dates` is treated as brand-new and gets a
        # 450-day warm-up download on every refresh.
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
        last_dates = {row[0]: row[1] for row in date_rows}
        oldest_dates = {row[0]: row[2] for row in date_rows}
    else:
        # oldest-date lookup is only needed for backfill planning; skipping the MIN()
        # correlated subquery halves the planning scan on the huge bars table.
        oldest_select = ("(SELECT MIN(b.date) FROM bars b "
                         "WHERE b.symbol=a.symbol AND b.timeframe='1Day')"
                         if allow_backfill else "NULL")
        date_rows = conn.execute(
            f"""SELECT a.symbol,
                      (SELECT MAX(b.date) FROM bars b
                       WHERE b.symbol=a.symbol AND b.timeframe='1Day'),
                      {oldest_select}
               FROM assets a
               WHERE a.status='active'"""
        ).fetchall()
        last_dates = {row[0]: row[1] for row in date_rows}
        oldest_dates = {row[0]: row[2] for row in date_rows}
    conn.close()

    if not symbols:
        _update_status(step_pct=100, symbols_total=0, symbols_done=0)
        return []

    from datetime import date, timedelta
    cutoff = _last_weekday_cutoff(market)
    today_str = _market_date(market).strftime("%Y-%m-%d")
    market_open = _market_is_open_now(market)
    BACKFILL_CUTOFF = "2016-01-01"

    new_backfill_syms = []
    incremental_syms = []
    up_to_date = 0
    new_stocks = []
    backfill_stocks = []

    for sym in symbols:
        ld = last_dates.get(sym)
        od = oldest_dates.get(sym)
        if ld is None:
            # Never downloaded — always backfill
            new_stocks.append(sym)
            new_backfill_syms.append(sym)
        elif ld >= cutoff:
            if market_open:
                # Market open: ALWAYS re-download (supports multiple refreshes per day)
                incremental_syms.append(sym)
            elif ld < today_str:
                # Market closed: download if bar is stale
                incremental_syms.append(sym)
            else:
                up_to_date += 1
            continue
        elif allow_backfill and od and od > BACKFILL_CUTOFF:
            backfill_stocks.append(sym)
            new_backfill_syms.append(sym)
        else:
            incremental_syms.append(sym)

    total = len(new_backfill_syms) + len(incremental_syms)
    if total == 0:
        _update_status(symbols_total=len(symbols), symbols_done=len(symbols), step_pct=100,
                       phase=f"All {up_to_date} symbols up to date")
        return []

    new_count = len(new_stocks)
    backfill_count = len(backfill_stocks)
    incr_count = len(incremental_syms)
    phase_msg = f"Downloading {total} symbols ({up_to_date} up to date"
    if new_count:
        phase_msg += f", {new_count} new"
    if backfill_count:
        phase_msg += f", {backfill_count} backfill"
    if incr_count:
        phase_msg += f", {incr_count} incremental"
    phase_msg += ")"
    _update_status(symbols_total=total, symbols_done=0, phase=phase_msg, new_stocks_count=new_count)

    updated = []
    all_syms = new_backfill_syms + incremental_syms
    is_incremental = not new_backfill_syms and total > 0

    if all_syms:
        try:
            def _india_progress(done, total_syms):
                if _check_cancel():
                    return
                pct = round(done / total_syms * 100, 1) if total_syms else 100
                s = _update_status(step_pct=pct, symbols_done=done, symbols_total=total_syms)
                s["overall_pct"] = _compute_overall_pct(s)
                _persist_status(s)
            if is_incremental:
                download_bars_india(all_syms, start_date=cutoff,
                                    cancel_check=_check_cancel, progress_callback=_india_progress)
            else:
                download_bars_india(all_syms, start_date="1970-01-01",
                                    cancel_check=_check_cancel, progress_callback=_india_progress)
            updated = all_syms
        except Exception as e:
            logger.warning(f"India download error: {e}")

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
            cancel_check=_check_cancel, progress_callback=_bhav_progress)
        if bars_added > 0:
            logger.info(f"Bhavcopy filled {bars_added} bars across {dates_filled} dates")
            s = _update_status(phase=f"Bhavcopy filled {bars_added} bars")
            s["overall_pct"] = _compute_overall_pct(s)
            _persist_status(s)
            # Add bhavcopy symbols to updated list so stats get computed
            if bhav_symbols:
                updated = list(set(updated or []) | bhav_symbols)

        # Backfill new symbols that have very few bars (e.g. 1-day bhavcopy only)
        backfilled = backfill_new_bhavcopy_symbols(
            max_bars_threshold=50, cancel_check=_check_cancel, progress_callback=_bhav_progress)
        if backfilled > 0:
            s = _update_status(phase=f"Backfilled {backfilled} new symbols via yfinance")
            s["overall_pct"] = _compute_overall_pct(s)
            _persist_status(s)
            # Add backfilled symbols to stats computation
            updated = list(set(updated or []))
    except Exception as e:
        logger.warning(f"Bhavcopy gap-fill error: {e}")

    s = _update_status(symbols_done=total, step_pct=100, phase=f"Downloaded {len(updated)} symbols")
    s["overall_pct"] = _compute_overall_pct(s)
    _persist_status(s)

    return updated


def start_background_daemon(market="US"):
    def _daemon():
        while True:
            time.sleep(300)
            try:
                update_historical_screener(market)
            except Exception as e:
                logger.error(f"Background daemon error: {e}")
    t = threading.Thread(target=_daemon, daemon=True)
    t.start()
    return t
