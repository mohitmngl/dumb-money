import sqlite3
conn = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', timeout=15)
conn.execute('PRAGMA busy_timeout=10000')

# Check if 2026-07-24 bars exist
r = conn.execute("SELECT COUNT(*) FROM bars WHERE timeframe='1Day' AND date='2026-07-24'").fetchone()
print(f"Bars on 2026-07-24: {r[0]}")

# Check a sample symbol
r = conn.execute("SELECT symbol, MAX(date) FROM bars WHERE timeframe='1Day' AND symbol='AAPL'").fetchone()
print(f"AAPL latest bar: {r}")

r = conn.execute("SELECT symbol, MAX(date) FROM historical_screener WHERE symbol='AAPL'").fetchone()
print(f"AAPL latest hist_screener: {r}")

# Check how many symbols have bar date > hist_screener date
r = conn.execute("""
    SELECT COUNT(*) FROM (
        SELECT b.sym, b.max_bar, h.max_hist
        FROM (SELECT symbol as sym, MAX(date) as max_bar FROM bars WHERE timeframe='1Day' GROUP BY symbol) b
        LEFT JOIN (SELECT symbol as sym, MAX(date) as max_hist FROM historical_screener GROUP BY symbol) h
        ON b.sym = h.sym
        WHERE b.max_bar > COALESCE(h.max_hist, '1900-01-01')
    )
""").fetchone()
print(f"Symbols where bar date > hist_screener date: {r[0]}")

# Check version
r = conn.execute("SELECT value FROM settings WHERE key='historical_screener_version'").fetchone()
print(f"Historical screener version: {r}")

conn.close()
