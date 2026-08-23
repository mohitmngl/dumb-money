"""Rebuild historical_string_screener for US and India.
Uses the existing function but with explicit error handling."""
import sys, time, traceback
sys.path.insert(0, '.')
from dumbmoney.basket_screener import update_historical_string_screener

for market in ['US', 'INDIA']:
    t0 = time.time()
    print(f'[{time.strftime("%H:%M:%S")}] Starting {market} HSS rebuild...', flush=True)
    try:
        n = update_historical_string_screener(
            market=market,
            force_rebuild=True,
            progress_callback=lambda p, msg: print(f'  [{market}] {p}% {msg}', flush=True)
        )
        print(f'[{market}] Done: {n} rows in {time.time()-t0:.1f}s', flush=True)
    except Exception as e:
        print(f'[{market}] ERROR: {e}', flush=True)
        traceback.print_exc()
        sys.stdout.flush()
