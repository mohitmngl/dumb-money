"""Diagnose why idx_hss_date creation fails."""
import sqlite3, sys, os, time, traceback, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(filename="_index_diagnose.log", level=logging.DEBUG, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

logger.info("Opening screener.db...")
t0 = time.time()
c = sqlite3.connect("screener.db", timeout=300)
logger.info(f"Connected in {time.time()-t0:.1f}s")

c.execute("PRAGMA journal_mode=WAL")
c.execute("PRAGMA synchronous=NORMAL")
c.execute("PRAGMA cache_size=-5000000")

n = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
logger.info(f"historical_string_screener rows: {n:,}")

c.execute("BEGIN")
try:
    logger.info("Starting CREATE INDEX...")
    c.execute("CREATE INDEX IF NOT EXISTS idx_hss_date ON historical_string_screener(date)")
    c.execute("COMMIT")
    logger.info("COMMIT successful")
except Exception as e:
    logger.error(f"ERROR: {e}")
    traceback.print_exc(file=open("_index_diagnose.log", "a"))
    c.execute("ROLLBACK")
    logger.info("ROLLBACK executed")

c.close()
Logger = logger
logger.info("CLOSED")
