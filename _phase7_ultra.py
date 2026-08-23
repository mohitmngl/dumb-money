"""Phase 7: Ultra-aggressive - rare day selection, single-stock focus, 90%+ WR hunt."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 7: ULTRA-AGGRESSIVE 90%+ WR HUNT")
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

# Market features
mkt_mean = np.nanmean(ret_mat, axis=1)
mkt_breadth = (ret_mat > 0).mean(axis=1)
mkt_median = np.nanmedian(ret_mat, axis=1)
mkt_std = np.nanstd(ret_mat, axis=1)
mkt_mean_5d = pd.Series(mkt_mean).rolling(5).mean().values
mkt_mean_20d = pd.Series(mkt_mean).rolling(20).mean().values
mkt_breadth_5d = pd.Series(mkt_breadth).rolling(5).mean().values

# Stock rolling features
ret_5d = np.full_like(ret_mat, np.nan)
ret_10d = np.full_like(ret_mat, np.nan)
vol_5d = np.full_like(ret_mat, np.nan)
for j in range(n_str):
    ret_5d[:, j] = pd.Series(ret_mat[:, j]).rolling(5).sum().values
    ret_10d[:, j] = pd.Series(ret_mat[:, j]).rolling(10).sum().values
    vol_5d[:, j] = pd.Series(ret_mat[:, j]).rolling(5).std().values

print(f"Loaded ({time.time()-t0:.1f}s)")

results = []

# ============================================================
# APPROACH A: "BAD DAY RECOVERY" - buy beaten-down stocks on upmarket days
# ============================================================
print("\nAPPROACH A: BAD DAY RECOVERY")

# On days when market is up, buy stocks that were beaten down yesterday
mkt_up_today = mkt_mean > 0.002
mkt_up_5d = mkt_mean_5d > 0
mkt_bull_breadth = mkt_breadth > 0.55

# Stocks that went DOWN yesterday (change_pct < -1, -2, -3, -5)
for chg_thr in [-1, -2, -3, -5, -10]:
    for ai_thr in [0.6, 0.7, 0.8, 0.85, 0.9]:
        for prob_thr in [0.6, 0.7, 0.8, 0.85, 0.9]:
            # Stock was beaten down BUT has good fundamentals
            beaten = feat_mats['change_pct'] < chg_thr
            good_ai = pct['ai_tech_score'] >= ai_thr
            good_prob = pct['prob_up_st_cross'] >= prob_thr
            
            for mkt_cond_name, mkt_cond in [
                ('mkt_up', mkt_up_today),
                ('mkt_up_5d', mkt_up_today & mkt_up_5d),
                ('mkt_bull', mkt_up_today & mkt_bull_breadth),
            ]:
                combined = mkt_cond[:, np.newaxis] & beaten & good_ai & good_prob
                subset_rets = ret_mat[combined]
                valid_rets = subset_rets[~np.isnan(subset_rets)]
                n = len(valid_rets)
                if n < 30:
                    continue
                
                wr = (valid_rets > 0).mean()
                avg_ret = valid_rets.mean()
                
                if wr >= 0.70:
                    results.append({
                        'strategy': f'A_recovery_chg{chg_thr}_ai{int(ai_thr*100)}_prob{int(prob_thr*100)}_{mkt_cond_name}',
                        'win_rate': float(wr * 100),
                        'avg_daily_ret': float(avg_ret * 100),
                        'total_ret': 0,
                        'n_days': n,
                        'yearly_wr': {}
                    })

# ============================================================
# APPROACH B: "MOMENTUM CONTINUATION" - very specific streak + market
# ============================================================
print("\nAPPROACH B: MOMENTUM CONTINUATION")

for streak_n in [3, 5, 7]:
    for ai_thr in [0.7, 0.8, 0.85, 0.9, 0.95]:
        for prob_thr in [0.7, 0.8, 0.85, 0.9, 0.95]:
            streak_up = feat_mats['streak'] >= streak_n
            good_ai = pct['ai_tech_score'] >= ai_thr
            good_prob = pct['prob_up_st_cross'] >= prob_thr
            
            for mkt_name, mkt_mask in [
                ('any', np.ones(n_dates, dtype=bool)),
                ('mkt_up', mkt_up_today),
                ('mkt_bull', mkt_up_today & mkt_bull_breadth),
                ('mkt_golden', mkt_up_5d & (mkt_mean_20d > 0)),
            ]:
                combined = mkt_mask[:, np.newaxis] & streak_up & good_ai & good_prob
                subset_rets = ret_mat[combined]
                valid_rets = subset_rets[~np.isnan(subset_rets)]
                n = len(valid_rets)
                if n < 30:
                    continue
                
                wr = (valid_rets > 0).mean()
                avg_ret = valid_rets.mean()
                
                if wr >= 0.70:
                    results.append({
                        'strategy': f'B_mom_str{streak_n}_ai{int(ai_thr*100)}_prob{int(prob_thr*100)}_{mkt_name}',
                        'win_rate': float(wr * 100),
                        'avg_daily_ret': float(avg_ret * 100),
                        'total_ret': 0,
                        'n_days': n,
                        'yearly_wr': {}
                    })

# ============================================================
# APPROACH C: "TOP 1 STOCK" very conditional
# ============================================================
print("\nAPPROACH C: TOP 1 STOCK VERY CONDITIONAL")

# For each day, find the SINGLE BEST stock and check if it's positive
for score_name, score_mat in [
    ('ai_x_prob', pct['ai_tech_score'] * pct['prob_up_st_cross']),
    ('ai_x_prob_x_wa', pct['ai_tech_score'] * pct['prob_up_st_cross'] * pct['weighted_alpha']),
    ('composite', (pct['ai_tech_score'] + pct['prob_up_st_cross'] + pct['weighted_alpha']) / 3),
]:
    for mkt_name, mkt_mask in [
        ('massive_bull', mkt_mean > 0.005),
        ('extreme_breadth', mkt_breadth > 0.65),
        ('mega_bull', (mkt_mean > 0.005) & (mkt_breadth > 0.6)),
        ('golden', (mkt_mean_5d > 0.002) & (mkt_breadth > 0.55)),
    ]:
        daily_wr = []
        daily_rets = []
        
        for i in range(n_dates):
            if not mkt_mask[i]:
                continue
            
            scores = score_mat[i]
            rets = ret_mat[i]
            vm = ~np.isnan(scores) & ~np.isnan(rets)
            if vm.sum() < 10:
                continue
            
            scores_masked = scores.copy()
            scores_masked[~vm] = -np.inf
            best_idx = np.argmax(scores_masked)
            best_ret = rets[best_idx]
            
            if not np.isnan(best_ret):
                daily_wr.append(best_ret > 0)
                daily_rets.append(best_ret)
        
        if len(daily_wr) < 20:
            continue
        
        wr = np.mean(daily_wr)
        avg_ret = np.mean(daily_rets)
        
        if wr >= 0.70:
            results.append({
                'strategy': f'C_top1_{score_name}_{mkt_name}',
                'win_rate': float(wr * 100),
                'avg_daily_ret': float(avg_ret * 100),
                'total_ret': float((np.prod(1 + np.array(daily_rets)) - 1) * 100),
                'n_days': len(daily_wr),
                'yearly_wr': {}
            })

# ============================================================
# APPROACH D: "CONSECUTIVE UP DAY PATTERN" - rare but very specific
# ============================================================
print("\nAPPROACH D: CONSECUTIVE UP PATTERNS")

# Check: if market was up N days in a row AND breadth was high, is tomorrow up?
for lookback in [2, 3, 5, 7, 10]:
    # Compute consecutive up days for market
    mkt_up = (mkt_mean > 0).astype(int)
    consec_up = np.zeros(n_dates)
    for i in range(n_dates):
        if mkt_up[i]:
            consec_up[i] = consec_up[i-1] + 1 if i > 0 else 1
        else:
            consec_up[i] = 0
    
    for min_consec in [2, 3, 4, 5, 7]:
        for min_breadth in [0.5, 0.55, 0.6, 0.65]:
            mkt_cond = (consec_up >= min_consec) & (mkt_breadth >= min_breadth)
            
            for stock_ai in [0.8, 0.85, 0.9, 0.95]:
                good_stock = pct['ai_tech_score'] >= stock_ai
                
                combined = mkt_cond[:, np.newaxis] & good_stock
                subset_rets = ret_mat[combined]
                valid_rets = subset_rets[~np.isnan(subset_rets)]
                n = len(valid_rets)
                if n < 20:
                    continue
                
                wr = (valid_rets > 0).mean()
                avg_ret = valid_rets.mean()
                
                if wr >= 0.70:
                    results.append({
                        'strategy': f'D_consec{min_consec}_br{int(min_breadth*100)}_ai{int(stock_ai*100)}',
                        'win_rate': float(wr * 100),
                        'avg_daily_ret': float(avg_ret * 100),
                        'total_ret': 0,
                        'n_days': n,
                        'yearly_wr': {}
                    })

# Sort and save
results.sort(key=lambda x: (x['win_rate'], x['n_days']), reverse=True)
seen = set()
unique = []
for r in results:
    if r['strategy'] not in seen:
        seen.add(r['strategy'])
        unique.append(r)
results = unique

with open('strategy_results/phase7_results.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"\nTotal unique results: {len(results)} ({time.time()-t0:.1f}s)")

# Print 80%+ WR (being realistic)
high_wr = [r for r in results if r['win_rate'] >= 80]
print(f"\n{'='*80}")
print(f"80%+ WIN RATE: {len(high_wr)}")
print(f"{'='*80}")
for r in sorted(high_wr, key=lambda x: (-x['win_rate'], -x['n_days']))[:50]:
    print(f"  {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}, Ret={r['avg_daily_ret']:.4f}%")

# Also check if 90% exists anywhere
high90 = [r for r in results if r['win_rate'] >= 90]
print(f"\n{'='*80}")
print(f"90%+ WIN RATE: {len(high90)}")
print(f"{'='*80}")
for r in high_wr[:30]:
    print(f"  {r['strategy']}: WR={r['win_rate']:.1f}%, N={r['n_days']}")
