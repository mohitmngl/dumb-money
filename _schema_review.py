"""P9: DB schema review for historical_string_screener and related tables."""
import sqlite3

c = sqlite3.connect("screener.db", timeout=5)

# 1. Check existing indexes on historical_string_screener
print("=== historical_string_screener indexes ===")
idxs = c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='historical_string_screener'").fetchall()
for name, sql in idxs:
    print(f"  {name}: {sql}")

# 2. Check table schema
print("\n=== historical_string_screener schema ===")
schema = c.execute("PRAGMA table_info(historical_string_screener)").fetchall()
for col in schema:
    print(f"  {col[1]} ({col[2]})")

# 3. Check string_screener_metrics indexes
print("\n=== string_screener_metrics indexes ===")
idxs2 = c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='string_screener_metrics'").fetchall()
for name, sql in idxs2:
    print(f"  {name}: {sql}")

# 4. Check string_constituents indexes
print("\n=== string_constituents indexes ===")
idxs3 = c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='string_constituents'").fetchall()
for name, sql in idxs3:
    print(f"  {name}: {sql}")

# 5. Check string_universe indexes
print("\n=== string_universe indexes ===")
idxs4 = c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='string_universe'").fetchall()
for name, sql in idxs4:
    print(f"  {name}: {sql}")

# 6. Query plan for date-filter query (most common)
print("\n=== Query plan: date-filter sort by change_pct ===")
plan = c.execute("EXPLAIN QUERY PLAN SELECT h.string_id, h.date, h.price, h.change_pct, h.weighted_alpha FROM historical_string_screener h WHERE h.date = '2026-07-17' ORDER BY h.change_pct DESC LIMIT 50 OFFSET 0").fetchall()
for row in plan:
    print(f"  {row}")

# 7. Query plan for date-filter with string_id
print("\n=== Query plan: date-filter + string_id LIKE ===")
plan2 = c.execute("EXPLAIN QUERY PLAN SELECT h.string_id, h.date, h.price, h.change_pct, h.weighted_alpha FROM historical_string_screener h WHERE h.date = '2026-07-17' AND h.string_id LIKE 'S000%' ORDER BY h.weighted_alpha DESC LIMIT 50 OFFSET 0").fetchall()
for row in plan2:
    print(f"  {row}")

# 8. Check DB settings
print("\n=== DB settings ===")
for key in ["journal_mode", "wal_autocheckpoint", "synchronous", "cache_size", "mmap_size"]:
    try:
        r = c.execute(f"PRAGMA {key}").fetchone()
        print(f"  {key}: {r[0]}")
    except:
        pass

# 9. Check table sizes
print("\n=== Table row counts ===")
for tbl in ["historical_string_screener", "string_screener_metrics", "string_universe", "string_constituents"]:
    try:
        r = c.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
        print(f"  {tbl}: {r[0]:,}")
    except:
        pass

c.close()
