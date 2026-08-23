"""Force fix the idx_hs_date schema corruption by directly manipulating sqlite_master."""
import sqlite3, time
c = sqlite3.connect("screener.db", timeout=600)
c.execute("PRAGMA journal_mode=WAL")
c.execute("PRAGMA synchronous=FULL")

# Check if we can detect the index via EXPLAIN
plan = c.execute("EXPLAIN QUERY PLAN SELECT date FROM historical_string_screener WHERE date='2026-01-01'").fetchall()
print(f"Query plan: {plan}")

# Try enabling writable_schema to directly remove the stale entry
c.execute("PRAGMA writable_schema=ON")
# Check sqlite_master directly for any index on historical_string_screener with date
rows = c.execute("SELECT rowid, * FROM sqlite_master WHERE name LIKE '%idx_hs%' OR (type='index' AND tbl_name='historical_string_screener')").fetchall()
print(f"Master rows for hss indexes: {rows}")
# Check ALL indexes on ALL tables named idx_hs
rows2 = c.execute("SELECT rowid, type, name, tbl_name, rootpage FROM sqlite_master WHERE name LIKE '%idx_hs%'").fetchall()
print(f"All idx_hs entries: {rows2}")
c.close()
