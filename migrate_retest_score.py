"""
One-time migration: compute old_swing_retest_score for existing hist_screener rows.
Does a targeted UPDATE — no full rebuild needed.
"""

import sys, os, time, sqlite3
import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt")
os.chdir(r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt")

from dumbmoney.db import get_db
from dumbmoney.retest_engine import compute_retest_score_for_symbol


def migrate(market):
    db_name = "screener.db" if market == "US" else "india.db"
    db_path = os.path.join(os.path.dirname(__file__), db_name)
    conn = sqlite3.connect(db_path, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA cache_size=-262144")

    # Get symbols that have hist_screener rows
    syms = [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM historical_screener"
    ).fetchall()]
    print(f"{market}: {len(syms)} symbols with hist_screener rows")

    t0 = time.time()
    updated = 0
    skipped = 0

    for idx, sym in enumerate(syms):
        if idx % 200 == 0 and idx > 0:
            elapsed = time.time() - t0
            rate = idx / elapsed
            eta = (len(syms) - idx) / rate if rate > 0 else 0
            print(f"  [{idx}/{len(syms)}] {updated} updated, {skipped} skipped, ETA {eta:.0f}s")

        # Load bars for this symbol
        bars = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM bars "
            "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
            conn, params=(sym,), parse_dates=["date"]
        )
        if len(bars) < 30:
            skipped += 1
            continue

        try:
            series = compute_retest_score_for_symbol(bars)
            if series is None or len(series) == 0:
                skipped += 1
                continue

            # Build UPDATE pairs: (score, symbol, date) for each row
            dates = bars["date"].dt.strftime("%Y-%m-%d").values
            pairs = []
            for i in range(len(series)):
                val = series.iloc[i]
                score = 0.0 if val is None or (isinstance(val, float) and np.isnan(val)) else float(val)
                if score != 0.0:  # only update non-zero
                    pairs.append((round(score, 2), sym, dates[i]))

            if pairs:
                conn.executemany(
                    "UPDATE historical_screener SET old_swing_retest_score=? "
                    "WHERE symbol=? AND date=?",
                    pairs
                )
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  Error {sym}: {e}")
            skipped += 1

        # Commit every 500 symbols
        if idx % 500 == 0 and idx > 0:
            conn.commit()

    conn.commit()
    conn.close()
    elapsed = time.time() - t0
    print(f"{market} done: {updated} symbols updated, {skipped} skipped, {elapsed:.0f}s")


if __name__ == "__main__":
    market = sys.argv[1] if len(sys.argv) > 1 else "US"
    migrate(market)
