import sqlite3, csv, io, urllib.request

# Fetch Nifty 500 symbols
req = urllib.request.Request(
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    headers={"User-Agent": "Mozilla/5.0"}
)
resp = urllib.request.urlopen(req, timeout=15)
data = resp.read().decode("utf-8")
reader = csv.reader(io.StringIO(data))
header = next(reader)
nifty500_raw = set()
for row in reader:
    if row:
        nifty500_raw.add(row[0].strip())

c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

# Check symbol format in DB
sample = c.execute("SELECT symbol FROM assets LIMIT 5").fetchall()
print("DB symbols:", [r[0] for r in sample])

# Check if raw NSE symbols (without .NS) exist
sample_nifty = list(nifty500_raw)[:5]
print("Nifty raw:", sample_nifty)

# Try matching without .NS
nifty500_ns = set(s + ".NS" for s in nifty500_raw)
common = nifty500_ns & set(r[0] for r in c.execute("SELECT symbol FROM assets").fetchall())
print(f"Matched with .NS: {len(common)}")

# Try matching raw
common2 = nifty500_raw & set(r[0] for r in c.execute("SELECT symbol FROM assets").fetchall())
print(f"Matched raw: {len(common2)}")

# Check hist_screener symbols
hs_syms = set(r[0] for r in c.execute("SELECT DISTINCT symbol FROM historical_screener WHERE date='2024-03-12' LIMIT 10").fetchall())
print(f"Hist screener sample: {hs_syms}")

common3 = nifty500_ns & hs_syms
print(f"Hist screener matched with .NS: {len(common3)}")

common4 = nifty500_raw & hs_syms
print(f"Hist screener matched raw: {len(common4)}")

# Try the first matched symbol
test_sym = list(common3)[0] if common3 else list(common4)[0] if common4 else None
print(f"Test symbol: {test_sym}")
if test_sym:
    r = c.execute("SELECT symbol, date, change_pct FROM historical_screener WHERE symbol=? AND date='2024-03-12'", (test_sym,)).fetchone()
    print(f"Result: {r}")

c.close()
