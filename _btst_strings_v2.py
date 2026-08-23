"""BTST on US strings - date-by-date SQL approach (fast)"""
import numpy as np, pandas as pd, sys, io, os, time, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

db_path = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db'
conn = sqlite3.connect(db_path)

# Get distinct dates
dates = [r[0] for r in conn.execute(
    "SELECT DISTINCT date FROM historical_string_screener WHERE next_day_return IS NOT NULL ORDER BY date"
).fetchall()]
print(f"Dates with returns: {len(dates)} ({dates[0]} to {dates[-1]})", flush=True)

# Strategy configs
strategies = [
    ("S1: atr_crossed_above + prob_up_st_cross top30",
     "atr_crossed_above=1", "prob_up_st_cross", 30),
    ("S2: No filter, weighted_alpha top15",
     None, "weighted_alpha", 15),
    ("S3: No filter, streak top10",
     None, "streak", 10),
    ("S4: atr_signal & accel_signal + prob_up_st_cross top20",
     "atr_signal=1 AND accel_signal=1", "prob_up_st_cross", 20),
    ("S5: No filter, ai_volume_profile_score top15",
     None, "ai_volume_profile_score", 15),
    ("S6: atr_crossed_above + atr_streak top30",
     "atr_crossed_above=1", "atr_streak", 30),
]

for name, filt, rank_col, topn in strategies:
    print(f"\n{'='*90}", flush=True)
    print(f"  {name}", flush=True)
    print(f"{'='*90}", flush=True)
    
    equity = 1.0
    rets = []
    dts = []
    
    where_extra = f"AND {filt}" if filt else ""
    
    for d in dates:
        sql = f"""
            SELECT next_day_return FROM historical_string_screener
            WHERE date = ? AND next_day_return IS NOT NULL {where_extra}
            ORDER BY {rank_col} DESC LIMIT {topn}
        """
        rows = conn.execute(sql, (d,)).fetchall()
        if len(rows) >= max(5, topn//2):
            arr = np.array([r[0] for r in rows])
            r_mean = np.mean(arr)
            # next_day_return is stored as percentage (x100)
            r_dec = r_mean / 100.0
            equity *= (1 + r_dec)
            rets.append(r_dec)
            dts.append(d)
    
    arr = np.array(rets)
    print(f"  Days: {len(arr)}", flush=True)
    if len(arr) > 0:
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
        for y in range(int(dts[0][:4]), int(dts[-1][:4])+1):
            mask = [i for i,d2 in enumerate(dts) if d2.startswith(str(y))]
            if len(mask)==0: continue
            yr = arr[mask]
            ann = np.prod(1+yr)-1
            print(f"    {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)", flush=True)
        
        # Monthly last 12
        print("  MONTHLY (last 12):", flush=True)
        months = {}
        for i,d2 in enumerate(dts):
            k = d2[:7]
            months.setdefault(k,[]).append(arr[i])
        for k, v in list(months.items())[-12:]:
            mon = np.prod(1+np.array(v))-1
            print(f"    {k}: {mon*100:>+7.1f}%  ({len(v)}d)", flush=True)

conn.close()
print("\nALL DONE", flush=True)
