import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')
print("Connected", flush=True)
r = c.execute("SELECT COUNT(*), MAX(date) FROM historical_screener").fetchone()
print(f"hist_screener: {r[0]} rows, max date: {r[1]}", flush=True)
c.close()
