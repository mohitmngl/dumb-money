import sys, time, os
sys.path.insert(0, 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')
os.chdir('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')

from dumbmoney.engine import update_historical_screener

def prog(pct, msg):
    print(f"  [{pct}%] {msg}", flush=True)

print("Running India historical_screener rebuild...", flush=True)
t0 = time.time()
update_historical_screener("INDIA", progress_callback=prog, only_symbols=None, force_rebuild=True, cancel_check=lambda: False)
print(f"Done in {time.time()-t0:.1f}s", flush=True)

import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')
dates = c.execute("""
    SELECT date, COUNT(*) FROM historical_screener
    WHERE date BETWEEN '2026-07-20' AND '2026-07-28'
    GROUP BY date ORDER BY date
""").fetchall()
print("\nHist screener dates after rebuild:")
for d, cnt in dates:
    print(f"  {d}: {cnt} rows")
c.close()
