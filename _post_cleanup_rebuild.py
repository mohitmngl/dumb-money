"""Chained post-cleanup rebuild: waits for DB write lock, applies migrations,
recomputes stats (ATR 2x + R2), rebuilds historical screeners (asof-v3), then
rebuilds LS strings with gross-exposure math. Logs to post_cleanup_rebuild.log."""
import sqlite3, time, sys, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler("post_cleanup_rebuild.log"), logging.StreamHandler()])
log = logging.getLogger("rebuild")

def wait_for_lock(db, timeout_s=7200):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            c = sqlite3.connect(db, timeout=5)
            c.execute("BEGIN IMMEDIATE")
            c.rollback(); c.close()
            return True
        except sqlite3.OperationalError:
            time.sleep(15)
    return False

def migrate(db, pairs):
    conn = sqlite3.connect(db, timeout=30)
    cur = conn.cursor()
    for table, col, typedef in pairs:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            log.info(f"{db}: +{table}.{col}")
        except sqlite3.OperationalError as e:
            if "duplicate" not in str(e).lower():
                log.warning(f"{db}: {table}.{col}: {e}")
    try:
        cur.execute("ALTER TABLE portfolio_strings ADD COLUMN sort_order INTEGER DEFAULT 0")
        log.info(f"{db}: +portfolio_strings.sort_order")
    except sqlite3.OperationalError:
        pass
    cur.execute("CREATE TABLE IF NOT EXISTS ipos (symbol TEXT PRIMARY KEY, first_seen TEXT, first_bar TEXT)")
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stats_r2 ON stats(r_squared)")
    except sqlite3.OperationalError:
        pass
    conn.commit(); conn.close()

EQ = [("stats", "r_squared", "REAL DEFAULT 0"), ("historical_screener", "r_squared", "REAL DEFAULT 0"),
      ("string_screener_metrics", "r_squared", "REAL DEFAULT 0"), ("historical_string_screener", "r_squared", "REAL DEFAULT 0")]
CR = [("crypto_stats", "r_squared", "REAL DEFAULT 0"), ("crypto_historical_screener", "r_squared", "REAL DEFAULT 0")]

log.info("waiting for screener.db write lock (basket data delete still running)...")
if not wait_for_lock("screener.db"):
    log.error("could not lock screener.db after 2h; aborting")
    sys.exit(1)
log.info("lock acquired — running migrations")
migrate("screener.db", EQ)
migrate("india.db", EQ)
migrate("crypto.db", CR)

sys.path.insert(0, ".")
from dumbmoney.engine import vectorized_stats_pass, update_historical_screener, update_signal_prob_matrix

def prog(pct, msg):
    if isinstance(pct, (int, float)) and (int(pct) % 10 == 0):
        log.info(f"  {pct:.0f}% {msg}")

for market in ("US", "INDIA"):
    log.info(f"[{market}] full stats recompute (ATR 2x + R2)")
    try:
        n = vectorized_stats_pass(market, progress_callback=lambda d, t: None)
        log.info(f"[{market}] stats done: {n}")
    except Exception as e:
        log.error(f"[{market}] stats failed: {e}")
    log.info(f"[{market}] historical rebuild (asof-v3) — this is the long one")
    try:
        update_historical_screener(market, progress_callback=prog, force_rebuild=True)
        update_signal_prob_matrix(market, progress_callback=prog)
        log.info(f"[{market}] historical + signal matrix done")
    except Exception as e:
        log.error(f"[{market}] historical failed: {e}")

log.info("[US] LS strings pipeline (gross-exposure math)")
try:
    from dumbmoney.basket_screener import (
        generate_long_short_strings, compute_current_metrics,
        update_historical_string_screener, build_close_pivot_cache)
    n = generate_long_short_strings("US", n=25000)
    log.info(f"[US] generated {n} LS strings")
    build_close_pivot_cache("US")
    log.info("[US] pivot cache built")
    compute_current_metrics("US")
    log.info("[US] LS current metrics done")
    update_historical_string_screener("US", force_rebuild=True,
                                      progress_callback=prog, string_id_like="LS%")
    log.info("[US] LS historical done")
except Exception as e:
    log.error(f"[US] LS pipeline failed: {e}")

log.info("ALL DONE")
