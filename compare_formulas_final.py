"""
Compare Fitted (70-feature) vs Codex (SMA4 + caps) Weighted Alpha
against Barchart reference data.

Both formulas use daily close prices only.
"""

import json
import csv
import math
import sys
import os
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ── Load Barchart reference ──────────────────────────────────────────────
CSV_PATH = r"C:\Users\Admin\Downloads\stocks-screener-weighted-alpha-52-high-07-17-2026.csv"
DB_PATH = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db"
MODEL_PATH = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\clean_weighted_alpha_model.json"
FORMULA_PATH = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\clean_weighted_alpha_formula.py"

def load_barchart():
    """Load Barchart CSV, strip + and , from Wtd Alpha."""
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            sym = r.get("Symbol", "").strip()
            wa_val = r.get("Wtd Alpha")
            if not sym or not wa_val:
                continue
            raw = wa_val.strip().replace("+", "").replace(",", "")
            try:
                val = float(raw)
            except (ValueError, TypeError):
                continue
            rows.append((sym, val))
    return rows


# ── Fitted formula (70-feature regression) ───────────────────────────────
# Import from the copied file
sys.path.insert(0, os.path.dirname(__file__))
from clean_weighted_alpha_formula import (
    weighted_alpha_from_closes as fitted_wa,
    MODEL as fitted_model,
)


# ── Codex formula (from markdown: SMA4 + -6%/+5% caps + linear weights) ─
def codex_weighted_alpha(closes, lookback=250, smooth=4):
    """Exact Codex daily formula from the markdown.
    
    1. 4-bar SMA smoothing on close
    2. 250 smoothed returns
    3. Clip each to [-6%, +5%]
    4. Linear weights 0.5 → 1.0
    5. Scale = 100 / 0.75
    """
    closes = np.asarray(closes, dtype=np.float64)
    if len(closes) < lookback + smooth:
        return None
    
    # 4-bar SMA via convolution
    sma = np.convolve(closes, np.ones(smooth) / smooth, mode='valid')
    if len(sma) < 2:
        return None
    
    # Smoothed returns
    rets = sma[1:] / sma[:-1] - 1.0
    
    # Take last 250
    if len(rets) < lookback:
        return None
    rets = rets[-lookback:]
    
    # Clip
    L, U = -0.06, 0.05
    clipped = np.clip(rets, L, U)
    
    # Linear weights
    w = np.linspace(0.5, 1.0, lookback)
    wn = w / w.mean()
    
    # Scale
    wa = float(np.dot(wn, clipped)) * (100.0 / 0.75)
    return wa


def codex_weighted_alpha_no_smooth(closes, lookback=250):
    """Codex formula WITHOUT 4-bar SMA (raw daily returns)."""
    closes = np.asarray(closes, dtype=np.float64)
    if len(closes) < lookback + 1:
        return None
    
    rets = closes[1:] / closes[:-1] - 1.0
    rets = rets[-lookback:]
    
    L, U = -0.06, 0.05
    clipped = np.clip(rets, L, U)
    
    w = np.linspace(0.5, 1.0, lookback)
    wn = w / w.mean()
    
    wa = float(np.dot(wn, clipped)) * (100.0 / 0.75)
    return wa


# ── Spearman rank correlation ────────────────────────────────────────────
def spearman_ranks(values):
    """Return ranks (1-based) for a list of values. Ties get average rank."""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = np.empty(n)
    i = 0
    while i < n:
        j = i
        while j < n - 1 and indexed[j + 1][1] == indexed[j][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def spearman_correlation(a, b):
    """Spearman rank correlation between two arrays."""
    ra = spearman_ranks(a)
    rb = spearman_ranks(b)
    n = len(a)
    mean_ra = ra.mean()
    mean_rb = rb.mean()
    cov = np.sum((ra - mean_ra) * (rb - mean_rb))
    std_a = np.sqrt(np.sum((ra - mean_ra) ** 2))
    std_b = np.sqrt(np.sum((rb - mean_rb) ** 2))
    if std_a == 0 or std_b == 0:
        return 0.0
    return float(cov / (std_a * std_b))


# ── Load bars from DB ────────────────────────────────────────────────────
def load_bars(symbol, min_bars=300):
    """Load daily closes for a symbol from screener.db."""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        cur = conn.execute(
            "SELECT date, close FROM bars WHERE symbol = ? ORDER BY date ASC",
            (symbol,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    
    if len(rows) < min_bars:
        return None
    
    closes = np.array([r[1] for r in rows], dtype=np.float64)
    dates = [r[0] for r in rows]
    return closes, dates


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("FITTED (70-feature) vs CODEX (SMA4 + caps) Weighted Alpha")
    print("Against Barchart reference data")
    print("=" * 70)
    
    barchart = load_barchart()
    print(f"\nBarchart CSV: {len(barchart)} stocks")
    
    # Try loading from Alpaca API for stocks not in DB
    # For now, use DB only
    fitted_vals = []
    codex_vals = []
    codex_nosmooth_vals = []
    barchart_vals = []
    matched_syms = []
    skipped = 0
    
    for sym, bc_wa in barchart:
        result = load_bars(sym, min_bars=300)
        if result is None:
            skipped += 1
            continue
        
        closes, dates = result
        
        # Fitted formula
        try:
            fw = fitted_wa(closes, reject_split_like=True)
        except ValueError:
            skipped += 1
            continue
        
        # Codex with 4-bar SMA
        cw = codex_weighted_alpha(closes, lookback=250, smooth=4)
        if cw is None:
            skipped += 1
            continue
        
        # Codex without smoothing
        cw_ns = codex_weighted_alpha_no_smooth(closes, lookback=250)
        
        fitted_vals.append(fw)
        codex_vals.append(cw)
        codex_nosmooth_vals.append(cw_ns if cw_ns is not None else 0.0)
        barchart_vals.append(bc_wa)
        matched_syms.append(sym)
    
    fitted_vals = np.array(fitted_vals)
    codex_vals = np.array(codex_vals)
    codex_nosmooth_vals = np.array(codex_nosmooth_vals)
    barchart_vals = np.array(barchart_vals)
    
    print(f"Matched: {len(matched_syms)}")
    print(f"Skipped (no bars / split outlier): {skipped}")
    
    # ── Stats ────────────────────────────────────────────────────────
    def stats(name, computed, actual):
        spear = spearman_correlation(computed, actual)
        mae = np.mean(np.abs(computed - actual))
        rmse = np.sqrt(np.mean((computed - actual) ** 2))
        median_err = np.median(np.abs(computed - actual))
        
        # Rank accuracy
        rc = spearman_ranks(computed)
        ra = spearman_ranks(actual)
        rank_err = np.abs(rc - ra)
        within_50 = np.mean(rank_err <= 50) * 100
        within_100 = np.mean(rank_err <= 100) * 100
        
        print(f"\n{'-' * 50}")
        print(f"  {name}")
        print(f"{'-' * 50}")
        print(f"  Spearman:        {spear:.6f}")
        print(f"  MAE:             {mae:.4f}")
        print(f"  RMSE:            {rmse:.4f}")
        print(f"  Median error:    {median_err:.4f}")
        print(f"  Rank ±50:        {within_50:.1f}%")
        print(f"  Rank ±100:       {within_100:.1f}%")
        
        # Sample top 5
        print(f"\n  Top 5 by Barchart:")
        top_idx = np.argsort(actual)[-5:][::-1]
        for i in top_idx:
            print(f"    {matched_syms[i]:8s}  BC={actual[i]:10.2f}  "
                  f"Fitted={computed[i]:10.2f}  Diff={actual[i]-computed[i]:8.2f}")
        
        return spear, mae, rmse
    
    print("\n" + "=" * 70)
    s1, m1, r1 = stats("FITTED FORMULA (70-feature regression)", fitted_vals, barchart_vals)
    s2, m2, r2 = stats("CODEX FORMULA (SMA4 + caps)", codex_vals, barchart_vals)
    s3, m3, r3 = stats("CODEX NO-SMOOTH (raw daily returns)", codex_nosmooth_vals, barchart_vals)
    
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(f"  {'Formula':<30} {'Spearman':>10} {'MAE':>10} {'RMSE':>10}")
    print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10}")
    print(f"  {'Fitted (70-feature)':<30} {s1:>10.4f} {m1:>10.2f} {r1:>10.2f}")
    print(f"  {'Codex (SMA4 + caps)':<30} {s2:>10.4f} {m2:>10.2f} {r2:>10.2f}")
    print(f"  {'Codex (no smooth)':<30} {s3:>10.4f} {m3:>10.2f} {r3:>10.2f}")
    
    # Save full results
    out_path = os.path.join(os.path.dirname(__file__), "compare_final_results.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "barchart_wa", "fitted_wa", "codex_wa", "codex_nosmooth_wa"])
        for i, sym in enumerate(matched_syms):
            w.writerow([sym, f"{barchart_vals[i]:.4f}", f"{fitted_vals[i]:.4f}",
                        f"{codex_vals[i]:.4f}", f"{codex_nosmooth_vals[i]:.4f}"])
    print(f"\nFull results saved to: {out_path}")


if __name__ == "__main__":
    main()
