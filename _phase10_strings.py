"""Phase 10: Exhaustive search on US strings for 90%+ WR."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

t0 = time.time()
df = pd.read_parquet('strategy_results/string_sample_us_500.parquet')
df['date'] = pd.to_datetime(df['date'])
df['ret_1d'] = df['next_day_return'] / 100.0

all_dates = sorted(df['date'].unique())
n_dates = len(all_dates)
strs = sorted(df['string_id'].unique())
n_str = len(strs)
str_idx = {s: i for i, s in enumerate(strs)}
date_idx = {d: i for i, d in enumerate(all_dates)}

ret_mat = np.full((n_dates, n_str), np.nan)
feat_cols = ['ai_tech_score', 'ai_overall_score', 'prob_up_st_cross', 'weighted_alpha',
             'atrp', 'streak', 'change_pct', 'atr_signal', 'atr_streak']
feat_mats = {}
for f in feat_cols:
    feat_mats[f] = np.full((n_dates, n_str), np.nan)

d_idx = df['date'].map(date_idx).values
s_idx = df['string_id'].map(str_idx).values
v = (~np.isnan(d_idx)) & (~np.isnan(s_idx))
di = d_idx[v].astype(int); si = s_idx[v].astype(int)
ret_mat[di, si] = df['ret_1d'].values[v]
for f in feat_cols:
    if f in df.columns:
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
date_years = np.array([d.year for d in all_dates])

print(f"Loaded: {n_str} strings, {n_dates} dates ({time.time()-t0:.1f}s)")

results = []

# Exhaustive search
beaten_thresholds = [-3, -4, -5, -6, -7, -8]
ai_thresholds = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
prob_thresholds = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]

mkt_conditions = {
    'golden': (mkt_mean_5d > 0) & (mkt_mean_20d > 0) & (mkt_breadth > 0.55),
    'golden_loose': (mkt_mean_5d > 0) & (mkt_mean_20d > 0),
    'mup5d': (mkt_mean_5d > 0),
    'any': np.ones(n_dates, dtype=bool),
}

extra_conditions = {
    'none': np.ones((n_dates, n_str), dtype=bool),
    'atr_signal': feat_mats['atr_signal'] > 0,
    'streak_ge0': feat_mats['streak'] >= 0,
}

# Also try: streak-based and composite
for streak_n in [2, 3, 5]:
    extra_conditions[f'strk_ge{streak_n}'] = feat_mats['streak'] >= streak_n

# Composite
comp = (pct['ai_tech_score'] + pct['prob_up_st_cross'] + pct['weighted_alpha']) / 3
for comp_thr in [0.8, 0.85, 0.9]:
    extra_conditions[f'comp_ge{comp_thr:.2f}'] = comp >= comp_thr

print(f"Testing combos...")
tested = 0

for beaten_thr in beaten_thresholds:
    beaten_mask = feat_mats['change_pct'] < beaten_thr
    
    for ai_thr in ai_thresholds:
        ai_mask = pct['ai_tech_score'] >= ai_thr
        
        for prob_thr in prob_thresholds:
            prob_mask = pct['prob_up_st_cross'] >= prob_thr
            
            for mkt_name, mkt_1d in mkt_conditions.items():
                for ext_name, ext_mask in extra_conditions.items():
                    combined = mkt_1d[:, np.newaxis] & beaten_mask & ai_mask & prob_mask & ext_mask
                    
                    subset = ret_mat[combined]
                    valid = subset[~np.isnan(subset)]
                    n = len(valid)
                    tested += 1
                    
                    if n < 10:
                        continue
                    
                    wr = (valid > 0).mean()
                    if wr < 0.80:
                        continue
                    
                    avg_ret = valid.mean()
                    
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

results.sort(key=lambda x: (x['wr'], x['n']), reverse=True)

with open('strategy_results/phase10_string_results.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"Tested: {tested}, Passed: {len(results)} ({time.time()-t0:.1f}s)")

print(f"\n{'='*80}")
print(f"90%+ WIN RATE: {len([r for r in results if r['wr'] >= 90])}")
print(f"{'='*80}")
for r in [r for r in results if r['wr'] >= 90][:30]:
    yr = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r['y'].items())])
    print(f"  {r['s']}: WR={r['wr']}%, N={r['n']}, Ret={r['ar']:.4f}%")
    if yr: print(f"    {yr}")

print(f"\nTOP 30:")
for i, r in enumerate(results[:30]):
    yr = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r['y'].items())])
    print(f"{i+1}. {r['s']}: WR={r['wr']}%, N={r['n']}, Ret={r['ar']:.4f}%")
    if yr: print(f"   {yr}")
