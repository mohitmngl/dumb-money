import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=120)
c.execute('PRAGMA busy_timeout=120000')
# Check all dates with data
dates = c.execute("""
    SELECT date, COUNT(*) FROM historical_screener
    GROUP BY date ORDER BY date DESC LIMIT 15
""").fetchall()
print("Most recent dates in hist_screener:")
for d, cnt in dates:
    print(f"  {d}: {cnt} rows")
r = c.execute("SELECT COUNT(*) FROM historical_screener").fetchone()
print(f"\nTotal: {r[0]}")
# Check if Jul 27 exists
r = c.execute("SELECT COUNT(*) FROM historical_screener WHERE date='2026-07-27'").fetchone()
print(f"Jul 27 rows: {r[0]}")
c.close()
