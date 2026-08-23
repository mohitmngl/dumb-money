"""Fast BTST strings - create index first, then single-pass"""
import numpy as np, pandas as pd, sys, io, os, time, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

db_path = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db'
conn = sqlite3.connect(db_path)

# Check/create indexes
print("Checking indexes...", flush=True)
indexes = [r[1] for r in conn.execute("SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='historical_string_screener'").fetchall()]
print(f"  Existing: {indexes}", flush=True)

if 'idx_hss_date' not in indexes:
    print("  Creating idx_hss_date...", flush=True)
    conn.execute("CREATE INDEX idx_hss_date ON historical_string_screener(date)")
    conn.commit()

# Check sample - can we get one date quickly?
print("\nTesting single date query...", flush=True)
t0 = time.time()
sample = pd.read_sql("""
    SELECT string_id, next_day_return, atr_crossed_above, prob_up_st_cross,
           atr_signal, weighted_alpha, streak, atr_streak,
           accel_signal, ai_volume_profile_score
    FROM historical_string_screener
    WHERE date = '2026-01-15' AND next_day_return IS NOT NULL
    ORDER BY prob_up_st_cross DESC LIMIT 30
""", conn)
print(f"  Got {len(sample)} rows in {time.time()-t0:.2f}s", flush=True)

# Get date count
n_dates = conn.execute("SELECT COUNT(DISTINCT date) FROM historical_string_screener WHERE next_day_return IS NOT NULL").fetchone()[0]
print(f"  Total dates: {n_dates}", flush=True)

# Strategy: iterate dates, get top N each day
# S1: atr_crossed_above=1, rank prob_up_st_cross, top30
print(f"\n{'='*90}", flush=True)
print("  S1: atr_crossed_above=1 | prob_up_st_cross | top30", flush=True)
print(f"{'='*90}", flush=True)

t0 = time.time()
dates = [r[0] for r in conn.execute(
    "SELECT DISTINCT date FROM historical_string_screener WHERE next_day_return IS NOT NULL ORDER BY date"
).fetchall()]

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
        arr = np.array([r[0] for r in rows])
        r_dec = np.mean(arr) / 100.0
        equity *= (1 + r_dec)
        rets.append(r_dec)
        dts.append(d)
    if (i+1) % 200 == 0:
        print(f"  ... {i+1}/{len(dates)} dates, equity=${equity:.2f} ({time.time()-t0:.0f}s)", flush=True)

arr = np.array(rets)
print(f"\n  Done in {time.time()-t0:.0f}s", flush=True)
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
        mask = [i2 for i2,d2 in enumerate(dts) if d2.startswith(str(y))]
        if len(mask)==0: continue
        yr = arr[mask]
        ann = np.prod(1+yr)-1
        print(f"    {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)", flush=True)
    # Monthly last 12
    print("  MONTHLY (last 12):", flush=True)
    months = {}
    for i2,d2 in enumerate(dts):
        k = d2[:7]
        months.setdefault(k,[]).append(arr[i2])
    for k, v in list(months.items())[-12:]:
        mon = np.prod(1+np.array(v))-1
        print(f"    {k}: {mon*100:>+7.1f}%  ({len(v)}d)", flush=True)

# S2: No filter, weighted_alpha top15
print(f"\n{'='*90}", flush=True)
print("  S2: No filter | weighted_alpha | top15", flush=True)
print(f"{'='*90}", flush=True)

t0 = time.time()
equity2 = 1.0
rets2 = []
dts2 = []

for d in dates:
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL
        ORDER BY weighted_alpha DESC LIMIT 15
    """, (d,)).fetchall()
    if len(rows) >= 5:
        arr2 = np.array([r[0] for r in rows])
        r_dec = np.mean(arr2) / 100.0
        equity2 *= (1 + r_dec)
        rets2.append(r_dec)
        dts2.append(d)

arr2 = np.array(rets2)
print(f"  Done in {time.time()-t0:.0f}s", flush=True)
print(f"  Days: {len(arr2)}", flush=True)
if len(arr2) > 0:
    print(f"  $1 -> ${equity2:.2f}  Total: {(equity2-1)*100:.1f}%", flush=True)
    print(f"  Avg Daily: {np.mean(arr2)*100:.3f}%  Median: {np.median(arr2)*100:.3f}%  Std: {np.std(arr2)*100:.3f}%", flush=True)
    print(f"  WR: {np.mean(arr2>0)*100:.1f}%", flush=True)
    sh2 = np.mean(arr2)/np.std(arr2)*np.sqrt(252) if np.std(arr2)>0 else 0
    print(f"  Sharpe: {sh2:.2f}", flush=True)
    rm2 = np.maximum.accumulate(np.cumprod(1+arr2))
    dd2 = (np.cumprod(1+arr2) - rm2) / rm2
    print(f"  MaxDD: {np.min(dd2)*100:.1f}%", flush=True)
    print("  ANNUAL:", flush=True)
    for y in range(int(dts2[0][:4]), int(dts2[-1][:4])+1):
        mask = [i2 for i2,d2 in enumerate(dts2) if d2.startswith(str(y))]
        if len(mask)==0: continue
        yr = arr2[mask]
        ann = np.prod(1+yr)-1
        print(f"    {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)", flush=True)

# S3: No filter, streak top10
print(f"\n{'='*90}", flush=True)
print("  S3: No filter | streak | top10", flush=True)
print(f"{'='*90}", flush=True)

t0 = time.time()
equity3 = 1.0
rets3 = []
dts3 = []

for d in dates:
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL
        ORDER BY streak DESC LIMIT 10
    """, (d,)).fetchall()
    if len(rows) >= 5:
        arr3 = np.array([r[0] for r in rows])
        r_dec = np.mean(arr3) / 100.0
        equity3 *= (1 + r_dec)
        rets3.append(r_dec)
        dts3.append(d)

arr3 = np.array(rets3)
print(f"  Done in {time.time()-t0:.0f}s", flush=True)
print(f"  Days: {len(arr3)}", flush=True)
if len(arr3) > 0:
    print(f"  $1 -> ${equity3:.2f}  Total: {(equity3-1)*100:.1f}%", flush=True)
    print(f"  Avg Daily: {np.mean(arr3)*100:.3f}%  Median: {np.median(arr3)*100:.3f}%  Std: {np.std(arr3)*100:.3f}%", flush=True)
    print(f"  WR: {np.mean(arr3>0)*100:.1f}%", flush=True)
    sh3 = np.mean(arr3)/np.std(arr3)*np.sqrt(252) if np.std(arr3)>0 else 0
    print(f"  Sharpe: {sh3:.2f}", flush=True)
    rm3 = np.maximum.accumulate(np.cumprod(1+arr3))
    dd3 = (np.cumprod(1+arr3) - rm3) / rm3
    print(f"  MaxDD: {np.min(dd3)*100:.1f}%", flush=True)
    print("  ANNUAL:", flush=True)
    for y in range(int(dts3[0][:4]), int(dts3[-1][:4])+1):
        mask = [i2 for i2,d2 in enumerate(dts3) if d2.startswith(str(y))]
        if len(mask)==0: continue
        yr = arr3[mask]
        ann = np.prod(1+yr)-1
        print(f"    {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)", flush=True)

# S4: atr_signal & accel_signal, prob_up_st_cross top20
print(f"\n{'='*90}", flush=True)
print("  S4: atr_signal=1 & accel_signal=1 | prob_up_st_cross | top20", flush=True)
print(f"{'='*90}", flush=True)

t0 = time.time()
equity4 = 1.0
rets4 = []
dts4 = []

for d in dates:
    rows = conn.execute("""
        SELECT next_day_return FROM historical_string_screener
        WHERE date = ? AND next_day_return IS NOT NULL AND atr_signal = 1 AND accel_signal = 1
        ORDER BY prob_up_st_cross DESC LIMIT 20
    """, (d,)).fetchall()
    if len(rows) >= 5:
        arr4 = np.array([r[0] for r in rows])
        r_dec = np.mean(arr4) / 100.0
        equity4 *= (1 + r_dec)
        rets4.append(r_dec)
        dts4.append(d)

arr4 = np.array(rets4)
print(f"  Done in {time.time()-t0:.0f}s", flush=True)
print(f"  Days: {len(arr4)}", flush=True)
if len(arr4) > 0:
    print(f"  $1 -> ${equity4:.2f}  Total: {(equity4-1)*100:.1f}%", flush=True)
    print(f"  Avg Daily: {np.mean(arr4)*100:.3f}%  Median: {np.median(arr4)*100:.3f}%  Std: {np.std(arr4)*100:.3f}%", flush=True)
    print(f"  WR: {np.mean(arr4>0)*100:.1f}%", flush=True)
    sh4 = np.mean(arr4)/np.std(arr4)*np.sqrt(252) if np.std(arr4)>0 else 0
    print(f"  Sharpe: {sh4:.2f}", flush=True)
    rm4 = np.maximum.accumulate(np.cumprod(1+arr4))
    dd4 = (np.cumprod(1+arr4) - rm4) / rm4
    print(f"  MaxDD: {np.min(dd4)*100:.1f}%", flush=True)
    print("  ANNUAL:", flush=True)
    for y in range(int(dts4[0][:4]), int(dts4[-1][:4])+1):
        mask = [i2 for i2,d2 in enumerate(dts4) if d2.startswith(str(y))]
        if len(mask)==0: continue
        yr = arr4[mask]
        ann = np.prod(1+yr)-1
        print(f"    {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)", flush=True)
    print("  MONTHLY (last 12):", flush=True)
    months4 = {}
    for i2,d2 in enumerate(dts4):
        k = d2[:7]
        months4.setdefault(k,[]).append(arr4[i2])
    for k, v in list(months4.items())[-12:]:
        mon = np.prod(1+np.array(v))-1
        print(f"    {k}: {mon*100:>+7.1f}%  ({len(v)}d)", flush=True)

conn.close()
print("\nALL DONE", flush=True)
