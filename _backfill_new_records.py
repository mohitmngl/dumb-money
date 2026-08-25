"""One-shot backfill of new_ath/new_atl flags for ALL historical dates, all markets.

historical_screener / crypto_historical_screener: flags are derived from the STORED
per-date ath/atl columns (already correct for every date). A row made a fresh record
iff its ath is strictly greater than every earlier row's ath (running max), i.e. the
same definition the refresh workers use. Only flag=1 rows are written (fresh columns
default to 0).

stats / crypto_stats: current snapshot — latest bar strictly exceeds every earlier
bar's extreme, evaluated directly against bars in one set-based UPDATE per table.

Idempotent: re-running produces the same values.
"""
import sys
import time

from dumbmoney.db import get_db


def backfill_hist_table(conn, table):
    t0 = time.time()
    flags_ath, flags_atl = [], []
    cur_sym, run_max, run_min = None, None, None
    rows = conn.execute(
        f"SELECT symbol, date, ath, atl FROM {table} ORDER BY symbol, date"
    )
    n_rows = 0
    for sym, date, ath, atl in rows:
        n_rows += 1
        if sym != cur_sym:
            cur_sym, run_max, run_min = sym, None, None
        # ath<=0 means the row never got extremes populated; never flag or poison state
        if ath is not None and ath > 0:
            if run_max is not None and ath > run_max:
                flags_ath.append((sym, date))
            run_max = ath if run_max is None else max(run_max, ath)
        if atl is not None and atl > 0:
            if run_min is not None and atl < run_min:
                flags_atl.append((sym, date))
            run_min = atl if run_min is None else min(run_min, atl)
    conn.executemany(
        f"UPDATE {table} SET new_ath=1 WHERE symbol=? AND date=?", flags_ath)
    conn.executemany(
        f"UPDATE {table} SET new_atl=1 WHERE symbol=? AND date=?", flags_atl)
    conn.commit()
    print(f"  {table}: {n_rows:,} rows scanned -> "
          f"{len(flags_ath):,} new_ath, {len(flags_atl):,} new_atl "
          f"in {time.time()-t0:.1f}s", flush=True)


def backfill_stats_table(conn, stats_t, bars_t, tf):
    t0 = time.time()
    # Latest bar strictly above/below the extreme of ALL earlier bars (NULL-safe:
    # single-bar symbols compare against NULL -> 0).
    conn.execute(f"""
        UPDATE {stats_t} SET new_ath = CASE WHEN
            (SELECT b.high FROM {bars_t} b
             WHERE b.symbol={stats_t}.symbol AND b.timeframe='{tf}'
             ORDER BY b.date DESC LIMIT 1)
          > (SELECT MAX(b.high) FROM {bars_t} b
             WHERE b.symbol={stats_t}.symbol AND b.timeframe='{tf}'
               AND b.date < (SELECT MAX(c.date) FROM {bars_t} c
                             WHERE c.symbol={stats_t}.symbol AND c.timeframe='{tf}'))
        THEN 1 ELSE 0 END""")
    conn.execute(f"""
        UPDATE {stats_t} SET new_atl = CASE WHEN
            (SELECT b.low FROM {bars_t} b
             WHERE b.symbol={stats_t}.symbol AND b.timeframe='{tf}'
             ORDER BY b.date DESC LIMIT 1)
          < (SELECT MIN(b.low) FROM {bars_t} b
             WHERE b.symbol={stats_t}.symbol AND b.timeframe='{tf}'
               AND b.date < (SELECT MAX(c.date) FROM {bars_t} c
                             WHERE c.symbol={stats_t}.symbol AND c.timeframe='{tf}'))
        THEN 1 ELSE 0 END""")
    n_ath = conn.execute(f"SELECT COUNT(*) FROM {stats_t} WHERE new_ath=1").fetchone()[0]
    n_atl = conn.execute(f"SELECT COUNT(*) FROM {stats_t} WHERE new_atl=1").fetchone()[0]
    conn.commit()
    print(f"  {stats_t}: {n_ath:,} new_ath, {n_atl:,} new_atl "
          f"in {time.time()-t0:.1f}s", flush=True)


def main():
    for market in ("US", "INDIA"):
        print(f"[{market}]", flush=True)
        conn = get_db(market)
        try:
            backfill_hist_table(conn, "historical_screener")
            backfill_stats_table(conn, "stats", "bars", "1Day")
        finally:
            conn.close()
    print("[CRYPTO]", flush=True)
    conn = get_db("CRYPTO")
    try:
        backfill_hist_table(conn, "crypto_historical_screener")
        backfill_stats_table(conn, "crypto_stats", "crypto_bars", "1d")
    finally:
        conn.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    sys.exit(main())
