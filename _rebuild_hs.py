"""Rebuild historical_screener for both markets (single-process on Windows)."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dumbmoney.engine import update_historical_screener

if __name__ == '__main__':
    for market in ["US", "INDIA"]:
        print(f"[{time.strftime('%H:%M:%S')}] Starting historical_screener rebuild for {market}...")
        sys.stdout.flush()
        t0 = time.time()
        update_historical_screener(market=market, force_rebuild=True, progress_callback=lambda p, msg: print(f"  [{market}] {p}% {msg}"), parallel=False)
        elapsed = time.time() - t0
        print(f"[{time.strftime('%H:%M:%S')}] {market} rebuild complete in {elapsed/60:.1f} min")
        sys.stdout.flush()

    print("ALL DONE")
