"""Phase 1: Load US stock data and compute comprehensive features."""
import pandas as pd
import numpy as np
import time, warnings
warnings.filterwarnings('ignore')

print("=" * 80)
print("PHASE 1: LOADING US STOCK DATA")
print("=" * 80)
t0 = time.time()

df = pd.read_parquet('strategy_results/US_stock_cache.parquet')
df['date'] = pd.to_datetime(df['date'])
df['ret_1d'] = df['next_day_return'] / 100.0

# Filter to liquid stocks
str_stats = df.groupby('symbol').agg(
    n_dates=('date', 'count'),
    avg_vol=('volume', 'mean'),
    avg_atrp=('atrp', 'mean')
)
good = str_stats[(str_stats['n_dates'] >= 400) & (str_stats['avg_vol'] > 100000) & (str_stats['avg_atrp'] > 2.0)].index
df = df[df['symbol'].isin(good)].copy()

n_str = df['symbol'].nunique()
n_dates = df['date'].nunique()
print(f"Loaded: {n_str} liquid stocks, {n_dates} dates, {len(df)} rows")
print(f"Date range: {df['date'].min()} to {df['date'].max()}")
print(f"Load time: {time.time()-t0:.1f}s")

# Save basic stats
print(f"\nReturn distribution:")
print(f"  Mean daily return: {df['ret_1d'].mean()*100:.4f}%")
print(f"  Std daily return: {df['ret_1d'].std()*100:.4f}%")
print(f"  Positive days: {(df['ret_1d'] > 0).mean()*100:.1f}%")
print(f"  Median daily return: {df['ret_1d'].median()*100:.4f}%")

# Save for next phase
df.to_parquet('strategy_results/us_liquid_stocks.parquet', index=False)
print(f"\nSaved to us_liquid_stocks.parquet ({time.time()-t0:.1f}s)")
