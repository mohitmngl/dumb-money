"""Find missing strings and resume rebuild properly."""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

import sqlite3
from dumbmoney.basket_screener import update_historical_string_screener

conn = sqlite3.connect("screener.db", timeout=10)
all_sids = set(r[0] for r in conn.execute("SELECT string_id FROM string_universe WHERE market='US'").fetchall())
covered = set(r[0] for r in conn.execute("SELECT DISTINCT string_id FROM historical_string_screener").fetchall())
missing = sorted(all_sids - covered)
conn.close()

print(f"All: {len(all_sids)}, covered: {len(covered)}, missing: {len(missing)}")
if not missing:
    print("Nothing missing!")
    sys.exit(0)

# Process in batches of 2000
BATCH = 2000
total = 0
for i in range(0, len(missing), BATCH):
    batch = missing[i:i+BATCH]
    print(f"\nBatch {i//BATCH+1}/{(len(missing)+BATCH-1)//BATCH}: {batch[0]}..{batch[-1]} ({len(batch)} strings)")
    t0 = time.time()
    try:
        n = update_historical_string_screener(
            "US",
            only_strings=batch,
            force_rebuild=False,
        )
        total += n
        print(f"  {n} rows in {time.time()-t0:.1f}s (running total: {total:,})")
    except Exception as e:
        print(f"  ERROR: {e}")
        # Try one at a time
        for sid in batch:
            try:
                n = update_historical_string_screener("US", only_strings=[sid], force_rebuild=False)
                total += n
            except:
                print(f"  SKIP {sid}")

conn = sqlite3.connect("screener.db", timeout=10)
final_count = conn.execute("SELECT COUNT(DISTINCT string_id) FROM historical_string_screener").fetchone()[0]
print(f"\n=== DONE: {final_count} strings covered ===")
conn.close()
