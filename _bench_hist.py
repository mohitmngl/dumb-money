"""Benchmark the optimized historical string screener on a small subset."""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

from dumbmoney.basket_screener import update_historical_string_screener

# Test with 100 strings, 50 dates — fast correctness check
print("=== Small test: 100 strings, 50 dates ===")
t0 = time.time()
n = update_historical_string_screener(
    "US",
    only_strings=None,  # all strings
    force_rebuild=True,
    date_limit=50,
    string_id_like="S00000*",  # just S000001-S000009
)
elapsed = time.time() - t0
print(f"\nResult: {n} rows in {elapsed:.1f}s")

import sqlite3
c = sqlite3.connect("screener.db")
total = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
latest = c.execute("SELECT MAX(date) FROM historical_string_screener").fetchone()[0]
oldest = c.execute("SELECT MIN(date) FROM historical_string_screener").fetchone()[0]
sample = c.execute("SELECT string_id, date, price, change_pct, atr_signal, accel_signal, weighted_alpha FROM historical_string_screener LIMIT 3").fetchall()
c.close()
print(f"Total rows in DB: {total}")
print(f"Date range: {oldest} to {latest}")
print("Sample rows:")
for r in sample:
    print(f"  {r}")
