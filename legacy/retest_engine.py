"""
OLD_SWING_RETEST_SCORE Engine

Detects old swing-high resistance breakouts, retests, and scores the current
opportunity quality. All detection uses only data available at each point in
time (no future leakage).

Main entry points:
  compute_retest_score_for_symbol(grp)  -- per-symbol, returns score series
  compute_retest_score_current(grp)     -- current-mode, returns single float
"""

import numpy as np
import pandas as pd
import logging
import os
import numba as _numba

logger = logging.getLogger(__name__)

_HAS_NUMBA = True
try:
    from numba import njit, prange
except ImportError:
    _HAS_NUMBA = False
    def njit(f=None, **kw):
        if f is None:
            return lambda fn: fn
        return f
    prange = range

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SWING_LEFT = 5
SWING_RIGHT = 5
SWING_MIN_PROMINENCE_ATR = 1.5
CLUSTER_DISTANCE_ATR = 0.4
BREAKOUT_MIN_DISTANCE_ATR = 0.25
RETEST_LOW_MIN_ATR = -1.50
RETEST_LOW_MAX_ATR = 1.00
RETEST_CLOSE_CONFIRM_ATR = -0.70
RETEST_INVALIDATE_ATR = -2.00
UPPER_BARRIER_ATR = 2.0
LOWER_BARRIER_ATR = 0.75
TIME_BARRIER = 20


# ===================================================================
# 1. SWING HIGH DETECTION (Numba)
# ===================================================================

@njit(cache=True)
def _detect_swing_highs_numba(high, low, left, right):
    """Detect confirmed swing highs using left/right bar pivots.

    Returns arrays of swing-high indices and their prices.
    A swing high at index i requires high[i] > high[i-left:i] and
    high[i] > high[i+1:i+right+1].
    """
    n = len(high)
    count = 0
    idxs = np.empty(n, dtype=np.int64)
    prices = np.empty(n, dtype=np.float64)

    for i in range(left, n - right):
        is_swing = True
        for j in range(i - left, i):
            if high[j] >= high[i]:
                is_swing = False
                break
        if not is_swing:
            continue
        for j in range(i + 1, i + right + 1):
            if j < n and high[j] >= high[i]:
                is_swing = False
                break
        if is_swing:
            idxs[count] = i
            prices[count] = high[i]
            count += 1

    return idxs[:count], prices[:count]


@njit(cache=True)
def _compute_atr_numba(high, low, close, period=14):
    """Compute ATR using Wilder's smoothing."""
    n = len(close)
    atr = np.zeros(n, dtype=np.float64)
    if n < 2:
        return atr
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))
    atr[0] = tr[0]
    alpha = 1.0 / period
    for i in range(1, n):
        atr[i] = atr[i - 1] * (1.0 - alpha) + tr[i] * alpha
    return atr


@njit(cache=True)
def _prominence_of_swing(high, low, swing_idx, swing_price, lookback=50):
    """Compute prominence: how far above surrounding lows this swing high is."""
    n = len(low)
    start = max(0, swing_idx - lookback)
    end = min(n, swing_idx + lookback + 1)
    min_low = low[start]
    for i in range(start + 1, end):
        if low[i] < min_low:
            min_low = low[i]
    return swing_price - min_low


@njit(cache=True)
def _filter_and_cluster_numba(swing_idxs, swing_prices, high, low, atr,
                               min_prominence_atr, cluster_dist_atr):
    """Filter by prominence and cluster nearby swing highs.

    Returns clustered zone arrays: zone_levels, zone_prominences,
    zone_touches, zone_widths, zone_start_idxs.
    """
    n_swings = len(swing_idxs)
    if n_swings == 0:
        return (np.empty(0, dtype=np.float64),
                np.empty(0, dtype=np.float64),
                np.zeros(0, dtype=np.int32),
                np.empty(0, dtype=np.float64),
                np.zeros(0, dtype=np.int64))

    # Compute prominence for each swing
    prominences = np.empty(n_swings, dtype=np.float64)
    for i in range(n_swings):
        prominences[i] = _prominence_of_swing(high, low, swing_idxs[i],
                                                swing_prices[i])

    # Filter by minimum prominence
    valid_count = 0
    v_idxs = np.empty(n_swings, dtype=np.int64)
    v_prices = np.empty(n_swings, dtype=np.float64)
    v_proms = np.empty(n_swings, dtype=np.float64)
    for i in range(n_swings):
        if prominences[i] >= min_prominence_atr * atr[max(0, min(swing_idxs[i], len(atr)-1))]:
            v_idxs[valid_count] = swing_idxs[i]
            v_prices[valid_count] = swing_prices[i]
            v_proms[valid_count] = prominences[i]
            valid_count += 1

    if valid_count == 0:
        return (np.empty(0, dtype=np.float64),
                np.empty(0, dtype=np.float64),
                np.zeros(0, dtype=np.int32),
                np.empty(0, dtype=np.float64),
                np.zeros(0, dtype=np.int64))

    v_idxs = v_idxs[:valid_count]
    v_prices = v_prices[:valid_count]
    v_proms = v_proms[:valid_count]

    # Cluster: merge swings within cluster_dist_atr of each other
    clustered = np.zeros(valid_count, dtype=np.bool_)
    zone_levels = np.empty(valid_count, dtype=np.float64)
    zone_proms = np.empty(valid_count, dtype=np.float64)
    zone_touches = np.zeros(valid_count, dtype=np.int32)
    zone_widths = np.empty(valid_count, dtype=np.float64)
    zone_starts = np.zeros(valid_count, dtype=np.int64)
    n_zones = 0

    for i in range(valid_count):
        if clustered[i]:
            continue
        clustered[i] = True
        a_idx = v_idxs[i]
        a_price = v_prices[i]
        w_prom = v_proms[i]
        w_sum = v_proms[i]
        min_p = a_price
        max_p = a_price
        touch = 1

        for j in range(i + 1, valid_count):
            if clustered[j]:
                continue
            cur_atr = atr[max(0, min(int(v_idxs[j]), len(atr)-1))]
            if abs(v_prices[j] - a_price) <= cluster_dist_atr * cur_atr:
                clustered[j] = True
                w_prom += v_proms[j]
                w_sum += v_proms[j]
                a_price = (a_price * touch + v_prices[j]) / (touch + 1)
                if v_prices[j] < min_p:
                    min_p = v_prices[j]
                if v_prices[j] > max_p:
                    max_p = v_prices[j]
                touch += 1

        zone_levels[n_zones] = a_price
        zone_proms[n_zones] = w_prom
        zone_touches[n_zones] = touch
        zone_widths[n_zones] = max_p - min_p
        zone_starts[n_zones] = v_idxs[i]
        n_zones += 1

    return (zone_levels[:n_zones], zone_proms[:n_zones],
            zone_touches[:n_zones], zone_widths[:n_zones],
            zone_starts[:n_zones])


# ===================================================================
# 2. BREAKOUT DETECTION (Numba)
# ===================================================================

@njit(cache=True)
def _detect_breakouts_numba(close, high, low, volume, atr, vol_sma20,
                             zone_levels, zone_widths, zone_starts):
    """Detect breakouts above each resistance zone.

    Returns per-bar: breakout_level (0 = no breakout), breakout_distance_atr,
    breakout_body_atr, breakout_clv, breakout_vol_ratio.
    """
    n = len(close)
    n_zones = len(zone_levels)
    breakout_level = np.zeros(n, dtype=np.float64)
    breakout_dist = np.zeros(n, dtype=np.float64)
    breakout_body = np.zeros(n, dtype=np.float64)
    breakout_clv = np.zeros(n, dtype=np.float64)
    breakout_vol = np.zeros(n, dtype=np.float64)
    breakout_zone_idx = np.full(n, -1, dtype=np.int64)

    if n_zones == 0:
        return breakout_level, breakout_dist, breakout_body, breakout_clv, breakout_vol, breakout_zone_idx

    for i in range(SWING_LEFT + SWING_RIGHT, n):
        cur_atr = atr[i] if atr[i] > 0 else 1e-10
        for z in range(n_zones):
            # Only check if bar is after the zone was formed
            if i < zone_starts[z] + SWING_RIGHT:
                continue
            level = zone_levels[z]
            # Breakout: close >= level + 0.25 ATR
            if close[i] >= level + BREAKOUT_MIN_DISTANCE_ATR * cur_atr:
                body = abs(close[i] - (high[i] + low[i]) / 2.0)
                range_size = high[i] - low[i]
                clv = 0.0
                if range_size > 0:
                    clv = ((close[i] - low[i]) - (high[i] - close[i])) / range_size

                vol_ratio = 1.0
                if vol_sma20[i] > 0:
                    vol_ratio = volume[i] / vol_sma20[i]

                body_atr = body / cur_atr if cur_atr > 0 else 0

                # Check if this is a better breakout for this zone than existing
                if breakout_zone_idx[i] == z:
                    continue

                # Record if no breakout yet, or zone is higher (more relevant resistance)
                if breakout_level[i] == 0 or zone_levels[z] > zone_levels[breakout_zone_idx[i]]:
                    breakout_level[i] = level
                    breakout_dist[i] = (close[i] - level) / cur_atr
                    breakout_body[i] = body_atr
                    breakout_clv[i] = clv
                    breakout_vol[i] = vol_ratio
                    breakout_zone_idx[i] = z

    return breakout_level, breakout_dist, breakout_body, breakout_clv, breakout_vol, breakout_zone_idx


# ===================================================================
# 3. RETEST DETECTION (Numba)
# ===================================================================

@njit(cache=True)
def _detect_retests_numba(close, high, low, volume, atr,
                           breakout_level, bk_zone_idx,
                           zone_levels, zone_starts):
    """Detect retests after breakouts — Numba.

    For each bar after a breakout, check if price returns to the zone.
    bk_zone_idx[i] = zone index for bar i (from breakout detection).
    """
    n = len(close)
    retest_level = np.zeros(n, dtype=np.float64)
    retest_depth = np.zeros(n, dtype=np.float64)
    retest_close_rel = np.zeros(n, dtype=np.float64)
    retest_wick = np.zeros(n, dtype=np.float64)
    retest_valid = np.zeros(n, dtype=np.int32)
    retest_event = np.full(n, -1, dtype=np.int64)

    n_zones = len(zone_levels)
    active_breakout_bar = np.full(n_zones, -1, dtype=np.int64)
    active_breakout_level = np.zeros(n_zones, dtype=np.float64)
    active_event_id = np.full(n_zones, -1, dtype=np.int64)
    event_counter = 0

    for i in range(n):
        cur_atr = atr[i] if atr[i] > 0 else 1e-10

        if bk_zone_idx[i] >= 0 and breakout_level[i] > 0:
            z = int(bk_zone_idx[i])
            if z < n_zones:
                active_breakout_bar[z] = i
                active_breakout_level[z] = breakout_level[i]
                active_event_id[z] = event_counter
                event_counter += 1

        for z in range(n_zones):
            if active_breakout_bar[z] < 0:
                continue
            if i <= active_breakout_bar[z]:
                continue

            level = active_breakout_level[z]
            if close[i] < level + RETEST_INVALIDATE_ATR * cur_atr:
                retest_valid[i] = 0
                retest_event[i] = active_event_id[z]
                active_breakout_bar[z] = -1
                continue

            if (low[i] >= level + RETEST_LOW_MIN_ATR * cur_atr and
                    low[i] <= level + RETEST_LOW_MAX_ATR * cur_atr):
                if close[i] >= level + RETEST_CLOSE_CONFIRM_ATR * cur_atr:
                    retest_level[i] = level
                    retest_depth[i] = (level - low[i]) / cur_atr
                    retest_close_rel[i] = (close[i] - level) / cur_atr
                    range_size = high[i] - low[i]
                    if range_size > 0:
                        retest_wick[i] = (close[i] - low[i]) / range_size
                    else:
                        retest_wick[i] = 0.5
                    retest_valid[i] = 1
                    retest_event[i] = active_event_id[z]

    return retest_level, retest_depth, retest_close_rel, retest_wick, retest_valid, retest_event


# ===================================================================
# 4. TRADE OUTCOME LABELING (Numba)
# ===================================================================

@njit(cache=True)
def _compute_trade_outcomes_numba(close, high, low, entry_bar, entry_price,
                                   signal_atr, upper_atr, lower_atr, time_limit):
    """For each entry point, compute MFE/MAE and outcome label.

    outcome: 1 = WIN, -1 = DEEP_DRAWDOWN, 0 = TIMEOUT
    """
    n = len(close)
    n_entries = len(entry_bar)

    outcome = np.zeros(n_entries, dtype=np.int32)
    mfe_5 = np.zeros(n_entries, dtype=np.float64)
    mfe_10 = np.zeros(n_entries, dtype=np.float64)
    mfe_20 = np.zeros(n_entries, dtype=np.float64)
    mae_5 = np.zeros(n_entries, dtype=np.float64)
    mae_10 = np.zeros(n_entries, dtype=np.float64)
    mae_20 = np.zeros(n_entries, dtype=np.float64)
    days_to_1atr = np.full(n_entries, -1.0, dtype=np.float64)
    days_to_2atr = np.full(n_entries, -1.0, dtype=np.float64)
    days_to_3atr = np.full(n_entries, -1.0, dtype=np.float64)
    days_to_peak = np.full(n_entries, -1.0, dtype=np.float64)

    upper_barrier = entry_price + upper_atr * signal_atr
    lower_barrier = entry_price - lower_atr * signal_atr

    for e in range(n_entries):
        eb = entry_bar[e]
        if eb < 0 or eb >= n:
            continue
        ep = entry_price[e]
        atr_val = signal_atr[e] if signal_atr[e] > 0 else 1e-10

        peak = ep
        trough = ep
        peak_bar = 0

        won = False
        lost = False

        for j in range(eb + 1, min(eb + time_limit + 1, n)):
            days_from_entry = j - eb

            # Update peak/trough
            if high[j] > peak:
                peak = high[j]
                peak_bar = days_from_entry
            if low[j] < trough:
                trough = low[j]

            # Check barriers (conservative: check lower first if both hit)
            if low[j] <= lower_barrier and high[j] >= upper_barrier:
                lost = True
                break
            if high[j] >= upper_barrier:
                won = True
                break
            if low[j] <= lower_barrier:
                lost = True
                break

            # MFE/MAE at checkpoints
            cur_mfe = (peak - ep) / atr_val
            cur_mae = (trough - ep) / atr_val
            if days_from_entry == 5:
                mfe_5[e] = cur_mfe
                mae_5[e] = cur_mae
            if days_from_entry == 10:
                mfe_10[e] = cur_mfe
                mae_10[e] = cur_mae
            if days_from_entry == 20:
                mfe_20[e] = cur_mfe
                mae_20[e] = cur_mae

            # Days to target
            if days_to_1atr[e] < 0 and peak >= ep + atr_val:
                days_to_1atr[e] = days_from_entry
            if days_to_2atr[e] < 0 and peak >= ep + 2.0 * atr_val:
                days_to_2atr[e] = days_from_entry
            if days_to_3atr[e] < 0 and peak >= ep + 3.0 * atr_val:
                days_to_3atr[e] = days_from_entry

        days_to_peak[e] = peak_bar

        # Fill uncached MFE/MAE from final state
        if mfe_5[e] == 0 and peak_bar > 0:
            mfe_5[e] = (peak - ep) / atr_val
        if mfe_10[e] == 0 and peak_bar > 0:
            mfe_10[e] = (peak - ep) / atr_val
        if mfe_20[e] == 0 and peak_bar > 0:
            mfe_20[e] = (peak - ep) / atr_val
        if mae_5[e] == 0 and peak_bar > 0:
            mae_5[e] = (trough - ep) / atr_val
        if mae_10[e] == 0 and peak_bar > 0:
            mae_10[e] = (trough - ep) / atr_val
        if mae_20[e] == 0 and peak_bar > 0:
            mae_20[e] = (trough - ep) / atr_val

        if won:
            outcome[e] = 1
        elif lost:
            outcome[e] = -1
        else:
            outcome[e] = 0  # TIMEOUT

    return (outcome, mfe_5, mfe_10, mfe_20,
            mae_5, mae_10, mae_20,
            days_to_1atr, days_to_2atr, days_to_3atr, days_to_peak)


# ===================================================================
# 5. STRUCTURE QUALITY COMPONENTS
# ===================================================================

@njit(cache=True)
def _structure_quality_numba(level_quality, breakout_quality, retest_precision,
                              retest_hold_quality, volume_quality, trend_quality,
                              bounce_quality, overhead_space):
    """Compute STRUCTURE_QUALITY from 8 component scores."""
    secondary = (volume_quality + trend_quality + bounce_quality + overhead_space) / 4.0
    sq = (0.20 * level_quality +
          0.20 * breakout_quality +
          0.25 * retest_precision +
          0.20 * retest_hold_quality +
          0.15 * secondary)
    return min(max(sq, 0.0), 1.0)


# ===================================================================
# 6. FRESHNESS DECAY
# ===================================================================

@njit(cache=True)
def _freshness_decay_numba(distance_atr, candles_since):
    """Compute distance and time freshness multipliers."""
    if distance_atr <= 0.50:
        dist_fresh = 1.0
    elif distance_atr <= 1.00:
        dist_fresh = 0.90
    elif distance_atr <= 1.50:
        dist_fresh = 0.70
    elif distance_atr <= 2.00:
        dist_fresh = 0.40
    else:
        dist_fresh = 0.0

    if candles_since <= 5:
        time_fresh = 1.0
    elif candles_since <= 10:
        time_fresh = 0.90
    elif candles_since <= 15:
        time_fresh = 0.70
    elif candles_since <= 20:
        time_fresh = 0.50
    else:
        time_fresh = 0.0

    return dist_fresh, time_fresh


# ===================================================================
# 6b. NUMBA VECTORIZED LOOPS (replacing Python for-loops)
# ===================================================================

@njit(cache=True)
def _vol_sma_numba(volume, period=20):
    """Rolling volume SMA using cumsum — replaces Python loop."""
    n = len(volume)
    result = np.zeros(n, dtype=np.float64)
    if n == 0:
        return result
    cumsum = 0.0
    for i in range(n):
        cumsum += volume[i]
        if i >= period:
            cumsum -= volume[i - period]
            result[i] = cumsum / period
        else:
            result[i] = cumsum / (i + 1)
    return result


@njit(cache=True)
def _track_breakout_bars_numba(bk_level, bk_zone_idx, n):
    """Track breakout bars — replaces Python loop."""
    breakout_bar = np.full(n, -1, dtype=np.int64)
    for i in range(n):
        if bk_level[i] > 0 and bk_zone_idx[i] >= 0:
            breakout_bar[i] = i
    return breakout_bar


@njit(cache=True)
def _compute_quality_numba(
    n, rt_valid, atr, bk_zone_idx, bk_dist, bk_body, bk_clv, bk_vol,
    rt_depth, rt_close_rel, rt_wick, volume, ema20, ema50, ema200,
    high, low, close, zone_levels, zone_proms, zone_touches, zone_widths,
    n_zones
):
    """Compute all8 quality scores in one Numba pass."""
    level_q = np.zeros(n, dtype=np.float64)
    breakout_q = np.zeros(n, dtype=np.float64)
    retest_prec = np.zeros(n, dtype=np.float64)
    retest_hold = np.zeros(n, dtype=np.float64)
    volume_q = np.zeros(n, dtype=np.float64)
    trend_q = np.zeros(n, dtype=np.float64)
    bounce_q = np.zeros(n, dtype=np.float64)
    overhead_q = np.zeros(n, dtype=np.float64)

    for i in range(n):
        if rt_valid[i] != 1:
            continue
        cur_atr = atr[i] if atr[i] > 0 else 1e-10

        # Level quality
        z_idx = bk_zone_idx[i] if bk_zone_idx[i] >= 0 else 0
        if z_idx < n_zones:
            touches = zone_touches[z_idx]
            prom = zone_proms[z_idx]
            zone_w = zone_widths[z_idx]
            level_q[i] = min(1.0, (touches / 3.0) * 0.5 +
                             min(prom / (3.0 * cur_atr), 1.0) * 0.3 +
                             max(0.0, 1.0 - zone_w / cur_atr) * 0.2)
        else:
            level_q[i] = 0.5

        # Breakout quality
        bd = bk_dist[i] if bk_dist[i] > 0 else 0.0
        bb = bk_body[i] if bk_body[i] > 0 else 0.0
        bc = bk_clv[i] if bk_clv[i] > 0 else 0.0
        bv = bk_vol[i] if bk_vol[i] > 0 else 1.0
        breakout_q[i] = min(1.0, bd * 0.25 + bb / 0.5 * 0.25 +
                            bc * 0.25 + min(bv / 2.0, 1.0) * 0.25)

        # Retest precision
        precision_raw = abs(-rt_depth[i]) / 0.60
        retest_prec[i] = min(1.0, max(0.0, 1.0 - precision_raw))

        # Retest hold quality
        cr = rt_close_rel[i]
        wick = rt_wick[i]
        retest_hold[i] = min(1.0, max(0.0, min(cr + 0.5, 1.0) * 0.6 + wick * 0.4))

        # Volume quality
        if i > 0:
            start = max(0, i - 20)
            s = 0.0
            cnt = 0
            for j in range(start, i):
                s += volume[j]
                cnt += 1
            avg_vol = s / cnt if cnt > 0 else volume[i]
        else:
            avg_vol = volume[i]
        vol_ratio = volume[i] / avg_vol if avg_vol > 0 else 1.0
        volume_q[i] = min(1.0, vol_ratio / 2.0)

        # Trend quality
        trend_score = 0.0
        if ema20[i] > ema50[i]:
            trend_score += 0.33
        if ema50[i] > ema200[i]:
            trend_score += 0.33
        if ema20[i] > ema200[i]:
            trend_score += 0.34
        trend_q[i] = trend_score

        # Bounce quality
        rng = high[i] - low[i]
        if rng > 0:
            clv = ((close[i] - low[i]) - (high[i] - close[i])) / rng
            bounce_q[i] = min(1.0, max(0.0, (clv + 1.0) / 2.0))
        else:
            bounce_q[i] = 0.5

        # Overhead space
        next_resistance = close[i] * 2.0
        for z in range(n_zones):
            if zone_levels[z] > close[i] and zone_levels[z] < next_resistance:
                next_resistance = zone_levels[z]
        overhead_q[i] = min(1.0, (next_resistance - close[i]) / (3.0 * cur_atr))

    return level_q, breakout_q, retest_prec, retest_hold, volume_q, trend_q, bounce_q, overhead_q


@njit(cache=True)
def _compute_raw_score_numba(n, rt_valid, struct_q, atr, close, level_q,
                              breakout_q, retest_prec, retest_hold,
                              volume_q, trend_q, bounce_q, overhead_q):
    """Compute raw model utility scores in one Numba pass."""
    raw_score = np.zeros(n, dtype=np.float64)
    for i in range(n):
        if rt_valid[i] != 1:
            continue
        cur_atr = atr[i] if atr[i] > 0 else 1e-10
        p_win = struct_q[i] * 0.6 + 0.2
        p_drawdown = (1.0 - struct_q[i]) * 0.4
        conservative_upside = min(max(struct_q[i], 0.0), 1.0)
        drawdown_safety = min(max(1.0 - (1.0 - struct_q[i]) * 0.5, 0.0), 1.0)
        if i >= 5:
            momentum_5d = (close[i] - close[i - 5]) / close[i - 5] if close[i - 5] > 0 else 0.0
        else:
            momentum_5d = 0.0
        speed = min(max(np.exp(-max(0.0, 10.0 - momentum_5d * 100.0) / 12.0), 0.1), 1.0)
        structure_component = 0.75 + 0.25 * struct_q[i]
        drawdown_penalty = np.exp(-4.0 * max(0.0, p_drawdown - 0.25))
        model_utility = (p_win * (1.0 - p_drawdown) *
                         conservative_upside * drawdown_safety *
                         speed * structure_component * drawdown_penalty)
        raw_score[i] = min(max(model_utility * 100.0, 0.0), 100.0)
    return raw_score


@njit(cache=True)
def _apply_freshness_decay_numba(n, rt_valid, rt_level, rt_event, raw_score,
                                  atr, close, RETEST_INVALIDATE_ATR):
    """Apply freshness decay to produce final scores — all in Numba."""
    final_score = np.full(n, np.nan, dtype=np.float64)
    last_retest_bar = -1
    last_retest_level = 0.0
    last_retest_atr = 1.0
    max_events = 10000
    event_seen = np.zeros(max_events, dtype=np.bool_)

    for i in range(n):
        cur_atr = atr[i] if atr[i] > 0 else 1e-10

        if rt_valid[i] == 1:
            evt = rt_event[i]
            if evt >= 0 and evt < max_events and not event_seen[evt]:
                event_seen[evt] = True
                last_retest_bar = i
                last_retest_level = rt_level[i]
                last_retest_atr = cur_atr
                final_score[i] = raw_score[i]
        elif last_retest_bar >= 0:
            candles_since = i - last_retest_bar
            dist_atr = (close[i] - last_retest_level) / last_retest_atr if last_retest_atr > 0 else 0.0

            if close[i] < last_retest_level + RETEST_INVALIDATE_ATR * cur_atr:
                final_score[i] = np.nan
                last_retest_bar = -1
                continue
            if dist_atr > 2.0:
                final_score[i] = np.nan
                continue
            if candles_since > 20:
                final_score[i] = np.nan
                last_retest_bar = -1
                continue

            df, tf = _freshness_decay_numba(max(0.0, dist_atr), candles_since)
            if df > 0.0 and tf > 0.0 and raw_score[i] > 0.0:
                final_score[i] = raw_score[i] * df * tf
            else:
                final_score[i] = np.nan

    return final_score


# ===================================================================
# 7. MAIN SCORING FUNCTION (Per-Symbol, Full History)
# ===================================================================

def compute_retest_score_for_symbol(grp, model=None):
    """Compute OLD_SWING_RETEST_SCORE for a single symbol's full history.
    Optimized: all heavy loops run in Numba.
    """
    if len(grp) < 60:
        return pd.Series(np.nan, index=grp.index)

    grp = grp.sort_values("date").reset_index(drop=True)
    c = grp["close"].astype(float).values
    h = grp["high"].astype(float).values
    lo = grp["low"].astype(float).values
    v = grp["volume"].astype(float).values
    n = len(c)

    atr = _compute_atr_numba(h, lo, c, 14)
    vol_sma = _vol_sma_numba(v, 20)
    ema20 = _ema_numba(c, 20)
    ema50 = _ema_numba(c, 50)
    ema200 = _ema_numba(c, 200)

    swing_idxs, swing_prices = _detect_swing_highs_numba(h, lo, SWING_LEFT, SWING_RIGHT)
    zone_levels, zone_proms, zone_touches, zone_widths, zone_starts = \
        _filter_and_cluster_numba(swing_idxs, swing_prices, h, lo, atr,
                                   SWING_MIN_PROMINENCE_ATR, CLUSTER_DISTANCE_ATR)

    n_zones = len(zone_levels)
    if n_zones == 0:
        return pd.Series(np.nan, index=grp.index)

    bk_level, bk_dist, bk_body, bk_clv, bk_vol, bk_zone_idx = \
        _detect_breakouts_numba(c, h, lo, v, atr, vol_sma, zone_levels, zone_widths, zone_starts)

    breakout_bar = _track_breakout_bars_numba(bk_level, bk_zone_idx, n)

    rt_level, rt_depth, rt_close_rel, rt_wick, rt_valid, rt_event = \
        _detect_retests_numba(c, h, lo, v, atr, bk_level, bk_zone_idx, zone_levels, zone_starts)

    level_q, breakout_q, retest_prec, retest_hold, volume_q, trend_q, bounce_q, overhead_q = \
        _compute_quality_numba(n, rt_valid, atr, bk_zone_idx, bk_dist, bk_body, bk_clv, bk_vol,
                               rt_depth, rt_close_rel, rt_wick, v, ema20, ema50, ema200,
                               h, lo, c, zone_levels, zone_proms, zone_touches, zone_widths, n_zones)

    struct_q = np.zeros(n, dtype=np.float64)
    for i in range(n):
        if rt_valid[i] == 1:
            struct_q[i] = _structure_quality_numba(
                level_q[i], breakout_q[i], retest_prec[i], retest_hold[i],
                volume_q[i], trend_q[i], bounce_q[i], overhead_q[i])

    raw_score = _compute_raw_score_numba(n, rt_valid, struct_q, atr, c,
                                          level_q, breakout_q, retest_prec, retest_hold,
                                          volume_q, trend_q, bounce_q, overhead_q)

    final_score = _apply_freshness_decay_numba(n, rt_valid, rt_level, rt_event,
                                                raw_score, atr, c, RETEST_INVALIDATE_ATR)

    return pd.Series(final_score, index=grp.index)


def compute_retest_score_current(grp, model=None):
    """Compute OLD_SWING_RETEST_SCORE for current mode (last bar only).
    Returns a single float (0-100) or np.nan.
    """
    series = compute_retest_score_for_symbol(grp, model)
    if series is None or len(series) == 0:
        return np.nan
    val = series.iloc[-1]
    return val if not np.isnan(val) else np.nan


# ===================================================================
# HELPER: EMA
# ===================================================================

@njit(cache=True)
def _ema_numba(data, period):
    """Exponential moving average."""
    n = len(data)
    result = np.zeros(n, dtype=np.float64)
    if n == 0:
        return result
    alpha = 2.0 / (period + 1)
    result[0] = data[0]
    for i in range(1, n):
        result[i] = alpha * data[i] + (1.0 - alpha) * result[i - 1]
    return result
