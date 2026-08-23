import sys, time, os
sys.path.insert(0, 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')
os.chdir('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')

import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

# What's missing
all_bar_dates = [r[0] for r in c.execute(
    "SELECT DISTINCT date FROM bars WHERE timeframe='1Day' ORDER BY date"
).fetchall()]
hist_dates = set(r[0] for r in c.execute(
    "SELECT DISTINCT date FROM historical_screener"
).fetchall())
missing = [d for d in all_bar_dates if d not in hist_dates]
print(f"Total bar dates: {len(all_bar_dates)}")
print(f"Hist screener dates: {len(hist_dates)}")
print(f"Missing dates: {len(missing)}")
if missing:
    print(f"  First missing: {missing[0]}")
    print(f"  Last missing: {missing[-1]}")
    print(f"  Sample: {missing[:10]}")

# How many symbols per date
r = c.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM historical_screener").fetchone()
print(f"\nHist screener: {r[0]} rows, {r[1]} to {r[2]}")

# Check per-date counts for recent dates
dates = c.execute("""
    SELECT date, COUNT(*) FROM historical_screener
    WHERE date >= '2026-07-20' GROUP BY date ORDER BY date
""").fetchall()
print("\nRecent dates:")
for d, cnt in dates:
    print(f"  {d}: {cnt}")

c.close()
