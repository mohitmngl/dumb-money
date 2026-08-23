"""Full US basket historical rebuild — 50K strings, all dates."""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

from dumbmoney.basket_screener import update_historical_string_screener

print("=== FULL US REBUILD: 50K strings, all dates ===")
t0 = time.time()
n = update_historical_string_screener(
    "US",
    force_rebuild=True,
    progress_callback=lambda pct, msg: print(f"  [{pct}%] {msg}") if pct % 10 == 0 else None,
)
elapsed = time.time() - t0
print(f"\nResult: {n} rows in {elapsed:.1f}s ({elapsed/60:.1f} min)")
print(f"Throughput: {n/elapsed:.0f} rows/s")

import sqlite3
c = sqlite3.connect("screener.db")
total = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
latest = c.execute("SELECT MAX(date) FROM historical_string_screener").fetchone()[0]
oldest = c.execute("SELECT MIN(date) FROM historical_string_screener").fetchone()[0]
n_sids = c.execute("SELECT COUNT(DISTINCT string_id) FROM historical_string_screener").fetchone()[0]
c.close()
print(f"Total rows: {total}, strings: {n_sids}, dates: {oldest} to {latest}")
