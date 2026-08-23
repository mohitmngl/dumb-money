import sys, time, os, traceback
sys.path.insert(0, 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')
os.chdir('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')

print("Testing update_historical_screener after removing lazy import...", flush=True)

from dumbmoney.engine import update_historical_screener

def prog(pct, msg):
    print(f"  [{pct}%] {msg}", flush=True)

t0 = time.time()
try:
    update_historical_screener("US", progress_callback=prog, only_symbols=None, cancel_check=lambda: False)
except Exception as e:
    print(f"Exception: {e}", flush=True)
    traceback.print_exc()

elapsed = time.time() - t0
print(f"\nDone in {elapsed:.1f}s", flush=True)

import sqlite3
conn = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', timeout=15)
conn.execute('PRAGMA busy_timeout=10000')
r = conn.execute("SELECT COUNT(*), MAX(date) FROM historical_screener").fetchone()
print(f"After: {r[0]} rows, max date {r[1]}", flush=True)
r = conn.execute("SELECT COUNT(*) FROM historical_screener WHERE date='2026-07-24'").fetchone()
print(f"Rows on 2026-07-24: {r[0]}", flush=True)
conn.close()
