"""
MONSTER STRATEGY FINDER v6 - SAMPLED FAST
- Pre-sorts data, uses numpy argpartition per date (vectorized via pre-built index)
- Tests 25% of dates for speed, verifies top results on all dates
"""
import numpy as np, pandas as pd, sys, io, os, time, json, itertools, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*100)
print("  MONSTER STRATEGY FINDER v6 - FAST")
print("="*100, flush=True)

# 1. LOAD
t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
df = df[df['price'] >= 1.0].copy()
df = df.sort_values(['date','symbol']).reset_index(drop=True)
print(f"Loaded {len(df)} rows ({time.time()-t0:.0f}s)", flush=True)

# Pre-sort and build index
dates_u = np.sort(df['date'].unique())
nd = len(dates_u)
ds = np.searchsorted(df['date'].values, dates_u, side='left')
de = np.searchsorted(df['date'].values, dates_u, side='right')
print(f"Dates: {nd} ({time.time()-t0:.0f}s)", flush=True)

# Pre-extract ALL columns as numpy arrays (much faster than pandas)
A = {}
for col in ['ret_1d','ret_5d','ret_1mo','weighted_alpha','atrp','streak','atr_value',
            'atr_streak','accel_a','accel_base','prob_up_1d','prob_up_5d','prob_up_st_cross',
            'change_pct','ai_overall_score','ai_tech_score','ai_momentum_score',
            'atr_crossed_above','accel_crossed_up','accel_crossed_down']:
    A[col] = df[col].values.astype(np.float32)

# Derived features (computed once)
A['accel_a_pos'] = np.maximum(A['accel_a'], 0)
A['accel_a_abs'] = np.abs(A['accel_a'])
A['accel_base_pos'] = np.maximum(A['accel_base'], 0)
A['accel_ratio'] = np.where(np.abs(A['accel_base'])>0.001, A['accel_a']/A['accel_base'], 0)
A['accel_diff'] = A['accel_a'] - A['accel_base']
A['accel_sum'] = A['accel_a'] + A['accel_base']
A['accel_product'] = A['accel_a'] * A['accel_base']
A['accel_sq'] = A['accel_a']**2
A['accel_log'] = np.log1p(np.abs(A['accel_a']))*np.sign(A['accel_a'])
A['atr_streak_abs'] = np.abs(A['atr_streak'])
A['atr_product'] = A['atr_value']*A['atr_streak']
A['atr_sq'] = A['atr_value']**2
A['atr_log'] = np.log1p(np.abs(A['atr_value']))*np.sign(A['atr_value'])
A['atr_pct_x_streak'] = A['atrp']*A['atr_streak']
A['atr_pct_x_value'] = A['atrp']*A['atr_value']
A['wa_pos'] = np.maximum(A['weighted_alpha'], 0)
A['wa_abs'] = np.abs(A['weighted_alpha'])
A['wa_sq'] = A['weighted_alpha']**2
A['wa_log'] = np.log1p(np.abs(A['weighted_alpha']))*np.sign(A['weighted_alpha'])
A['wa_x_accel'] = A['weighted_alpha']*A['accel_a']
A['wa_x_atr'] = A['weighted_alpha']*A['atr_value']
A['wa_x_streak'] = A['weighted_alpha']*A['streak']
A['accel_x_atr'] = A['accel_a']*A['atr_value']
A['accel_x_streak'] = A['accel_a']*A['atr_streak']
A['wa_accel_atr'] = A['weighted_alpha']*A['accel_a']*A['atr_value']
A['wa_accel_streak'] = A['weighted_alpha']*A['accel_a']*A['atr_streak']
A['wa_div_accel'] = np.where(np.abs(A['accel_a'])>0.001, A['weighted_alpha']/np.abs(A['accel_a']), 0)
A['wa_div_atr'] = np.where(np.abs(A['atr_value'])>0.001, A['weighted_alpha']/np.abs(A['atr_value']), 0)
A['accel_div_atr'] = np.where(np.abs(A['atr_value'])>0.001, A['accel_a']/np.abs(A['atr_value']), 0)
A['prob_avg'] = (A['prob_up_1d']+A['prob_up_5d']+A['prob_up_st_cross'])/3
A['prob_product'] = A['prob_up_1d']*A['prob_up_5d']*A['prob_up_st_cross']
A['prob_wa'] = A['weighted_alpha']*A['prob_up_st_cross']
A['prob_accel'] = A['accel_a']*A['prob_up_st_cross']
A['prob_accel_wa'] = A['weighted_alpha']*A['accel_a']*A['prob_up_st_cross']
A['streak_x_wa'] = A['streak']*A['weighted_alpha']
A['streak_x_accel'] = A['streak']*A['accel_a']
A['streak_x_atr'] = A['streak']*A['atr_value']
A['ai_tech_x_wa'] = A['ai_tech_score']*A['weighted_alpha']
A['ai_mom_x_wa'] = A['ai_momentum_score']*A['weighted_alpha']
A['ai_tech_x_accel'] = A['ai_tech_score']*A['accel_a']
A['ai_mom_x_accel'] = A['ai_momentum_score']*A['accel_a']
A['ai_overall_x_wa'] = A['ai_overall_score']*A['weighted_alpha']
A['ai_overall_x_accel'] = A['ai_overall_score']*A['accel_a']
A['composite_1'] = A['weighted_alpha']*0.4+A['accel_a']*0.3+A['atr_value']*0.3
A['composite_2'] = A['weighted_alpha']*0.3+A['prob_up_st_cross']*0.3+A['accel_a']*0.2+A['atr_streak']*0.2
A['composite_3'] = A['weighted_alpha']*0.33+A['accel_a']*0.33+A['atr_value']*0.34
A['composite_4'] = A['ai_overall_score']*0.3+A['weighted_alpha']*0.3+A['accel_a']*0.2+A['atr_value']*0.2
A['composite_5'] = A['prob_up_st_cross']*0.4+A['accel_a']*0.3+A['weighted_alpha']*0.3
A['composite_6'] = A['weighted_alpha']*A['accel_a']*A['prob_up_st_cross']
A['triple_wa_accel_atr'] = A['weighted_alpha']*A['accel_a']*A['atr_value']
A['triple_wa_accel_streak'] = A['weighted_alpha']*A['accel_a']*A['atr_streak']
A['triple_wa_accel_prob'] = A['weighted_alpha']*A['accel_a']*A['prob_up_st_cross']
A['wa_above_0'] = (A['weighted_alpha']>0).astype(np.float32)
A['accel_above_0'] = (A['accel_a']>0).astype(np.float32)
A['atr_above_0'] = (A['atr_value']>0).astype(np.float32)
A['streak_above_0'] = (A['streak']>0).astype(np.float32)
A['change_x_wa'] = A['change_pct']*A['weighted_alpha']
A['change_x_accel'] = A['change_pct']*A['accel_a']
A['pct_accel'] = A['atrp']*A['accel_a']

FEATS = list(A.keys())
HOLDS = {'1d': 'ret_1d', '5d': 'ret_5d', '1mo': 'ret_1mo'}
TOP_NS = [5, 10, 15, 20, 30]
print(f"Features: {len(FEATS)} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# FAST STATS
###############################################################################
def fs(r):
    r = r[np.isfinite(r)]; n = len(r)
    if n < 30: return None
    cl = np.cumsum(np.log1p(r)); cc = np.exp(cl)
    tr = float(cc[-1]-1); sd = float(np.std(r,ddof=1))
    ar = float((1+tr)**(252/n)-1) if tr>-1 else -1
    av = float(sd*np.sqrt(252))
    sh = float(np.mean(r)/sd*np.sqrt(252)) if sd>1e-10 else 0
    rm = np.maximum.accumulate(cc); mdd = float(np.min((cc-rm)/rm))
    wr = float(np.mean(r>0))
    gp = float(np.sum(r[r>0])); gl = float(np.abs(np.sum(r[r<0])))
    pf = float(gp/gl) if gl>0 else 0
    x = np.arange(n); sl,ic = np.polyfit(x,cl,1)
    rsq = float(1-np.sum((cl-(ic+sl*x))**2)/np.sum((cl-np.mean(cl))**2))
    return {'sharpe':round(sh,3),'cagr':round(ar,4),'vol':round(av,4),
            'mdd':round(mdd,4),'wr':round(wr,4),'pf':round(pf,3),'rsq':round(rsq,4),'n':n}

###############################################################################
# FAST TOP-N - pre-sliced numpy arrays
###############################################################################
def fast_topn(feat_vals, ret_vals, tn, ds, de, nd):
    daily = np.full(nd, np.nan)
    for i in range(nd):
        s=ds[i]; e=de[i]; n=e-s
        if n<tn+5: continue
        fv=feat_vals[s:e]; rv=ret_vals[s:e]
        m = np.isfinite(fv)&np.isfinite(rv)
        cnt=np.sum(m)
        if cnt<tn: continue
        f=np.ascontiguousarray(fv[m]); r=np.ascontiguousarray(rv[m])
        idx = np.argpartition(f,-tn)[-tn:]
        daily[i]=np.mean(r[idx])
    return daily

# USE 25% SAMPLE FOR SPEED
sample_mask = np.zeros(nd, dtype=bool)
sample_mask[::4] = True
sds = ds[sample_mask]
sde = de[sample_mask]
snd = np.sum(sample_mask)
print(f"Using {snd} sample dates ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# PHASE 1: All single features
###############################################################################
print(f"\n[PHASE 1] {len(FEATS)} features x {len(TOP_NS)} top-N x {len(HOLDS)} holds", flush=True)
t0 = time.time()
all_results = []
cnt = 0

for fname in FEATS:
    fvals = A[fname]
    for hname, hcol in HOLDS.items():
        rvals = A[hcol]
        for tn in TOP_NS:
            daily = fast_topn(fvals, rvals, tn, sds, sde, snd)
            st = fs(daily)
            if st:
                st['strat'] = f"rank={fname}|top{tn}|{hname}"
                st['feat'] = fname; st['tn'] = tn; st['hold'] = hname
                st['type'] = 'single'
                all_results.append(st)
            cnt += 1
    if (cnt%(len(TOP_NS)*len(HOLDS)))==0:
        elapsed = time.time()-t0
        rate = cnt/(elapsed+0.01)
        eta = (len(FEATS)*len(TOP_NS)*len(HOLDS)-cnt)/(rate+0.01)
        print(f"  {len(FEATS)}/{len(FEATS)} features ({elapsed:.0f}s, ETA {eta:.0f}s) cnt={len(all_results)}", flush=True)

print(f"  Phase 1 done: {len(all_results)} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# PHASE 2: Top features dual combos
###############################################################################
print(f"\n[PHASE 2] Dual combos from top 15 features...", flush=True)
t0 = time.time()
res_df = pd.DataFrame(all_results)
top15 = [f for f in res_df.sort_values('sharpe', ascending=False)['feat'].unique() if f in A][:15]

# Pre-compute combo features
combos_2 = {}
for f1, f2 in itertools.combinations(top15, 2):
    combos_2[f"{f1}+{f2}"] = A[f1] + A[f2]

cnt = 0
for cname, cvals in combos_2.items():
    for hname, hcol in HOLDS.items():
        rvals = A[hcol]
        for tn in [10, 15, 20]:
            daily = fast_topn(cvals, rvals, tn, sds, sde, snd)
            st = fs(daily)
            if st:
                st['strat'] = f"rank={cname}|top{tn}|{hname}"
                st['feat'] = cname; st['tn'] = tn; st['hold'] = hname
                st['type'] = 'dual'
                all_results.append(st)
            cnt += 1
    if cnt%(len(HOLDS)*3)==0:
        print(f"  {cnt} ({time.time()-t0:.0f}s)", flush=True)

print(f"  Phase 2 done: {cnt} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# PHASE 3: Top features weighted combos
###############################################################################
print(f"\n[PHASE 3] Weighted dual combos from top 10...", flush=True)
t0 = time.time()
res_df = pd.DataFrame(all_results)
top10 = [f for f in res_df.sort_values('sharpe', ascending=False)['feat'].unique() if f in A][:10]

cnt = 0
for f1, f2 in itertools.combinations(top10, 2):
    for w1, w2 in [(0.7,0.3),(0.6,0.4),(0.5,0.5),(0.8,0.2),(0.9,0.1)]:
        cvals = w1*A[f1] + w2*A[f2]
        cname = f"{w1:.1f}*{f1}+{w2:.1f}*{f2}"
        for hname, hcol in HOLDS.items():
            rvals = A[hcol]
            daily = fast_topn(cvals, rvals, 15, sds, sde, snd)
            st = fs(daily)
            if st:
                st['strat'] = f"rank={cname}|top15|{hname}"
                st['feat'] = cname; st['tn'] = 15; st['hold'] = hname
                st['type'] = 'weighted'
                all_results.append(st)
            cnt += 1
    if cnt%50==0:
        print(f"  {cnt} ({time.time()-t0:.0f}s)", flush=True)

print(f"  Phase 3 done: {cnt} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# PHASE 4: Triple combos
###############################################################################
print(f"\n[PHASE 4] Triple combos from top 8...", flush=True)
t0 = time.time()
res_df = pd.DataFrame(all_results)
top8 = [f for f in res_df.sort_values('sharpe', ascending=False)['feat'].unique() if f in A][:8]

cnt = 0
for f1, f2, f3 in itertools.combinations(top8, 3):
    cvals = A[f1] + A[f2] + A[f3]
    cname = f"{f1}+{f2}+{f3}"
    for hname, hcol in HOLDS.items():
        rvals = A[hcol]
        for tn in [10, 15]:
            daily = fast_topn(cvals, rvals, tn, sds, sde, snd)
            st = fs(daily)
            if st:
                st['strat'] = f"rank={cname}|top{tn}|{hname}"
                st['feat'] = cname; st['tn'] = tn; st['hold'] = hname
                st['type'] = 'triple'
                all_results.append(st)
            cnt += 1

print(f"  Phase 4 done: {cnt} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# PHASE 5: Binary filter combos
###############################################################################
print(f"\n[PHASE 5] Binary filter combos...", flush=True)
t0 = time.time()
BINS = ['atr_crossed_above','accel_crossed_up','accel_crossed_down']
top5 = [f for f in pd.DataFrame(all_results).sort_values('sharpe', ascending=False)['feat'].unique() if f in A][:5]

cnt = 0
for bin_col in BINS:
    bv = A[bin_col]
    for feat in top5:
        fv = A[feat]
        cvals = bv * fv
        cname = f"{bin_col}*{feat}"
        for hname, hcol in HOLDS.items():
            rvals = A[hcol]
            for tn in [10, 15]:
                daily = fast_topn(cvals, rvals, tn, sds, sde, snd)
                st = fs(daily)
                if st:
                    st['strat'] = f"filter={cname}|top{tn}|{hname}"
                    st['feat'] = cname; st['tn'] = tn; st['hold'] = hname
                    st['type'] = 'binary_filter'
                    all_results.append(st)
                cnt += 1

# Triple binary
for b1, b2 in itertools.combinations(BINS, 2):
    bv = A[b1] * A[b2]
    cname = f"{b1}+{b2}"
    for feat in top5:
        fv = A[feat]
        cvals = bv * fv
        for hname, hcol in HOLDS.items():
            rvals = A[hcol]
            daily = fast_topn(cvals, rvals, 15, sds, sde, snd)
            st = fs(daily)
            if st:
                st['strat'] = f"filter={cname}*{feat}|top15|{hname}"
                st['feat'] = f"{cname}*{feat}"; st['tn'] = 15; st['hold'] = hname
                st['type'] = 'binary_filter'
                all_results.append(st)
            cnt += 1

print(f"  Phase 5 done: {cnt} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# VERIFY TOP 50 ON FULL DATA
###############################################################################
print(f"\n[VERIFY] Top 50 on full data...", flush=True)
t0 = time.time()
res_df = pd.DataFrame(all_results)
top50 = res_df.sort_values('sharpe', ascending=False).head(50)

verified = []
for _, row in top50.iterrows():
    fname = row['feat']; hcol = HOLDS[row['hold']]; tn = int(row['tn'])
    # Reconstruct feature
    if '+' in fname and '*' not in fname:
        parts = fname.split('+')
        fvals = sum(A[p] for p in parts)
    elif '*' in fname:
        parts = fname.split('*')
        try:
            fvals = float(parts[0]) * A[parts[1]] + float(parts[2]) * A[parts[3]]
        except:
            continue
    else:
        fvals = A.get(fname)
        if fvals is None: continue

    daily = fast_topn(fvals, A[hcol], tn, ds, de, nd)
    st = fs(daily)
    if st:
        st['strat'] = row['strat']
        st['feat'] = fname; st['tn'] = tn; st['hold'] = row['hold']
        st['type'] = row.get('type','')
        verified.append(st)

print(f"  Verified {len(verified)} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# SAVE & RANK
###############################################################################
print(f"\n[SAVE]", flush=True)
# Merge sample + verified
all_results.extend(verified)

seen = set()
unique = []
for r in all_results:
    key = (r['feat'], r['tn'], r['hold'], r.get('type',''))
    if key not in seen:
        seen.add(key)
        unique.append(r)
all_results = unique

with open(os.path.join(OUTPUT, 'monster_results.json'), 'w') as f:
    json.dump(all_results, f, indent=2, default=str)

df_r = pd.DataFrame(all_results)
df_r['score'] = df_r['sharpe'] * df_r['rsq'] / (df_r['vol'] + 0.001)

sep = "="*150
for hold, hl in [('1d','BTST'),('5d','5-DAY'),('1mo','1-MONTH')]:
    hdf = df_r[df_r['hold']==hold]
    if len(hdf)==0: continue
    print(f"\n{sep}")
    print(f"  {hl} -- {len(hdf)} strategies")
    print(sep)
    for col, asc, cat in [('sharpe',False,'SHARPE'),('cagr',False,'CAGR'),
                           ('mdd',True,'DD'),('vol',True,'VOL'),('rsq',False,'LINEAR'),
                           ('wr',False,'WR'),('score',False,'BALANCED')]:
        top = hdf.sort_values(col, ascending=asc).head(5)
        print(f"\n  [{cat}]")
        for _, r in top.iterrows():
            print(f"    Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% PF={r['pf']:>5.2f} R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:100]}")

print(f"\n{sep}")
print(f"  GLOBAL TOP 30 BALANCED")
print(sep)
for i, (_, r) in enumerate(df_r.sort_values('score', ascending=False).head(30).iterrows()):
    print(f"  #{i+1:2d} Score={r['score']:>6.3f} Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:100]}")

print(f"\n{len(all_results)} unique strategies")
print("DONE")
