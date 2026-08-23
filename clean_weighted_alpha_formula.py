"""OHLCV-only clean-subset weighted-alpha approximation.

The fitted coefficients are stored beside this file in
clean_weighted_alpha_model.json.  The model was fit only to symbols having
at least 253 1Day closes through 2026-07-16 and no split-like close jump in
the latest 253 closes.
"""

import json
from pathlib import Path

import numpy as np


MODEL = json.loads(
    (Path(__file__).with_name("clean_weighted_alpha_model.json")).read_text(
        encoding="utf-8"
    )
)


def _make_features(closes, caps=(0.25, 0.5, 0.75, 1.0, 2.0), ns=(189, 252)):
    p_all = np.asarray(closes, dtype=float)[-253:]
    out, names = [], []
    for n in ns:
        p = p_all[-n - 1:]
        dlevel = np.diff(p) / p[0]
        dret = p[1:] / p[:-1] - 1.0
        logret = np.diff(np.log(p))
        w = np.linspace(0.5, 1.0, n)
        wn = w / w.mean()
        wp = np.linspace(0.5, 1.0, n + 1)

        def add(name, value):
            names.append(f"{name}_{n}")
            out.append(float(value))

        add("raw", (p[-1] / p[0] - 1.0) * 100.0)
        add("cumavg", np.sum(wp * (p / p[0] - 1.0)) / np.sum(wp) * 100.0)
        add("cumavglog", np.sum(wp * np.log(p / p[0])) / np.sum(wp) * 100.0)
        add("levelsum", np.sum(w * dlevel) * 100.0)
        add("levelsum_norm", np.sum(wn * dlevel) * 100.0)
        add("dailyret", np.sum(w * dret) * 100.0)
        add("dailyret_norm", np.sum(wn * dret) * 100.0)
        add("dailylog", np.sum(w * logret) * 100.0)
        add("dailylog_norm", np.sum(wn * logret) * 100.0)
        add("max_cum", (np.max(p) / p[0] - 1.0) * 100.0)
        add("min_cum", (np.min(p) / p[0] - 1.0) * 100.0)
        add("positive_dlevel", np.sum(w * np.maximum(dlevel, 0.0)) * 100.0)
        add("negative_dlevel", np.sum(w * np.minimum(dlevel, 0.0)) * 100.0)
        for cap in caps:
            add(f"levelcap{cap}", np.sum(w * np.clip(dlevel, -cap, cap)) * 100.0)
            add(f"levelcap{cap}_norm", np.sum(wn * np.clip(dlevel, -cap, cap)) * 100.0)
        for cap in (0.05, 0.10, 0.20, 0.30, 0.50, 1.0):
            add(f"retcap{cap}", np.sum(w * np.clip(dret, -cap, cap)) * 100.0)
            add(f"logcap{cap}", np.sum(w * np.clip(logret, -cap, cap)) * 100.0)
    return np.asarray([out[names.index(name)] for name in MODEL["features"]], dtype=float)


def weighted_alpha_from_closes(closes, reject_split_like=True):
    """Return the reconstructed weighted alpha from chronological daily closes.

    Supply at least 253 positive, finite daily closes, ending at the same
    snapshot date used for the fit.  The function uses only close prices;
    open/high/low/volume are not needed by this fitted approximation.
    """
    closes = np.asarray(closes, dtype=float)
    if len(closes) < MODEL["minimum_daily_bars"]:
        raise ValueError("At least 253 chronological daily closes are required")
    if not np.all(np.isfinite(closes)) or np.any(closes <= 0):
        raise ValueError("All closes must be finite and positive")
    latest = closes[-MODEL["minimum_daily_bars"]:]
    ratios = latest[1:] / latest[:-1]
    if reject_split_like and np.any(
        (ratios <= MODEL["outlier_low_ratio"]) | (ratios >= MODEL["outlier_high_ratio"])
    ):
        raise ValueError("Split-like close discontinuity detected; exclude this symbol")
    x = _make_features(closes)
    z = (x - np.asarray(MODEL["mean"], dtype=float)) / np.asarray(MODEL["std"], dtype=float)
    transformed = float(MODEL["coef_intercept"]) + float(np.dot(z, np.asarray(MODEL["coef_standardized"], dtype=float)))
    return float(max(transformed, 0.0) ** (1.0 / float(MODEL["target_power"])))
