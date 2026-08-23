import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', timeout=10)
c.execute('PRAGMA busy_timeout=5000')
r = c.execute("SELECT COUNT(*), MAX(date) FROM historical_screener").fetchone()
print(f"Total rows: {r[0]}, max date: {r[1]}")
r = c.execute("SELECT COUNT(*) FROM historical_screener WHERE date = '2026-07-24'").fetchone()
print(f"Rows on 2026-07-24: {r[0]}")
r = c.execute("SELECT COUNT(*) FROM historical_screener WHERE date = '2026-07-23'").fetchone()
print(f"Rows on 2026-07-23: {r[0]}")
# Check AAPL
r = c.execute("SELECT symbol, date FROM historical_screener WHERE symbol='AAPL' ORDER BY date DESC LIMIT 3").fetchall()
print(f"AAPL recent: {r}")
c.close()
