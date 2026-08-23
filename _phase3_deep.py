"""Phase 3: Deep multi-factor percentile stacking for 90%+ WR."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 3: DEEP MULTI-FACTOR STACKING")
print("=" * 80)
t0 = time.time()

df = pd.read_parquet('strategy_results/us_liquid_stocks.parquet')
df['date'] = pd.to_datetime(df['date'])
df['ret_1d'] = df['next_day_return'] / 100.0
n_str = df['symbol'].nunique()
n_dates = df['date'].nunique()
print(f"Loaded: {n_str} stocks, {n_dates} dates")

# Compute cross-sectional percentiles for each date
print("Computing cross-sectional percentiles...")
for col in ['ai_tech_score', 'ai_overall_score', 'prob_up_st_cross', 'weighted_alpha',
            'atrp', 'streak', 'change_pct', 'atr_streak', 'volume', 'confluence']:
    if col in df.columns:
        df[f'pct_{col}'] = df.groupby('date')[col].rank(pct=True)

# Compute rolling features
print("Computing rolling features...")
groups = df.groupby('symbol')
df['ret_5d'] = groups['ret_1d'].transform(lambda x: x.rolling(5).sum())
df['ret_10d'] = groups['ret_1d'].transform(lambda x: x.rolling(10).sum())
df['ret_20d'] = groups['ret_1d'].transform(lambda x: x.rolling(20).sum())
df['vol_20d'] = groups['ret_1d'].transform(lambda x: x.rolling(20).std())
df['vol_ratio'] = df['volume'] / groups['volume'].transform(lambda x: x.rolling(20).mean())
df['price_vs_20d'] = df['price'] / groups['price'].transform(lambda x: x.rolling(20).mean()) - 1

# Market-wide features (aggregate across all stocks per date)
print("Computing market features...")
mkt = df.groupby('date').agg(
    mkt_ret=('ret_1d', 'mean'),
    mkt_breadth=('ret_1d', lambda x: (x > 0).mean()),
    mkt_vol=('ret_1d', 'std'),
    n_up=('ret_1d', lambda x: (x > 0).sum()),
    n_down=('ret_1d', lambda x: (x <= 0).sum())
).reset_index()
df = df.merge(mkt, on='date', how='left')

# Stock-specific features
df['momentum_rank'] = df.groupby('date')['weighted_alpha'].rank(pct=True)
df['quality_rank'] = df.groupby('date')['ai_tech_score'].rank(pct=True)
df['risk_rank'] = df.groupby('date')['atrp'].rank(pct=True, ascending=False)
df['composite_score'] = (df['momentum_rank'] + df['quality_rank'] + df['risk_rank']) / 3

print(f"Features computed ({time.time()-t0:.1f}s)")

# Strategy 1: Multi-factor percentile stacking
print("\n" + "=" * 80)
print("STRATEGY 1: MULTI-FACTOR PERCENTILE STACKING")
print("=" * 80)

# Try all combinations of 2-5 factors with percentile thresholds
factors = {
    'pct_ai_tech': ('pct_ai_tech_score', 'gt'),
    'pct_ai_overall': ('pct_ai_overall_score', 'gt'),
    'pct_prob_st': ('pct_prob_up_st_cross', 'gt'),
    'pct_wa': ('pct_weighted_alpha', 'gt'),
    'pct_atrp': ('pct_atrp', 'lt'),  # Lower ATRP = less volatile
    'pct_streak': ('pct_streak', 'gt'),
    'pct_change': ('pct_change_pct', 'gt'),
    'pct_volume': ('pct_volume', 'gt'),
    'pct_confluence': ('pct_confluence', 'gt'),
    'pct_mkt_breadth': ('mkt_breadth', 'gt'),
}

# Strategy 2: Top-N stock selection with feature stacking
print("\n" + "=" * 80)
print("STRATEGY 2: TOP-N SELECTION WITH COMPOSITE SCORING")
print("=" * 80)

results = []
tested = 0

# For each day, pick top N stocks by composite score and check if ALL are positive
for top_n in [1, 2, 3, 5, 7, 10]:
    for min_score in [0.5, 0.6, 0.7, 0.8, 0.9]:
        # Composite score conditions
        daily_wr = []
        daily_rets = []
        dates_used = []
        
        for date in df['date'].unique():
            day_data = df[df['date'] == date]
            if len(day_data) < top_n * 2:
                continue
            
            # Filter by minimum composite score
            qualified = day_data[day_data['composite_score'] >= min_score]
            if len(qualified) < top_n:
                continue
            
            # Pick top N
            top = qualified.nlargest(top_n, 'composite_score')
            top_rets = top['ret_1d'].values
            
            # Win = ALL top N stocks are positive
            all_positive = (top_rets > 0).all()
            avg_ret = top_rets.mean()
            
            daily_wr.append(all_positive)
            daily_rets.append(avg_ret)
            dates_used.append(date)
        
        if len(daily_wr) < 100:
            continue
        
        wr = np.mean(daily_wr)
        avg_daily_ret = np.mean(daily_rets)
        
        # Year-by-year
        yearly_wr = {}
        yearly_ret = {}
        for yr in range(2020, 2027):
            yr_mask = [d.year == yr for d in dates_used]
            yr_wr = np.mean([daily_wr[i] for i in range(len(daily_wr)) if yr_mask[i]])
            yr_ret = np.mean([daily_rets[i] for i in range(len(daily_rets)) if yr_mask[i]])
            if sum(yr_mask) > 20:
                yearly_wr[yr] = float(yr_wr * 100)
                yearly_ret[yr] = float(yr_ret * 100)
        
        results.append({
            'strategy': f'composite_top{top_n}_min{min_score}',
            'top_n': top_n,
            'min_score': min_score,
            'n_days': len(daily_wr),
            'win_rate': float(wr * 100),
            'avg_daily_ret': float(avg_daily_ret * 100),
            'total_ret': float((np.prod(1 + np.array(daily_rets)) - 1) * 100),
            'yearly_wr': yearly_wr,
            'yearly_ret': yearly_ret
        })
        tested += 1

# Strategy 3: Condition stacking with specific thresholds
print("\n" + "=" * 80)
print("STRATEGY 3: CONDITION STACKING WITH SPECIFIC THRESHOLDS")
print("=" * 80)

# Stack multiple conditions
stacked_conditions = [
    ('high_ai_high_prob', lambda d: (d['ai_tech_score'] >= 80) & (d['prob_up_st_cross'] >= 80)),
    ('high_ai_low_vol', lambda d: (d['ai_tech_score'] >= 85) & (d['atrp'] <= 3)),
    ('high_prob_low_vol', lambda d: (d['prob_up_st_cross'] >= 85) & (d['atrp'] <= 3)),
    ('triple_high', lambda d: (d['ai_tech_score'] >= 80) & (d['prob_up_st_cross'] >= 80) & (d['weighted_alpha'] >= 50)),
    ('momentum_quality', lambda d: (d['weighted_alpha'] >= 60) & (d['ai_tech_score'] >= 75)),
    ('extreme_quality', lambda d: (d['ai_tech_score'] >= 90) & (d['prob_up_st_cross'] >= 90)),
    ('low_vol_high_ai', lambda d: (d['atrp'] <= 2) & (d['ai_tech_score'] >= 85) & (d['prob_up_st_cross'] >= 70)),
    ('streak_momentum', lambda d: (d['streak'] >= 3) & (d['weighted_alpha'] >= 40) & (d['ai_tech_score'] >= 70)),
    ('oversold_bounce', lambda d: (d['streak'] <= -3) & (d['ai_tech_score'] >= 75) & (d['prob_up_st_cross'] >= 60)),
    ('trend_quality', lambda d: (d['atr_signal'] > 0) & (d['ai_tech_score'] >= 80) & (d['atrp'] <= 5)),
    ('quality_momentum', lambda d: (d['ai_tech_score'] >= 85) & (d['weighted_alpha'] >= 50) & (d['prob_up_st_cross'] >= 75)),
    ('ultra_quality', lambda d: (d['ai_tech_score'] >= 90) & (d['weighted_alpha'] >= 60) & (d['prob_up_st_cross'] >= 85)),
    ('streak_ai_prob', lambda d: (d['streak'] >= 2) & (d['ai_tech_score'] >= 80) & (d['prob_up_st_cross'] >= 80)),
    ('low_vol_triple', lambda d: (d['atrp'] <= 3) & (d['ai_tech_score'] >= 80) & (d['prob_up_st_cross'] >= 80)),
    ('high_everything', lambda d: (d['ai_tech_score'] >= 85) & (d['prob_up_st_cross'] >= 85) & (d['weighted_alpha'] >= 50) & (d['atrp'] <= 5)),
]

for name, cond_func in stacked_conditions:
    try:
        mask = cond_func(df)
        subset = df[mask]
        n = len(subset)
        if n < 50:
            continue
        
        wr = (subset['ret_1d'] > 0).mean()
        avg_ret = subset['ret_1d'].mean()
        
        yearly_wr = {}
        for yr in range(2020, 2027):
            yr_data = subset[subset['date'].dt.year == yr]
            if len(yr_data) > 20:
                yearly_wr[yr] = float((yr_data['ret_1d'] > 0).mean() * 100)
        
        results.append({
            'strategy': f'stacked_{name}',
            'n_trades': n,
            'win_rate': float(wr * 100),
            'avg_daily_ret': float(avg_ret * 100),
            'total_ret': 0,
            'yearly_wr': yearly_wr,
            'yearly_ret': {}
        })
    except Exception as e:
        pass

# Strategy 4: Top-N stock portfolio win rate (ALL must be positive)
print("\n" + "=" * 80)
print("STRATEGY 4: TOP-N PORTFOLIO WIN RATE")
print("=" * 80)

# For each day, pick top N by various features and check if ALL are positive
for feat in ['ai_tech_score', 'ai_overall_score', 'prob_up_st_cross', 'weighted_alpha', 'composite_score']:
    for top_n in [1, 2, 3]:
        daily_all_positive = []
        daily_avg_ret = []
        dates_used = []
        
        for date in df['date'].unique():
            day_data = df[df['date'] == date]
            if len(day_data) < top_n * 2:
                continue
            
            top = day_data.nlargest(top_n, feat)
            if len(top) < top_n:
                continue
            
            top_rets = top['ret_1d'].values
            all_pos = (top_rets > 0).all()
            
            daily_all_positive.append(all_pos)
            daily_avg_ret.append(top_rets.mean())
            dates_used.append(date)
        
        if len(daily_all_positive) < 100:
            continue
        
        wr = np.mean(daily_all_positive)
        avg_ret = np.mean(daily_avg_ret)
        
        yearly_wr = {}
        for yr in range(2020, 2027):
            yr_mask = [d.year == yr for d in dates_used]
            yr_wr_vals = [daily_all_positive[i] for i in range(len(daily_all_positive)) if yr_mask[i]]
            if len(yr_wr_vals) > 20:
                yearly_wr[yr] = float(np.mean(yr_wr_vals) * 100)
        
        results.append({
            'strategy': f'top{top_n}_{feat}_all_positive',
            'n_days': len(daily_all_positive),
            'win_rate': float(wr * 100),
            'avg_daily_ret': float(avg_ret * 100),
            'total_ret': float((np.prod(1 + np.array(daily_avg_ret)) - 1) * 100),
            'yearly_wr': yearly_wr,
            'yearly_ret': {}
        })

# Sort by win rate
results.sort(key=lambda x: x['win_rate'], reverse=True)

# Save
with open('strategy_results/phase3_results.json', 'w') as f:
    json.dump(results[:200], f, indent=2)

print(f"\nTotal strategies tested: {tested}")
print(f"\nTop 30 by win rate:")
print(f"{'#':<4} {'Strategy':<45} {'N':>6} {'WR%':>6} {'AvgRet%':>8} {'TotalRet%':>10}")
print("-" * 90)
for i, r in enumerate(results[:30]):
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"{i+1:<4} {r['strategy']:<45} {r.get('n_days', r.get('n_trades', 0)):>6} {r['win_rate']:>6.1f} {r['avg_daily_ret']:>8.4f} {r.get('total_ret', 0):>10.1f}")
    if yr_str:
        print(f"     Years: {yr_str}")

# Filter 90%+ WR
high_wr = [r for r in results if r['win_rate'] >= 90]
print(f"\n{'='*80}")
print(f"STRATEGIES WITH 90%+ WIN RATE: {len(high_wr)}")
print(f"{'='*80}")
for r in high_wr:
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"  {r['strategy']}: WR={r['win_rate']:.1f}%, N={r.get('n_days', r.get('n_trades', 0))}, AvgRet={r['avg_daily_ret']:.4f}%")
    print(f"    Years: {yr_str}")
