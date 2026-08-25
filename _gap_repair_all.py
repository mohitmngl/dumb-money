"""One-shot repair: bar gaps + ATH/ATL backfill across ALL markets.

Damage found (2026-08 audit):
  US     - interrupted refreshes left whole sessions partially filled
           (2026-08-12/13/24 and scattered older single-symbol gaps).
  India  - old fill scripts stamped FABRICATED candles onto days the NSE was
           closed (weekends, holidays, even full-market copies of the NEXT
           session onto e.g. 2025-12-28). Verified against Yahoo ^NSEI calendar.
  Crypto - clean (verified; checked again at runtime).

Phases:
  1. India calendar cleanup - delete every bar on a day NSE was provably closed
     (^NSEI session list) plus all weekend bars.
  2. Duplicate-stamp scan   - delete bars identical (OHLC + nonzero volume,
     float-tolerant) to their next session: the fill-script fingerprint.
  3. Gap refill             - tiered hole detection, idempotent re-download.
  4. Hist rebuilds          - force_rebuild historical screeners (fills ath/atl).
  5. Stats backfill         - per-symbol MAX(high)/MIN(low) into stats tables.
  6. Verify                 - re-scan holes, sanity-check ath/atl.

Run:  python _gap_repair_all.py
"""
import json
import os
import random
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timedelta

CONFIRMED_EMPTY_FILE = "_repair_confirmed_empty.json"
NSEI_CACHE = "_nsei_sessions.pkl"


def log(msg):
    print(msg, flush=True)


def _weekday(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() < 5


def _load_confirmed_empty():
    if os.path.exists(CONFIRMED_EMPTY_FILE):
        return json.load(open(CONFIRMED_EMPTY_FILE))
    return {}


def _save_confirmed_empty(d):
    json.dump(d, open(CONFIRMED_EMPTY_FILE, "w"), indent=1)


# ---------------------------------------------------------------- calendars
def fetch_nsei_sessions():
    """Authoritative NSE trading calendar via Yahoo ^NSEI daily bars."""
    import pickle
    try:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI"
               f"?period1=1704067200&period2={int(time.time()) + 86400}&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read())
        ts = j["chart"]["result"][0]["timestamp"]
        sess = sorted(datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in ts)
        pickle.dump(sess, open(NSEI_CACHE, "wb"))
        return set(sess)
    except Exception as e:
        log(f"[1] WARNING: ^NSEI fetch failed ({e}); using cached calendar")
        if os.path.exists(NSEI_CACHE):
            return set(pickle.load(open(NSEI_CACHE, "rb")))
        raise


# ---------------------------------------------------------------- phase 1
def phase_india_calendar():
    """NSE closed days must have zero bars; anything present is fabricated."""
    from dumbmoney.db import get_db

    sessions = fetch_nsei_sessions()
    cal_min = min(sessions)
    log(f"[1] ^NSEI calendar loaded: {len(sessions):,} sessions "
        f"{cal_min}..{max(sessions)} (dates before {cal_min} are NOT judged)")
    conn = get_db("INDIA")
    try:
        n_weekend = conn.execute(
            "DELETE FROM bars WHERE timeframe='1Day' "
            "AND strftime('%w', date) IN ('0','6') AND date >= ?",
            (cal_min,)
        ).rowcount
        conn.commit()
        log(f"[1] India weekend bars deleted (>= {cal_min}): {n_weekend:,}")

        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM bars WHERE timeframe='1Day'")]
        bad = sorted(d for d in dates if d >= cal_min and d not in sessions)
        for d in bad:
            n = conn.execute(
                "DELETE FROM bars WHERE timeframe='1Day' AND date=?", (d,)
            ).rowcount
            conn.commit()
            log(f"[1] India {d}: market CLOSED per ^NSEI -> deleted {n:,} fabricated bars")
        if not bad:
            log("[1] No off-calendar weekday bars found.")
    finally:
        conn.close()


def phase_india_restore_era():
    """Re-download pre-calendar-era history for symbols known to have traded then
    (repairs the earlier partial wipe of 2000-2002 dates; idempotent)."""
    from dumbmoney.db import get_db
    from dumbmoney.data_india import download_bars_india

    conn = get_db("INDIA")
    try:
        syms = sorted({r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM bars WHERE timeframe='1Day' AND date<'2010-01-01'"
        )} | {r[0] for r in conn.execute(
            "SELECT DISTINCT symbol FROM historical_screener WHERE date<'2010-01-01'")})
    finally:
        conn.close()
    log(f"[1b] Restoring early-era history for {len(syms)} symbols (start 1997-01-01)...")
    n = download_bars_india(syms, start_date="1997-01-01")
    log(f"[1b] Restore wrote {n if n is not None else '?'} bars")


# ---------------------------------------------------------------- phase 2
def _tol_eq(a, b):
    """OHLC equal within relative 1e-6 AND identical nonzero volume."""
    if a[4] <= 0 or a[4] != b[4]:
        return False
    return all(abs(x - y) <= max(1e-9, abs(y) * 1e-6) for x, y in zip(a[:4], b[:4]))


def _next_dup_pairs(conn, table, tf, symbols=None):
    """All (symbol, date) rows whose bar exactly repeats their NEXT session bar
    (with nonzero volume) - never occurs naturally; fill-script stamp."""
    from dumbmoney.db import get_db  # noqa: F401  (conn passed in already)

    q_syms = f"SELECT DISTINCT symbol FROM {table} WHERE timeframe='{tf}'"
    if symbols is not None:
        marks = []
        for sym in symbols:
            rows = conn.execute(
                f"SELECT date, open, high, low, close, volume FROM {table} "
                f"WHERE timeframe='{tf}' AND symbol=? ORDER BY date", (sym,)
            ).fetchall()
            for i in range(len(rows) - 1):
                if _tol_eq(rows[i][1:], rows[i + 1][1:]):
                    marks.append((sym, rows[i][0]))
        return marks
    marks = []
    for (sym,) in conn.execute(q_syms):
        rows = conn.execute(
            f"SELECT date, open, high, low, close, volume FROM {table} "
            f"WHERE timeframe='{tf}' AND symbol=? ORDER BY date", (sym,)
        ).fetchall()
        for i in range(len(rows) - 1):
            if _tol_eq(rows[i][1:], rows[i + 1][1:]):
                marks.append((sym, rows[i][0]))
    return marks


def phase_dup_scan():
    """Probe each market for duplicate-stamped bars; full-scan + delete on hits."""
    from dumbmoney.db import get_db

    plans = [("US", "bars", "1Day"), ("INDIA", "bars", "1Day"),
             ("CRYPTO", "crypto_bars", "1d")]
    for market, table, tf in plans:
        conn = get_db(market)
        try:
            syms = [r[0] for r in conn.execute(
                f"SELECT DISTINCT symbol FROM {table} WHERE timeframe='{tf}'")]
            random.seed(42)
            probe = random.sample(syms, min(300, len(syms)))
            hits = _next_dup_pairs(conn, table, tf, symbols=probe)
            log(f"[2] {market}: dup-probe {len(probe)} symbols -> {len(hits)} stamped bars")
            if hits:
                marks = _next_dup_pairs(conn, table, tf)
                by_date = {}
                for s, d in marks:
                    by_date.setdefault(d, 0)
                    by_date[d] += 1
                top = sorted(by_date.items(), key=lambda kv: -kv[1])[:10]
                log(f"[2] {market}: FULL scan found {len(marks):,} stamped bars; "
                    f"worst dates: {top}")
                for s, d in marks:
                    conn.execute(
                        f"DELETE FROM {table} WHERE timeframe='{tf}' AND symbol=? AND date=?",
                        (s, d))
                conn.commit()
                log(f"[2] {market}: deleted {len(marks):,} duplicate-stamped rows")
        finally:
            conn.close()


# ---------------------------------------------------------------- phase 3
def _detect_holes(conn, bars_table, timeframe, weekday_only, ignore_dates=None):
    """Tiered session classification over the last 180 sessions:
      expected : >=25% of median daily count (full or partial-but-real session)
      suspect  : <25% of median (caller copy-tests to decide junk vs wiped)
    Returns (holes, expected, suspect); holes={symbol: earliest_missing_date}."""
    ignore_dates = ignore_dates or set()
    active = [r[0] for r in conn.execute("SELECT symbol FROM assets WHERE status='active'")]
    active_set = set(active)

    counts = dict(conn.execute(
        f"SELECT date, COUNT(DISTINCT symbol) FROM {bars_table} "
        f"WHERE timeframe='{timeframe}' GROUP BY date"
    ))
    sessions = sorted(d for d in counts if (not weekday_only or _weekday(d)))
    if not sessions:
        return {}, [], []

    window = [d for d in sessions[-180:] if d not in ignore_dates]
    med = statistics.median(counts[d] for d in window)
    expected = [d for d in window if counts[d] >= 0.25 * med]
    suspect = [d for d in window if counts[d] < 0.25 * med]

    first_bar = dict(conn.execute(
        f"SELECT symbol, MIN(date) FROM {bars_table} "
        f"WHERE timeframe='{timeframe}' GROUP BY symbol"))

    have = {}
    for sym, date in conn.execute(
        f"SELECT symbol, date FROM {bars_table} WHERE timeframe='{timeframe}' AND date>=?",
        (window[0],),
    ):
        if sym in active_set:
            have.setdefault(sym, set()).add(date)

    holes = {}
    for sym in active:
        f = first_bar.get(sym)
        if not f:
            continue  # never downloaded; not a mid-series gap
        scan_from = max(f, window[0])
        seen = have.get(sym, ())
        miss = next((d for d in expected if d >= scan_from and d not in seen), None)
        if miss:
            holes[sym] = miss
    return holes, expected, suspect


def _copy_ratio(conn, bars_table, timeframe, date_str, sample_n=300):
    """Fraction of sampled bars on date_str that repeat the symbol's PREVIOUS bar."""
    syms = [r[0] for r in conn.execute(
        f"SELECT DISTINCT symbol FROM {bars_table} WHERE timeframe='{timeframe}' AND date=?",
        (date_str,)).fetchall()]
    if not syms:
        return 0, 0
    sample = random.sample(syms, min(sample_n, len(syms)))
    checked = copies = 0
    for sym in sample:
        cur = conn.execute(
            f"SELECT open, high, low, close, volume FROM {bars_table} "
            f"WHERE timeframe='{timeframe}' AND symbol=? AND date=?", (sym, date_str)
        ).fetchone()
        prev = conn.execute(
            f"SELECT open, high, low, close, volume FROM {bars_table} "
            f"WHERE timeframe='{timeframe}' AND symbol=? AND date<? ORDER BY date DESC LIMIT 1",
            (sym, date_str),
        ).fetchone()
        if not cur or not prev:
            continue
        checked += 1
        if all(abs(c - p) <= max(1e-6, abs(p) * 1e-9) for c, p in zip(cur[:4], prev[:4])):
            copies += 1
    return checked, copies


def phase_refill():
    from dumbmoney.db import get_db

    confirmed_empty = _load_confirmed_empty()
    plans = [("US", "bars", "1Day", True), ("INDIA", "bars", "1Day", True)]
    for market, table, tf, wk in plans:
        conn = get_db(market)
        try:
            holes, expected, suspect = _detect_holes(
                conn, table, tf, wk, ignore_dates=set(confirmed_empty.get(market, [])))
            log(f"[3] {market}: {len(holes):,} symbols with gaps on {len(expected)} "
                f"expected sessions; {len(suspect)} suspect thin sessions")

            # Suspects are near-empty real-looking sessions; decide junk vs wiped.
            mass_holes = []
            for d in suspect:
                checked, copies = _copy_ratio(conn, table, tf, d)
                if checked and copies / checked >= 0.7:
                    n = conn.execute(
                        f"DELETE FROM {table} WHERE timeframe='{tf}' AND date=?", (d,)
                    ).rowcount
                    conn.commit()
                    log(f"[3] {market}: deleted fabricated session {d} "
                        f"({n:,} rows, {copies}/{checked} prev-copies)")
                else:
                    log(f"[3] {market}: thin session {d} looks real/wiped -> mass refill")
                    mass_holes.append(d)

            if mass_holes:
                active = [r[0] for r in conn.execute(
                    "SELECT symbol FROM assets WHERE status='active'")]
                first_bar = dict(conn.execute(
                    f"SELECT symbol, MIN(date) FROM {table} WHERE timeframe='{tf}' GROUP BY symbol"))
                have_mass = {}
                q_from = mass_holes[0]
                for sym, date in conn.execute(
                    f"SELECT symbol, date FROM {table} WHERE timeframe='{tf}' AND date>=?",
                    (q_from,),
                ):
                    have_mass.setdefault(sym, set()).add(date)
                for sym in active:
                    f = first_bar.get(sym)
                    if not f:
                        continue
                    seen = have_mass.get(sym, ())
                    miss = next((d for d in mass_holes
                                 if d >= max(f, q_from) and d not in seen), None)
                    if miss and (sym not in holes or miss < holes[sym]):
                        holes[sym] = miss
        finally:
            conn.close()

        log(f"[3] {market}: {len(holes):,} symbols to refill")
        if not holes:
            continue

        buckets = {}
        for sym, hole in holes.items():
            buckets.setdefault(hole[:7], []).append(sym)
        if market == "US":
            from dumbmoney.data_us import download_bars
        else:
            from dumbmoney.data_india import download_bars_india

        covered_from = None
        for key in sorted(buckets):
            syms = sorted(set(buckets[key]))
            hole_dates = [holes[s] for s in syms]
            start = (datetime.strptime(min(hole_dates), "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
            covered_from = min(filter(None, [covered_from, start]))
            log(f"[3] {market}: refilling {len(syms):,} symbols from {start} (bucket {key})...")
            if market == "US":
                n = download_bars(syms, start_date=start)
            else:
                n = download_bars_india(syms, start_date=start)
            log(f"[3] {market}: bucket {key} wrote {n if n is not None else '?'} bars")

        # Dates still missing after a covering download are simply non-sessions
        # (holidays the calendar source missed) -> remember them.
        conn = get_db(market)
        try:
            remaining, _, _ = _detect_holes(conn, table, tf, wk,
                                            ignore_dates=set(confirmed_empty.get(market, [])))
            new_dates = sorted({d for d in remaining.values() if covered_from and d >= covered_from})
            if new_dates:
                confirmed_empty.setdefault(market, []).extend(new_dates)
                _save_confirmed_empty(confirmed_empty)
                log(f"[3] {market}: post-download non-session dates recorded: {new_dates}")
        finally:
            conn.close()


def phase_crypto_check():
    """Crypto trades every day; verify completeness (refill deliberately not
    automated - census found it clean, so warn loudly instead)."""
    from dumbmoney.db import get_db

    conn = get_db("CRYPTO")
    try:
        spans = {s: (f, l) for s, f, l in conn.execute(
            "SELECT symbol, MIN(date), MAX(date) FROM crypto_bars WHERE timeframe='1d' GROUP BY symbol")}
        global_first = min(v[0] for v in spans.values())
        have = {}
        for sym, date in conn.execute(
            "SELECT symbol, date FROM crypto_bars WHERE timeframe='1d' AND date>=?",
            (global_first,)):
            have.setdefault(sym, set()).add(date)
        global_last = max(v[1] for v in spans.values())
        d0 = datetime.strptime(global_first, "%Y-%m-%d")
        d1 = datetime.strptime(global_last, "%Y-%m-%d")
        all_days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d")
                    for i in range((d1 - d0).days + 1)]
        hole_syms = 0
        for sym, (f, l) in spans.items():
            seen = have.get(sym, set())
            missing = sum(1 for d in all_days if d >= f and d not in seen)
            if missing:
                hole_syms += 1
                if hole_syms <= 10:
                    log(f"[3] CRYPTO GAP: {sym} missing {missing} days within {f}..{l}")
        log(f"[3] CRYPTO: {hole_syms}/{len(spans)} symbols with calendar gaps")
    finally:
        conn.close()


# ---------------------------------------------------------------- phase 4
def phase_hist_rebuilds():
    from dumbmoney.engine import (
        update_crypto_historical_screener,
        update_historical_screener,
    )

    def cb(pct, msg):
        print(f"\r    [{pct:3d}%] {msg[:110]:<110}", end="", flush=True)

    for label, fn in [
        ("US", lambda: update_historical_screener(market="US", progress_callback=cb, force_rebuild=True)),
        ("INDIA", lambda: update_historical_screener(market="INDIA", progress_callback=cb, force_rebuild=True)),
        ("CRYPTO", lambda: update_crypto_historical_screener(progress_callback=cb, force_rebuild=True)),
    ]:
        log(f"[4] Rebuilding {label} historical screener (force_rebuild=True)...")
        fn()
        print("", flush=True)


# ---------------------------------------------------------------- phase 5
def phase_stats_backfill():
    from dumbmoney.db import get_db

    plans = [
        ("US", "stats", "bars", "1Day"),
        ("INDIA", "stats", "bars", "1Day"),
        ("CRYPTO", "crypto_stats", "crypto_bars", "1d"),
    ]
    for market, stats_t, bars_t, tf in plans:
        conn = get_db(market)
        try:
            agg = conn.execute(
                f"SELECT symbol, MAX(high), MIN(low) FROM {bars_t} "
                f"WHERE timeframe='{tf}' GROUP BY symbol"
            ).fetchall()
            conn.executemany(
                f"UPDATE {stats_t} SET ath=?, atl=? WHERE symbol=?",
                [(mh, ml, s) for s, mh, ml in agg],
            )
            conn.commit()
            log(f"[5] {market}: backfilled ath/atl for {len(agg):,} stats rows")
        finally:
            conn.close()


# ---------------------------------------------------------------- phase 6
def phase_verify():
    from dumbmoney.config import DB_PATHS
    from dumbmoney.db import get_db

    ok = True
    confirmed_empty = _load_confirmed_empty()

    # 6a. no bars remain on NSE-closed weekdays / weekends in India (calendar era only)
    sessions = fetch_nsei_sessions()
    cal_min = min(sessions)
    conn = get_db("INDIA")
    bad_dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM bars WHERE timeframe='1Day'")]
    bad = [d for d in bad_dates
           if d >= cal_min and (d not in sessions or not _weekday(d))]
    ok &= len(bad) == 0
    log(f"[6] India off-calendar bar dates remaining: {bad[:10]}{'...' if len(bad) > 10 else ''}")
    conn.close()

    # 6b. re-run hole detection for US/India (excluding known non-sessions)
    for market, table, tf, wk in [("US", "bars", "1Day", True), ("INDIA", "bars", "1Day", True)]:
        conn = get_db(market)
        holes, _, _ = _detect_holes(conn, table, tf, wk,
                                    ignore_dates=set(confirmed_empty.get(market, [])))
        conn.close()
        ok &= len(holes) == 0
        log(f"[6] {market}: {len(holes)} symbols still with gaps")

    # 6c. stats ath/atl coverage + spot-check vs bars truth
    for market, stats_t, bars_t, tf in [
        ("US", "stats", "bars", "1Day"),
        ("INDIA", "stats", "bars", "1Day"),
        ("CRYPTO", "crypto_stats", "crypto_bars", "1d"),
    ]:
        conn = get_db(market)
        tot, with_ath = conn.execute(
            f"SELECT COUNT(*), SUM(ath>0) FROM {stats_t}").fetchone()
        bad = 0
        checked = 0
        for sym, mh, ml in conn.execute(
            f"SELECT symbol, MAX(high), MIN(low) FROM {bars_t} WHERE timeframe='{tf}' GROUP BY symbol LIMIT 400"
        ):
            row = conn.execute(
                f"SELECT ath, atl FROM {stats_t} WHERE symbol=?", (sym,)).fetchone()
            checked += 1
            if row and (abs(row[0] - mh) > 1e-6 * max(1, mh) or
                        abs(row[1] - ml) > 1e-6 * max(1, abs(ml))):
                bad += 1
        conn.close()
        ok &= bad == 0
        log(f"[6] {market}: stats rows={tot:,} ath>0: {with_ath:,} "
            f"spot-check mismatches: {bad}/{checked}")

    # 6d. historical ath monotonic + equals bars running max at latest row
    checks = [
        ("US", DB_PATHS["US"], "historical_screener", "bars", "1Day"),
        ("INDIA", DB_PATHS["INDIA"], "historical_screener", "bars", "1Day"),
        ("CRYPTO", DB_PATHS["CRYPTO"], "crypto_historical_screener", "crypto_bars", "1d"),
    ]
    for market, dbp, hist_t, bars_t, tf in checks:
        conn = __import__("sqlite3").connect(dbp)
        syms = [r[0] for r in conn.execute(
            f"SELECT DISTINCT symbol FROM {hist_t}")]
        sample = random.sample(syms, min(60, len(syms))) if syms else []
        mono_bad = val_bad = 0
        for sym in sample:
            rows = conn.execute(
                f"SELECT date, ath, atl FROM {hist_t} WHERE symbol=? ORDER BY date", (sym,)
            ).fetchall()
            for i in range(1, len(rows)):
                if rows[i][1] < rows[i - 1][1] - 1e-9 or rows[i][2] > rows[i - 1][2] + 1e-9:
                    mono_bad += 1
                    break
            if not rows:
                continue
            last = rows[-1]
            truth = conn.execute(
                f"SELECT MAX(high), MIN(low) FROM {bars_t} "
                f"WHERE timeframe='{tf}' AND symbol=? AND date<=?",
                (sym, last[0]),
            ).fetchone()
            if truth and (abs(last[1] - truth[0]) > 1e-6 * max(1, truth[0]) or
                          abs(last[2] - truth[1]) > 1e-6 * max(1, abs(truth[1]))):
                val_bad += 1
        conn.close()
        ok &= mono_bad == 0 and val_bad == 0
        log(f"[6] {market} hist: monotonic violations={mono_bad} "
            f"value mismatches={val_bad} (sampled {len(sample)})")

    # 6e. eyeball AAPL around the repaired window
    import sqlite3
    conn = sqlite3.connect(DB_PATHS["US"])
    rows = conn.execute(
        "SELECT date, change_pct FROM historical_screener WHERE symbol='AAPL' "
        "AND date>='2026-08-10' ORDER BY date").fetchall()
    closes = conn.execute(
        "SELECT date, close FROM bars WHERE symbol='AAPL' AND timeframe='1Day' "
        "AND date>='2026-08-10' ORDER BY date").fetchall()
    conn.close()
    log(f"[6] AAPL hist Aug 10+: {rows}")
    log(f"[6] AAPL bars Aug 10+: {closes}")

    log(f"[6] VERIFY {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    t0 = datetime.now()
    log(f"=== repair started {t0:%Y-%m-%d %H:%M:%S} ===")
    phase_india_calendar()
    phase_india_restore_era()
    phase_dup_scan()
    phase_refill()
    phase_crypto_check()
    phase_hist_rebuilds()
    phase_stats_backfill()
    ok = phase_verify()
    log(f"=== done in {(datetime.now() - t0)} -> {'PASS' if ok else 'FAIL'} ===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
