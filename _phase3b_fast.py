"""Phase 3b: Ultra-fast vectorized multi-factor search."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 3B: ULTRA-FAST VECTORIZED SEARCH")
print("=" * 80)
t0 = time.time()

df = pd.read_parquet('strategy_results/us_liquid_stocks.parquet')
df['date'] = pd.to_datetime(df['date'])
df['ret_1d'] = df['next_day_return'] / 100.0
n_str = df['symbol'].nunique()
n_dates = df['date'].nunique()
print(f"Loaded: {n_str} stocks, {n_dates} dates")

# Build numpy matrices
all_dates = sorted(df['date'].unique())
date_idx = {d: i for i, d in enumerate(all_dates)}
syms = sorted(df['symbol'].unique())
sym_idx = {s: i for i, s in enumerate(syms)}

print("Building matrices...")
ret_mat = np.full((n_dates, n_str), np.nan)
feat_cols = ['ai_tech_score', 'ai_overall_score', 'prob_up_st_cross', 'weighted_alpha',
             'atrp', 'streak', 'change_pct', 'atr_signal', 'accel_signal',
             'atr_streak', 'volume', 'price']
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

print(f"  Matrices: ({n_dates}, {n_str}) ({time.time()-t0:.1f}s)")

# Compute derived features
print("Computing derived features...")
# Cross-sectional ranks (vectorized)
pct_mats = {}
for f in feat_cols:
    col_mat = feat_mats[f]
    # Rank along axis=1 (stocks) for each date
    ranked = np.apply_along_axis(lambda x: np.argsort(np.argsort(x)), 1, col_mat)
    valid_counts = (~np.isnan(col_mat)).sum(axis=1, keepdims=True)
    pct_mats[f] = ranked / (np.maximum(valid_counts, 1))

# Composite scores
pct_ai = pct_mats['ai_tech_score']
pct_prob = pct_mats['prob_up_st_cross']
pct_wa = pct_mats['weighted_alpha']
pct_atrp_inv = 1 - pct_mats['atrp']  # Lower ATRP = better
pct_streak = pct_mats['streak']

composite_3 = (pct_ai + pct_prob + pct_wa) / 3
composite_4 = (pct_ai + pct_prob + pct_wa + pct_atrp_inv) / 4
composite_quality = (pct_ai * 2 + pct_prob + pct_wa) / 4
composite_ultra = (pct_ai + pct_prob + pct_wa + pct_atrp_inv + pct_streak) / 5

# Market breadth per date
mkt_breadth = (ret_mat > 0).mean(axis=1)
mkt_ret = np.nanmean(ret_mat, axis=1)

# Strategy search
print("Searching strategies...")
t0 = time.time()
results = []

# === APPROACH 1: Top-N ALL POSITIVE ===
# For each day, pick top N by score. Win = ALL N are positive.
for score_name, score_mat in [
    ('ai_tech', pct_mats['ai_tech_score']),
    ('prob_st', pct_mats['prob_up_st_cross']),
    ('ai_tech_x_prob', pct_ai * pct_prob),
    ('composite_3', composite_3),
    ('composite_4', composite_4),
    ('composite_quality', composite_quality),
    ('composite_ultra', composite_ultra),
]:
    for top_n in [1, 2, 3, 5]:
        for min_pctile in [0.0, 0.5, 0.6, 0.7, 0.8, 0.9]:
            daily_wr = []
            daily_rets = []
            
            for i in range(n_dates):
                scores = score_mat[i]
                rets = ret_mat[i]
                
                valid_mask = ~np.isnan(scores) & ~np.isnan(rets)
                if valid_mask.sum() < top_n:
                    continue
                
                # Apply minimum percentile filter
                scores_valid = scores.copy()
                scores_valid[~valid_mask] = -np.inf
                threshold = np.percentile(scores[valid_mask], min_pctile * 100)
                above = scores_valid >= threshold
                if above.sum() < top_n:
                    continue
                
                # Get top N
                scores_masked = scores.copy()
                scores_masked[~above] = -np.inf
                top_idx = np.argpartition(-scores_masked, top_n)[:top_n]
                
                top_rets = rets[top_idx]
                valid_top = top_rets[~np.isnan(top_rets)]
                if len(valid_top) >= max(1, top_n // 2):
                    all_pos = (valid_top > 0).all()
                    daily_wr.append(all_pos)
                    daily_rets.append(valid_top.mean())
            
            if len(daily_wr) < 100:
                continue
            
            wr = np.mean(daily_wr)
            avg_ret = np.mean(daily_rets)
            total_ret = np.prod(1 + np.array(daily_rets)) - 1
            
            # Year breakdown
            yearly_wr = {}
            for yr in range(2020, 2027):
                yr_start = np.searchsorted(all_dates, np.datetime64(f'{yr}-01-01'))
                yr_end = np.searchsorted(all_dates, np.datetime64(f'{yr}-12-31'))
                yr_wr_vals = daily_wr[yr_start:min(yr_end, len(daily_wr))]
                if len(yr_wr_vals) > 20:
                    yearly_wr[yr] = float(np.mean(yr_wr_vals) * 100)
            
            if wr >= 0.50:
                results.append({
                    'strategy': f'{score_name}_top{top_n}_pct{min_pctile:.1f}_allpos',
                    'win_rate': float(wr * 100),
                    'avg_daily_ret': float(avg_ret * 100),
                    'total_ret': float(total_ret * 100),
                    'n_days': len(daily_wr),
                    'yearly_wr': yearly_wr
                })
            
            if len(results) % 100 == 0:
                print(f"  ... {len(results)} results, {time.time()-t0:.1f}s")

# === APPROACH 2: CONDITION STACKING ===
print("\nCondition stacking...")
stacked = [
    ('ai80_prob80', (pct_ai >= 0.8) & (pct_prob >= 0.8)),
    ('ai85_prob85', (pct_ai >= 0.85) & (pct_prob >= 0.85)),
    ('ai90_prob90', (pct_ai >= 0.9) & (pct_prob >= 0.9)),
    ('ai80_prob80_wa50', (pct_ai >= 0.8) & (pct_prob >= 0.8) & (pct_wa >= 0.5)),
    ('ai85_prob85_wa60', (pct_ai >= 0.85) & (pct_prob >= 0.85) & (pct_wa >= 0.6)),
    ('ai90_prob90_wa70', (pct_ai >= 0.9) & (pct_prob >= 0.9) & (pct_wa >= 0.7)),
    ('ai80_low_atrp', (pct_ai >= 0.8) & (pct_atrp_inv >= 0.7)),
    ('ai85_low_atrp', (pct_ai >= 0.85) & (pct_atrp_inv >= 0.7)),
    ('ai90_low_atrp', (pct_ai >= 0.9) & (pct_atrp_inv >= 0.7)),
    ('ai80_prob80_low_atrp', (pct_ai >= 0.8) & (pct_prob >= 0.8) & (pct_atrp_inv >= 0.7)),
    ('ai85_prob85_low_atrp', (pct_ai >= 0.85) & (pct_prob >= 0.85) & (pct_atrp_inv >= 0.7)),
    ('ai90_prob90_low_atrp', (pct_ai >= 0.9) & (pct_prob >= 0.9) & (pct_atrp_inv >= 0.8)),
    ('ultra_quality', (pct_ai >= 0.9) & (pct_prob >= 0.9) & (pct_wa >= 0.7) & (pct_atrp_inv >= 0.7)),
    ('mega_quality', (pct_ai >= 0.95) & (pct_prob >= 0.9) & (pct_wa >= 0.8)),
    ('triple_extreme', (pct_ai >= 0.9) & (pct_prob >= 0.9) & (pct_wa >= 0.9) & (pct_atrp_inv >= 0.8)),
]

for name, mask in stacked:
    subset_rets = ret_mat[mask]
    valid_rets = subset_rets[~np.isnan(subset_rets)]
    n = len(valid_rets)
    if n < 50:
        continue
    
    wr = (valid_rets > 0).mean()
    avg_ret = valid_rets.mean()
    
    # Year breakdown
    yearly_wr = {}
    for yr in range(2020, 2027):
        yr_start = np.searchsorted(all_dates, np.datetime64(f'{yr}-01-01'))
        yr_end = np.searchsorted(all_dates, np.datetime64(f'{yr}-12-31'))
        yr_mask = mask[yr_start:yr_end]
        yr_rets = ret_mat[yr_start:yr_end][yr_mask]
        yr_valid = yr_rets[~np.isnan(yr_rets)]
        if len(yr_valid) > 20:
            yearly_wr[yr] = float((yr_valid > 0).mean() * 100)
    
    results.append({
        'strategy': f'stack_{name}',
        'win_rate': float(wr * 100),
        'avg_daily_ret': float(avg_ret * 100),
        'total_ret': 0,
        'n_days': n,
        'yearly_wr': yearly_wr
    })

# === APPROACH 3: MARKET-CONDITIONAL ===
print("\nMarket-conditional strategies...")
# Only trade when market is up / breadth > 50%
mkt_up = mkt_ret > 0
mkt_bull = mkt_breadth > 0.55
mkt_strong_bull = mkt_breadth > 0.6

for mkt_name, mkt_mask in [('mkt_up', mkt_up), ('mkt_bull', mkt_bull), ('mkt_strong_bull', mkt_strong_bull)]:
    for score_name, score_mat in [('ai_tech', pct_mats['ai_tech_score']), ('prob_st', pct_mats['prob_up_st_cross']),
                                   ('composite_3', composite_3), ('composite_4', composite_4)]:
        for top_n in [1, 2, 3, 5]:
            daily_wr = []
            daily_rets = []
            
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
            
            if len(daily_wr) < 50:
                continue
            
            wr = np.mean(daily_wr)
            avg_ret = np.mean(daily_rets)
            total_ret = np.prod(1 + np.array(daily_rets)) - 1
            
            if wr >= 0.50:
                results.append({
                    'strategy': f'{mkt_name}_{score_name}_top{top_n}',
                    'win_rate': float(wr * 100),
                    'avg_daily_ret': float(avg_ret * 100),
                    'total_ret': float(total_ret * 100),
                    'n_days': len(daily_wr),
                    'yearly_wr': {}
                })

# === APPROACH 4: MIN-MAX CONDITION (buy best, sell worst on same day) ===
print("\nLong-short strategies...")
for score_name, score_mat in [('ai_tech', pct_mats['ai_tech_score']), ('composite_3', composite_3)]:
    for top_n in [1, 2, 3, 5]:
        daily_wr = []
        daily_rets = []
        
        for i in range(n_dates):
            scores = score_mat[i]
            rets = ret_mat[i]
            valid_mask = ~np.isnan(scores) & ~np.isnan(rets)
            if valid_mask.sum() < top_n * 2:
                continue
            
            # Long top N
            scores_masked = scores.copy()
            scores_masked[~valid_mask] = -np.inf
            top_idx = np.argpartition(-scores_masked, top_n)[:top_n]
            
            # Short bottom N
            scores_masked2 = scores.copy()
            scores_masked2[~valid_mask] = np.inf
            bot_idx = np.argpartition(scores_masked2, top_n)[:top_n]
            
            long_ret = np.nanmean(rets[top_idx])
            short_ret = -np.nanmean(rets[bot_idx])  # Short = negative return
            combined = long_ret + short_ret
            
            daily_wr.append(combined > 0)
            daily_rets.append(combined)
        
        if len(daily_wr) < 100:
            continue
        
        wr = np.mean(daily_wr)
        avg_ret = np.mean(daily_rets)
        total_ret = np.prod(1 + np.array(daily_rets)) - 1
        
        results.append({
            'strategy': f'longshort_{score_name}_top{top_n}',
            'win_rate': float(wr * 100),
            'avg_daily_ret': float(avg_ret * 100),
            'total_ret': float(total_ret * 100),
            'n_days': len(daily_wr),
            'yearly_wr': {}
        })

# Sort and save
results.sort(key=lambda x: x['win_rate'], reverse=True)

with open('strategy_results/phase3b_results.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"\nTotal results: {len(results)} ({time.time()-t0:.1f}s)")
print(f"\nTop 40 by win rate:")
print(f"{'#':<4} {'Strategy':<50} {'N':>6} {'WR%':>6} {'AvgRet%':>8} {'TotRet%':>10}")
print("-" * 95)
for i, r in enumerate(results[:40]):
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"{i+1:<4} {r['strategy']:<50} {r['n_days']:>6} {r['win_rate']:>6.1f} {r['avg_daily_ret']:>8.4f} {r.get('total_ret', 0):>10.1f}")
    if yr_str:
        print(f"     {yr_str}")

high_wr = [r for r in results if r['win_rate'] >= 90]
print(f"\n{'='*80}")
print(f"90%+ WIN RATE STRATEGIES: {len(high_wr)}")
print(f"{'='*80}")
for r in high_wr[:20]:
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"  {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, AvgRet={r['avg_daily_ret']:.4f}%, Total={r.get('total_ret', 0):.1f}%")
    print(f"    {yr_str}")
