import sqlite3, csv, io, urllib.request

# Fetch Nifty 500
req = urllib.request.Request(
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    headers={"User-Agent": "Mozilla/5.0"}
)
resp = urllib.request.urlopen(req, timeout=15)
data = resp.read().decode("utf-8")
reader = csv.reader(io.StringIO(data))
next(reader)
nifty500 = set()
for row in reader:
    if row and len(row) > 2:
        nifty500.add(row[2].strip() + ".NS")
print(f"Nifty 500: {len(nifty500)} symbols\n", flush=True)

c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

# Get all trading dates in range
dates = [r[0] for r in c.execute("""
    SELECT DISTINCT date FROM historical_screener
    WHERE date BETWEEN '2024-02-23' AND '2024-03-13'
    ORDER BY date
""").fetchall()]
print(f"Trading dates: {len(dates)} ({dates[0]} to {dates[-1]})\n", flush=True)

placeholders = ",".join(["?"] * len(nifty500))

for dt in dates:
    rows = c.execute(f"""
        SELECT h.symbol, a.name, h.price, h.change_pct, h.volume,
               h.prob_up_st_cross, h.weighted_alpha
        FROM historical_screener h
        LEFT JOIN assets a ON h.symbol = a.symbol
        WHERE h.date = ?
          AND h.symbol IN ({placeholders})
          AND h.atr_crossed_above = 1
        ORDER BY h.change_pct DESC
        LIMIT 5
    """, [dt] + list(nifty500)).fetchall()

    print(f"--- {dt} ({len(rows)} crossed above ST) ---")
    if rows:
        for i, (sym, name, price, chg, vol, prob, wa) in enumerate(rows, 1):
            n = (name or '')[:22]
            print(f"  {i}. {sym:<15} {n:<22} +{chg or 0:.2f}%  Rs{price or 0:,.2f}  Vol:{vol or 0:>10,.0f}  ProbST:{prob or 0:.1f}%  WA:{wa or 0:.1f}")
    else:
        print("  (no stocks crossed above ST)")
    print()

c.close()
