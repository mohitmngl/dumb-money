"""Simulate the best US BTST strategy - equity curve + periodic returns"""
import numpy as np, pandas as pd, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
cache = os.path.join(OUTPUT, 'US_stock_cache.parquet')
df = pd.read_parquet(cache)
df['date'] = pd.to_datetime(df['date'])

# Strategy: atr_crossed_above=1, rank by prob_up_st_cross, top 30
# Best balance of sample (1119 days), low vol (85.8%), high R2 (0.984)
print("Strategy: atr_crossed_above=1 | rank=prob_up_st_cross | top30")
print("Sample: 1119 days, Sharpe=9.852, R2=0.984")
print()

dates = sorted(df['date'].unique())
equity = 1.0
rows = []

for d in dates:
    day = df[df['date']==d]
    if len(day) < 30: continue
    if 'atr_crossed_above' not in day.columns or 'prob_up_st_cross' not in day.columns: continue
    
    filtered = day[day['atr_crossed_above']==1]
    if len(filtered) < 5: continue
    
    top = filtered.nlargest(30, 'prob_up_st_cross')
    if 'ret_1d' in top.columns and len(top) > 0:
        ret = top['ret_1d'].mean()
        if np.isfinite(ret):
            equity *= (1 + ret)
            rows.append({'date': d, 'equity': equity, 'ret': ret})

eq = pd.DataFrame(rows)
arr = eq['ret'].values

print(f"Period: {eq['date'].iloc[0].date()} to {eq['date'].iloc[-1].date()}")
print(f"Trading Days: {len(eq)}")
print(f"Start: $1.00 -> End: ${eq['equity'].iloc[-1]:.2f}")
print(f"Total Return: {(eq['equity'].iloc[-1]-1)*100:.1f}%")
print()

# Daily stats
print("=== DAILY STATS ===")
print(f"Avg Daily: {np.mean(arr)*100:.3f}%")
print(f"Median Daily: {np.median(arr)*100:.3f}%")
print(f"Std Dev: {np.std(arr)*100:.3f}%")
print(f"Best Day: {np.max(arr)*100:.2f}%")
print(f"Worst Day: {np.min(arr)*100:.2f}%")
print(f"Days >0: {np.sum(arr>0)} ({np.mean(arr>0)*100:.1f}%)")
print(f"Days <0: {np.sum(arr<0)} ({np.mean(arr<0)*100:.1f}%)")
print(f"Days =0: {np.sum(arr==0)}")
print(f"Sharpe: {np.mean(arr)/np.std(arr)*np.sqrt(252):.3f}")

# Max drawdown
rm = eq['equity'].cummax()
dd = (eq['equity'] - rm) / rm
print(f"Max Drawdown: {dd.min()*100:.1f}%")

# Annual
print("\n=== ANNUAL RETURNS ===")
eq['year'] = eq['date'].dt.year
for y, g in eq.groupby('year'):
    r = g['ret'].values
    ann = np.prod(1+r)-1
    days = len(r)
    avg_d = np.mean(r)*100
    wr = np.mean(r>0)*100
    best = np.max(r)*100
    worst = np.min(r)*100
    print(f"  {y}: {ann*100:>+8.1f}%  ({days:4d} days, avg {avg_d:.2f}%/d, WR {wr:.0f}%, best {best:.1f}%, worst {worst:.1f}%)")

# Monthly
print("\n=== MONTHLY RETURNS (last 24) ===")
eq['month'] = eq['date'].dt.to_period('M')
for m, g in eq.groupby('month'):
    r = g['ret'].values
    mon = np.prod(1+r)-1
    print(f"  {m}: {mon*100:>+7.1f}%  ({len(r)} days)")

# Rolling 20-day
print("\n=== ROLLING 20-DAY RETURNS (last 12) ===")
eq['roll20'] = eq['ret'].rolling(20).apply(lambda x: np.prod(1+x)-1, raw=True)
for _, r in eq.dropna(subset=['roll20']).tail(12).iterrows():
    print(f"  {r['date'].date()}: {r['roll20']*100:>+7.1f}%")

# Rolling 63-day
print("\n=== ROLLING QUARTERLY (63d) ===")
eq['roll63'] = eq['ret'].rolling(63).apply(lambda x: np.prod(1+x)-1, raw=True)
for _, r in eq.dropna(subset=['roll63']).tail(8).iterrows():
    print(f"  {r['date'].date()}: {r['roll63']*100:>+7.1f}%")

# Year-to-date 2026
ytd = eq[eq['date'].dt.year==2026]['ret'].values
if len(ytd) > 0:
    print(f"\n=== 2026 YTD ===")
    print(f"  Days: {len(ytd)}")
    print(f"  YTD Return: {(np.prod(1+ytd)-1)*100:.1f}%")
    print(f"  Avg Daily: {np.mean(ytd)*100:.3f}%")
    print(f"  WR: {np.mean(ytd>0)*100:.0f}%")

# Equity curve text visualization
print("\n=== EQUITY CURVE (monthly) ===")
monthly_eq = eq.groupby('month')['equity'].last()
first = monthly_eq.iloc[0]
for m, v in monthly_eq.items():
    chg = (v/first - 1) * 100
    bar_len = min(int(abs(chg)/5), 50)
    bar = "+" * bar_len if chg > 0 else "-" * bar_len
    print(f"  {m}: ${v:>8.2f} ({chg:>+7.1f}%) {bar}")
    first = v

print("\nDONE")
