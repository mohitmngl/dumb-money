"""Run basket historical rebuild with date_limit=500 (last ~2 years) to avoid OOM."""
import sys, os, time, logging
sys.path.insert(0, os.getcwd())
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
from dumbmoney.basket_screener import update_historical_string_screener

t0 = time.time()
print("Starting US basket historical rebuild (date_limit=500)...")
rows = update_historical_string_screener("US", force_rebuild=True, date_limit=500)
print(f"Done. Rows written: {rows}, elapsed: {time.time()-t0:.1f}s")
