"""Detailed analysis of top creative BTST strategies."""
import numpy as np, pandas as pd, sys, io, os, time, json, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*120)
print("  TOP CREATIVE BTST STRATEGIES - DETAILED ANALYSIS")
print("="*120, flush=True)

t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
df = df[df['price'] >= 1.0].copy()
df['date'] = pd.to_datetime(df['date'])
df['ret'] = df['next_day_return'] / 100.0
df = df.sort_values(['date','symbol']).reset_index(drop=True)

dates_u = np.sort(df['date'].unique())
nd = len(dates_u)
ds_arr = np.searchsorted(df['date'].values, dates_u, side='left')
de_arr = np.searchsorted(df['date'].values, dates_u, side='right')

# Use last 24 months
cutoff = pd.Timestamp.now() - pd.DateOffset(months=24)
mask_24m = dates_u >= cutoff
idx_24m = np.where(mask_24m)[0]
sds_24 = ds_arr[mask_24m]; sde_24 = de_arr[mask_24m]; snd_24 = len(idx_24m)

print(f"Data: {len(df)} rows, {nd} dates, {snd_24} last-24mo dates ({time.time()-t0:.0f}s)", flush=True)

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

# Build features
print("Building features...", flush=True)
def cs_rk(arr):
    out=np.full_like(arr,np.nan)
    for i in range(nd):
        s,e=ds_arr[i],de_arr[i]; v=arr[s:e]; m=np.isfinite(v); cnt=np.sum(m)
        if cnt<5: continue
        out[s:e][m]=np.argsort(np.argsort(v[m])).astype(float)/max(cnt-1,1)
    return out

r_wa=cs_rk(wa); r_accel=cs_rk(aa); r_prob=cs_rk(pst)

# Feature builders
def feat_prob1_div_atr(): return np.where(np.abs(atr_val)>1e-6, p1/np.abs(atr_val), 0)
def feat_prob5_div_atr(): return np.where(np.abs(atr_val)>1e-6, p5/np.abs(atr_val), 0)
def feat_streak_div_atrp(): return np.where(np.abs(atrp_v)>1e-6, streak/np.abs(atrp_v), 0)
def feat_wa_div_atr(): return np.where(np.abs(atr_val)>1e-6, wa/np.abs(atr_val), 0)
def feat_accel_base_div_atrp(): return np.where(np.abs(atrp_v)>1e-6, ab/np.abs(atrp_v), 0)
def feat_accel_a_div_atrp(): return np.where(np.abs(atrp_v)>1e-6, aa/np.abs(atrp_v), 0)
def feat_prob1_div_atr_streak_div_atrp(): return feat_prob1_div_atr()+feat_streak_div_atrp()
def feat_prob1_div_atr_accel_base_div_atrp(): return feat_prob1_div_atr()+feat_accel_base_div_atrp()
def feat_r_both_gt05_accel_base_div_atrp(): return ((r_wa>0.5).astype(float)*(r_accel>0.5).astype(float))*feat_accel_base_div_atrp()
def feat_prob1_div_atr_x_atr_streak_log(): return feat_prob1_div_atr()*(np.log1p(np.abs(atr_stk))*np.sign(atr_stk))
def feat_prob1_div_atr_z_wa_gt1(): return feat_prob1_div_atr()*((np.where(np.abs(atr_val)>1e-6,(wa-np.zeros_like(wa))/np.where(np.abs(atr_val)>1e-6,atr_val,1),0)>1).astype(float))

# Top 10 strategies to analyze
STRATS = [
    ("prob1_div_atr|top10", feat_prob1_div_atr, 10, "Single: prob_up_1d/ATR, top 10"),
    ("prob1_div_atr+streak_div_atrp|top10", feat_prob1_div_atr_streak_div_atrp, 10, "Sum: prob1/ATR + streak/ATRP, top 10"),
    ("prob1_div_atr+prob_st|top10", lambda: feat_prob1_div_atr()+pst, 10, "Sum: prob1/ATR + prob_up_st_cross, top 10"),
    ("prob1_div_atr+ai_t|top10", lambda: feat_prob1_div_atr()+ai_t, 10, "Sum: prob1/ATR + AI tech score, top 10"),
    ("prob1_div_atr+accel_base_div_atrp|top10", feat_prob1_div_atr_accel_base_div_atrp, 10, "Sum: prob1/ATR + accel_base/ATRP, top 10"),
    ("prob1_div_atr*atr_streak_log|top15", feat_prob1_div_atr_x_atr_streak_log, 15, "Prod: prob1/ATR * log(|atr_streak|), top 15"),
    ("filter=r_both_gt05*accel_base_div_atrp|top15", feat_r_both_gt05_accel_base_div_atrp, 15, "Filter: rank_both>0.5 * accel_base/ATRP, top 15"),
    ("prob5_div_atr|top10", feat_prob5_div_atr, 10, "Single: prob_up_5d/ATR, top 10"),
    ("wa_div_atr|top30", feat_wa_div_atr, 30, "Single: weighted_alpha/ATR, top 30"),
    ("accel_base_div_atrp*rr_wa_x_accel|top15", lambda: feat_accel_base_div_atrp()*(r_wa*r_accel), 15, "Prod: accel_base/ATRP * rank_wa*rank_accel, top 15"),
]

# Run all strategies on full data and last 24 months
print("\nRunning strategies...", flush=True)
for strat_name, feat_fn, tn, desc in STRATS:
    print(f"\n{'='*120}")
    print(f"  {strat_name}")
    print(f"  {desc}")
    print(f"{'='*120}", flush=True)
    
    fv = feat_fn()
    
    # Full period
    daily_full = np.full(nd, np.nan)
    for i in range(nd):
        s,e = ds_arr[i], de_arr[i]
        f=fv[s:e]; r=ret_arr[s:e]
        m=np.isfinite(f)&np.isfinite(r); cnt=np.sum(m)
        if cnt<tn+2: continue
        f2=np.ascontiguousarray(f[m]); r2=np.ascontiguousarray(r[m])
        idx=np.argpartition(f2,-tn)[-tn:]
        daily_full[i]=np.mean(r2[idx])
    
    # Last 24 months
    daily_24 = daily_full[mask_24m]
    
    for period, daily, darr in [("Full", daily_full, dates_u), ("Last 24mo", daily_24, dates_u[mask_24m])]:
        r = daily[np.isfinite(daily)]
        n = len(r)
        if n < 10: continue
        cl = np.cumsum(np.log1p(r))
        cc = np.exp(cl)
        tr = float(cc[-1]-1)
        sd = float(np.std(r,ddof=1))
        ar = float((1+tr)**(252/n)-1) if tr>-1 else -1
        av = float(sd*np.sqrt(252))
        sh = float(np.mean(r)/sd*np.sqrt(252)) if sd>1e-10 else 0
        rm = np.maximum.accumulate(cc)
        mdd = float(np.min((cc-rm)/rm))
        wr = float(np.mean(r>0))
        gp = float(np.sum(r[r>0])); gl = float(np.abs(np.sum(r[r<0])))
        pf = gp/gl if gl>0 else 0
        
        # Monthly breakdown
        md_arr = darr[np.isfinite(daily)]
        months = pd.Series(md_arr).dt.to_period('M').unique()
        m_rets = []
        for m in months:
            mask = pd.Series(md_arr).dt.to_period('M') == m
            mr = daily[np.isfinite(daily)][mask.values]
            if len(mr)>0: m_rets.append(float(np.prod(1+mr)-1))
        
        win_m = sum(1 for x in m_rets if x>0)
        tot_m = len(m_rets)
        
        print(f"\n  [{period}] {n} dates")
        print(f"    CAGR: {ar*100:>8.2f}%  Vol: {av*100:>7.2f}%  Sharpe: {sh:>7.3f}")
        print(f"    MDD:  {mdd*100:>8.2f}%  WR:  {wr*100:>7.1f}%  PF:  {pf:>6.2f}")
        print(f"    Total Return: {tr*100:>8.2f}%  Avg Daily: {np.mean(r)*100:>7.4f}%")
        print(f"    Monthly: {tot_m} months, {win_m} win ({win_m/tot_m*100:.0f}%)")
        if m_rets:
            print(f"    Best month: {max(m_rets)*100:>7.2f}%  Worst month: {min(m_rets)*100:>7.2f}%")
            print(f"    Avg monthly: {np.mean(m_rets)*100:>7.2f}%  Std monthly: {np.std(m_rets)*100:>7.2f}%")
        
        # Year-by-year (only for full period or if >1 year)
        if period == "Full" and n > 252:
            years = pd.Series(md_arr).dt.year.unique()
            print(f"\n    Year-by-year:")
            for y in years:
                mask = pd.Series(md_arr).dt.year == y
                yr = daily[np.isfinite(daily)][mask.values]
                if len(yr)<50: continue
                ycl = np.cumsum(np.log1p(yr)); ycc=np.exp(ycl)
                ytr=float(ycc[-1]-1); ysd=float(np.std(yr,ddof=1))
                ysh=float(np.mean(yr)/ysd*np.sqrt(252)) if ysd>1e-10 else 0
                ywr=float(np.mean(yr>0))
                yrm=np.maximum.accumulate(ycc); ymdd=float(np.min((ycc-yrm)/yrm))
                print(f"      {y}: Ret={ytr*100:>7.2f}% Sh={ysh:>6.3f} WR={ywr*100:>5.1f}% MDD={ymdd*100:>7.2f}% N={len(yr)}")

# Now let's do a realistic BTST simulation for the best strategy
print(f"\n{'='*120}")
print(f"  REALISTIC BTST SIMULATION: prob1_div_atr|top10")
print(f"{'='*120}", flush=True)

fv = feat_prob1_div_atr()
daily = np.full(nd, np.nan)
positions = []
for i in range(nd):
    s,e = ds_arr[i], de_arr[i]
    f=fv[s:e]; r=ret_arr[s:e]
    syms = df['symbol'].values[s:e]
    m=np.isfinite(f)&np.isfinite(r); cnt=np.sum(m)
    if cnt<tn+2: continue
    f2=np.ascontiguousarray(f[m]); r2=np.ascontiguousarray(r[m])
    s2=np.array(syms)[m]
    idx=np.argpartition(f2,-10)[-10:]
    daily[i]=np.mean(r2[idx])
    positions.append({'date': str(dates_u[i])[:10], 'symbols': list(s2[idx]), 
                      'returns': [f"{x*100:.2f}%" for x in r2[idx]]})

# Print recent positions
print("\n  Recent 10-day positions:")
for p in positions[-10:]:
    print(f"    {p['date']}: {', '.join(p['symbols'][:5])}... Returns: {', '.join(p['returns'][:5])}")

print(f"\nTotal: {len(STRATS)} strategies analyzed, {time.time()-t0:.0f}s")
print("DONE")
