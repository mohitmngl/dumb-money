import sys, traceback
print("Starting test...", flush=True)
try:
    from dumbmoney.engine import update_historical_screener
    print("Import OK", flush=True)
    
    def prog(pct, msg):
        print(f"  [{pct}%] {msg}", flush=True)
    
    print("Calling update_historical_screener...", flush=True)
    update_historical_screener("US", progress_callback=prog, only_symbols=None, cancel_check=lambda: False)
    print("Done", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
