"""Check India historical_screener status."""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
c = sqlite3.connect("india.db", timeout=30)
n = c.execute("SELECT COUNT(*) FROM historical_screener").fetchone()[0]
u = c.execute("SELECT COUNT(DISTINCT symbol) FROM historical_screener").fetchone()[0]
d = c.execute("SELECT COUNT(DISTINCT date) FROM historical_screener").fetchone()[0]
print(f"India historical_screener: rows={n:,}, symbols={u:,}, dates={d}")
c.close()
