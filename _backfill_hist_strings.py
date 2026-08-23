"""Backfill historical_string_screener for chart data."""
import sys, time, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
sys.path.insert(0, r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt")
from dumbmoney.basket_screener import update_historical_string_screener

for mkt in ["US", "INDIA"]:
    t0 = time.time()
    print(f"=== {mkt}: building historical string screener ===", flush=True)
    n = update_historical_string_screener(mkt, force_rebuild=True, date_limit=130)
    print(f"=== {mkt}: done {n} rows in {time.time()-t0:.1f}s ===", flush=True)
print("ALL DONE", flush=True)
