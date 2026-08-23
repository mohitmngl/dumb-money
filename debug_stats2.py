import sys
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
import pandas as pd
from dumbmoney.db import get_db

conn = get_db('US')
df = pd.read_sql("SELECT symbol, date, close FROM bars WHERE symbol='MU' ORDER BY date DESC LIMIT 3", conn)
print('MU recent bars:')
print(df.to_string())
print()
df2 = pd.read_sql("SELECT symbol, price, change_pct, last_updated FROM stats WHERE symbol='MU'", conn)
print('MU stats:')
print(df2.to_string())

# Check if the vectorized_stats actually changed anything
# Compare total stats count vs total active symbols
stats_count = pd.read_sql("SELECT COUNT(*) as cnt FROM stats", conn).iloc[0, 0]
assets_count = pd.read_sql("SELECT COUNT(*) as cnt FROM assets WHERE status='active' AND asset_class='stock'", conn).iloc[0, 0]
print(f'\nStats rows: {stats_count}')
print(f'Active stock assets: {assets_count}')

# Check when stats were last updated for a sample
df3 = pd.read_sql("SELECT symbol, last_updated FROM stats ORDER BY last_updated DESC LIMIT 5", conn)
print('\nMost recently updated stats:')
print(df3.to_string())
conn.close()
