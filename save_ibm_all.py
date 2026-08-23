"""Save all IBM 15-min candles with WA to a clean CSV."""
import pandas as pd
import numpy as np

df = pd.read_csv("ibm_15min_bars.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

N = 250; m = 26
L = -0.002839470936396615; U = +0.0015636274286274306

closes = df["close"].values.astype(np.float64)
sma = pd.Series(closes).rolling(m).mean().values
ret = np.full(len(closes), np.nan)
v = (sma[:-1] != 0) & (~np.isnan(sma[:-1]))
ret[1:][v] = sma[1:][v] / sma[:-1][v] - 1.0
clipped = np.clip(ret, L, U)
weights = 0.5 + 0.5 * np.arange(N) / (N - 1)
w_mean = 0.75
wa = np.full(len(closes), np.nan)
for t in range(m + N - 1, len(closes)):
    w = clipped[t - N + 1: t + 1]
    if not np.any(np.isnan(w)):
        wa[t] = (100.0 / w_mean) * np.dot(weights, w)

df["wa"] = wa
df["pct_15m"] = df["close"].pct_change() * 100
df["sma_26"] = sma

# Save full dataset
out = df[["timestamp", "open", "high", "low", "close", "volume", "sma_26", "pct_15m", "wa"]].copy()
out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
out.to_csv("ibm_15min_all_candles_with_wa.csv", index=False)
print(f"Saved {len(out)} candles to ibm_15min_all_candles_with_wa.csv")
print(f"Date range: {out['timestamp'].iloc[0]} to {out['timestamp'].iloc[-1]}")
