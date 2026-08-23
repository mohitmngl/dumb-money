import sys, time, os
sys.path.insert(0, 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')
os.chdir('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')

# Download India bars for July 27-28
from dumbmoney.data_india import _download_india_bars

print("Downloading India bars for Jul 27-28...", flush=True)
t0 = time.time()
try:
    result = _download_india_bars("INDIA", start_date="2026-07-27", end_date="2026-07-28")
    print(f"Download done in {time.time()-t0:.1f}s: {result}", flush=True)
except Exception as e:
    print(f"Download error: {e}", flush=True)
    import traceback
    traceback.print_exc()
