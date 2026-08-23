"""
STRATEGY ANALYSIS - Full Deep Dive
"""
import json, os, sys, io
import numpy as np
import pandas as pd
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'

def load(market):
    with open(os.path.join(OUTPUT, f'{market}_all_strategies.json')) as f:
        return pd.DataFrame(json.load(f))

US = load('US'); IND = load('India')
print(f"Loaded: US={len(US)} strategies, India={len(IND)} strategies")

MIN_DAYS = 100
US_F = US[US['n'] >= MIN_DAYS].copy()
IND_F = IND[IND['n'] >= MIN_DAYS].copy()
print(f"After filter n>={MIN_DAYS}: US={len(US_F)}, India={len(IND_F)}")

HOLDS = {'1d': 'BTST', '5d': '5-DAY', '1mo': '1-MONTH'}
CATS = [
    ('sharpe',  False, 'SHARPE'),
    ('cagr',    False, 'CAGR'),
    ('mdd',     True,  'DD'),
    ('vol',     True,  'VOL'),
    ('rsq',     False, 'LINEAR'),
    ('wr',      False, 'WR'),
    ('pf',      False, 'PF'),
    ('sortino', False, 'SORTINO'),
    ('calmar',  False, 'CALMAR'),
    ('omega',   False, 'OMEGA'),
]

def top_strategies(df, hold, metric, asc, n=10):
    hdf = df[df['hold'] == hold].sort_values(metric, ascending=asc).head(n)
    return hdf

sep = "=" * 120
dash = "-" * 120

print("")
print(sep)
print("  TOP STRATEGIES PER CATEGORY -- US MARKET")
print(sep)
for h, hl in HOLDS.items():
    hdf = US_F[US_F['hold']==h]
    print("")
    print(dash)
    print(f"  {hl} ({h}) -- {len(hdf)} strategies with n>={MIN_DAYS}")
    print(dash)
    print(f"  {'Sharpe':>7} {'CAGR':>8} {'MDD':>8} {'Vol':>7} {'WinR':>6} {'PF':>6} {'R2':>6} {'Days':>5}  Strategy")
    print(f"  {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*5}  {'-'*60}")
    for ci, (col, asc, cat) in enumerate(CATS):
        rows = top_strategies(hdf, h, col, asc, 3)
        for ri, (_, r) in enumerate(rows.iterrows()):
            tag = f"  [{cat}]" if ri == 0 else ""
            print(f"  {r['sharpe']:>7.3f} {r['cagr']*100:>7.1f}% {r['mdd']*100:>7.1f}% {r['vol']*100:>6.1f}% {r['wr']*100:>5.1f}% {r['pf']:>6.2f} {r['rsq']:>6.3f} {r['n']:>5}  {r['strat'][:70]}{tag}")

print("")
print(sep)
print("  TOP STRATEGIES PER CATEGORY -- INDIA MARKET")
print(sep)
for h, hl in HOLDS.items():
    hdf = IND_F[IND_F['hold']==h]
    print("")
    print(dash)
    print(f"  {hl} ({h}) -- {len(hdf)} strategies with n>={MIN_DAYS}")
    print(dash)
    print(f"  {'Sharpe':>7} {'CAGR':>8} {'MDD':>8} {'Vol':>7} {'WinR':>6} {'PF':>6} {'R2':>6} {'Days':>5}  Strategy")
    print(f"  {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*5}  {'-'*60}")
    for ci, (col, asc, cat) in enumerate(CATS):
        rows = top_strategies(hdf, h, col, asc, 3)
        for ri, (_, r) in enumerate(rows.iterrows()):
            tag = f"  [{cat}]" if ri == 0 else ""
            print(f"  {r['sharpe']:>7.3f} {r['cagr']*100:>7.1f}% {r['mdd']*100:>7.1f}% {r['vol']*100:>6.1f}% {r['wr']*100:>5.1f}% {r['pf']:>6.2f} {r['rsq']:>6.3f} {r['n']:>5}  {r['strat'][:70]}{tag}")

print("")
print(sep)
print("  COLUMN IMPORTANCE -- Which Rank Columns Actually Matter?")
print(sep)

for market, mdf, label in [(US_F, US_F, 'US'), (IND_F, IND_F, 'India')]:
    print("")
    print(f"  {label} -- Avg metrics by rank column (all holds, no filter):")
    nofilt = mdf[mdf['filt']=='none']
    if len(nofilt) == 0: continue
    grouped = nofilt.groupby('rc').agg({
        'sharpe': 'mean', 'cagr': 'mean', 'mdd': 'mean', 'vol': 'mean',
        'wr': 'mean', 'pf': 'mean', 'rsq': 'mean', 'n': 'mean',
        'strat': 'count'
    }).rename(columns={'strat':'strategies'}).sort_values('sharpe', ascending=False)
    print(f"  {'Column':<28} {'Avg Sharpe':>10} {'Avg CAGR':>9} {'Avg MDD':>9} {'Avg Vol':>8} {'Avg WR':>7} {'Avg PF':>7} {'Avg R2':>7} {'#':>4}")
    print(f"  {'-'*28} {'-'*10} {'-'*9} {'-'*9} {'-'*8} {'-'*7} {'-'*7} {'-'*7} {'-'*4}")
    for rc, row in grouped.iterrows():
        print(f"  {rc:<28} {row['sharpe']:>10.3f} {row['cagr']*100:>8.1f}% {row['mdd']*100:>8.1f}% {row['vol']*100:>7.1f}% {row['wr']*100:>6.1f}% {row['pf']:>7.2f} {row['rsq']:>7.3f} {int(row['strategies']):>4}")

print("")
print(sep)
print("  BINARY FILTER IMPACT -- Do Filters Help?")
print(sep)

for market, mdf, label in [(US_F, US_F, 'US'), (IND_F, IND_F, 'India')]:
    print("")
    print(f"  {label}:")
    for h, hl in HOLDS.items():
        hdf = mdf[mdf['hold']==h]
        nofilt = hdf[hdf['filt']=='none']
        filtered = hdf[hdf['filt']!='none']
        if len(nofilt) == 0 or len(filtered) == 0: continue
        print(f"    {hl}:")
        print(f"    {'Status':<15} {'Count':>6} {'Avg Sharpe':>10} {'Avg CAGR':>9} {'Avg MDD':>9} {'Avg WR':>7} {'Avg PF':>7} {'Avg n':>7}")
        print(f"    {'-'*15} {'-'*6} {'-'*10} {'-'*9} {'-'*9} {'-'*7} {'-'*7} {'-'*7}")
        for lbl, sub in [('No filter', nofilt), ('With filter', filtered)]:
            print(f"    {lbl:<15} {len(sub):>6} {sub['sharpe'].mean():>10.3f} {sub['cagr'].mean()*100:>8.1f}% {sub['mdd'].mean()*100:>8.1f}% {sub['wr'].mean()*100:>6.1f}% {sub['pf'].mean():>7.2f} {sub['n'].mean():>7.0f}")

print("")
print(sep)
print("  TOP-N THRESHOLD SENSITIVITY -- Does Concentration Help?")
print(sep)

for market, mdf, label in [(US_F, US_F, 'US'), (IND_F, IND_F, 'India')]:
    print("")
    print(f"  {label} (no-filter only):")
    nofilt = mdf[mdf['filt']=='none']
    for h, hl in HOLDS.items():
        hdf = nofilt[nofilt['hold']==h]
        if len(hdf)==0: continue
        grouped = hdf.groupby('tn').agg({
            'sharpe': 'mean', 'cagr': 'mean', 'mdd': 'mean', 'vol': 'mean',
            'wr': 'mean', 'n': 'mean', 'strat': 'count'
        }).rename(columns={'strat':'count'})
        print(f"    {hl}:")
        print(f"    {'TopN':<8} {'#':>6} {'Avg Sharpe':>10} {'Avg CAGR':>9} {'Avg MDD':>9} {'Avg Vol':>8} {'Avg WR':>7} {'Avg Days':>8}")
        for tn, row in grouped.iterrows():
            print(f"    Top{str(tn):<5} {int(row['count']):>6} {row['sharpe']:>10.3f} {row['cagr']*100:>8.1f}% {row['mdd']*100:>8.1f}% {row['vol']*100:>7.1f}% {row['wr']*100:>6.1f}% {row['n']:>8.0f}")

print("")
print(sep)
print("  US vs INDIA -- Head-to-Head (same rank col, same hold, no filter)")
print(sep)

us_nf = US_F[US_F['filt']=='none'].copy()
ind_nf = IND_F[IND_F['filt']=='none'].copy()

merged = us_nf.merge(ind_nf, on=['rc','tn','hold'], suffixes=('_us','_ind'))
print(f"  Matched strategies: {len(merged)}")
print("")
print(f"  {'Rank Col':<28} {'TopN':>4} {'Hold':>4} {'US Sh':>7} {'IND Sh':>7} {'Winner':>7} {'US CAGR':>8} {'IND CAGR':>9} {'US MDD':>8} {'IND MDD':>8}")
print(f"  {'-'*28} {'-'*4} {'-'*4} {'-'*7} {'-'*7} {'-'*7} {'-'*8} {'-'*9} {'-'*8} {'-'*8}")
for _, r in merged.sort_values('sharpe_us', ascending=False).iterrows():
    winner = 'US' if r['sharpe_us'] > r['sharpe_ind'] else 'India'
    print(f"  {r['rc']:<28} {str(r['tn']):>4} {r['hold']:>4} {r['sharpe_us']:>7.3f} {r['sharpe_ind']:>7.3f} {winner:>7} {r['cagr_us']*100:>7.1f}% {r['cagr_ind']*100:>8.1f}% {r['mdd_us']*100:>7.1f}% {r['mdd_ind']*100:>7.1f}%")

print("")
print(sep)
print("  PERIODIC RETURNS FOR TOP 5 STRATEGIES (from cached bar data)")
print(sep)

for market in ['US', 'India']:
    cache = os.path.join(OUTPUT, f'{market}_stock_cache.parquet')
    if not os.path.exists(cache): continue
    df = pd.read_parquet(cache)
    df['date'] = pd.to_datetime(df['date'])
    df['year'] = df['date'].dt.year

    strats_df = US_F if market=='US' else IND_F
    for h, hl in [('1d','BTST'),('5d','5-DAY'),('1mo','1-MONTH')]:
        top3 = strats_df[strats_df['hold']==h].sort_values('sharpe', ascending=False).head(3)
        for si, (_, sr) in enumerate(top3.iterrows()):
            rc = sr['rc']; tn = int(sr['tn'])
            print("")
            print(f"  {market} #{si+1} {hl}: {sr['strat'][:75]}")
            print(f"    Sharpe={sr['sharpe']:.3f} CAGR={sr['cagr']*100:.1f}% MDD={sr['mdd']*100:.1f}% WR={sr['wr']*100:.1f}% PF={sr['pf']:.2f}")

            ret_key = {'1d':'ret_1d','5d':'ret_5d','1mo':'ret_1mo'}[h]
            if ret_key not in df.columns: continue
            rets = df.groupby('date').apply(
                lambda g: g.nlargest(tn, rc)[ret_key].mean() if rc in g.columns and len(g) >= tn else np.nan
            ).dropna()
            if len(rets) == 0: continue

            rdf = pd.DataFrame({'date': rets.index, 'ret': rets.values})
            rdf['year'] = rdf['date'].dt.year

            # Annual
            annual = rdf.groupby('year')['ret'].apply(lambda x: np.prod(1+x)-1)
            print(f"    ANNUAL:")
            for y, v in annual.items():
                bar = "+" * min(int(abs(v)*30), 30) if v > 0 else "-" * min(int(abs(v)*30), 30)
                print(f"      {y}: {v*100:>+8.1f}%  {bar}")

            # Monthly (last 12)
            rdf['month'] = rdf['date'].dt.to_period('M')
            monthly = rdf.groupby('month')['ret'].apply(lambda x: np.prod(1+x)-1)
            print(f"    MONTHLY (last 12):")
            for m, v in list(monthly.items())[-12:]:
                bar = "+" * min(int(abs(v)*50), 30) if v > 0 else "-" * min(int(abs(v)*50), 30)
                print(f"      {m}: {v*100:>+8.1f}%  {bar}")

            # Rolling stats
            cum = np.cumprod(1 + rets.values)
            dd = cum / np.maximum.accumulate(cum) - 1
            print(f"    SUMMARY: Days={len(rets)} TotalRet={(cum[-1]-1)*100:.1f}% AvgDaily={np.mean(rets.values)*100:.3f}% MedianDaily={np.median(rets.values)*100:.3f}% BestDay={np.max(rets.values)*100:.2f}% WorstDay={np.min(rets.values)*100:.2f}% MaxDD={np.min(dd)*100:.1f}%")

print("")
print(sep)
print("  METRIC CORRELATIONS")
print(sep)

for market, mdf, label in [(US_F, US_F, 'US'), (IND_F, IND_F, 'India')]:
    cols = ['sharpe','cagr','mdd','vol','wr','pf','rsq','sortino']
    corr = mdf[cols].corr()
    print("")
    print(f"  {label} metric correlations:")
    header = f"  {'':>10}"
    for c in cols: header += f" {c[:6]:>7}"
    print(header)
    for r in cols:
        line = f"  {r:>10}"
        for c in cols:
            v = corr.loc[r, c]
            line += f" {v:>7.2f}"
        print(line)

print("")
print(sep)
print("  FINAL ACTIONABLE RECOMMENDATIONS")
print(sep)

for market, mdf, label in [(US_F, US_F, 'US'), (IND_F, IND_F, 'India')]:
    print("")
    print(f"  --- {label} ---")
    for h, hl in HOLDS.items():
        hdf = mdf[(mdf['hold']==h) & (mdf['filt']=='none')]
        if len(hdf)==0: continue
        balanced = hdf[(hdf['n']>=200)].sort_values('sharpe', ascending=False)
        if len(balanced)==0: continue
        best = balanced.iloc[0]
        print(f"    {hl}:")
        print(f"      BEST OVERALL: {best['strat'][:70]}")
        print(f"        Sharpe={best['sharpe']:.3f} CAGR={best['cagr']*100:.1f}% MDD={best['mdd']*100:.1f}% Vol={best['vol']*100:.1f}% WR={best['wr']*100:.1f}% PF={best['pf']:.2f} R2={best['rsq']:.3f} Days={best['n']}")

        safe = hdf[(hdf['n']>=200) & (hdf['cagr']>0)].sort_values('mdd', ascending=True)
        if len(safe)>0:
            s = safe.iloc[0]
            print(f"      SAFEST: {s['strat'][:70]}")
            print(f"        Sharpe={s['sharpe']:.3f} CAGR={s['cagr']*100:.1f}% MDD={s['mdd']*100:.1f}% Vol={s['vol']*100:.1f}% WR={s['wr']*100:.1f}%")

        lin = hdf[(hdf['n']>=200)].sort_values('rsq', ascending=False)
        if len(lin)>0:
            l = lin.iloc[0]
            print(f"      MOST CONSISTENT: {l['strat'][:70]}")
            print(f"        Sharpe={l['sharpe']:.3f} CAGR={l['cagr']*100:.1f}% MDD={l['mdd']*100:.1f}% R2={l['rsq']:.3f} Vol={l['vol']*100:.1f}%")

print("")
print(sep)
print("  ALL ANALYSIS COMPLETE")
print(sep)
