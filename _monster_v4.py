"""
MONSTER STRATEGY FINDER v4 - BLAZING FAST
- Pre-screens features on 200 dates, then full sweep on top features
- Uses numpy vectorized per-date rank via argsort + cumulative approach
"""
import numpy as np, pandas as pd, sys, io, os, time, json, itertools, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*100)
print("  MONSTER STRATEGY FINDER v4 - BLAZING")
print("="*100, flush=True)

# 1. LOAD
t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
df = df[df['price'] >= 1.0].copy()
df = df.sort_values('date').reset_index(drop=True)
print(f"Loaded {len(df)} rows, {df['date'].nunique()} dates ({time.time()-t0:.0f}s)", flush=True)

# Date index
dates_u = df['date'].values
nd = len(np.unique(dates_u))
ds = np.searchsorted(dates_u, np.unique(dates_u), side='left')
de = np.searchsorted(dates_u, np.unique(dates_u), side='right')

# Column arrays
c = {}
for col in df.columns:
    c[col] = df[col].values

# Features
a = c['accel_a']; b = c['accel_base']; wa = c['weighted_alpha']
sv = c['atr_value']; ss = c['atr_streak']; atr = c['atrp']
st = c['streak']; pst = c['prob_up_st_cross']
p1 = c['prob_up_1d']; p5 = c['prob_up_5d']
ai_o = c['ai_overall_score']; ai_t = c['ai_tech_score']
ai_m = c['ai_momentum_score']; ai_v = c['ai_volume_score']
ch = c['change_pct']; pr = c['price']

F = {}
F['weighted_alpha'] = wa; F['atrp'] = atr; F['streak'] = st
F['atr_value'] = sv; F['atr_streak'] = ss; F['accel_a'] = a; F['accel_base'] = b
F['prob_up_1d'] = p1; F['prob_up_5d'] = p5; F['prob_up_st_cross'] = pst; F['change_pct'] = ch

F['accel_a_pos'] = np.maximum(a,0); F['accel_a_abs'] = np.abs(a)
F['accel_base_pos'] = np.maximum(b,0)
F['accel_ratio'] = np.where(np.abs(b)>0.001, a/b, 0)
F['accel_diff'] = a-b; F['accel_sum'] = a+b; F['accel_product'] = a*b
F['accel_sq'] = a**2; F['accel_log'] = np.log1p(np.abs(a))*np.sign(a)

F['atr_value_abs'] = np.abs(sv); F['atr_streak_abs'] = np.abs(ss)
F['atr_product'] = sv*ss; F['atr_sq'] = sv**2
F['atr_log'] = np.log1p(np.abs(sv))*np.sign(sv)
F['atr_pct_x_streak'] = atr*ss; F['atr_pct_x_value'] = atr*sv

F['wa_pos'] = np.maximum(wa,0); F['wa_abs'] = np.abs(wa)
F['wa_sq'] = wa**2; F['wa_log'] = np.log1p(np.abs(wa))*np.sign(wa)

F['wa_x_accel'] = wa*a; F['wa_x_atr'] = wa*sv; F['wa_x_streak'] = wa*st
F['accel_x_atr'] = a*sv; F['accel_x_streak'] = a*ss
F['wa_accel_atr'] = wa*a*sv; F['wa_accel_streak'] = wa*a*ss
F['wa_div_accel'] = np.where(np.abs(a)>0.001, wa/np.abs(a), 0)
F['wa_div_atr'] = np.where(np.abs(sv)>0.001, wa/np.abs(sv), 0)
F['accel_div_atr'] = np.where(np.abs(sv)>0.001, a/np.abs(sv), 0)

F['prob_avg'] = (p1+p5+pst)/3; F['prob_product'] = p1*p5*pst
F['prob_wa'] = wa*pst; F['prob_accel'] = a*pst; F['prob_accel_wa'] = wa*a*pst

F['streak_x_wa'] = st*wa; F['streak_x_accel'] = st*a; F['streak_x_atr'] = st*sv

F['ai_tech_x_wa'] = ai_t*wa; F['ai_mom_x_wa'] = ai_m*wa
F['ai_tech_x_accel'] = ai_t*a; F['ai_mom_x_accel'] = ai_m*a
F['ai_overall_x_wa'] = ai_o*wa; F['ai_overall_x_accel'] = ai_o*a

F['composite_1'] = wa*0.4+a*0.3+sv*0.3
F['composite_2'] = wa*0.3+pst*0.3+a*0.2+ss*0.2
F['composite_3'] = wa*0.33+a*0.33+sv*0.34
F['composite_4'] = ai_o*0.3+wa*0.3+a*0.2+sv*0.2
F['composite_5'] = pst*0.4+a*0.3+wa*0.3
F['composite_6'] = wa*a*pst

F['triple_wa_accel_atr'] = wa*a*sv
F['triple_wa_accel_streak'] = wa*a*ss
F['triple_wa_accel_prob'] = wa*a*pst

F['wa_above_0'] = (wa>0).astype(float)
F['accel_above_0'] = (a>0).astype(float)
F['atr_above_0'] = (sv>0).astype(float)
F['streak_above_0'] = (st>0).astype(float)

F['price_x_wa'] = pr*wa; F['change_x_wa'] = ch*wa; F['change_x_accel'] = ch*a
F['pct_accel'] = atr*a

print(f"{len(F)} features ({time.time()-t0:.0f}s)", flush=True)

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
# FAST TOP-N via pre-computed argpartition per date
###############################################################################
def fast_topn(feat_vals, ret_vals, tn):
    daily = np.full(nd, np.nan)
    for i in range(nd):
        s=ds[i]; e=de[i]
        fv=feat_vals[s:e]; rv=ret_vals[s:e]
        m = np.isfinite(fv)&np.isfinite(rv)
        if np.sum(m)<tn: continue
        f=fv[m]; r=rv[m]
        idx = np.argpartition(f,-tn)[-tn:]
        daily[i]=np.mean(r[idx])
    return daily

###############################################################################
# PHASE 1: Pre-screen on 200 dates, then full sweep top features
###############################################################################
print("\n[PHASE 1] Pre-screen on 200 dates...", flush=True)
t0 = time.time()
sample_idx = np.linspace(0, nd-1, 200, dtype=int)
holds = {'1d': c['ret_1d'], '5d': c['ret_5d'], '1mo': c['ret_1mo']}

screen_scores = {}
for fname, fvals in F.items():
    for hname, rvals in holds.items():
        daily = np.full(200, np.nan)
        for j, i in enumerate(sample_idx):
            s=ds[i]; e=de[i]
            fv=fvals[s:e]; rv=rvals[s:e]
            m = np.isfinite(fv)&np.isfinite(rv)
            if np.sum(m)<10: continue
            f=fv[m]; r=rv[m]
            idx = np.argpartition(f,-10)[-10:]
            daily[j]=np.mean(r[idx])
        r = daily[np.isfinite(daily)]
        if len(r)>20:
            sh = np.mean(r)/(np.std(r,ddof=1)+1e-10)*np.sqrt(252)
            screen_scores[f"{fname}|{hname}"] = sh

print(f"  Screened {len(screen_scores)} ({time.time()-t0:.0f}s)", flush=True)

# Top 25 features by screen sharpe
top25 = sorted(screen_scores.items(), key=lambda x: x[1], reverse=True)[:25]
top25_names = list(set(k.split('|')[0] for k,_ in top25))
print(f"  Top features: {top25_names[:15]}", flush=True)

# Full sweep on top features
print(f"\n[PHASE 2] Full sweep on {len(top25_names)} features...", flush=True)
t0 = time.time()
top_ns = [5, 10, 15, 20, 30]
all_results = []
cnt = 0

for fname in top25_names:
    fvals = F[fname]
    for hname, rvals in holds.items():
        for tn in top_ns:
            daily = fast_topn(fvals, rvals, tn)
            st = fs(daily)
            if st:
                st['strat'] = f"rank={fname}|top{tn}|{hname}"
                st['feat'] = fname; st['tn'] = tn; st['hold'] = hname
                all_results.append(st)
            cnt += 1

print(f"  {cnt} tested ({time.time()-t0:.0f}s)", flush=True)

# Also test ALL features with top15 only for broader coverage
print(f"\n[PHASE 3] Quick sweep all features (top15 only)...", flush=True)
t0 = time.time()
cnt3 = 0
for fname, fvals in F.items():
    if fname in top25_names: continue
    for hname, rvals in holds.items():
        daily = fast_topn(fvals, rvals, 15)
        st = fs(daily)
        if st:
            st['strat'] = f"rank={fname}|top15|{hname}"
            st['feat'] = fname; st['tn'] = 15; st['hold'] = hname
            all_results.append(st)
        cnt3 += 1
print(f"  {cnt3} tested ({time.time()-t0:.0f}s)", flush=True)

# DUAL COMBOS
print(f"\n[PHASE 4] Dual combos (top 15 features)...", flush=True)
t0 = time.time()
res_df = pd.DataFrame(all_results)
top15 = res_df.sort_values('sharpe', ascending=False)['feat'].unique()[:15]

cnt4 = 0
for f1, f2 in itertools.combinations(top15, 2):
    combo = F[f1] + F[f2]
    for hname, rvals in holds.items():
        for tn in [10, 15, 20]:
            daily = fast_topn(combo, rvals, tn)
            st = fs(daily)
            if st:
                st['strat'] = f"rank=({f1}+{f2})|top{tn}|{hname}"
                st['feat'] = f"{f1}+{f2}"; st['tn'] = tn; st['hold'] = hname
                all_results.append(st)
            cnt4 += 1
print(f"  {cnt4} combos ({time.time()-t0:.0f}s)", flush=True)

# TRIPLE COMBOS
print(f"\n[PHASE 5] Triple combos (top 8)...", flush=True)
t0 = time.time()
res_df2 = pd.DataFrame(all_results)
top8 = res_df2.sort_values('sharpe', ascending=False)['feat'].unique()[:8]

cnt5 = 0
for f1, f2, f3 in itertools.combinations(top8, 3):
    combo = F[f1] + F[f2] + F[f3]
    for hname, rvals in holds.items():
        for tn in [10, 15]:
            daily = fast_topn(combo, rvals, tn)
            st = fs(daily)
            if st:
                st['strat'] = f"rank=({f1}+{f2}+{f3})|top{tn}|{hname}"
                st['feat'] = f"{f1}+{f2}+{f3}"; st['tn'] = tn; st['hold'] = hname
                all_results.append(st)
            cnt5 += 1
print(f"  {cnt5} combos ({time.time()-t0:.0f}s)", flush=True)

# WEIGHTED COMBOS
print(f"\n[PHASE 6] Weighted combos (top 10)...", flush=True)
t0 = time.time()
res_df3 = pd.DataFrame(all_results)
top10 = res_df3.sort_values('sharpe', ascending=False)['feat'].unique()[:10]

cnt6 = 0
for f1, f2 in itertools.combinations(top10, 2):
    v1=F[f1]; v2=F[f2]
    for w1,w2 in [(0.7,0.3),(0.6,0.4),(0.5,0.5),(0.8,0.2)]:
        combo = w1*v1 + w2*v2
        for hname, rvals in holds.items():
            for tn in [10, 15]:
                daily = fast_topn(combo, rvals, tn)
                st = fs(daily)
                if st:
                    st['strat'] = f"rank={w1:.1f}*{f1}+{w2:.1f}*{f2}|top{tn}|{hname}"
                    st['feat'] = f"{w1}*{f1}+{w2}*{f2}"; st['tn'] = tn; st['hold'] = hname
                    all_results.append(st)
                cnt6 += 1
print(f"  {cnt6} combos ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# RANK & OUTPUT
###############################################################################
print(f"\n[RANK] Saving {len(all_results)} unique strategies...", flush=True)
seen = set()
unique = [r for r in all_results if r['strat'] not in seen and not seen.add(r['strat'])]
all_results = unique

with open(os.path.join(OUTPUT, 'monster_results.json'), 'w') as f:
    json.dump(all_results, f, indent=2, default=str)

df_r = pd.DataFrame(all_results)
df_r['score'] = df_r['sharpe'] * df_r['rsq'] / (df_r['vol'] + 0.001)

sep = "="*140
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
            print(f"    Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% PF={r['pf']:>5.2f} R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:90]}")

print(f"\n{sep}")
print(f"  GLOBAL TOP 30 BALANCED")
print(sep)
for i, (_, r) in enumerate(df_r.sort_values('score', ascending=False).head(30).iterrows()):
    print(f"  #{i+1:2d} Score={r['score']:>6.3f} Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:90]}")

print(f"\nTOTAL: {len(all_results)} unique strategies")
print("DONE")
