"""
NO-LOOKAHEAD MONSTER v3 - FAST
Uses every-10th date sample (178 dates), tests key combos only, verifies top 100 on full data.
"""
import numpy as np, pandas as pd, sys, io, os, time, json, itertools, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*100)
print("  NO-LOOKAHEAD MONSTER v3 - FAST")
print("="*100, flush=True)

t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
df = df[df['price'] >= 1.0].copy()
df = df.sort_values(['date','symbol']).reset_index(drop=True)
print(f"Loaded {len(df)} rows ({time.time()-t0:.0f}s)", flush=True)

dates_u = np.sort(df['date'].unique())
nd = len(dates_u)
ds_arr = np.searchsorted(df['date'].values, dates_u, side='left')
de_arr = np.searchsorted(df['date'].values, dates_u, side='right')

# Hold targets (DECIMAL returns - NOT ranking features)
H1 = df['next_day_return'].values.astype(np.float64)
H5 = df['next_5d_return'].values.astype(np.float64)
HM = df['ret_1mo'].values.astype(np.float64)

# Legitimate base features (NO future returns)
B = {}
for col in ['weighted_alpha','atrp','streak','atr_value','atr_streak','atr_multiplier',
            'ai_overall_score','ai_tech_score','ai_momentum_score','ai_volume_score',
            'ai_events_score','ai_volume_profile_score','ai_trendline_score','ai_sentiment_score',
            'prob_up_1d','prob_up_5d','prob_up_st_cross',
            'accel_a','accel_base','accel_signal','accel_crossed_up','accel_crossed_down',
            'atr_signal','atr_crossed_above','atr_crossed_below',
            'change_pct','price','volume']:
    B[col] = df[col].values.astype(np.float64)

BASE = list(B.keys())
print(f"Base: {len(BASE)} ({time.time()-t0:.0f}s)", flush=True)

# EVERY-10TH DATE SAMPLE = ~178 dates
samp_idx = np.arange(0, nd, 10)
sds = ds_arr[samp_idx]; sde = de_arr[samp_idx]; snd = len(samp_idx)
print(f"Sample: {snd} dates ({time.time()-t0:.0f}s)", flush=True)

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

def ftn(fv, rv, tn, _ds, _de, _nd):
    daily = np.full(_nd, np.nan)
    for i in range(_nd):
        s,e=_ds[i],_de[i]; f=fv[s:e]; r=rv[s:e]
        m=np.isfinite(f)&np.isfinite(r); cnt=np.sum(m)
        if cnt<tn+2: continue
        f2=np.ascontiguousarray(f[m]); r2=np.ascontiguousarray(r[m])
        idx=np.argpartition(f2,-tn)[-tn:]
        daily[i]=np.mean(r2[idx])
    return daily

def tst(fv, hk, tn, samp=True):
    rv = [H1,H5,HM][hk]
    if samp: return ftn(fv,rv,tn,sds,sde,snd)
    else: return ftn(fv,rv,tn,ds_arr,de_arr,nd)

def add(r, f, tn, hk, tp):
    r['strat']=f"rank={f}|top{tn}|{['1d','5d','1mo'][hk]}"; r['feat']=f; r['tn']=tn
    r['hold']=['1d','5d','1mo'][hk]; r['type']=tp; return r

all_results = []

# =========================================================================
# PHASE 1: ALL SINGLE BASE FEATURES (raw, log, sq, above0)
# =========================================================================
print(f"\n[PHASE 1] {len(BASE)} base x 4 transforms x 5 topN x 3 holds", flush=True)
t0p = time.time(); cnt = 0
for bname, bvals in B.items():
    transforms = {
        bname: bvals,
        f"{bname}_log": np.log1p(np.abs(bvals))*np.sign(bvals),
        f"{bname}_sq": bvals**2,
        f"{bname}_above0": (bvals>0).astype(float),
    }
    for fname, fvals in transforms.items():
        for tn in [5,10,15,20,30]:
            for hk in range(3):
                st = fs(tst(fvals, hk, tn))
                if st: all_results.append(add(st, fname, tn, hk, 'single'))
                cnt += 1
    if cnt%500==0:
        print(f"  {cnt} ({time.time()-t0p:.0f}s) res={len(all_results)}", flush=True)
print(f"  Phase 1: {cnt} ({time.time()-t0p:.0f}s)", flush=True)

# =========================================================================
# PHASE 2: PAIR SUMS (top 15 base features)
# =========================================================================
print(f"\n[PHASE 2] Pair sums top 15...", flush=True)
t0p = time.time()
res_df = pd.DataFrame(all_results)
top15 = res_df.sort_values('sharpe', ascending=False)['feat'].unique()[:15]
top15 = [f for f in top15 if f in B][:15]

cnt = 0
for i in range(len(top15)):
    for j in range(i+1, len(top15)):
        combo = B[top15[i]] + B[top15[j]]
        cn = f"{top15[i]}+{top15[j]}"
        for hk in range(3):
            for tn in [10,15,20]:
                st = fs(tst(combo, hk, tn))
                if st: all_results.append(add(st, cn, tn, hk, 'pair_sum'))
                cnt += 1
    if (i+1)%5==0:
        print(f"  {i+1}/{len(top15)} ({time.time()-t0p:.0f}s) res={len(all_results)}", flush=True)
print(f"  Phase 2: {cnt} ({time.time()-t0p:.0f}s)", flush=True)

# =========================================================================
# PHASE 3: PAIR PRODUCTS (top 15 base)
# =========================================================================
print(f"\n[PHASE 3] Pair products top 15...", flush=True)
t0p = time.time()
cnt = 0
for i in range(len(top15)):
    for j in range(i+1, len(top15)):
        combo = B[top15[i]] * B[top15[j]]
        cn = f"{top15[i]}*{top15[j]}"
        for hk in range(3):
            st = fs(tst(combo, hk, 15))
            if st: all_results.append(add(st, cn, 15, hk, 'pair_prod'))
            cnt += 1
print(f"  Phase 3: {cnt} ({time.time()-t0p:.0f}s)", flush=True)

# =========================================================================
# PHASE 4: PAIR RATIOS (top 12 base)
# =========================================================================
print(f"\n[PHASE 4] Pair ratios top 12...", flush=True)
t0p = time.time()
top12 = top15[:12]
cnt = 0
for i in range(len(top12)):
    for j in range(len(top12)):
        if i==j: continue
        combo = np.where(np.abs(B[top12[j]])>1e-6, B[top12[i]]/np.abs(B[top12[j]]), 0)
        cn = f"{top12[i]}/{top12[j]}"
        for hk in range(3):
            st = fs(tst(combo, hk, 15))
            if st: all_results.append(add(st, cn, 15, hk, 'pair_ratio'))
            cnt += 1
print(f"  Phase 4: {cnt} ({time.time()-t0p:.0f}s)", flush=True)

# =========================================================================
# PHASE 5: WEIGHTED PAIRS (top 10 base)
# =========================================================================
print(f"\n[PHASE 5] Weighted pairs top 10...", flush=True)
t0p = time.time()
top10 = top15[:10]
cnt = 0
for i in range(len(top10)):
    for j in range(i+1, len(top10)):
        v1,v2 = B[top10[i]], B[top10[j]]
        for w in [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9]:
            combo = w*v1 + (1-w)*v2
            cn = f"{w:.1f}*{top10[i]}+{1-w:.1f}*{top10[j]}"
            for hk in range(3):
                st = fs(tst(combo, hk, 15))
                if st: all_results.append(add(st, cn, 15, hk, 'weighted'))
                cnt += 1
print(f"  Phase 5: {cnt} ({time.time()-t0p:.0f}s)", flush=True)

# =========================================================================
# PHASE 6: TRIPLES (top 8 base)
# =========================================================================
print(f"\n[PHASE 6] Triples top 8...", flush=True)
t0p = time.time()
top8 = top15[:8]
cnt = 0
for i in range(len(top8)):
    for j in range(i+1, len(top8)):
        for k in range(j+1, len(top8)):
            combo = B[top8[i]]+B[top8[j]]+B[top8[k]]
            cn = f"{top8[i]}+{top8[j]}+{top8[k]}"
            for hk in range(3):
                st = fs(tst(combo, hk, 15))
                if st: all_results.append(add(st, cn, 15, hk, 'triple'))
                cnt += 1
print(f"  Phase 6: {cnt} ({time.time()-t0p:.0f}s)", flush=True)

# =========================================================================
# PHASE 7: BINARY FILTER combos
# =========================================================================
print(f"\n[PHASE 7] Binary filter combos...", flush=True)
t0p = time.time()
BINS = [('atr_crossed_above',B['atr_crossed_above']),
        ('accel_crossed_up',B['accel_crossed_up']),
        ('accel_crossed_down',B['accel_crossed_down'])]
cnt = 0
for bn,bv in BINS:
    for feat in top10:
        combo = bv * B[feat]
        cn = f"{bn}*{feat}"
        for hk in range(3):
            for tn in [10,15,20]:
                st = fs(tst(combo, hk, tn))
                if st: all_results.append(add(st, cn, tn, hk, 'binary_filter'))
                cnt += 1

# Double binary
for (b1n,b1v),(b2n,b2v) in itertools.combinations(BINS,2):
    bv2 = b1v*b2v
    for feat in top10:
        combo = bv2 * B[feat]
        cn = f"{b1n}*{b2n}*{feat}"
        for hk in range(3):
            st = fs(tst(combo, hk, 15))
            if st: all_results.append(add(st, cn, 15, hk, 'binary_filter'))
            cnt += 1
print(f"  Phase 7: {cnt} ({time.time()-t0p:.0f}s)", flush=True)

# =========================================================================
# PHASE 8: KEY COMPOSITES
# =========================================================================
print(f"\n[PHASE 8] Composites...", flush=True)
t0p = time.time()
wa=B['weighted_alpha']; aa=B['accel_a']; sv=B['atr_value']; ss=B['atr_streak']
pst=B['prob_up_st_cross']; ai=B['ai_overall_score']; st_v=B['streak']
p1=B['prob_up_1d']; p5=B['prob_up_5d']; atr=B['atrp']

comps = {
    'accel_div_atr': np.where(np.abs(sv)>1e-6, aa/np.abs(sv), 0),
    'wa_div_atr': np.where(np.abs(sv)>1e-6, wa/np.abs(sv), 0),
    'wa_04_a_03_atr_03': wa*0.4+aa*0.3+sv*0.3,
    'wa_03_pst_03_a_02_ss_02': wa*0.3+pst*0.3+aa*0.2+ss*0.2,
    'wa_a_pst': wa*aa*pst,
    'wa_a_atr': wa*aa*sv,
    'wa_x_pst': wa*pst,
    'ai_x_wa': ai*wa,
    'ai_x_accel': ai*aa,
    'prob_avg': (p1+p5+pst)/3,
    'prob_prod': p1*p5*pst,
    'accel_x_streak': aa*st_v,
    'wa_x_accel_x_atr': wa*aa*sv,
    'wa_x_accel_x_pst': wa*aa*pst,
}

cnt = 0
for cn, cv in comps.items():
    for tn in [5,10,15,20,30]:
        for hk in range(3):
            st = fs(tst(cv, hk, tn))
            if st: all_results.append(add(st, cn, tn, hk, 'composite'))
            cnt += 1
print(f"  Phase 8: {cnt} ({time.time()-t0p:.0f}s)", flush=True)

# =========================================================================
# VERIFY TOP 100 ON FULL DATA
# =========================================================================
print(f"\n[VERIFY] Top 100 on all {nd} dates...", flush=True)
t0v = time.time()
res_all = pd.DataFrame(all_results)
top100 = res_all.drop_duplicates('strat').sort_values('sharpe', ascending=False).head(100)

verified = []
for _, row in top100.iterrows():
    fname = row['feat']; hk = row['hold']; tn = int(row['tn'])
    hk_idx = {'1d':0,'5d':1,'1mo':2}[hk]
    
    fvals = None
    if fname in B: fvals = B[fname]
    elif fname in comps: fvals = comps[fname]
    elif '+' in fname and '*' not in fname and '/' not in fname:
        parts = fname.split('+')
        if all(p in B for p in parts): fvals = sum(B[p] for p in parts)
    elif '*' in fname and '+' not in fname:
        parts = fname.split('*')
        if all(p in B for p in parts):
            fvals = B[parts[0]]
            for p in parts[1:]: fvals = fvals * B[p]
    elif '/' in fname:
        parts = fname.split('/')
        if parts[0] in B and parts[1] in B:
            fvals = np.where(np.abs(B[parts[1]])>1e-6, B[parts[0]]/np.abs(B[parts[1]]), 0)
    elif fname.endswith('_log'):
        base = fname[:-4]
        if base in B: fvals = np.log1p(np.abs(B[base]))*np.sign(B[base])
    elif fname.endswith('_sq'):
        base = fname[:-3]
        if base in B: fvals = B[base]**2
    elif fname.endswith('_above0'):
        base = fname[:-7]
        if base in B: fvals = (B[base]>0).astype(float)
    elif any(fname.startswith(f"{bn}*") for bn,_ in BINS):
        parts = fname.split('*')
        if len(parts)==2 and parts[0] in dict(BINS) and parts[1] in B:
            fvals = dict(BINS)[parts[0]] * B[parts[1]]
        elif len(parts)==3:
            b1 = dict(BINS).get(parts[0])
            b2 = dict(BINS).get(parts[1])
            if b1 is not None and b2 is not None and parts[2] in B:
                fvals = b1 * b2 * B[parts[2]]
    
    if fvals is None: continue
    
    daily = ftn(fvals, [H1,H5,HM][hk_idx], tn, ds_arr, de_arr, nd)
    st = fs(daily)
    if st:
        st['strat']=row['strat']; st['feat']=fname; st['tn']=tn
        st['hold']=hk; st['type']=row.get('type','')
        verified.append(st)

print(f"  Verified {len(verified)} ({time.time()-t0v:.0f}s)", flush=True)

# =========================================================================
# OUTPUT
# ===========================================================================
print(f"\n[OUTPUT]", flush=True)
seen = set()
unique = [r for r in verified if r['strat'] not in seen and not seen.add(r['strat'])]

with open(os.path.join(OUTPUT, 'monster_no_lookahead.json'), 'w') as f:
    json.dump(unique, f, indent=2, default=str)

df_r = pd.DataFrame(unique)
df_r['score'] = df_r['sharpe'] * df_r['rsq'] / (df_r['vol'] + 0.001)

sep = "="*160
for hi, hl in enumerate(['NEXT-DAY (BTST)','NEXT-5-DAY','NEXT-MONTH']):
    hdf = df_r[df_r['hold']==['1d','5d','1mo'][hi]]
    if len(hdf)==0: continue
    print(f"\n{sep}")
    print(f"  {hl} -- {len(hdf)} strategies (VERIFIED {nd} dates, ZERO look-ahead)")
    print(sep)
    for col, asc, cat in [('sharpe',False,'SHARPE'),('cagr',False,'CAGR'),
                           ('mdd',True,'MDD'),('vol',True,'VOL'),('rsq',False,'LINEAR'),
                           ('wr',False,'WR'),('score',False,'BALANCED')]:
        top = hdf.sort_values(col, ascending=asc).head(10)
        print(f"\n  [{cat}]")
        for _, r in top.iterrows():
            print(f"    Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.2f}% MDD={r['mdd']*100:>7.2f}% "
                  f"Vol={r['vol']*100:>6.2f}% WR={r['wr']*100:>5.1f}% PF={r['pf']:>5.2f} R2={r['rsq']:>5.3f} "
                  f"N={r['n']:>4}  {r['strat'][:110]}")

print(f"\n{sep}")
print(f"  GLOBAL TOP 50 BALANCED")
print(sep)
for i, (_, r) in enumerate(df_r.sort_values('score', ascending=False).head(50).iterrows()):
    print(f"  #{i+1:2d} Score={r['score']:>6.3f} Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.2f}% "
          f"MDD={r['mdd']*100:>7.2f}% Vol={r['vol']*100:>6.2f}% WR={r['wr']*100:>5.1f}% R2={r['rsq']:>5.3f} "
          f"N={r['n']:>4}  {r['strat'][:110]}")

print(f"\n{len(unique)} unique strategies, total {time.time()-t0:.0f}s")
print("DONE")
