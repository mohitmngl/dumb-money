import time
import logging
import csv
import io
import urllib.request
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import requests as _requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

_yf_sessions = []
_yf_session_idx = 0
_yf_lock = threading.Lock()
_yf_ready = threading.Event()


def _make_yf_session():
    """Create a single authenticated Yahoo Finance session with cookie + crumb."""
    s = _requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10,
                          max_retries=Retry(total=2, backoff_factor=0.5,
                                            status_forcelist=[429, 500, 502, 503, 504]))
    s.mount('https://', adapter)
    s.get('https://fc.yahoo.com', timeout=5)
    r = s.get('https://query2.finance.yahoo.com/v1/test/getcrumb', timeout=5)
    return s, r.text


def _init_yf_sessions():
    """Pre-create all Yahoo sessions in parallel threads."""
    global _yf_sessions
    if _yf_ready.is_set():
        return
    with _yf_lock:
        if _yf_ready.is_set():
            return
        _yf_sessions = []
        results = [None] * 10

        def _create_one(idx):
            try:
                results[idx] = _make_yf_session()
            except Exception as e:
                logger.warning(f"Failed to create Yahoo session {idx}: {e}")

        threads = [threading.Thread(target=_create_one, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        for r in results:
            if r is not None:
                _yf_sessions.append(r)
        _yf_ready.set()
        logger.info(f"Created {len(_yf_sessions)} Yahoo sessions")


def _get_yf_session():
    """Get next session in round-robin from pool of authenticated sessions."""
    global _yf_session_idx
    if not _yf_ready.is_set():
        _init_yf_sessions()
    if not _yf_sessions:
        raise RuntimeError("No Yahoo sessions available")
    with _yf_lock:
        s, crumb = _yf_sessions[_yf_session_idx % len(_yf_sessions)]
        _yf_session_idx += 1
        return s, crumb


def _fetch_nse_symbols():
    """Fetch all NSE equity symbols from archives."""
    try:
        req = urllib.request.Request(
            'https://archives.nseindia.com/content/equities/EQUITY_L.csv',
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = resp.read().decode('utf-8')
        reader = csv.reader(io.StringIO(data))
        next(reader)
        symbols = []
        for row in reader:
            sym = row[0].strip()
            if sym:
                symbols.append(sym + '.NS')
        return symbols
    except Exception as e:
        logger.warning(f"NSE CSV fetch failed: {e}")
        return []


def get_india_universe():
    return _fetch_nse_symbols()


def _download_one(sym, start_date=None):
    """Download one symbol from Yahoo Finance chart API."""
    try:
        session, crumb = _get_yf_session()
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}"
        if start_date and start_date > "2016-01-01":
            from datetime import datetime as dt
            p1 = int(dt.strptime(start_date, "%Y-%m-%d").timestamp())
            p2 = int(dt.now().timestamp())
            params = {"period1": p1, "period2": p2, "interval": "1d", "crumb": crumb}
        else:
            # period1=0 => full history since listing (max available)
            p2 = int(datetime.now().timestamp())
            params = {"period1": 0, "period2": p2, "interval": "1d", "crumb": crumb}
        r = session.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return sym, []
        data = r.json()
        result = data['chart']['result'][0]
        ts = result['timestamp']
        ohlcv = result['indicators']['quote'][0]
        bars = []
        for j in range(len(ts)):
            dt = datetime.utcfromtimestamp(ts[j]).strftime("%Y-%m-%d")
            c = ohlcv['close'][j]
            if c is None:
                continue
            bars.append((sym, dt,
                         float(ohlcv['open'][j] or 0),
                         float(ohlcv['high'][j] or 0),
                         float(ohlcv['low'][j] or 0),
                         float(c),
                         int(ohlcv['volume'][j] or 0)))
        return sym, bars
    except Exception:
        return sym, []


def download_bars_india(symbols=None, start_date=None, progress_callback=None, cancel_check=None):
    """Download bars for India symbols using raw Yahoo Finance API.
    Background writer thread handles DB writes so downloads never block.

    Args:
        symbols: list of tickers to download (defaults to the full NSE universe)
        start_date: start date for incremental downloads (YYYY-MM-DD)
        progress_callback: fn(done_count, total_count)
        cancel_check: fn() -> bool
    """
    from dumbmoney.db import get_db
    from queue import Queue

    if symbols is None:
        symbols = get_india_universe()

    _init_yf_sessions()

    total = len(symbols)
    done_count = 0
    all_bars_count = 0
    BATCH_DB = 20

    logger.info(f"India download starting: {total} symbols, {len(_yf_sessions)} sessions, start_date={start_date}")

    write_queue = Queue()
    total_bars_written = [0]
    write_error = [None]
    _write_batch = []
    _write_lock = threading.Lock()

    def _flush_batch(c):
        nonlocal _write_batch
        if not _write_batch:
            return
        batch = _write_batch
        _write_batch = []
        try:
            for sym, bars in batch:
                if bars:
                    c.executemany(
                        """INSERT OR REPLACE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
                           VALUES (?, '1Day', ?, ?, ?, ?, ?, ?)""",
                        bars
                    )
            c.commit()
            total = sum(len(b) for _, b in batch)
            total_bars_written[0] += total
        except Exception as e:
            write_error[0] = str(e)
            logger.warning(f"India writer batch error: {e}")

    def _writer():
        try:
            conn = get_db("INDIA")
            while True:
                item = write_queue.get()
                if item is None:
                    _flush_batch(conn)
                    break
                with _write_lock:
                    _write_batch.append(item)
                    if len(_write_batch) >= 50:
                        _flush_batch(conn)
            conn.close()
            logger.info(f"India writer thread: wrote {total_bars_written[0]} bars total")
        except Exception as e:
            write_error[0] = str(e)
            logger.warning(f"India writer thread error: {e}")

    writer_thread = threading.Thread(target=_writer, daemon=True)
    writer_thread.start()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_download_one, s, start_date): s for s in symbols}
        for f in as_completed(futures):
            if cancel_check and cancel_check():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            sym, bars = f.result()
            done_count += 1
            if bars:
                write_queue.put((sym, bars))
            if done_count % 50 == 0:
                logger.info(f"India download: {done_count}/{total} done")
            if done_count % BATCH_DB == 0 or done_count == total:
                if progress_callback:
                    progress_callback(done_count, total)

    write_queue.put(None)
    writer_thread.join(timeout=30)

    if progress_callback:
        progress_callback(total, total)
    logger.info(f"India download complete: {total_bars_written[0]} bars")
    return total_bars_written[0]


def fill_gaps_from_bhavcopy(series=None, start_date=None, end_date=None,
                             coverage_threshold=0.95, progress_callback=None,
                             cancel_check=None):
    """Fill missing bars from NSE bhavcopy (direct NSE EOD data).

    Fetches bhavcopy for each trading day in the range and inserts OHLCV
    for any symbol that is missing bars on those dates. Bhavcopy is the
    authoritative NSE source — used as fallback after yfinance.

    Args:
        series: list of NSE series to include, e.g. ['EQ','BE','ST'].
                Defaults to ['EQ','BE'] (excludes ETFs like GS/GB/SM).
        start_date: start date YYYY-MM-DD (default: 30 days ago)
        end_date: end date YYYY-MM-DD (default: today)
        coverage_threshold: skip dates where bar count >= this fraction of
                            total stats symbols (0.0–1.0). Default 0.95 means
                            skip dates that already have 95%+ coverage.
        progress_callback: fn(message)
        cancel_check: fn() -> bool
    Returns:
        (dates_filled, bars_added, updated_symbols) tuple
    """
    from dumbmoney.db import get_db
    from datetime import date, timedelta
    from nsepython import get_bhavcopy

    if series is None:
        series = ['EQ', 'BE']

    conn = get_db("INDIA")
    today = date.today()

    if end_date is None:
        end_date = today.strftime("%Y-%m-%d")
    if start_date is None:
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    # Get total symbol count for coverage threshold
    total_syms = conn.execute("SELECT COUNT(DISTINCT symbol) FROM stats").fetchone()[0]
    if total_syms == 0:
        conn.close()
        return 0, 0, set()

    min_bars = int(total_syms * coverage_threshold)

    # Find dates in range that have bars but below coverage threshold
    rows = conn.execute(
        """SELECT date, COUNT(DISTINCT symbol) as cnt FROM bars
           WHERE date >= ? AND date <= ?
           GROUP BY date HAVING cnt < ? ORDER BY date""",
        (start_date, end_date, min_bars)
    ).fetchall()
    gap_dates = [r[0] for r in rows]

    # Also check for dates that have NO bars at all in the range
    all_dates_with_bars = set(r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM bars WHERE date >= ? AND date <= ?",
        (start_date, end_date)
    ).fetchall())

    # Generate expected trading days (skip weekends)
    from datetime import timedelta as td
    d = date.fromisoformat(start_date)
    while d <= date.fromisoformat(end_date):
        ds = d.strftime("%Y-%m-%d")
        if d.weekday() < 5 and ds not in all_dates_with_bars and ds not in gap_dates:
            gap_dates.append(ds)
        d += td(days=1)

    gap_dates.sort()
    if not gap_dates:
        conn.close()
        logger.info("No gap dates found in range")
        return 0, 0, set()

    logger.info(f"Bhavcopy gap-fill: {len(gap_dates)} dates to check, series={series}")
    dates_filled = 0
    total_inserted = 0
    updated_symbols = set()

    for d in gap_dates:
        if cancel_check and cancel_check():
            break
        try:
            dt = date.fromisoformat(d)
            nse_date = dt.strftime("%d-%m-%Y")
            if progress_callback:
                progress_callback(f"Bhavcopy: fetching {d}...")

            bhav = get_bhavcopy(nse_date)
            if bhav is None or len(bhav) == 0:
                logger.warning(f"Bhavcopy returned no data for {d}")
                continue

            bhav.columns = bhav.columns.str.strip()
            bhav['SERIES'] = bhav['SERIES'].str.strip()
            filtered = bhav[bhav['SERIES'].isin(series)].copy()
            if len(filtered) == 0:
                continue

            bars_to_insert = []
            for _, row in filtered.iterrows():
                sym = row['SYMBOL'].strip() + '.NS'
                try:
                    o = float(row['OPEN_PRICE'])
                    h = float(row['HIGH_PRICE'])
                    l = float(row['LOW_PRICE'])
                    c = float(row['CLOSE_PRICE'])
                    v = int(row['TTL_TRD_QNTY'])
                    if c > 0 and v > 0:
                        bars_to_insert.append((sym, '1Day', d, o, h, l, c, v))
                except (ValueError, TypeError):
                    continue

            if bars_to_insert:
                conn.executemany(
                    """INSERT OR REPLACE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    bars_to_insert
                )
                conn.commit()
                total_inserted += len(bars_to_insert)
                dates_filled += 1
                updated_symbols.update(sym for sym, _, _, _, _, _, _, _ in bars_to_insert)
                logger.info(f"Bhavcopy {d}: inserted {len(bars_to_insert)} bars ({len(filtered)} EQ/BE symbols)")

        except Exception as e:
            logger.warning(f"Bhavcopy error for {d}: {e}")
            continue

    conn.close()
    logger.info(f"Bhavcopy gap-fill complete: {dates_filled} dates, {total_inserted} bars, {len(updated_symbols)} symbols")
    return dates_filled, total_inserted, updated_symbols


def backfill_new_bhavcopy_symbols(max_bars_threshold=50, progress_callback=None,
                                   cancel_check=None, return_symbols=False):
    """Backfill historical bars for symbols that have very few bars.

    After bhavcopy gap-fill, some symbols may only have 1 day of data.
    This function uses jugaad-data (direct NSE) to download full history
    for those symbols so stats can be computed meaningfully.

    Args:
        max_bars_threshold: symbols with fewer bars than this get backfilled
        progress_callback: fn(message)
        cancel_check: fn() -> bool
        return_symbols: if True, return the list of backfilled symbols
                        (so stats/history can recompute them this same run)
    Returns:
        number of symbols backfilled, or the symbol list when return_symbols=True
    """
    from dumbmoney.db import get_db
    from datetime import date, timedelta

    conn = get_db("INDIA")
    rows = conn.execute("""
        SELECT b.symbol, COUNT(*) as cnt
        FROM bars b
        WHERE b.timeframe = '1Day'
        GROUP BY b.symbol
        HAVING cnt < ?
        ORDER BY cnt
    """, (max_bars_threshold,)).fetchall()
    conn.close()

    if not rows:
        return [] if return_symbols else 0

    syms_to_backfill = [r[0] for r in rows]
    logger.info(f"Backfilling {len(syms_to_backfill)} symbols with <{max_bars_threshold} bars via NSE")
    if progress_callback:
        progress_callback(f"Backfilling {len(syms_to_backfill)} new symbols via NSE...")

    # Import jugaad-data
    try:
        from jugaad_data.nse import stock_df as jugaad_stock_df
    except ImportError:
        logger.warning("jugaad-data not installed, falling back to yfinance")
        return _backfill_yfinance_fallback(syms_to_backfill, progress_callback, cancel_check,
                                           return_symbols=return_symbols)

    conn = get_db("INDIA")
    filled_syms = []
    today = date.today()
    start = date(2015, 1, 1)

    for i, sym in enumerate(syms_to_backfill):
        if cancel_check and cancel_check():
            break

        # Strip .NS suffix for NSE symbol name
        nse_sym = sym.replace('.NS', '')
        try:
            df = jugaad_stock_df(symbol=nse_sym, from_date=start, to_date=today, series='EQ')
            if df is not None and len(df) > 0:
                # Normalize column names (jugaad-data uses different names)
                cols = {c.strip().upper(): c for c in df.columns}
                date_col = cols.get('DATE', cols.get('CH_TIMESTAMP', None))
                open_col = cols.get('OPEN', cols.get('CH_OPENING_PRICE', None))
                high_col = cols.get('HIGH', cols.get('CH_TRADE_HIGH_PRICE', None))
                low_col = cols.get('LOW', cols.get('CH_TRADE_LOW_PRICE', None))
                close_col = cols.get('CLOSE', cols.get('CH_CLOSING_PRICE', cols.get('LTP', None)))
                vol_col = cols.get('VOLUME', cols.get('CH_TOT_TRADED_QTY', None))

                if not all([date_col, open_col, high_col, low_col, close_col, vol_col]):
                    logger.warning(f"Backfill: missing columns for {sym}: {list(df.columns)}")
                    continue

                bars = []
                for _, row in df.iterrows():
                    try:
                        dt = row[date_col]
                        if hasattr(dt, 'date'):
                            dt = dt.date().strftime("%Y-%m-%d")
                        else:
                            dt = str(dt)[:10]
                        c = float(row[close_col])
                        v = int(row[vol_col])
                        if c > 0 and v > 0:
                            bars.append((sym, dt,
                                         float(row[open_col]), float(row[high_col]),
                                         float(row[low_col]), c, v))
                    except (ValueError, TypeError, KeyError):
                        continue

                if bars:
                    conn.executemany(
                        """INSERT OR REPLACE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
                           VALUES (?, '1Day', ?, ?, ?, ?, ?, ?)""",
                        bars
                    )
                    conn.commit()
                    filled_syms.append(sym)

            if (i + 1) % 20 == 0:
                logger.info(f"Backfill: {i+1}/{len(syms_to_backfill)} done")
                if progress_callback:
                    progress_callback(f"Backfill: {i+1}/{len(syms_to_backfill)}")

        except Exception as e:
            logger.warning(f"Backfill error for {sym}: {e}")
            continue

    conn.close()
    if progress_callback:
        progress_callback(f"Backfilled {len(filled_syms)} symbols via NSE")
    logger.info(f"Backfill complete: {len(filled_syms)} symbols via NSE")
    return filled_syms if return_symbols else len(filled_syms)


def _backfill_yfinance_fallback(syms_to_backfill, progress_callback, cancel_check,
                                return_symbols=False):
    """Fallback yfinance backfill if jugaad-data is not available."""
    _init_yf_sessions()
    filled_syms = []
    from queue import Queue
    write_queue = Queue()

    def _writer():
        try:
            c = get_db("INDIA")
            batch = []
            while True:
                item = write_queue.get()
                if item is None:
                    if batch:
                        c.executemany(
                            """INSERT OR REPLACE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
                               VALUES (?, '1Day', ?, ?, ?, ?, ?, ?)""",
                            batch
                        )
                        c.commit()
                    c.close()
                    break
                batch.append(item)
                if len(batch) >= 100:
                    c.executemany(
                        """INSERT OR REPLACE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
                           VALUES (?, '1Day', ?, ?, ?, ?, ?, ?)""",
                        batch
                    )
                    c.commit()
                    batch = []
        except Exception as e:
            logger.warning(f"Backfill writer error: {e}")

    writer = threading.Thread(target=_writer, daemon=True)
    writer.start()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_download_one, s, "1970-01-01"): s for s in syms_to_backfill}
        for f in as_completed(futures):
            if cancel_check and cancel_check():
                break
            sym, bars = f.result()
            if bars:
                for bar in bars:
                    write_queue.put(bar)
                filled_syms.append(sym)
            if len(filled_syms) % 20 == 0 and filled_syms:
                logger.info(f"Backfill: {len(filled_syms)}/{len(syms_to_backfill)} done")

    write_queue.put(None)
    writer.join(timeout=30)
    if progress_callback:
        progress_callback(f"Backfilled {len(filled_syms)} symbols via yfinance")
    return filled_syms if return_symbols else len(filled_syms)


def get_live_prices_india(symbols):
    prices = {}
    if not symbols:
        return prices
    try:
        with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as executor:
            futures = {}
            for sym in symbols:
                futures[executor.submit(_fetch_one_live_india, sym)] = sym
            for f in as_completed(futures):
                try:
                    sym, price_data = f.result()
                    if price_data:
                        prices[sym] = price_data
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Live price error: {e}")
    return prices


def _fetch_one_live_india(sym):
    try:
        session, crumb = _get_yf_session()
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}"
        params = {"range": "5d", "interval": "1d", "crumb": crumb}
        r = session.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return sym, None
        data = r.json()
        result = data['chart']['result'][0]
        ohlcv = result['indicators']['quote'][0]
        closes = [c for c in ohlcv['close'] if c is not None]
        if len(closes) >= 2:
            price = closes[-1]
            prev = closes[-2]
            change_pct = ((price - prev) / prev * 100) if prev > 0 else 0
            return sym, {
                "price": price, "change_pct": round(change_pct, 2),
                "volume": int(ohlcv['volume'][-1] or 0),
                "open": float(ohlcv['open'][-1] or 0),
                "high": float(ohlcv['high'][-1] or 0),
                "low": float(ohlcv['low'][-1] or 0),
            }
    except Exception:
        pass
    return sym, None


def sync_india_assets(force=False, cache_max_age_days=7):
    """Sync all NSE assets into assets table.
    Normal refresh reuses today's cached NSE universe; force=True refreshes the
    symbol list from the exchange source.
    """
    from dumbmoney.db import get_db
    conn = get_db("INDIA")
    try:
        row = conn.execute(
            "SELECT COUNT(*), MAX(last_updated) FROM assets WHERE status='active'"
        ).fetchone()
        if not force and row and row[0] and row[1]:
            try:
                last_dt = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00")).replace(tzinfo=None)
                age_days = (datetime.utcnow() - last_dt).total_seconds() / 86400
                if age_days <= cache_max_age_days:
                    return int(row[0])
            except Exception:
                pass
    finally:
        conn.close()

    tickers = get_india_universe()
    if not tickers:
        return 0

    conn = get_db("INDIA")
    now = datetime.utcnow().isoformat()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO assets (symbol, name, asset_class, exchange, status,
               tradable, fractionable, marginable, last_updated)
               VALUES (?, ?, 'Stock', 'NSE', 'active', 0, 0, 0, ?)""",
            [(t, t.replace(".NS", ""), now) for t in tickers]
        )
        if tickers:
            conn.execute(
                "DELETE FROM assets WHERE symbol NOT IN ({})".format(
                    ",".join("?" * len(tickers))
                ),
                list(tickers)
            )
        conn.commit()
    finally:
        conn.close()
    return len(tickers)


def update_nifty500_constituents():
    """Fetch current Nifty 500 list and snapshot into nifty500_constituents table.

    Tracks additions/removals over time by end-dating removed symbols and
    inserting new ones with today as from_date. Called once per India refresh.

    Returns (added_count, removed_count) or (-1, -1) on fetch failure.
    """
    from dumbmoney.db import get_db
    try:
        import csv, io
        from curl_cffi import requests as cffi_req
        session = cffi_req.Session(impersonate="chrome120")
        resp = session.get(
            "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
            timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Nifty 500 CSV returned status {resp.status_code}")
            return -1, -1
        reader = csv.reader(io.StringIO(resp.text))
        next(reader)  # skip header
        current_syms = set()
        for row in reader:
            sym = row[2].strip() if len(row) > 2 else ""
            if sym:
                current_syms.add(sym + ".NS")
        if not current_syms:
            logger.warning("Nifty 500 CSV returned 0 symbols")
            return -1, -1
    except Exception as e:
        logger.warning(f"Failed to fetch Nifty 500: {e}")
        return -1, -1

    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_db("INDIA")
    try:
        # Get currently active constituents (to_date = '9999-12-31')
        existing = set(
            r[0] for r in conn.execute(
                "SELECT symbol FROM nifty500_constituents WHERE to_date = '9999-12-31'"
            ).fetchall()
        )

        removed = existing - current_syms
        added = current_syms - existing

        # End-date removed symbols
        if removed:
            conn.executemany(
                "UPDATE nifty500_constituents SET to_date = ? WHERE symbol = ? AND to_date = '9999-12-31'",
                [(today, s) for s in removed]
            )

        # Insert new symbols with from_date = earliest bar date (or 2015-01-01 fallback)
        # This ensures historical queries work: a stock currently in Nifty 500 is treated
        # as if it was in the index for all its available history.
        if added:
            for sym in added:
                earliest = conn.execute(
                    "SELECT MIN(date) FROM bars WHERE symbol = ? AND timeframe = '1Day'",
                    (sym,)
                ).fetchone()[0]
                from_date = earliest or '2015-01-01'
                conn.execute(
                    "INSERT OR IGNORE INTO nifty500_constituents (symbol, from_date, to_date) VALUES (?, ?, '9999-12-31')",
                    (sym, from_date)
                )

        conn.commit()
        logger.info(f"Nifty 500 snapshot: {len(added)} added, {len(removed)} removed (total active: {len(current_syms)})")
        return len(added), len(removed)
    finally:
        conn.close()


def _snapshot_constituents(table_name, current_syms, label):
    """Generic SCD-Type-2 snapshot for any constituents table.

    End-dates removed symbols, inserts new ones with from_date = earliest bar date.
    Returns (added_count, removed_count).
    """
    from dumbmoney.db import get_db
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_db("INDIA")
    try:
        existing = set(
            r[0] for r in conn.execute(
                f"SELECT symbol FROM {table_name} WHERE to_date = '9999-12-31'"
            ).fetchall()
        )
        removed = existing - current_syms
        added = current_syms - existing

        if removed:
            conn.executemany(
                f"UPDATE {table_name} SET to_date = ? WHERE symbol = ? AND to_date = '9999-12-31'",
                [(today, s) for s in removed]
            )
        if added:
            for sym in added:
                earliest = conn.execute(
                    "SELECT MIN(date) FROM bars WHERE symbol = ? AND timeframe = '1Day'",
                    (sym,)
                ).fetchone()[0]
                from_date = earliest or '2015-01-01'
                conn.execute(
                    f"INSERT OR IGNORE INTO {table_name} (symbol, from_date, to_date) VALUES (?, ?, '9999-12-31')",
                    (sym, from_date)
                )
        conn.commit()
        logger.info(f"{label} snapshot: {len(added)} added, {len(removed)} removed (total active: {len(current_syms)})")
        return len(added), len(removed)
    finally:
        conn.close()


def update_nifty50_constituents():
    """Fetch current Nifty 50 list and snapshot into nifty50_constituents table."""
    try:
        import csv, io
        from curl_cffi import requests as cffi_req
        session = cffi_req.Session(impersonate="chrome120")
        resp = session.get(
            "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
            timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Nifty 50 CSV returned status {resp.status_code}")
            return -1, -1
        reader = csv.reader(io.StringIO(resp.text))
        next(reader)  # skip header
        current_syms = set()
        for row in reader:
            sym = row[2].strip() if len(row) > 2 else ""
            if sym:
                current_syms.add(sym + ".NS")
        if not current_syms:
            logger.warning("Nifty 50 CSV returned 0 symbols")
            return -1, -1
    except Exception as e:
        logger.warning(f"Failed to fetch Nifty 50: {e}")
        return -1, -1
    return _snapshot_constituents("nifty50_constituents", current_syms, "Nifty 50")


def update_fo_constituents():
    """Fetch current F&O stock list from NSE contract file and snapshot into fo_constituents."""
    try:
        import csv, io, gzip
        from datetime import timedelta
        from curl_cffi import requests as cffi_req
        session = cffi_req.Session(impersonate="chrome120")
        session.get("https://www.nseindia.com", timeout=15)
        today = datetime.utcnow()
        current_syms = set()
        for days_back in range(0, 7):
            d = today - timedelta(days=days_back)
            date_str = d.strftime("%d%m%Y")
            url = f"https://nsearchives.nseindia.com/content/fo/NSE_FO_contract_{date_str}.csv.gz"
            try:
                resp = session.get(url, timeout=20)
                if resp.status_code == 200:
                    data = gzip.decompress(resp.content)
                    text = data.decode("utf-8", errors="replace")
                    reader = csv.DictReader(io.StringIO(text))
                    for row in reader:
                        sym = row.get("TckrSymb", "").strip()
                        instrm = row.get("FinInstrmNm", "").strip()
                        if sym and "STK" in instrm and "NSETEST" not in sym:
                            current_syms.add(sym + ".NS")
                    break
            except Exception:
                continue
        if not current_syms:
            logger.warning("F&O contract file returned 0 stock symbols")
            return -1, -1
    except Exception as e:
        logger.warning(f"Failed to fetch F&O stocks: {e}")
        return -1, -1
    return _snapshot_constituents("fo_constituents", current_syms, "F&O")
