"""Quick CREATE INDEX - run immediately."""
import sqlite3, time
t0 = time.time()
c = sqlite3.connect("screener.db", timeout=600)
c.execute("PRAGMA journal_mode=WAL")
c.execute("PRAGMA synchronous=NORMAL")
print(f"Connected, starting CREATE INDEX...")
c.execute("CREATE INDEX IF NOT EXISTS idx_hss_date ON historical_string_screener(date)")
c.commit()
c.close()
print(f"idx_hss_date created in {time.time()-t0:.0f}s")
import os
os._exit(0)
