"""Test per-chunk indicator computation with missing LS strings."""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("test_chunk.log")])
from dumbmoney.basket_screener import update_historical_string_screener

t0 = time.time()
try:
    n = update_historical_string_screener("US", only_strings=[f"LS{i:06d}" for i in range(1, 21)], force_rebuild=False)
    print(f"OK: {n} rows in {time.time()-t0:.1f}s")
except Exception as e:
    import traceback; traceback.print_exc()
