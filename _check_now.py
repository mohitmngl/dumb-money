import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=120)
c.execute('PRAGMA busy_timeout=120000')
print("Connected", flush=True)
dates = c.execute("""
    SELECT date, COUNT(*) FROM historical_screener
    WHERE date BETWEEN '2026-07-20' AND '2026-07-28'
    GROUP BY date ORDER BY date
""").fetchall()
print("India hist_screener dates:")
for d, cnt in dates:
    print(f"  {d}: {cnt} rows")
r = c.execute("SELECT COUNT(*) FROM historical_screener").fetchone()
print(f"\nTotal rows: {r[0]}")
r = c.execute("SELECT MAX(date) FROM historical_screener").fetchone()
print(f"Max date: {r[0]}")
c.close()
