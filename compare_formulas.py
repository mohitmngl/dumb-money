import pandas as pd
import numpy as np
import sqlite3

# === 1. Load Barchart reference CSV ===
csv = pd.read_csv(r"C:\Users\Admin\Downloads\stocks-screener-weighted-alpha-52-high-07-17-2026.csv")
csv.columns = csv.columns.str.strip()
csv["Wtd Alpha"] = pd.to_numeric(csv["Wtd Alpha"], errors="coerce")
csv = csv.dropna(subset=["Wtd Alpha"])
csv = csv.sort_values("Wtd Alpha", ascending=False).reset_index(drop=True)
csv["barchart_rank"] = range(1, len(csv) + 1)
top30 = csv.head(30).copy()
print("=== Top 30 from Barchart CSV ===")
print(top30[["Symbol", "Wtd Alpha", "barchart_rank"]].to_string(index=False))

# === 2. Load close prices from DB ===
db = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db"
conn = sqlite3.connect(db, timeout=10)
syms = list(top30["Symbol"].unique())
placeholders = ",".join(["?"] * len(syms))
bars = pd.read_sql(
    f"SELECT symbol, date, close FROM bars WHERE timeframe='1Day' AND symbol IN ({placeholders}) ORDER BY symbol, date",
    conn, params=syms
)
conn.close()
bars["close"] = pd.to_numeric(bars["close"], errors="coerce")
bars = bars.dropna(subset=["close"])

# === 3. Codex's formula: 4-bar SMA, clipped returns, 250 periods ===
def codex_weighted_alpha(close_arr, lookback=250, smooth=4, lower_cap=-0.06, upper_cap=0.05):
    n = len(close_arr)
    if n < smooth + lookback + 1:
        return np.nan
    s = pd.Series(close_arr)
    # 4-bar SMA smoothing
    sma = s.rolling(smooth, min_periods=smooth).mean().values
    # Percentage changes of smoothed series
    ret = np.empty_like(sma)
    ret[0] = 0
    for i in range(1, n):
        if sma[i - 1] != 0 and not np.isnan(sma[i - 1]):
            ret[i] = sma[i] / sma[i - 1] - 1
        else:
            ret[i] = 0
    # Take last 250 returns
    tail = ret[-lookback:]
    # Clip returns
    clipped = np.clip(tail, lower_cap, upper_cap)
    # Linear weights
    weights = np.linspace(0.5, 1.0, lookback)
    w_mean = weights.mean()  # 0.75
    # Weighted alpha
    wa = (100 / w_mean) * np.dot(clipped, weights) / lookback * lookback
    wa = (100 / w_mean) * np.sum(clipped * weights)
    return wa

# === 4. Our formula: above_min_log, 252 periods ===
def our_weighted_alpha(close_arr, lookback=252):
    n = len(close_arr)
    if n < 2:
        return 0.0
    scale = 200.0
    cs = pd.Series(close_arr)
    rm = cs.rolling(lookback, min_periods=2).min().values
    with np.errstate(divide='ignore', invalid='ignore'):
        pct_above = np.maximum(np.where(rm > 0, close_arr / rm, 0) - 1.0, 0.0)
    compressed = np.log1p(pct_above)
    compressed[~np.isfinite(compressed)] = 0.0
    # Sign from 1yr return
    if n >= lookback and close_arr[-lookback] > 0:
        sign = 1.0 if close_arr[-1] >= close_arr[-lookback] else -1.0
    else:
        sign = 0.0
    # Linear weights over window
    out = np.zeros(n)
    for i in range(1, n):
        start = max(0, i - lookback + 1)
        w_len = i - start + 1
        if w_len < 2 or rm[i] <= 0 or not np.isfinite(rm[i]):
            continue
        seg = compressed[start:i + 1]
        w = np.linspace(0.5, 1.0, w_len)
        w = w / w.sum()
        out[i] = np.dot(seg, w) * scale * (1.0 if close_arr[i] >= close_arr[start] else -1.0)
    return out[-1]

# === 5. Compute both formulas for top 30 ===
results = []
for _, row in top30.iterrows():
    sym = row["Symbol"]
    barchart_wa = row["Wtd Alpha"]
    barchart_rank = row["barchart_rank"]
    
    sym_bars = bars[bars["symbol"] == sym].sort_values("date").reset_index(drop=True)
    closes = sym_bars["close"].values.astype(float)
    
    if len(closes) < 276:
        print(f"  {sym}: only {len(closes)} bars, skipping")
        continue
    
    codex_wa = codex_weighted_alpha(closes)
    our_wa = our_weighted_alpha(closes)
    
    results.append({
        "Symbol": sym,
        "Barchart_WA": barchart_wa,
        "Barchart_Rank": barchart_rank,
        "Codex_WA": codex_wa,
        "Our_WA": our_wa,
        "Codex_Error": abs(codex_wa - barchart_wa),
        "Our_Error": abs(our_wa - barchart_wa),
        "bars_used": len(closes)
    })

df = pd.DataFrame(results)

# === 6. Add rank columns ===
df["Codex_Rank"] = df["Codex_WA"].rank(ascending=False, method="min").astype(int)
df["Our_Rank"] = df["Our_WA"].rank(ascending=False, method="min").astype(int)

# === 7. Print comparison ===
print("\n" + "=" * 120)
print("COMPARISON: Top 30 Stocks")
print("=" * 120)
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 200)
pd.set_option("display.float_format", lambda x: f"{x:,.2f}")
print(df[["Symbol", "Barchart_WA", "Barchart_Rank", "Codex_WA", "Codex_Rank", "Our_WA", "Our_Rank", "Codex_Error", "Our_Error"]].to_string(index=False))

# === 8. Summary stats ===
print("\n" + "=" * 120)
print("SUMMARY STATISTICS")
print("=" * 120)
print(f"{'Metric':<40} {'Codex Formula':>20} {'Our Formula':>20}")
print("-" * 80)
print(f"{'Mean Absolute Error':<40} {df['Codex_Error'].mean():>20.2f} {df['Our_Error'].mean():>20.2f}")
print(f"{'Median Absolute Error':<40} {df['Codex_Error'].median():>20.2f} {df['Our_Error'].median():>20.2f}")
print(f"{'Max Absolute Error':<40} {df['Codex_Error'].max():>20.2f} {df['Our_Error'].max():>20.2f}")
print(f"{'Mean Signed Error (bias)':<40} {(df['Codex_WA'] - df['Barchart_WA']).mean():>20.2f} {(df['Our_WA'] - df['Barchart_WA']).mean():>20.2f}")

# Spearman rank correlation
from scipy.stats import spearmanr
codex_spearman, _ = spearmanr(df["Barchart_WA"], df["Codex_WA"])
our_spearman, _ = spearmanr(df["Barchart_WA"], df["Our_WA"])
print(f"{'Spearman Rank Correlation':<40} {codex_spearman:>20.4f} {our_spearman:>20.4f}")

# Rank flip count (where rank differs by more than 3)
codex_flips = (abs(df["Codex_Rank"] - df["Barchart_Rank"]) > 3).sum()
our_flips = (abs(df["Our_Rank"] - df["Barchart_Rank"]) > 3).sum()
print(f"{'Rank flips > 3 positions':<40} {codex_flips:>20} {our_flips:>20}")

# Top 10 rank preservation
codex_top10_match = len(set(df.nsmallest(10, "Codex_Rank")["Symbol"]) & set(df.nsmallest(10, "Barchart_Rank")["Symbol"]))
our_top10_match = len(set(df.nsmallest(10, "Our_Rank")["Symbol"]) & set(df.nsmallest(10, "Barchart_Rank")["Symbol"]))
print(f"{'Top-10 stocks in common':<40} {codex_top10_match:>20} {our_top10_match:>20}")
print(f"{'Top-20 stocks in common':<40} {len(set(df.nsmallest(20, 'Codex_Rank')['Symbol']) & set(df.nsmallest(20, 'Barchart_Rank')['Symbol'])):>20} {len(set(df.nsmallest(20, 'Our_Rank')['Symbol']) & set(df.nsmallest(20, 'Barchart_Rank')['Symbol'])):>20}")

# Scale comparison
print(f"\n{'Codex WA range in top 30:':<40} {df['Codex_WA'].min():.1f} to {df['Codex_WA'].max():.1f}")
print(f"{'Our WA range in top 30:':<40} {df['Our_WA'].min():.1f} to {df['Our_WA'].max():.1f}")
print(f"{'Barchart WA range in top 30:':<40} {df['Barchart_WA'].min():.1f} to {df['Barchart_WA'].max():.1f}")
