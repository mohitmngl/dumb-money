import os

import numpy as np
import pandas as pd

try:
    from numba import njit, prange
    HAVE_NUMBA = True
except ImportError:
    HAVE_NUMBA = False
    def njit(*a, **kw):
        def decorator(f):
            return f
        return decorator
    prange = range


def supertrend(df, period=14, multiplier=2.0):
    """Exact port of TradingView's ta.supertrend() Pine Script.
    Uses hl2 source, Wilder's ATR, two-band ratcheting with close[1] tests,
    and the prevSuperTrend == prevUpperBand direction convention.

    df must have columns: open, high, low, close.
    Returns DataFrame with: supertrend, trend, signal, stop, atr_value, streak,
    crossed_above, crossed_below, atr_crossed_above, atr_crossed_below.

    Convention: trend=1 → uptrend (ST below price), trend=-1 → downtrend (ST above price).
    """
    h = df["high"].values.astype(np.float64)
    l = df["low"].values.astype(np.float64)
    c = df["close"].values.astype(np.float64)
    n = len(c)
    if n < 2:
        return pd.DataFrame({
            "supertrend": np.nan, "trend": 0, "signal": 0, "stop": np.nan,
            "atr_value": np.nan, "streak": 0, "crossed_above": 0, "crossed_below": 0,
            "atr_crossed_above": 0, "atr_crossed_below": 0
        }, index=df.index)

    st_arr, direction, signal, crossed_above, crossed_below, atr, streak_arr = \
        _supertrend_numba(h, l, c, period, multiplier)

    return pd.DataFrame({
        "supertrend": st_arr, "trend": direction, "signal": signal, "stop": st_arr,
        "atr_value": atr, "streak": streak_arr,
        "crossed_above": crossed_above, "crossed_below": crossed_below,
        "atr_crossed_above": crossed_above, "atr_crossed_below": crossed_below
    }, index=df.index)


@njit(cache=True)
def _supertrend_numba(h, l, c, period, multiplier):
    n = len(c)
    hl2 = (h + l) / 2.0

    c_prev = np.empty(n, dtype=np.float64)
    c_prev[0] = c[0]
    c_prev[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - c_prev), np.abs(l - c_prev)))

    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    st_arr = np.full(n, np.nan)
    direction = np.zeros(n, dtype=np.int8)

    for i in range(n):
        if np.isnan(atr[i]):
            direction[i] = -1
            st_arr[i] = np.nan
            continue

        if i == 0:
            prev_lower = 0.0
            prev_upper = 0.0
        else:
            prev_lower = final_lower[i - 1] if not np.isnan(final_lower[i - 1]) else 0.0
            prev_upper = final_upper[i - 1] if not np.isnan(final_upper[i - 1]) else 0.0

        if basic_lower[i] > prev_lower or c_prev[i] < prev_lower:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = prev_lower

        if basic_upper[i] < prev_upper or c_prev[i] > prev_upper:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = prev_upper

        prev_st = st_arr[i - 1] if i > 0 else np.nan
        prev_upper_val = final_upper[i - 1] if i > 0 and not np.isnan(final_upper[i - 1]) else np.nan

        if not np.isnan(prev_st) and prev_st == prev_upper_val:
            direction[i] = 1 if c[i] > final_upper[i] else -1
        elif not np.isnan(prev_st):
            direction[i] = -1 if c[i] < final_lower[i] else 1
        else:
            direction[i] = -1

        st_arr[i] = final_lower[i] if direction[i] == 1 else final_upper[i]

    signal = np.zeros(n, dtype=np.int8)
    crossed_above = np.zeros(n, dtype=np.int8)
    crossed_below = np.zeros(n, dtype=np.int8)
    for i in range(1, n):
        if direction[i] != 0 and direction[i - 1] != 0:
            if direction[i] == 1 and direction[i - 1] == -1:
                signal[i] = 1
                crossed_above[i] = 1
            elif direction[i] == -1 and direction[i - 1] == 1:
                signal[i] = -1
                crossed_below[i] = 1

    streak_arr = np.zeros(n, dtype=np.int32)
    for i in range(n):
        if direction[i] == 0:
            streak_arr[i] = 0
        elif i == 0 or direction[i] != direction[i - 1]:
            streak_arr[i] = 1 if direction[i] == 1 else -1
        else:
            streak_arr[i] = streak_arr[i - 1] + (1 if direction[i] == 1 else -1)

    return st_arr, direction, signal, crossed_above, crossed_below, atr, streak_arr


def atr_trailing_stop(df, period=14, multiplier=2.0):
    """ATR Trailing Stop formula (from TradingView docs).
    
    Uses recursive trailing stop based on ATR, not HL2 bands.
    Simpler than SuperTrend - no upper/lower band ratcheting.
    
    df must have columns: open, high, low, close.
    Returns DataFrame with: supertrend, trend, signal, stop, atr_value, streak,
    crossed_above, crossed_below, atr_crossed_above, atr_crossed_below.
    
    Convention: trend=1 → uptrend (stop below price), trend=-1 → downtrend (stop above price).
    """
    h = df["high"].values.astype(np.float64)
    l = df["low"].values.astype(np.float64)
    c = df["close"].values.astype(np.float64)
    n = len(c)
    if n < 2:
        return pd.DataFrame({
            "supertrend": np.nan, "trend": 0, "signal": 0, "stop": np.nan,
            "atr_value": np.nan, "streak": 0, "crossed_above": 0, "crossed_below": 0,
            "atr_crossed_above": 0, "atr_crossed_below": 0
        }, index=df.index)

    st_arr, direction, signal, crossed_above, crossed_below, atr, streak_arr = \
        _atr_trailing_stop_numba(h, l, c, period, multiplier)

    return pd.DataFrame({
        "supertrend": st_arr, "trend": direction, "signal": signal, "stop": st_arr,
        "atr_value": atr, "streak": streak_arr,
        "crossed_above": crossed_above, "crossed_below": crossed_below,
        "atr_crossed_above": crossed_above, "atr_crossed_below": crossed_below
    }, index=df.index)


@njit(cache=True)
def _atr_trailing_stop_numba(h, l, c, period, multiplier):
    """ATR Trailing Stop core logic.
    
    ATR Wilder RMA: ATR[P-1]=mean(TR[0:P]); ATR[i]=((P-1)*ATR[i-1]+TR[i])/P
    Loss[i] = M * ATR[i]
    
    If close > prev_stop AND prev_close > prev_stop: stop = max(prev_stop, close - Loss)
    If close < prev_stop AND prev_close < prev_stop: stop = min(prev_stop, close + Loss)
    If cross: stop = close - Loss (bullish) or close + Loss (bearish)
    """
    n = len(c)
    
    # True Range
    c_prev = np.empty(n, dtype=np.float64)
    c_prev[0] = c[0]
    c_prev[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - c_prev), np.abs(l - c_prev)))
    
    # ATR Wilder RMA
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    
    # Trailing stop computation
    st_arr = np.full(n, np.nan)
    direction = np.zeros(n, dtype=np.int8)
    
    for i in range(n):
        if np.isnan(atr[i]):
            direction[i] = -1
            st_arr[i] = np.nan
            continue
        
        loss = multiplier * atr[i]
        prev_stop = st_arr[i - 1] if i > 0 else np.nan
        prev_close = c[i - 1] if i > 0 else c[i]
        
        if np.isnan(prev_stop):
            # First valid bar - initialize
            direction[i] = -1
            st_arr[i] = c[i] + loss
        elif c[i] > prev_stop and prev_close > prev_stop:
            # Bullish continuation - stop moves up
            new_stop = c[i] - loss
            st_arr[i] = max(prev_stop, new_stop)
            direction[i] = 1
        elif c[i] < prev_stop and prev_close < prev_stop:
            # Bearish continuation - stop moves down
            new_stop = c[i] + loss
            st_arr[i] = min(prev_stop, new_stop)
            direction[i] = -1
        elif c[i] > prev_stop and prev_close <= prev_stop:
            # Cross up - new bullish stop
            direction[i] = 1
            st_arr[i] = c[i] - loss
        elif c[i] < prev_stop and prev_close >= prev_stop:
            # Cross down - new bearish stop
            direction[i] = -1
            st_arr[i] = c[i] + loss
        else:
            # Should not happen, but default to previous
            direction[i] = direction[i - 1] if i > 0 else -1
            st_arr[i] = prev_stop
    
    # Signal and crossover detection
    signal = np.zeros(n, dtype=np.int8)
    crossed_above = np.zeros(n, dtype=np.int8)
    crossed_below = np.zeros(n, dtype=np.int8)
    for i in range(1, n):
        if direction[i] == 1 and direction[i - 1] == -1:
            signal[i] = 1
            crossed_above[i] = 1
        elif direction[i] == -1 and direction[i - 1] == 1:
            signal[i] = -1
            crossed_below[i] = 1
    
    # Streak computation
    streak_arr = np.zeros(n, dtype=np.int32)
    for i in range(n):
        if direction[i] == 0:
            streak_arr[i] = 0
        elif i == 0 or direction[i] != direction[i - 1]:
            streak_arr[i] = 1 if direction[i] == 1 else -1
        else:
            streak_arr[i] = streak_arr[i - 1] + (1 if direction[i] == 1 else -1)
    
    return st_arr, direction, signal, crossed_above, crossed_below, atr, streak_arr


def build_anchored_blocks(dates, opens, highs, lows, closes, eval_idx, sessions):
    """Build non-overlapping synthetic candles anchored backwards from eval_idx.

    For each evaluation date, divide history backwards into consecutive blocks
    of exactly `sessions` daily bars. Each block becomes one synthetic candle:
        Open  = first session's Open
        High  = max(High) in block
        Low   = min(Low) in block
        Close = last session's Close

    Returns list of (date, open, high, low, close) in chronological order.
    """
    n = eval_idx + 1
    blocks = []
    pos = n
    while pos >= sessions:
        start = pos - sessions
        block_date = dates[pos - 1]
        block_open = opens[start]
        block_high = float(np.max(highs[start:pos]))
        block_low = float(np.min(lows[start:pos]))
        block_close = closes[pos - 1]
        blocks.append((block_date, block_open, block_high, block_low, block_close))
        pos = start
    blocks.reverse()
    return blocks


def compute_rolling_atr_trailing_stop(dates, opens, highs, lows, closes,
                                       eval_idx, sessions, period=14, multiplier=2.0):
    """Compute ATR Trailing Stop on anchored rolling synthetic candles.

    For a given evaluation date, builds anchored non-overlapping blocks of
    `sessions` daily bars, runs ATR Trailing Stop on the synthetic candle
    series, and returns the final (last synthetic candle) result.

    Returns dict with: trend, stop, atr_value, streak, crossed_above, crossed_below,
                       bars_below, bars_above, n_candles
    """
    blocks = build_anchored_blocks(dates, opens, highs, lows, closes, eval_idx, sessions)
    n_blocks = len(blocks)
    result = {
        'trend': 0, 'stop': 0.0, 'atr_value': 0.0, 'streak': 0,
        'crossed_above': 0, 'crossed_below': 0,
        'bars_below': 0, 'bars_above': 0, 'n_candles': n_blocks
    }
    if n_blocks < 3:
        return result

    bl_opens = np.array([b[1] for b in blocks], dtype=np.float64)
    bl_highs = np.array([b[2] for b in blocks], dtype=np.float64)
    bl_lows = np.array([b[3] for b in blocks], dtype=np.float64)
    bl_closes = np.array([b[4] for b in blocks], dtype=np.float64)

    bl_dates = [b[0] for b in blocks]
    bl_df = pd.DataFrame({
        'date': bl_dates, 'open': bl_opens, 'high': bl_highs,
        'low': bl_lows, 'close': bl_closes
    })

    st = atr_trailing_stop(bl_df, period=period, multiplier=multiplier)
    if len(st) == 0:
        return result

    last = st.iloc[-1]
    prev = st.iloc[-2] if len(st) >= 2 else last

    result['trend'] = int(last['trend'])
    result['stop'] = float(last['stop']) if pd.notna(last['stop']) else 0.0
    result['atr_value'] = float(last['atr_value']) if pd.notna(last['atr_value']) else 0.0
    result['streak'] = int(last['streak'])

    # Cross detection from last 2 synthetic candle trends
    if last['trend'] == 1 and prev['trend'] == -1:
        result['crossed_above'] = 1
    elif last['trend'] == -1 and prev['trend'] == 1:
        result['crossed_below'] = 1

    # Bars at side from the full trend series
    trend_arr = st['trend'].fillna(0).astype(int).values
    bas = bars_at_side(trend_arr)
    bas_last = int(bas[-1]) if len(bas) > 0 else 0
    result['bars_below'] = bas_last if result['trend'] == 1 else 0
    result['bars_above'] = bas_last if result['trend'] == -1 else 0

    return result


if HAVE_NUMBA:
    @njit(cache=True)
    def _rolling_atr_incremental_numba(highs, lows, closes, sessions, period,
                                       multiplier, min_idx, trends, stops, atrs,
                                       streaks, cross_above, cross_below,
                                       bars_bl, bars_ab):
        """O(n) equivalent of the per-date anchored-block rebuild.

        Block anchors depend only on eval_idx mod sessions, so one sequential
        pass per residue class reproduces every per-eval call's block prefix
        exactly -> bitwise-identical outputs (same recursion, same order)."""
        n = closes.shape[0]

        bh = np.full(n, np.nan)
        bl = np.full(n, np.nan)
        bc = np.full(n, np.nan)
        for i in range(sessions - 1, n):
            max_h = highs[i - sessions + 1]
            min_l = lows[i - sessions + 1]
            for j in range(i - sessions + 2, i + 1):
                if highs[j] > max_h:
                    max_h = highs[j]
                if lows[j] < min_l:
                    min_l = lows[j]
            bh[i] = max_h
            bl[i] = min_l
            bc[i] = closes[i]

        for r in range(sessions):
            m = r
            while m < sessions - 1:
                m += sessions
            if m >= n:
                continue

            # trailing-stop recursion state (mirrors _atr_trailing_stop_numba)
            prev_st = np.nan
            prev_dir = np.int8(0)
            prev_c = np.nan
            streak = np.int32(0)
            # ATR: seed = mean of first `period` TRs, then Wilder RMA
            tr_sum = 0.0
            tr_seen = 0
            atr_val = np.nan
            # bars_at_side second-pass state
            bas_run = 0
            bas_prev_s = np.int8(0)
            bas_last_cc = 0
            kk = 0

            while m < n:
                h_b = bh[m]
                l_b = bl[m]
                c_b = bc[m]
                pc = c_b if kk == 0 else prev_c
                tr = max(h_b - l_b, max(abs(h_b - pc), abs(l_b - pc)))
                if tr_seen < period:
                    tr_sum += tr
                    tr_seen += 1
                    if tr_seen == period:
                        atr_val = tr_sum / period
                else:
                    atr_val = (atr_val * (period - 1) + tr) / period

                if np.isnan(atr_val):
                    d = np.int8(-1)
                    st = np.nan
                else:
                    loss = multiplier * atr_val
                    if np.isnan(prev_st):
                        d = np.int8(-1)
                        st = c_b + loss
                    elif c_b > prev_st and pc > prev_st:
                        d = np.int8(1)
                        st = max(prev_st, c_b - loss)
                    elif c_b < prev_st and pc < prev_st:
                        d = np.int8(-1)
                        st = min(prev_st, c_b + loss)
                    elif c_b > prev_st and pc <= prev_st:
                        d = np.int8(1)
                        st = c_b - loss
                    elif c_b < prev_st and pc >= prev_st:
                        d = np.int8(-1)
                        st = c_b + loss
                    else:
                        d = prev_dir if kk > 0 else np.int8(-1)
                        st = prev_st

                if d == 0:
                    streak = np.int32(0)
                elif kk == 0 or d != prev_dir:
                    streak = np.int32(1) if d == 1 else np.int32(-1)
                else:
                    streak = streak + (np.int32(1) if d == 1 else np.int32(-1))

                if d == 0:
                    bas_run = 0
                    bas_prev_s = np.int8(0)
                    bas_last_cc = 0
                    bas = 0
                elif d == bas_prev_s:
                    bas_run += 1
                    bas = bas_last_cc
                else:
                    bas_last_cc = bas_run if bas_run > 0 and bas_prev_s != 0 else 0
                    bas = bas_last_cc
                    bas_run = 1
                    bas_prev_s = d

                xa = 1 if (d == 1 and prev_dir == -1) else 0
                xb = 1 if (d == -1 and prev_dir == 1) else 0

                kk += 1
                if m >= min_idx and kk >= 3:
                    trends[m] = d
                    stops[m] = 0.0 if np.isnan(st) else st
                    atrs[m] = 0.0 if np.isnan(atr_val) else atr_val
                    streaks[m] = streak
                    cross_above[m] = xa
                    cross_below[m] = xb
                    bars_bl[m] = bas if d == 1 else 0
                    bars_ab[m] = bas if d == -1 else 0

                prev_st = st
                prev_dir = d
                prev_c = c_b
                m += sessions


def compute_rolling_atr_batch(dates, opens, highs, lows, closes, sessions,
                               period=14, multiplier=2.0):
    """Compute rolling ATR Trailing Stop for ALL dates in one symbol.

    Default impl is an O(n) incremental kernel (ROLLING_ATR_IMPL=legacy
    restores the original per-date anchored rebuild)."""
    n = len(dates)
    trends = np.zeros(n, dtype=np.int32)
    stops = np.zeros(n, dtype=np.float64)
    atrs = np.zeros(n, dtype=np.float64)
    streaks = np.zeros(n, dtype=np.int32)
    cross_above = np.zeros(n, dtype=np.int32)
    cross_below = np.zeros(n, dtype=np.int32)
    bars_bl = np.zeros(n, dtype=np.int32)
    bars_ab = np.zeros(n, dtype=np.int32)

    if n < sessions + 1:
        return trends, stops, atrs, streaks, cross_above, cross_below, bars_bl, bars_ab

    min_idx = max(period + 1, sessions) - 1

    if HAVE_NUMBA and os.environ.get("ROLLING_ATR_IMPL", "fast") != "legacy":
        _rolling_atr_incremental_numba(
            np.asarray(highs, dtype=np.float64),
            np.asarray(lows, dtype=np.float64),
            np.asarray(closes, dtype=np.float64),
            sessions, period, multiplier, min_idx,
            trends, stops, atrs, streaks, cross_above, cross_below, bars_bl, bars_ab)
        return trends, stops, atrs, streaks, cross_above, cross_below, bars_bl, bars_ab

    return _compute_rolling_atr_batch_legacy(dates, opens, highs, lows, closes,
                                             sessions, period, multiplier)


def _compute_rolling_atr_batch_legacy(dates, opens, highs, lows, closes, sessions,
                               period=14, multiplier=2.0):
    """Compute rolling ATR Trailing Stop for ALL dates in one symbol.

    Precomputes block aggregations with sliding window, then runs ATR
    per date using Numba. Much faster than rebuilding blocks each time.
    """
    n = len(dates)
    trends = np.zeros(n, dtype=np.int32)
    stops = np.zeros(n, dtype=np.float64)
    atrs = np.zeros(n, dtype=np.float64)
    streaks = np.zeros(n, dtype=np.int32)
    cross_above = np.zeros(n, dtype=np.int32)
    cross_below = np.zeros(n, dtype=np.int32)
    bars_bl = np.zeros(n, dtype=np.int32)
    bars_ab = np.zeros(n, dtype=np.int32)

    if n < sessions + 1:
        return trends, stops, atrs, streaks, cross_above, cross_below, bars_bl, bars_ab

    min_idx = max(period + 1, sessions) - 1

    # Precompute block aggregations using sliding window (O(n) total)
    bh = np.full(n, np.nan)
    bl = np.full(n, np.nan)
    bc = np.full(n, np.nan)
    for i in range(sessions - 1, n):
        start = i - sessions + 1
        max_h = highs[start]
        min_l = lows[start]
        for j in range(start + 1, i + 1):
            if highs[j] > max_h:
                max_h = highs[j]
            if lows[j] < min_l:
                min_l = lows[j]
        bh[i] = max_h
        bl[i] = min_l
        bc[i] = closes[i]

    # For each date, extract anchored blocks and run ATR
    for eval_idx in range(min_idx, n):
        n_blocks = 0
        pos = eval_idx + 1
        while pos >= sessions:
            n_blocks += 1
            pos -= sessions

        if n_blocks < 3:
            continue

        block_h = np.empty(n_blocks, dtype=np.float64)
        block_l = np.empty(n_blocks, dtype=np.float64)
        block_c = np.empty(n_blocks, dtype=np.float64)
        idx = 0
        pos = eval_idx + 1
        while pos >= sessions:
            block_end = pos - 1
            block_h[idx] = bh[block_end]
            block_l[idx] = bl[block_end]
            block_c[idx] = bc[block_end]
            idx += 1
            pos -= sessions

        # Reverse to chronological
        for i in range(n_blocks // 2):
            j = n_blocks - 1 - i
            block_h[i], block_h[j] = block_h[j], block_h[i]
            block_l[i], block_l[j] = block_l[j], block_l[i]
            block_c[i], block_c[j] = block_c[j], block_c[i]

        st_arr, direction, signal, xa, xb, atr_arr, sk = \
            _atr_trailing_stop_numba(block_h, block_l, block_c, period, multiplier)

        trends[eval_idx] = int(direction[-1])
        stops[eval_idx] = float(st_arr[-1]) if not np.isnan(st_arr[-1]) else 0.0
        atrs[eval_idx] = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else 0.0
        streaks[eval_idx] = int(sk[-1])
        # Cross from last 2 trends
        if len(direction) >= 2:
            if direction[-1] == 1 and direction[-2] == -1:
                cross_above[eval_idx] = 1
            elif direction[-1] == -1 and direction[-2] == 1:
                cross_below[eval_idx] = 1
        # Bars at side
        bas = bars_at_side(direction)
        bars_bl[eval_idx] = int(bas[-1]) if trends[eval_idx] == 1 else 0
        bars_ab[eval_idx] = int(bas[-1]) if trends[eval_idx] == -1 else 0

    return trends, stops, atrs, streaks, cross_above, cross_below, bars_bl, bars_ab


def r_squared(close, window=90):
    """Rolling R² of a linear regression of log(close) vs bar index.

    1.0 = price tracks a perfectly straight line on a log chart (classic
    'straight uptrend'). Value is signed by slope direction: +R² for
    uptrends, -R² for downtrends, so sorting descending surfaces the
    straightest UPtrending charts first.
    O(n) via rolling sums; no per-window regression loops.
    """
    c = np.asarray(close, dtype=float)
    n = len(c)
    if n < 3:
        return pd.Series(np.zeros(n), index=close.index if hasattr(close, "index") else None)

    y = np.log(np.maximum(c, 1e-12))
    t = np.arange(n, dtype=float)

    s1 = pd.Series(y).rolling(window, min_periods=window).sum().values
    syy = pd.Series(y * y).rolling(window, min_periods=window).sum().values
    sxy_abs = pd.Series(t * y).rolling(window, min_periods=window).sum().values

    k0 = t - (window - 1)                     # first index inside each window
    k0[k0 < 0] = 0
    sxy = sxy_abs - k0 * s1                   # Σ(i·y) with i = 0..w-1 per window

    sx = window * (window - 1) / 2.0
    sxx = window * (window - 1) * (2 * window - 1) / 6.0

    with np.errstate(divide="ignore", invalid="ignore"):
        num = window * sxy - sx * s1
        den = (window * sxx - sx * sx) * (window * syy - s1 * s1)
        r2 = (num * num) / den
        slope = num / (window * sxx - sx * sx)
        r2 = np.where(den > 0, r2, 0.0)

    signed = np.where(slope < 0, -r2, r2)
    signed = np.nan_to_num(signed, nan=0.0, posinf=0.0, neginf=0.0)
    out = pd.Series(signed, index=close.index if hasattr(close, "index") else None)
    return out.fillna(0.0)


def weighted_alpha(df, lookback=252):
    """Weighted Alpha per Barchart definition: measures how much a stock has risen
    or fallen over a one-year period, with more weight on recent activity.

    Formula: 4-bar SMA smoothing, 250 smoothed returns clipped to -6%/+5%,
    linear weights 0.5->1.0, scale 100/0.75.
    For stocks with <250 bars, uses shorter lookback proportional to available data.
    """
    close = df["close"].astype(float).ffill().fillna(0).values
    n = len(close)
    if n < 2:
        return pd.Series(np.zeros(n), index=df.index)

    result = np.zeros(n)
    try:
        lb = 250
        smooth = 4
        if n >= smooth + 2:
            sma = np.convolve(close, np.ones(smooth) / smooth, mode="valid")
            if len(sma) >= 2:
                rets = sma[1:] / sma[:-1] - 1.0
                effective_lb = min(lb, len(rets))
                if effective_lb >= 2:
                    rets = rets[-effective_lb:]
                    clipped = np.clip(rets, -0.06, 0.05)
                    w = np.linspace(0.5, 1.0, effective_lb)
                    wn = w / w.mean()
                    result[-1] = float(np.dot(wn, clipped)) * (100.0 / 0.75)
    except Exception:
        pass

    return pd.Series(result, index=df.index)


def accel(df):
    """Accel indicator: a = SMA28*SMA14/(SMA7^2), base = (c+27*SMA27)*(c+13*SMA13)/(8*(c+6*SMA6)^2).
    Signal: a > base => bullish (+1), else bearish (-1)."""
    c = df["close"].astype(float)
    sma7 = c.rolling(7, min_periods=1).mean()
    sma14 = c.rolling(14, min_periods=1).mean()
    sma27 = c.rolling(27, min_periods=1).mean()
    sma28 = c.rolling(28, min_periods=1).mean()
    sma6 = c.rolling(6, min_periods=1).mean()
    sma13 = c.rolling(13, min_periods=1).mean()

    a = sma28 * sma14 / (sma7 ** 2)
    base = (c + 27 * sma27) * (c + 13 * sma13) / (8 * (c + 6 * sma6) ** 2)

    sig = np.where(a > base, 1, -1)
    prev = pd.Series(sig).shift(1).fillna(0).values

    crossed_up = ((sig == 1) & (prev == -1)).astype(int)
    crossed_down = ((sig == -1) & (prev == 1)).astype(int)

    accel_streak = _streak_numba(sig.astype(np.int32))

    return pd.DataFrame({
        "accel_a": a.round(6), "accel_base": base.round(6),
        "accel_signal": sig,
        "accel_crossed_up": crossed_up, "accel_crossed_down": crossed_down,
        "accel_streak": accel_streak
    }, index=df.index)


def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def rsi_wilder(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50.0)


def prob_up(close_series, horizon=1):
    """Trailing % of completed periods where close rose over `horizon` bars."""
    c = close_series.astype(float)
    cond = (c.pct_change(horizon) > 0).astype(float)
    return cond.rolling(60, min_periods=5).mean() * 100


def prob_up_after_st_cross_up(st_crossed_up, next_day_return):
    """Expanding-window P(next day up | ST 14d/1x crossed up).
    st_crossed_up: int array (1 when ST crossed from bearish to bullish)
    next_day_return: float array (realized next-day pct return, NaN at last bar)
    Returns float array 0-100, default 50 when no crosses yet."""
    cross = st_crossed_up.astype(int)
    n = len(cross)
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    cum_cross = np.cumsum(cross)
    next_up = np.where(np.isfinite(next_day_return), (next_day_return > 0).astype(float), np.nan)
    next_up_cross = np.where(cross == 1, next_up, 0.0)
    cum_next_up = np.cumsum(next_up_cross)
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(cum_cross > 0, cum_next_up / cum_cross * 100, 50.0)
    return result


def next_day_return(close_series):
    """Realized (next_close - close)/close*100 for each bar."""
    c = close_series.astype(float)
    return ((c.shift(-1) - c) / c * 100).fillna(0.0)


def streak_vectorized(close_series):
    """Consecutive up/down days: +N for N up days, -N for N down days."""
    if isinstance(close_series, np.ndarray):
        close_series = pd.Series(close_series)
    c = close_series.astype(float)
    diff = c.diff()
    sign = np.sign(diff.values)
    sign = np.nan_to_num(sign, nan=0.0).astype(np.int32)
    return _streak_numba(sign)


@njit(cache=True)
def _streak_numba(sign):
    n = len(sign)
    result = np.zeros(n, dtype=np.int32)
    for i in range(1, n):
        if sign[i] == 0:
            result[i] = 0
        elif sign[i] == sign[i - 1]:
            result[i] = result[i - 1] + sign[i]
        else:
            result[i] = sign[i]
    return result


@njit(cache=True)
def _bars_at_side_numba(signal):
    """For each position, count how many consecutive bars the signal was at the
    opposite side before the current state began.

    When signal=1 (up), output = count of preceding consecutive -1 bars.
    When signal=-1 (down), output = count of preceding consecutive 1 bars.
    When signal=0, output = 0.
    """
    n = len(signal)
    result = np.zeros(n, dtype=np.int32)
    run_len = 0
    for i in range(n):
        s = signal[i]
        if s == 1:
            result[i] = run_len if run_len > 0 else 0
            run_len = 0
        elif s == -1:
            result[i] = run_len if run_len > 0 else 0
            run_len = 0
        else:
            run_len = 0
            result[i] = 0
        # Track runs of the current state for next transition
        if i > 0:
            if signal[i] == signal[i - 1]:
                pass  # run continues (handled by run_len tracking below)
    # Second pass: track run lengths, persist count through continuation bars
    run_len = 0
    prev_s = 0
    last_cross_count = 0
    for i in range(n):
        s = signal[i]
        if s == 0:
            run_len = 0
            prev_s = 0
            last_cross_count = 0
            result[i] = 0
        elif s == prev_s:
            run_len += 1
            result[i] = last_cross_count
        else:
            # State changed: the previous run length becomes the bars_at_side
            last_cross_count = run_len if run_len > 0 and prev_s != 0 else 0
            result[i] = last_cross_count
            run_len = 1
            prev_s = s
    return result


if HAVE_NUMBA:
    @njit(cache=True, fastmath=True, parallel=True)
    def _bars_at_side_numba_2d(signals):
        """Vectorized bars_at_side for 2D array (n_rows, n_cols)."""
        n_rows, n_cols = signals.shape
        result = np.zeros((n_rows, n_cols), dtype=np.int32)
        for i in prange(n_rows):
            result[i] = _bars_at_side_numba(signals[i])
        return result


def bars_at_side(signal):
    """Wrapper: compute st_bars_below/above or accel_bars_below/above.

    For crossed_up (signal transitions from -1 to 1): returns how many bars it was below.
    For crossed_down (signal transitions from 1 to -1): returns how many bars it was above.
    Otherwise returns 0.
    Accepts 1D or 2D array. For 2D, processes all rows in parallel via numba prange.
    """
    sig = np.asarray(signal, dtype=np.int32)
    if sig.ndim == 1:
        return _bars_at_side_numba(sig)
    if sig.ndim == 2:
        if HAVE_NUMBA:
            return _bars_at_side_numba_2d(sig)
        out = np.empty_like(sig)
        for i in range(sig.shape[0]):
            out[i] = _bars_at_side_numba(sig[i])
        return out
    raise ValueError(f"bars_at_side expected 1D or 2D array, got {sig.ndim}D")


def atrp(high, low, close, period=20):
    """ATRP = mean over last period bars of (high-low)/close*100."""
    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    daily = (h - l) / c * 100
    return daily.rolling(period, min_periods=1).mean().fillna(0.0)


def compute_confluence(row):
    """Confluence score 0-100: weighted blend of SuperTrend up, Accel up, WA percentile, etc."""
    score = 0.0
    if row.get("atr_signal", 0) == 1:
        score += 25
    elif row.get("atr_signal", 0) == -1:
        score -= 10
    if row.get("accel_signal", 0) == 1:
        score += 25
    elif row.get("accel_signal", 0) == -1:
        score -= 10
    wa = row.get("weighted_alpha", 0)
    if wa > 50:
        score += 25
    elif wa > 20:
        score += 15
    elif wa > 0:
        score += 5
    else:
        score -= 5
    streak = row.get("streak", 0)
    if streak >= 3:
        score += 15
    elif streak >= 1:
        score += 5
    prob = row.get("prob_up_1d", 50)
    if prob > 60:
        score += 10
    elif prob > 55:
        score += 5
    return max(0, min(100, score))


def compute_confluence_vectorized(atr_signal, accel_signal, weighted_alpha, streak, prob_up_1d):
    """Vectorized confluence computation for arrays. Returns score 0-100."""
    score = np.zeros(len(atr_signal), dtype=float)
    # SuperTrend
    score = np.where(atr_signal == 1, score + 25, score)
    score = np.where(atr_signal == -1, score - 10, score)
    # Accel
    score = np.where(accel_signal == 1, score + 25, score)
    score = np.where(accel_signal == -1, score - 10, score)
    # Weighted Alpha
    score = np.where(weighted_alpha > 50, score + 25, score)
    score = np.where((weighted_alpha > 20) & (weighted_alpha <= 50), score + 15, score)
    score = np.where((weighted_alpha > 0) & (weighted_alpha <= 20), score + 5, score)
    score = np.where(weighted_alpha <= 0, score - 5, score)
    # Streak
    score = np.where(streak >= 3, score + 15, score)
    score = np.where((streak >= 1) & (streak < 3), score + 5, score)
    # Probability
    score = np.where(prob_up_1d > 60, score + 10, score)
    score = np.where((prob_up_1d > 55) & (prob_up_1d <= 60), score + 5, score)
    return np.clip(score, 0, 100)


def _sigmoid_map(raw, steepness=5.0):
    """Map raw signal in [-1, 1] to [0, 100] via sigmoid.
    raw=0 → 50, raw=1 → ~98, raw=-1 → ~2, raw=0.5 → ~82."""
    return 100.0 / (1.0 + np.exp(-steepness * raw))


def _compute_ai_matrix_score(
    st_signal, st_crossed, accel_signal, accel_crossed_up, accel_crossed_down,
    streak, weighted_alpha, atrp, prob_up_1d, rsi,
    sma20=0.0, sma50=0.0,
    volume_ratio_5_20=1.0, volume_spike=False,
    price=0.0, price_high_20d=0.0, price_low_20d=0.0,
):
    """Sigmoid-based AI Matrix Score: single 0-100 directional prediction.

    S = 100 * sigmoid(z)
    z = 1.20*D + 0.40*X + 0.35*V + 0.25*B + 0.30*P + 0.15*MA + 0.10*R
    """
    _e = np.exp

    def _sig(x):
        x = max(-500.0, min(500.0, x))
        return 1.0 / (1.0 + _e(-x))

    def _logit(p):
        p = max(1e-6, min(1.0 - 1e-6, p))
        return np.log(p / (1.0 - p))

    # D — Directional: trend + momentum + RSI oscillator
    wa_norm = np.tanh(weighted_alpha / 15.0)
    streak_amp = 1.0 + 0.3 * np.tanh(streak / 3.0)
    wa_component = wa_norm * streak_amp
    trend_component = (st_signal + accel_signal) * 0.5
    rsi_component = (rsi - 50.0) / 20.0
    D = (wa_component + trend_component + rsi_component) / 3.0

    # X — Crossover freshness
    raw_cross = st_signal + accel_signal
    boost = 1.0 + 0.5 * float(st_crossed or accel_crossed_up or accel_crossed_down)
    X = raw_cross * 0.5 * boost

    # V — Volume confirmation
    log_ratio = np.log(max(volume_ratio_5_20, 0.01))
    spike_impulse = 0.3 * float(volume_spike)
    V = np.tanh((log_ratio + spike_impulse) * 2.0)

    # B — Oversold bounce
    oversold = _sig((50.0 - rsi) / 10.0)
    vol_confirm = _sig((atrp - 3.0) / 1.5)
    B = oversold * vol_confirm * 2.0 - 1.0

    # P — Probability log-odds
    P = _logit(prob_up_1d / 100.0)

    # Weighted sum
    z = 1.20 * D + 0.40 * X + 0.35 * V + 0.25 * B + 0.30 * P

    # Optional: MA trend bias
    if sma20 > 0 and sma50 > 0:
        z += 0.15 * np.tanh((sma20 - sma50) / (0.05 * sma50 + 1e-9))

    # Optional: price position reinforcement
    if price_high_20d > price_low_20d and price > 0:
        pos = (price - price_low_20d) / (price_high_20d - price_low_20d)
        range_hint = 0.10 * (pos - 0.5) * 2.0
        if (weighted_alpha > 0 and pos > 0.5) or (weighted_alpha < 0 and pos < 0.5):
            z += range_hint
        else:
            z -= range_hint * 0.5

    return round(100.0 * _sig(z), 2)


def ai_score_latest(bars_df, precomputed=None):
    """Local vectorized AI scorer on the latest window of bars.
    Returns dict with overall_score, bias, tech_score, momentum_score, volume_score,
    events_score, volume_profile_score, trendline_score, sentiment_score,
    ai_matrix, conclusion.
    
    precomputed: optional dict with pre-computed indicators to avoid redundant computation:
        st_result, ac_result, wa_val, streak_val, prob_1d_val
    """
    if len(bars_df) < 30:
        return {
            "overall_score": 0, "bias": "neutral", "tech_score": 0, "momentum_score": 0,
            "volume_score": 0, "events_score": 0, "volume_profile_score": 0,
            "trendline_score": 0, "sentiment_score": 0, "ai_matrix": 0.0,
            "conclusion": "HOLD"
        }

    window = bars_df.tail(60).copy()
    c = window["close"].astype(float)
    o = window["open"].astype(float)
    h = window["high"].astype(float)
    l = window["low"].astype(float)
    v = window["volume"].astype(float).fillna(1)

    price = c.iloc[-1]

    # ── Tech score: trend alignment + RSI position ──
    rsi_val = rsi_wilder(c, 14).iloc[-1]
    sma20 = c.rolling(20).mean().iloc[-1]
    sma50 = c.rolling(50).mean().iloc[-1] if len(c) >= 50 else sma20

    # Raw signal: price-vs-SMA alignment (-1 to +1)
    sma20_pct = (price - sma20) / (sma20 + 1e-10) * 100  # % above/below SMA20
    sma50_pct = (price - sma50) / (sma50 + 1e-10) * 100
    sma_spread = (sma20 - sma50) / (sma50 + 1e-10) * 100

    # Combine: strong uptrend = +1, strong downtrend = -1
    trend_raw = np.clip(
        0.4 * np.tanh(sma20_pct / 5.0) +
        0.3 * np.tanh(sma50_pct / 5.0) +
        0.3 * np.tanh(sma_spread / 3.0),
        -1, 1
    )

    # RSI contribution: 50 is neutral, extremes penalize
    rsi_raw = np.clip((rsi_val - 50.0) / 30.0, -1, 1)
    if rsi_val > 80:
        rsi_raw = -0.3  # overbought penalty
    elif rsi_val < 20:
        rsi_raw = -0.2  # oversold, slight bearish

    tech_raw = 0.6 * trend_raw + 0.4 * rsi_raw
    tech = round(_sigmoid_map(tech_raw, 4.5), 2)

    # ── Momentum score: multi-period returns ──
    pct_3d = (c.iloc[-1] / c.iloc[-4] - 1) * 100 if len(c) >= 4 else 0
    pct_5d = (c.iloc[-1] / c.iloc[-6] - 1) * 100 if len(c) >= 6 else 0
    pct_20d = (c.iloc[-1] / c.iloc[-21] - 1) * 100 if len(c) >= 21 else 0

    # Consistency: fraction of recent closes that are up
    recent_closes = c.tail(10)
    up_frac = ((recent_closes.diff() > 0).sum() / max(len(recent_closes) - 1, 1))

    mom_raw = np.clip(
        0.25 * np.tanh(pct_3d / 3.0) +
        0.30 * np.tanh(pct_5d / 5.0) +
        0.25 * np.tanh(pct_20d / 10.0) +
        0.20 * (up_frac - 0.5) * 2.0,
        -1, 1
    )
    momentum = round(_sigmoid_map(mom_raw, 4.5), 2)

    # ── Volume score: relative volume + trend confirmation ──
    vol_avg_20 = v.rolling(20).mean().iloc[-1] if len(v) >= 20 else v.mean()
    vol_avg_5 = v.tail(5).mean()
    vol_ratio = vol_avg_5 / (vol_avg_20 + 1e-10)
    vol_spike = v.iloc[-1] / (vol_avg_20 + 1e-10)

    # Volume expanding on up moves = bullish; on down moves = bearish
    price_up = price > c.iloc[-2] if len(c) >= 2 else True
    vol_direction = np.tanh((vol_ratio - 1.0) * 3.0) * (1.0 if price_up else -0.6)

    # Extreme spike detection (earnings-day-like)
    spike_bonus = np.clip(np.tanh((vol_spike - 2.0) * 0.8), 0, 1) * 0.4

    vol_raw = np.clip(vol_direction + spike_bonus, -1, 1)
    volume_score = round(_sigmoid_map(vol_raw, 4.5), 2)

    # ── Volume profile: price position within range ──
    range_20 = h.tail(20).max() - l.tail(20).min()
    price_pos = (price - l.tail(20).min()) / (range_20 + 1e-10)  # 0..1

    # Also consider 60-day range for context
    range_60 = h.max() - l.min()
    price_pos_60 = (price - l.min()) / (range_60 + 1e-10) if range_60 > 0 else 0.5

    vp_raw = np.clip(
        0.6 * (price_pos * 2.0 - 1.0) +  # map 0..1 → -1..+1
        0.4 * (price_pos_60 * 2.0 - 1.0),
        -1, 1
    )
    vol_profile = round(_sigmoid_map(vp_raw, 4.0), 2)

    # ── Trendline: higher highs / higher lows ──
    highs_20 = h.tail(20)
    lows_20 = l.tail(20)
    mid = len(highs_20) // 2

    hh = 1.0 if highs_20.iloc[-1] > highs_20.iloc[mid] else (-1.0 if highs_20.iloc[-1] < highs_20.iloc[mid] else 0.0)
    hl = 1.0 if lows_20.iloc[-1] > lows_20.iloc[mid] else (-1.0 if lows_20.iloc[-1] < lows_20.iloc[mid] else 0.0)

    # Add slope magnitude
    high_slope = (highs_20.iloc[-1] - highs_20.iloc[0]) / (highs_20.iloc[0] + 1e-10)
    low_slope = (lows_20.iloc[-1] - lows_20.iloc[0]) / (lows_20.iloc[0] + 1e-10)

    tl_raw = np.clip(
        0.35 * hh + 0.35 * hl +
        0.15 * np.tanh(high_slope * 100) +
        0.15 * np.tanh(low_slope * 100),
        -1, 1
    )
    trendline = round(_sigmoid_map(tl_raw, 4.0), 2)

    # ── Sentiment: RSI + volume-price agreement ──
    rsi_sent = np.clip((rsi_val - 50.0) / 25.0, -1, 1)
    vol_price_agree = 1.0 if (vol_ratio > 1.2 and price_up) else (-1.0 if (vol_ratio > 1.2 and not price_up) else 0.0)
    close_vs_open = (price - o.iloc[-1]) / (o.iloc[-1] + 1e-10) * 100
    candle_raw = np.tanh(close_vs_open / 2.0)

    sent_raw = np.clip(
        0.40 * rsi_sent +
        0.30 * vol_price_agree +
        0.30 * candle_raw,
        -1, 1
    )
    sentiment = round(_sigmoid_map(sent_raw, 4.5), 2)

    # ── Events score: earnings gaps, volume spikes, gap patterns ──
    # Gap detection: open vs previous close
    gaps = []
    for i in range(1, min(len(c), 20)):
        gap_pct = (o.iloc[-i] / c.iloc[-(i + 1)] - 1) * 100 if (i + 1) <= len(c) else 0
        gaps.append(gap_pct)
    gaps = np.array(gaps) if gaps else np.array([0.0])

    # Largest recent gap
    max_gap = np.max(np.abs(gaps))
    # Direction of largest gap
    largest_gap_sign = np.sign(gaps[np.argmax(np.abs(gaps))]) if len(gaps) > 0 else 0

    # Volume spike: any day in last 5 with >3x average = likely earnings/event
    recent_vols = v.tail(5).values
    avg_vol = vol_avg_20 if vol_avg_20 > 0 else 1.0
    spike_days = np.sum(recent_vols > 3.0 * avg_vol)

    # Price reaction after spike: did the stock hold gains?
    if spike_days > 0:
        # Find the spike day and check follow-through
        spike_idx = np.argmax(recent_vols > 3.0 * avg_vol)
        if spike_idx < len(c) - 1:
            post_spike_return = (c.iloc[-1] / c.iloc[-(5 - spike_idx)] - 1) * 100
        else:
            post_spike_return = 0
    else:
        post_spike_return = 0

    # Composite events signal
    gap_signal = np.tanh(largest_gap_sign * max_gap / 3.0) * 0.4
    spike_signal = np.tanh((spike_days - 0.5) * 2.0) * 0.3
    reaction_signal = np.tanh(post_spike_return / 3.0) * 0.3

    evt_raw = np.clip(gap_signal + spike_signal + reaction_signal, -1, 1)
    events_score = round(_sigmoid_map(evt_raw, 4.0), 2)

    # ── Overall weighted score ──
    overall = round(
        tech * 0.20 + momentum * 0.25 + volume_score * 0.15 +
        vol_profile * 0.10 + trendline * 0.10 + sentiment * 0.10 + events_score * 0.10,
        2
    )

    if overall > 60:
        bias = "bullish"
        conclusion = "BUY"
    elif overall < 40:
        bias = "bearish"
        conclusion = "SELL"
    else:
        bias = "neutral"
        conclusion = "HOLD"

    # ── AI Matrix Score: single 0-100 directional prediction ──
    if precomputed:
        st = precomputed["st_result"]
        ac = precomputed["ac_result"]
        st_signal = int(st["trend"].iloc[-1])
        ac_signal = int(ac["accel_signal"].iloc[-1])
        st_cross = bool(st["crossed_above"].iloc[-1] or st["crossed_below"].iloc[-1])
        ac_cross_up = bool(ac["accel_crossed_up"].iloc[-1])
        ac_cross_down = bool(ac["accel_crossed_down"].iloc[-1])
        fresh_cross = st_cross or ac_cross_up or ac_cross_down
        streak_val = precomputed["streak_val"]
        wa_val = precomputed["wa_val"]
        prob_1d_val = precomputed["prob_1d_val"]
    else:
        st = supertrend(bars_df, period=14, multiplier=2.0)
        ac = accel(bars_df)
        st_signal = int(st["trend"].iloc[-1])
        ac_signal = int(ac["accel_signal"].iloc[-1])
        st_cross = bool(st["crossed_above"].iloc[-1] or st["crossed_below"].iloc[-1])
        ac_cross_up = bool(ac["accel_crossed_up"].iloc[-1])
        ac_cross_down = bool(ac["accel_crossed_down"].iloc[-1])
        fresh_cross = st_cross or ac_cross_up or ac_cross_down
        streak_val = int(streak_vectorized(c)[-1])
        wa_series = weighted_alpha(bars_df)
        wa_val = float(wa_series.iloc[-1]) if len(wa_series) > 0 else 0.0
        prob_1d_val = float(prob_up(c, 1).iloc[-1])
    rsi_val = float(rsi_wilder(c, 14).iloc[-1])
    atrp_val = float(((h - l) / c * 100).tail(20).mean())
    vol_avg_20 = float(v.rolling(20, min_periods=1).mean().iloc[-1])
    vol_ratio = float(v.tail(5).mean()) / (vol_avg_20 + 1e-10)
    vol_spike = bool(v.iloc[-1] > 3.0 * vol_avg_20)
    sma20_val = float(c.rolling(20, min_periods=1).mean().iloc[-1])
    sma50_val = float(c.rolling(50, min_periods=1).mean().iloc[-1])
    price_pos_20 = float((price - l.tail(20).min()) / (h.tail(20).max() - l.tail(20).min() + 1e-10))

    ai_matrix = _compute_ai_matrix_score(
        st_signal=st_signal, st_crossed=fresh_cross,
        accel_signal=ac_signal, accel_crossed_up=ac_cross_up, accel_crossed_down=ac_cross_down,
        streak=streak_val, weighted_alpha=wa_val,
        atrp=atrp_val, prob_up_1d=prob_1d_val, rsi=rsi_val,
        sma20=sma20_val, sma50=sma50_val,
        volume_ratio_5_20=vol_ratio, volume_spike=vol_spike,
        price=price, price_high_20d=float(h.tail(20).max()), price_low_20d=float(l.tail(20).min())
    )

    return {
        "overall_score": overall, "bias": bias,
        "tech_score": tech, "momentum_score": momentum,
        "volume_score": volume_score, "events_score": events_score,
        "volume_profile_score": vol_profile,
        "trendline_score": trendline, "sentiment_score": sentiment,
        "ai_matrix": ai_matrix,
        "conclusion": conclusion
    }


def compute_signal_prob_matrix(hs_df):
    """Compute probability-permutation matrix from historical_screener data."""
    if hs_df.empty:
        return pd.DataFrame()

    df = hs_df.copy()
    df["st_state"] = "neutral"
    df.loc[df["atr_signal"] == 1, "st_state"] = "cross_up"
    df.loc[(df["atr_signal"] == 0) & (df["atr_streak"] > 0), "st_state"] = "in_uptrend"
    df.loc[df["atr_signal"] == -1, "st_state"] = "cross_down"
    df.loc[(df["atr_signal"] == 0) & (df["atr_streak"] < 0), "st_state"] = "in_downtrend"

    df["accel_state"] = "neutral"
    df.loc[df["accel_signal"] == 1, "accel_state"] = "accel_up"
    df.loc[df["accel_signal"] == -1, "accel_state"] = "accel_down"
    if "accel_crossed_up" in df.columns:
        df.loc[df["accel_crossed_up"] == 1, "accel_state"] = "cross_up"
    if "accel_crossed_down" in df.columns:
        df.loc[df["accel_crossed_down"] == 1, "accel_state"] = "cross_down"

    df["wa_bucket"] = "0-20"
    df.loc[df["weighted_alpha"] > 50, "wa_bucket"] = ">50"
    df.loc[(df["weighted_alpha"] > 20) & (df["weighted_alpha"] <= 50), "wa_bucket"] = "20-50"
    df.loc[(df["weighted_alpha"] > 0) & (df["weighted_alpha"] <= 20), "wa_bucket"] = "0-20"
    df.loc[df["weighted_alpha"] <= 0, "wa_bucket"] = "<0"

    grouped = df.groupby(["st_state", "accel_state", "wa_bucket"])
    results = []
    for (st, accel_s, wa), group in grouped:
        if len(group) < 10:
            continue
        ndr = group["next_day_return"]
        results.append({
            "st_state": st, "accel_state": accel_s, "wa_bucket": wa,
            "prob_up_1d": round((ndr > 0).mean() * 100, 2),
            "prob_up_1pct": round((ndr > 1).mean() * 100, 2),
            "prob_up_2pct": round((ndr > 2).mean() * 100, 2),
            "prob_down_2pct": round((ndr < -2).mean() * 100, 2),
            "sample_count": len(group),
            "avg_next_day_return": round(ndr.mean(), 4),
            "sharpe": round(ndr.mean() / (ndr.std() + 1e-10), 4)
        })
    return pd.DataFrame(results).drop_duplicates(subset=["st_state", "accel_state", "wa_bucket"], keep="last")


def combined_ohlc(symbols_data, weights=None):
    """Combine multiple symbols' OHLC into one series (equal-weighted normalized index).
    symbols_data: dict of symbol -> DataFrame with open,high,low,close columns (same dates).
    Returns DataFrame with combined OHLC."""
    if not symbols_data:
        return pd.DataFrame()
    syms = list(symbols_data.keys())
    if weights is None:
        weights = {s: 1.0 / len(syms) for s in syms}

    all_dates = set()
    for df in symbols_data.values():
        if "date" in df.columns:
            all_dates.update(df["date"].tolist())
        else:
            all_dates.update(df.index.tolist())
    all_dates = sorted(all_dates)

    combined = pd.DataFrame({"date": all_dates}).set_index("date")
    for sym, df in symbols_data.items():
        if "date" in df.columns:
            df = df.set_index("date")
        w = weights.get(sym, 1.0 / len(syms))
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                if col not in combined.columns:
                    combined[col] = 0.0
                combined[col] += df[col].reindex(combined.index).ffill().fillna(0) * w

    combined["volume"] = 0
    for sym, df in symbols_data.items():
        if "date" in df.columns:
            df = df.set_index("date")
        if "volume" in df.columns:
            combined["volume"] += df["volume"].reindex(combined.index).fillna(0).astype(int)

    return combined.reset_index()
