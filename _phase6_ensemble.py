"""Phase 6: Ensemble voting + multi-day patterns for 90%+ WR."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 6: ENSEMBLE + MULTI-DAY PATTERNS")
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

# Percentile ranks
pct_mats = {}
for f in feat_cols:
    mat = feat_mats[f]
    ranked = np.zeros_like(mat)
    for i in range(n_dates):
        row = mat[i]
        vm = ~np.isnan(row)
        if vm.sum() > 0:
            order = np.argsort(np.argsort(row[vm]))
            ranked[i, vm] = order / max(vm.sum() - 1, 1)
    pct_mats[f] = ranked

# Market stats
mkt_mean = np.nanmean(ret_mat, axis=1)
mkt_breadth = (ret_mat > 0).mean(axis=1)
mkt_mean_5d = pd.Series(mkt_mean).rolling(5).mean().values
mkt_mean_20d = pd.Series(mkt_mean).rolling(20).mean().values

# Ret 5d for each stock
ret_5d = np.full_like(ret_mat, np.nan)
for j in range(n_str):
    ret_5d[:, j] = pd.Series(ret_mat[:, j]).rolling(5).sum().values

# Previous day return (market)
mkt_prev_ret = np.roll(mkt_mean, 1)
mkt_prev_ret[0] = np.nan

print(f"Loaded ({time.time()-t0:.1f}s)")

results = []

# ============================================================
# ENSEMBLE VOTING: Multiple independent signals must agree
# ============================================================
print("\nENSEMBLE VOTING...")

# Define signal generators
def signal_ai_high(pct, thr): return pct >= thr
def signal_prob_high(pct, thr): return pct >= thr
def signal_wa_high(pct, thr): return pct >= thr
def signal_streak_up(pct, thr): return pct >= thr
def signal_low_vol(pct, thr): return pct <= thr

# Generate multiple independent signals
signals = {}
for thr in [0.7, 0.8, 0.85, 0.9, 0.95]:
    signals[f'ai{int(thr*100)}'] = signal_ai_high(pct_mats['ai_tech_score'], thr)
    signals[f'prob{int(thr*100)}'] = signal_prob_high(pct_mats['prob_up_st_cross'], thr)
    signals[f'wa{int(thr*100)}'] = signal_wa_high(pct_mats['weighted_alpha'], thr)
    signals[f'strk{int(thr*100)}'] = signal_streak_up(pct_mats['streak'], thr)
    signals[f'lowvol{int(thr*100)}'] = signal_low_vol(pct_mats['atrp'], thr)

# Ensemble: require N of M signals
signal_names = list(signals.keys())
n_sigs = len(signal_names)

for min_agree in [2, 3, 4, 5, 6]:
    for subset_size in [3, 4, 5]:
        # Try all combinations of subset_size signals
        from itertools import combinations
        combos = list(combinations(range(n_sigs), subset_size))
        
        for combo_indices in combos[:50]:  # Limit combos
            combo_names = [signal_names[i] for i in combo_indices]
            
            # For each date, count how many of these signals are true for each stock
            daily_wr = []
            daily_rets = []
            
            for i in range(n_dates):
                # For each stock, count agreeing signals
                agree_counts = np.zeros(n_str)
                for idx in combo_indices:
                    sig = signals[signal_names[idx]][i]
                    agree_counts += sig.astype(float)
                
                # Select stocks where min_agree signals agree
                qualified = agree_counts >= min_agree
                rets = ret_mat[i]
                valid_mask = qualified & ~np.isnan(rets)
                
                if valid_mask.sum() < 1:
                    continue
                
                top_rets = rets[valid_mask]
                all_pos = (top_rets > 0).all()
                daily_wr.append(all_pos)
                daily_rets.append(top_rets.mean())
            
            if len(daily_wr) < 50:
                continue
            
            wr = np.mean(daily_wr)
            if wr >= 0.55:
                avg_ret = np.mean(daily_rets)
                total_ret = np.prod(1 + np.array(daily_rets)) - 1
                results.append({
                    'strategy': f'ensemble_{min_agree}of{subset_size}_{"+".join(combo_names[:3])}',
                    'win_rate': float(wr * 100),
                    'avg_daily_ret': float(avg_ret * 100),
                    'total_ret': float(total_ret * 100),
                    'n_days': len(daily_wr),
                    'yearly_wr': {}
                })

# ============================================================
# MULTI-DAY PATTERN: What happened yesterday/last 5 days
# ============================================================
print("\nMULTI-DAY PATTERNS...")

# Strategy: if market went up yesterday AND stock has positive 5d momentum
for mkt_yest_thr in [0, 0.002, 0.005]:
    for stock_5d_thr in [0, 0.01, 0.02, 0.05]:
        for ai_thr in [0.8, 0.85, 0.9]:
            mkt_yest_up = mkt_mean > mkt_yest_thr
            stock_5d_up = ret_5d > stock_5d_thr
            ai_high = pct_mats['ai_tech_score'] >= ai_thr
            
            for mkt_5d in [True, False]:
                if mkt_5d:
                    mkt_cond = mkt_yest_up & (mkt_mean_5d > 0)
                else:
                    mkt_cond = mkt_yest_up
                
                combined = mkt_cond[:, np.newaxis] & stock_5d_up & ai_high
                subset_rets = ret_mat[combined]
                valid_rets = subset_rets[~np.isnan(subset_rets)]
                n = len(valid_rets)
                if n < 30:
                    continue
                
                wr = (valid_rets > 0).mean()
                avg_ret = valid_rets.mean()
                
                if wr >= 0.55:
                    results.append({
                        'strategy': f'multi_mkt{mkt_yest_thr:.3f}_5d{stock_5d_thr:.2f}_ai{int(ai_thr*100)}_mkt5d{mkt_5d}',
                        'win_rate': float(wr * 100),
                        'avg_daily_ret': float(avg_ret * 100),
                        'total_ret': 0,
                        'n_days': n,
                        'yearly_wr': {}
                    })

# ============================================================
# VERY RARE CONDITIONS: Extremely specific
# ============================================================
print("\nVERY RARE CONDITIONS...")

# Find conditions where n_days is small but WR is very high
ai95 = pct_mats['ai_tech_score'] >= 0.95
prob95 = pct_mats['prob_up_st_cross'] >= 0.95
ai90 = pct_mats['ai_tech_score'] >= 0.9
prob90 = pct_mats['prob_up_st_cross'] >= 0.9
str90 = pct_mats['streak'] >= 0.9
ai85 = pct_mats['ai_tech_score'] >= 0.85
prob85 = pct_mats['prob_up_st_cross'] >= 0.85

mkt_std = np.nanstd(ret_mat, axis=1)
mkt_std_30pct = np.nanpercentile(mkt_std, 30)
low_vol_mkt = mkt_std < mkt_std_30pct

rare_conditions = [
    ('mega_bull_extreme_ai', (mkt_mean > 0.01)[:, np.newaxis] & (mkt_breadth > 0.65)[:, np.newaxis] & ai95 & prob95),
    ('mega_bull_streak_ai', (mkt_mean > 0.01)[:, np.newaxis] & ai95 & str90),
    ('extreme_breadth_ai_prob', (mkt_breadth > 0.65)[:, np.newaxis] & ai90 & prob90),
    ('golden_perfect_ai', (mkt_mean_5d > 0.002)[:, np.newaxis] & (mkt_mean_20d > 0.001)[:, np.newaxis] & (mkt_breadth > 0.55)[:, np.newaxis] & ai90),
    ('low_vol_bull_ai_prob', (mkt_mean_5d > 0)[:, np.newaxis] & low_vol_mkt[:, np.newaxis] & ai85 & prob85),
]

for name, mask in rare_conditions:
    subset_rets = ret_mat[mask]
    valid_rets = subset_rets[~np.isnan(subset_rets)]
    n = len(valid_rets)
    if n < 5:
        continue
    
    wr = (valid_rets > 0).mean()
    avg_ret = valid_rets.mean()
    
    results.append({
        'strategy': f'rare_{name}',
        'win_rate': float(wr * 100),
        'avg_daily_ret': float(avg_ret * 100),
        'total_ret': 0,
        'n_days': n,
        'yearly_wr': {}
    })

# ============================================================
# PER-STOCK ENSEMBLE: Stock must have X signals
# ============================================================
print("\nPER-STOCK ENSEMBLE...")

# For each stock on each day, compute how many signals are bullish
ai_sig = (pct_mats['ai_tech_score'] >= 0.85).astype(float)
prob_sig = (pct_mats['prob_up_st_cross'] >= 0.85).astype(float)
wa_sig = (pct_mats['weighted_alpha'] >= 0.7).astype(float)
streak_sig = (pct_mats['streak'] >= 0.7).astype(float)
lowvol_sig = (pct_mats['atrp'] <= 0.3).astype(float)

bull_signals = ai_sig + prob_sig + wa_sig + streak_sig + lowvol_sig

for min_bull in [3, 4, 5]:
    for mkt_name, mkt_mask in [
        ('any', np.ones(n_dates, dtype=bool)),
        ('bull_5d', mkt_mean_5d > 0),
        ('high_breadth', mkt_breadth > 0.55),
        ('massive_bull', mkt_mean > 0.005),
    ]:
        qualified = bull_signals >= min_bull
        combined = mkt_mask[:, np.newaxis] & qualified
        subset_rets = ret_mat[combined]
        valid_rets = subset_rets[~np.isnan(subset_rets)]
        n = len(valid_rets)
        if n < 20:
            continue
        
        wr = (valid_rets > 0).mean()
        avg_ret = valid_rets.mean()
        
        if wr >= 0.55:
            results.append({
                'strategy': f'ensemble_{min_bull}of5_{mkt_name}',
                'win_rate': float(wr * 100),
                'avg_daily_ret': float(avg_ret * 100),
                'total_ret': 0,
                'n_days': n,
                'yearly_wr': {}
            })

# Sort and save
results.sort(key=lambda x: (x['win_rate'], x['n_days']), reverse=True)
# Deduplicate
seen = set()
unique_results = []
for r in results:
    key = r['strategy']
    if key not in seen:
        seen.add(key)
        unique_results.append(r)
results = unique_results

with open('strategy_results/phase6_results.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"\nTotal unique results: {len(results)} ({time.time()-t0:.1f}s)")

high_wr = [r for r in results if r['win_rate'] >= 90]
print(f"\n{'='*80}")
print(f"90%+ WIN RATE: {len(high_wr)}")
print(f"{'='*80}")
for r in sorted(high_wr, key=lambda x: (-x['win_rate'], -x['n_days'])):
    print(f"  {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")

print(f"\nTOP 30:")
for i, r in enumerate(results[:30]):
    print(f"{i+1}. {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")
