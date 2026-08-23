import sqlite3

conn = sqlite3.connect('screener.db')
print("=== US Asset Classes ===")
for r in conn.execute('SELECT asset_class, COUNT(*) as cnt FROM assets GROUP BY asset_class ORDER BY cnt DESC'):
    print(f"  {r[0]}: {r[1]}")

print("\n=== Stats asset_class ===")
for r in conn.execute('SELECT asset_class, COUNT(*) as cnt FROM stats GROUP BY asset_class ORDER BY cnt DESC'):
    print(f"  {r[0]}: {r[1]}")

print("\n=== Possible ETFs labeled as us_equity (name contains etf/fund/trust/spac/index) ===")
rows = conn.execute("""SELECT a.symbol, a.name, a.asset_class FROM assets a
    WHERE a.asset_class='us_equity'
    AND (LOWER(a.name) LIKE '%etf%' OR LOWER(a.name) LIKE '%fund%'
         OR LOWER(a.name) LIKE '%trust%' OR LOWER(a.name) LIKE '%spac%'
         OR LOWER(a.name) LIKE '%index%' OR LOWER(a.name) LIKE '%bond%'
         OR LOWER(a.name) LIKE '%treasury%' OR LOWER(a.name) LIKE '%note%')
    LIMIT 50""").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} [{r[2]}]")
print(f"  Total suspected: {len(rows)}")

print("\n=== Alpaca asset_class values for these symbols ===")
for r in conn.execute("""SELECT a.symbol, a.name, a.asset_class, a.class_type FROM assets a
    WHERE a.asset_class='us_equity'
    AND (LOWER(a.name) LIKE '%etf%' OR LOWER(a.name) LIKE '%fund%'
         OR LOWER(a.name) LIKE '%trust%' OR LOWER(a.name) LIKE '%spac%'
         OR LOWER(a.name) LIKE '%index%' OR LOWER(a.name) LIKE '%bond%'
         OR LOWER(a.name) LIKE '%treasury%' OR LOWER(a.name) LIKE '%note%')
    LIMIT 50"""):
    print(f"  {r[0]}: class_type={r[3]}, name={r[1]}")

print("\n=== What class_type values exist in assets? ===")
for r in conn.execute('SELECT class_type, COUNT(*) FROM assets GROUP BY class_type ORDER BY COUNT(*) DESC'):
    print(f"  {r[0]}: {r[1]}")

print("\n=== Assets where class_type != asset_class (mismatch) ===")
rows = conn.execute("""SELECT symbol, name, asset_class, class_type FROM assets
    WHERE class_type IS NOT NULL AND class_type != '' AND class_type != asset_class
    LIMIT 50""").fetchall()
for r in rows:
    print(f"  {r[0]}: asset_class={r[2]}, class_type={r[3]}, name={r[1]}")
print(f"  Total mismatch: {len(rows)}")

conn.close()
