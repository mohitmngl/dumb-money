import numpy as np
from intraday_backtest.config import (
    WA_SMOOTH_WINDOW, WA_LOOKBACK, WA_L_CAP, WA_U_CAP
)


def weighted_alpha_batch(batch_prices_276):
    """Compute Weighted Alpha for all batches from latest 276 batch prices.

    Uses numpy for speed. Exact spec from WEIGHTED_ALPHA_EXACT_REFERENCE.md.

    Args:
        batch_prices_276: (276, K) array of latest 276 batch prices

    Returns:
        wa: (K,) array of Weighted Alpha values
    """
    bp = np.asarray(batch_prices_276, dtype=np.float32)  # (276, K) float32 for speed
    K = bp.shape[1]

    # SMA(WA_SMOOTH_WINDOW) via cumsum
    cs = np.cumsum(bp, axis=0)  # (276, K)
    padded = np.vstack([np.zeros((WA_SMOOTH_WINDOW, K)), cs])  # (302, K)
    sma = (padded[WA_SMOOTH_WINDOW:] - padded[:len(bp)]) / float(WA_SMOOTH_WINDOW)  # (276, K)
    sma = sma[WA_SMOOTH_WINDOW - 1:]  # (251, K)

    # Smoothed returns: 250 values
    with np.errstate(divide='ignore', invalid='ignore'):
        r_smooth = sma[1:] / sma[:-1] - 1.0  # (250, K)
    r_smooth = np.nan_to_num(r_smooth, nan=0.0, posinf=0.0, neginf=0.0)

    # Clip
    r_clipped = np.clip(r_smooth, WA_L_CAP, WA_U_CAP)

    # Linear recency weights
    w = 0.5 + 0.5 * np.arange(WA_LOOKBACK) / (WA_LOOKBACK - 1.0)
    w_mean = float(np.mean(w))  # 0.75

    # Weighted Alpha: (100 / mean(w)) * sum(w * r*)
    wa = (100.0 / w_mean) * (r_clipped.T @ w)  # (K,)

    return wa


def weighted_alpha_single(price_series):
    """Weighted Alpha for a single price series."""
    bp = np.asarray(price_series, dtype=np.float64)
    cs = np.cumsum(bp)
    padded = np.concatenate([np.zeros(WA_SMOOTH_WINDOW), cs])
    sma = (padded[WA_SMOOTH_WINDOW:] - padded[:len(bp)]) / float(WA_SMOOTH_WINDOW)
    sma = sma[WA_SMOOTH_WINDOW - 1:]

    with np.errstate(divide='ignore', invalid='ignore'):
        r_smooth = sma[1:] / sma[:-1] - 1.0
    r_smooth = np.nan_to_num(r_smooth, nan=0.0)

    r_clipped = np.clip(r_smooth, WA_L_CAP, WA_U_CAP)
    w = 0.5 + 0.5 * np.arange(WA_LOOKBACK) / (WA_LOOKBACK - 1.0)
    w_mean = float(np.mean(w))

    return float((100.0 / w_mean) * np.dot(w, r_clipped))
