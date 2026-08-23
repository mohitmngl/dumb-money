import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

# Check bar dates
dates = c.execute("""
    SELECT date, COUNT(*) FROM bars WHERE timeframe='1Day'
    AND date BETWEEN '2026-07-20' AND '2026-07-28'
    GROUP BY date ORDER BY date
""").fetchall()
print("Bar dates:", dates)

# Check hist_screener dates
dates2 = c.execute("""
    SELECT date, COUNT(*) FROM historical_screener
    WHERE date BETWEEN '2026-07-20' AND '2026-07-28'
    GROUP BY date ORDER BY date
""").fetchall()
print("Hist screener dates:", dates2)

# Check if bars exist for Jul 24
r = c.execute("SELECT COUNT(*) FROM bars WHERE timeframe='1Day' AND date='2026-07-24'").fetchone()
print(f"Bars on 2026-07-24: {r[0]}")

c.close()
