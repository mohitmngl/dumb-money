"""Full US historical_string_screener rebuild with progress updates."""
import sys, time, logging
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger()

from dumbmoney.basket_screener import update_historical_string_screener

print("Starting full US historical_string_screener rebuild...")
print("This will take approximately 60-80 minutes.")
print("Progress updates every 2 minutes.\n")

t0 = time.time()
last_update = [t0]

def progress_callback(pct, msg):
    now = time.time()
    if now - last_update[0] >= 120:  # 2 minutes
        elapsed = now - t0
        eta = (elapsed / max(pct, 1)) * (100 - pct)
        print(f"\n[{time.strftime('%H:%M:%S')}] Progress: {pct}% | Elapsed: {elapsed/60:.1f}min | ETA: {eta/60:.1f}min | {msg}")
        last_update[0] = now

count = update_historical_string_screener(
    market="US",
    force_rebuild=True,
    progress_callback=progress_callback,
)

elapsed = time.time() - t0
print(f"\n{'='*60}")
print(f"REBUILD COMPLETE")
print(f"Rows inserted: {count:,}")
print(f"Time: {elapsed/60:.1f} minutes")
print(f"Rate: {count/elapsed:.0f} rows/s")
print(f"{'='*60}")
