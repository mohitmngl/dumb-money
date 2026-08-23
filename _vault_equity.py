"""Generate equity curve data for the 3 vault strategies."""
import numpy as np, pandas as pd, sys, io, os, json, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("Generating equity curves for vault strategies...", flush=True)

t0 = __import__('time').time()
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
print(f"Data: {len(df)} rows, {df['symbol'].nunique()} stocks, {nd} dates", flush=True)

# Extract arrays
ch=df['change_pct'].values.astype(np.float64); vol_arr=df['volume'].values.astype(np.float64)
wa=df['weighted_alpha'].values.astype(np.float64); atrp_v=df['atrp'].values.astype(np.float64)
streak=df['streak'].values.astype(np.float64); atr_val=df['atr_value'].values.astype(np.float64)
atr_stk=df['atr_streak'].values.astype(np.float64); aa=df['accel_a'].values.astype(np.float64)
ab=df['accel_base'].values.astype(np.float64); pst=df['prob_up_st_cross'].values.astype(np.float64)
p1=df['prob_up_1d'].values.astype(np.float64); p5=df['prob_up_5d'].values.astype(np.float64)
ai_o=df['ai_overall_score'].values.astype(np.float64); ai_t=df['ai_tech_score'].values.astype(np.float64)
ret_arr=df['ret'].values.astype(np.float64)

# Build features
def cs_z(arr):
    out=np.full_like(arr,np.nan)
    for i in range(nd):
        s,e=ds_arr[i],de_arr[i]; v=arr[s:e]; m=np.isfinite(v)
        if np.sum(m)<5: continue
        vv=v[m]; mu=np.mean(vv); sd=np.std(vv)
        if sd>1e-10: out[s:e][m]=(v[m]-mu)/sd
    return out

print("Building features...", flush=True)
ai_t_div_atr = np.where(np.abs(atr_val)>1e-6, ai_t/np.abs(atr_val), 0)
ai_o_div_atr = np.where(np.abs(atr_val)>1e-6, ai_o/np.abs(atr_val), 0)
prob_st_sq = pst**2
change_div_atr = np.where(np.abs(atr_val)>1e-6, ch/np.abs(atr_val), 0)
z_prob_st = cs_z(pst)

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

STRATS = [
    ("ai-tech-atr-prob-st-squared", ai_t_div_atr * prob_st_sq, 15),
    ("ai-overall-atr-prob-st-squared", ai_o_div_atr * prob_st_sq, 15),
    ("change-atr-zprob-st", change_div_atr * z_prob_st, 15),
]

results = {}
for slug, fv, tn in STRATS:
    print(f"  Computing {slug}...", flush=True)
    daily = ftn(fv, ret_arr, tn, ds_arr, de_arr, nd)
    
    # Build equity curve (sample to ~500 points for SVG)
    valid_mask = np.isfinite(daily)
    valid_dates = dates_u[valid_mask]
    valid_rets = daily[valid_mask]
    
    cum = np.cumprod(1 + valid_rets)
    
    # Sample every N points to get ~500 points max
    n_valid = len(cum)
    step = max(1, n_valid // 500)
    sample_idx = list(range(0, n_valid, step))
    if sample_idx[-1] != n_valid - 1:
        sample_idx.append(n_valid - 1)
    
    dates_sample = [str(valid_dates[i])[:10] for i in sample_idx]
    cum_sample = [float(cum[i]) for i in sample_idx]
    
    # Also compute running max for drawdown shading
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    dd_sample = [float(dd[i]) for i in sample_idx]
    
    results[slug] = {
        'dates': dates_sample,
        'equity': cum_sample,
        'drawdown': dd_sample,
    }
    print(f"    {len(sample_idx)} points, final value={cum[-1]:.2f}", flush=True)

# Save
out_path = os.path.join(OUTPUT, 'vault_equity_curves.json')
with open(out_path, 'w') as f:
    json.dump(results, f)
print(f"\nSaved to {out_path}", flush=True)
print(f"Total: {__import__('time').time()-t0:.0f}s", flush=True)
