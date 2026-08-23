"""Fast BTST on US strings - load into pandas first, iterate in-memory"""
import numpy as np, pandas as pd, sys, io, time, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

db_path = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db'
conn = sqlite3.connect(db_path, timeout=60)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=120000')
conn.execute('PRAGMA cache_size=-128000')

# Load 2024+ data into pandas
print("Loading 2024+ data...", flush=True)
t0 = time.time()
df = pd.read_sql("""
    SELECT date, string_id, next_day_return, atr_crossed_above, prob_up_st_cross,
           weighted_alpha, streak, atr_streak, atr_signal, accel_signal,
           ai_volume_profile_score, atr_value
    FROM historical_string_screener
    WHERE date >= '2024-01-01' AND next_day_return IS NOT NULL
""", conn)
conn.close()
print(f"Loaded {len(df)} rows in {time.time()-t0:.0f}s", flush=True)

df['date'] = df['date'].astype(str)
df['ret'] = df['next_day_return'] / 100.0
df['ret'] = df['ret'].clip(-0.5, 2.0)  # clip outliers
dates = sorted(df['date'].unique())
print(f"Dates: {len(dates)} ({dates[0]} to {dates[-1]})")

strategies = [
    ("S1: atr_crossed_above + prob_up_st_cross top30",
     lambda d: d[d['atr_crossed_above']==1], "prob_up_st_cross", 30),
    ("S2: No filter, weighted_alpha top15",
     lambda d: d, "weighted_alpha", 15),
    ("S3: No filter, streak top10",
     lambda d: d, "streak", 10),
    ("S4: atr_signal & accel_signal + prob_up_st_cross top20",
     lambda d: d[(d['atr_signal']==1) & (d['accel_signal']==1)], "prob_up_st_cross", 20),
    ("S5: No filter, ai_volume_profile_score top15",
     lambda d: d, "ai_volume_profile_score", 15),
]

for name, filt_fn, rank_col, topn in strategies:
    print(f"\n{'='*90}", flush=True)
    print(f"  {name}", flush=True)
    print(f"{'='*90}", flush=True)
    t0 = time.time()
    
    equity = 1.0
    rets = []
    dts = []
    
    for d in dates:
        day = df[df['date']==d]
        filtered = filt_fn(day)
        if len(filtered) < max(5, topn//2): continue
        top = filtered.nlargest(topn, rank_col)
        r = top['ret'].mean()
        if np.isfinite(r):
            equity *= (1 + r)
            rets.append(r)
            dts.append(d)
    
    arr = np.array(rets)
    elapsed = time.time()-t0
    print(f"  Done in {elapsed:.0f}s", flush=True)
    if len(arr) > 0:
        print(f"  Days: {len(arr)}", flush=True)
        print(f"  $1 -> ${equity:.2f}  Total: {(equity-1)*100:.1f}%", flush=True)
        print(f"  Avg Daily: {np.mean(arr)*100:.3f}%  Median: {np.median(arr)*100:.3f}%  Std: {np.std(arr)*100:.3f}%", flush=True)
        print(f"  Best: {np.max(arr)*100:.2f}%  Worst: {np.min(arr)*100:.2f}%", flush=True)
        print(f"  WR: {np.mean(arr>0)*100:.1f}% ({np.sum(arr>0)}/{len(arr)})", flush=True)
        sh = np.mean(arr)/np.std(arr)*np.sqrt(252) if np.std(arr)>0 else 0
        print(f"  Sharpe: {sh:.2f}", flush=True)
        rm = np.maximum.accumulate(np.cumprod(1+arr))
        dd = (np.cumprod(1+arr) - rm) / rm
        print(f"  MaxDD: {np.min(dd)*100:.1f}%", flush=True)
        # Annual
        print("  ANNUAL:", flush=True)
        for y in range(2024, 2027):
            mask = [i for i,d2 in enumerate(dts) if d2.startswith(str(y))]
            if len(mask)==0: continue
            yr = arr[mask]
            ann = np.prod(1+yr)-1
            print(f"    {y}: {ann*100:>+8.1f}%  ({len(yr)}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)", flush=True)
        # Monthly last 12
        print("  MONTHLY (last 12):", flush=True)
        months = {}
        for i,d2 in enumerate(dts):
            months.setdefault(d2[:7],[]).append(arr[i])
        for k, v in list(months.items())[-12:]:
            mon = np.prod(1+np.array(v))-1
            print(f"    {k}: {mon*100:>+7.1f}%  ({len(v)}d)", flush=True)

print("\nALL DONE", flush=True)
