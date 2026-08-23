"""Background HSS rebuild with logging."""
import sys, time, os
sys.path.insert(0, '.')

# Redirect all output to a log file
log = open('_hss_rebuild.log', 'w', buffering=1)
sys.stdout = log
sys.stderr = log

print(f"[{time.strftime('%H:%M:%S')}] Starting HSS rebuild...", flush=True)
try:
    from dumbmoney.basket_screener import update_historical_string_screener
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Import done", flush=True)
    n = update_historical_string_screener(
        market='US', force_rebuild=True,
        progress_callback=lambda p, msg: print(f"[{time.strftime('%H:%M:%S')}] US {p}% {msg}", flush=True)
    )
    print(f"[{time.strftime('%H:%M:%S')}] US done: {n} rows in {time.time()-t0:.1f}s", flush=True)
    
    t1 = time.time()
    n2 = update_historical_string_screener(
        market='INDIA', force_rebuild=True,
        progress_callback=lambda p, msg: print(f"[{time.strftime('%H:%M:%S')}] INDIA {p}% {msg}", flush=True)
    )
    print(f"[{time.strftime('%H:%M:%S')}] INDIA done: {n2} rows in {time.time()-t1:.1f}s", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    import traceback
    traceback.print_exc()
print(f"[{time.strftime('%H:%M:%S')}] ALL DONE", flush=True)
log.close()
