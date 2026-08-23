"""Memory-safe full rebuild: indicators computed per chunk, raw metrics loaded once."""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("safe_rebuild.log")])
logger = logging.getLogger(__name__)

from dumbmoney.basket_screener import update_historical_string_screener

logger.info("=== FULL US REBUILD (memory-safe): 50K strings all dates ===")
t0 = time.time()
n = update_historical_string_screener(
    "US",
    force_rebuild=True,
)
elapsed = time.time() - t0
logger.info(f"Result: {n} rows in {elapsed:.1f}s ({elapsed/60:.1f} min)")
logger.info(f"Throughput: {n/elapsed:.0f} rows/s")
