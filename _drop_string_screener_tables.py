"""Drop String Screener + saved-strings tables once the basket-delete job
releases the DB locks. Logs to drop_ss_tables.log."""
import sqlite3, time, logging, sys
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler("drop_ss_tables.log"), logging.StreamHandler()])
log = logging.getLogger("drop")

TABLES = ["ss_entries", "ss_backtest_status", "ss_strategies", "string_symbols", "strings"]

def wait_lock(db, timeout_s=14400):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            c = sqlite3.connect(db, timeout=5)
            c.execute("BEGIN IMMEDIATE"); c.rollback(); c.close()
            return True
        except sqlite3.OperationalError:
            time.sleep(20)
    return False

for db in ("screener.db", "india.db", "crypto.db"):
    log.info(f"waiting for {db} lock...")
    if not wait_lock(db):
        log.error(f"{db} still locked after 4h; skipping (tables remain)")
        continue
    conn = sqlite3.connect(db, timeout=60)
    cur = conn.cursor()
    for t in TABLES:
        try:
            cur.execute(f"DROP TABLE IF EXISTS {t}")
            log.info(f"{db}: dropped {t}")
        except sqlite3.OperationalError as e:
            log.warning(f"{db}: {t}: {e}")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.commit(); conn.close()
    log.info(f"{db}: done, wal checkpointed")
log.info("DROP DONE")
