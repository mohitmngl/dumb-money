"""Phase 8: Push to 90%+ - combine recovery + extreme conditions."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 8: PUSHING TO 90%+")
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
             'atr_streak', 'volume', 'price', 'atr_value', 'accel_a', 'accel_base']
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

# Market features
mkt_mean = np.nanmean(ret_mat, axis=1)
mkt_breadth = (ret_mat > 0).mean(axis=1)
mkt_mean_5d = pd.Series(mkt_mean).rolling(5).mean().values
mkt_mean_20d = pd.Series(mkt_mean).rolling(20).mean().values
mkt_std_20d = pd.Series(mkt_mean).rolling(20).std().values

# Stock rolling
ret_5d = np.full_like(ret_mat, np.nan)
for j in range(n_str):
    ret_5d[:, j] = pd.Series(ret_mat[:, j]).rolling(5).sum().values

print(f"Loaded ({time.time()-t0:.1f}s)")

results = []

# ============================================================
# EXTREME RECOVERY: Stock dropped >5% AND market conditions perfect
# ============================================================
print("\nEXTREME RECOVERY STRATEGIES...")

beaten_5 = feat_mats['change_pct'] < -5
beaten_3 = feat_mats['change_pct'] < -3
beaten_10 = feat_mats['change_pct'] < -10

mkt_up = mkt_mean > 0.002
mkt_up_5d = mkt_mean_5d > 0
mkt_bull = mkt_breadth > 0.55
mkt_golden = mkt_up_5d & (mkt_mean_20d > 0) & mkt_bull

# Very specific stock quality filters
ai_gte_75 = pct['ai_tech_score'] >= 0.75
ai_gte_80 = pct['ai_tech_score'] >= 0.80
ai_gte_85 = pct['ai_tech_score'] >= 0.85
ai_gte_90 = pct['ai_tech_score'] >= 0.90
ai_gte_95 = pct['ai_tech_score'] >= 0.95

prob_gte_75 = pct['prob_up_st_cross'] >= 0.75
prob_gte_80 = pct['prob_up_st_cross'] >= 0.80
prob_gte_85 = pct['prob_up_st_cross'] >= 0.85
prob_gte_90 = pct['prob_up_st_cross'] >= 0.90
prob_gte_95 = pct['prob_up_st_cross'] >= 0.95

wa_gte_60 = pct['weighted_alpha'] >= 0.60
wa_gte_70 = pct['weighted_alpha'] >= 0.70
wa_gte_80 = pct['weighted_alpha'] >= 0.80

# Try all combos of: beaten threshold x AI threshold x prob threshold x market condition x optional extra
combos = [
    # (beaten_mask, ai_mask, prob_mask, mkt_mask, name)
    (beaten_5, ai_gte_85, prob_gte_90, mkt_up_5d, 'chg-5_ai85_prob90_mup5d'),
    (beaten_5, ai_gte_80, prob_gte_90, mkt_up_5d, 'chg-5_ai80_prob90_mup5d'),
    (beaten_5, ai_gte_85, prob_gte_90, mkt_golden, 'chg-5_ai85_prob90_golden'),
    (beaten_5, ai_gte_80, prob_gte_90, mkt_golden, 'chg-5_ai80_prob90_golden'),
    (beaten_5, ai_gte_90, prob_gte_90, mkt_up_5d, 'chg-5_ai90_prob90_mup5d'),
    (beaten_5, ai_gte_90, prob_gte_90, mkt_golden, 'chg-5_ai90_prob90_golden'),
    (beaten_5, ai_gte_95, prob_gte_90, mkt_up_5d, 'chg-5_ai95_prob90_mup5d'),
    (beaten_5, ai_gte_85, prob_gte_85, mkt_up_5d, 'chg-5_ai85_prob85_mup5d'),
    (beaten_5, ai_gte_85, prob_gte_85, mkt_golden, 'chg-5_ai85_prob85_golden'),
    (beaten_5, ai_gte_90, prob_gte_85, mkt_up_5d, 'chg-5_ai90_prob85_mup5d'),
    (beaten_5, ai_gte_85, prob_gte_90, mkt_up_5d & mkt_bull, 'chg-5_ai85_prob90_mup5d_bull'),
    (beaten_5, ai_gte_80, prob_gte_90, mkt_up_5d & mkt_bull, 'chg-5_ai80_prob90_mup5d_bull'),
    (beaten_3, ai_gte_85, prob_gte_90, mkt_up_5d, 'chg-3_ai85_prob90_mup5d'),
    (beaten_3, ai_gte_85, prob_gte_90, mkt_golden, 'chg-3_ai85_prob90_golden'),
    (beaten_10, ai_gte_85, prob_gte_90, mkt_up_5d, 'chg-10_ai85_prob90_mup5d'),
    (beaten_10, ai_gte_80, prob_gte_90, mkt_up_5d, 'chg-10_ai80_prob90_mup5d'),
    # Add extra conditions
    (beaten_5, ai_gte_85, prob_gte_90, mkt_up_5d[:, np.newaxis] & wa_gte_60, 'chg-5_ai85_prob90_mup5d_wa60'),
    (beaten_5, ai_gte_85, prob_gte_90, mkt_up_5d[:, np.newaxis] & wa_gte_70, 'chg-5_ai85_prob90_mup5d_wa70'),
    (beaten_5, ai_gte_85, prob_gte_90, mkt_golden[:, np.newaxis] & wa_gte_60, 'chg-5_ai85_prob90_golden_wa60'),
    (beaten_5, ai_gte_85, prob_gte_90, mkt_up_5d[:, np.newaxis] & (feat_mats['atr_signal'] > 0), 'chg-5_ai85_prob90_mup5d_atr+'),
    (beaten_5, ai_gte_85, prob_gte_90, mkt_up_5d[:, np.newaxis] & (feat_mats['atr_streak'] >= 3), 'chg-5_ai85_prob90_mup5d_atrs3'),
    (beaten_5, ai_gte_85, prob_gte_90, mkt_up_5d[:, np.newaxis] & (feat_mats['streak'] >= 0), 'chg-5_ai85_prob90_mup5d_str0'),
    (beaten_5, ai_gte_85, prob_gte_90, mkt_golden[:, np.newaxis] & (feat_mats['atr_signal'] > 0), 'chg-5_ai85_prob90_golden_atr+'),
]

for beaten_mask, ai_mask, prob_mask, mkt_mask, name in combos:
    # mkt_mask can be 1D (dates,) or 2D (dates, stocks)
    if mkt_mask.ndim == 1:
        combined = mkt_mask[:, np.newaxis] & beaten_mask & ai_mask & prob_mask
    else:
        combined = mkt_mask & beaten_mask & ai_mask & prob_mask
    subset_rets = ret_mat[combined]
    valid_rets = subset_rets[~np.isnan(subset_rets)]
    n = len(valid_rets)
    if n < 15:
        continue
    
    wr = (valid_rets > 0).mean()
    avg_ret = valid_rets.mean()
    
    # Year breakdown
    yearly_wr = {}
    # Need to compute per-date
    for i in range(n_dates):
        date_mask = combined[i]
        date_rets = ret_mat[i, date_mask]
        date_valid = date_rets[~np.isnan(date_rets)]
        if len(date_valid) == 0:
            continue
        yr = all_dates[i].year
        if yr not in yearly_wr:
            yearly_wr[yr] = {'wins': 0, 'total': 0}
        yearly_wr[yr]['wins'] += (date_valid > 0).sum()
        yearly_wr[yr]['total'] += len(date_valid)
    
    yearly_wr_pct = {yr: float(v['wins']/v['total']*100) for yr, v in yearly_wr.items() if v['total'] >= 5}
    
    results.append({
        'strategy': f'recovery_{name}',
        'win_rate': float(wr * 100),
        'avg_daily_ret': float(avg_ret * 100),
        'total_ret': 0,
        'n_days': n,
        'yearly_wr': yearly_wr_pct
    })

# ============================================================
# ALSO TRY: When ALL conditions aligned (stock-level)
# ============================================================
print("\nALL-CONDITION ALIGNMENT...")

# For each stock-date, how many bullish conditions?
bull_count = (
    (pct['ai_tech_score'] >= 0.8).astype(float) +
    (pct['prob_up_st_cross'] >= 0.8).astype(float) +
    (pct['weighted_alpha'] >= 0.7).astype(float) +
    (pct['atr_signal'] > 0).astype(float) +
    (feat_mats['streak'] >= 3).astype(float) +
    (feat_mats['atr_streak'] >= 2).astype(float)
)

for min_bull in [5, 6]:
    for mkt_name, mkt_mask in [
        ('mkt_up', mkt_up),
        ('mkt_up_5d', mkt_up_5d),
        ('mkt_golden', mkt_golden),
    ]:
        qualified = bull_count >= min_bull
        combined = mkt_mask[:, np.newaxis] & qualified
        subset_rets = ret_mat[combined]
        valid_rets = subset_rets[~np.isnan(subset_rets)]
        n = len(valid_rets)
        if n < 15:
            continue
        
        wr = (valid_rets > 0).mean()
        avg_ret = valid_rets.mean()
        
        results.append({
            'strategy': f'bull{min_bull}_{mkt_name}',
            'win_rate': float(wr * 100),
            'avg_daily_ret': float(avg_ret * 100),
            'total_ret': 0,
            'n_days': n,
            'yearly_wr': {}
        })

# Sort
results.sort(key=lambda x: (x['win_rate'], x['n_days']), reverse=True)
seen = set()
unique = []
for r in results:
    if r['strategy'] not in seen:
        seen.add(r['strategy'])
        unique.append(r)
results = unique

with open('strategy_results/phase8_results.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"\nTotal: {len(results)} ({time.time()-t0:.1f}s)")

# Print 85%+ WR
print(f"\n{'='*80}")
print("85%+ WIN RATE STRATEGIES:")
print(f"{'='*80}")
for r in [r for r in results if r['win_rate'] >= 85]:
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"  {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")
    if yr_str:
        print(f"    Years: {yr_str}")

print(f"\n{'='*80}")
print("TOP 30:")
print(f"{'='*80}")
for i, r in enumerate(results[:30]):
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r.get('yearly_wr', {}).items())])
    print(f"{i+1}. {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")
    if yr_str:
        print(f"   {yr_str}")
