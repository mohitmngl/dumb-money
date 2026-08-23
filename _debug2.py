import sqlite3
conn = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', timeout=15)
conn.execute('PRAGMA busy_timeout=10000')
print("Connected")
r = conn.execute("SELECT COUNT(*) FROM bars WHERE timeframe='1Day' AND date='2026-07-24'").fetchone()
print(f"Bars on 2026-07-24: {r[0]}")
conn.close()
