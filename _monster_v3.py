"""
MONSTER STRATEGY FINDER v3 - TURBO
- Pre-sorts by date, uses numpy date-indexed slicing
- 75 features x 5 top-N x 3 holds = 1125 combos
- Then dual/triple/weighted combos from top features
"""
import numpy as np, pandas as pd, sys, io, os, time, json, itertools, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*100)
print("  MONSTER STRATEGY FINDER v3 - TURBO")
print("="*100, flush=True)

# 1. LOAD
print("\n[1] Loading US stock cache...", flush=True)
t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
df = df[df['price'] >= 1.0].copy()
print(f"  {len(df)} rows, {df['date'].nunique()} dates ({time.time()-t0:.0f}s)", flush=True)

# 2. PRE-SORT AND BUILD DATE INDEX
print("\n[2] Pre-sorting and building date index...", flush=True)
t0 = time.time()
df = df.sort_values('date').reset_index(drop=True)
dates_u = df['date'].unique()
nd = len(dates_u)
# Build date start/end indices for fast slicing
date_starts = np.searchsorted(df['date'].values, dates_u, side='left')
date_ends = np.searchsorted(df['date'].values, dates_u, side='right')
print(f"  {nd} dates indexed ({time.time()-t0:.0f}s)", flush=True)

# Get column arrays (all aligned)
arr = {}
for c in ['weighted_alpha','atrp','streak','atr_value','atr_streak','atr_multiplier',
          'accel_a','accel_base','accel_signal','accel_crossed_up','accel_crossed_down',
          'atr_signal','atr_crossed_above','atr_crossed_below',
          'prob_up_1d','prob_up_5d','prob_up_st_cross','change_pct','price',
          'ai_overall_score','ai_tech_score','ai_momentum_score',
          'ai_volume_score','ai_events_score','ai_volume_profile_score',
          'ai_trendline_score','ai_sentiment_score',
          'ret_1d','ret_5d','ret_1mo']:
    if c in df.columns:
        arr[c] = df[c].values

# 3. FEATURES
print("\n[3] Creating features...", flush=True)
a = arr['accel_a']; b = arr['accel_base']; wa = arr['weighted_alpha']
sv = arr['atr_value']; ss = arr['atr_streak']; atr = arr['atrp']
st = arr['streak']; pst = arr['prob_up_st_cross']
p1 = arr['prob_up_1d']; p5 = arr['prob_up_5d']
ai_o = arr['ai_overall_score']; ai_t = arr['ai_tech_score']
ai_m = arr['ai_momentum_score']; ai_v = arr['ai_volume_score']
ch = arr['change_pct']; pr = arr['price']

feats = {}

# RAW
for c in ['weighted_alpha','atrp','streak','atr_value','atr_streak',
          'accel_a','accel_base','prob_up_1d','prob_up_5d','prob_up_st_cross','change_pct']:
    feats[c] = arr[c]

# ACCEL
feats['accel_a_pos'] = np.maximum(a, 0)
feats['accel_a_abs'] = np.abs(a)
feats['accel_base_pos'] = np.maximum(b, 0)
feats['accel_ratio'] = np.where(np.abs(b) > 0.001, a/b, 0)
feats['accel_diff'] = a - b
feats['accel_sum'] = a + b
feats['accel_product'] = a * b
feats['accel_sq'] = a**2
feats['accel_log'] = np.log1p(np.abs(a)) * np.sign(a)

# ST
feats['atr_value_abs'] = np.abs(sv)
feats['atr_streak_abs'] = np.abs(ss)
feats['atr_product'] = sv * ss
feats['atr_sq'] = sv**2
feats['atr_log'] = np.log1p(np.abs(sv)) * np.sign(sv)
feats['atr_pct_x_streak'] = atr * ss
feats['atr_pct_x_value'] = atr * sv

# WA
feats['wa_pos'] = np.maximum(wa, 0)
feats['wa_abs'] = np.abs(wa)
feats['wa_sq'] = wa**2
feats['wa_log'] = np.log1p(np.abs(wa)) * np.sign(wa)

# CROSS
feats['wa_x_accel'] = wa * a
feats['wa_x_atr'] = wa * sv
feats['wa_x_streak'] = wa * st
feats['accel_x_atr'] = a * sv
feats['accel_x_streak'] = a * ss
feats['wa_accel_atr'] = wa * a * sv
feats['wa_accel_streak'] = wa * a * ss
feats['wa_div_accel'] = np.where(np.abs(a) > 0.001, wa/np.abs(a), 0)
feats['wa_div_atr'] = np.where(np.abs(sv) > 0.001, wa/np.abs(sv), 0)
feats['accel_div_atr'] = np.where(np.abs(sv) > 0.001, a/np.abs(sv), 0)

# PROB
feats['prob_avg'] = (p1 + p5 + pst) / 3
feats['prob_product'] = p1 * p5 * pst
feats['prob_wa'] = wa * pst
feats['prob_accel'] = a * pst
feats['prob_accel_wa'] = wa * a * pst

# STREAK
feats['streak_x_wa'] = st * wa
feats['streak_x_accel'] = st * a
feats['streak_x_atr'] = st * sv

# AI
feats['ai_tech_x_wa'] = ai_t * wa
feats['ai_mom_x_wa'] = ai_m * wa
feats['ai_tech_x_accel'] = ai_t * a
feats['ai_mom_x_accel'] = ai_m * a
feats['ai_overall_x_wa'] = ai_o * wa
feats['ai_overall_x_accel'] = ai_o * a

# COMPOSITES
feats['composite_1'] = wa*0.4 + a*0.3 + sv*0.3
feats['composite_2'] = wa*0.3 + pst*0.3 + a*0.2 + ss*0.2
feats['composite_3'] = wa*0.33 + a*0.33 + sv*0.34
feats['composite_4'] = ai_o*0.3 + wa*0.3 + a*0.2 + sv*0.2
feats['composite_5'] = pst*0.4 + a*0.3 + wa*0.3
feats['composite_6'] = wa * a * pst

# TRIPLE
feats['triple_wa_accel_atr'] = wa * a * sv
feats['triple_wa_accel_streak'] = wa * a * ss
feats['triple_wa_accel_prob'] = wa * a * pst

# THRESHOLD
feats['wa_above_0'] = (wa > 0).astype(float)
feats['accel_above_0'] = (a > 0).astype(float)
feats['atr_above_0'] = (sv > 0).astype(float)
feats['streak_above_0'] = (st > 0).astype(float)

# Price
feats['price_x_wa'] = pr * wa
feats['change_x_wa'] = ch * wa
feats['change_x_accel'] = ch * a
feats['pct_accel'] = atr * a

print(f"  {len(feats)} features", flush=True)

###############################################################################
# 4. FAST STATS
###############################################################################
def fast_stats(r):
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 30: return None
    cl = np.cumsum(np.log1p(r))
    c = np.exp(cl)
    tr = float(c[-1]-1); sd = float(np.std(r, ddof=1))
    ar = float((1+tr)**(252/n)-1) if tr > -1 else -1
    av = float(sd*np.sqrt(252))
    sh = float(np.mean(r)/sd*np.sqrt(252)) if sd > 1e-10 else 0
    rm = np.maximum.accumulate(c); mdd = float(np.min((c-rm)/rm))
    wr = float(np.mean(r>0))
    gp = float(np.sum(r[r>0])); gl = float(np.abs(np.sum(r[r<0])))
    pf = float(gp/gl) if gl > 0 else 0
    x = np.arange(n); sl,ic = np.polyfit(x,cl,1)
    rsq = float(1 - np.sum((cl-(ic+sl*x))**2) / np.sum((cl-np.mean(cl))**2))
    return {'sharpe':round(sh,3),'cagr':round(ar,4),'vol':round(av,4),
            'mdd':round(mdd,4),'wr':round(wr,4),'pf':round(pf,3),'rsq':round(rsq,4),'n':n}

###############################################################################
# 5. VECTORIZED SWEEP - Using pre-sorted date index
###############################################################################
print("\n[4] Phase 1: Single feature sweep...", flush=True)
t0 = time.time()

holds = {'1d': 'ret_1d', '5d': 'ret_5d', '1mo': 'ret_1mo'}
top_ns = [5, 10, 15, 20, 30]
all_results = []
cnt = 0

for feat_name, feat_vals in feats.items():
    for hold_name, ret_col in holds.items():
        rv = arr[ret_col]
        for tn in top_ns:
            daily = np.empty(nd)
            daily[:] = np.nan
            for d_idx in range(nd):
                s = date_starts[d_idx]; e = date_ends[d_idx]
                fv = feat_vals[s:e]; rv_d = rv[s:e]
                mask = np.isfinite(fv) & np.isfinite(rv_d)
                if np.sum(mask) < tn: continue
                fv_m = fv[mask]; rv_m = rv_d[mask]
                top_idx = np.argpartition(fv_m, -tn)[-tn:]
                daily[d_idx] = np.mean(rv_m[top_idx])
            
            st = fast_stats(daily)
            if st:
                st['strat'] = f"rank={feat_name}|top{tn}|{hold_name}"
                st['feat'] = feat_name; st['tn'] = tn; st['hold'] = hold_name
                all_results.append(st)
            cnt += 1
    
    if cnt % 200 == 0:
        print(f"  {cnt} tested ({time.time()-t0:.0f}s)", flush=True)

print(f"  Phase 1: {cnt} tested, {len(all_results)} valid ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 6. Phase 2: Dual combos from top 20 features
###############################################################################
print("\n[5] Phase 2: Dual combos (top 20 features)...", flush=True)
t0 = time.time()

res_df = pd.DataFrame(all_results)
top20 = res_df.sort_values('sharpe', ascending=False)['feat'].unique()[:20]

cnt2 = 0
for f1, f2 in itertools.combinations(top20, 2):
    v1 = feats[f1]; v2 = feats[f2]
    combo = v1 + v2
    
    for hold_name, ret_col in holds.items():
        rv = arr[ret_col]
        for tn in [10, 15, 20]:
            daily = np.empty(nd); daily[:] = np.nan
            for d_idx in range(nd):
                s = date_starts[d_idx]; e = date_ends[d_idx]
                c_d = combo[s:e]; rv_d = rv[s:e]
                mask = np.isfinite(c_d) & np.isfinite(rv_d)
                if np.sum(mask) < tn: continue
                top_idx = np.argpartition(c_d[mask], -tn)[-tn:]
                daily[d_idx] = np.mean(rv_d[mask][top_idx])
            
            st = fast_stats(daily)
            if st:
                st['strat'] = f"rank=({f1}+{f2})|top{tn}|{hold_name}"
                st['feat'] = f"{f1}+{f2}"; st['tn'] = tn; st['hold'] = hold_name
                all_results.append(st)
            cnt2 += 1

print(f"  Phase 2: {cnt2} combos ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 7. Phase 3: Triple combos from top 8
###############################################################################
print("\n[6] Phase 3: Triple combos...", flush=True)
t0 = time.time()

res_df2 = pd.DataFrame(all_results)
top8 = res_df2.sort_values('sharpe', ascending=False)['feat'].unique()[:8]

cnt3 = 0
for f1, f2, f3 in itertools.combinations(top8, 3):
    combo = feats[f1] + feats[f2] + feats[f3]
    
    for hold_name, ret_col in holds.items():
        rv = arr[ret_col]
        for tn in [10, 15]:
            daily = np.empty(nd); daily[:] = np.nan
            for d_idx in range(nd):
                s = date_starts[d_idx]; e = date_ends[d_idx]
                c_d = combo[s:e]; rv_d = rv[s:e]
                mask = np.isfinite(c_d) & np.isfinite(rv_d)
                if np.sum(mask) < tn: continue
                top_idx = np.argpartition(c_d[mask], -tn)[-tn:]
                daily[d_idx] = np.mean(rv_d[mask][top_idx])
            
            st = fast_stats(daily)
            if st:
                st['strat'] = f"rank=({f1}+{f2}+{f3})|top{tn}|{hold_name}"
                st['feat'] = f"{f1}+{f2}+{f3}"; st['tn'] = tn; st['hold'] = hold_name
                all_results.append(st)
            cnt3 += 1

print(f"  Phase 3: {cnt3} combos ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 8. Phase 4: Weighted combos from top 10
###############################################################################
print("\n[7] Phase 4: Weighted combos...", flush=True)
t0 = time.time()

res_df3 = pd.DataFrame(all_results)
top10 = res_df3.sort_values('sharpe', ascending=False)['feat'].unique()[:10]

cnt4 = 0
for f1, f2 in itertools.combinations(top10, 2):
    v1 = feats[f1]; v2 = feats[f2]
    for w1, w2 in [(0.7,0.3),(0.6,0.4),(0.5,0.5),(0.8,0.2)]:
        combo = w1*v1 + w2*v2
        
        for hold_name, ret_col in holds.items():
            rv = arr[ret_col]
            for tn in [10, 15]:
                daily = np.empty(nd); daily[:] = np.nan
                for d_idx in range(nd):
                    s = date_starts[d_idx]; e = date_ends[d_idx]
                    c_d = combo[s:e]; rv_d = rv[s:e]
                    mask = np.isfinite(c_d) & np.isfinite(rv_d)
                    if np.sum(mask) < tn: continue
                    top_idx = np.argpartition(c_d[mask], -tn)[-tn:]
                    daily[d_idx] = np.mean(rv_d[mask][top_idx])
                
                st = fast_stats(daily)
                if st:
                    st['strat'] = f"rank={w1:.1f}*{f1}+{w2:.1f}*{f2}|top{tn}|{hold_name}"
                    st['feat'] = f"{w1}*{f1}+{w2}*{f2}"; st['tn'] = tn; st['hold'] = hold_name
                    all_results.append(st)
                cnt4 += 1

print(f"  Phase 4: {cnt4} combos ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 9. SAVE & RANK
###############################################################################
print("\n[8] Saving and ranking...", flush=True)

seen = set()
unique = []
for r in all_results:
    if r['strat'] not in seen:
        seen.add(r['strat'])
        unique.append(r)

all_results = unique
with open(os.path.join(OUTPUT, 'monster_results.json'), 'w') as f:
    json.dump(all_results, f, indent=2, default=str)

df_r = pd.DataFrame(all_results)
df_r['score'] = df_r['sharpe'] * df_r['rsq'] / (df_r['vol'] + 0.001)

sep = "=" * 140

for hold, hl in [('1d','BTST'),('5d','5-DAY'),('1mo','1-MONTH')]:
    hdf = df_r[df_r['hold']==hold]
    if len(hdf) == 0: continue
    
    print(f"\n{sep}")
    print(f"  {hl} -- {len(hdf)} strategies")
    print(sep)
    
    cats = [
        ('sharpe', False, 'SHARPE'),
        ('cagr', False, 'CAGR'),
        ('mdd', True, 'SHALLOWEST DD'),
        ('vol', True, 'LOWEST VOL'),
        ('rsq', False, 'MOST LINEAR'),
        ('wr', False, 'BEST WIN RATE'),
        ('score', False, 'BEST BALANCED'),
    ]
    
    for col, asc, cat in cats:
        top = hdf.sort_values(col, ascending=asc).head(5)
        print(f"\n  [{cat}]")
        for _, r in top.iterrows():
            print(f"    Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% PF={r['pf']:>5.2f} R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:90]}")

# GLOBAL
print(f"\n{sep}")
print(f"  GLOBAL TOP 30 BALANCED (all holds combined)")
print(sep)
top30 = df_r.sort_values('score', ascending=False).head(30)
for i, (_, r) in enumerate(top30.iterrows()):
    print(f"  #{i+1:2d} Score={r['score']:>6.3f} Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:90]}")

print(f"\nTOTAL: {len(all_results)} unique strategies from {cnt+cnt2+cnt3+cnt4} tested")
print("DONE")
