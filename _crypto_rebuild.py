"""Crypto full rebuild: migrations -> stats (ATR 2x + AI) -> historical (crypto-v2)
-> live ticker columns. Logs to crypto_rebuild.log."""
import sqlite3, sys, logging, time
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler("crypto_rebuild.log"), logging.StreamHandler()])
log = logging.getLogger("crypto")

conn = sqlite3.connect("crypto.db", timeout=30)
cur = conn.cursor()
for table in ("crypto_stats", "crypto_historical_screener"):
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN r_squared REAL DEFAULT 0")
        log.info(f"+{table}.r_squared")
    except sqlite3.OperationalError:
        pass
conn.commit(); conn.close()

sys.path.insert(0, ".")
from dumbmoney.engine import compute_crypto_stats_batch, update_crypto_historical_screener

log.info("crypto stats recompute (ATR 2x)")
n = compute_crypto_stats_batch(progress_callback=lambda d, t: None)
log.info(f"crypto stats done: {n} symbols")

def prog(pct, msg):
    if isinstance(pct, (int, float)) and int(pct) % 20 == 0:
        log.info(f"  hist {pct:.0f}% {msg}")

log.info("crypto historical rebuild (crypto-v2)")
update_crypto_historical_screener(progress_callback=prog)
log.info("crypto historical done")

from dumbmoney.data_crypto import update_live_columns
n = update_live_columns()
log.info(f"live columns updated for {n} symbols")
log.info("CRYPTO DONE")
