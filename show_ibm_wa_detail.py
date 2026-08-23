"""Show all 15-min candles for IBM around the July 14 crash (4-5 days each side)."""
import pandas as pd
import numpy as np

df = pd.read_csv("ibm_15min_bars.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

# Codex WA params
N = 250
m = 26
L = -0.002839470936396615
U = +0.0015636274286274306

closes = df["close"].values.astype(np.float64)
n = len(closes)

sma = pd.Series(closes).rolling(m).mean().values
ret = np.full(n, np.nan)
valid = (sma[:-1] != 0) & (~np.isnan(sma[:-1]))
ret[1:][valid] = sma[1:][valid] / sma[:-1][valid] - 1.0
clipped = np.clip(ret, L, U)

weights = 0.5 + 0.5 * np.arange(N) / (N - 1)
w_mean = 0.75

wa = np.full(n, np.nan)
for t in range(m + N - 1, n):
    w = clipped[t - N + 1: t + 1]
    if not np.any(np.isnan(w)):
        wa[t] = (100.0 / w_mean) * np.dot(weights, w)

df["wa"] = wa
df["pct"] = df["close"].pct_change() * 100

# Filter to 4-5 days around July 14 crash
start = pd.Timestamp("2026-07-07")
end = pd.Timestamp("2026-07-18 20:00:00")
ts = df["timestamp"].dt.tz_localize(None)
mask = (ts >= start) & (ts <= end)
window = df[mask].copy()

print(f"{'Timestamp':<26} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} {'15m%':>8} {'WA':>8}")
print("-" * 90)

prev_date = None
for _, row in window.iterrows():
    cur_date = row["timestamp"].date()
    if prev_date and cur_date != prev_date:
        print("-" * 90)
    prev_date = cur_date
    
    pct_str = f"{row['pct']:+.2f}%" if not np.isnan(row['pct']) else ""
    wa_str = f"{row['wa']:.2f}" if not np.isnan(row['wa']) else "N/A"
    
    # Mark big drops
    marker = ""
    if not np.isnan(row['pct']) and row['pct'] < -3:
        marker = " <<<"
    elif not np.isnan(row['pct']) and row['pct'] > 3:
        marker = " ^^^"
    
    print(f"  {str(row['timestamp'])[:19]:<24} {row['open']:>8.2f} {row['high']:>8.2f} {row['low']:>8.2f} {row['close']:>8.2f} {pct_str:>8} {wa_str:>8}{marker}")

# Summary
wa_valid = window["wa"].dropna()
print(f"\nWA range in window: {wa_valid.min():.2f} to {wa_valid.max():.2f}")
print(f"Price range in window: {window['close'].min():.2f} to {window['close'].max():.2f}")
