import sqlite3
c = sqlite3.connect("screener.db", timeout=30)
c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
rows = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
strings = c.execute("SELECT COUNT(DISTINCT string_id) FROM historical_string_screener").fetchone()[0]
all_sids = c.execute("SELECT COUNT(*) FROM string_universe WHERE market='US'").fetchone()[0]
print(f"rows={rows:,} strings={strings}/{all_sids}")
# check which strings are missing
covered = set(r[0] for r in c.execute("SELECT DISTINCT string_id FROM historical_string_screener").fetchall())
all_sids_list = [r[0] for r in c.execute("SELECT string_id FROM string_universe WHERE market='US'").fetchall()]
missing = [s for s in all_sids_list if s not in covered]
print(f"missing: {len(missing)}")
if missing:
    print(f"first 5 missing: {missing[:5]}")
    print(f"last 5 missing: {missing[-5:]}")
# check indexes
idxs = c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='historical_string_screener'").fetchall()
print(f"indexes: {[i[0] for i in idxs]}")
# check WAL mode
wal = c.execute("PRAGMA journal_mode").fetchone()
print(f"journal_mode: {wal[0]}")
sync = c.execute("PRAGMA synchronous").fetchone()
print(f"synchronous: {sync[0]}")
c.close()
