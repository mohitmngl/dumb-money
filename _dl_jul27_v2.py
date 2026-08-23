import sys, time, os
sys.path.insert(0, 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')
os.chdir('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')

from dumbmoney.data_india import download_bars_india

print("Downloading India bars starting from 2026-07-25...", flush=True)
t0 = time.time()
try:
    download_bars_india(start_date="2026-07-25")
    print(f"Download done in {time.time()-t0:.1f}s", flush=True)
except Exception as e:
    print(f"Download error: {e}", flush=True)
    import traceback
    traceback.print_exc()

# Verify
import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')
dates = c.execute("""
    SELECT date, COUNT(*) FROM bars WHERE timeframe='1Day'
    AND date >= '2026-07-25' GROUP BY date ORDER BY date
""").fetchall()
print("\nBars after download:")
for d, cnt in dates:
    print(f"  {d}: {cnt} bars")
c.close()
