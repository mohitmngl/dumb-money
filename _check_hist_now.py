import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=60)
c.execute('PRAGMA busy_timeout=60000')
dates = c.execute("""
    SELECT date, COUNT(*) FROM historical_screener
    WHERE date >= '2026-07-25' GROUP BY date ORDER BY date
""").fetchall()
print("Hist screener dates:")
for d, cnt in dates:
    print(f"  {d}: {cnt} rows")
c.close()
