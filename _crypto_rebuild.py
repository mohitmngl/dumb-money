"""Crypto full rebuild: stats (ATR 2x) -> historical (crypto-v2) -> live columns."""
import sys, logging
from multiprocessing import freeze_support

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler("crypto_rebuild.log"), logging.StreamHandler()])
    log = logging.getLogger("crypto")
    sys.path.insert(0, ".")

    import sqlite3
    t0 = __import__("time").time()
    conn = sqlite3.connect("crypto.db", timeout=600)
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_crypto_bars_tf_date ON crypto_bars(timeframe, date)")
    conn.commit()
    conn.close()
    log.info(f"tf-date index ready ({time.time()-t0:.1f}s)")

    from dumbmoney.engine import compute_crypto_stats_batch, update_crypto_historical_screener
    from dumbmoney.data_crypto import update_live_columns

    log.info("crypto stats recompute (ATR 2x)")
    n = compute_crypto_stats_batch(progress_callback=lambda d, t: None)
    if n == 0:
        log.error("stats recompute returned 0 symbols - ABORTING (live table would stay stale)")
        return
    log.info(f"crypto stats done: {n} symbols")

    def prog(pct, msg):
        if isinstance(pct, (int, float)) and int(pct) % 20 == 0:
            log.info(f"  hist {pct:.0f}% {msg}")

    log.info("crypto historical rebuild (crypto-v2, force: include backfilled dates)")
    update_crypto_historical_screener(force_rebuild=True, progress_callback=prog)
    log.info("crypto historical done")

    n = update_live_columns()
    log.info(f"live columns updated for {n} symbols")
    log.info("CRYPTO DONE")

if __name__ == "__main__":
    freeze_support()
    main()
