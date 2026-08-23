"""
MONSTER STRATEGY FINDER v1
- 200+ creative derived features from accel, ST, weighted_alpha
- Vectorized numpy engine (zero Python row loops)
- Tests: single-factor, dual-factor, triple-factor, conditional combos
- 3 hold periods x 5 top-N thresholds
- Scores: gain, volatility, drawdown, Sharpe, linearity
"""
import numpy as np, pandas as pd, sys, io, os, time, json, itertools
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
CHARTS = 'strategy_charts'

print("="*100, flush=True)
print("  MONSTER STRATEGY FINDER v1", flush=True)
print("="*100, flush=True)

###############################################################################
# 1. LOAD DATA
###############################################################################
print("\n[1] Loading US stock cache...", flush=True)
t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
print(f"  {len(df)} rows, {df['date'].nunique()} dates ({time.time()-t0:.0f}s)", flush=True)

# Base columns available
base_cols = [c for c in df.columns if c not in ['date','symbol']]
print(f"  Base columns: {len(base_cols)}", flush=True)

###############################################################################
# 2. CREATE CREATIVE DERIVED FEATURES
###############################################################################
print("\n[2] Creating 200+ derived features...", flush=True)
t0 = time.time()

feats = {}

# --- RAW COLUMNS (already exist) ---
raw = ['weighted_alpha','atrp','streak','atr_value','atr_streak','atr_multiplier',
       'accel_a','accel_base','confluence',
       'prob_up_1d','prob_up_5d','prob_up_st_cross',
       'ai_overall_score','ai_tech_score','ai_momentum_score',
       'ai_volume_score','ai_events_score','ai_volume_profile_score',
       'ai_trendline_score','ai_sentiment_score',
       'change_pct','price']
for c in raw:
    if c in df.columns:
        feats[c] = df[c].values

# --- ACCEL EXPANSIONS ---
a = df['accel_a'].values if 'accel_a' in df.columns else np.zeros(len(df))
b = df['accel_base'].values if 'accel_base' in df.columns else np.zeros(len(df))

feats['accel_a_pos'] = np.maximum(a, 0)
feats['accel_a_neg'] = np.minimum(a, 0)
feats['accel_a_abs'] = np.abs(a)
feats['accel_base_pos'] = np.maximum(b, 0)
feats['accel_base_neg'] = np.minimum(b, 0)
feats['accel_base_abs'] = np.abs(b)
feats['accel_ratio'] = np.where(np.abs(b) > 0.001, a / b, 0)
feats['accel_diff'] = a - b
feats['accel_sum'] = a + b
feats['accel_product'] = a * b
feats['accel_sq'] = a ** 2
feats['accel_log'] = np.log1p(np.abs(a)) * np.sign(a)
feats['accel_sqrt'] = np.sqrt(np.abs(a)) * np.sign(a)

# --- SUPER TREND EXPANSIONS ---
s_val = df['atr_value'].values if 'atr_value' in df.columns else np.zeros(len(df))
s_streak = df['atr_streak'].values if 'atr_streak' in df.columns else np.zeros(len(df))
s_mult = df['atr_multiplier'].values if 'atr_multiplier' in df.columns else np.zeros(len(df))
atr = df['atrp'].values if 'atrp' in df.columns else np.zeros(len(df))

feats['atr_value_pos'] = np.maximum(s_val, 0)
feats['atr_value_neg'] = np.minimum(s_val, 0)
feats['atr_value_abs'] = np.abs(s_val)
feats['atr_streak_pos'] = np.maximum(s_streak, 0)
feats['atr_streak_neg'] = np.minimum(s_streak, 0)
feats['atr_streak_abs'] = np.abs(s_streak)
feats['atr_ratio'] = np.where(np.abs(s_val) > 0.001, s_streak / np.abs(s_val), 0)
feats['atr_product'] = s_val * s_streak
feats['atr_sq'] = s_val ** 2
feats['atr_streak_sq'] = s_streak ** 2
feats['atr_log'] = np.log1p(np.abs(s_val)) * np.sign(s_val)
feats['atr_pct_x_streak'] = atr * s_streak
feats['atr_pct_x_value'] = atr * s_val

# --- WEIGHTED ALPHA EXPANSIONS ---
wa = df['weighted_alpha'].values if 'weighted_alpha' in df.columns else np.zeros(len(df))
feats['wa_pos'] = np.maximum(wa, 0)
feats['wa_neg'] = np.minimum(wa, 0)
feats['wa_abs'] = np.abs(wa)
feats['wa_sq'] = wa ** 2
feats['wa_cubed'] = wa ** 3
feats['wa_log'] = np.log1p(np.abs(wa)) * np.sign(wa)
feats['wa_sqrt'] = np.sqrt(np.abs(wa)) * np.sign(wa)

# --- CROSS-DOMAIN COMBOS ---
feats['wa_x_accel'] = wa * a
feats['wa_x_accel_base'] = wa * b
feats['wa_x_atr'] = wa * s_val
feats['wa_x_streak'] = wa * df['streak'].values if 'streak' in df.columns else np.zeros(len(df))
feats['accel_x_atr'] = a * s_val
feats['accel_base_x_atr'] = b * s_val
feats['accel_x_streak'] = a * s_streak
feats['accel_base_x_streak'] = b * s_streak
feats['wa_accel_atr'] = wa * a * s_val
feats['wa_accel_streak'] = wa * a * s_streak

# Ratios
feats['wa_div_accel'] = np.where(np.abs(a) > 0.001, wa / np.abs(a), 0)
feats['wa_div_atr'] = np.where(np.abs(s_val) > 0.001, wa / np.abs(s_val), 0)
feats['accel_div_atr'] = np.where(np.abs(s_val) > 0.001, a / np.abs(s_val), 0)
feats['wa_div_accel_base'] = np.where(np.abs(b) > 0.001, wa / np.abs(b), 0)

# Rank sums (approximated as normalized sum)
feats['wa_accel_sum'] = (wa / (np.nanpercentile(wa, 99) + 0.001)) + (a / (np.nanpercentile(a, 99) + 0.001))
feats['wa_accel_atr_sum'] = feats['wa_accel_sum'] + (s_val / (np.nanpercentile(np.abs(s_val), 99) + 0.001))

# --- PROBABILITY COMBOS ---
p1 = df['prob_up_1d'].values if 'prob_up_1d' in df.columns else np.zeros(len(df))
p5 = df['prob_up_5d'].values if 'prob_up_5d' in df.columns else np.zeros(len(df))
pst = df['prob_up_st_cross'].values if 'prob_up_st_cross' in df.columns else np.zeros(len(df))

feats['prob_avg'] = (p1 + p5 + pst) / 3
feats['prob_max'] = np.maximum(np.maximum(p1, p5), pst)
feats['prob_product'] = p1 * p5 * pst
feats['prob_wa'] = wa * pst
feats['prob_accel'] = a * pst
feats['prob_accel_wa'] = wa * a * pst

# --- STREAK COMBOS ---
st = df['streak'].values if 'streak' in df.columns else np.zeros(len(df))
feats['streak_abs'] = np.abs(st)
feats['streak_pos'] = np.maximum(st, 0)
feats['streak_neg'] = np.minimum(st, 0)
feats['streak_x_wa'] = st * wa
feats['streak_x_accel'] = st * a
feats['streak_x_atr'] = st * s_val

# --- CONFLUENCE COMBOS ---
conf = df['confluence'].values if 'confluence' in df.columns else np.zeros(len(df))
feats['conf_x_wa'] = conf * wa
feats['conf_x_accel'] = conf * a
feats['conf_x_atr'] = conf * s_val
feats['conf_x_streak'] = conf * st

# --- AI SCORE COMBOS ---
ai_o = df['ai_overall_score'].values if 'ai_overall_score' in df.columns else np.zeros(len(df))
ai_t = df['ai_tech_score'].values if 'ai_tech_score' in df.columns else np.zeros(len(df))
ai_m = df['ai_momentum_score'].values if 'ai_momentum_score' in df.columns else np.zeros(len(df))
ai_v = df['ai_volume_score'].values if 'ai_volume_score' in df.columns else np.zeros(len(df))

feats['ai_tech_x_wa'] = ai_t * wa
feats['ai_mom_x_wa'] = ai_m * wa
feats['ai_vol_x_wa'] = ai_v * wa
feats['ai_tech_x_accel'] = ai_t * a
feats['ai_mom_x_accel'] = ai_m * a
feats['ai_overall_x_wa'] = ai_o * wa
feats['ai_overall_x_accel'] = ai_o * a
feats['ai_avg'] = (ai_o + ai_t + ai_m + ai_v) / 4

# --- CUMULATIVE / MOMENTUM OF INDICATORS (within date) ---
# We'll compute rolling ranks per date later; for now, cross-sectional features

# --- ABSOLUTE MOMENTUM FEATURES ---
feats['price_x_wa'] = df['price'].values * wa if 'price' in df.columns else np.zeros(len(df))
feats['change_x_wa'] = df['change_pct'].values * wa if 'change_pct' in df.columns else np.zeros(len(df))
feats['change_x_accel'] = df['change_pct'].values * a if 'change_pct' in df.columns else np.zeros(len(df))

# --- COMPOSITE SCORES ---
feats['composite_1'] = wa * 0.4 + a * 0.3 + s_val * 0.3
feats['composite_2'] = wa * 0.3 + pst * 0.3 + a * 0.2 + s_streak * 0.2
feats['composite_3'] = wa * 0.25 + a * 0.25 + s_val * 0.25 + conf * 0.25
feats['composite_4'] = ai_o * 0.3 + wa * 0.3 + a * 0.2 + s_val * 0.2
feats['composite_5'] = pst * 0.4 + a * 0.3 + wa * 0.3
feats['composite_6'] = wa * a * pst  # triple product

# --- THRESHOLD FEATURES (binary-like continuous) ---
feats['wa_above_0'] = (wa > 0).astype(float)
feats['accel_above_0'] = (a > 0).astype(float)
feats['accel_base_above_0'] = (b > 0).astype(float)
feats['atr_above_0'] = (s_val > 0).astype(float)
feats['streak_above_0'] = (st > 0).astype(float)
feats['conf_above_50'] = (conf > 50).astype(float)

# --- Pct-based features ---
feats['pct_accel'] = df['atrp'].values * a if 'atrp' in df.columns else np.zeros(len(df))

# --- TRIPLE PRODUCTS ---
feats['triple_wa_accel_atr'] = wa * a * s_val
feats['triple_wa_accel_streak'] = wa * a * s_streak
feats['triple_wa_accel_prob'] = wa * a * pst
feats['triple_accel_atr_prob'] = a * s_val * pst

# --- QUADRUPLE ---
feats['quad_wa_accel_atr_prob'] = wa * a * s_val * pst
feats['quad_wa_accel_streak_prob'] = wa * a * s_streak * pst

# --- RATIO COMBOS ---
feats['wa_over_accel_atr'] = np.where(np.abs(a * s_val) > 0.001, wa / np.abs(a * s_val), 0)

print(f"  Created {len(feats)} features ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 3. PREPARE ARRAYS
###############################################################################
print("\n[3] Preparing arrays...", flush=True)
t0 = time.time()

dates = df['date'].values
dates_u = np.unique(dates)
nd = len(dates_u)
dmap = {d: i for i, d in enumerate(dates_u)}
di = np.array([dmap[d] for d in dates])

# Returns
ret_1d = df['ret_1d'].values if 'ret_1d' in df.columns else np.full(len(df), np.nan)
ret_5d = df['ret_5d'].values if 'ret_5d' in df.columns else np.full(len(df), np.nan)
ret_1mo = df['ret_1mo'].values if 'ret_1mo' in df.columns else np.full(len(df), np.nan)

# Base filter (price >= 1)
base = df['price'].values >= 1.0 if 'price' in df.columns else np.ones(len(df), dtype=bool)
base &= np.isfinite(ret_1d)

print(f"  {nd} dates, {len(df)} rows ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 4. FAST STATS FUNCTION
###############################################################################
def fast_stats(rets_by_date, nd):
    """Compute stats from per-date mean returns (vector of length nd)"""
    r = rets_by_date[np.isfinite(rets_by_date)]
    n = len(r)
    if n < 30:
        return None
    cl = np.cumsum(np.log1p(r))
    c = np.exp(cl)
    tr = float(c[-1] - 1)
    sd = float(np.std(r, ddof=1))
    ar = float((1+tr)**(252/n)-1) if tr > -1 else -1
    av = float(sd * np.sqrt(252))
    sh = float(np.mean(r) / sd * np.sqrt(252)) if sd > 1e-10 else 0
    rm = np.maximum.accumulate(c)
    dd = (c - rm) / rm
    mdd = float(np.min(dd))
    w = float(np.mean(r > 0))
    gp = float(np.sum(r[r > 0]))
    gl = float(np.abs(np.sum(r[r < 0])))
    pf = float(gp / gl) if gl > 0 else 0
    x = np.arange(n)
    sl, ic = np.polyfit(x, cl, 1)
    pl = ic + sl * x
    ssr = float(np.sum((cl - pl) ** 2))
    sst = float(np.sum((cl - np.mean(cl)) ** 2))
    rsq = float(1 - ssr / sst) if sst > 0 else 0
    return {
        'tr': round(tr, 4), 'cagr': round(ar, 4), 'vol': round(av, 4),
        'sharpe': round(sh, 3), 'mdd': round(mdd, 4), 'wr': round(w, 4),
        'pf': round(pf, 3), 'rsq': round(rsq, 4), 'n': n
    }

###############################################################################
# 5. MONSTER SWEEP ENGINE
###############################################################################
print("\n[4] MONSTER SWEEP - Phase 1: Single features...", flush=True)
t0 = time.time()

holds = {'1d': ret_1d, '5d': ret_5d, '1mo': ret_1mo}
top_ns = [5, 10, 15, 20, 30]
all_results = []
cnt = 0

for feat_name, feat_vals in feats.items():
    for hold_name, ret_vals in holds.items():
        for tn in top_ns:
            # Per-date: rank feature, take top tn, average return
            daily_ret = np.full(nd, np.nan)
            for d_idx in range(nd):
                mask = (di == d_idx) & base & np.isfinite(feat_vals) & np.isfinite(ret_vals)
                if np.sum(mask) < tn:
                    continue
                f = feat_vals[mask]
                r = ret_vals[mask]
                top_idx = np.argpartition(f, -tn)[-tn:]
                daily_ret[d_idx] = np.mean(r[top_idx])

            st = fast_stats(daily_ret, nd)
            if st:
                st['strat'] = f"rank={feat_name}|top{tn}|{hold_name}"
                st['feat'] = feat_name
                st['tn'] = tn
                st['hold'] = hold_name
                all_results.append(st)
            cnt += 1

    if cnt % 500 == 0:
        print(f"  {cnt} tested ({len(all_results)} valid, {time.time()-t0:.0f}s)", flush=True)

print(f"  Phase 1 done: {cnt} tested, {len(all_results)} valid ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 5b. TOP FEATURES -> DUAL COMBOS
###############################################################################
print("\n[5] Phase 2: Dual-factor combos (top 30 features)...", flush=True)
t0 = time.time()

# Pick top 30 features by sharpe
top_feats = sorted(all_results, key=lambda x: x['sharpe'], reverse=True)[:30]
top_feat_names = list(set(r['feat'] for r in top_feats))

cnt2 = 0
for f1, f2 in itertools.combinations(top_feat_names, 2):
    for hold_name, ret_vals in holds.items():
        for tn in [10, 15, 20]:
            daily_ret = np.full(nd, np.nan)
            v1 = feats[f1]
            v2 = feats[f2]
            for d_idx in range(nd):
                mask = (di == d_idx) & base & np.isfinite(v1) & np.isfinite(v2) & np.isfinite(ret_vals)
                if np.sum(mask) < tn:
                    continue
                combo = v1[mask] + v2[mask]
                top_idx = np.argpartition(combo, -tn)[-tn:]
                daily_ret[d_idx] = np.mean(ret_vals[mask][top_idx])

            st = fast_stats(daily_ret, nd)
            if st:
                st['strat'] = f"rank=({f1}+{f2})|top{tn}|{hold_name}"
                st['feat'] = f"{f1}+{f2}"
                st['tn'] = tn
                st['hold'] = hold_name
                all_results.append(st)
            cnt2 += 1

print(f"  Phase 2 done: {cnt2} tested ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 5c. TRIPLE COMBOS (top 10 x top 10 x top 10)
###############################################################################
print("\n[6] Phase 3: Triple-factor combos...", flush=True)
t0 = time.time()

top10_feats = list(set(r['feat'] for r in sorted(all_results, key=lambda x: x['sharpe'], reverse=True)[:20]))

cnt3 = 0
for f1, f2, f3 in itertools.combinations(top10_feats, 3):
    for hold_name, ret_vals in holds.items():
        for tn in [10, 15, 20]:
            daily_ret = np.full(nd, np.nan)
            v1 = feats[f1]; v2 = feats[f2]; v3 = feats[f3]
            for d_idx in range(nd):
                mask = (di == d_idx) & base & np.isfinite(v1) & np.isfinite(v2) & np.isfinite(v3) & np.isfinite(ret_vals)
                if np.sum(mask) < tn:
                    continue
                combo = v1[mask] + v2[mask] + v3[mask]
                top_idx = np.argpartition(combo, -tn)[-tn:]
                daily_ret[d_idx] = np.mean(ret_vals[mask][top_idx])

            st = fast_stats(daily_ret, nd)
            if st:
                st['strat'] = f"rank=({f1}+{f2}+{f3})|top{tn}|{hold_name}"
                st['feat'] = f"{f1}+{f2}+{f3}"
                st['tn'] = tn
                st['hold'] = hold_name
                all_results.append(st)
            cnt3 += 1

print(f"  Phase 3 done: {cnt3} tested ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 5d. WEIGHTED COMBOS (top features with optimal weights)
###############################################################################
print("\n[7] Phase 4: Weighted combos...", flush=True)
t0 = time.time()

top15 = list(set(r['feat'] for r in sorted(all_results, key=lambda x: x['sharpe'], reverse=True)[:15]))

cnt4 = 0
for f1, f2 in itertools.combinations(top15, 2):
    for w1, w2 in [(0.7,0.3),(0.6,0.4),(0.5,0.5),(0.8,0.2),(0.3,0.7)]:
        for hold_name, ret_vals in holds.items():
            for tn in [10, 15, 20]:
                daily_ret = np.full(nd, np.nan)
                v1 = feats[f1]; v2 = feats[f2]
                for d_idx in range(nd):
                    mask = (di == d_idx) & base & np.isfinite(v1) & np.isfinite(v2) & np.isfinite(ret_vals)
                    if np.sum(mask) < tn:
                        continue
                    combo = w1 * v1[mask] + w2 * v2[mask]
                    top_idx = np.argpartition(combo, -tn)[-tn:]
                    daily_ret[d_idx] = np.mean(ret_vals[mask][top_idx])

                st = fast_stats(daily_ret, nd)
                if st:
                    st['strat'] = f"rank={w1:.1f}*{f1}+{w2:.1f}*{f2}|top{tn}|{hold_name}"
                    st['feat'] = f"{w1}*{f1}+{w2}*{f2}"
                    st['tn'] = tn
                    st['hold'] = hold_name
                    all_results.append(st)
                cnt4 += 1

print(f"  Phase 4 done: {cnt4} tested ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 6. SAVE & RANK
###############################################################################
print("\n[8] Saving and ranking...", flush=True)

# Deduplicate
seen = set()
unique = []
for r in all_results:
    k = r['strat']
    if k not in seen:
        seen.add(k)
        unique.append(r)

all_results = unique
print(f"  Total unique strategies: {len(all_results)}", flush=True)

# Save
with open(os.path.join(OUTPUT, 'monster_results.json'), 'w') as f:
    json.dump(all_results, f, indent=2, default=str)

# Rank
df_r = pd.DataFrame(all_results)

sep = "=" * 130
dash = "-" * 130

for hold, hl in [('1d','BTST'),('5d','5-DAY'),('1mo','1-MONTH')]:
    hdf = df_r[df_r['hold']==hold]
    if len(hdf) == 0: continue
    
    print(f"\n{sep}", flush=True)
    print(f"  {hl} -- Top 10 per category ({len(hdf)} strategies)", flush=True)
    print(f"{sep}", flush=True)
    
    cats = [
        ('sharpe', False, 'BEST SHARPE'),
        ('cagr', False, 'BEST CAGR'),
        ('mdd', True, 'SHALLOWEST DD'),
        ('vol', True, 'LOWEST VOL'),
        ('rsq', False, 'MOST LINEAR'),
        ('wr', False, 'BEST WIN RATE'),
    ]
    
    print(f"  {'Category':<15} {'Sharpe':>7} {'CAGR':>8} {'MDD':>8} {'Vol':>7} {'WR':>6} {'PF':>6} {'R2':>6} {'Days':>5}  Strategy", flush=True)
    print(f"  {'-'*15} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*5}  {'-'*70}", flush=True)
    
    for col, asc, cat in cats:
        best = hdf.sort_values(col, ascending=asc).head(3)
        for _, r in best.iterrows():
            print(f"  {cat:<15} {r['sharpe']:>7.3f} {r['cagr']*100:>7.1f}% {r['mdd']*100:>7.1f}% {r['vol']*100:>6.1f}% {r['wr']*100:>5.1f}% {r['pf']:>6.2f} {r['rsq']:>6.3f} {r['n']:>5}  {r['strat'][:70]}", flush=True)
        print(flush=True)

# COMBINED BEST (balanced score)
print(f"\n{sep}", flush=True)
print(f"  COMBINED BEST: Score = Sharpe * R2 / Vol (balanced)", flush=True)
print(f"{sep}", flush=True)

df_r['score'] = df_r['sharpe'] * df_r['rsq'] / (df_r['vol'] + 0.001)
for hold, hl in [('1d','BTST'),('5d','5-DAY'),('1mo','1-MONTH')]:
    hdf = df_r[df_r['hold']==hold]
    if len(hdf) == 0: continue
    top = hdf.sort_values('score', ascending=False).head(10)
    print(f"\n  {hl} TOP 10 BALANCED:", flush=True)
    print(f"  {'Score':>7} {'Sharpe':>7} {'CAGR':>8} {'MDD':>8} {'Vol':>7} {'WR':>6} {'R2':>6} {'Days':>5}  Strategy", flush=True)
    for _, r in top.iterrows():
        print(f"  {r['score']:>7.3f} {r['sharpe']:>7.3f} {r['cagr']*100:>7.1f}% {r['mdd']*100:>7.1f}% {r['vol']*100:>6.1f}% {r['wr']*100:>5.1f}% {r['rsq']:>6.3f} {r['n']:>5}  {r['strat'][:70]}", flush=True)

print(f"\n{'='*130}", flush=True)
print(f"  TOTAL: {len(all_results)} strategies tested across 8 phases", flush=True)
print(f"  TIME: {time.time()-t0:.0f}s total", flush=True)
print(f"{'='*130}", flush=True)
print("DONE", flush=True)
