import sys
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
import pandas as pd
from dumbmoney.db import get_db

conn = get_db('US')

# Is MU in assets?
r = pd.read_sql("SELECT symbol, status, asset_class, tradable FROM assets WHERE symbol='MU'", conn)
print('MU in assets:')
print(r.to_string())

# How many assets have stale stats?
df = pd.read_sql("""
    SELECT a.symbol, a.status, a.asset_class, a.tradable, s.last_updated, s.price, b.close as latest_close
    FROM assets a
    JOIN stats s ON a.symbol = s.symbol
    JOIN bars b ON a.symbol = b.symbol
    WHERE a.symbol = 'MU' AND b.date = (SELECT MAX(date) FROM bars WHERE symbol='MU')
""", conn)
print('\nMU asset + stats + bars:')
print(df.to_string())

# How many stats are stale (not updated today)?
df2 = pd.read_sql("SELECT COUNT(*) as cnt FROM stats WHERE last_updated < '2026-07-27'", conn)
print(f'\nStale stats (before 2026-07-27): {df2.iloc[0, 0]}')

df3 = pd.read_sql("SELECT COUNT(*) as cnt FROM stats WHERE last_updated >= '2026-07-27'", conn)
print(f'Fresh stats (2026-07-27+): {df3.iloc[0, 0]}')

# Show a few stale ones
df4 = pd.read_sql("SELECT symbol, price, last_updated FROM stats WHERE last_updated < '2026-07-27' LIMIT 10", conn)
print('\nSample stale stats:')
print(df4.to_string())

conn.close()
