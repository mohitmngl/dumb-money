import pandas as pd
import pytz

df = pd.read_csv('ibm_15min_all_candles_with_wa.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
et = pytz.timezone('US/Eastern')
df['ts_et'] = df['timestamp'].dt.tz_convert(et)
df['time_str'] = df['ts_et'].dt.strftime('%I:%M %p')
df['date'] = df['ts_et'].dt.date
df['day_str'] = df['ts_et'].dt.strftime('%a')

for date in df['date'].unique():
    day = df[df['date'] == date]
    first3 = day.head(3)
    last3 = day.tail(3)
    day_name = day.iloc[0]['day_str']
    n = len(day)
    print(f"--- {date} ({day_name}) [{n} candles] ---")
    for _, r in first3.iterrows():
        print(f"  {r['time_str']:>8}  C={r['close']:>8.2f}  WA={r['wa']:.2f}")
    print("  ...")
    for _, r in last3.iterrows():
        print(f"  {r['time_str']:>8}  C={r['close']:>8.2f}  WA={r['wa']:.2f}")
    print()

# Save with ET timestamps
df['timestamp_et'] = df['ts_et'].dt.strftime('%Y-%m-%d %I:%M:%S %p ET')
out = df[['timestamp_et', 'open', 'high', 'low', 'close', 'volume', 'sma_26', 'pct_15m', 'wa']].copy()
out.to_csv('ibm_15min_with_wa_et.csv', index=False)
print("Saved ibm_15min_with_wa_et.csv")
