"""Find US BTST strategies with >2% avg daily return, least volatility, most linear"""
import json, os, sys, io
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'

with open(os.path.join(OUTPUT, 'US_all_strategies.json')) as f:
    data = json.load(f)

df = pd.DataFrame(data)
# Filter: BTST only, n>=200 days, avg daily return > 2%
btst = df[(df['hold']=='1d') & (df['n']>=200)].copy()

# avg daily return = cagr-derived daily or we can compute from tr and n
# avg daily return = (1 + tr)^(1/n) - 1
btst['avg_daily'] = (1 + btst['tr']) ** (1/btst['n']) - 1

# Filter for > 2% daily
good = btst[btst['avg_daily'] > 0.02].copy()
print(f"Strategies with >2% avg daily return (n>=200): {len(good)}")
print()

if len(good) == 0:
    # Try > 1.5%
    good = btst[btst['avg_daily'] > 0.015].copy()
    print(f"Trying >1.5%: {len(good)}")
if len(good) == 0:
    good = btst[btst['avg_daily'] > 0.01].copy()
    print(f"Trying >1%: {len(gad)}")

# Rank by: lowest volatility first, then highest R2
good_sorted = good.sort_values(['vol', 'rsq'], ascending=[True, False])

print(f"\n{'='*130}")
print(f"  US BTST STRATEGIES: >{0.02*100:.0f}% DAILY RETURN, RANKED BY LOWEST VOLATILITY")
print(f"{'='*130}")
print(f"  {'AvgDaily':>9} {'Sharpe':>7} {'CAGR':>8} {'MDD':>8} {'Vol':>7} {'WR':>6} {'PF':>6} {'R2':>6} {'Days':>5}  Strategy")
print(f"  {'-'*9} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*5}  {'-'*65}")

for _, r in good_sorted.head(30).iterrows():
    marker = " <<<" if r['rsq'] > 0.8 and r['vol'] < 1.0 else ""
    print(f"  {r['avg_daily']*100:>8.2f}% {r['sharpe']:>7.3f} {r['cagr']*100:>7.1f}% {r['mdd']*100:>7.1f}% {r['vol']*100:>6.1f}% {r['wr']*100:>5.1f}% {r['pf']:>6.2f} {r['rsq']:>6.3f} {r['n']:>5}  {r['strat'][:65]}{marker}")

# Also rank by R2 (most linear)
good_linear = good.sort_values(['rsq', 'vol'], ascending=[False, True])
print(f"\n{'='*130}")
print(f"  US BTST STRATEGIES: >2% DAILY, RANKED BY MOST LINEAR (R2)")
print(f"{'='*130}")
print(f"  {'AvgDaily':>9} {'Sharpe':>7} {'CAGR':>8} {'MDD':>8} {'Vol':>7} {'WR':>6} {'PF':>6} {'R2':>6} {'Days':>5}  Strategy")
print(f"  {'-'*9} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*5}  {'-'*65}")

for _, r in good_linear.head(30).iterrows():
    marker = " <<<" if r['rsq'] > 0.9 and r['vol'] < 1.0 else ""
    print(f"  {r['avg_daily']*100:>8.2f}% {r['sharpe']:>7.3f} {r['cagr']*100:>7.1f}% {r['mdd']*100:>7.1f}% {r['vol']*100:>6.1f}% {r['wr']*100:>5.1f}% {r['pf']:>6.2f} {r['rsq']:>6.3f} {r['n']:>5}  {r['strat'][:65]}{marker}")

# Composite score: balance daily return, volatility, R2
# Score = (avg_daily * rsq) / vol  (higher = better)
good['score'] = (good['avg_daily'] * good['rsq']) / (good['vol'] + 0.001)
good_composite = good.sort_values('score', ascending=False)
print(f"\n{'='*130}")
print(f"  US BTST STRATEGIES: COMPOSITE SCORE = (DailyReturn * R2) / Volatility")
print(f"{'='*130}")
print(f"  {'Score':>7} {'AvgDaily':>9} {'Sharpe':>7} {'CAGR':>8} {'MDD':>8} {'Vol':>7} {'WR':>6} {'PF':>6} {'R2':>6} {'Days':>5}  Strategy")
print(f"  {'-'*7} {'-'*9} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*5}  {'-'*65}")

for _, r in good_composite.head(30).iterrows():
    print(f"  {r['score']:>7.4f} {r['avg_daily']*100:>8.2f}% {r['sharpe']:>7.3f} {r['cagr']*100:>7.1f}% {r['mdd']*100:>7.1f}% {r['vol']*100:>6.1f}% {r['wr']*100:>5.1f}% {r['pf']:>6.2f} {r['rsq']:>6.3f} {r['n']:>5}  {r['strat'][:65]}")

# Now simulate the top strategy to show equity curve
print(f"\n{'='*130}")
print(f"  EQUITY CURVE SIMULATION - TOP STRATEGY")
print(f"{'='*130}")

# Load cache
cache = os.path.join(OUTPUT, 'US_stock_cache.parquet')
df_cache = pd.read_parquet(cache)
df_cache['date'] = pd.to_datetime(df_cache['date'])

# Pick the best composite strategy
best = good_composite.iloc[0]
rc = best['rc']; tn_str = best['tn']
tn = int(tn_str) if tn_str.isdigit() else int(tn_str.replace('p','').replace('t','')) if 'p' in str(tn_str) else 20

print(f"  Strategy: {best['strat']}")
print(f"  Rank Col: {rc}, Top-N: {tn}")
print(f"  AvgDaily: {best['avg_daily']*100:.2f}% Sharpe: {best['sharpe']:.3f} R2: {best['rsq']:.3f}")

# Simulate
dates = sorted(df_cache['date'].unique())
equity = 1.0
equity_curve = []
daily_rets = []

for d in dates:
    day = df_cache[df_cache['date']==d]
    if len(day) < tn: continue
    if rc not in day.columns: continue
    top = day.nlargest(tn, rc)
    if 'ret_1d' in top.columns and len(top) > 0:
        ret = top['ret_1d'].mean()
        if np.isfinite(ret):
            equity *= (1 + ret)
            daily_rets.append(ret)
            equity_curve.append({'date': d, 'equity': equity, 'ret': ret})

eq_df = pd.DataFrame(equity_curve)
daily_arr = np.array(daily_rets)

print(f"\n  Simulated: {len(eq_df)} trading days")
print(f"  Start: {eq_df['date'].iloc[0].date()}  End: {eq_df['date'].iloc[-1].date()}")
print(f"  Start Equity: $1.00  End Equity: ${eq_df['equity'].iloc[-1]:.2f}")
print(f"  Total Return: {(eq_df['equity'].iloc[-1]-1)*100:.1f}%")
print(f"  Avg Daily: {np.mean(daily_arr)*100:.3f}%")
print(f"  Median Daily: {np.median(daily_arr)*100:.3f}%")
print(f"  Best Day: {np.max(daily_arr)*100:.2f}%")
print(f"  Worst Day: {np.min(daily_arr)*100:.2f}%")
print(f"  Std Dev: {np.std(daily_arr)*100:.3f}%")
print(f"  Days >0: {np.sum(daily_arr>0)} ({np.mean(daily_arr>0)*100:.1f}%)")
print(f"  Days <0: {np.sum(daily_arr<0)} ({np.mean(daily_arr<0)*100:.1f}%)")
print(f"  Max Drawdown: {((eq_df['equity']/eq_df['equity'].cummax()-1).min())*100:.1f}%")

# Annual returns
eq_df['year'] = eq_df['date'].dt.year
annual = eq_df.groupby('year')['ret'].apply(lambda x: np.prod(1+x)-1)
print(f"\n  ANNUAL RETURNS:")
for y, v in annual.items():
    bar = '+' * min(int(abs(v)*20), 40) if v > 0 else '-' * min(int(abs(v)*20), 40)
    print(f"    {y}: {v*100:>+8.1f}%  {bar}")

# Monthly
eq_df['month'] = eq_df['date'].dt.to_period('M')
monthly = eq_df.groupby('month')['ret'].apply(lambda x: np.prod(1+x)-1)
print(f"\n  MONTHLY RETURNS (last 24):")
for m, v in list(monthly.items())[-24:]:
    bar = '+' * min(int(abs(v)*40), 30) if v > 0 else '-' * min(int(abs(v)*40), 30)
    print(f"    {m}: {v*100:>+7.1f}%  {bar}")

# Rolling 63-day (quarterly)
rm63 = eq_df.set_index('date')['ret'].rolling(63).apply(lambda x: np.prod(1+x)-1, raw=True).dropna()
print(f"\n  ROLLING QUARTERLY (63d):")
print(f"    Best:  {rm63.max()*100:.1f}%")
print(f"    Worst: {rm63.min()*100:.1f}%")
print(f"    Avg:   {rm63.mean()*100:.1f}%")
print(f"    Current: {rm63.iloc[-1]*100:.1f}%")

# Check if >2% daily is real
print(f"\n  >>> VERDICT: Avg daily return = {np.mean(daily_arr)*100:.3f}%")
if np.mean(daily_arr) >= 0.02:
    print(f"  >>> YES - exceeds 2% daily target")
else:
    print(f"  >>> NO - below 2% daily target")
    # Find threshold
    for thresh in [0.015, 0.01, 0.005]:
        above = good[good['avg_daily'] > thresh]
        if len(above) > 0:
            print(f"  >>> {len(above)} strategies with >{thresh*100:.1f}% daily")
