import sys, time, traceback
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
t0 = time.time()

try:
    from dumbmoney.engine import vectorized_stats_pass
    print(f'[{time.time()-t0:.0f}s] Running vectorized_stats_pass(US, only_symbols=None)...', flush=True)
    n = vectorized_stats_pass('US', only_symbols=None)
    print(f'[{time.time()-t0:.0f}s] Stats: {n} symbols computed', flush=True)
except Exception as e:
    print(f'[{time.time()-t0:.0f}s] ERROR in stats: {e}', flush=True)
    traceback.print_exc()

try:
    from dumbmoney.refresh import update_historical_screener
    print(f'[{time.time()-t0:.0f}s] Running historical_screener...', flush=True)
    update_historical_screener('US', only_symbols=None)
    print(f'[{time.time()-t0:.0f}s] Historical done', flush=True)
except Exception as e:
    print(f'[{time.time()-t0:.0f}s] ERROR in historical: {e}', flush=True)
    traceback.print_exc()

import sqlite3
DB = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db'
conn = sqlite3.connect(DB, timeout=10)
conn.execute('PRAGMA busy_timeout=10000')
for sym in ['MU', 'AAPL', 'SNDK', 'NVDA']:
    r = conn.execute("SELECT symbol, price, change_pct FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r: print(f'  {r[0]}: price={r[1]}, chg={r[2]}')
r = conn.execute("SELECT MAX(date) FROM historical_screener").fetchone()
print(f'hist screener max: {r[0]}')
conn.close()
print(f'[{time.time()-t0:.0f}s] ALL DONE', flush=True)
