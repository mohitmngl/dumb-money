"""Quick final analysis - correlations and recommendations only"""
import json, os, sys, io
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
def load(m):
    with open(os.path.join(OUTPUT, f'{m}_all_strategies.json')) as f:
        return pd.DataFrame(json.load(f))

US = load('US'); IND = load('India')
US_F = US[US['n'] >= 100].copy()
IND_F = IND[IND['n'] >= 100].copy()

sep = "=" * 120

# 1. Correlations
print(sep)
print("  METRIC CORRELATIONS -- Do High-Sharpe strategies also have high CAGR?")
print(sep)

for market, mdf, label in [(US_F, US_F, 'US'), (IND_F, IND_F, 'India')]:
    cols = ['sharpe','cagr','mdd','vol','wr','pf','rsq','sortino']
    corr = mdf[cols].corr()
    print(f"\n  {label} metric correlations:")
    header = f"  {'':>10}"
    for c in cols: header += f" {c[:7]:>8}"
    print(header)
    for r in cols:
        line = f"  {r:>10}"
        for c in cols:
            v = corr.loc[r, c]
            line += f" {v:>8.2f}"
        print(line)

# 2. Final actionable recommendations
print(f"\n{sep}")
print("  FINAL ACTIONABLE RECOMMENDATIONS")
print(sep)

for market, mdf, label in [(US_F, US_F, 'US'), (IND_F, IND_F, 'India')]:
    print(f"\n  {'='*80}")
    print(f"  {label}")
    print(f"  {'='*80}")
    for h, hl in [('1d','BTST'),('5d','5-DAY'),('1mo','1-MONTH')]:
        hdf = mdf[(mdf['hold']==h) & (mdf['filt']=='none')]
        if len(hdf)==0: continue

        # Best overall
        balanced = hdf[(hdf['n']>=200)].sort_values('sharpe', ascending=False)
        if len(balanced)>0:
            best = balanced.iloc[0]
            print(f"\n    {hl}:")
            print(f"      BEST SHARPE: {best['strat'][:70]}")
            print(f"        Sh={best['sharpe']:.3f} CAGR={best['cagr']*100:.1f}% MDD={best['mdd']*100:.1f}% Vol={best['vol']*100:.1f}% WR={best['wr']*100:.1f}% PF={best['pf']:.2f} R2={best['rsq']:.3f} Days={best['n']}")

        # Most linear
        lin = hdf[(hdf['n']>=200)].sort_values('rsq', ascending=False)
        if len(lin)>0:
            l = lin.iloc[0]
            print(f"      MOST LINEAR:  {l['strat'][:70]}")
            print(f"        Sh={l['sharpe']:.3f} CAGR={l['cagr']*100:.1f}% MDD={l['mdd']*100:.1f}% R2={l['rsq']:.3f} Vol={l['vol']*100:.1f}%")

        # Highest CAGR (reasonable)
        cagr = hdf[(hdf['n']>=200)].sort_values('cagr', ascending=False)
        if len(cagr)>0:
            c = cagr.iloc[0]
            print(f"      BEST CAGR:   {c['strat'][:70]}")
            print(f"        Sh={c['sharpe']:.3f} CAGR={c['cagr']*100:.1f}% MDD={c['mdd']*100:.1f}% Vol={c['vol']*100:.1f}% WR={c['wr']*100:.1f}%")

        # Lowest vol (still profitable)
        safe = hdf[(hdf['n']>=200) & (hdf['cagr']>0)].sort_values('vol', ascending=True)
        if len(safe)>0:
            s = safe.iloc[0]
            print(f"      LEAST VOL:   {s['strat'][:70]}")
            print(f"        Sh={s['sharpe']:.3f} CAGR={s['cagr']*100:.1f}% MDD={s['mdd']*100:.1f}% Vol={s['vol']*100:.1f}% WR={s['wr']*100:.1f}%")

        # Lowest DD (still profitable)
        safe2 = hdf[(hdf['n']>=200) & (hdf['cagr']>0)].sort_values('mdd', ascending=True)
        if len(safe2)>0:
            s2 = safe2.iloc[0]
            print(f"      SHALLOWEST:  {s2['strat'][:70]}")
            print(f"        Sh={s2['sharpe']:.3f} CAGR={s2['cagr']*100:.1f}% MDD={s2['mdd']*100:.1f}% Vol={s2['vol']*100:.1f}% WR={s2['wr']*100:.1f}%")

# 3. TRUSTWORTHINESS MATRIX
print(f"\n{sep}")
print("  TRUSTWORTHINESS MATRIX -- What to actually use")
print(sep)

for market, mdf, label in [(US_F, US_F, 'US'), (IND_F, IND_F, 'India')]:
    print(f"\n  {label}:")
    for h, hl in [('1d','BTST'),('5d','5-DAY'),('1mo','1-MONTH')]:
        hdf = mdf[(mdf['hold']==h) & (mdf['filt']=='none')]
        if len(hdf)==0: continue
        # Tier 1: n>=500
        t1 = hdf[hdf['n']>=500].sort_values('sharpe', ascending=False)
        # Tier 2: n>=200
        t2 = hdf[(hdf['n']>=200) & (hdf['n']<500)].sort_values('sharpe', ascending=False)
        # Tier 3: n>=100
        t3 = hdf[(hdf['n']>=100) & (hdf['n']<200)].sort_values('sharpe', ascending=False)

        print(f"\n    {hl}:")
        print(f"    {'Tier':<8} {'Best Strategy':<55} {'Sharpe':>7} {'CAGR':>8} {'MDD':>8} {'WR':>6} {'Days':>5}")
        for tier, tdf, lbl in [('TIER 1', t1, '500+ days'), ('TIER 2', t2, '200-499'), ('TIER 3', t3, '100-199')]:
            if len(tdf)>0:
                r = tdf.iloc[0]
                print(f"    {tier:<8} {r['strat'][:55]:<55} {r['sharpe']:>7.3f} {r['cagr']*100:>7.1f}% {r['mdd']*100:>7.1f}% {r['wr']*100:>5.1f}% {r['n']:>5}")

# 4. KEY INSIGHTS
print(f"\n{sep}")
print("  KEY INSIGHTS & WARNINGS")
print(sep)
print("""
  1. COLUMN IMPORTANCE:
     - US: accel_base and accel_a are the only positive columns (momentum acceleration)
     - India: ai_volume_profile_score, streak, ai_momentum_score dominate (momentum + AI signals)
     - atrp, change_pct, atr_value are DEAD LAST in both markets (avoid)

  2. BINARY FILTERS:
     - Filters REDUCE sample size dramatically (1777 -> 923 avg days)
     - Some filters produce INSANE CAGR from tiny samples (survivorship bias amplified)
     - No-filter strategies are MORE RELIABLE for actual trading

  3. TOP-N SENSITIVITY:
     - US: More concentration (top5) does NOT help - higher vol, worse Sharpe
     - India: More concentration (top5) helps slightly for BTST (Sh=1.54 vs 1.25 for top30)
     - Best sweet spot: top15-20 for most strategies

  4. MARKET DIFFERENCE:
     - US: ALL no-filter strategies LOSE money (negative Sharpe). Only accel_base/accel_a are positive
     - India: ALL no-filter strategies MAKE money. Momentum and AI signals work very well
     - India is a MUCH better market for these screener columns

  5. HOLD PERIOD:
     - US: 1-month is worst (negative Sharpe). BTST and 5-day are marginally better
     - India: BTST has highest Sharpe (1.36). 5-day has highest avg return. 1-month is safest

  6. TOP US BTST STRATEGY (trustworthy):
     - atr_crossed_above=1 + rank prob_up_st_cross top20
     - Annual: 2020 +60.9%, 2021 +120.2%, 2022 -10.5%, 2023 +33.2%, 2024 +62%, 2025 +144.9%, 2026 YTD +64%
     - 927 days sample, 97.7% win rate, MDD -7.2%, avg daily +0.24%
     - WARNING: 97.7% WR is suspicious - likely survivorship bias + small-cap pump

  7. TOP INDIA STRATEGY (trustworthy):
     - ai_volume_profile_score top15 (no filter), 7656 days
     - Sharpe 3.816, avg WR 63.2%, PF 2.48
     - India momentum works because market has strong trending stocks

  8. CRITICAL WARNING:
     - US strategies with binary filters show IMPOSSIBLE CAGRs (10^300%)
     - This is pure overfitting to tiny samples. DO NOT TRADE THESE.
     - Use only strategies with 200+ days AND reasonable CAGR (<1000%)
""")

print(sep)
print("  ANALYSIS COMPLETE")
print(sep)
