"""
MONSTER STRATEGY FINDER v5 - ZERO DATE LOOPS
Pure pandas vectorized: groupby('date').rank() + groupby('date').apply()
"""
import numpy as np, pandas as pd, sys, io, os, time, json, itertools, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*100)
print("  MONSTER STRATEGY FINDER v5 - ZERO DATE LOOPS")
print("="*100, flush=True)

# 1. LOAD & PREPARE
t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
df = df[df['price'] >= 1.0].copy()
df = df.sort_values(['date','symbol']).reset_index(drop=True)

# Add all derived features as columns
print("[1] Computing features...", flush=True)
c = df.columns
df['accel_a_pos'] = np.maximum(df['accel_a'], 0)
df['accel_a_abs'] = np.abs(df['accel_a'])
df['accel_base_pos'] = np.maximum(df['accel_base'], 0)
df['accel_ratio'] = np.where(np.abs(df['accel_base'])>0.001, df['accel_a']/df['accel_base'], 0)
df['accel_diff'] = df['accel_a'] - df['accel_base']
df['accel_sum'] = df['accel_a'] + df['accel_base']
df['accel_product'] = df['accel_a'] * df['accel_base']
df['accel_sq'] = df['accel_a']**2
df['accel_log'] = np.log1p(np.abs(df['accel_a']))*np.sign(df['accel_a'])
df['atr_streak_abs'] = np.abs(df['atr_streak'])
df['atr_product'] = df['atr_value']*df['atr_streak']
df['atr_sq'] = df['atr_value']**2
df['atr_log'] = np.log1p(np.abs(df['atr_value']))*np.sign(df['atr_value'])
df['atr_pct_x_streak'] = df['atrp']*df['atr_streak']
df['atr_pct_x_value'] = df['atrp']*df['atr_value']
df['wa_pos'] = np.maximum(df['weighted_alpha'], 0)
df['wa_abs'] = np.abs(df['weighted_alpha'])
df['wa_sq'] = df['weighted_alpha']**2
df['wa_log'] = np.log1p(np.abs(df['weighted_alpha']))*np.sign(df['weighted_alpha'])
df['wa_x_accel'] = df['weighted_alpha']*df['accel_a']
df['wa_x_atr'] = df['weighted_alpha']*df['atr_value']
df['wa_x_streak'] = df['weighted_alpha']*df['streak']
df['accel_x_atr'] = df['accel_a']*df['atr_value']
df['accel_x_streak'] = df['accel_a']*df['atr_streak']
df['wa_accel_atr'] = df['weighted_alpha']*df['accel_a']*df['atr_value']
df['wa_accel_streak'] = df['weighted_alpha']*df['accel_a']*df['atr_streak']
df['wa_div_accel'] = np.where(np.abs(df['accel_a'])>0.001, df['weighted_alpha']/np.abs(df['accel_a']), 0)
df['wa_div_atr'] = np.where(np.abs(df['atr_value'])>0.001, df['weighted_alpha']/np.abs(df['atr_value']), 0)
df['accel_div_atr'] = np.where(np.abs(df['atr_value'])>0.001, df['accel_a']/np.abs(df['atr_value']), 0)
df['prob_avg'] = (df['prob_up_1d']+df['prob_up_5d']+df['prob_up_st_cross'])/3
df['prob_product'] = df['prob_up_1d']*df['prob_up_5d']*df['prob_up_st_cross']
df['prob_wa'] = df['weighted_alpha']*df['prob_up_st_cross']
df['prob_accel'] = df['accel_a']*df['prob_up_st_cross']
df['prob_accel_wa'] = df['weighted_alpha']*df['accel_a']*df['prob_up_st_cross']
df['streak_x_wa'] = df['streak']*df['weighted_alpha']
df['streak_x_accel'] = df['streak']*df['accel_a']
df['streak_x_atr'] = df['streak']*df['atr_value']
df['ai_tech_x_wa'] = df['ai_tech_score']*df['weighted_alpha']
df['ai_mom_x_wa'] = df['ai_momentum_score']*df['weighted_alpha']
df['ai_tech_x_accel'] = df['ai_tech_score']*df['accel_a']
df['ai_mom_x_accel'] = df['ai_momentum_score']*df['accel_a']
df['ai_overall_x_wa'] = df['ai_overall_score']*df['weighted_alpha']
df['ai_overall_x_accel'] = df['ai_overall_score']*df['accel_a']
df['composite_1'] = df['weighted_alpha']*0.4+df['accel_a']*0.3+df['atr_value']*0.3
df['composite_2'] = df['weighted_alpha']*0.3+df['prob_up_st_cross']*0.3+df['accel_a']*0.2+df['atr_streak']*0.2
df['composite_3'] = df['weighted_alpha']*0.33+df['accel_a']*0.33+df['atr_value']*0.34
df['composite_4'] = df['ai_overall_score']*0.3+df['weighted_alpha']*0.3+df['accel_a']*0.2+df['atr_value']*0.2
df['composite_5'] = df['prob_up_st_cross']*0.4+df['accel_a']*0.3+df['weighted_alpha']*0.3
df['composite_6'] = df['weighted_alpha']*df['accel_a']*df['prob_up_st_cross']
df['triple_wa_accel_atr'] = df['weighted_alpha']*df['accel_a']*df['atr_value']
df['triple_wa_accel_streak'] = df['weighted_alpha']*df['accel_a']*df['atr_streak']
df['triple_wa_accel_prob'] = df['weighted_alpha']*df['accel_a']*df['prob_up_st_cross']
df['wa_above_0'] = (df['weighted_alpha']>0).astype(float)
df['accel_above_0'] = (df['accel_a']>0).astype(float)
df['atr_above_0'] = (df['atr_value']>0).astype(float)
df['streak_above_0'] = (df['streak']>0).astype(float)
df['change_x_wa'] = df['change_pct']*df['weighted_alpha']
df['change_x_accel'] = df['change_pct']*df['accel_a']
df['pct_accel'] = df['atrp']*df['accel_a']

# Core feature columns (base features only - combos are computed inline)
FEATS = [
    'weighted_alpha','atrp','streak','atr_value','atr_streak','accel_a','accel_base',
    'prob_up_1d','prob_up_5d','prob_up_st_cross','change_pct',
    'ai_overall_score','ai_tech_score','ai_momentum_score',
    'accel_a_pos','accel_a_abs','accel_base_pos','accel_ratio','accel_diff',
    'accel_sum','accel_product','accel_sq','accel_log',
    'atr_streak_abs','atr_product','atr_sq','atr_log','atr_pct_x_streak','atr_pct_x_value',
    'wa_pos','wa_abs','wa_sq','wa_log',
    'wa_x_accel','wa_x_atr','wa_x_streak','accel_x_atr','accel_x_streak',
    'wa_accel_atr','wa_accel_streak','wa_div_accel','wa_div_atr','accel_div_atr',
    'prob_avg','prob_product','prob_wa','prob_accel','prob_accel_wa',
    'streak_x_wa','streak_x_accel','streak_x_atr',
    'ai_tech_x_wa','ai_mom_x_wa','ai_tech_x_accel','ai_mom_x_accel',
    'ai_overall_x_wa','ai_overall_x_accel',
    'composite_1','composite_2','composite_3','composite_4','composite_5','composite_6',
    'triple_wa_accel_atr','triple_wa_accel_streak','triple_wa_accel_prob',
    'wa_above_0','accel_above_0','atr_above_0','streak_above_0',
    'change_x_wa','change_x_accel','pct_accel'
]

HOLDS = {'1d': 'ret_1d', '5d': 'ret_5d', '1mo': 'ret_1mo'}
TOP_NS = [5, 10, 15, 20, 30]

print(f"  {len(FEATS)} features, {len(df)} rows ({time.time()-t0:.0f}s)", flush=True)

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
# VECTORIZED STRATEGY TEST
###############################################################################
def test_strategy(feat_col, hold_col, top_n, df_ref):
    """Zero-date-loop: groupby rank + filter + aggregate."""
    d = df_ref[['date', feat_col, hold_col]].copy()
    d = d.dropna(subset=[feat_col, hold_col])
    if len(d) == 0: return None
    
    # Rank within each date
    d['rank'] = d.groupby('date')[feat_col].rank(method='first', ascending=False)
    
    # Take top N per date
    top = d[d['rank'] <= top_n]
    
    # Average return per date
    daily = top.groupby('date')[hold_col].mean().values
    
    return fs(daily)

###############################################################################
# PHASE 1: All single features, all top-N, all holds
###############################################################################
print(f"\n[PHASE 1] {len(FEATS)} features x {len(TOP_NS)} top-N x {len(HOLDS)} holds = {len(FEATS)*len(TOP_NS)*len(HOLDS)} tests", flush=True)
t0 = time.time()
all_results = []

for fi, fname in enumerate(FEATS):
    for hname, hcol in HOLDS.items():
        for tn in TOP_NS:
            st = test_strategy(fname, hcol, tn, df)
            if st:
                st['strat'] = f"rank={fname}|top{tn}|{hname}"
                st['feat'] = fname; st['tn'] = tn; st['hold'] = hname
                st['type'] = 'single'
                all_results.append(st)
    if (fi+1)%10==0:
        elapsed = time.time()-t0
        rate = (fi+1)/elapsed
        eta = (len(FEATS)-fi-1)/rate
        print(f"  {fi+1}/{len(FEATS)} ({elapsed:.0f}s, {rate:.1f}/s, ETA {eta:.0f}s)", flush=True)

print(f"  Phase 1 done: {len(all_results)} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# PHASE 2: Dual combos (top 20 features by sharpe)
###############################################################################
print(f"\n[PHASE 2] Dual combos from top 20...", flush=True)
t0 = time.time()
res_df = pd.DataFrame(all_results)
top20 = res_df.sort_values('sharpe', ascending=False)['feat'].unique()[:20]

# Add feature columns to df for combos
for f in top20:
    if f not in df.columns:
        print(f"  WARNING: {f} not in df", flush=True)

# Create combo features in df
for f1, f2 in itertools.combinations(top20, 2):
    col = f"combo_{f1}_{f2}"
    df[col] = df[f1] + df[f2]

cnt = 0
for f1, f2 in itertools.combinations(top20, 2):
    col = f"combo_{f1}_{f2}"
    for hname, hcol in HOLDS.items():
        for tn in [10, 15, 20]:
            st = test_strategy(col, hcol, tn, df)
            if st:
                st['strat'] = f"rank=({f1}+{f2})|top{tn}|{hname}"
                st['feat'] = f"{f1}+{f2}"; st['tn'] = tn; st['hold'] = hname
                st['type'] = 'dual'
                all_results.append(st)
            cnt += 1
    if cnt%50==0:
        print(f"  {cnt} ({time.time()-t0:.0f}s)", flush=True)

print(f"  Phase 2 done: {cnt} ({time.time()-t0:.0f}s)", flush=True)

# Cleanup temp combo columns
for f1, f2 in itertools.combinations(top20, 2):
    col = f"combo_{f1}_{f2}"
    if col in df.columns: del df[col]

###############################################################################
# PHASE 3: Weighted dual combos (top 10 features)
###############################################################################
print(f"\n[PHASE 3] Weighted dual combos from top 10...", flush=True)
t0 = time.time()
res_df = pd.DataFrame(all_results)
top10 = res_df.sort_values('sharpe', ascending=False)['feat'].unique()[:10]

cnt = 0
for f1, f2 in itertools.combinations(top10, 2):
    for w1, w2 in [(0.7,0.3),(0.6,0.4),(0.5,0.5),(0.8,0.2)]:
        col = f"wc_{f1}_{f2}_{w1}"
        df[col] = w1*df[f1] + w2*df[f2]
        for hname, hcol in HOLDS.items():
            st = test_strategy(col, hcol, 15, df)
            if st:
                st['strat'] = f"rank={w1:.1f}*{f1}+{w2:.1f}*{f2}|top15|{hname}"
                st['feat'] = f"{w1}*{f1}+{w2}*{f2}"; st['tn'] = 15; st['hold'] = hname
                st['type'] = 'weighted_dual'
                all_results.append(st)
            cnt += 1
        del df[col]
    if cnt%50==0:
        print(f"  {cnt} ({time.time()-t0:.0f}s)", flush=True)

print(f"  Phase 3 done: {cnt} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# PHASE 4: Triple combos (top 8)
###############################################################################
print(f"\n[PHASE 4] Triple combos from top 8...", flush=True)
t0 = time.time()
res_df = pd.DataFrame(all_results)
top8 = res_df.sort_values('sharpe', ascending=False)['feat'].unique()[:8]

cnt = 0
for f1, f2, f3 in itertools.combinations(top8, 3):
    col = f"tc_{f1}_{f2}_{f3}"
    df[col] = df[f1] + df[f2] + df[f3]
    for hname, hcol in HOLDS.items():
        st = test_strategy(col, hcol, 15, df)
        if st:
            st['strat'] = f"rank=({f1}+{f2}+{f3})|top15|{hname}"
            st['feat'] = f"{f1}+{f2}+{f3}"; st['tn'] = 15; st['hold'] = hname
            st['type'] = 'triple'
            all_results.append(st)
        cnt += 1
    del df[col]

print(f"  Phase 4 done: {cnt} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# PHASE 5: Threshold filter combos (atr_crossed_above + rank features)
###############################################################################
print(f"\n[PHASE 5] Binary filter combos...", flush=True)
t0 = time.time()
BINS = ['atr_crossed_above','accel_crossed_up','accel_crossed_down']
# These are float 0/1 in the parquet

# Pre-filter: only rows with all 3 binary filters
df['bin_sum'] = df['atr_crossed_above'] + df['accel_crossed_up'] + df['accel_crossed_down']

cnt = 0
for bin_col in BINS + ['bin_sum']:
    for feat in top10[:5]:
        col = f"bf_{bin_col}_{feat}"
        df[col] = df[bin_col] * df[feat]
        for hname, hcol in HOLDS.items():
            for tn in [10, 15]:
                st = test_strategy(col, hcol, tn, df)
                if st:
                    st['strat'] = f"filter={bin_col}*{feat}|top{tn}|{hname}"
                    st['feat'] = f"{bin_col}*{feat}"; st['tn'] = tn; st['hold'] = hname
                    st['type'] = 'binary_filter'
                    all_results.append(st)
                cnt += 1
        del df[col]

# Triple binary filters
for bin_combo in itertools.combinations(BINS, 2):
    col_name = f"binc_{'_'.join(bin_combo)}"
    df[col_name] = df[bin_combo[0]] * df[bin_combo[1]]
    for feat in top10[:5]:
        col = f"bf2_{col_name}_{feat}"
        df[col] = df[col_name] * df[feat]
        for hname, hcol in HOLDS.items():
            st = test_strategy(col, hcol, 15, df)
            if st:
                st['strat'] = f"filter={'+'.join(bin_combo)}*{feat}|top15|{hname}"
                st['feat'] = f"{'+'.join(bin_combo)}*{feat}"; st['tn'] = 15; st['hold'] = hname
                st['type'] = 'binary_filter'
                all_results.append(st)
            cnt += 1
        del df[col]
    del df[col_name]

if 'bin_sum' in df.columns: del df['bin_sum']

print(f"  Phase 5 done: {cnt} ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# SAVE & RANK
###############################################################################
print(f"\n[SAVE] {len(all_results)} strategies...", flush=True)
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
            print(f"    Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% PF={r['pf']:>5.2f} R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:95]}")

print(f"\n{sep}")
print(f"  GLOBAL TOP 30 BALANCED")
print(sep)
for i, (_, r) in enumerate(df_r.sort_values('score', ascending=False).head(30).iterrows()):
    print(f"  #{i+1:2d} Score={r['score']:>6.3f} Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:95]}")

print(f"\nTOTAL: {len(all_results)} unique strategies")
print("DONE")
