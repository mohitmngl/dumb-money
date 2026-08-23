import os, sqlite3
db = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db'
for p in [db+'-shm', db+'-wal']:
    try: os.remove(p)
    except: pass
c = sqlite3.connect(db, timeout=5)
for sym in ['AAPL', 'NVDA', 'MSFT', 'TSLA']:
    row = c.execute('SELECT weighted_alpha FROM stats WHERE symbol=?', (sym,)).fetchone()
    if row: print(f'{sym}: {row[0]:.1f}')
# Check historical for comparison
for sym in ['AAPL', 'NVDA', 'MSFT', 'TSLA']:
    row = c.execute('SELECT weighted_alpha FROM historical_screener WHERE symbol=? ORDER BY date DESC LIMIT 1', (sym,)).fetchone()
    if row: print(f'{sym} historical: {row[0]:.1f}')
c.close()
