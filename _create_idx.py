"""Create composite index for fast per-date top-N queries"""
import sqlite3, time

db_path = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db'
conn = sqlite3.connect(db_path, timeout=60)
conn.execute('PRAGMA journal_mode=WAL')

# Check existing indexes
indexes = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='historical_string_screener'").fetchall()
print("Existing indexes:")
for name, sql in indexes:
    print(f"  {name}: {sql}")

# Create composite indexes for our top-N queries
print("\nCreating composite indexes...", flush=True)

for col in ['prob_up_st_cross', 'weighted_alpha', 'streak', 'atr_streak', 'ai_volume_profile_score']:
    idx_name = f'idx_hss_{col}'
    try:
        t0 = time.time()
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON historical_string_screener(date, {col} DESC)")
        conn.commit()
        print(f"  {idx_name}: created ({time.time()-t0:.0f}s)", flush=True)
    except Exception as e:
        print(f"  {idx_name}: {e}", flush=True)

# Test speed
print("\nTesting query speed...", flush=True)
t0 = time.time()
for d in ['2026-01-15', '2025-06-15', '2024-01-15']:
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL AND atr_crossed_above = 1
        ORDER BY prob_up_st_cross DESC LIMIT 30
    """, (d,)).fetchall()
    print(f"  {d}: {len(rows)} rows", flush=True)
print(f"  Total: {time.time()-t0:.2f}s for 3 dates", flush=True)

conn.close()
print("DONE", flush=True)
