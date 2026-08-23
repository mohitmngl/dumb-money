"""Detailed analysis of top liquid BTST strategies with year-by-year breakdown."""
import numpy as np, pandas as pd, sys, io, os, time, json, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*120)
print("  DETAILED ANALYSIS - TOP LIQUID BTST STRATEGIES")
print("="*120, flush=True)

t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
df = df[df['price'] >= 1.0].copy()
df['date'] = pd.to_datetime(df['date'])
df['ret'] = df['next_day_return'] / 100.0
df = df.sort_values(['date','symbol']).reset_index(drop=True)

# Liquidity filter
cutoff = pd.Timestamp.now() - pd.DateOffset(months=24)
df24 = df[df['date'] >= cutoff].copy()
sym_stats = df24.groupby('symbol').agg(avg_vol=('volume','mean'), avg_atrp=('atrp','mean'), nd=('date','count')).reset_index()
LIQUID = set(sym_stats[(sym_stats['avg_vol'] > 100000) & (sym_stats['avg_atrp'] > 2.0) & (sym_stats['nd'] >= 400)]['symbol'])
df = df[df['symbol'].isin(LIQUID)].copy()
df = df.sort_values(['date','symbol']).reset_index(drop=True)

dates_u = np.sort(df['date'].unique())
nd = len(dates_u)
ds_arr = np.searchsorted(df['date'].values, dates_u, side='left')
de_arr = np.searchsorted(df['date'].values, dates_u, side='right')
print(f"Data: {len(df)} rows, {df['symbol'].nunique()} stocks, {nd} dates ({time.time()-t0:.0f}s)", flush=True)

# Extract arrays
ch=df['change_pct'].values.astype(np.float64); vol_arr=df['volume'].values.astype(np.float64)
wa=df['weighted_alpha'].values.astype(np.float64); atrp_v=df['atrp'].values.astype(np.float64)
streak=df['streak'].values.astype(np.float64); atr_val=df['atr_value'].values.astype(np.float64)
atr_stk=df['atr_streak'].values.astype(np.float64); aa=df['accel_a'].values.astype(np.float64)
ab=df['accel_base'].values.astype(np.float64); pst=df['prob_up_st_cross'].values.astype(np.float64)
p1=df['prob_up_1d'].values.astype(np.float64); p5=df['prob_up_5d'].values.astype(np.float64)
ai_o=df['ai_overall_score'].values.astype(np.float64); ai_t=df['ai_tech_score'].values.astype(np.float64)
ai_m=df['ai_momentum_score'].values.astype(np.float64); ret_arr=df['ret'].values.astype(np.float64)
p=df['price'].values.astype(np.float64)

# Build features
print("Building features...", flush=True)

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

z_prob_st = cs_z(pst)
r_prob_st = cs_rk(pst)
prob_st_sq = pst**2
change_div_atr = np.where(np.abs(atr_val)>1e-6, ch/np.abs(atr_val), 0)
ai_t_div_atr = np.where(np.abs(atr_val)>1e-6, ai_t/np.abs(atr_val), 0)
ai_o_div_atr = np.where(np.abs(atr_val)>1e-6, ai_o/np.abs(atr_val), 0)
r_change = cs_rk(ch)
z_change = cs_z(ch)
accel_a_div_atr = np.where(np.abs(atr_val)>1e-6, aa/np.abs(atr_val), 0)
accel_base_div_atr = np.where(np.abs(atr_val)>1e-6, ab/np.abs(atr_val), 0)
prob5_div_atr = np.where(np.abs(atr_val)>1e-6, p5/np.abs(atr_val), 0)
z_volume = cs_z(vol_arr)
prob_st_log = np.log1p(np.abs(pst))*np.sign(pst)
z_wa_gt1 = (cs_z(wa)>1).astype(float)

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

STRATS = [
    ("change_div_atr*z_prob_st|top15", change_div_atr*z_prob_st, 15, "change/ATR * zscore(prob_up_st_cross)"),
    ("ai_t_div_atr*prob_st_sq|top15", ai_t_div_atr*prob_st_sq, 15, "ai_tech/ATR * prob_st^2"),
    ("ai_o_div_atr*prob_st_sq|top15", ai_o_div_atr*prob_st_sq, 15, "ai_overall/ATR * prob_st^2"),
    ("change_div_atr*r_prob_st|top15", change_div_atr*r_prob_st, 15, "change/ATR * rank(prob_st)"),
    ("r_change*prob_st|top15", r_change*pst, 15, "rank(change) * prob_up_st_cross"),
    ("ai_t_div_atr*prob_st|top15", ai_t_div_atr*pst, 15, "ai_tech/ATR * prob_up_st_cross"),
    ("ai_t_div_atr*accel_plus_prob|top15", ai_t_div_atr*(aa+pst), 15, "ai_tech/ATR * (accel_a+prob_st)"),
    ("prob_st_sq*prob5_div_atr|top15", prob_st_sq*prob5_div_atr, 15, "prob_st^2 * prob_up_5d/ATR"),
    ("accel_a_div_atr*prob_st_sq|top15", accel_a_div_atr*prob_st_sq, 15, "accel_a/ATR * prob_st^2"),
    ("accel_base_div_atr*z_prob_st|top20", accel_base_div_atr*z_prob_st, 20, "accel_base/ATR * zscore(prob_st)"),
    ("ai_t_div_atr|top15", ai_t_div_atr, 15, "ai_tech/ATR (single)"),
    ("accel_a_div_atr|top15", accel_a_div_atr, 15, "accel_a/ATR (single)"),
]

print(f"\nRunning {len(STRATS)} strategies on {nd} dates...", flush=True)
for strat_name, fv, tn, desc in STRATS:
    daily = ftn(fv, ret_arr, tn, ds_arr, de_arr, nd)
    
    # Full period
    st = fs(daily)
    if not st: continue
    
    # Last 24 months
    mask_24 = dates_u >= cutoff
    st24 = fs(daily[mask_24])
    
    # Year-by-year
    print(f"\n{'='*120}")
    print(f"  {strat_name} — {desc}")
    print(f"  Full: Sh={st['sharpe']:.3f} CAGR={st['cagr']*100:.1f}% MDD={st['mdd']*100:.1f}% Vol={st['vol']*100:.1f}% WR={st['wr']*100:.1f}% PF={st['pf']:.2f} N={st['n']}")
    if st24:
        print(f"  24mo: Sh={st24['sharpe']:.3f} CAGR={st24['cagr']*100:.1f}% MDD={st24['mdd']*100:.1f}% Vol={st24['vol']*100:.1f}% WR={st24['wr']*100:.1f}% PF={st24['pf']:.2f} N={st24['n']}")
    
    # Year-by-year
    print(f"  Year-by-year:")
    years = pd.Series(dates_u).dt.year.unique()
    for y in years:
        mask = pd.Series(dates_u).dt.year == y
        yr = daily[mask]
        yr_valid = yr[np.isfinite(yr)]
        if len(yr_valid)<50: continue
        ycl = np.cumsum(np.log1p(yr_valid)); ycc=np.exp(ycl)
        ytr=float(ycc[-1]-1); ysd=float(np.std(yr_valid,ddof=1))
        ysh=float(np.mean(yr_valid)/ysd*np.sqrt(252)) if ysd>1e-10 else 0
        ywr=float(np.mean(yr_valid>0))
        yrm=np.maximum.accumulate(ycc); ymdd=float(np.min((ycc-yrm)/yrm))
        ygp=float(np.sum(yr_valid[yr_valid>0])); ygl=float(np.abs(np.sum(yr_valid[yr_valid<0])))
        ypf=ygp/ygl if ygl>0 else 0
        print(f"    {y}: Ret={ytr*100:>7.1f}% Sh={ysh:>6.3f} WR={ywr*100:>5.1f}% MDD={ymdd*100:>7.1f}% PF={ypf:>5.2f} N={len(yr_valid)}")
    
    # Recent 30 days positions
    last30 = daily[-30:]
    valid_last30 = [(str(dates_u[i])[:10], daily[i]) for i in range(nd-30, nd) if np.isfinite(daily[i])]
    if valid_last30:
        avg_ret = np.mean([x[1] for x in valid_last30])
        wr_30 = np.mean([x[1]>0 for x in valid_last30])
        print(f"  Last 30d: Avg={avg_ret*100:.3f}% WR={wr_30*100:.0f}%")

print(f"\nTotal: {time.time()-t0:.0f}s")
print("DONE")
