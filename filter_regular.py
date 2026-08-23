import pandas as pd, pytz

df = pd.read_csv('ibm_15min_all_candles_with_wa.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
et = pytz.timezone('US/Eastern')
df['ts_et'] = df['timestamp'].dt.tz_convert(et)
df['hour'] = df['ts_et'].dt.hour
df['minute'] = df['ts_et'].dt.minute

# Regular hours only: 9:30 AM to 3:45 PM ET (exclude pre-market 4am-9:29am)
mask = (df['hour'] > 9) | ((df['hour'] == 9) & (df['minute'] >= 30))
mask &= (df['hour'] < 16)
reg = df[mask].copy()

reg['timestamp_et'] = reg['ts_et'].dt.strftime('%Y-%m-%d %I:%M:%S %p ET')
out = reg[['timestamp_et', 'open', 'high', 'low', 'close', 'volume', 'sma_26', 'pct_15m', 'wa']].copy()
out.to_csv('ibm_15min_regular_only_with_wa.csv', index=False)
print("Regular hours candles:", len(out))
print("Date range:", out['timestamp_et'].iloc[0], "to", out['timestamp_et'].iloc[-1])
