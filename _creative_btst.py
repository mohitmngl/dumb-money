"""Creative BTST Finder v3 - With proper liquidity filters."""
import numpy as np, pandas as pd, sys, io, os, time, json, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*100)
print("  CREATIVE BTST FINDER v3 - LIQUID STOCKS ONLY")
print("="*100, flush=True)

t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
df = df[df['price'] >= 1.0].copy()
df['date'] = pd.to_datetime(df['date'])
df['ret'] = df['next_day_return'] / 100.0
df = df.sort_values(['date','symbol']).reset_index(drop=True)

# LIQUIDITY FILTER: avg volume > 100K over last 24 months, avg ATRP > 2%
cutoff = pd.Timestamp.now() - pd.DateOffset(months=24)
df24 = df[df['date'] >= cutoff].copy()
sym_stats = df24.groupby('symbol').agg(avg_vol=('volume','mean'), avg_atrp=('atrp','mean'), nd=('date','count')).reset_index()

# Require: avg vol > 100K, avg ATRP > 2%, at least 400 dates in 24mo
LIQUID = set(sym_stats[(sym_stats['avg_vol'] > 100000) & (sym_stats['avg_atrp'] > 2.0) & (sym_stats['nd'] >= 400)]['symbol'])
print(f"Liquid stocks (vol>100K, ATRP>2%, 400+ days): {len(LIQUID)} of {len(sym_stats)}", flush=True)

df = df[df['symbol'].isin(LIQUID)].copy()
df = df.sort_values(['date','symbol']).reset_index(drop=True)

dates_u = np.sort(df['date'].unique())
nd = len(dates_u)
ds_arr = np.searchsorted(df['date'].values, dates_u, side='left')
de_arr = np.searchsorted(df['date'].values, dates_u, side='right')
mask_24m = dates_u >= cutoff

print(f"Data: {len(df)} rows, {df['symbol'].nunique()} stocks, {nd} dates ({time.time()-t0:.0f}s)", flush=True)

# Extract arrays
p=df['price'].values.astype(np.float64); ch=df['change_pct'].values.astype(np.float64)
vol=df['volume'].values.astype(np.float64); wa=df['weighted_alpha'].values.astype(np.float64)
atrp_v=df['atrp'].values.astype(np.float64); streak=df['streak'].values.astype(np.float64)
atr_val=df['atr_value'].values.astype(np.float64); atr_stk=df['atr_streak'].values.astype(np.float64)
aa=df['accel_a'].values.astype(np.float64); ab=df['accel_base'].values.astype(np.float64)
pst=df['prob_up_st_cross'].values.astype(np.float64); p1=df['prob_up_1d'].values.astype(np.float64)
p5=df['prob_up_5d'].values.astype(np.float64); ai_o=df['ai_overall_score'].values.astype(np.float64)
ai_t=df['ai_tech_score'].values.astype(np.float64); ai_m=df['ai_momentum_score'].values.astype(np.float64)
ret_arr=df['ret'].values.astype(np.float64)

print("Building features...", flush=True)
t1 = time.time()

def cs_z(arr):
    out=np.full_like(arr,np.nan)
    for i in range(nd):
        s,e=ds_arr[i],de_arr[i]; v=arr[s:e]; m=np.isfinite(v)
        if np.sum(m)<5: continue
        vv=v[m]; mu=np.mean(vv); sd=np.std(vv)
        if sd>1e-10: out[s:e][m]=(v[m]-mu)/sd
    return out

def cs_rk(arr):
    out=np.full_like(arr,np.nan)
    for i in range(nd):
        s,e=ds_arr[i],de_arr[i]; v=arr[s:e]; m=np.isfinite(v); cnt=np.sum(m)
        if cnt<5: continue
        out[s:e][m]=np.argsort(np.argsort(v[m])).astype(float)/max(cnt-1,1)
    return out

D = {}
raw = [('wa',wa),('atrp',atrp_v),('streak',streak),('atr_val',atr_val),('atr_streak',atr_stk),
       ('accel_a',aa),('accel_base',ab),('prob_st',pst),('prob1',p1),('prob5',p5),
       ('change',ch),('ai_o',ai_o),('ai_t',ai_t),('ai_m',ai_m),('volume',vol)]
for n,v in raw: D[n]=v

for n,v in [('wa',wa),('atrp',atrp_v),('streak',streak),('accel_a',aa),('accel_base',ab),
            ('prob_st',pst),('change',ch),('ai_o',ai_o),('ai_t',ai_t),('ai_m',ai_m),
            ('volume',vol),('prob1',p1),('prob5',p5),('atr_val',atr_val),('atr_streak',atr_stk)]:
    D[f'z_{n}']=cs_z(v)

for n,v in [('wa',wa),('atrp',atrp_v),('streak',streak),('accel_a',aa),('prob_st',pst),
            ('change',ch),('ai_o',ai_o),('volume',vol),('atr_val',atr_val),('atr_streak',atr_stk)]:
    D[f'r_{n}']=cs_rk(v)

for n,v in [('wa',wa),('accel_a',aa),('accel_base',ab),('prob_st',pst),('streak',streak),
            ('change',ch),('ai_o',ai_o),('ai_t',ai_t),('prob1',p1),('prob5',p5),('atr_streak',atr_stk)]:
    D[f'{n}_div_atr']=np.where(np.abs(atr_val)>1e-6,v/np.abs(atr_val),0)
    D[f'{n}_div_atrp']=np.where(np.abs(atrp_v)>1e-6,v/np.abs(atrp_v),0)

for n1,v1,n2,v2 in [('wa',wa,'accel_a',aa),('wa',wa,'prob_st',pst),('wa',wa,'streak',streak),
    ('wa',wa,'atrp',atrp_v),('accel_a',aa,'prob_st',pst),('accel_a',aa,'streak',streak),
    ('prob_st',pst,'streak',streak),('ai_o',ai_o,'wa',wa),('ai_o',ai_o,'accel_a',aa),
    ('ai_o',ai_o,'prob_st',pst),('change',ch,'wa',wa),('change',ch,'accel_a',aa),
    ('prob1',p1,'prob5',p5),('prob1',p1,'prob_st',pst),('prob5',p5,'prob_st',pst)]:
    D[f'{n1}_x_{n2}']=v1*v2

D['wa_plus_accel']=wa+aa; D['wa_plus_prob']=wa+pst; D['wa_plus_streak']=wa+streak
D['accel_plus_prob']=aa+pst; D['wa_accel_prob']=wa+aa+pst
D['wa_accel_prob_streak']=wa+aa+pst+streak; D['ai_wa_accel']=ai_o+wa+aa
D['prob_avg']=(p1+p5+pst)/3; D['streak_plus_wa']=streak+wa; D['streak_plus_accel']=streak+aa

D['comp_1']=wa*0.4+aa*0.3+atr_val*0.3; D['comp_2']=wa*0.3+pst*0.3+aa*0.2+atr_stk*0.2
D['comp_3']=ai_o*0.3+wa*0.3+aa*0.2+atr_val*0.2; D['comp_4']=pst*0.4+aa*0.3+wa*0.3
D['comp_5']=wa*0.25+aa*0.25+pst*0.25+ai_o*0.25; D['comp_6']=wa*0.5+aa*0.5
D['comp_7']=pst*0.5+aa*0.5; D['comp_8']=ai_o*0.5+wa*0.5

D['zz_wa_accel']=D['z_wa']+D['z_accel_a']; D['zz_wa_prob']=D['z_wa']+D['z_prob_st']
D['zz_wa_x_accel']=D['z_wa']*D['z_accel_a']; D['zz_wa_x_prob']=D['z_wa']*D['z_prob_st']
D['zz_accel_x_prob']=D['z_accel_a']*D['z_prob_st']
D['zz_composite']=D['z_wa']*0.4+D['z_accel_a']*0.3+D['z_prob_st']*0.3
D['zz_ai_composite']=D['z_ai_o']*0.5+D['z_wa']*0.3+D['z_accel_a']*0.2
D['zz_all_mom']=D['z_wa']*0.3+D['z_accel_a']*0.3+D['z_streak']*0.2+D['z_prob_st']*0.2

D['rr_wa_accel']=(D['r_wa']+D['r_accel_a'])/2; D['rr_wa_x_accel']=D['r_wa']*D['r_accel_a']
D['rr_composite']=D['r_wa']*0.4+D['r_accel_a']*0.3+D['r_prob_st']*0.3

D['z_wa_gt1']=(D['z_wa']>1).astype(float); D['z_accel_gt1']=(D['z_accel_a']>1).astype(float)
D['z_prob_gt1']=(D['z_prob_st']>1).astype(float)
D['z_wa_accel_gt1']=D['z_wa_gt1']*D['z_accel_gt1']
D['z_all3_gt1']=D['z_wa_gt1']*D['z_accel_gt1']*D['z_prob_gt1']
D['r_both_gt05']=(D['r_wa']>0.5).astype(float)*(D['r_accel_a']>0.5).astype(float)

for n,v in [('wa',wa),('accel_a',aa),('atr_val',atr_val),('volume',vol),('atr_streak',atr_stk),('prob_st',pst)]:
    D[f'{n}_log']=np.log1p(np.abs(v))*np.sign(v)
    D[f'{n}_sq']=v**2

FEAT = {k:v for k,v in D.items() if np.isfinite(v).mean()>0.5}
print(f"  {len(FEAT)} features ({time.time()-t1:.0f}s)", flush=True)

samp_idx = np.arange(0, nd, 4)
sds=ds_arr[samp_idx]; sde=de_arr[samp_idx]; snd=len(samp_idx)
print(f"  Sample: {snd} dates", flush=True)

def fs(r):
    r=r[np.isfinite(r)]; n=len(r)
    if n<15: return None
    cl=np.cumsum(np.log1p(r)); cc=np.exp(cl)
    tr=float(cc[-1]-1); sd=float(np.std(r,ddof=1))
    ar=float((1+tr)**(252/n)-1) if tr>-1 else -1
    av=float(sd*np.sqrt(252))
    sh=float(np.mean(r)/sd*np.sqrt(252)) if sd>1e-10 else 0
    rm=np.maximum.accumulate(cc); mdd=float(np.min((cc-rm)/rm))
    wr=float(np.mean(r>0))
    gp=float(np.sum(r[r>0])); gl=float(np.abs(np.sum(r[r<0])))
    pf=gp/gl if gl>0 else 0
    return dict(sharpe=round(sh,3),cagr=round(ar,4),vol=round(av,4),
                mdd=round(mdd,4),wr=round(wr,4),pf=round(pf,3),n=n)

def ftn(fv, rv, tn, _ds, _de, _nd):
    daily=np.full(_nd,np.nan)
    for i in range(_nd):
        s,e=_ds[i],_de[i]; f=fv[s:e]; r=rv[s:e]
        m=np.isfinite(f)&np.isfinite(r); cnt=np.sum(m)
        if cnt<tn+2: continue
        f2=np.ascontiguousarray(f[m]); r2=np.ascontiguousarray(r[m])
        idx=np.argpartition(f2,-tn)[-tn:]
        daily[i]=np.mean(r2[idx])
    return daily

all_results = []
T5=5; T10=10; T15=15; T20=20; T30=30

# SINGLES
t2=time.time(); cnt=0
for fname, fvals in FEAT.items():
    for tn in [T5,T10,T15,T20,T30]:
        daily=ftn(fvals,ret_arr,tn,sds,sde,snd)
        st=fs(daily)
        if st:
            st['strat']=f"rank={fname}|top{tn}"; st['feat']=fname; st['tn']=tn; st['type']='single'
            all_results.append(st)
        cnt+=1
print(f"Singles: {cnt} ({time.time()-t2:.0f}s) res={len(all_results)}", flush=True)

res_df=pd.DataFrame(all_results)
top_feats=res_df.sort_values('sharpe',ascending=False)['feat'].unique()

# PAIR SUMS (top 30)
t2=time.time(); cnt=0; top30=top_feats[:30]
for i in range(len(top30)):
    for j in range(i+1,len(top30)):
        k1,k2=top30[i],top30[j]
        combo=FEAT[k1]+FEAT[k2]; cn=f"{k1}+{k2}"
        for tn in [T10,T15,T20]:
            daily=ftn(combo,ret_arr,tn,sds,sde,snd)
            st=fs(daily)
            if st:
                st['strat']=f"rank={cn}|top{tn}"; st['feat']=cn; st['tn']=tn; st['type']='pair_sum'
                all_results.append(st)
            cnt+=1
print(f"Pair sums: {cnt} ({time.time()-t2:.0f}s) res={len(all_results)}", flush=True)

# PAIR PRODUCTS (top 30)
t2=time.time(); cnt=0
for i in range(len(top30)):
    for j in range(i+1,len(top30)):
        k1,k2=top30[i],top30[j]
        combo=FEAT[k1]*FEAT[k2]; cn=f"{k1}*{k2}"
        daily=ftn(combo,ret_arr,T15,sds,sde,snd)
        st=fs(daily)
        if st:
            st['strat']=f"rank={cn}|top15"; st['feat']=cn; st['tn']=T15; st['type']='pair_prod'
            all_results.append(st)
        cnt+=1
print(f"Pair prods: {cnt} ({time.time()-t2:.0f}s) res={len(all_results)}", flush=True)

# WEIGHTED PAIRS (top 20, 3 weights)
t2=time.time(); cnt=0; top20=top_feats[:20]
for i in range(len(top20)):
    for j in range(i+1,len(top20)):
        k1,k2=top20[i],top20[j]
        for w in [0.3,0.5,0.7]:
            combo=w*FEAT[k1]+(1-w)*FEAT[k2]; cn=f"{w:.1f}*{k1}+{1-w:.1f}*{k2}"
            daily=ftn(combo,ret_arr,T15,sds,sde,snd)
            st=fs(daily)
            if st:
                st['strat']=f"rank={cn}|top15"; st['feat']=cn; st['tn']=T15; st['type']='weighted'
                all_results.append(st)
            cnt+=1
print(f"Weighted: {cnt} ({time.time()-t2:.0f}s) res={len(all_results)}", flush=True)

# BINARY FILTER (top 20)
BINS=[('z_wa_gt1',D['z_wa_gt1']),('z_accel_gt1',D['z_accel_gt1']),
      ('z_prob_gt1',D['z_prob_gt1']),('z_wa_accel_gt1',D['z_wa_accel_gt1']),
      ('r_both_gt05',D['r_both_gt05'])]
t2=time.time(); cnt=0
for bn,bv in BINS:
    for feat in top20:
        combo=bv*FEAT[feat]; cn=f"{bn}*{feat}"
        daily=ftn(combo,ret_arr,T15,sds,sde,snd)
        st=fs(daily)
        if st:
            st['strat']=f"filter={cn}|top15"; st['feat']=cn; st['tn']=T15; st['type']='binary'
            all_results.append(st)
        cnt+=1
print(f"Binary: {cnt} ({time.time()-t2:.0f}s) res={len(all_results)}", flush=True)

# VERIFY TOP 400 on FULL data
print(f"\n[VERIFY] Top 400 on all {nd} dates...", flush=True)
t1=time.time()
res_all=pd.DataFrame(all_results)
top400=res_all.drop_duplicates('strat').sort_values('sharpe',ascending=False).head(400)

BINS_DICT=dict(BINS)
verified=[]
for _, row in top400.iterrows():
    fname=row['feat']; tn=int(row['tn'])
    fvals=None
    if fname in FEAT: fvals=FEAT[fname]
    elif '+' in fname and '*' not in fname:
        parts=fname.split('+')
        if all(p in FEAT for p in parts): fvals=sum(FEAT[p] for p in parts)
    elif '*' in fname and '+' not in fname:
        parts=fname.split('*')
        if len(parts)==2 and parts[0] in FEAT and parts[1] in FEAT:
            fvals=FEAT[parts[0]]*FEAT[parts[1]]
    if fvals is None: continue
    daily=ftn(fvals,ret_arr,tn,ds_arr,de_arr,nd)
    st=fs(daily)
    if st:
        st['strat']=row['strat']; st['feat']=fname; st['tn']=tn; st['type']=row.get('type','')
        verified.append(st)
print(f"  Verified {len(verified)} ({time.time()-t1:.0f}s)", flush=True)

# OUTPUT
seen=set()
unique=[r for r in verified if r['strat'] not in seen and not seen.add(r['strat'])]
with open(os.path.join(OUTPUT,'creative_btst_liquid.json'),'w') as f:
    json.dump(unique,f,indent=2,default=str)

df_r=pd.DataFrame(unique)
df_r['score']=df_r['sharpe']*df_r['wr']/(df_r['vol']+0.001)

sep="="*160
for title,col,asc in [("TOP 50 BY SHARPE",'sharpe',False),("TOP 50 BY BALANCED SCORE",'score',False),
                        ("TOP 30 BY LOWEST DRAWDOWN (Sharpe>1)",'mdd',True)]:
    print(f"\n{sep}\n  {title} (BTST, liquid stocks only, {nd} dates)\n{sep}")
    subset=df_r if 'DRAWDOWN' not in title else df_r[df_r['sharpe']>1.0]
    for i,(_,r) in enumerate(subset.sort_values(col,ascending=asc).head(50 if 'DRAWDOWN' not in title else 30).iterrows()):
        print(f"  #{i+1:2d} Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.2f}% MDD={r['mdd']*100:>7.2f}% "
              f"Vol={r['vol']*100:>6.2f}% WR={r['wr']*100:>5.1f}% PF={r['pf']:>5.2f} N={r['n']:>4}  {r['strat'][:110]}")

print(f"\n{len(unique)} strategies, total {time.time()-t0:.0f}s")
print("DONE")
