"""Phase 5: Load US strings and search for 90%+ WR strategies."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 5: US STRING DATA - 90%+ WIN RATE SEARCH")
print("=" * 80)
t0 = time.time()

# Load US strings (use the 260-string sample we already have)
df = pd.read_parquet('strategy_results/string_sample_us_500.parquet')
df['date'] = pd.to_datetime(df['date'])
df['ret_1d'] = df['next_day_return'] / 100.0
n_str = df['string_id'].nunique()
n_dates = df['date'].nunique()
print(f"Loaded: {n_str} strings, {n_dates} dates ({time.time()-t0:.1f}s)")

# Build matrices
all_dates = sorted(df['date'].unique())
date_idx = {d: i for i, d in enumerate(all_dates)}
strs = sorted(df['string_id'].unique())
str_idx = {s: i for i, s in enumerate(strs)}

ret_mat = np.full((n_dates, n_str), np.nan)
feat_cols = ['ai_tech_score', 'ai_overall_score', 'prob_up_st_cross', 'weighted_alpha',
             'atrp', 'streak', 'change_pct', 'atr_signal', 'accel_signal',
             'atr_streak', 'volume', 'price']
feat_mats = {}
for f in feat_cols:
    feat_mats[f] = np.full((n_dates, n_str), np.nan)

d_idx = df['date'].map(date_idx).values
s_idx = df['string_id'].map(str_idx).values
valid = (~np.isnan(d_idx)) & (~np.isnan(s_idx))
di = d_idx[valid].astype(int)
si = s_idx[valid].astype(int)
ret_mat[di, si] = df['ret_1d'].values[valid]
for f in feat_cols:
    if f in df.columns:
        feat_mats[f][di, si] = df[f].values[valid]

# Cross-sectional ranks
pct_mats = {}
for f in feat_cols:
    mat = feat_mats[f]
    ranked = np.zeros_like(mat)
    for i in range(n_dates):
        row = mat[i]
        valid_mask = ~np.isnan(row)
        if valid_mask.sum() > 0:
            order = np.argsort(np.argsort(row[valid_mask]))
            ranked[i, valid_mask] = order / max(valid_mask.sum() - 1, 1)
    pct_mats[f] = ranked

# Market-wide stats
mkt_mean = np.nanmean(ret_mat, axis=1)
mkt_breadth = (ret_mat > 0).mean(axis=1)
mkt_mean_5d = pd.Series(mkt_mean).rolling(5).mean().values
mkt_mean_20d = pd.Series(mkt_mean).rolling(20).mean().values

print(f"Matrices built ({time.time()-t0:.1f}s)")

results = []

# === STRING-SPECIFIC STRATEGIES ===
print("\nSearching string strategies...")

# Market states for strings
market_states = {
    'any': np.ones(n_dates, dtype=bool),
    'bull_5d': mkt_mean_5d > 0,
    'bull_20d': mkt_mean_20d > 0,
    'high_breadth': mkt_breadth > 0.55,
    'massive_bull': mkt_mean > 0.005,
    'perfect': (mkt_mean > 0) & (mkt_mean_5d > 0) & (mkt_breadth > 0.55),
}

# Approach 1: Top-N strings all positive
for score_name, score_mat in [
    ('streak', pct_mats['streak']),
    ('ai_tech', pct_mats['ai_tech_score']),
    ('prob_st', pct_mats['prob_up_st_cross']),
    ('composite', (pct_mats['ai_tech_score'] + pct_mats['prob_up_st_cross'] + pct_mats['weighted_alpha']) / 3),
]:
    for top_n in [1, 2, 3, 5]:
        for mkt_name, mkt_mask in market_states.items():
            daily_wr = []
            daily_rets = []
            dates_used = []
            
            for i in range(n_dates):
                if not mkt_mask[i]:
                    continue
                
                scores = score_mat[i]
                rets = ret_mat[i]
                valid_mask = ~np.isnan(scores) & ~np.isnan(rets)
                if valid_mask.sum() < top_n:
                    continue
                
                scores_masked = scores.copy()
                scores_masked[~valid_mask] = -np.inf
                top_idx = np.argpartition(-scores_masked, top_n)[:top_n]
                
                top_rets = rets[top_idx]
                valid_top = top_rets[~np.isnan(top_rets)]
                if len(valid_top) >= max(1, top_n // 2):
                    all_pos = (valid_top > 0).all()
                    daily_wr.append(all_pos)
                    daily_rets.append(valid_top.mean())
                    dates_used.append(all_dates[i])
            
            if len(daily_wr) < 30:
                continue
            
            wr = np.mean(daily_wr)
            avg_ret = np.mean(daily_rets)
            total_ret = np.prod(1 + np.array(daily_rets)) - 1
            
            yearly_wr = {}
            for yr in range(2020, 2027):
                yr_mask = [d.year == yr for d in dates_used]
                yr_wr = [daily_wr[j] for j in range(len(daily_wr)) if yr_mask[j]]
                if len(yr_wr) > 10:
                    yearly_wr[yr] = float(np.mean(yr_wr) * 100)
            
            results.append({
                'strategy': f'{mkt_name}_{score_name}_top{top_n}',
                'win_rate': float(wr * 100),
                'avg_daily_ret': float(avg_ret * 100),
                'total_ret': float(total_ret * 100),
                'n_days': len(daily_wr),
                'yearly_wr': yearly_wr
            })

# Approach 2: Extreme percentile stacking on strings
extreme_filters = [
    ('ai90', pct_mats['ai_tech_score'] >= 0.9),
    ('ai95', pct_mats['ai_tech_score'] >= 0.95),
    ('prob90', pct_mats['prob_up_st_cross'] >= 0.9),
    ('prob95', pct_mats['prob_up_st_cross'] >= 0.95),
    ('streak90', pct_mats['streak'] >= 0.9),
    ('ai90_prob90', (pct_mats['ai_tech_score'] >= 0.9) & (pct_mats['prob_up_st_cross'] >= 0.9)),
    ('ai95_prob95', (pct_mats['ai_tech_score'] >= 0.95) & (pct_mats['prob_up_st_cross'] >= 0.95)),
    ('ai90_prob90_wa80', (pct_mats['ai_tech_score'] >= 0.9) & (pct_mats['prob_up_st_cross'] >= 0.9) & (pct_mats['weighted_alpha'] >= 0.8)),
    ('ai95_prob95_wa90', (pct_mats['ai_tech_score'] >= 0.95) & (pct_mats['prob_up_st_cross'] >= 0.95) & (pct_mats['weighted_alpha'] >= 0.9)),
    ('ultra', (pct_mats['ai_tech_score'] >= 0.95) & (pct_mats['prob_up_st_cross'] >= 0.95) & (pct_mats['weighted_alpha'] >= 0.9) & (pct_mats['atrp'] <= 0.3)),
]

for name, mask in extreme_filters:
    for mkt_name, mkt_mask in market_states.items():
        combined = mkt_mask[:, np.newaxis] & mask
        subset_rets = ret_mat[combined]
        valid_rets = subset_rets[~np.isnan(subset_rets)]
        n = len(valid_rets)
        if n < 10:
            continue
        
        wr = (valid_rets > 0).mean()
        avg_ret = valid_rets.mean()
        
        yearly_wr = {}
        for yr in range(2020, 2027):
            yr_start = np.searchsorted(all_dates, np.datetime64(f'{yr}-01-01'))
            yr_end = np.searchsorted(all_dates, np.datetime64(f'{yr}-12-31'))
            yr_combined = combined[yr_start:yr_end]
            yr_rets = ret_mat[yr_start:yr_end][yr_combined]
            yr_valid = yr_rets[~np.isnan(yr_rets)]
            if len(yr_valid) > 5:
                yearly_wr[yr] = float((yr_valid > 0).mean() * 100)
        
        results.append({
            'strategy': f'{name}_{mkt_name}',
            'win_rate': float(wr * 100),
            'avg_daily_ret': float(avg_ret * 100),
            'total_ret': 0,
            'n_days': n,
            'yearly_wr': yearly_wr
        })

# Approach 3: Streak patterns on strings
for streak_n in [3, 5, 7]:
    for streak_dir in ['up', 'down']:
        if streak_dir == 'up':
            streak_mask = feat_mats['streak'] >= streak_n
        else:
            streak_mask = feat_mats['streak'] <= -streak_n
        
        for mkt_name, mkt_mask in market_states.items():
            combined = mkt_mask[:, np.newaxis] & streak_mask
            subset_rets = ret_mat[combined]
            valid_rets = subset_rets[~np.isnan(subset_rets)]
            n = len(valid_rets)
            if n < 20:
                continue
            
            wr = (valid_rets > 0).mean()
            avg_ret = valid_rets.mean()
            
            if wr >= 0.50:
                results.append({
                    'strategy': f'string_streak_{streak_dir}{streak_n}_{mkt_name}',
                    'win_rate': float(wr * 100),
                    'avg_daily_ret': float(avg_ret * 100),
                    'total_ret': 0,
                    'n_days': n,
                    'yearly_wr': {}
                })

results.sort(key=lambda x: (x['win_rate'], x['n_days']), reverse=True)

with open('strategy_results/phase5_string_results.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"\nTotal results: {len(results)} ({time.time()-t0:.1f}s)")

# Print 90%+ WR
high_wr = [r for r in results if r['win_rate'] >= 90]
print(f"\n{'='*80}")
print(f"90%+ WIN RATE STRING STRATEGIES: {len(high_wr)}")
print(f"{'='*80}")
for r in sorted(high_wr, key=lambda x: (-x['win_rate'], -x['n_days'])):
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"  {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")
    if yr_str:
        print(f"    {yr_str}")

# Print top 30
print(f"\n{'='*80}")
print("TOP 30 STRING STRATEGIES BY WIN RATE")
print(f"{'='*80}")
for i, r in enumerate(results[:30]):
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"{i+1}. {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")
    if yr_str:
        print(f"   {yr_str}")
