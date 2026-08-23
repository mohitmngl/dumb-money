"""Create idx_hss_date index on historical_string_screener(date)."""
import sqlite3, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print(f"[{time.strftime('%H:%M:%S')}] Creating idx_hss_date on US historical_string_screener...")
c = sqlite3.connect("screener.db", timeout=600)
c.execute("PRAGMA journal_mode=WAL")
start = time.time()
c.execute("CREATE INDEX IF NOT EXISTS idx_hss_date ON historical_string_screener(date)")
elapsed = time.time() - start
print(f"[{time.strftime('%H:%M:%S')}] Index created in {elapsed/60:.1f} min")
c.close()
