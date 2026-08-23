"""Deterministic synthetic OHLCV builders for retest engine tests.

Bars: (open, high, low, close, volume). Deterministic (no randomness).
- flat(close, n): n steady bars (high=close+span, low=close-span).
- ramp(start, end, n): linear closes start->end; open=prev close; high=max(c,pc)+span.
- spike(high_price, base): pivot bar (close=high_price-0.05, high=high_price,
  low=high_price-1.55) followed by a red follow-through bar closing 4 below the
  high, so the pivot high is a strict local max across its +-5 neighborhood.
"""
import datetime as dt

import numpy as np

from dumbmoney.retest_engine import wilders_atr

SPAN = 0.55


def dates(n, start="2024-01-02"):
    d = dt.date.fromisoformat(start)
    out = []
    for _ in range(n):
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def flat(close, n, vol=2_000_000.0):
    return [(close, close + SPAN, close - SPAN, close, vol) for _ in range(n)]


def ramp(start, end, n, vol=2_000_000.0):
    rows = []
    prev = start
    for c in np.linspace(start, end, n):
        h = max(c, prev) + SPAN
        lo = min(c, prev) - SPAN
        rows.append((prev, h, lo, float(c), vol))
        prev = float(c)
    return rows


def spike(high_price, base, vol=2_000_000.0):
    c1 = high_price - 0.05
    lo1 = high_price - 1.55
    c2 = high_price - 4.0
    return [(base, high_price, lo1, c1, vol), (c1, c1, c2 - SPAN, c2, vol)]


def hand(*bars):
    return list(bars)


def bar(o, h, l, c, vol=2_000_000.0):
    return (o, h, l, c, vol)


def series(blocks):
    rows = []
    for b in blocks:
        rows.extend(b)
    o = np.array([r[0] for r in rows], dtype=float)
    h = np.array([r[1] for r in rows], dtype=float)
    l = np.array([r[2] for r in rows], dtype=float)
    c = np.array([r[3] for r in rows], dtype=float)
    v = np.array([r[4] for r in rows], dtype=float)
    return o, h, l, c, v


def run(blocks, market="US", symbol="TEST", score_fn=None):
    from dumbmoney.retest_engine import fold_symbol

    o, h, l, c, v = series(blocks)
    d = dates(len(c))
    return fold_symbol(h, l, c, o, v, d, market, symbol, score_fn=score_fn)


def atr_of(blocks, idx=-1):
    o, h, l, c, v = series(blocks)
    return float(wilders_atr(h, l, c)[idx])


# -------------------------------------------------------------------- scenario
def old_swing_scenario(pivot_idx=40, pivot_high=108.0, post_flat=4, breakout_ramp=9,
                       breakout_end=108.5, descent_end=101.0, warmup=40):
    """Blocks: warmup flat -> spike pivot -> descent -> flat -> breakout ramp.

    Breakout crossing bar = pivot_idx + 3 + post_flat + 7 (9-bar ramp crosses at
    its last bar). Age at crossing = 16 + post_flat.
    """
    blocks = [flat(100.0, warmup)]
    blocks.append(spike(pivot_high, 100.0))
    blocks.append(ramp(pivot_high - 4.0, descent_end, 6))
    blocks.append(flat(descent_end, post_flat))
    blocks.append(ramp(descent_end, breakout_end, breakout_ramp))
    return blocks


def confirm_scenario():
    """Breakout -> hold 4 bars above -> touch (confirmable) -> confirm -> target."""
    blocks = old_swing_scenario(pivot_idx=40, post_flat=4)  # crossing at bar 60, age 20
    crossing = 60
    blocks.append(flat(108.5, 2))            # 61..62 hold above (delay ramps)
    blocks.append(ramp(108.5, 107.4, 1))     # 63 touch, close 107.4 (below confirm line)
    blocks.append(ramp(107.4, 108.0, 1))     # 64 confirm close 108.0
    blocks.append(ramp(108.0, 111.0, 6))     # 65..70 target close >= entry+2ATR
    return blocks, {"crossing": crossing}
