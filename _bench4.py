"""Benchmark: test 1000 strings to extrapolate 50K speed."""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

from dumbmoney.basket_screener import update_historical_string_screener

print("=== 1000 strings, 500 dates ===")
t0 = time.time()
n = update_historical_string_screener(
    "US",
    force_rebuild=True,
    date_limit=500,
    string_id_like="S000[0-9]*",  # S000001-S000009, S000010-S000019, ... S000090-S000099 = ~1000 strings
)
elapsed = time.time() - t0
print(f"\nResult: {n} rows in {elapsed:.1f}s ({n/elapsed:.0f} rows/s)")

import sqlite3
c = sqlite3.connect("screener.db")
total = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
print(f"Total rows: {total}")
c.close()
