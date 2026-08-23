"""Step 1: Create parquet cache from DB (run once)"""
import pandas as pd, sys, io, time, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

db_path = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db'
conn = sqlite3.connect(db_path)

# Load in yearly chunks and save parquet
cols = "date, string_id, next_day_return, atr_crossed_above, prob_up_st_cross, weighted_alpha, streak, atr_streak, atr_signal, accel_signal, ai_volume_profile_score"

print("Loading 2020...", flush=True)
dfs = []
for y in range(2020, 2027):
    t0 = time.time()
    chunk = pd.read_sql(f"SELECT {cols} FROM historical_string_screener WHERE date LIKE '{y}-%' AND next_day_return IS NOT NULL", conn)
    print(f"  {y}: {len(chunk)} rows ({time.time()-t0:.0f}s)", flush=True)
    dfs.append(chunk)

conn.close()
df = pd.concat(dfs, ignore_index=True)
print(f"Total: {len(df)} rows", flush=True)

# Save parquet
out = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/strategy_results/US_strings_cache.parquet'
df.to_parquet(out, index=False)
print(f"Saved to {out}", flush=True)
