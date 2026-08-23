import sys, time, os
sys.path.insert(0, 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')
os.chdir('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')

from dumbmoney.engine import update_historical_screener

def prog(pct, msg):
    print(f"  [{pct}%] {msg}", flush=True)

# Find symbols that need hist_screener update
import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')
max_bars = dict(c.execute("SELECT symbol, MAX(date) FROM bars WHERE timeframe='1Day' GROUP BY symbol").fetchall())
max_hist = dict(c.execute("SELECT symbol, MAX(date) FROM historical_screener GROUP BY symbol").fetchall())
c.close()
stale = [s for s, bd in max_bars.items() if max_hist.get(s, '') < bd]
print(f"Symbols needing hist_screener update: {len(stale)}", flush=True)

t0 = time.time()
update_historical_screener("INDIA", progress_callback=prog, only_symbols=stale, cancel_check=lambda: False)
print(f"\nDone in {time.time()-t0:.1f}s", flush=True)

# Verify
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')
dates = c.execute("""
    SELECT date, COUNT(*) FROM historical_screener
    WHERE date >= '2026-07-25' GROUP BY date ORDER BY date
""").fetchall()
print("\nHist screener after update:")
for d, cnt in dates:
    print(f"  {d}: {cnt} rows")
c.close()
