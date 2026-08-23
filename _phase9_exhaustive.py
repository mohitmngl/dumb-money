"""Phase 9: Final push - exhaustive combo of the best conditions."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 9: FINAL PUSH TO 90%+")
print("=" * 80)
t0 = time.time()

df = pd.read_parquet('strategy_results/us_liquid_stocks.parquet')
df['date'] = pd.to_datetime(df['date'])
df['ret_1d'] = df['next_day_return'] / 100.0

all_dates = sorted(df['date'].unique())
n_dates = len(all_dates)
date_idx = {d: i for i, d in enumerate(all_dates)}
syms = sorted(df['symbol'].unique())
n_str = len(syms)
sym_idx = {s: i for i, s in enumerate(syms)}

ret_mat = np.full((n_dates, n_str), np.nan)
feat_cols = ['ai_tech_score', 'ai_overall_score', 'prob_up_st_cross', 'weighted_alpha',
             'atrp', 'streak', 'change_pct', 'atr_signal', 'accel_signal',
             'atr_streak', 'volume', 'price', 'atr_value']
feat_mats = {}
for f in feat_cols:
    feat_mats[f] = np.full((n_dates, n_str), np.nan)

d_idx = df['date'].map(date_idx).values
s_idx = df['symbol'].map(sym_idx).values
valid = (~np.isnan(d_idx)) & (~np.isnan(s_idx))
di = d_idx[valid].astype(int)
si = s_idx[valid].astype(int)
ret_mat[di, si] = df['ret_1d'].values[valid]
for f in feat_cols:
    feat_mats[f][di, si] = df[f].values[valid]

# Pct ranks
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

# Market
mkt_mean = np.nanmean(ret_mat, axis=1)
mkt_breadth = (ret_mat > 0).mean(axis=1)
mkt_mean_5d = pd.Series(mkt_mean).rolling(5).mean().values
mkt_mean_20d = pd.Series(mkt_mean).rolling(20).mean().values
mkt_golden = (mkt_mean_5d > 0) & (mkt_mean_20d > 0) & (mkt_breadth > 0.55)

print(f"Loaded ({time.time()-t0:.1f}s)")

results = []

# The best strategy was: recovery_chg-5_ai85_prob90_golden (88.5%, N=61)
# Let's exhaustively vary every parameter around this

# Beaten thresholds
beaten_thresholds = [-3, -4, -5, -6, -7, -8, -10]

# AI thresholds
ai_thresholds = [0.70, 0.75, 0.80, 0.82, 0.85, 0.87, 0.90, 0.92, 0.95]

# Prob thresholds
prob_thresholds = [0.70, 0.75, 0.80, 0.82, 0.85, 0.87, 0.90, 0.92, 0.95]

# WA thresholds
wa_thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

# Market conditions
mkt_conditions = {
    'golden': mkt_golden,
    'golden_loose': (mkt_mean_5d > 0) & (mkt_mean_20d > 0),
    'golden_bull': mkt_golden & (mkt_breadth > 0.6),
    'mup5d_bull': (mkt_mean_5d > 0) & (mkt_breadth > 0.55),
    'mup5d': (mkt_mean_5d > 0),
}

# Extra stock conditions
extra_conditions = {
    'none': np.ones((n_dates, n_str), dtype=bool),
    'atr_signal': feat_mats['atr_signal'] > 0,
    'streak_ge0': feat_mats['streak'] >= 0,
    'streak_ge2': feat_mats['streak'] >= 2,
    'atr_streak_ge2': feat_mats['atr_streak'] >= 2,
    'wa50': pct['weighted_alpha'] >= 0.5,
    'wa60': pct['weighted_alpha'] >= 0.6,
    'wa70': pct['weighted_alpha'] >= 0.7,
}

print(f"Exhaustive search: {len(beaten_thresholds)} x {len(ai_thresholds)} x {len(prob_thresholds)} x {len(mkt_conditions)} x {len(extra_conditions)} = {len(beaten_thresholds)*len(ai_thresholds)*len(prob_thresholds)*len(mkt_conditions)*len(extra_conditions)} combos")

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
                    subset_rets = ret_mat[combined]
                    valid_rets = subset_rets[~np.isnan(subset_rets)]
                    n = len(valid_rets)
                    
                    tested += 1
                    
                    if n < 15:
                        continue
                    
                    wr = (valid_rets > 0).mean()
                    avg_ret = valid_rets.mean()
                    
                    # Year breakdown
                    yearly = {}
                    for i in range(n_dates):
                        dm = combined[i]
                        dr = ret_mat[i, dm]
                        dv = dr[~np.isnan(dr)]
                        if len(dv) == 0:
                            continue
                        yr = all_dates[i].year
                        if yr not in yearly:
                            yearly[yr] = {'w': 0, 'n': 0}
                        yearly[yr]['w'] += int((dv > 0).sum())
                        yearly[yr]['n'] += len(dv)
                    yearly_pct = {yr: round(v['w']/v['n']*100, 1) for yr, v in yearly.items() if v['n'] >= 3}
                    
                    results.append({
                        'strategy': f'rec_chg{beaten_thr}_ai{ai_thr:.2f}_prob{prob_thr:.2f}_{mkt_name}_{ext_name}',
                        'win_rate': float(wr * 100),
                        'avg_daily_ret': float(avg_ret * 100),
                        'n_days': n,
                        'yearly_wr': yearly_pct
                    })
                    
                    if tested % 10000 == 0:
                        print(f"  Tested {tested} ({time.time()-t0:.1f}s), {len(results)} passed")

# Sort
results.sort(key=lambda x: (x['win_rate'], x['n_days']), reverse=True)
seen = set()
unique = []
for r in results:
    key = r['strategy']
    if key not in seen:
        seen.add(key)
        unique.append(r)
results = unique

with open('strategy_results/phase9_results.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"\nTested: {tested}, Passed: {len(results)} ({time.time()-t0:.1f}s)")

# Print 90%+ WR
print(f"\n{'='*80}")
print(f"90%+ WIN RATE: {len([r for r in results if r['win_rate'] >= 90])}")
print(f"{'='*80}")
for r in [r for r in results if r['win_rate'] >= 90][:50]:
    yr = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"  {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")
    if yr: print(f"    {yr}")

# Print top 50
print(f"\n{'='*80}")
print("TOP 50:")
print(f"{'='*80}")
for i, r in enumerate(results[:50]):
    yr = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"{i+1}. {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")
    if yr: print(f"   {yr}")
