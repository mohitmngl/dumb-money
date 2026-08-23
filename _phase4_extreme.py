"""Phase 4: Aggressive search for 90%+ WR - strings, seasonal, market-state, gap patterns."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 4: AGGRESSIVE SEARCH FOR 90%+ WR")
print("=" * 80)
t0 = time.time()

# Load US stocks
df = pd.read_parquet('strategy_results/us_liquid_stocks.parquet')
df['date'] = pd.to_datetime(df['date'])
df['ret_1d'] = df['next_day_return'] / 100.0
n_str = df['symbol'].nunique()
n_dates = df['date'].nunique()

# Build matrices
all_dates = sorted(df['date'].unique())
date_idx = {d: i for i, d in enumerate(all_dates)}
syms = sorted(df['symbol'].unique())
sym_idx = {s: i for i, s in enumerate(syms)}

ret_mat = np.full((n_dates, n_str), np.nan)
feat_cols = ['ai_tech_score', 'ai_overall_score', 'prob_up_st_cross', 'weighted_alpha',
             'atrp', 'streak', 'change_pct', 'atr_signal', 'accel_signal',
             'atr_streak', 'volume', 'price', 'atr_value', 'atr_multiplier']
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

print(f"Loaded: {n_str} stocks, {n_dates} dates ({time.time()-t0:.1f}s)")

# Compute market-wide stats per date
print("Computing market-wide stats...")
mkt_mean = np.nanmean(ret_mat, axis=1)
mkt_breadth = (ret_mat > 0).mean(axis=1)
mkt_vol = np.nanstd(ret_mat, axis=1)

# Rolling market stats (5-day, 20-day)
mkt_mean_5d = pd.Series(mkt_mean).rolling(5).mean().values
mkt_mean_20d = pd.Series(mkt_mean).rolling(20).mean().values
mkt_breadth_5d = pd.Series(mkt_breadth).rolling(5).mean().values

# Compute per-stock rolling features
print("Computing per-stock rolling features...")
# ret_1d already in ret_mat
ret_5d = np.full_like(ret_mat, np.nan)
ret_10d = np.full_like(ret_mat, np.nan)
vol_20d = np.full_like(ret_mat, np.nan)
for j in range(n_str):
    col = ret_mat[:, j]
    ret_5d[:, j] = pd.Series(col).rolling(5).sum().values
    ret_10d[:, j] = pd.Series(col).rolling(10).sum().values
    vol_20d[:, j] = pd.Series(col).rolling(20).std().values

# Cross-sectional ranks
print("Computing cross-sectional ranks...")
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

print(f"Features computed ({time.time()-t0:.1f}s)")

results = []

# ============================================================
# APPROACH 1: MARKET-STATE CONDITIONAL STRATEGIES
# ============================================================
print("\n" + "=" * 60)
print("APPROACH 1: MARKET-STATE CONDITIONAL")
print("=" * 60)

# Define market states
market_states = {
    'strong_bull_5d': mkt_mean_5d > 0.002,
    'bull_5d': mkt_mean_5d > 0,
    'strong_bull_20d': mkt_mean_20d > 0.001,
    'bull_20d': mkt_mean_20d > 0,
    'high_breadth': mkt_breadth > 0.55,
    'very_high_breadth': mkt_breadth > 0.6,
    'extreme_breadth': mkt_breadth > 0.65,
    'low_vol': mkt_vol < np.nanpercentile(mkt_vol, 30),
    'high_bull_today': mkt_mean > 0.005,
    'massive_bull_today': mkt_mean > 0.01,
    'breadth_low_vol': (mkt_breadth > 0.55) & (mkt_vol < np.nanpercentile(mkt_vol, 40)),
    'bull_5d_low_vol': (mkt_mean_5d > 0) & (mkt_vol < np.nanpercentile(mkt_vol, 40)),
    'bull_20d_high_breadth': (mkt_mean_20d > 0) & (mkt_breadth > 0.55),
    'extreme_bull': (mkt_breadth > 0.6) & (mkt_mean > 0.005) & (mkt_vol < np.nanpercentile(mkt_vol, 50)),
    'golden': (mkt_mean_5d > 0) & (mkt_mean_20d > 0) & (mkt_breadth > 0.55),
    'perfect_bull': (mkt_mean > 0) & (mkt_mean_5d > 0) & (mkt_mean_20d > 0) & (mkt_breadth > 0.55),
}

for state_name, state_mask in market_states.items():
    for score_name, score_mat in [
        ('ai_tech', pct_mats['ai_tech_score']),
        ('prob_st', pct_mats['prob_up_st_cross']),
        ('ai_x_prob', pct_mats['ai_tech_score'] * pct_mats['prob_up_st_cross']),
        ('composite', (pct_mats['ai_tech_score'] + pct_mats['prob_up_st_cross'] + pct_mats['weighted_alpha']) / 3),
    ]:
        for top_n in [1, 2, 3, 5]:
            daily_wr = []
            daily_rets = []
            dates_used = []
            
            for i in range(n_dates):
                if not state_mask[i]:
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
            
            # Year breakdown
            yearly_wr = {}
            for yr in range(2020, 2027):
                yr_mask = [d.year == yr for d in dates_used]
                yr_wr = [daily_wr[j] for j in range(len(daily_wr)) if yr_mask[j]]
                if len(yr_wr) > 10:
                    yearly_wr[yr] = float(np.mean(yr_wr) * 100)
            
            if wr >= 0.60:
                results.append({
                    'strategy': f'{state_name}_{score_name}_top{top_n}',
                    'win_rate': float(wr * 100),
                    'avg_daily_ret': float(avg_ret * 100),
                    'total_ret': float(total_ret * 100),
                    'n_days': len(daily_wr),
                    'yearly_wr': yearly_wr
                })

# ============================================================
# APPROACH 2: COMPOUND MARKET + STOCK CONDITIONS
# ============================================================
print("\n" + "=" * 60)
print("APPROACH 2: COMPOUND MARKET + STOCK CONDITIONS")
print("=" * 60)

# Stack market conditions with stock conditions
for mkt_state_name, mkt_mask in market_states.items():
    for stock_filter_name, stock_mask in [
        ('ai80', pct_mats['ai_tech_score'] >= 0.8),
        ('ai85', pct_mats['ai_tech_score'] >= 0.85),
        ('ai90', pct_mats['ai_tech_score'] >= 0.9),
        ('prob80', pct_mats['prob_up_st_cross'] >= 0.8),
        ('prob85', pct_mats['prob_up_st_cross'] >= 0.85),
        ('prob90', pct_mats['prob_up_st_cross'] >= 0.9),
        ('ai80_prob80', (pct_mats['ai_tech_score'] >= 0.8) & (pct_mats['prob_up_st_cross'] >= 0.8)),
        ('ai85_prob85', (pct_mats['ai_tech_score'] >= 0.85) & (pct_mats['prob_up_st_cross'] >= 0.85)),
        ('ai90_prob90', (pct_mats['ai_tech_score'] >= 0.9) & (pct_mats['prob_up_st_cross'] >= 0.9)),
        ('ai90_prob90_wa70', (pct_mats['ai_tech_score'] >= 0.9) & (pct_mats['prob_up_st_cross'] >= 0.9) & (pct_mats['weighted_alpha'] >= 0.7)),
        ('ai90_prob90_low_atrp', (pct_mats['ai_tech_score'] >= 0.9) & (pct_mats['prob_up_st_cross'] >= 0.9) & (pct_mats['atrp'] <= 0.3)),
        ('ultra', (pct_mats['ai_tech_score'] >= 0.95) & (pct_mats['prob_up_st_cross'] >= 0.9) & (pct_mats['weighted_alpha'] >= 0.8)),
    ]:
        # Combined mask: market state AND stock condition
        combined = state_mask[:, np.newaxis] & stock_mask
        subset_rets = ret_mat[combined]
        valid_rets = subset_rets[~np.isnan(subset_rets)]
        n = len(valid_rets)
        if n < 20:
            continue
        
        wr = (valid_rets > 0).mean()
        avg_ret = valid_rets.mean()
        
        if wr >= 0.55:
            # Year breakdown
            yearly_wr = {}
            for yr in range(2020, 2027):
                yr_start = np.searchsorted(all_dates, np.datetime64(f'{yr}-01-01'))
                yr_end = np.searchsorted(all_dates, np.datetime64(f'{yr}-12-31'))
                yr_combined = combined[yr_start:yr_end]
                yr_rets = ret_mat[yr_start:yr_end][yr_combined]
                yr_valid = yr_rets[~np.isnan(yr_rets)]
                if len(yr_valid) > 10:
                    yearly_wr[yr] = float((yr_valid > 0).mean() * 100)
            
            results.append({
                'strategy': f'{mkt_state_name}+{stock_filter_name}',
                'win_rate': float(wr * 100),
                'avg_daily_ret': float(avg_ret * 100),
                'total_ret': 0,
                'n_days': n,
                'yearly_wr': yearly_wr
            })

# ============================================================
# APPROACH 3: CONSECUTIVE PATTERN STRATEGIES
# ============================================================
print("\n" + "=" * 60)
print("APPROACH 3: CONSECUTIVE PATTERN STRATEGIES")
print("=" * 60)

# Look at patterns: if stock went up N days in a row AND market is X, what happens next?
for streak_n in [3, 5, 7, 10]:
    for streak_dir in ['up', 'down']:
        if streak_dir == 'up':
            streak_mask = feat_mats['streak'] >= streak_n
        else:
            streak_mask = feat_mats['streak'] <= -streak_n
        
        for mkt_state_name, mkt_mask in [
            ('any', np.ones(n_dates, dtype=bool)),
            ('bull_5d', mkt_mean_5d > 0),
            ('bull_20d', mkt_mean_20d > 0),
            ('high_breadth', mkt_breadth > 0.55),
        ]:
            combined = mkt_mask[:, np.newaxis] & streak_mask
            subset_rets = ret_mat[combined]
            valid_rets = subset_rets[~np.isnan(subset_rets)]
            n = len(valid_rets)
            if n < 30:
                continue
            
            wr = (valid_rets > 0).mean()
            avg_ret = valid_rets.mean()
            
            if wr >= 0.55:
                results.append({
                    'strategy': f'streak_{streak_dir}{streak_n}_{mkt_state_name}',
                    'win_rate': float(wr * 100),
                    'avg_daily_ret': float(avg_ret * 100),
                    'total_ret': 0,
                    'n_days': n,
                    'yearly_wr': {}
                })

# ============================================================
# APPROACH 4: QUADRUPLE-CONDITION EXTREME FILTERING
# ============================================================
print("\n" + "=" * 60)
print("APPROACH 4: QUADRUPLE+ EXTREME FILTERING")
print("=" * 60)

# Try very aggressive multi-factor filtering
extreme_filters = [
    ('ultra_ai_prob_wa', (pct_mats['ai_tech_score'] >= 0.95) & (pct_mats['prob_up_st_cross'] >= 0.95) & (pct_mats['weighted_alpha'] >= 0.9)),
    ('ultra_ai_prob_wa_atrp', (pct_mats['ai_tech_score'] >= 0.95) & (pct_mats['prob_up_st_cross'] >= 0.95) & (pct_mats['weighted_alpha'] >= 0.9) & (pct_mats['atrp'] <= 0.2)),
    ('ultra_ai_prob_wa_streak', (pct_mats['ai_tech_score'] >= 0.95) & (pct_mats['prob_up_st_cross'] >= 0.95) & (pct_mats['weighted_alpha'] >= 0.9) & (pct_mats['streak'] >= 0.8)),
    ('ultra_all5', (pct_mats['ai_tech_score'] >= 0.95) & (pct_mats['prob_up_st_cross'] >= 0.95) & (pct_mats['weighted_alpha'] >= 0.9) & (pct_mats['atrp'] <= 0.2) & (pct_mats['streak'] >= 0.8)),
    ('ultra_mega', (pct_mats['ai_tech_score'] >= 0.98) & (pct_mats['prob_up_st_cross'] >= 0.98)),
    ('ultra_mega_wa', (pct_mats['ai_tech_score'] >= 0.98) & (pct_mats['prob_up_st_cross'] >= 0.98) & (pct_mats['weighted_alpha'] >= 0.95)),
    ('ultra_mega_wa_atrp', (pct_mats['ai_tech_score'] >= 0.98) & (pct_mats['prob_up_st_cross'] >= 0.98) & (pct_mats['weighted_alpha'] >= 0.95) & (pct_mats['atrp'] <= 0.15)),
    ('top_1pct_all4', (pct_mats['ai_tech_score'] >= 0.99) & (pct_mats['prob_up_st_cross'] >= 0.99) & (pct_mats['weighted_alpha'] >= 0.99)),
    ('top_1pct_ai_prob', (pct_mats['ai_tech_score'] >= 0.99) & (pct_mats['prob_up_st_cross'] >= 0.99)),
]

for name, mask in extreme_filters:
    for mkt_state_name, mkt_mask in [
        ('any', np.ones(n_dates, dtype=bool)),
        ('bull', mkt_mean_5d > 0),
        ('strong_bull', (mkt_mean_5d > 0) & (mkt_breadth > 0.55)),
        ('perfect', (mkt_mean > 0) & (mkt_mean_5d > 0) & (mkt_breadth > 0.55)),
    ]:
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
            'strategy': f'{name}_{mkt_state_name}',
            'win_rate': float(wr * 100),
            'avg_daily_ret': float(avg_ret * 100),
            'total_ret': 0,
            'n_days': n,
            'yearly_wr': yearly_wr
        })

# Sort and save
results.sort(key=lambda x: (x['win_rate'], x['n_days']), reverse=True)

with open('strategy_results/phase4_results.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"\nTotal results: {len(results)} ({time.time()-t0:.1f}s)")

# Print 90%+ WR
high_wr = [r for r in results if r['win_rate'] >= 90]
print(f"\n{'='*80}")
print(f"90%+ WIN RATE STRATEGIES: {len(high_wr)}")
print(f"{'='*80}")
for r in sorted(high_wr, key=lambda x: (-x['win_rate'], -x['n_days'])):
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"  {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, AvgRet={r['avg_daily_ret']:.4f}%")
    if yr_str:
        print(f"    {yr_str}")

# Print top 50 overall
print(f"\n{'='*80}")
print("TOP 50 BY WIN RATE")
print(f"{'='*80}")
for i, r in enumerate(results[:50]):
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"{i+1}. {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")
    if yr_str:
        print(f"   {yr_str}")
