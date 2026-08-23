import pandas as pd
import numpy as np
import sqlite3
from scipy.stats import spearmanr, kendalltau
import warnings
warnings.filterwarnings("ignore")

# === 1. Load all Barchart CSV ===
csv = pd.read_csv(r"C:\Users\Admin\Downloads\stocks-screener-weighted-alpha-52-high-07-17-2026.csv")
csv.columns = csv.columns.str.strip()
csv["Wtd Alpha"] = csv["Wtd Alpha"].astype(str).str.replace("+", "", regex=False).str.replace(",", "", regex=False)
csv["Wtd Alpha"] = pd.to_numeric(csv["Wtd Alpha"], errors="coerce")
csv = csv.dropna(subset=["Wtd Alpha"])
csv = csv.sort_values("Wtd Alpha", ascending=False).reset_index(drop=True)
csv["barchart_rank"] = range(1, len(csv) + 1)
print(f"Loaded {len(csv)} stocks from Barchart CSV")

# === 2. Load ALL bars from DB ===
db = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db"
conn = sqlite3.connect(db, timeout=10)
all_syms = list(csv["Symbol"].unique())
placeholders = ",".join(["?"] * len(all_syms))
bars = pd.read_sql(
    f"SELECT symbol, date, close FROM bars WHERE timeframe='1Day' AND symbol IN ({placeholders}) ORDER BY symbol, date",
    conn, params=all_syms
)
conn.close()
bars["close"] = pd.to_numeric(bars["close"], errors="coerce")
bars = bars.dropna(subset=["close"])
print(f"Loaded {len(bars):,} bars for {bars['symbol'].nunique()} symbols")

# === 3. Codex formula ===
def codex_wa(close_arr, lookback=250, smooth=4, lower_cap=-0.06, upper_cap=0.05):
    n = len(close_arr)
    if n < smooth + lookback + 1:
        return np.nan
    s = pd.Series(close_arr, dtype=float)
    sma = s.rolling(smooth, min_periods=smooth).mean().values
    ret = np.zeros(n)
    for i in range(1, n):
        if sma[i - 1] != 0 and not np.isnan(sma[i - 1]):
            ret[i] = sma[i] / sma[i - 1] - 1
    tail = ret[-lookback:]
    clipped = np.clip(tail, lower_cap, upper_cap)
    weights = np.linspace(0.5, 1.0, lookback)
    return float((100 / 0.75) * np.sum(clipped * weights))

# === 4. Our formula ===
def our_wa(close_arr, lookback=252):
    n = len(close_arr)
    if n < 2:
        return 0.0
    scale = 200.0
    cs = pd.Series(close_arr, dtype=float)
    rm = cs.rolling(lookback, min_periods=2).min().values
    with np.errstate(divide='ignore', invalid='ignore'):
        pct_above = np.maximum(np.where(rm > 0, close_arr / rm, 0) - 1.0, 0.0)
    compressed = np.log1p(pct_above)
    compressed[~np.isfinite(compressed)] = 0.0
    # Use latest value
    i = n - 1
    start = max(0, i - lookback + 1)
    w_len = i - start + 1
    if w_len < 2 or rm[i] <= 0 or not np.isfinite(rm[i]):
        return 0.0
    seg = compressed[start:i + 1]
    w = np.linspace(0.5, 1.0, w_len)
    w = w / w.sum()
    magnitude = float(np.dot(seg, w)) * scale
    sign = 1.0 if close_arr[-1] >= close_arr[start] else -1.0
    return magnitude * sign

# === 5. Detect potential splits ===
def detect_splits(close_arr, threshold=0.3):
    """Detect days with >30% price change (likely splits)."""
    if len(close_arr) < 2:
        return 0
    pct = np.abs(np.diff(close_arr) / close_arr[:-1])
    return np.sum(pct > threshold)

# === 6. Compute both formulas for ALL stocks ===
results = []
missing = 0
insufficient = 0
for _, row in csv.iterrows():
    sym = row["Symbol"]
    barchart_wa = row["Wtd Alpha"]
    barchart_rank = row["barchart_rank"]

    sym_bars = bars[bars["symbol"] == sym].sort_values("date").reset_index(drop=True)
    closes = sym_bars["close"].values.astype(float)

    if len(closes) == 0:
        missing += 1
        continue
    if len(closes) < 276:
        insufficient += 1
        continue

    # Detect splits
    split_days = detect_splits(closes)

    # Check for extreme price jumps (reverse splits, etc.)
    pct_changes = np.abs(np.diff(closes) / closes[:-1])
    max_jump = np.max(pct_changes) if len(pct_changes) > 0 else 0
    has_extreme_jump = max_jump > 2.0  # >200% in one day

    codex_val = codex_wa(closes)
    our_val = our_wa(closes)

    results.append({
        "Symbol": sym,
        "Barchart_WA": barchart_wa,
        "Barchart_Rank": barchart_rank,
        "Codex_WA": codex_val,
        "Our_WA": our_val,
        "bars": len(closes),
        "split_days": split_days,
        "max_jump": max_jump,
        "has_extreme_jump": has_extreme_jump,
    })

df = pd.DataFrame(results)
print(f"\nProcessed: {len(df)} stocks, {missing} missing from DB, {insufficient} insufficient bars")

# === 7. Rank columns ===
df["Codex_Rank"] = df["Codex_WA"].rank(ascending=False, method="min").astype(int)
df["Our_Rank"] = df["Our_WA"].rank(ascending=False, method="min").astype(int)

# === 8. Overall correlation (ALL stocks) ===
codex_spearman_all, _ = spearmanr(df["Barchart_WA"], df["Codex_WA"])
our_spearman_all, _ = spearmanr(df["Barchart_WA"], df["Our_WA"])
codex_kendall_all, _ = kendalltau(df["Barchart_WA"], df["Codex_WA"])
our_kendall_all, _ = kendalltau(df["Barchart_WA"], df["Our_WA"])

print("\n" + "=" * 90)
print("FULL 1000-STOCK RANKING ANALYSIS")
print("=" * 90)
print(f"{'Metric':<45} {'Codex':>20} {'Ours':>20}")
print("-" * 85)
print(f"{'Spearman Rank Correlation':<45} {codex_spearman_all:>20.4f} {our_spearman_all:>20.4f}")
print(f"{'Kendall Tau':<45} {codex_kendall_all:>20.4f} {our_kendall_all:>20.4f}")
print(f"{'Mean Absolute Error':<45} {df['Codex_WA'].sub(df['Barchart_WA']).abs().mean():>20.1f} {df['Our_WA'].sub(df['Barchart_WA']).abs().mean():>20.1f}")
print(f"{'Median Absolute Error':<45} {df['Codex_WA'].sub(df['Barchart_WA']).abs().median():>20.1f} {df['Our_WA'].sub(df['Barchart_WA']).abs().median():>20.1f}")

# Sign agreement
codex_sign = (np.sign(df["Codex_WA"]) == np.sign(df["Barchart_WA"])).mean() * 100
our_sign = (np.sign(df["Our_WA"]) == np.sign(df["Barchart_WA"])).mean() * 100
print(f"{'Sign agreement (%)':<45} {codex_sign:>19.1f}% {our_sign:>19.1f}%")

# === 9. Rank band analysis ===
print("\n" + "=" * 90)
print("RANK BAND ANALYSIS (how many stocks are in correct decile)")
print("=" * 90)
for band_start, band_end, label in [(1, 100, "Top 100"), (101, 300, "101-300"), (301, 500, "301-500"), (501, 1000, "501-1000")]:
    band = df[(df["Barchart_Rank"] >= band_start) & (df["Barchart_Rank"] <= band_end)]
    codex_match = ((band["Codex_Rank"] >= band_start) & (band["Codex_Rank"] <= band_end)).mean() * 100
    our_match = ((band["Our_Rank"] >= band_start) & (band["Our_Rank"] <= band_end)).mean() * 100
    print(f"  {label:<12} Codex: {codex_match:5.1f}%   Ours: {our_match:5.1f}%   ({len(band)} stocks)")

# === 10. Outlier analysis ===
print("\n" + "=" * 90)
print("OUTLIER ANALYSIS")
print("=" * 90)
print(f"  Stocks with extreme price jumps (>200%): {df['has_extreme_jump'].sum()}")
print(f"  Stocks with split-like days (>30% move): {df['split_days'].sum()}")

outliers = df[df["has_extreme_jump"] | (df["Codex_WA"].sub(df["Barchart_WA"]).abs() > 300) | (df["Our_WA"].sub(df["Barchart_WA"]).abs() > 300)]
if len(outliers) > 0:
    print(f"\n  Flagged outliers ({len(outliers)} stocks):")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 15)
    print(outliers[["Symbol", "Barchart_WA", "Codex_WA", "Our_WA", "Barchart_Rank", "Codex_Rank", "Our_Rank", "has_extreme_jump", "split_days"]].to_string(index=False))

# === 11. Top 50 and Bottom 50 rank tracking ===
print("\n" + "=" * 90)
print("RANK TRACKING: Top 50 and Bottom 50")
print("=" * 90)
top50 = df.nsmallest(50, "Barchart_Rank")
bot50 = df.nlargest(50, "Barchart_Rank")

for label, subset in [("Top 50", top50), ("Bottom 50", bot50)]:
    codex_err = (subset["Codex_Rank"] - subset["Barchart_Rank"]).abs().mean()
    our_err = (subset["Our_Rank"] - subset["Barchart_Rank"]).abs().mean()
    print(f"  {label}: Avg rank error — Codex: {codex_err:.1f}, Ours: {our_err:.1f}")

# === 12. Consistency: rank error distribution ===
print("\n" + "=" * 90)
print("RANK ERROR DISTRIBUTION")
print("=" * 90)
codex_rank_err = (df["Codex_Rank"] - df["Barchart_Rank"]).abs()
our_rank_err = (df["Our_Rank"] - df["Barchart_Rank"]).abs()
for pct in [50, 75, 90, 95]:
    print(f"  {pct}th percentile rank error: Codex {np.percentile(codex_rank_err, pct):.0f}, Ours {np.percentile(our_rank_err, pct):.0f}")

# === 13. Scale comparison ===
print("\n" + "=" * 90)
print("SCALE COMPARISON")
print("=" * 90)
for label, col in [("Barchart", "Barchart_WA"), ("Codex", "Codex_WA"), ("Ours", "Our_WA")]:
    v = df[col]
    print(f"  {label:<12} min={v.min():>8.1f}  median={v.median():>8.1f}  mean={v.mean():>8.1f}  max={v.max():>8.1f}")

# === 14. Final verdict ===
print("\n" + "=" * 90)
print("FINAL VERDICT")
print("=" * 90)
winner = "Codex" if codex_spearman_all > our_spearman_all else "Ours"
print(f"  Spearman correlation: Codex={codex_spearman_all:.4f}, Ours={our_spearman_all:.4f} → {winner} wins")
print(f"  Sign agreement: Codex={codex_sign:.1f}%, Ours={our_sign:.1f}% → {'Codex' if codex_sign > our_sign else 'Ours'} wins")
codex_rank_err_mean = codex_rank_err.mean()
our_rank_err_mean = our_rank_err.mean()
print(f"  Mean rank error: Codex={codex_rank_err_mean:.1f}, Ours={our_rank_err_mean:.1f} → {'Codex' if codex_rank_err_mean < our_rank_err_mean else 'Ours'} wins")
print(f"\n  Stocks with wrong sign: Codex={(np.sign(df['Codex_WA']) != np.sign(df['Barchart_WA'])).sum()}, Ours={(np.sign(df['Our_WA']) != np.sign(df['Barchart_WA'])).sum()}")
