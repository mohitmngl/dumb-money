"""Test processing 1000 missing LS strings."""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
import sqlite3
from dumbmoney.basket_screener import update_historical_string_screener

conn = sqlite3.connect("screener.db", timeout=30)
missing = [r[0] for r in conn.execute("SELECT string_id FROM string_universe WHERE market='US' AND string_id NOT IN (SELECT DISTINCT string_id FROM historical_string_screener) ORDER BY string_id").fetchall()]
conn.close()
print(f"missing: {len(missing)}")

# Test first 1000
batch = missing[:1000]
print(f"Processing {len(batch)} strings: {batch[0]}..{batch[-1]}")
t0 = time.time()
try:
    n = update_historical_string_screener("US", only_strings=batch, force_rebuild=False)
    print(f"OK: {n} rows in {time.time()-t0:.1f}s")
except Exception as e:
    import traceback; traceback.print_exc()
