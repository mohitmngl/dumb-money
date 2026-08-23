"""
VECTORIZED strategy return analysis for accel_div_atr and wa_div_atr.
"""
import numpy as np, pandas as pd, sys, io, os, time, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*100)
print("  STRATEGY RETURN ANALYSIS: accel_div_atr & wa_div_atr")
print("="*100, flush=True)

t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
df = df[df['price'] >= 1.0].copy()
df = df.sort_values(['date','symbol']).reset_index(drop=True)
print(f"Loaded {len(df)} rows ({time.time()-t0:.0f}s)", flush=True)

# Compute features
df['accel_div_atr'] = np.where(np.abs(df['atr_value'])>1e-6, df['accel_a']/np.abs(df['atr_value']), 0)
df['wa_div_atr'] = np.where(np.abs(df['atr_value'])>1e-6, df['weighted_alpha']/np.abs(df['atr_value']), 0)

# Convert next_day_return from percentage to decimal
df['ret_dec'] = df['next_day_return'] / 100.0

dates = np.sort(df['date'].unique())
nd = len(dates)
print(f"Dates: {nd}, from {dates[0]} to {dates[-1]}")

# Pivot tables: rows=date, cols=symbol
print("Building pivot tables...", flush=True)
t1 = time.time()
ret_pivot = df.pivot_table(index='date', columns='symbol', values='ret_dec')
feat_ad_pivot = df.pivot_table(index='date', columns='symbol', values='accel_div_atr')
feat_wa_pivot = df.pivot_table(index='date', columns='symbol', values='wa_div_atr')
print(f"Pivots built ({time.time()-t1:.0f}s), shape={ret_pivot.shape}", flush=True)

date_arr = ret_pivot.index.values
ret_mat = ret_pivot.values  # (dates, symbols) - daily returns in decimal

def get_rebal_mask(date_arr, rebal):
    """Return boolean mask of rebalance dates."""
    n = len(date_arr)
    mask = np.zeros(n, dtype=bool)
    if rebal == 'daily':
        mask[:] = True
    else:
        dt = pd.to_datetime(date_arr)
        if rebal == 'weekly':
            groups = dt.isocalendar().year.astype(str) + '-W' + dt.isocalendar().week.astype(str)
        elif rebal == 'monthly':
            groups = dt.year.astype(str) + '-' + dt.month.astype(str).str.zfill(2)
        elif rebal == 'annual':
            groups = dt.year.astype(str)
        else:
            mask[:] = True
            return mask
        
        seen = set()
        for i, g in enumerate(groups):
            if g not in seen:
                mask[i] = True
                seen.add(g)
    return mask

def simulate_fast(feat_pivot, ret_mat, date_arr, top_n, rebal):
    """Fast vectorized simulation."""
    feat_mat = feat_pivot.values  # (dates, symbols)
    nd = len(date_arr)
    rebal_mask = get_rebal_mask(date_arr, rebal)
    
    # Track portfolio weights
    weights = np.zeros(feat_mat.shape[1])  # current weights
    port_returns = np.zeros(nd)
    
    for i in range(nd):
        if rebal_mask[i]:
            # Get valid (non-NaN) feature values for this date
            fv = feat_mat[i]
            valid = np.isfinite(fv)
            valid_count = np.sum(valid)
            
            if valid_count >= top_n:
                # Find top N by feature value (among valid)
                valid_idx = np.where(valid)[0]
                feat_valid = fv[valid_idx]
                # argpartition for speed
                if top_n < len(valid_idx):
                    top_idx = valid_idx[np.argpartition(feat_valid, -top_n)[-top_n:]]
                else:
                    top_idx = valid_idx
                # Equal weight
                w = np.zeros(feat_mat.shape[1])
                w[top_idx] = 1.0 / len(top_idx)
                weights = w
        
        # Daily return
        rv = ret_mat[i]
        valid_r = np.isfinite(rv)
        port_returns[i] = np.sum(weights[valid_r] * rv[valid_r])
    
    return port_returns

def stats(r, label):
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 30: return None
    cum = np.cumprod(1 + r)
    tr = cum[-1] - 1
    yrs = n / 252
    cagr = cum[-1]**(1/yrs) - 1 if yrs > 0 else 0
    sd = float(np.std(r, ddof=1))
    sh = float(np.mean(r)/sd*np.sqrt(252)) if sd>1e-10 else 0
    rm = np.maximum.accumulate(cum); mdd = float(np.min((cum-rm)/rm))
    wr = float(np.mean(r>0))
    gp = float(np.sum(r[r>0])); gl = float(np.abs(np.sum(r[r<0])))
    pf = gp/gl if gl>0 else 0
    dv = float(np.std(r[r<0], ddof=1)*np.sqrt(252)) if np.sum(r<0)>1 else 0.001
    sortino = float(np.mean(r)*252/dv)
    calmar = cagr/abs(mdd) if abs(mdd)>1e-10 else 0
    
    return {
        'label': label, 'n': n, 'total_return': tr, 'cagr': cagr,
        'annual_vol': sd*np.sqrt(252), 'sharpe': sh, 'sortino': sortino,
        'max_dd': mdd, 'win_rate': wr, 'profit_factor': pf, 'calmar': calmar,
        'avg_daily': np.mean(r)*100, 'best_day': np.max(r)*100, 'worst_day': np.min(r)*100,
    }

# Run all simulations
results = []
for feat_name, feat_pivot in [('accel_div_atr', feat_ad_pivot), ('wa_div_atr', feat_wa_pivot)]:
    print(f"\n{'='*110}")
    print(f"  {feat_name}")
    if feat_name == 'accel_div_atr':
        print(f"  accel_a = SMA28*SMA14/(SMA7^2) | atr_value = 14-period Wilder's ATR")
        print(f"  = momentum acceleration / volatility")
    else:
        print(f"  weighted_alpha = 250-day linear-weighted price trend | atr_value = 14-period Wilder's ATR")
        print(f"  = 1-year trend strength / volatility")
    print(f"{'='*110}", flush=True)
    
    for top_n in [10, 20, 30]:
        for rebal in ['daily', 'weekly', 'monthly', 'annual']:
            print(f"  [{rebal:7s} top{top_n:>2d}]...", end=' ', flush=True)
            t2 = time.time()
            rets = simulate_fast(feat_pivot, ret_mat, date_arr, top_n, rebal)
            st = stats(rets, f"{feat_name}_{rebal}_top{top_n}")
            elapsed = time.time()-t2
            
            if st:
                results.append(st)
                print(f"{elapsed:.0f}s  Ret={st['total_return']*100:>8.1f}%  CAGR={st['cagr']*100:>7.2f}%  "
                      f"Vol={st['annual_vol']*100:>6.1f}%  Sh={st['sharpe']:>6.2f}  "
                      f"MDD={st['max_dd']*100:>7.1f}%  WR={st['win_rate']*100:>5.1f}%  "
                      f"PF={st['profit_factor']:>5.2f}  Calmar={st['calmar']:>5.2f}")
            else:
                print(f"SKIP")

# Summary table
print(f"\n\n{'='*110}")
print(f"  SUMMARY TABLE")
print(f"{'='*110}")
print(f"  {'Feature':<20s} {'Rebal':<9s} {'TopN':>4s} {'CAGR':>8s} {'Vol':>7s} {'Sharpe':>7s} {'Sortino':>8s} {'MDD':>8s} {'WR':>6s} {'PF':>6s} {'Calmar':>7s}")
print(f"  {'-'*20} {'-'*9} {'-'*4} {'-'*8} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*6} {'-'*6} {'-'*7}")
for r in results:
    print(f"  {r['label']:<20s} {r['label'].split('_')[1]:<9s} {r['label'].split('_')[2]:>4s} "
          f"{r['cagr']*100:>7.2f}% {r['annual_vol']*100:>6.1f}% {r['sharpe']:>7.2f} "
          f"{r['sortino']:>8.2f} {r['max_dd']*100:>7.1f}% {r['win_rate']*100:>5.1f}% "
          f"{r['profit_factor']:>6.2f} {r['calmar']:>7.2f}")

# Year-by-year for best strategy
print(f"\n\n{'='*110}")
print(f"  YEAR-BY-YEAR: accel_div_atr, top 30, monthly")
print(f"{'='*110}", flush=True)

rets_monthly = simulate_fast(feat_ad_pivot, ret_mat, date_arr, 30, 'monthly')
dt = pd.to_datetime(date_arr)
rets_df = pd.DataFrame({'date': date_arr, 'ret': rets_monthly, 'year': dt.year})

for year in sorted(rets_df['year'].unique()):
    yr = rets_df[rets_df['year']==year]['ret'].values
    cum = np.prod(1+yr)-1
    sd = np.std(yr, ddof=1) if len(yr)>1 else 0
    sh = (np.mean(yr)/sd*np.sqrt(252)) if sd>1e-10 else 0
    wr = np.mean(yr>0)*100
    print(f"  {year}: Return={cum*100:>8.1f}%  Sharpe={sh:>6.2f}  WR={wr:>5.1f}%  Days={len(yr)}")

print(f"\nTotal time: {time.time()-t0:.0f}s")
print("DONE")
