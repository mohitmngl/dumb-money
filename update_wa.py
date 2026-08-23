import os, sqlite3, time

db = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db'
shm = db + '-shm'
wal = db + '-wal'
for p in [shm, wal]:
    try:
        if os.path.exists(p):
            os.remove(p)
    except:
        pass

c = sqlite3.connect(db, timeout=10, isolation_level=None)
c.execute('PRAGMA busy_timeout=30000')

# Get latest WA per symbol from historical_screener
t0 = time.time()
latest = {}
for row in c.execute("""
    SELECT h.symbol, h.weighted_alpha
    FROM historical_screener h
    INNER JOIN (SELECT symbol, MAX(date) as max_date FROM historical_screener GROUP BY symbol) m
    ON h.symbol = m.symbol AND h.date = m.max_date
"""):
    latest[row[0]] = row[1]
t1 = time.time()
print(f"Got latest WA for {len(latest)} symbols in {t1-t0:.1f}s")

# Update in batches
t2 = time.time()
batch = []
for sym, wa in latest.items():
    batch.append((wa, sym))
    if len(batch) >= 5000:
        c.executemany('UPDATE stats SET weighted_alpha = ? WHERE symbol = ?', batch)
        batch = []
if batch:
    c.executemany('UPDATE stats SET weighted_alpha = ? WHERE symbol = ?', batch)
c.execute('COMMIT')
t3 = time.time()
print(f"Updated in {t3-t2:.1f}s")

# Verify
for sym in ['AAPL', 'NVDA', 'MSFT', 'TSLA']:
    row = c.execute('SELECT weighted_alpha FROM stats WHERE symbol=?', (sym,)).fetchone()
    if row:
        print(f'{sym} new WA: {row[1]:.1f}')

c.close()
print("Done!")
