import sqlite3
c = sqlite3.connect("screener.db", timeout=5)
try:
    idx = c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND name='idx_hss_date'").fetchone()
    print(f"Index: {idx}")
except Exception as e:
    print(f"Error: {e}")
c.close()
