"""Fast BTST on US strings - just S1, output to file"""
import numpy as np, sys, io, os, time, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

db_path = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db'
conn = sqlite3.connect(db_path)

# Get dates
dates = [r[0] for r in conn.execute(
    "SELECT DISTINCT date FROM historical_string_screener WHERE next_day_return IS NOT NULL ORDER BY date"
).fetchall()]
print(f"Dates: {len(dates)} ({dates[0]} to {dates[-1]})", flush=True)

# S1: atr_crossed_above=1, rank prob_up_st_cross, top30
print("S1: atr_crossed_above=1 | prob_up_st_cross | top30", flush=True)
t0 = time.time()
equity = 1.0
rets = []
dts = []
skipped = 0

for i, d in enumerate(dates):
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL AND atr_crossed_above = 1
        ORDER BY prob_up_st_cross DESC LIMIT 30
    """, (d,)).fetchall()
    if len(rows) >= 5:
        arr = np.array([r[0] for r in rows])
        r_dec = np.mean(arr) / 100.0
        equity *= (1 + r_dec)
        rets.append(r_dec)
        dts.append(d)
    else:
        skipped += 1
    if (i+1) % 300 == 0:
        elapsed = time.time()-t0
        eta = elapsed/(i+1)*(len(dates)-i-1)
        print(f"  {i+1}/{len(dates)} ({elapsed:.0f}s, ETA {eta:.0f}s) eq=${equity:.2f} skips={skipped}", flush=True)

arr = np.array(rets)
print(f"\nDone in {time.time()-t0:.0f}s", flush=True)
print(f"Days: {len(arr)}  Skipped: {skipped}", flush=True)
print(f"$1 -> ${equity:.2f}  Total: {(equity-1)*100:.1f}%", flush=True)
print(f"Avg Daily: {np.mean(arr)*100:.3f}%  Median: {np.median(arr)*100:.3f}%  Std: {np.std(arr)*100:.3f}%", flush=True)
print(f"Best: {np.max(arr)*100:.2f}%  Worst: {np.min(arr)*100:.2f}%", flush=True)
print(f"WR: {np.mean(arr>0)*100:.1f}% ({np.sum(arr>0)}/{len(arr)})", flush=True)
sh = np.mean(arr)/np.std(arr)*np.sqrt(252) if np.std(arr)>0 else 0
print(f"Sharpe: {sh:.2f}", flush=True)
rm = np.maximum.accumulate(np.cumprod(1+arr))
dd = (np.cumprod(1+arr) - rm) / rm
print(f"MaxDD: {np.min(dd)*100:.1f}%", flush=True)

# Annual
print("\nANNUAL:", flush=True)
for y in range(int(dts[0][:4]), int(dts[-1][:4])+1):
    mask = [i2 for i2,d2 in enumerate(dts) if d2.startswith(str(y))]
    if len(mask)==0: continue
    yr = arr[mask]
    ann = np.prod(1+yr)-1
    print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)", flush=True)

# Monthly last 24
print("\nMONTHLY (last 24):", flush=True)
months = {}
for i2,d2 in enumerate(dts):
    k = d2[:7]
    months.setdefault(k,[]).append(arr[i2])
for k, v in list(months.items())[-24:]:
    mon = np.prod(1+np.array(v))-1
    print(f"  {k}: {mon*100:>+7.1f}%  ({len(v)}d)", flush=True)

# Rolling 20d
print("\nROLLING 20D (last 12):", flush=True)
for i2 in range(max(0,len(arr)-12*20), len(arr)-19, 20):
    chunk = arr[i2:i2+20]
    r20 = np.prod(1+chunk)-1
    print(f"  {dts[i2+19]}: {r20*100:>+7.1f}%", flush=True)

conn.close()
print("\nDONE", flush=True)
