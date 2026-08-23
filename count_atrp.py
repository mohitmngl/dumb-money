import sqlite3, time

conn = sqlite3.connect(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db', timeout=30)

print("=== STOCK COUNT BY ATRP THRESHOLD ===")
for thr in [5, 10, 15, 20, 30, 50]:
    r = conn.execute("SELECT COUNT(*) FROM stats WHERE atrp > ? AND price > 5 AND volume > 100000", (thr,)).fetchone()
    r2 = conn.execute("SELECT COUNT(*) FROM stats WHERE atrp > ? AND price > 5 AND volume > 500000", (thr,)).fetchone()
    print(f"  ATRP>{thr}%: vol>100K = {r[0]}, vol>500K = {r2[0]}")

r = conn.execute("SELECT COUNT(*) FROM stats WHERE atrp > 10 AND price > 5 AND volume > 100000").fetchone()
n_stocks = r[0]
print(f"\nTarget: ATRP>10%, price>$5, vol>100K = {n_stocks} stocks")

# Alpaca rate limit: ~200 req/min for IEX
# Each stock = 1 request for 1-min bars
# With parallel or sequential
print(f"\n=== TIME ESTIMATE ===")
print(f"  1 req per stock, sequential")
print(f"  Alpaca IEX rate limit: ~200 req/min (3.3/sec)")
print(f"  Sequential: {n_stocks / 3.3:.0f}s = {n_stocks / 3.3 / 60:.1f} min")
print(f"  With 10 parallel: {n_stocks / 33:.0f}s = {n_stocks / 33 / 60:.1f} min")
print(f"  Each 1min bar request returns up to 1000 bars")

conn.close()
