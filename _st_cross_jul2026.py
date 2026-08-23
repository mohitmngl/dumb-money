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

# Check available dates
dates_check = c.execute("""
    SELECT DISTINCT date FROM historical_screener
    WHERE date IN ('2026-07-23','2026-07-24','2026-07-25','2026-07-26','2026-07-27')
    ORDER BY date
""").fetchall()
print(f"Available dates near target: {[r[0] for r in dates_check]}\n", flush=True)

placeholders = ",".join(["?"] * len(nifty500))

for dt in ['2026-07-24', '2026-07-25', '2026-07-27']:
    rows = c.execute(f"""
        SELECT h.symbol, a.name, h.price, h.change_pct, h.volume,
               h.prob_up_st_cross, h.weighted_alpha, h.atr_signal, h.atr_streak
        FROM historical_screener h
        LEFT JOIN assets a ON h.symbol = a.symbol
        WHERE h.date = ?
          AND h.symbol IN ({placeholders})
          AND h.atr_crossed_above = 1
        ORDER BY h.change_pct DESC
        LIMIT 5
    """, [dt] + list(nifty500)).fetchall()

    total_cross = c.execute(f"""
        SELECT COUNT(*) FROM historical_screener h
        WHERE h.date = ? AND h.symbol IN ({placeholders}) AND h.atr_crossed_above = 1
    """, [dt] + list(nifty500)).fetchone()[0]

    print(f"=== {dt} ({total_cross} Nifty 500 stocks crossed above ST) ===")
    if rows:
        for i, (sym, name, price, chg, vol, prob, wa, st_sig, st_str) in enumerate(rows, 1):
            n = (name or '')[:22]
            print(f"  {i}. {sym:<15} {n:<22} +{chg or 0:.2f}%  Rs{price or 0:,.2f}  Vol:{vol or 0:>10,.0f}  ProbST:{prob or 0:.1f}%  WA:{wa or 0:.1f}")
    else:
        print("  (no stocks crossed above ST)")
    print()

c.close()
