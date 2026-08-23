"""Fast BTST on US strings - recent dates only (2024+), per-date with PRAGMAs"""
import numpy as np, sys, io, time, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

db_path = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db'
conn = sqlite3.connect(db_path, timeout=60)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=120000')
conn.execute('PRAGMA cache_size=-64000')  # 64MB cache

# Get dates from 2024+
print("Getting dates from 2024+...", flush=True)
dates = [r[0] for r in conn.execute(
    "SELECT DISTINCT date FROM historical_string_screener WHERE date >= '2024-01-01' AND next_day_return IS NOT NULL ORDER BY date"
).fetchall()]
print(f"Dates: {len(dates)} ({dates[0]} to {dates[-1]})", flush=True)

# S1: atr_crossed_above=1, rank prob_up_st_cross, top30
print("\nS1: atr_crossed_above=1 | prob_up_st_cross | top30", flush=True)
t0 = time.time()
equity = 1.0
rets = []
dts = []
for i, d in enumerate(dates):
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL AND atr_crossed_above = 1
        ORDER BY prob_up_st_cross DESC LIMIT 30
    """, (d,)).fetchall()
    if len(rows) >= 5:
        r_dec = np.mean([r[0] for r in rows]) / 100.0
        equity *= (1 + r_dec)
        rets.append(r_dec)
        dts.append(d)
    if (i+1) % 200 == 0:
        print(f"  {i+1}/{len(dates)} ({time.time()-t0:.0f}s) eq=${equity:.2f}", flush=True)

arr = np.array(rets)
print(f"\nDone in {time.time()-t0:.0f}s", flush=True)
print(f"Days: {len(arr)}")
print(f"$1 -> ${equity:.2f}  Total: {(equity-1)*100:.1f}%")
print(f"Avg Daily: {np.mean(arr)*100:.3f}%  Std: {np.std(arr)*100:.3f}%")
print(f"WR: {np.mean(arr>0)*100:.1f}% ({np.sum(arr>0)}/{len(arr)})")
sh = np.mean(arr)/np.std(arr)*np.sqrt(252) if np.std(arr)>0 else 0
print(f"Sharpe: {sh:.2f}")
rm = np.maximum.accumulate(np.cumprod(1+arr))
dd = (np.cumprod(1+arr) - rm) / rm
print(f"MaxDD: {np.min(dd)*100:.1f}%")
# Annual
for y in range(2024, 2027):
    mask = [i for i,d2 in enumerate(dts) if d2.startswith(str(y))]
    if len(mask)==0: continue
    yr = arr[mask]
    ann = np.prod(1+yr)-1
    print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr)}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")
# Monthly last 12
months = {}
for i,d2 in enumerate(dts):
    months.setdefault(d2[:7],[]).append(arr[i])
print("MONTHLY (last 12):")
for k, v in list(months.items())[-12:]:
    mon = np.prod(1+np.array(v))-1
    print(f"  {k}: {mon*100:>+7.1f}%  ({len(v)}d)")

# S2: No filter, weighted_alpha top15
print("\n\nS2: No filter | weighted_alpha | top15", flush=True)
t0 = time.time()
equity2 = 1.0; rets2 = []; dts2 = []
for d in dates:
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL
        ORDER BY weighted_alpha DESC LIMIT 15
    """, (d,)).fetchall()
    if len(rows) >= 5:
        r_dec = np.mean([r[0] for r in rows]) / 100.0
        equity2 *= (1 + r_dec)
        rets2.append(r_dec)
        dts2.append(d)

arr2 = np.array(rets2)
print(f"Done in {time.time()-t0:.0f}s")
print(f"Days: {len(arr2)}  $1 -> ${equity2:.2f}  Total: {(equity2-1)*100:.1f}%")
print(f"Avg Daily: {np.mean(arr2)*100:.3f}%  Std: {np.std(arr2)*100:.3f}%  WR: {np.mean(arr2>0)*100:.1f}%")
sh2 = np.mean(arr2)/np.std(arr2)*np.sqrt(252) if np.std(arr2)>0 else 0
print(f"Sharpe: {sh2:.2f}")
rm2 = np.maximum.accumulate(np.cumprod(1+arr2))
dd2 = (np.cumprod(1+arr2) - rm2) / rm2
print(f"MaxDD: {np.min(dd2)*100:.1f}%")
for y in range(2024, 2027):
    mask = [i for i,d2 in enumerate(dts2) if d2.startswith(str(y))]
    if len(mask)==0: continue
    yr = arr2[mask]
    ann = np.prod(1+yr)-1
    print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr)}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")

# S3: No filter, streak top10
print("\n\nS3: No filter | streak | top10", flush=True)
t0 = time.time()
equity3 = 1.0; rets3 = []; dts3 = []
for d in dates:
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL
        ORDER BY streak DESC LIMIT 10
    """, (d,)).fetchall()
    if len(rows) >= 5:
        r_dec = np.mean([r[0] for r in rows]) / 100.0
        equity3 *= (1 + r_dec)
        rets3.append(r_dec)
        dts3.append(d)

arr3 = np.array(rets3)
print(f"Done in {time.time()-t0:.0f}s")
print(f"Days: {len(arr3)}  $1 -> ${equity3:.2f}  Total: {(equity3-1)*100:.1f}%")
print(f"Avg Daily: {np.mean(arr3)*100:.3f}%  Std: {np.std(arr3)*100:.3f}%  WR: {np.mean(arr3>0)*100:.1f}%")
sh3 = np.mean(arr3)/np.std(arr3)*np.sqrt(252) if np.std(arr3)>0 else 0
print(f"Sharpe: {sh3:.2f}")
rm3 = np.maximum.accumulate(np.cumprod(1+arr3))
dd3 = (np.cumprod(1+arr3) - rm3) / rm3
print(f"MaxDD: {np.min(dd3)*100:.1f}%")
for y in range(2024, 2027):
    mask = [i for i,d2 in enumerate(dts3) if d2.startswith(str(y))]
    if len(mask)==0: continue
    yr = arr3[mask]
    ann = np.prod(1+yr)-1
    print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr)}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")

# S4: atr_signal & accel_signal + prob_up_st_cross top20
print("\n\nS4: atr_signal & accel_signal | prob_up_st_cross | top20", flush=True)
t0 = time.time()
equity4 = 1.0; rets4 = []; dts4 = []
for d in dates:
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL AND atr_signal = 1 AND accel_signal = 1
        ORDER BY prob_up_st_cross DESC LIMIT 20
    """, (d,)).fetchall()
    if len(rows) >= 5:
        r_dec = np.mean([r[0] for r in rows]) / 100.0
        equity4 *= (1 + r_dec)
        rets4.append(r_dec)
        dts4.append(d)

arr4 = np.array(rets4)
print(f"Done in {time.time()-t0:.0f}s")
print(f"Days: {len(arr4)}  $1 -> ${equity4:.2f}  Total: {(equity4-1)*100:.1f}%")
if len(arr4) > 0:
    print(f"Avg Daily: {np.mean(arr4)*100:.3f}%  Std: {np.std(arr4)*100:.3f}%  WR: {np.mean(arr4>0)*100:.1f}%")
    sh4 = np.mean(arr4)/np.std(arr4)*np.sqrt(252) if np.std(arr4)>0 else 0
    print(f"Sharpe: {sh4:.2f}")
    rm4 = np.maximum.accumulate(np.cumprod(1+arr4))
    dd4 = (np.cumprod(1+arr4) - rm4) / rm4
    print(f"MaxDD: {np.min(dd4)*100:.1f}%")
    for y in range(2024, 2027):
        mask = [i for i,d2 in enumerate(dts4) if d2.startswith(str(y))]
        if len(mask)==0: continue
        yr = arr4[mask]
        ann = np.prod(1+yr)-1
        print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr)}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")
    months4 = {}
    for i,d2 in enumerate(dts4):
        months4.setdefault(d2[:7],[]).append(arr4[i])
    print("MONTHLY (last 12):")
    for k, v in list(months4.items())[-12:]:
        mon = np.prod(1+np.array(v))-1
        print(f"  {k}: {mon*100:>+7.1f}%  ({len(v)}d)")

# S5: No filter, ai_volume_profile_score top15
print("\n\nS5: No filter | ai_volume_profile_score | top15", flush=True)
t0 = time.time()
equity5 = 1.0; rets5 = []; dts5 = []
for d in dates:
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL
        ORDER BY ai_volume_profile_score DESC LIMIT 15
    """, (d,)).fetchall()
    if len(rows) >= 5:
        r_dec = np.mean([r[0] for r in rows]) / 100.0
        equity5 *= (1 + r_dec)
        rets5.append(r_dec)
        dts5.append(d)

arr5 = np.array(rets5)
print(f"Done in {time.time()-t0:.0f}s")
print(f"Days: {len(arr5)}  $1 -> ${equity5:.2f}  Total: {(equity5-1)*100:.1f}%")
if len(arr5) > 0:
    print(f"Avg Daily: {np.mean(arr5)*100:.3f}%  Std: {np.std(arr5)*100:.3f}%  WR: {np.mean(arr5>0)*100:.1f}%")
    sh5 = np.mean(arr5)/np.std(arr5)*np.sqrt(252) if np.std(arr5)>0 else 0
    print(f"Sharpe: {sh5:.2f}")
    rm5 = np.maximum.accumulate(np.cumprod(1+arr5))
    dd5 = (np.cumprod(1+arr5) - rm5) / rm5
    print(f"MaxDD: {np.min(dd5)*100:.1f}%")
    for y in range(2024, 2027):
        mask = [i for i,d2 in enumerate(dts5) if d2.startswith(str(y))]
        if len(mask)==0: continue
        yr = arr5[mask]
        ann = np.prod(1+yr)-1
        print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr)}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")

conn.close()
print("\nALL DONE", flush=True)
