"""Test DB initialization step by step."""
import sys, os, time, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dumbmoney.db import US_DB, INDIA_DB, SCHEMA_SQL, INDEXES_SQL, ensure_schema, migrate_nulls

for name, db_path in [("US", US_DB), ("INDIA", INDIA_DB)]:
    print(f"\n=== {name}: {db_path} ===")
    if not os.path.exists(db_path):
        print(f"  DB not found, skipping")
        continue
    
    t0 = time.time()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-64000")
    print(f"  connected in {time.time()-t0:.1f}s")
    
    # Test schema
    t1 = time.time()
    conn.executescript(SCHEMA_SQL)
    print(f"  SCHEMA_SQL in {time.time()-t1:.1f}s")
    
    # Test each index individually
    for stmt in INDEXES_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            t2 = time.time()
            try:
                conn.execute(stmt)
                elapsed = time.time() - t2
                if elapsed > 1:
                    print(f"  SLOW ({elapsed:.1f}s): {stmt[:80]}")
            except Exception as e:
                print(f"  ERROR: {e}")
    
    print(f"  total: {time.time()-t0:.1f}s")
    conn.close()

print("\nDone!")
