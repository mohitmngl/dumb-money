import sys, os, time
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
os.chdir(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')

print("Starting vectorized stats pass...")
t0 = time.time()
from dumbmoney.engine import vectorized_stats_pass
result = vectorized_stats_pass('US')
print(f"Stats pass completed: {result} symbols in {time.time()-t0:.1f}s")

import sqlite3
c = sqlite3.connect(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db', timeout=3)
for sym in ['AAPL', 'NVDA', 'MSFT', 'TSLA']:
    row = c.execute("SELECT symbol, weighted_alpha FROM stats WHERE symbol = ?", (sym,)).fetchone()
    if row:
        print(f'{sym} current stats WA: {row[1]:.1f}')
c.close()
print("Done!")
