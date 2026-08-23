import sqlite3
c = sqlite3.connect('screener.db')
r = c.execute("SELECT COUNT(*) FROM bars WHERE timeframe='1Day' AND date='2026-07-21'").fetchone()
print('Bars for Jul 21:', r[0])
r2 = c.execute("SELECT MAX(date) FROM bars WHERE timeframe='1Day'").fetchone()
print('Latest bar:', r2[0])
# Check if new bars were downloaded
r3 = c.execute("SELECT COUNT(DISTINCT symbol) FROM bars WHERE timeframe='1Day' AND date='2026-07-21'").fetchone()
print('Distinct symbols with Jul 21 bars:', r3[0])
c.close()
