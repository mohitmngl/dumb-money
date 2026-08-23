import sqlite3
conn = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', timeout=15)
conn.execute('PRAGMA busy_timeout=10000')

r = conn.execute("SELECT COUNT(*) FROM historical_screener WHERE date='2026-07-24'").fetchone()
print(f"Hist screener rows on 2026-07-24: {r[0]}")

r = conn.execute("SELECT COUNT(*) FROM historical_screener WHERE date='2026-07-23'").fetchone()
print(f"Hist screener rows on 2026-07-23: {r[0]}")

# Check AAPL specifically
r = conn.execute("SELECT symbol, date FROM historical_screener WHERE symbol='AAPL' ORDER BY date DESC LIMIT 3").fetchall()
print(f"AAPL recent hist rows: {r}")

r = conn.execute("SELECT symbol, date FROM bars WHERE symbol='AAPL' AND timeframe='1Day' ORDER BY date DESC LIMIT 3").fetchall()
print(f"AAPL recent bars: {r}")

# Check version setting
r = conn.execute("SELECT value FROM settings WHERE key='historical_screener_version'").fetchone()
print(f"Version: {r}")

conn.close()
