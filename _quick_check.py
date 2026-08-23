import sqlite3
conn = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', timeout=15)
conn.execute('PRAGMA busy_timeout=10000')
r = conn.execute("SELECT COUNT(*), MAX(date) FROM historical_screener").fetchone()
print(f"Rows: {r[0]}, max date: {r[1]}", flush=True)
r = conn.execute("SELECT COUNT(*) FROM historical_screener WHERE date='2026-07-24'").fetchone()
print(f"Rows on 2026-07-24: {r[0]}", flush=True)
conn.close()
