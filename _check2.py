import sqlite3, os
c = sqlite3.connect("screener.db", timeout=60)
c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
# quick table existence check
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("tables:", tables[:10])
hss_count = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
print(f"hist_string rows={hss_count:,}")
# use approximate count by checking a specific range
missing = c.execute("SELECT COUNT(*) FROM string_universe WHERE market='US' AND string_id NOT IN (SELECT DISTINCT string_id FROM historical_string_screener LIMIT 1000)").fetchone()[0]
print(f"missing? {missing}")
# get a sample
rows = c.execute("SELECT string_id, date FROM historical_string_screener LIMIT 5").fetchall()
print("sample:", rows)
db_size = os.path.getsize("screener.db")
print(f"DB size: {db_size/1e9:.2f} GB")
print(f"page_count: {c.execute('PRAGMA page_count').fetchone()[0]}")
print(f"page_size: {c.execute('PRAGMA page_size').fetchone()[0]}")
c.close()
if os.path.exists("screener.db-shm"):
    os.remove("screener.db-shm")
    print("removed stale -shm")
