"""Proper batch resume: only process strings with ZERO rows in historical_string_screener."""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

import sqlite3
from dumbmoney.basket_screener import update_historical_string_screener

conn = sqlite3.connect("screener.db", timeout=10)
all_sids = [r[0] for r in conn.execute("SELECT string_id FROM string_universe WHERE market='US' ORDER BY string_id").fetchall()]
covered = set(r[0] for r in conn.execute("SELECT DISTINCT string_id FROM historical_string_screener").fetchall())
conn.close()

missing = [s for s in all_sids if s not in covered]
print(f"All: {len(all_sids)}, covered: {len(covered)}, missing: {len(missing)}")
if not missing:
    print("Nothing missing!")
    sys.exit(0)

print(f"First missing: {missing[0]}, Last: {missing[-1]}")

# Process in batches of 3000 (matching STR_CHUNK size)
BATCH = 3000
total_rows = 0
for i in range(0, len(missing), BATCH):
    batch = missing[i:i+BATCH]
    batch_num = i // BATCH + 1
    total_batches = (len(missing) + BATCH - 1) // BATCH
    print(f"\n=== Batch {batch_num}/{total_batches}: {batch[0]}..{batch[-1]} ({len(batch)} strings) ===")
    t0 = time.time()
    try:
        n = update_historical_string_screener(
            "US",
            only_strings=batch,
            force_rebuild=False,
        )
        total_rows += n
        elapsed = time.time() - t0
        print(f"  {n:,} rows in {elapsed:.1f}s (running total: {total_rows:,})")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()

conn = sqlite3.connect("screener.db", timeout=10)
final = conn.execute("SELECT COUNT(DISTINCT string_id) FROM historical_string_screener").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
print(f"\n=== DONE: {final} strings, {total:,} rows ===")
conn.close()
