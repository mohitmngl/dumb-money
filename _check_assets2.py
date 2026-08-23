import sqlite3

conn = sqlite3.connect('screener.db')

# Check what columns assets has
print("=== assets table columns ===")
for r in conn.execute("PRAGMA table_info(assets)"):
    print(f"  {r[1]}: {r[2]}")

print("\n=== All asset classes and exchange values ===")
for r in conn.execute('SELECT asset_class, exchange, COUNT(*) FROM assets GROUP BY asset_class, exchange ORDER BY COUNT(*) DESC'):
    print(f"  {r[0]} | {r[1]}: {r[2]}")

# Check how Alpaca returns asset types
print("\n=== Sample symbols with ETF in name ===")
rows = conn.execute("""SELECT symbol, name, asset_class, exchange FROM assets
    WHERE LOWER(name) LIKE '%etf%'
    LIMIT 30""").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} [{r[2]}] ({r[3]})")

print(f"\n  Total ETFs by name: {len(rows)}")

# Check how Alpaca classifies ETFs
print("\n=== Check Alpaca data_us if it has class info ===")
try:
    for r in conn.execute("PRAGMA table_info(data_us)"):
        print(f"  {r[1]}: {r[2]}")
except:
    print("  No data_us table")

conn.close()
