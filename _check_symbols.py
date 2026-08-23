"""Check what the 'stocks' in the cache actually are."""
import pandas as pd, numpy as np

df = pd.read_parquet('strategy_results/US_stock_cache.parquet')
df['date'] = pd.to_datetime(df['date'])
cutoff = pd.Timestamp.now() - pd.DateOffset(months=24)
df = df[df['date'] >= cutoff]

# Get unique symbols and their stats
syms = df.groupby('symbol').agg(
    n=('date','count'),
    avg_vol=('volume','mean'),
    avg_price=('price','mean'),
    avg_atrp=('atrp','mean')
).reset_index()

print(f"Total symbols in cache (last 24mo): {len(syms)}")
print(f"\nSample of top symbols by volume:")
top = syms.sort_values('avg_vol', ascending=False).head(30)
for _, r in top.iterrows():
    print(f"  {r['symbol']:>8s}  N={r['n']:>4.0f}  AvgVol={r['avg_vol']:>15,.0f}  AvgPrice=${r['avg_price']:>8.2f}  AvgATRP={r['avg_atrp']:>6.2f}%")

print(f"\nSymbols with very low ATRP (<5%):")
low_atrp = syms[syms['avg_atrp'] < 5].sort_values('avg_atrp')
print(f"  Count: {len(low_atrp)}")
for _, r in low_atrp.head(20).iterrows():
    print(f"  {r['symbol']:>8s}  AvgATRP={r['avg_atrp']:>6.2f}%  AvgPrice=${r['avg_price']:>8.2f}  AvgVol={r['avg_vol']:>15,.0f}")

print(f"\nSymbols with avg volume < 1000:")
low_vol = syms[syms['avg_vol'] < 1000].sort_values('avg_vol')
print(f"  Count: {len(low_vol)}")
for _, r in low_vol.head(20).iterrows():
    print(f"  {r['symbol']:>8s}  AvgVol={r['avg_vol']:>10,.0f}  AvgPrice=${r['avg_price']:>8.2f}  AvgATRP={r['avg_atrp']:>6.2f}%")
