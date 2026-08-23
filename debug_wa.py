import sqlite3, pandas as pd, numpy as np

conn = sqlite3.connect(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db')
df = pd.read_sql("SELECT date, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date", conn, params=('AAPL',))
print(f'AAPL bars: {len(df)} rows, from {df.date.iloc[0]} to {df.date.iloc[-1]}')
print(f'First 3 closes: {df.close.iloc[:3].tolist()}')
print(f'Last 3 closes: {df.close.iloc[-3:].tolist()}')

close = df.close.astype(float).values
lookback = 252
n = min(lookback, len(close))
print(f'\nUsing n={n} bars')
print(f'BUG: close[0]={close[0]:.2f} (from {df.date.iloc[0]})')
print(f'BUG: close[{n-1}]={close[n-1]:.2f} (from {df.date.iloc[n-1]})')
cum_ret = (close[:n] / close[0]) - 1.0
print(f'cum_ret at start={cum_ret[0]}, cum_ret at end={cum_ret[n-1]}')
weights = np.linspace(0.5, 1.0, n)
weights = weights / weights.sum()
wa_wrong = float(np.dot(cum_ret, weights)) * 100
print(f'WA (using FIRST {n} bars) = {wa_wrong:.4f}')

# Correct: use LAST 252 bars
close_last = close[-n:]
print(f'\nFIX: close[-{n}]={close_last[0]:.2f} (from {df.date.iloc[-n]})')
print(f'FIX: close[-1]={close_last[-1]:.2f} (from {df.date.iloc[-1]})')
cum_ret2 = (close_last / close_last[0]) - 1.0
weights2 = np.linspace(0.5, 1.0, n)
weights2 = weights2 / weights2.sum()
wa_correct = float(np.dot(cum_ret2, weights2)) * 100
print(f'WA (using LAST {n} bars) = {wa_correct:.4f}')
print(f'Weighted annual return = {(close[-1]/close[-252]-1)*100:.2f}%')
conn.close()
