import json, numpy as np, pandas as pd, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('strategy_results/US_all_strategies.json') as f:
    data = json.load(f)
df = pd.DataFrame(data)
btst = df[(df['hold']=='1d') & (df['n']>=500)]
btst['avg_daily'] = (1 + btst['tr']) ** (1/btst['n']) - 1
btst['score'] = btst['avg_daily'] / (btst['vol'] + 0.001) * btst['rsq']

hdr = "  {:>7} {:>7} {:>8} {:>7} {:>6} {:>6} {:>6} {:>5}  {}".format(
    "Daily","Sharpe","MDD","Vol","WR","PF","R2","Days","Strategy")
print(hdr)
print("-"*130)
for _, r in btst[btst['avg_daily']>0.005].sort_values('score', ascending=False).head(20).iterrows():
    print("  {:>5.2f}% {:>7.3f} {:>7.1f}% {:>6.1f}% {:>5.1f}% {:>6.2f} {:>6.3f} {:>5}  {}".format(
        r['avg_daily']*100, r['sharpe'], r['mdd']*100, r['vol']*100, r['wr']*100,
        r['pf'], r['rsq'], r['n'], r['strat'][:65]))
