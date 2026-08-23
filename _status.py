import sqlite3
c = sqlite3.connect("screener.db", timeout=30)
c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
total = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
strings = c.execute("SELECT COUNT(DISTINCT string_id) FROM historical_string_screener").fetchone()[0]
all_sids = c.execute("SELECT COUNT(*) FROM string_universe WHERE market='US'").fetchone()[0]
missing = all_sids - strings
print(f"rows={total:,} strings={strings}/{all_sids} missing={missing}")
c.close()
