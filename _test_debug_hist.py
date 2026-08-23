import sys, time, os, traceback
sys.path.insert(0, 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')
os.chdir('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')

# Monkey-patch to add debug
import dumbmoney.engine as eng
_orig_compute = eng._compute_symbol_batch
_call_count = [0]
_return_counts = [0]

def debug_compute(args):
    _call_count[0] += 1
    result = _orig_compute(args)
    _return_counts[0] += len(result)
    if _call_count[0] <= 3 or _call_count[0] % 10 == 0:
        print(f"  batch #{_call_count[0]}: {args[0][:2]}... returned {len(result)} records (cumulative: {_return_counts[0]})", flush=True)
    return result

eng._compute_symbol_batch = debug_compute

print("Running update_historical_screener with debug patch...", flush=True)

def prog(pct, msg):
    print(f"  [{pct}%] {msg}", flush=True)

t0 = time.time()
try:
    eng.update_historical_screener("US", progress_callback=prog, only_symbols=None, cancel_check=lambda: False)
except Exception as e:
    print(f"Exception: {e}", flush=True)
    traceback.print_exc()

elapsed = time.time() - t0
print(f"\nDone in {elapsed:.1f}s", flush=True)
print(f"Total batches called: {_call_count[0]}", flush=True)
print(f"Total records returned: {_return_counts[0]}", flush=True)

import sqlite3
conn = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', timeout=15)
conn.execute('PRAGMA busy_timeout=10000')
r = conn.execute("SELECT COUNT(*), MAX(date) FROM historical_screener").fetchone()
print(f"After: {r[0]} rows, max date {r[1]}", flush=True)
conn.close()
