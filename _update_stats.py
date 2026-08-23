import sqlite3

conn = sqlite3.connect('screener.db')
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")

# Build mapping
mapping = dict(conn.execute("SELECT symbol, asset_class FROM assets").fetchall())
print(f"Loaded {len(mapping)} asset mappings")

# Use temp table for fast join update
conn.execute("DROP TABLE IF EXISTS _tmp_class")
conn.execute("CREATE TEMP TABLE _tmp_class (symbol TEXT PRIMARY KEY, asset_class TEXT)")
conn.executemany("INSERT INTO _tmp_class VALUES (?, ?)", list(mapping.items()))
conn.commit()
print("Temp table created")

conn.execute("UPDATE stats SET asset_class = (SELECT t.asset_class FROM _tmp_class t WHERE t.symbol = stats.symbol) WHERE stats.symbol IN (SELECT t.symbol FROM _tmp_class t)")
conn.commit()
print("Stats updated")

print("\n=== Stats asset_class distribution ===")
for r in conn.execute("SELECT asset_class, COUNT(*) FROM stats GROUP BY asset_class ORDER BY COUNT(*) DESC"):
    print(f"  {r[0]}: {r[1]}")

conn.execute("DROP TABLE _tmp_class")
conn.execute("ANALYZE")
conn.commit()
print("\nDone!")
conn.close()
