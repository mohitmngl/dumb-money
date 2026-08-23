import sqlite3, csv, io, urllib.request

req = urllib.request.Request(
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    headers={"User-Agent": "Mozilla/5.0"}
)
resp = urllib.request.urlopen(req, timeout=15)
data = resp.read().decode("utf-8")
reader = csv.reader(io.StringIO(data))
header = next(reader)
nifty500 = set()
for row in reader:
    if row and len(row) > 2:
        sym = row[2].strip()
        if sym:
            nifty500.add(sym + ".NS")
print(f"Nifty 500: {len(nifty500)} symbols", flush=True)

c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

placeholders = ",".join(["?"] * len(nifty500))
rows = c.execute(f"""
    SELECT h.symbol, a.name, h.price, h.change_pct, h.volume, h.weighted_alpha, h.streak
    FROM historical_screener h
    LEFT JOIN assets a ON h.symbol = a.symbol
    WHERE h.date = '2024-03-12'
      AND h.symbol IN ({placeholders})
    ORDER BY h.change_pct DESC
    LIMIT 30
""", list(nifty500)).fetchall()

print(f"\nTop 30 Nifty 500 Gainers on 2024-03-12\n")
print(f"{'#':<4} {'Symbol':<15} {'Name':<30} {'Price':>10} {'Chg%':>8} {'Volume':>12} {'WA':>8} {'Streak':>7}")
print("-" * 100)
for i, (sym, name, price, chg, vol, wa, streak) in enumerate(rows, 1):
    name_short = (name or '')[:28]
    print(f"{i:<4} {sym:<15} {name_short:<30} {price or 0:>10.2f} {chg or 0:>7.2f}% {vol or 0:>12,.0f} {wa or 0:>8.2f} {streak or 0:>7}")

c.close()
