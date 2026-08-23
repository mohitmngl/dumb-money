"""Strategy return analysis for LONG-ONLY basket strings - FAST with small sample."""
import numpy as np, pandas as pd, sys, io, os, time, sqlite3, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

print("Extracting 500 long-only strings directly...", flush=True)
t0 = time.time()
conn = sqlite3.connect('screener.db')
conn.execute("PRAGMA mmap_size=268435456")

# Get 500 string IDs first (fast)
sids = [r[0] for r in conn.execute(
    "SELECT string_id FROM string_universe WHERE market='US' AND string_id LIKE 'S%' "
    "ORDER BY string_id LIMIT 500").fetchall()]
print(f"Got {len(sids)} string IDs ({time.time()-t0:.0f}s)", flush=True)

# Build IN clause
sid_list = ','.join(f"'{s}'" for s in sids)
query = f"""SELECT string_id, date, price, weighted_alpha, atr_value, accel_a,
           atrp, streak, atr_streak,
           next_day_return, next_5d_return,
           accel_signal, accel_crossed_up, accel_crossed_down,
           atr_crossed_above, atr_crossed_below
           FROM historical_string_screener
           WHERE string_id IN ({sid_list})"""
df = pd.read_sql_query(query, conn)
conn.close()
print(f"Extracted {len(df):,} rows ({time.time()-t0:.0f}s)", flush=True)

df = df.sort_values(['string_id','date']).reset_index(drop=True)
print(f"Strings: {df['string_id'].nunique()}, Dates: {df['date'].nunique()}")

df['accel_div_atr'] = np.where(np.abs(df['atr_value'])>1e-6, df['accel_a']/np.abs(df['atr_value']), 0)
df['wa_div_atr'] = np.where(np.abs(df['atr_value'])>1e-6, df['weighted_alpha']/np.abs(df['atr_value']), 0)
df['ret_dec'] = df['next_day_return'] / 100.0

print("\nBuilding pivot tables...", flush=True)
t1 = time.time()
ret_pivot = df.pivot_table(index='date', columns='string_id', values='ret_dec')
feat_ad_pivot = df.pivot_table(index='date', columns='string_id', values='accel_div_atr')
feat_wa_pivot = df.pivot_table(index='date', columns='string_id', values='wa_div_atr')
print(f"Pivots: shape={ret_pivot.shape} ({time.time()-t1:.0f}s)", flush=True)

date_arr = ret_pivot.index.values
ret_mat = ret_pivot.values

def get_rebal_mask(date_arr, rebal):
    n = len(date_arr)
    mask = np.zeros(n, dtype=bool)
    if rebal == 'daily':
        mask[:] = True
        return mask
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

def simulate_fast(feat_mat, ret_mat, date_arr, top_n, rebal):
    nd = len(date_arr)
    rebal_mask = get_rebal_mask(date_arr, rebal)
    weights = np.zeros(feat_mat.shape[1])
    port_returns = np.zeros(nd)
    for i in range(nd):
        if rebal_mask[i]:
            fv = feat_mat[i]
            valid = np.isfinite(fv)
            valid_count = np.sum(valid)
            if valid_count >= top_n:
                valid_idx = np.where(valid)[0]
                feat_valid = fv[valid_idx]
                if top_n < len(valid_idx):
                    top_idx = valid_idx[np.argpartition(feat_valid, -top_n)[-top_n:]]
                else:
                    top_idx = valid_idx
                w = np.zeros(feat_mat.shape[1])
                w[top_idx] = 1.0 / len(top_idx)
                weights = w
        rv = ret_mat[i]
        valid_r = np.isfinite(rv)
        port_returns[i] = np.sum(weights[valid_r] * rv[valid_r])
    return port_returns

def compute_stats(r, label):
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
    neg = r[r<0]
    dv = float(np.std(neg, ddof=1)*np.sqrt(252)) if len(neg)>1 else 0.001
    sortino = float(np.mean(r)*252/dv)
    calmar = cagr/abs(mdd) if abs(mdd)>1e-10 else 0
    return {'label': label, 'n': n, 'total_return': tr, 'cagr': cagr,
            'annual_vol': sd*np.sqrt(252), 'sharpe': sh, 'sortino': sortino,
            'max_dd': mdd, 'win_rate': wr, 'profit_factor': pf, 'calmar': calmar}

results = []
for feat_name, feat_mat in [('accel_div_atr', feat_ad_pivot.values), ('wa_div_atr', feat_wa_pivot.values)]:
    print(f"\n{'='*110}")
    print(f"  {feat_name} -- LONG-ONLY BASKET STRINGS (500 strings)")
    if feat_name == 'accel_div_atr':
        print(f"  accel_a / abs(atr_value) = momentum acceleration / volatility")
    else:
        print(f"  weighted_alpha / abs(atr_value) = 1-year trend / volatility")
    print(f"{'='*110}", flush=True)
    for top_n in [10, 20, 30, 50]:
        for rebal in ['daily', 'weekly', 'monthly', 'annual']:
            print(f"  [{rebal:7s} top{top_n:>2d}]...", end=' ', flush=True)
            t2 = time.time()
            rets = simulate_fast(feat_mat, ret_mat, date_arr, top_n, rebal)
            st = compute_stats(rets, f"{feat_name}_{rebal}_top{top_n}")
            elapsed = time.time()-t2
            if st:
                results.append(st)
                print(f"{elapsed:.0f}s  Ret={st['total_return']*100:>8.1f}%  CAGR={st['cagr']*100:>7.2f}%  "
                      f"Vol={st['annual_vol']*100:>6.1f}%  Sh={st['sharpe']:>6.2f}  "
                      f"MDD={st['max_dd']*100:>7.1f}%  WR={st['win_rate']*100:>5.1f}%  "
                      f"PF={st['profit_factor']:>5.2f}  Calmar={st['calmar']:>5.2f}")
            else:
                print("SKIP")

print(f"\n\n{'='*130}")
print(f"  SUMMARY: LONG-ONLY BASKET STRINGS (500 strings)")
print(f"{'='*130}")
print(f"  {'Feature':<20s} {'Rebal':<9s} {'TopN':>4s} {'CAGR':>8s} {'Vol':>7s} {'Sharpe':>7s} {'Sortino':>8s} {'MDD':>8s} {'WR':>6s} {'PF':>6s} {'Calmar':>7s}")
print(f"  {'-'*20} {'-'*9} {'-'*4} {'-'*8} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*6} {'-'*6} {'-'*7}")
for r in sorted(results, key=lambda x: x['sharpe'], reverse=True):
    parts = r['label'].split('_')
    fname = parts[0]+'_'+parts[1]
    print(f"  {fname:<20s} {parts[2]:<9s} {parts[3]:>4s} "
          f"{r['cagr']*100:>7.2f}% {r['annual_vol']*100:>6.1f}% {r['sharpe']:>7.2f} "
          f"{r['sortino']:>8.2f} {r['max_dd']*100:>7.1f}% {r['win_rate']*100:>5.1f}% "
          f"{r['profit_factor']:>6.2f} {r['calmar']:>7.2f}")

# Year-by-year
print(f"\n\n{'='*110}")
print(f"  YEAR-BY-YEAR: accel_div_atr, top 30, monthly")
print(f"{'='*110}", flush=True)
rets = simulate_fast(feat_ad_pivot.values, ret_mat, date_arr, 30, 'monthly')
dt = pd.to_datetime(date_arr)
rdf = pd.DataFrame({'date': date_arr, 'ret': rets, 'year': dt.year})
for year in sorted(rdf['year'].unique()):
    yr = rdf[rdf['year']==year]['ret'].values
    cum = np.prod(1+yr)-1
    sd = np.std(yr, ddof=1) if len(yr)>1 else 0
    sh = (np.mean(yr)/sd*np.sqrt(252)) if sd>1e-10 else 0
    wr = np.mean(yr>0)*100
    print(f"  {year}: Return={cum*100:>8.1f}%  Sharpe={sh:>6.2f}  WR={wr:>5.1f}%  Days={len(yr)}")

print(f"\nTotal time: {time.time()-t0:.0f}s")
print("DONE")
