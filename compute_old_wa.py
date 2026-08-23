import pandas as pd, numpy as np

df = pd.read_csv('ibm_15min_all_candles_with_wa.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

closes = df['close'].values.astype(np.float64)
n = len(closes)

# --- OLD formula: close/rolling_min, log1p, scale 200 ---
N_old = 252
lookback_old = 252
wa_old = np.full(n, np.nan)
for t in range(N_old, n):
    window = closes[t - N_old + 1: t + 1]
    rolling_min = window.min()
    if rolling_min <= 0:
        continue
    returns = closes[t - N_old + 1: t + 1] / rolling_min - 1.0
    log_returns = np.log1p(returns)
    weights = 0.5 + 0.5 * np.arange(N_old) / (N_old - 1)
    raw = np.dot(weights, log_returns)
    wa_old[t] = 200.0 * raw

# sign from 1yr return
for t in range(N_old, n):
    if closes[t] > closes[t - lookback_old]:
        pass  # positive, keep as is
    else:
        wa_old[t] = -abs(wa_old[t]) if not np.isnan(wa_old[t]) else np.nan

df['wa_old'] = wa_old
df['wa_old_200'] = wa_old * 1.0  # already scale 200

# Filter regular hours only
et = __import__('pytz').timezone('US/Eastern')
df['ts_et'] = df['timestamp'].dt.tz_convert(et)
df['hour'] = df['ts_et'].dt.hour
df['minute'] = df['ts_et'].dt.minute
mask = ((df['hour'] > 9) | ((df['hour'] == 9) & (df['minute'] >= 30))) & (df['hour'] < 16)
reg = df[mask].copy()

reg['timestamp_et'] = reg['ts_et'].dt.strftime('%Y-%m-%d %I:%M:%S %p ET')
out = reg[['timestamp_et', 'open', 'high', 'low', 'close', 'volume', 'sma_26', 'pct_15m', 'wa', 'wa_old']].copy()
out.to_csv('ibm_15min_regular_old_formula.csv', index=False)
print("Regular hours candles:", len(out))
print("Date range:", out['timestamp_et'].iloc[0], "to", out['timestamp_et'].iloc[-1])

# Show comparison around Jul 14 crash
print("\n=== OLD vs NEW WA around Jul 14 crash ===")
crash = reg[(reg['ts_et'] >= '2026-07-13') & (reg['ts_et'] <= '2026-07-17')].copy()
for _, r in crash.iterrows():
    t = r['timestamp_et']
    c = r['close']
    new_wa = r['wa']
    old_wa = r['wa_old']
    new_s = f"{new_wa:.2f}" if not np.isnan(new_wa) else "N/A"
    old_s = f"{old_wa:.2f}" if not np.isnan(old_wa) else "N/A"
    print(f"  {t:<24} C={c:>8.2f}  NEW_WA={new_s:>8}  OLD_WA={old_s:>8}")
