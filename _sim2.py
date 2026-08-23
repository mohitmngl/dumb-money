"""Quick BTST simulation - processes in chunks to avoid memory issues"""
import numpy as np, pandas as pd, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("Loading data...", flush=True)
df = pd.read_parquet('strategy_results/US_stock_cache.parquet', columns=['date','atr_crossed_above','prob_up_st_cross','ret_1d'])
df['date'] = pd.to_datetime(df['date'])
print(f"Loaded {len(df)} rows", flush=True)

dates = sorted(df['date'].unique())
print(f"Dates: {len(dates)} ({dates[0]} to {dates[-1]})", flush=True)

equity = 1.0
rets = []
dts = []

for d in dates:
    day = df[df['date']==d]
    if len(day) < 30: continue
    filtered = day[day['atr_crossed_above']==1]
    if len(filtered) < 5: continue
    top = filtered.nlargest(30, 'prob_up_st_cross')
    r = top['ret_1d'].mean()
    if np.isfinite(r):
        equity *= (1+r)
        rets.append(r)
        dts.append(d)

arr = np.array(rets)
print(f"\nTrading days: {len(arr)}", flush=True)
print(f"Period: {dts[0].date()} to {dts[-1].date()}")
print(f"$1.00 -> ${equity:.2f}")
print(f"Total Return: {(equity-1)*100:.1f}%")

print(f"\n=== DAILY ===")
print(f"Avg: {np.mean(arr)*100:.3f}%  Median: {np.median(arr)*100:.3f}%  Std: {np.std(arr)*100:.3f}%")
print(f"Best: {np.max(arr)*100:.2f}%  Worst: {np.min(arr)*100:.2f}%")
print(f"Winners: {np.sum(arr>0)}/{len(arr)} ({np.mean(arr>0)*100:.1f}%)")
print(f"Sharpe: {np.mean(arr)/np.std(arr)*np.sqrt(252):.2f}")
rm = np.maximum.accumulate(np.cumprod(1+arr))
dd = (np.cumprod(1+arr) - rm) / rm
print(f"MaxDD: {np.min(dd)*100:.1f}%")

print(f"\n=== ANNUAL ===")
eqs = np.cumprod(1+arr)
for y in range(dts[0].year, dts[-1].year+1):
    mask = [i for i,d in enumerate(dts) if d.year==y]
    if len(mask)==0: continue
    yr = arr[mask]
    ann = np.prod(1+yr)-1
    print(f"  {y}: {ann*100:>+8.1f}%  ({len(yr):4d}d, avg {np.mean(yr)*100:.2f}%/d, WR {np.mean(yr>0)*100:.0f}%)")

print(f"\n=== MONTHLY (last 24) ===")
months = {}
for i,d in enumerate(dts):
    k = d.strftime('%Y-%m')
    months.setdefault(k,[]).append(arr[i])
items = list(months.items())
for k, v in items[-24:]:
    mon = np.prod(1+np.array(v))-1
    print(f"  {k}: {mon*100:>+7.1f}%  ({len(v)}d)")

print(f"\n=== ROLLING 20D (last 12) ===")
for i in range(max(0,len(arr)-12*20), len(arr)-20+1, 20):
    chunk = arr[i:i+20]
    r20 = np.prod(1+chunk)-1
    print(f"  {dts[i+19].date()}: {r20*100:>+7.1f}%")

print(f"\n=== YTD 2026 ===")
ytd = np.array([r for r,d in zip(arr,dts) if d.year==2026])
if len(ytd)>0:
    print(f"  {len(ytd)}d: {(np.prod(1+ytd)-1)*100:.1f}%  WR={np.mean(ytd>0)*100:.0f}%  Avg={np.mean(ytd)*100:.3f}%/d")

print("\nDONE")
