"""Reset DB locking mode and run full optimized rebuild."""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("rebuild.log")])

import sqlite3
# Reset locking mode
conn = sqlite3.connect("screener.db", timeout=60)
conn.execute("PRAGMA locking_mode=NORMAL")
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
conn.execute("PRAGMA journal_mode=wal")
conn.execute("PRAGMA synchronous=OFF")
conn.execute("PRAGMA cache_size=-800000")
print(f"locking_mode: {conn.execute('PRAGMA locking_mode').fetchone()[0]}")
print(f"journal_mode: {conn.execute('PRAGMA journal_mode').fetchone()[0]}")
print(f"synchronous: {conn.execute('PRAGMA synchronous').fetchone()[0]}")
conn.close()

from dumbmoney.basket_screener import update_historical_string_screener

print("=== FULL US REBUILD: 50K strings all dates ===")
t0 = time.time()
n = update_historical_string_screener(
    "US",
    force_rebuild=True,
)
elapsed = time.time() - t0
print(f"\nResult: {n} rows in {elapsed:.1f}s ({elapsed/60:.1f} min)")
print(f"Throughput: {n/elapsed:.0f} rows/s")
# set synchronous back for safety
conn = sqlite3.connect("screener.db", timeout=60)
conn.execute("PRAGMA synchronous=FULL")
conn.close()
