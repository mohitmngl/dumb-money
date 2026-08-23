"""Compare Fitted vs Codex WA using CS (Barchart) rank positions."""

import csv
import sqlite3
import numpy as np
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from clean_weighted_alpha_formula import weighted_alpha_from_closes as fitted_wa

CSV_PATH = r"C:\Users\Admin\Downloads\stocks-screener-weighted-alpha-52-high-07-17-2026.csv"
DB_PATH = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db"


def load_barchart():
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
            except:
                continue
            rows.append((sym, val))
    return rows


def codex_wa(closes, lookback=250, smooth=4):
    closes = np.asarray(closes, dtype=np.float64)
    if len(closes) < lookback + smooth:
        return None
    sma = np.convolve(closes, np.ones(smooth) / smooth, mode="valid")
    if len(sma) < 2:
        return None
    rets = sma[1:] / sma[:-1] - 1.0
    if len(rets) < lookback:
        return None
    rets = rets[-lookback:]
    clipped = np.clip(rets, -0.06, 0.05)
    w = np.linspace(0.5, 1.0, lookback)
    wn = w / w.mean()
    return float(np.dot(wn, clipped)) * (100.0 / 0.75)


def load_bars(sym):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        cur = conn.execute("SELECT close FROM bars WHERE symbol=? ORDER BY date ASC", (sym,))
        closes = np.array([r[0] for r in cur.fetchall()], dtype=np.float64)
    finally:
        conn.close()
    return closes if len(closes) >= 300 else None


def spearman_ranks(vals):
    n = len(vals)
    idx = sorted(range(n), key=lambda i: vals[i])
    ranks = np.empty(n)
    i = 0
    while i < n:
        j = i
        while j < n - 1 and vals[idx[j + 1]] == vals[idx[j]]:
            j += 1
        for k in range(i, j + 1):
            ranks[idx[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def main():
    barchart = load_barchart()
    print(f"Barchart CSV: {len(barchart)} stocks")

    data = []
    for sym, bc_wa in barchart:
        closes = load_bars(sym)
        if closes is None:
            continue
        try:
            fw = fitted_wa(closes, reject_split_like=True)
        except ValueError:
            continue
        cw = codex_wa(closes)
        if cw is None:
            continue
        data.append((sym, bc_wa, fw, cw))

    print(f"Matched: {len(data)}")

    # Assign Barchart ranks (1=highest)
    data_sorted_bc = sorted(data, key=lambda x: x[1], reverse=True)
    bc_ranks = {}
    for i, (sym, bc, fw, cw) in enumerate(data_sorted_bc):
        bc_ranks[sym] = i + 1

    # Assign Fitted ranks
    data_sorted_fw = sorted(data, key=lambda x: x[2], reverse=True)
    fw_ranks = {}
    for i, (sym, bc, fw, cw) in enumerate(data_sorted_fw):
        fw_ranks[sym] = i + 1

    # Assign Codex ranks
    data_sorted_cw = sorted(data, key=lambda x: x[3], reverse=True)
    cw_ranks = {}
    for i, (sym, bc, fw, cw) in enumerate(data_sorted_cw):
        cw_ranks[sym] = i + 1

    # Print rank comparison for top/bottom stocks
    print("\n" + "=" * 80)
    print(f"{'Symbol':>8} {'BC_WA':>10} {'BC_Rank':>8} {'FW_WA':>10} {'FW_Rank':>8} {'FW_Err':>7} {'CW_WA':>10} {'CW_Rank':>8} {'CW_Err':>7}")
    print("=" * 80)

    # Top 20 by Barchart
    print("--- TOP 20 by Barchart ---")
    for sym, bc, fw, cw in data_sorted_bc[:20]:
        br = bc_ranks[sym]
        fr = fw_ranks[sym]
        cr = cw_ranks[sym]
        print(f"{sym:>8} {bc:>10.2f} {br:>8} {fw:>10.2f} {fr:>8} {abs(br-fr):>7} {cw:>10.2f} {cr:>8} {abs(br-cr):>7}")

    # Bottom 20
    print(f"\n--- BOTTOM 20 by Barchart ---")
    for sym, bc, fw, cw in data_sorted_bc[-20:]:
        br = bc_ranks[sym]
        fr = fw_ranks[sym]
        cr = cw_ranks[sym]
        print(f"{sym:>8} {bc:>10.2f} {br:>8} {fw:>10.2f} {fr:>8} {abs(br-fr):>7} {cw:>10.2f} {cr:>8} {abs(br-cr):>7}")

    # Rank error stats
    bc_arr = np.array([bc_ranks[s] for s, _, _, _ in data])
    fw_arr = np.array([fw_ranks[s] for s, _, _, _ in data])
    cw_arr = np.array([cw_ranks[s] for s, _, _, _ in data])

    fw_err = np.abs(bc_arr - fw_arr)
    cw_err = np.abs(bc_arr - cw_arr)

    print("\n" + "=" * 80)
    print("RANK ERROR STATS (lower = better)")
    print("=" * 80)
    print(f"{'Metric':<25} {'Fitted':>12} {'Codex':>12}")
    print(f"{'-'*25} {'-'*12} {'-'*12}")
    print(f"{'Mean rank error':<25} {np.mean(fw_err):>12.1f} {np.mean(cw_err):>12.1f}")
    print(f"{'Median rank error':<25} {np.median(fw_err):>12.1f} {np.median(cw_err):>12.1f}")
    print(f"{'Max rank error':<25} {np.max(fw_err):>12.0f} {np.max(cw_err):>12.0f}")
    print(f"{'Within 10 ranks':<25} {np.mean(fw_err<=10)*100:>11.1f}% {np.mean(cw_err<=10)*100:>11.1f}%")
    print(f"{'Within 25 ranks':<25} {np.mean(fw_err<=25)*100:>11.1f}% {np.mean(cw_err<=25)*100:>11.1f}%")
    print(f"{'Within 50 ranks':<25} {np.mean(fw_err<=50)*100:>11.1f}% {np.mean(cw_err<=50)*100:>11.1f}%")
    print(f"{'Within 100 ranks':<25} {np.mean(fw_err<=100)*100:>11.1f}% {np.mean(cw_err<=100)*100:>11.1f}%")

    # Spearman
    spear_fw = spearman_ranks(bc_arr.tolist()) 
    # Actually compute Spearman correlation properly
    def spearman(a, b):
        ra = np.argsort(np.argsort(a)).astype(float) + 1
        rb = np.argsort(np.argsort(b)).astype(float) + 1
        n = len(a)
        return 1 - 6 * np.sum((ra - rb)**2) / (n * (n**2 - 1))

    s_fw = spearman(bc_arr, fw_arr)
    s_cw = spearman(bc_arr, cw_arr)
    print(f"\n{'Spearman with BC ranks':<25} {s_fw:>12.6f} {s_cw:>12.6f}")

    # Top 10 overlap
    bc_top10 = set(s for s, _, _, _ in data_sorted_bc[:10])
    fw_top10 = set(s for s, _, _, _ in data_sorted_fw[:10])
    cw_top10 = set(s for s, _, _, _ in data_sorted_cw[:10])
    print(f"\nTop-10 overlap with BC:")
    print(f"  Fitted: {len(bc_top10 & fw_top10)}/10 = {bc_top10 & fw_top10}")
    print(f"  Codex:  {len(bc_top10 & cw_top10)}/10 = {bc_top10 & cw_top10}")

    bc_top50 = set(s for s, _, _, _ in data_sorted_bc[:50])
    fw_top50 = set(s for s, _, _, _ in data_sorted_fw[:50])
    cw_top50 = set(s for s, _, _, _ in data_sorted_cw[:50])
    print(f"\nTop-50 overlap with BC:")
    print(f"  Fitted: {len(bc_top50 & fw_top50)}/50")
    print(f"  Codex:  {len(bc_top50 & cw_top50)}/50")


if __name__ == "__main__":
    main()
