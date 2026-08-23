"""Resume US historical_string_screener rebuild.
Processes remaining strings in 3000-string batches (memory-safe).
Each batch uses per-chunk indicator computation (~5 min per batch).
Total remaining: ~32K strings = ~11 batches = ~60 min.
"""
import sys, os, time, logging, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("resume_rebuild.log")])
logger = logging.getLogger(__name__)

from dumbmoney.basket_screener import update_historical_string_screener

conn = sqlite3.connect("screener.db", timeout=60)
done = set(r[0] for r in conn.execute("SELECT DISTINCT string_id FROM historical_string_screener").fetchall())
all_sids = [r[0] for r in conn.execute("SELECT string_id FROM string_universe WHERE market='US'").fetchall()]
conn.close()

missing = [s for s in all_sids if s not in done]
logger.info(f"Existing: {len(done)}, Missing: {len(missing)}")
if not missing:
    logger.info("Nothing to do!")
    sys.exit(0)

BATCH = 3000
total = 0
t0 = time.time()

for i in range(0, len(missing), BATCH):
    batch = missing[i:i+BATCH]
    batch_t0 = time.time()
    logger.info(f"\n=== Batch {i//BATCH + 1}/{-(-len(missing)//BATCH)}: {batch[0]}..{batch[-1]} ({len(batch)} strings) ===")
    try:
        n = update_historical_string_screener(
            "US",
            only_strings=batch,
            force_rebuild=False,
        )
        total += n
        elapsed = time.time() - batch_t0
        total_elapsed = time.time() - t0
        remaining = len(missing) - (i + len(batch))
        eta = (total_elapsed / max(i + len(batch), 1)) * remaining if remaining > 0 else 0
        logger.info(f"Batch done: {n:,} rows in {elapsed:.0f}s. "
                    f"Total: {total:,} rows. "
                    f"Remaining: {remaining} strings. "
                    f"ETA: {eta:.0f}s ({eta/60:.0f} min)")
    except Exception as e:
        import traceback
        logger.error(f"Batch failed: {e}")
        traceback.print_exc()
        logger.info("Continuing with next batch...")

elapsed = time.time() - t0
logger.info(f"\n=== DONE: {total:,} rows in {elapsed:.0f}s ({elapsed/60:.0f} min) ===")
