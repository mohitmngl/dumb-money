"""Test BTST strategy on US basket strings - full simulation"""
import numpy as np, pandas as pd, sys, io, os, time, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_DIR = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt'
db_path = os.path.join(DB_DIR, 'screener.db')
conn = sqlite3.connect(db_path)

# Get data info
info = pd.read_sql("""
    SELECT MIN(date) as min_date, MAX(date) as max_date, 
           COUNT(DISTINCT date) as n_dates,
           COUNT(DISTINCT string_id) as n_strings,
           COUNT(*) as total_rows
    FROM historical_string_screener
""", conn)
print(f"Strings: {info['n_strings'].values[0]}, Dates: {info['n_dates'].values[0]}, Rows: {info['total_rows'].values[0]}")
print(f"Range: {info['min_date'].values[0]} to {info['max_date'].values[0]}")

# Check what columns we have for strategy
# We need: atr_crossed_above, prob_up_st_cross, next_day_return
# next_day_return is the forward return (buy next day at open, sell at close)
print("\nLoading strategy columns...", flush=True)
t0 = time.time()
df = pd.read_sql("""
    SELECT string_id, date, next_day_return,
           atr_crossed_above, prob_up_st_cross, atr_signal,
           weighted_alpha, streak, atrp, atr_value, atr_streak,
           accel_a, accel_base, accel_signal, accel_crossed_up, accel_crossed_down,
           prob_up_1d, prob_up_5d, confluence,
           ai_overall_score, ai_tech_score, ai_momentum_score,
           ai_volume_score, ai_events_score, ai_volume_profile_score,
           ai_trendline_score, ai_sentiment_score,
           price, change_pct, volume
    FROM historical_string_screener
    WHERE next_day_return IS NOT NULL
""", conn)
conn.close()
print(f"Loaded {len(df)} rows in {time.time()-t0:.0f}s", flush=True)

df['date'] = pd.to_datetime(df['date'])
dates = sorted(df['date'].unique())
print(f"Dates: {len(dates)} ({dates[0].date()} to {dates[-1].date()})")
print(f"Strings per date: ~{len(df)//len(dates):.0f}")

# Strategy 1: atr_crossed_above=1, rank by prob_up_st_cross, top30
print("\n" + "="*100)
print("STRATEGY 1: atr_crossed_above=1 | rank=prob_up_st_cross | top30")
print("="*100)

equity = 1.0
rets = []
dts = []

for d in dates:
    day = df[df['date']==d]
    if len(day) < 30: continue
    filtered = day[day['atr_crossed_above']==1]
    if len(filtered) < 5: continue
    top = filtered.nlargest(30, 'prob_up_st_cross')
    r = top['next_day_return'].mean()
    if np.isfinite(r):
        r_dec = r / 100 if abs(r) > 1 else r  # handle percentage vs decimal
        equity *= (1 + r_dec)
        rets.append(r_dec)
        dts.append(d)

arr = np.array(rets)
print(f"Trading days: {len(arr)}")
if len(arr) > 0:
    print(f"Period: {dts[0].date()} to {dts[-1].date()}")
    print(f"$1 -> ${equity:.2f}")
    print(f"Total: {(equity-1)*100:.1f}%")
    print(f"Avg Daily: {np.mean(arr)*100:.3f}%  Median: {np.median(arr)*100:.3f}%  Std: {np.std(arr)*100:.3f}%")
    print(f"Best: {np.max(arr)*100:.2f}%  Worst: {np.min(arr)*100:.2f}%")
    print(f"WR: {np.mean(arr>0)*100:.1f}% ({np.sum(arr>0)}/{len(arr)})")
    print(f"Sharpe: {np.mean(arr)/np.std(arr)*np.sqrt(252):.2f}")
    rm = np.maximum.accumulate(np.cumprod(1+arr))
    dd = (np.cumprod(1+arr) - rm) / rm
    print(f"MaxDD: {np.min(dd)*100:.1f}%")
    
    # Annual
    print("\nANNUAL:")
    for y in range(dts[0].year, dts[-1].year+1):
        mask = [i for i,d2 in enumerate(dts) if d2.year==y]
        if len(mask)==0: continue
        yr = arr[mask]
        ann = np.prod(1+yr)-1
        print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")
    
    # Monthly last 24
    print("\nMONTHLY (last 24):")
    months = {}
    for i,d2 in enumerate(dts):
        k = d2.strftime('%Y-%m')
        months.setdefault(k,[]).append(arr[i])
    for k, v in list(months.items())[-24:]:
        mon = np.prod(1+np.array(v))-1
        print(f"  {k}: {mon*100:>+7.1f}%  ({len(v)}d)")
else:
    print("No valid trades found")

# Strategy 2: no filter, rank by weighted_alpha, top15
print("\n" + "="*100)
print("STRATEGY 2: No filter | rank=weighted_alpha | top15")
print("="*100)

equity2 = 1.0
rets2 = []
dts2 = []

for d in dates:
    day = df[df['date']==d]
    if len(day) < 15: continue
    top = day.nlargest(15, 'weighted_alpha')
    r = top['next_day_return'].mean()
    if np.isfinite(r):
        r_dec = r / 100 if abs(r) > 1 else r
        equity2 *= (1 + r_dec)
        rets2.append(r_dec)
        dts2.append(d)

arr2 = np.array(rets2)
print(f"Trading days: {len(arr2)}")
if len(arr2) > 0:
    print(f"Period: {dts2[0].date()} to {dts2[-1].date()}")
    print(f"$1 -> ${equity2:.2f}")
    print(f"Total: {(equity2-1)*100:.1f}%")
    print(f"Avg Daily: {np.mean(arr2)*100:.3f}%  Median: {np.median(arr2)*100:.3f}%  Std: {np.std(arr2)*100:.3f}%")
    print(f"WR: {np.mean(arr2>0)*100:.1f}%")
    print(f"Sharpe: {np.mean(arr2)/np.std(arr2)*np.sqrt(252):.2f}")
    rm2 = np.maximum.accumulate(np.cumprod(1+arr2))
    dd2 = (np.cumprod(1+arr2) - rm2) / rm2
    print(f"MaxDD: {np.min(dd2)*100:.1f}%")
    print("\nANNUAL:")
    for y in range(dts2[0].year, dts2[-1].year+1):
        mask = [i for i,d2 in enumerate(dts2) if d2.year==y]
        if len(mask)==0: continue
        yr = arr2[mask]
        ann = np.prod(1+yr)-1
        print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")

# Strategy 3: No filter, rank by streak, top10
print("\n" + "="*100)
print("STRATEGY 3: No filter | rank=streak | top10")
print("="*100)

equity3 = 1.0
rets3 = []
dts3 = []

for d in dates:
    day = df[df['date']==d]
    if len(day) < 10: continue
    top = day.nlargest(10, 'streak')
    r = top['next_day_return'].mean()
    if np.isfinite(r):
        r_dec = r / 100 if abs(r) > 1 else r
        equity3 *= (1 + r_dec)
        rets3.append(r_dec)
        dts3.append(d)

arr3 = np.array(rets3)
print(f"Trading days: {len(arr3)}")
if len(arr3) > 0:
    print(f"Period: {dts3[0].date()} to {dts3[-1].date()}")
    print(f"$1 -> ${equity3:.2f}")
    print(f"Total: {(equity3-1)*100:.1f}%")
    print(f"Avg Daily: {np.mean(arr3)*100:.3f}%  Median: {np.median(arr3)*100:.3f}%  Std: {np.std(arr3)*100:.3f}%")
    print(f"WR: {np.mean(arr3>0)*100:.1f}%")
    print(f"Sharpe: {np.mean(arr3)/np.std(arr3)*np.sqrt(252):.2f}")
    rm3 = np.maximum.accumulate(np.cumprod(1+arr3))
    dd3 = (np.cumprod(1+arr3) - rm3) / rm3
    print(f"MaxDD: {np.min(dd3)*100:.1f}%")
    print("\nANNUAL:")
    for y in range(dts3[0].year, dts3[-1].year+1):
        mask = [i for i,d2 in enumerate(dts3) if d2.year==y]
        if len(mask)==0: continue
        yr = arr3[mask]
        ann = np.prod(1+yr)-1
        print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")

# Strategy 4: atr_signal=1 + accel_signal=1, rank by prob_up_st_cross, top20
print("\n" + "="*100)
print("STRATEGY 4: atr_signal=1 & accel_signal=1 | rank=prob_up_st_cross | top20")
print("="*100)

equity4 = 1.0
rets4 = []
dts4 = []

for d in dates:
    day = df[df['date']==d]
    if len(day) < 20: continue
    filtered = day[(day['atr_signal']==1) & (day['accel_signal']==1)]
    if len(filtered) < 5: continue
    top = filtered.nlargest(20, 'prob_up_st_cross')
    r = top['next_day_return'].mean()
    if np.isfinite(r):
        r_dec = r / 100 if abs(r) > 1 else r
        equity4 *= (1 + r_dec)
        rets4.append(r_dec)
        dts4.append(d)

arr4 = np.array(rets4)
print(f"Trading days: {len(arr4)}")
if len(arr4) > 0:
    print(f"Period: {dts4[0].date()} to {dts4[-1].date()}")
    print(f"$1 -> ${equity4:.2f}")
    print(f"Total: {(equity4-1)*100:.1f}%")
    print(f"Avg Daily: {np.mean(arr4)*100:.3f}%  Median: {np.median(arr4)*100:.3f}%  Std: {np.std(arr4)*100:.3f}%")
    print(f"WR: {np.mean(arr4>0)*100:.1f}%")
    print(f"Sharpe: {np.mean(arr4)/np.std(arr4)*np.sqrt(252):.2f}")
    rm4 = np.maximum.accumulate(np.cumprod(1+arr4))
    dd4 = (np.cumprod(1+arr4) - rm4) / rm4
    print(f"MaxDD: {np.min(dd4)*100:.1f}%")
    print("\nANNUAL:")
    for y in range(dts4[0].year, dts4[-1].year+1):
        mask = [i for i,d2 in enumerate(dts4) if d2.year==y]
        if len(mask)==0: continue
        yr = arr4[mask]
        ann = np.prod(1+yr)-1
        print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")
    # Monthly last 12
    print("\nMONTHLY (last 12):")
    months4 = {}
    for i,d2 in enumerate(dts4):
        k = d2.strftime('%Y-%m')
        months4.setdefault(k,[]).append(arr4[i])
    for k, v in list(months4.items())[-12:]:
        mon = np.prod(1+np.array(v))-1
        print(f"  {k}: {mon*100:>+7.1f}%  ({len(v)}d)")

print("\nDONE")
