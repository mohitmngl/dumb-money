import sqlite3, csv, io, urllib.request

# Fetch Nifty 500 symbols
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
print(f"Nifty 500: {len(nifty500)} symbols", flush=True)

c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

placeholders = ",".join(["?"] * len(nifty500))

# List 1: Crossed above ST, sorted by change_pct
rows1 = c.execute(f"""
    SELECT h.symbol, a.name, h.price, h.change_pct, h.volume,
           h.atr_signal, h.atr_streak, h.atr_crossed_above, h.atr_multiplier,
           h.prob_up_st_cross, h.weighted_alpha, h.streak
    FROM historical_screener h
    LEFT JOIN assets a ON h.symbol = a.symbol
    WHERE h.date = '2024-03-12'
      AND h.symbol IN ({placeholders})
      AND h.atr_crossed_above = 1
    ORDER BY h.change_pct DESC
""", list(nifty500)).fetchall()

print(f"\n{'='*110}")
print(f"LIST 1: Nifty 500 Stocks That Crossed Above SuperTrend on 2024-03-12")
print(f"        (sorted by Change%)")
print(f"        Total: {len(rows1)} stocks")
print(f"{'='*110}")
print(f"{'#':<4} {'Symbol':<15} {'Name':<25} {'Price':>10} {'Chg%':>8} {'Vol':>10} {'ST_sig':>6} {'ST_str':>6} {'xABV':>5} {'Mult':>5} {'ProbST':>8} {'WA':>8}")
print("-"*110)
for i, (sym, name, price, chg, vol, st_sig, st_str, xabv, mult, prob, wa, stk) in enumerate(rows1, 1):
    n = (name or '')[:23]
    print(f"{i:<4} {sym:<15} {n:<25} {price or 0:>10.2f} {chg or 0:>7.2f}% {vol or 0:>10,.0f} {st_sig or 0:>6} {st_str or 0:>6} {xabv or 0:>5} {mult or 0:>5.1f} {prob or 0:>8.2f} {wa or 0:>8.2f}")

# List 2: Same stocks, sorted by prob_up_st_cross
rows2 = c.execute(f"""
    SELECT h.symbol, a.name, h.price, h.change_pct, h.volume,
           h.atr_signal, h.atr_streak, h.atr_crossed_above, h.atr_multiplier,
           h.prob_up_st_cross, h.weighted_alpha, h.streak
    FROM historical_screener h
    LEFT JOIN assets a ON h.symbol = a.symbol
    WHERE h.date = '2024-03-12'
      AND h.symbol IN ({placeholders})
      AND h.atr_crossed_above = 1
    ORDER BY h.prob_up_st_cross DESC
""", list(nifty500)).fetchall()

print(f"\n{'='*110}")
print(f"LIST 2: Same Stocks Sorted by SuperTrend Up Probability (prob_up_st_cross)")
print(f"        Total: {len(rows2)} stocks")
print(f"{'='*110}")
print(f"{'#':<4} {'Symbol':<15} {'Name':<25} {'Price':>10} {'Chg%':>8} {'Vol':>10} {'ST_sig':>6} {'ST_str':>6} {'xABV':>5} {'Mult':>5} {'ProbST':>8} {'WA':>8}")
print("-"*110)
for i, (sym, name, price, chg, vol, st_sig, st_str, xabv, mult, prob, wa, stk) in enumerate(rows2, 1):
    n = (name or '')[:23]
    print(f"{i:<4} {sym:<15} {n:<25} {price or 0:>10.2f} {chg or 0:>7.2f}% {vol or 0:>10,.0f} {st_sig or 0:>6} {st_str or 0:>6} {xabv or 0:>5} {mult or 0:>5.1f} {prob or 0:>8.2f} {wa or 0:>8.2f}")

c.close()
