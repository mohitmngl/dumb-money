"""Phase 9b: Optimized exhaustive search."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

t0 = time.time()
df = pd.read_parquet('strategy_results/us_liquid_stocks.parquet')
df['date'] = pd.to_datetime(df['date'])
df['ret_1d'] = df['next_day_return'] / 100.0

all_dates = sorted(df['date'].unique())
n_dates = len(all_dates)
syms = sorted(df['symbol'].unique())
n_str = len(syms)
sym_idx = {s: i for i, s in enumerate(syms)}
date_idx = {d: i for i, d in enumerate(all_dates)}

ret_mat = np.full((n_dates, n_str), np.nan)
feat_cols = ['ai_tech_score', 'ai_overall_score', 'prob_up_st_cross', 'weighted_alpha',
             'atrp', 'streak', 'change_pct', 'atr_signal', 'atr_streak']
feat_mats = {}
for f in feat_cols:
    feat_mats[f] = np.full((n_dates, n_str), np.nan)

d_idx = df['date'].map(date_idx).values
s_idx = df['symbol'].map(sym_idx).values
v = (~np.isnan(d_idx)) & (~np.isnan(s_idx))
di = d_idx[v].astype(int); si = s_idx[v].astype(int)
ret_mat[di, si] = df['ret_1d'].values[v]
for f in feat_cols:
    feat_mats[f][di, si] = df[f].values[v]

pct = {}
for f in feat_cols:
    mat = feat_mats[f]
    ranked = np.zeros_like(mat)
    for i in range(n_dates):
        row = mat[i]; vm = ~np.isnan(row)
        if vm.sum() > 0:
            order = np.argsort(np.argsort(row[vm]))
            ranked[i, vm] = order / max(vm.sum() - 1, 1)
    pct[f] = ranked

mkt_mean = np.nanmean(ret_mat, axis=1)
mkt_breadth = (ret_mat > 0).mean(axis=1)
mkt_mean_5d = pd.Series(mkt_mean).rolling(5).mean().values
mkt_mean_20d = pd.Series(mkt_mean).rolling(20).mean().values

# Precompute year array for fast yearly breakdown
date_years = np.array([d.year for d in all_dates])

print(f"Setup: {time.time()-t0:.1f}s")

results = []
tested = 0

beaten_thresholds = [-3, -4, -5, -6, -7, -8]
ai_thresholds = [0.70, 0.75, 0.80, 0.82, 0.85, 0.87, 0.90, 0.95]
prob_thresholds = [0.70, 0.75, 0.80, 0.82, 0.85, 0.87, 0.90, 0.95]

mkt_conditions = {
    'golden': (mkt_mean_5d > 0) & (mkt_mean_20d > 0) & (mkt_breadth > 0.55),
    'golden_loose': (mkt_mean_5d > 0) & (mkt_mean_20d > 0),
    'mup5d_bull': (mkt_mean_5d > 0) & (mkt_breadth > 0.55),
}

extra_conditions = {
    'none': np.ones((n_dates, n_str), dtype=bool),
    'atr_signal': feat_mats['atr_signal'] > 0,
    'streak_ge0': feat_mats['streak'] >= 0,
    'wa60': pct['weighted_alpha'] >= 0.6,
}

total = len(beaten_thresholds) * len(ai_thresholds) * len(prob_thresholds) * len(mkt_conditions) * len(extra_conditions)
print(f"Combos: {total}")

for beaten_thr in beaten_thresholds:
    beaten_mask = feat_mats['change_pct'] < beaten_thr
    
    for ai_thr in ai_thresholds:
        ai_mask = pct['ai_tech_score'] >= ai_thr
        
        for prob_thr in prob_thresholds:
            prob_mask = pct['prob_up_st_cross'] >= prob_thr
            
            for mkt_name, mkt_1d in mkt_conditions.items():
                for ext_name, ext_mask in extra_conditions.items():
                    combined = mkt_1d[:, np.newaxis] & beaten_mask & ai_mask & prob_mask & ext_mask
                    
                    # Fast total WR
                    subset = ret_mat[combined]
                    valid = subset[~np.isnan(subset)]
                    n = len(valid)
                    tested += 1
                    
                    if n < 15:
                        continue
                    
                    wr = (valid > 0).mean()
                    if wr < 0.80:
                        continue
                    
                    avg_ret = valid.mean()
                    
                    # Fast yearly breakdown using precomputed years
                    yearly = {}
                    for yr in range(2020, 2027):
                        yr_mask = date_years == yr
                        yr_combined = combined[yr_mask]
                        yr_rets = ret_mat[yr_mask][yr_combined]
                        yr_valid = yr_rets[~np.isnan(yr_rets)]
                        if len(yr_valid) >= 3:
                            yearly[yr] = float(round((yr_valid > 0).mean() * 100, 1))
                    
                    results.append({
                        's': f'c{beaten_thr}_ai{ai_thr:.2f}_p{prob_thr:.2f}_{mkt_name}_{ext_name}',
                        'wr': float(round(wr * 100, 1)),
                        'ar': float(round(avg_ret * 100, 4)),
                        'n': n,
                        'y': yearly
                    })
                    
                    if tested % 5000 == 0:
                        print(f"  {tested}/{total} ({time.time()-t0:.1f}s) {len(results)} passed")

results.sort(key=lambda x: (x['wr'], x['n']), reverse=True)

with open('strategy_results/phase9b_results.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"\nTested: {tested}, Passed: {len(results)} ({time.time()-t0:.1f}s)")

print(f"\n{'='*80}")
print(f"90%+ WIN RATE: {len([r for r in results if r['wr'] >= 90])}")
print(f"{'='*80}")
for r in [r for r in results if r['wr'] >= 90][:50]:
    yr = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r['y'].items())])
    print(f"  {r['s']}: WR={r['wr']}%, N={r['n']}, Ret={r['ar']:.4f}%")
    if yr: print(f"    {yr}")

print(f"\nTOP 40:")
for i, r in enumerate(results[:40]):
    yr = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r['y'].items())])
    print(f"{i+1}. {r['s']}: WR={r['wr']}%, N={r['n']}, Ret={r['ar']:.4f}%")
    if yr: print(f"   {yr}")
