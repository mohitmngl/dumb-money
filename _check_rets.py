"""Check what ret_* columns actually represent - look-ahead or not?"""
import pandas as pd, numpy as np

df = pd.read_parquet('strategy_results/US_stock_cache.parquet')
d = df[df['symbol']=='AAPL'].sort_values('date')

# What is ret_1d?
d['price_pct'] = d['price'].pct_change()
d['next_price_pct'] = d['price'].pct_change().shift(-1)

print("AAPL sample:")
print(d[['date','price','ret_1d','ret_5d','ret_1mo','next_day_return','price_pct','next_price_pct']].head(15).to_string())
print()

# Is ret_1d = today's pct change or tomorrow's?
print("ret_1d correlation with price_pct (today):", d['ret_1d'].corr(d['price_pct']))
print("ret_1d correlation with next_price_pct (tomorrow):", d['ret_1d'].corr(d['next_price_pct']))
print("next_day_return correlation with next_price_pct (tomorrow):", d['next_day_return'].corr(d['next_price_pct']))
print("ret_1d correlation with next_day_return:", d['ret_1d'].corr(d['next_day_return']))
print()

# Check: if we rank by ret_1d today, do we get next-day return?
# That would prove ret_1d is today's return (look-ahead if ranking for same day)
r = df[['ret_1d','next_day_return','ret_5d','ret_1mo']].dropna()
print("Full correlation matrix:")
print(r.corr().to_string())
print()

# Check actual values
print("ret_1d stats:", r['ret_1d'].describe().to_string())
print()
print("next_day_return stats:", r['next_day_return'].describe().to_string())
