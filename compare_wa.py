"""Compare fitted vs codex weighted-alpha formulas against Barchart reference."""

import sys
import os
import time
import json
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Config ──────────────────────────────────────────────────────────────────
CSV_PATH = r"C:\Users\Admin\Downloads\stocks-screener-weighted-alpha-52-high-07-17-2026.csv"
API_KEY = "PKUPBR7N6SS6NQUJ4U24NO7GEO"
API_SECRET = "BFGrUckWUymMRYVe9kkrz1V2zVLXeoxBU7Kr5K54Cfsq"
DATA_URL = "https://data.alpaca.markets"
BATCH_SIZE = 50          # symbols per Alpaca call
MAX_BARS = 1000          # bars per symbol
MIN_BARS = 253           # minimum bars needed
CACHE_FILE = os.path.join(os.path.dirname(__file__), "bars_cache.json")

# ── Alpaca session ──────────────────────────────────────────────────────────
sess = requests.Session()
sess.headers.update({
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET,
})

class RateLimiter:
    def __init__(self, max_requests=180, window=60):
        self.max_requests = max_requests
        self.window = window
        self.timestamps = []
    def wait(self):
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < self.window]
        if len(self.timestamps) >= self.max_requests:
            sleep_time = self.window - (now - self.timestamps[0]) + 0.5
            if sleep_time > 0:
                time.sleep(sleep_time)
        self.timestamps.append(time.time())

_rl = RateLimiter(max_requests=190, window=60)

def api_get(url, params=None, timeout=30):
    _rl.wait()
    try:
        r = sess.get(url, params=params, timeout=timeout)
        if r.status_code == 429:
            time.sleep(5)
            r = sess.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  API error: {e}")
        return None


# ── Codex formula (from indicators.py weighted_alpha) ───────────────────────
def codex_weighted_alpha(closes, lookback=250):
    """Reimplementation of dumbmoney/indicators.py weighted_alpha for closes array.
    250-period rolling-min window, log1p compression, linear weights, scale 200,
    sign from overall return direction."""
    c = np.asarray(closes, dtype=float)
    n = len(c)
    if n < 3:
        return np.nan

    scale = 200.0
    rm = pd.Series(c).rolling(lookback, min_periods=2).min().values

    i = n - 1  # last bar
    start = max(0, i - lookback + 1)
    window = c[start:i + 1]
    rm_val = rm[i]
    if np.isnan(rm_val) or rm_val <= 0 or len(window) < 2:
        return np.nan

    pct_above = np.maximum((window / rm_val) - 1.0, 0.0)
    compressed = np.log1p(pct_above)
    weights = np.linspace(0.5, 1.0, len(compressed))
    weights = weights / weights.sum()
    magnitude = float(np.dot(compressed, weights)) * scale

    if window[0] > 0:
        sign = 1.0 if window[-1] >= window[0] else -1.0
    else:
        sign = 0.0
    return magnitude * sign


# ── Download bars for a batch of symbols ────────────────────────────────────
def download_batch(symbols, start_date):
    """Download daily bars for a batch of symbols from Alpaca. Returns dict of symbol -> list of closes."""
    results = {}
    symbols_str = ",".join(symbols)
    params = {
        "symbols": symbols_str,
        "timeframe": "1Day",
        "start": start_date,
        "limit": MAX_BARS,
        "adjustment": "split",
        "feed": "iex",
        "sort": "asc",
    }
    data = api_get(f"{DATA_URL}/v2/stocks/bars", params=params)
    if not data or "bars" not in data:
        return results

    # Alpaca paginates; collect all bars
    all_bars = {}
    for sym, bars in data["bars"].items():
        all_bars[sym] = [(b["t"][:10], b["c"]) for b in bars]

    # Follow pagination
    while data.get("next_page_token"):
        params["page_token"] = data["next_page_token"]
        data = api_get(f"{DATA_URL}/v2/stocks/bars", params=params)
        if not data or "bars" not in data:
            break
        for sym, bars in data["bars"].items():
            if sym not in all_bars:
                all_bars[sym] = []
            all_bars[sym].extend([(b["t"][:10], b["c"]) for b in bars])

    for sym, bar_list in all_bars.items():
        if len(bar_list) >= MIN_BARS:
            # Sort by date ascending
            bar_list.sort(key=lambda x: x[0])
            results[sym] = [b[1] for b in bar_list]

    return results


# ── Load CSV ────────────────────────────────────────────────────────────────
def load_csv():
    df = pd.read_csv(CSV_PATH)
    # Parse Wtd Alpha: strip + and ,
    df["Wtd Alpha"] = (
        df["Wtd Alpha"]
        .astype(str)
        .str.replace("+", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    df["Wtd Alpha"] = pd.to_numeric(df["Wtd Alpha"], errors="coerce")
    df = df.dropna(subset=["Wtd Alpha"])
    return df


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("Loading CSV...")
    csv_df = load_csv()
    symbols = csv_df["Symbol"].tolist()
    barchart_wa = dict(zip(csv_df["Symbol"], csv_df["Wtd Alpha"]))
    print(f"  {len(symbols)} stocks in CSV")

    # ── Download bars ────────────────────────────────────────────────────
    # Need ~1 year of bars. Start from 1 year ago to be safe.
    start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")

    # Check cache
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)
            print(f"  Loaded {len(cache)} cached symbols")
        except Exception:
            cache = {}

    uncached = [s for s in symbols if s not in cache]
    print(f"  {len(uncached)} symbols to download (need {MIN_BARS}+ bars each)")

    # Download in batches
    n_batches = (len(uncached) + BATCH_SIZE - 1) // BATCH_SIZE
    for bi in range(n_batches):
        batch = uncached[bi * BATCH_SIZE : (bi + 1) * BATCH_SIZE]
        pct = round((bi + 1) / n_batches * 100)
        print(f"  Batch {bi+1}/{n_batches} ({pct}%): {len(batch)} symbols...", end=" ", flush=True)
        t0 = time.time()
        result = download_batch(batch, start_date)
        elapsed = round(time.time() - t0, 1)
        print(f"got {len(result)} OK ({elapsed}s)")
        cache.update(result)
        # Save cache periodically
        if (bi + 1) % 5 == 0 or bi == n_batches - 1:
            with open(CACHE_FILE, "w") as f:
                json.dump(cache, f)

    # Final cache save
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

    # ── Compute formulas ─────────────────────────────────────────────────
    from clean_weighted_alpha_formula import weighted_alpha_from_closes

    rows = []
    fitted_ok = 0
    fitted_fail = 0
    codex_ok = 0
    codex_fail = 0

    for sym in symbols:
        closes = cache.get(sym)
        barchart = barchart_wa[sym]

        # Fitted formula
        fitted_val = None
        try:
            fitted_val = weighted_alpha_from_closes(closes)
            fitted_ok += 1
        except Exception:
            fitted_fail += 1

        # Codex formula
        codex_val = None
        try:
            codex_val = codex_weighted_alpha(closes)
            if codex_val is not None and np.isfinite(codex_val):
                codex_ok += 1
            else:
                codex_val = None
                codex_fail += 1
        except Exception:
            codex_fail += 1

        rows.append({
            "symbol": sym,
            "barchart_wa": barchart,
            "fitted_wa": fitted_val,
            "codex_wa": codex_val,
            "bars": len(closes) if closes else 0,
        })

    rdf = pd.DataFrame(rows)

    # ── Stats ────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"Total stocks in CSV:              {len(symbols)}")
    print(f"Cached/downloaded bars OK:        {len(cache)}")
    print(f"Fitted formula OK / fail:         {fitted_ok} / {fitted_fail}")
    print(f"Codex formula OK / fail:          {codex_ok} / {codex_fail}")

    # Compare fitted vs Barchart
    fitted_df = rdf.dropna(subset=["fitted_wa"])
    if len(fitted_df) >= 3:
        spearman_f = fitted_df["fitted_wa"].corr(fitted_df["barchart_wa"], method="spearman")
        kendall_f = fitted_df["fitted_wa"].corr(fitted_df["barchart_wa"], method="kendall")
        mae_f = (fitted_df["fitted_wa"] - fitted_df["barchart_wa"]).abs().mean()
        rmse_f = np.sqrt(((fitted_df["fitted_wa"] - fitted_df["barchart_wa"]) ** 2).mean())
        print(f"\n--- Fitted Formula vs Barchart ({len(fitted_df)} stocks) ---")
        print(f"  Spearman correlation:  {spearman_f:.4f}")
        print(f"  Kendall tau:           {kendall_f:.4f}")
        print(f"  MAE:                   {mae_f:.2f}")
        print(f"  RMSE:                  {rmse_f:.2f}")

        # Rank position accuracy
        fitted_df = fitted_df.copy()
        fitted_df["rank_bc"] = fitted_df["barchart_wa"].rank(ascending=False)
        fitted_df["rank_fitted"] = fitted_df["fitted_wa"].rank(ascending=False)
        fitted_df["rank_diff"] = (fitted_df["rank_bc"] - fitted_df["rank_fitted"]).abs()
        median_rank_err = fitted_df["rank_diff"].median()
        within_50 = (fitted_df["rank_diff"] <= 50).mean() * 100
        within_100 = (fitted_df["rank_diff"] <= 100).mean() * 100
        print(f"  Median rank error:     {median_rank_err:.1f}")
        print(f"  Within 50 ranks:       {within_50:.1f}%")
        print(f"  Within 100 ranks:      {within_100:.1f}%")
    else:
        print("\n--- Fitted Formula: insufficient data ---")

    # Compare codex vs Barchart
    codex_df = rdf.dropna(subset=["codex_wa"])
    if len(codex_df) >= 3:
        spearman_c = codex_df["codex_wa"].corr(codex_df["barchart_wa"], method="spearman")
        kendall_c = codex_df["codex_wa"].corr(codex_df["barchart_wa"], method="kendall")
        mae_c = (codex_df["codex_wa"] - codex_df["barchart_wa"]).abs().mean()
        rmse_c = np.sqrt(((codex_df["codex_wa"] - codex_df["barchart_wa"]) ** 2).mean())
        print(f"\n--- Codex Formula vs Barchart ({len(codex_df)} stocks) ---")
        print(f"  Spearman correlation:  {spearman_c:.4f}")
        print(f"  Kendall tau:           {kendall_c:.4f}")
        print(f"  MAE:                   {mae_c:.2f}")
        print(f"  RMSE:                  {rmse_c:.2f}")

        codex_df = codex_df.copy()
        codex_df["rank_bc"] = codex_df["barchart_wa"].rank(ascending=False)
        codex_df["rank_codex"] = codex_df["codex_wa"].rank(ascending=False)
        codex_df["rank_diff"] = (codex_df["rank_bc"] - codex_df["rank_codex"]).abs()
        median_rank_err_c = codex_df["rank_diff"].median()
        within_50_c = (codex_df["rank_diff"] <= 50).mean() * 100
        within_100_c = (codex_df["rank_diff"] <= 100).mean() * 100
        print(f"  Median rank error:     {median_rank_err_c:.1f}")
        print(f"  Within 50 ranks:       {within_50_c:.1f}%")
        print(f"  Within 100 ranks:      {within_100_c:.1f}%")
    else:
        print("\n--- Codex Formula: insufficient data ---")

    # Save full results
    out_path = os.path.join(os.path.dirname(__file__), "compare_fitted_vs_barchart.csv")
    rdf.to_csv(out_path, index=False)
    print(f"\nFull results saved to: {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
