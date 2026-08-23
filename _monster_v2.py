"""
MONSTER STRATEGY FINDER v2 - VECTORIZED
- Uses pandas groupby rank instead of date-by-date loops
- 117 features x 5 top-N x 3 holds = 1755 combos in seconds
- Then dual/triple/weighted combos from top features
"""
import numpy as np, pandas as pd, sys, io, os, time, json, itertools, warnings
warnings.filterwarnings('ignore')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT = 'strategy_results'
print("="*100, flush=True)
print("  MONSTER STRATEGY FINDER v2", flush=True)
print("="*100, flush=True)

# 1. LOAD
print("\n[1] Loading US stock cache...", flush=True)
t0 = time.time()
df = pd.read_parquet(os.path.join(OUTPUT, 'US_stock_cache.parquet'))
print(f"  {len(df)} rows, {df['date'].nunique()} dates ({time.time()-t0:.0f}s)", flush=True)

# Base filter
df = df[df['price'] >= 1.0].copy()
print(f"  After price>=1 filter: {len(df)}", flush=True)

###############################################################################
# 2. CREATE 117 FEATURES
###############################################################################
print("\n[2] Creating features...", flush=True)
t0 = time.time()

# Ensure returns exist
if 'ret_1d' not in df.columns:
    df['ret_1d'] = df.groupby('symbol')['price'].pct_change().shift(-1)
if 'ret_5d' not in df.columns:
    df['ret_5d'] = df.groupby('symbol')['price'].pct_change().shift(-5)
if 'ret_1mo' not in df.columns:
    df['ret_1mo'] = df.groupby('symbol')['price'].pct_change().shift(-22)

# Basic
a = df['accel_a'].values; b = df['accel_base'].values
wa = df['weighted_alpha'].values
s_val = df['atr_value'].values; s_streak = df['atr_streak'].values
atr = df['atrp'].values; st = df['streak'].values
pst = df['prob_up_st_cross'].values
p1 = df['prob_up_1d'].values; p5 = df['prob_up_5d'].values
ch = df['change_pct'].values; pr = df['price'].values
conf = np.zeros(len(df))  # not in cache

# Feature builder
feats = {}

# RAW
for c in ['weighted_alpha','atrp','streak','atr_value','atr_streak','accel_a','accel_base',
          'confluence','prob_up_1d','prob_up_5d','prob_up_st_cross','change_pct']:
    if c in df.columns:
        feats[c] = df[c].values

# ACCEL
feats['accel_a_pos'] = np.maximum(a, 0)
feats['accel_a_abs'] = np.abs(a)
feats['accel_base_pos'] = np.maximum(b, 0)
feats['accel_base_abs'] = np.abs(b)
feats['accel_ratio'] = np.where(np.abs(b) > 0.001, a/b, 0)
feats['accel_diff'] = a - b
feats['accel_sum'] = a + b
feats['accel_product'] = a * b
feats['accel_sq'] = a**2
feats['accel_log'] = np.log1p(np.abs(a)) * np.sign(a)

# ST
feats['atr_value_abs'] = np.abs(s_val)
feats['atr_streak_abs'] = np.abs(s_streak)
feats['atr_product'] = s_val * s_streak
feats['atr_sq'] = s_val**2
feats['atr_log'] = np.log1p(np.abs(s_val)) * np.sign(s_val)
feats['atr_pct_x_streak'] = atr * s_streak
feats['atr_pct_x_value'] = atr * s_val

# WA
feats['wa_pos'] = np.maximum(wa, 0)
feats['wa_abs'] = np.abs(wa)
feats['wa_sq'] = wa**2
feats['wa_log'] = np.log1p(np.abs(wa)) * np.sign(wa)

# CROSS-DOMAIN
feats['wa_x_accel'] = wa * a
feats['wa_x_atr'] = wa * s_val
feats['wa_x_streak'] = wa * st
feats['accel_x_atr'] = a * s_val
feats['accel_x_streak'] = a * s_streak
feats['wa_accel_atr'] = wa * a * s_val
feats['wa_accel_streak'] = wa * a * s_streak
feats['wa_div_accel'] = np.where(np.abs(a) > 0.001, wa/np.abs(a), 0)
feats['wa_div_atr'] = np.where(np.abs(s_val) > 0.001, wa/np.abs(s_val), 0)
feats['accel_div_atr'] = np.where(np.abs(s_val) > 0.001, a/np.abs(s_val), 0)

# PROB
feats['prob_avg'] = (p1 + p5 + pst) / 3
feats['prob_product'] = p1 * p5 * pst
feats['prob_wa'] = wa * pst
feats['prob_accel'] = a * pst
feats['prob_accel_wa'] = wa * a * pst

# STREAK
feats['streak_x_wa'] = st * wa
feats['streak_x_accel'] = st * a
feats['streak_x_atr'] = st * s_val

# CONF (not in cache, skip)

# AI
ai_o = df['ai_overall_score'].values; ai_t = df['ai_tech_score'].values
ai_m = df['ai_momentum_score'].values; ai_v = df['ai_volume_score'].values
feats['ai_tech_x_wa'] = ai_t * wa
feats['ai_mom_x_wa'] = ai_m * wa
feats['ai_tech_x_accel'] = ai_t * a
feats['ai_mom_x_accel'] = ai_m * a
feats['ai_overall_x_wa'] = ai_o * wa
feats['ai_overall_x_accel'] = ai_o * a

# COMPOSITES
feats['composite_1'] = wa*0.4 + a*0.3 + s_val*0.3
feats['composite_2'] = wa*0.3 + pst*0.3 + a*0.2 + s_streak*0.2
feats['composite_3'] = wa*0.33 + a*0.33 + s_val*0.34
feats['composite_4'] = ai_o*0.3 + wa*0.3 + a*0.2 + s_val*0.2
feats['composite_5'] = pst*0.4 + a*0.3 + wa*0.3
feats['composite_6'] = wa * a * pst

# TRIPLE
feats['triple_wa_accel_atr'] = wa * a * s_val
feats['triple_wa_accel_streak'] = wa * a * s_streak
feats['triple_wa_accel_prob'] = wa * a * pst
feats['triple_accel_atr_prob'] = a * s_val * pst
feats['quad_wa_accel_atr_prob'] = wa * a * s_val * pst

# THRESHOLD
feats['wa_above_0'] = (wa > 0).astype(float)
feats['accel_above_0'] = (a > 0).astype(float)
feats['atr_above_0'] = (s_val > 0).astype(float)
feats['streak_above_0'] = (st > 0).astype(float)

# Price-based
feats['price_x_wa'] = pr * wa
feats['change_x_wa'] = ch * wa
feats['change_x_accel'] = ch * a
feats['pct_accel'] = atr * a

print(f"  {len(feats)} features ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 3. VECTORIZED SWEEP - Single features
###############################################################################
print("\n[3] Phase 1: Single feature sweep (vectorized)...", flush=True)
t0 = time.time()

holds = {'1d': 'ret_1d', '5d': 'ret_5d', '1mo': 'ret_1mo'}
top_ns = [5, 10, 15, 20, 30]
all_results = []
cnt = 0

for feat_name, feat_vals in feats.items():
    df['_fv'] = feat_vals
    
    for hold_name, ret_col in holds.items():
        if ret_col not in df.columns: continue
        
        for tn in top_ns:
            # Vectorized: rank per date, take top tn, average return
            ranked = df.groupby('date')['_fv'].rank(ascending=False, method='first', na_option='bottom')
            top_mask = (ranked <= tn) & df[ret_col].notna() & np.isfinite(df['_fv'])
            
            daily = df[top_mask].groupby('date')[ret_col].mean()
            daily = daily.dropna()
            
            if len(daily) < 30: continue
            
            r = daily.values
            n = len(r)
            cl = np.cumsum(np.log1p(r))
            c = np.exp(cl)
            tr = float(c[-1]-1)
            sd = float(np.std(r, ddof=1))
            ar = float((1+tr)**(252/n)-1) if tr > -1 else -1
            av = float(sd*np.sqrt(252))
            sh = float(np.mean(r)/sd*np.sqrt(252)) if sd > 1e-10 else 0
            rm = np.maximum.accumulate(c)
            mdd = float(np.min((c-rm)/rm))
            wr = float(np.mean(r>0))
            gp = float(np.sum(r[r>0])); gl = float(np.abs(np.sum(r[r<0])))
            pf = float(gp/gl) if gl > 0 else 0
            x = np.arange(n); sl,ic = np.polyfit(x,cl,1)
            rsq = float(1 - np.sum((cl-(ic+sl*x))**2) / np.sum((cl-np.mean(cl))**2))
            
            all_results.append({
                'strat': f"rank={feat_name}|top{tn}|{hold_name}",
                'feat': feat_name, 'tn': tn, 'hold': hold_name,
                'sharpe': round(sh,3), 'cagr': round(ar,4), 'vol': round(av,4),
                'mdd': round(mdd,4), 'wr': round(wr,4), 'pf': round(pf,3),
                'rsq': round(rsq,4), 'n': n
            })
            cnt += 1
    
    if cnt % 500 == 0:
        print(f"  {cnt} tested ({time.time()-t0:.0f}s)", flush=True)

print(f"  Phase 1: {cnt} strategies ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 4. Phase 2: Dual combos from top features
###############################################################################
print("\n[4] Phase 2: Dual combos...", flush=True)
t0 = time.time()

# Get top 25 features by sharpe
res_df = pd.DataFrame(all_results)
top25 = res_df.sort_values('sharpe', ascending=False).head(50)['feat'].unique()[:25]

cnt2 = 0
for f1, f2 in itertools.combinations(top25, 2):
    v1 = feats[f1]; v2 = feats[f2]
    df['_combo'] = v1 + v2
    
    for hold_name, ret_col in holds.items():
        if ret_col not in df.columns: continue
        for tn in [10, 15, 20]:
            ranked = df.groupby('date')['_combo'].rank(ascending=False, method='first', na_option='bottom')
            top_mask = (ranked <= tn) & df[ret_col].notna() & np.isfinite(df['_combo'])
            daily = df[top_mask].groupby('date')[ret_col].mean().dropna()
            
            if len(daily) < 30: continue
            r = daily.values; n = len(r)
            cl = np.cumsum(np.log1p(r)); c = np.exp(cl)
            tr = float(c[-1]-1); sd = float(np.std(r,ddof=1))
            ar = float((1+tr)**(252/n)-1) if tr > -1 else -1
            av = float(sd*np.sqrt(252))
            sh = float(np.mean(r)/sd*np.sqrt(252)) if sd > 1e-10 else 0
            rm = np.maximum.accumulate(c); mdd = float(np.min((c-rm)/rm))
            wr = float(np.mean(r>0))
            gp = float(np.sum(r[r>0])); gl = float(np.abs(np.sum(r[r<0])))
            pf = float(gp/gl) if gl > 0 else 0
            x = np.arange(n); sl,ic = np.polyfit(x,cl,1)
            rsq = float(1 - np.sum((cl-(ic+sl*x))**2) / np.sum((cl-np.mean(cl))**2))
            
            all_results.append({
                'strat': f"rank=({f1}+{f2})|top{tn}|{hold_name}",
                'feat': f"{f1}+{f2}", 'tn': tn, 'hold': hold_name,
                'sharpe': round(sh,3), 'cagr': round(ar,4), 'vol': round(av,4),
                'mdd': round(mdd,4), 'wr': round(wr,4), 'pf': round(pf,3),
                'rsq': round(rsq,4), 'n': n
            })
            cnt2 += 1

print(f"  Phase 2: {cnt2} combos ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 5. Phase 3: Triple combos
###############################################################################
print("\n[5] Phase 3: Triple combos...", flush=True)
t0 = time.time()

res_df2 = pd.DataFrame(all_results)
top10 = res_df2.sort_values('sharpe', ascending=False).head(100)['feat'].unique()[:10]

cnt3 = 0
for f1, f2, f3 in itertools.combinations(top10, 3):
    v1 = feats[f1]; v2 = feats[f2]; v3 = feats[f3]
    df['_combo'] = v1 + v2 + v3
    
    for hold_name, ret_col in holds.items():
        if ret_col not in df.columns: continue
        for tn in [10, 15]:
            ranked = df.groupby('date')['_combo'].rank(ascending=False, method='first', na_option='bottom')
            top_mask = (ranked <= tn) & df[ret_col].notna() & np.isfinite(df['_combo'])
            daily = df[top_mask].groupby('date')[ret_col].mean().dropna()
            
            if len(daily) < 30: continue
            r = daily.values; n = len(r)
            cl = np.cumsum(np.log1p(r)); c = np.exp(cl)
            tr = float(c[-1]-1); sd = float(np.std(r,ddof=1))
            ar = float((1+tr)**(252/n)-1) if tr > -1 else -1
            av = float(sd*np.sqrt(252))
            sh = float(np.mean(r)/sd*np.sqrt(252)) if sd > 1e-10 else 0
            rm = np.maximum.accumulate(c); mdd = float(np.min((c-rm)/rm))
            wr = float(np.mean(r>0))
            gp = float(np.sum(r[r>0])); gl = float(np.abs(np.sum(r[r<0])))
            pf = float(gp/gl) if gl > 0 else 0
            x = np.arange(n); sl,ic = np.polyfit(x,cl,1)
            rsq = float(1 - np.sum((cl-(ic+sl*x))**2) / np.sum((cl-np.mean(cl))**2))
            
            all_results.append({
                'strat': f"rank=({f1}+{f2}+{f3})|top{tn}|{hold_name}",
                'feat': f"{f1}+{f2}+{f3}", 'tn': tn, 'hold': hold_name,
                'sharpe': round(sh,3), 'cagr': round(ar,4), 'vol': round(av,4),
                'mdd': round(mdd,4), 'wr': round(wr,4), 'pf': round(pf,3),
                'rsq': round(rsq,4), 'n': n
            })
            cnt3 += 1

print(f"  Phase 3: {cnt3} combos ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 6. Phase 4: Weighted combos
###############################################################################
print("\n[6] Phase 4: Weighted combos...", flush=True)
t0 = time.time()

res_df3 = pd.DataFrame(all_results)
top12 = res_df3.sort_values('sharpe', ascending=False).head(60)['feat'].unique()[:12]

cnt4 = 0
for f1, f2 in itertools.combinations(top12, 2):
    v1 = feats[f1]; v2 = feats[f2]
    for w1, w2 in [(0.7,0.3),(0.6,0.4),(0.5,0.5),(0.8,0.2),(0.3,0.7)]:
        df['_combo'] = w1*v1 + w2*v2
        
        for hold_name, ret_col in holds.items():
            if ret_col not in df.columns: continue
            for tn in [10, 15]:
                ranked = df.groupby('date')['_combo'].rank(ascending=False, method='first', na_option='bottom')
                top_mask = (ranked <= tn) & df[ret_col].notna() & np.isfinite(df['_combo'])
                daily = df[top_mask].groupby('date')[ret_col].mean().dropna()
                
                if len(daily) < 30: continue
                r = daily.values; n = len(r)
                cl = np.cumsum(np.log1p(r)); c = np.exp(cl)
                tr = float(c[-1]-1); sd = float(np.std(r,ddof=1))
                ar = float((1+tr)**(252/n)-1) if tr > -1 else -1
                av = float(sd*np.sqrt(252))
                sh = float(np.mean(r)/sd*np.sqrt(252)) if sd > 1e-10 else 0
                rm = np.maximum.accumulate(c); mdd = float(np.min((c-rm)/rm))
                wr = float(np.mean(r>0))
                gp = float(np.sum(r[r>0])); gl = float(np.abs(np.sum(r[r<0])))
                pf = float(gp/gl) if gl > 0 else 0
                x = np.arange(n); sl,ic = np.polyfit(x,cl,1)
                rsq = float(1 - np.sum((cl-(ic+sl*x))**2) / np.sum((cl-np.mean(cl))**2))
                
                all_results.append({
                    'strat': f"rank={w1}*{f1}+{w2}*{f2}|top{tn}|{hold_name}",
                    'feat': f"{w1}*{f1}+{w2}*{f2}", 'tn': tn, 'hold': hold_name,
                    'sharpe': round(sh,3), 'cagr': round(ar,4), 'vol': round(av,4),
                    'mdd': round(mdd,4), 'wr': round(wr,4), 'pf': round(pf,3),
                    'rsq': round(rsq,4), 'n': n
                })
                cnt4 += 1

print(f"  Phase 4: {cnt4} combos ({time.time()-t0:.0f}s)", flush=True)

###############################################################################
# 7. SAVE & RANK
###############################################################################
print("\n[7] Ranking...", flush=True)

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

sep = "=" * 140
dash = "-" * 140

for hold, hl in [('1d','BTST'),('5d','5-DAY'),('1mo','1-MONTH')]:
    hdf = df_r[df_r['hold']==hold]
    if len(hdf) == 0: continue
    
    print(f"\n{sep}", flush=True)
    print(f"  {hl} -- {len(hdf)} strategies", flush=True)
    print(f"{sep}", flush=True)
    
    cats = [
        ('sharpe', False, 'SHARPE'),
        ('cagr', False, 'CAGR'),
        ('mdd', True, 'DD'),
        ('vol', True, 'VOL'),
        ('rsq', False, 'LINEAR'),
        ('wr', False, 'WR'),
        ('pf', False, 'PF'),
        ('score', False, 'BALANCED'),
    ]
    
    for col, asc, cat in cats:
        top = hdf.sort_values(col, ascending=asc).head(3)
        print(f"  [{cat}]", flush=True)
        for _, r in top.iterrows():
            print(f"    Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% PF={r['pf']:>5.2f} R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:80]}", flush=True)
        print(flush=True)

# GLOBAL TOP 20
print(f"\n{sep}", flush=True)
print(f"  GLOBAL TOP 20 BALANCED (all holds)", flush=True)
print(f"{sep}", flush=True)
top20 = df_r.sort_values('score', ascending=False).head(20)
for _, r in top20.iterrows():
    print(f"  Score={r['score']:>6.3f} Sh={r['sharpe']:>6.3f} CAGR={r['cagr']*100:>7.1f}% MDD={r['mdd']*100:>7.1f}% Vol={r['vol']*100:>6.1f}% WR={r['wr']*100:>5.1f}% R2={r['rsq']:>5.3f} N={r['n']:>4}  {r['strat'][:85]}", flush=True)

print(f"\nTOTAL: {len(all_results)} unique strategies", flush=True)
print("DONE", flush=True)
