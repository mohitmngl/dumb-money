"""Phase 2: Exhaustive search for 90%+ win rate BTST conditions."""
import pandas as pd
import numpy as np
import time, warnings, json
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 2: EXHAUSTIVE SEARCH FOR 90%+ WIN RATE CONDITIONS")
print("=" * 80)
t0 = time.time()

df = pd.read_parquet('strategy_results/us_liquid_stocks.parquet')
df['date'] = pd.to_datetime(df['date'])
df['ret_1d'] = df['next_day_return'] / 100.0
print(f"Loaded: {df['symbol'].nunique()} stocks, {df['date'].nunique()} dates")

# Create all possible filter conditions
# Each condition is a boolean mask on the data
conditions = {}

# === SINGLE FEATURE CONDITIONS ===

# Streak conditions
for n in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
    conditions[f'streak_gte_{n}'] = df['streak'] >= n
    conditions[f'streak_lte_{-n}'] = df['streak'] <= -n

# ATRP conditions (low vol = more stable)
for thr in [1, 2, 3, 4, 5, 8, 10, 15, 20]:
    conditions[f'atrp_lte_{thr}'] = df['atrp'] <= thr
    conditions[f'atrp_gte_{thr}'] = df['atrp'] >= thr

# AI scores
for thr in [60, 70, 75, 80, 85, 90, 95]:
    conditions[f'ai_tech_gte_{thr}'] = df['ai_tech_score'] >= thr
    conditions[f'ai_overall_gte_{thr}'] = df['ai_overall_score'] >= thr
    conditions[f'ai_tech_lte_{thr}'] = df['ai_tech_score'] <= (100 - thr)

# Prob up ST cross
for thr in [55, 60, 65, 70, 75, 80, 85, 90]:
    conditions[f'prob_st_gte_{thr}'] = df['prob_up_st_cross'] >= thr
    conditions[f'prob_st_lte_{thr}'] = df['prob_up_st_cross'] <= (100 - thr)

# Change pct
for thr in [-5, -3, -2, -1, 0, 1, 2, 3, 5]:
    conditions[f'change_gte_{thr}'] = df['change_pct'] >= thr
    conditions[f'change_lte_{thr}'] = df['change_pct'] <= thr

# Volume conditions
for thr in [0.5, 1, 2, 3, 5]:
    conditions[f'vol_ratio_gte_{thr}'] = df['volume'] >= thr * df['volume'].rolling(20).mean()

# Weighted alpha
for thr in [20, 30, 40, 50, 60, 70, 80]:
    conditions[f'wa_gte_{thr}'] = df['weighted_alpha'] >= thr
    conditions[f'wa_lte_{thr}'] = df['weighted_alpha'] <= -thr

# ATR signal
conditions['atr_signal_pos'] = df['atr_signal'] > 0
conditions['atr_signal_neg'] = df['atr_signal'] < 0

# Accel signal
conditions['accel_signal_pos'] = df['accel_signal'] > 0
conditions['accel_signal_neg'] = df['accel_signal'] < 0
conditions['accel_crossed_up'] = df['accel_crossed_up'] > 0

# ATR streak
for n in [1, 2, 3, 5]:
    conditions[f'atr_streak_gte_{n}'] = df['atr_streak'] >= n

# === COMPOUND CONDITIONS ===
# Combine streak with other features
for streak_n in [3, 5, 7]:
    for ai_thr in [70, 80, 90]:
        conditions[f'streak{streak_n}_ai{ai_thr}'] = (df['streak'] >= streak_n) & (df['ai_tech_score'] >= ai_thr)
    for prob_thr in [70, 80, 90]:
        conditions[f'streak{streak_n}_prob{prob_thr}'] = (df['streak'] >= streak_n) & (df['prob_up_st_cross'] >= prob_thr)
    for atrp_thr in [3, 5, 8]:
        conditions[f'streak{streak_n}_atrp{atrp_thr}'] = (df['streak'] >= streak_n) & (df['atrp'] <= atrp_thr)

# High AI + low ATRP
for ai_thr in [80, 90]:
    for atrp_thr in [3, 5]:
        conditions[f'ai{ai_thr}_atrp{atrp_thr}'] = (df['ai_tech_score'] >= ai_thr) & (df['atrp'] <= atrp_thr)

# High prob + low ATRP
for prob_thr in [80, 90]:
    for atrp_thr in [3, 5]:
        conditions[f'prob{prob_thr}_atrp{atrp_thr}'] = (df['prob_up_st_cross'] >= prob_thr) & (df['atrp'] <= atrp_thr)

# Triple conditions
for streak_n in [3, 5]:
    for ai_thr in [80]:
        for prob_thr in [80]:
            conditions[f'streak{streak_n}_ai{ai_thr}_prob{prob_thr}'] = (df['streak'] >= streak_n) & (df['ai_tech_score'] >= ai_thr) & (df['prob_up_st_cross'] >= prob_thr)

print(f"Testing {len(conditions)} conditions...")

# Test each condition
results = []
for name, mask in conditions.items():
    subset = df[mask]
    n = len(subset)
    if n < 100:
        continue
    
    wr = (subset['ret_1d'] > 0).mean()
    avg_ret = subset['ret_1d'].mean()
    median_ret = subset['ret_1d'].median()
    
    # Year-by-year win rate
    yearly_wr = {}
    for yr in range(2020, 2027):
        yr_data = subset[subset['date'].dt.year == yr]
        if len(yr_data) > 20:
            yearly_wr[yr] = float((yr_data['ret_1d'] > 0).mean() * 100)
    
    results.append({
        'condition': name,
        'n_trades': n,
        'win_rate': float(wr * 100),
        'avg_ret': float(avg_ret * 100),
        'median_ret': float(median_ret * 100),
        'yearly_wr': yearly_wr
    })

results.sort(key=lambda x: x['win_rate'], reverse=True)

# Save all results
with open('strategy_results/winrate_analysis.json', 'w') as f:
    json.dump(results[:500], f, indent=2)

print(f"\nTested {len(results)} conditions ({time.time()-t0:.1f}s)")
print(f"\nTop 50 conditions by win rate:")
print(f"{'#':<4} {'Condition':<35} {'N':>6} {'WR%':>6} {'AvgRet%':>8} {'Median%':>8}")
print("-" * 80)
for i, r in enumerate(results[:50]):
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r['yearly_wr'].items()) if v > 0])
    print(f"{i+1:<4} {r['condition']:<35} {r['n_trades']:>6} {r['win_rate']:>6.1f} {r['avg_ret']:>8.4f} {r['median_ret']:>8.4f}")
    if yr_str:
        print(f"     Years: {yr_str}")

# Filter for 90%+ win rate
high_wr = [r for r in results if r['win_rate'] >= 90 and r['n_trades'] >= 50]
print(f"\n{'='*80}")
print(f"CONDITIONS WITH 90%+ WIN RATE (at least 50 trades): {len(high_wr)}")
print(f"{'='*80}")
for r in high_wr:
    yr_str = " ".join([f"{k}:{v:.0f}%" for k,v in sorted(r['yearly_wr'].items())])
    print(f"  {r['condition']}: WR={r['win_rate']:.1f}%, N={r['n_trades']}, AvgRet={r['avg_ret']:.4f}%")
    print(f"    Years: {yr_str}")
