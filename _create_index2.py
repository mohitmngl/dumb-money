"""Create idx_hss_date index with timing and error reporting."""
import sqlite3, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print(f"[{time.strftime('%H:%M:%S')}] Creating idx_hss_date ON historical_string_screener(date)...")
sys.stdout.flush()
c = sqlite3.connect("screener.db", timeout=3600)
c.execute("PRAGMA journal_mode=WAL")
c.execute("PRAGMA page_size=4096")
c.execute("PRAGMA cache_size=-8000000")  # 8GB cache
t0 = time.time()
try:
    c.execute("CREATE INDEX IF NOT EXISTS idx_hss_date ON historical_string_screener(date)")
    elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] Created idx_hss_date in {elapsed:.0f}s ({elapsed/60:.1f} min)")
except Exception as e:
    elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] ERROR after {elapsed:.0f}s: {e}")
finally:
    c.close()
