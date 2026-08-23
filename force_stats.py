import sys, time, traceback, logging
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(levelname)s %(message)s')
t0 = time.time()

from dumbmoney.engine import vectorized_stats_pass

print(f'[{time.time()-t0:.0f}s] Starting full US stats...', flush=True)

errors = []
def progress(d, t):
    if d % 500 == 0 or d == t:
        print(f'[{time.time()-t0:.0f}s] stats {d}/{t}', flush=True)

try:
    n = vectorized_stats_pass('US', only_symbols=None, progress_callback=progress)
    print(f'[{time.time()-t0:.0f}s] Stats done: {n} symbols', flush=True)
except Exception as e:
    print(f'[{time.time()-t0:.0f}s] ERROR: {e}', flush=True)
    traceback.print_exc()

# Verify
import sqlite3
DB = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db'
conn = sqlite3.connect(DB, timeout=10)
conn.execute('PRAGMA busy_timeout=10000')
for sym in ['MU', 'AAPL', 'SNDK', 'NVDA', 'AMD']:
    r = conn.execute("SELECT symbol, price, change_pct, last_updated FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r: print(f'  {r[0]}: price={r[1]}, chg={r[2]}, updated={r[3]}')
fresh = conn.execute("SELECT COUNT(*) FROM stats WHERE last_updated >= '2026-07-27'").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
print(f'Fresh: {fresh}/{total}')
conn.close()
print(f'[{time.time()-t0:.0f}s] DONE', flush=True)
