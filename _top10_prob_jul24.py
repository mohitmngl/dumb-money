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

c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=60)
c.execute('PRAGMA busy_timeout=60000')

placeholders = ",".join(["?"] * len(nifty500))

# Top 10 by prob_up_st_cross on July 24
rows = c.execute(f"""
    SELECT h.symbol, a.name, h.price, h.change_pct, h.volume,
           h.prob_up_st_cross, h.weighted_alpha, h.atr_crossed_above, h.atr_streak, h.atr_signal
    FROM historical_screener h
    LEFT JOIN assets a ON h.symbol = a.symbol
    WHERE h.date = '2026-07-24'
      AND h.symbol IN ({placeholders})
      AND h.prob_up_st_cross > 0
    ORDER BY h.prob_up_st_cross DESC
    LIMIT 10
""", list(nifty500)).fetchall()

print("Top 10 Nifty 500 by Prob ST Cross Up - 2026-07-24\n")
print(f"{'#':<4} {'Symbol':<15} {'Name':<25} {'Price':>10} {'Chg%':>8} {'ProbST':>8} {'ST_sig':>6} {'ST_str':>6} {'xAbove':>6} {'WA':>8}")
print("-"*100)
for i, (sym, name, price, chg, vol, prob, wa, xabv, st_str, st_sig) in enumerate(rows, 1):
    n = (name or '')[:23]
    print(f"{i:<4} {sym:<15} {n:<25} {price or 0:>10.2f} {chg or 0:>7.2f}% {prob or 0:>7.1f}% {st_sig or 0:>6} {st_str or 0:>6} {xabv or 0:>6} {wa or 0:>8.1f}")

c.close()
