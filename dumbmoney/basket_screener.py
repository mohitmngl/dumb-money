"""Basket String Screener - vectorized matrix computation.

Each "string" is a fixed basket of stocks, e.g. AAPL*2.5+MSFT*1.8+NVDA*0.7.
Strings are pre-generated and stored permanently in `string_universe` /
`string_constituents`. Metrics are computed with:

    close_pivot  (symbols x dates) from bars — cached as .npy for instant load
    basket_values table — pre-stored basket value series (fixed baskets)
    gather+einsum — fast basket value computation (no sparse matmul)
    W @ per_symbol_metric_matrix — weighted metrics per chunk

Fully vectorized; no per-string Python loops in hot paths.
"""

import logging
import os
import time
import json
import numpy as np
import pandas as pd
from dumbmoney.indicators import bars_at_side
from datetime import datetime

try:
    import scipy.sparse as sp
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

try:
    from numba import njit, prange
    HAVE_NUMBA = True
except Exception:
    HAVE_NUMBA = False

from dumbmoney.db import get_db

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.cache')


def _chunked_read(sql_template, conn, sym_list, extra_params=None):
    """Read data in chunks to avoid SQLite 999-variable limit."""
    frames = []
    extra_params = extra_params or []
    for i in range(0, len(sym_list), CHUNK_SIZE):
        chunk = sym_list[i:i+CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))
        q = sql_template.replace("__PH__", placeholders)
        params = extra_params + chunk
        frames.append(pd.read_sql(q, conn, params=params))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

STRING_COUNT = 25000
MIN_CONSTITUENTS = 10
MAX_CONSTITUENTS = 10

_circuit_cache = {}
_nifty500_cache = None


def _fetch_nifty500_symbols():
    """Fetch Nifty 500 constituent symbols from NSE CSV archive.
    Returns a set of Yahoo-style symbols (e.g. 'RELIANCE.NS').
    Caches result for the process lifetime."""
    global _nifty500_cache
    if _nifty500_cache is not None:
        return _nifty500_cache
    try:
        import csv, io
        from curl_cffi import requests as cffi_req
        session = cffi_req.Session(impersonate="chrome120")
        resp = session.get(
            "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
            timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Nifty 500 CSV returned status {resp.status_code}")
            _nifty500_cache = set()
            return _nifty500_cache
        reader = csv.reader(io.StringIO(resp.text))
        next(reader)  # skip header
        symbols = set()
        for row in reader:
            sym = row[2].strip() if len(row) > 2 else ""
            if sym:
                symbols.add(sym + ".NS")
        _nifty500_cache = symbols
        logger.info(f"Fetched {len(symbols)} Nifty 500 constituents")
        return symbols
    except Exception as e:
        logger.warning(f"Failed to fetch Nifty 500: {e}")
        _nifty500_cache = set()
        return set()


def _is_at_circuit(sym, price):
    """Check if a stock is at upper or lower circuit using NSE data.
    Returns True if at circuit (should be excluded)."""
    if price <= 0:
        return True
    if sym in _circuit_cache:
        return _circuit_cache[sym]
    try:
        import requests as _req
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        resp = _req.get(
            f"https://www.nseindia.com/api/quote-equity?symbol={sym}",
            headers=headers, timeout=3)
        if resp.status_code != 200:
            _circuit_cache[sym] = False
            return False
        data = resp.json()
        price_info = data.get("priceInfo", {})
        upper_cp = price_info.get("upperCP", 0) or 0
        lower_cp = price_info.get("lowerCP", 0) or 0
        at_circuit = (price >= upper_cp and upper_cp > 0) or (price <= lower_cp and lower_cp > 0)
        _circuit_cache[sym] = at_circuit
        return at_circuit
    except Exception:
        _circuit_cache[sym] = False
        return False

STATS_COLS = [
    "weighted_alpha", "atrp", "atr_signal", "atr_stop", "atr_value", "atr_streak",
    "atr_crossed_above", "atr_crossed_below", "atr_multiplier", "volume",
    "prob_up_1d", "prob_up_5d", "prob_up_st_cross", "accel_a", "accel_base", "accel_signal",
    "accel_crossed_up", "accel_crossed_down", "accel_streak", "confluence",
]
AI_COLS = [
    "overall_score", "bias", "tech_score", "momentum_score",
    "volume_score", "events_score", "volume_profile_score",
    "trendline_score", "sentiment_score", "conclusion", "ai_matrix",
]
HIST_COLS = [c for c in STATS_COLS if c != "accel_streak"] + [
    "ai_matrix", "ai_overall_score", "ai_bias", "ai_volume_profile_score",
    "ai_trendline_score", "ai_sentiment_score",
    "ai_tech_score", "ai_momentum_score", "ai_volume_score",
    "ai_events_score", "ai_conclusion"]


def _eligible_symbols(market):
    conn = get_db(market)
    try:
        if market == "US":
            syms = [r[0] for r in conn.execute(
                "SELECT a.symbol FROM assets a JOIN stats s ON s.symbol=a.symbol "
                "WHERE a.status='active' AND a.tradable=1 "
                "AND COALESCE(a.exchange,'') <> 'OTC' "
                "AND LOWER(COALESCE(a.asset_class,'')) = 'stock' "
                "AND COALESCE(s.volume,0) >= 100000").fetchall()]
        else:
            nifty500 = _fetch_nifty500_symbols()
            if nifty500:
                all_syms = [r[0] for r in conn.execute(
                    "SELECT a.symbol FROM assets a JOIN stats s ON s.symbol=a.symbol "
                    "WHERE a.status='active' "
                    "AND LOWER(COALESCE(a.asset_class,'')) = 'stock' "
                    "AND COALESCE(s.volume,0) >= 100000").fetchall()]
                syms = [s for s in all_syms if s in nifty500]
                logger.info(f"India eligible: {len(syms)} from Nifty 500 (of {len(all_syms)} total)")
            else:
                syms = [r[0] for r in conn.execute(
                    "SELECT a.symbol FROM assets a JOIN stats s ON s.symbol=a.symbol "
                    "WHERE a.status='active' "
                    "AND LOWER(COALESCE(a.asset_class,'')) = 'stock' "
                    "AND COALESCE(s.volume,0) >= 100000").fetchall()]
        return syms
    finally:
        conn.close()




def _get_cache_path(market):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"close_pivot_{market}.npy"), os.path.join(_CACHE_DIR, f"close_meta_{market}.json")


def _get_ohlc_cache_paths(market):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    base = _CACHE_DIR
    return {
        'open': os.path.join(base, f"open_pivot_{market}.npy"),
        'high': os.path.join(base, f"high_pivot_{market}.npy"),
        'low': os.path.join(base, f"low_pivot_{market}.npy"),
    }


def build_close_pivot_cache(market):
    """Build .npy cache of OHLC pivots from bars. Returns (sym_list, dates, close_matrix)."""
    t0 = time.time()
    conn = get_db(market)
    try:
        date_rows = conn.execute(
            "SELECT date, COUNT(*) as cnt FROM bars WHERE timeframe='1Day' "
            "GROUP BY date HAVING cnt >= 100 ORDER BY date ASC"
        ).fetchall()
        valid_dates = [r[0] for r in date_rows]
        if not valid_dates:
            return [], [], np.zeros((0, 0), dtype=np.float32)

        sym_rows = conn.execute(
            "SELECT DISTINCT symbol FROM bars WHERE timeframe='1Day' ORDER BY symbol"
        ).fetchall()
        all_symbols = [r[0] for r in sym_rows]

        sym_idx = {s: i for i, s in enumerate(all_symbols)}
        date_idx = {d: i for i, d in enumerate(valid_dates)}
        n_sym = len(all_symbols)
        n_dates = len(valid_dates)

        close_matrix = np.full((n_sym, n_dates), np.nan, dtype=np.float32)
        open_matrix = np.full((n_sym, n_dates), np.nan, dtype=np.float32)
        high_matrix = np.full((n_sym, n_dates), np.nan, dtype=np.float32)
        low_matrix = np.full((n_sym, n_dates), np.nan, dtype=np.float32)

        cur = conn.execute(
            "SELECT symbol, date, open, high, low, close FROM bars WHERE timeframe='1Day'"
        )
        rows = cur.fetchmany(500000)
        filled = 0
        while rows:
            for sym, dt, op, hi, lo, cl in rows:
                si = sym_idx.get(sym)
                di = date_idx.get(dt)
                if si is not None and di is not None:
                    if cl is not None:
                        close_matrix[si, di] = float(cl)
                    if op is not None:
                        open_matrix[si, di] = float(op)
                    if hi is not None:
                        high_matrix[si, di] = float(hi)
                    if lo is not None:
                        low_matrix[si, di] = float(lo)
                    filled += 1
            rows = cur.fetchmany(500000)

        def _fwd_fill(m):
            mask = (m == 0.0) | np.isnan(m)
            idx = np.where(~mask, np.arange(m.shape[1]), 0)
            np.maximum.accumulate(idx, axis=1, out=idx)
            fidx = np.where(mask, idx, np.arange(m.shape[1]))
            rows, cols = np.indices(m.shape)
            out = m[rows, fidx]
            out[mask & (fidx == 0)] = 0.0
            return out

        close_matrix = _fwd_fill(close_matrix)
        open_matrix = _fwd_fill(open_matrix)
        high_matrix = _fwd_fill(high_matrix)
        low_matrix = _fwd_fill(low_matrix)

        npy_path, meta_path = _get_cache_path(market)
        np.save(npy_path, close_matrix)
        with open(meta_path, 'w') as f:
            json.dump({'symbols': all_symbols, 'dates': valid_dates}, f)

        ohlc_paths = _get_ohlc_cache_paths(market)
        np.save(ohlc_paths['open'], open_matrix)
        np.save(ohlc_paths['high'], high_matrix)
        np.save(ohlc_paths['low'], low_matrix)

        logger.info(f"[{market}] OHLC pivot cache built: {n_sym} sym x {n_dates} dates, {filled} values, {time.time()-t0:.1f}s")
        return all_symbols, valid_dates, close_matrix
    finally:
        conn.close()


def _load_close_pivot(market, sym_list=None, date_limit=None):
    """Load close_pivot from .npy cache (fast) or build inline (slow).
    Returns (sym_list_used, dates, close_matrix float32 (n_sym x n_dates))."""
    npy_path, meta_path = _get_cache_path(market)
    if os.path.exists(npy_path) and os.path.exists(meta_path):
        matrix = np.load(npy_path)
        with open(meta_path) as f:
            meta = json.load(f)
        all_symbols = meta['symbols']
        dates = meta['dates']
        if date_limit is not None:
            dates = dates[-date_limit:]
            matrix = matrix[:, -date_limit:]
        if sym_list is not None:
            sym_idx_map = {s: i for i, s in enumerate(all_symbols)}
            row_idx = [sym_idx_map[s] for s in sym_list if s in sym_idx_map]
            used_syms = [s for s in sym_list if s in sym_idx_map]
            return used_syms, dates, matrix[row_idx, :]
        return all_symbols, dates, matrix

    logger.info(f"[{market}] no .npy cache, building inline (slow)")
    conn = get_db(market)
    try:
        date_rows = conn.execute(
            "SELECT date, COUNT(*) as cnt FROM bars WHERE timeframe='1Day' "
            "GROUP BY date HAVING cnt >= 100 ORDER BY date ASC"
        ).fetchall()
        valid_dates = [r[0] for r in date_rows]
        if not valid_dates:
            return sym_list or [], [], np.zeros((len(sym_list or []), 0), dtype=np.float32)
        if date_limit is not None:
            valid_dates = valid_dates[-date_limit:]
        if sym_list is None:
            sym_rows = conn.execute(
                "SELECT DISTINCT symbol FROM bars WHERE timeframe='1Day' ORDER BY symbol"
            ).fetchall()
            sym_list = [r[0] for r in sym_rows]
        sym_idx = {s: i for i, s in enumerate(sym_list)}
        date_idx = {d: i for i, d in enumerate(valid_dates)}
        matrix = np.full((len(sym_list), len(valid_dates)), np.nan, dtype=np.float32)
        placeholders = ",".join("?" * len(sym_list))
        cur = conn.execute(
            f"SELECT symbol, date, close FROM bars WHERE timeframe='1Day' "
            f"AND symbol IN ({placeholders})", sym_list)
        rows = cur.fetchmany(500000)
        while rows:
            for sym, dt, close in rows:
                si = sym_idx.get(sym)
                di = date_idx.get(dt)
                if si is not None and di is not None and close is not None:
                    matrix[si, di] = float(close)
            rows = cur.fetchmany(500000)
        mask = (matrix == 0.0) | np.isnan(matrix)
        idx = np.where(~mask, np.arange(matrix.shape[1]), 0)
        np.maximum.accumulate(idx, axis=1, out=idx)
        fidx = np.where(mask, idx, np.arange(matrix.shape[1]))
        rows_arr, cols_arr = np.indices(matrix.shape)
        matrix = matrix[rows_arr, fidx]
        matrix[mask & (fidx == 0)] = 0.0
        return sym_list, valid_dates, matrix
    finally:
        conn.close()


def _gross_adjust(V, close_pivot, indices, weights):
    """Convert net basket values to GROSS-exposure accounting.

    The raw einsum value is net (shorts subtract), which hides the real
    exposure of a long+short string: a $600 long / $400 short string shows
    as ~$200. Correct accounting holds short proceeds as cash, so the
    string value at the baseline date equals its GROSS exposure
    (sum |weight x price|) and P&L accrues with correct signs afterwards:
        V(t) = gross(t0) + sum_i w_i * (p_i(t) - p_i(t0))
    Pure-long baskets are unchanged (cash adjustment = 0)."""
    abs_w = np.abs(weights)
    gross0 = np.einsum('bi,bi->b', abs_w, close_pivot[indices, 0])
    gross0 = np.nan_to_num(gross0, nan=0.0)
    cash = gross0 - V[:, 0]
    return V + cash[:, None]


def _gather_einsum(close_pivot, indices, weights):
    """Gather + einsum: compute basket values without sparse matmul.
    close_pivot: (n_sym, n_dates), indices: (n_strings, 10), weights: (n_strings, 10)
    Returns V: (n_strings, n_dates) in GROSS-exposure terms (see _gross_adjust).
    Chunked to keep peak RAM low."""
    n_strings = indices.shape[0]
    n_dates = close_pivot.shape[1]
    result = np.zeros((n_strings, n_dates), dtype=np.float32)
    chunk_size = 2000
    for i in range(0, n_strings, chunk_size):
        idx_chunk = indices[i:i+chunk_size]
        w_chunk = weights[i:i+chunk_size]
        result[i:i+chunk_size] = np.einsum('bi,bid->bd', w_chunk, close_pivot[idx_chunk])
    result = np.nan_to_num(result, nan=0.0)
    return _gross_adjust(result, close_pivot, indices, weights)


def _series_metrics(V):
    """Compute series metrics from basket value matrix V (n_strings x n_dates).
    Returns dict of series arrays."""
    V = np.nan_to_num(V, nan=0.0)
    first = V[:, 0:1].copy()
    first[first == 0] = 1.0
    first_abs = np.abs(first)
    Vn = (V / first_abs) * 1000.0
    Vn = np.nan_to_num(Vn, nan=1000.0)
    ret = np.zeros_like(Vn)
    ret[:, 1:] = ((Vn[:, 1:] - Vn[:, :-1]) / np.where(Vn[:, :-1] == 0, 1e-9, Vn[:, :-1])) * 100.0
    ret = np.nan_to_num(ret, nan=0.0)
    n_dates = Vn.shape[1]
    sgn = np.where(ret > 0, 1, np.where(ret < 0, -1, 0)).astype(np.int8)
    streak_arr = np.zeros_like(sgn)
    prev = np.zeros((Vn.shape[0],), dtype=np.int32)
    prev_sgn = np.zeros((Vn.shape[0],), dtype=np.int8)
    for t in range(n_dates):
        s = sgn[:, t]
        st = np.where(s == 0, 0, np.where((s == prev_sgn) & (prev_sgn != 0), prev + s, s))
        streak_arr[:, t] = st
        prev = st; prev_sgn = s
    return {"V": Vn, "ret": ret, "streak_series": streak_arr}


def _r_squared_matrix(V, window=90):
    """Row-wise rolling signed R2 of a linear fit on log(value), for the whole
    (n_strings x n_dates) matrix at once via cumulative sums. +1 = perfectly
    straight uptrending value line, -1 = straight down. O(n_strings * n_dates)."""
    n_strings, n_dates = V.shape
    out = np.zeros_like(V, dtype=np.float32)
    if n_dates < 3:
        return out
    w = min(window, n_dates)
    with np.errstate(divide="ignore", invalid="ignore"):
        y = np.log(np.maximum(V.astype(np.float64), 1e-9))
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    t = np.arange(n_dates, dtype=np.float64)[None, :]

    cs1 = np.cumsum(y, axis=1)
    csyy = np.cumsum(y * y, axis=1)
    csty = np.cumsum(t * y, axis=1)

    def _roll(cs):
        tot = np.zeros_like(cs)
        tot[:, w-1:] = cs[:, w-1:] - np.concatenate([np.zeros((cs.shape[0], 1)), cs[:, :-w]], axis=1)[:, w-1:]
        tot[:, :w-1] = cs[:, :w-1]
        return tot

    s1 = _roll(cs1)
    syy = _roll(csyy)
    sty_abs = _roll(csty)

    end_idx = np.arange(n_dates, dtype=np.float64)[None, :]
    k0 = end_idx - (w - 1)
    sxy = sty_abs - k0 * s1

    sx = w * (w - 1) / 2.0
    sxx = w * (w - 1) * (2 * w - 1) / 6.0

    num = w * sxy - sx * s1
    den = (w * sxx - sx * sx) * (w * syy - s1 * s1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r2 = np.where(den > 0, (num * num) / den, 0.0)
        slope = np.where((w * sxx - sx * sx) != 0, num / (w * sxx - sx * sx), 0.0)
    signed = np.where(slope < 0, -r2, r2)
    signed[:, :w-1] = 0.0  # first partial windows: undefined
    signed = np.nan_to_num(signed, nan=0.0, posinf=0.0, neginf=0.0)
    return signed.astype(np.float32)


def _load_ohlc_pivots(market, sym_list=None, date_limit=None):
    """Load high/low/open pivot .npy caches. Returns (high_pivot, low_pivot, open_pivot) or None."""
    ohlc_paths = _get_ohlc_cache_paths(market)
    npy_path, meta_path = _get_cache_path(market)
    if not all(os.path.exists(p) for p in [ohlc_paths['high'], ohlc_paths['low'], ohlc_paths['open'], meta_path]):
        return None
    with open(meta_path) as f:
        meta = json.load(f)
    all_symbols = meta['symbols']
    high_m = np.load(ohlc_paths['high'])
    low_m = np.load(ohlc_paths['low'])
    open_m = np.load(ohlc_paths['open'])
    if date_limit is not None:
        high_m = high_m[:, -date_limit:]
        low_m = low_m[:, -date_limit:]
        open_m = open_m[:, -date_limit:]
    if sym_list is not None:
        sym_idx_map = {s: i for i, s in enumerate(all_symbols)}
        row_idx = [sym_idx_map[s] for s in sym_list if s in sym_idx_map]
        high_m = high_m[row_idx, :]
        low_m = low_m[row_idx, :]
        open_m = open_m[row_idx, :]
    return high_m, low_m, open_m


def _compute_basket_ohlc(close_pivot, high_pivot, low_pivot, open_pivot, indices, weights):
    """Compute basket OHLC via chunked gather+einsum. Returns dict of (n_strings, n_dates) arrays.
    Shifted by the same gross-cash adjustment as the close series so stop levels
    stay comparable to the displayed (gross) string value."""
    n_strings = indices.shape[0]
    n_dates = close_pivot.shape[1]
    basket_close = np.zeros((n_strings, n_dates), dtype=np.float32)
    basket_high = np.zeros((n_strings, n_dates), dtype=np.float32)
    basket_low = np.zeros((n_strings, n_dates), dtype=np.float32)
    basket_open = np.zeros((n_strings, n_dates), dtype=np.float32)
    chunk_size = 2000
    for i in range(0, n_strings, chunk_size):
        idx_chunk = indices[i:i+chunk_size]
        w_chunk = weights[i:i+chunk_size]
        basket_close[i:i+chunk_size] = np.einsum('bi,bid->bd', w_chunk, close_pivot[idx_chunk])
        basket_high[i:i+chunk_size] = np.einsum('bi,bid->bd', w_chunk, high_pivot[idx_chunk])
        basket_low[i:i+chunk_size] = np.einsum('bi,bid->bd', w_chunk, low_pivot[idx_chunk])
        basket_open[i:i+chunk_size] = np.einsum('bi,bid->bd', w_chunk, open_pivot[idx_chunk])
    basket_close = np.nan_to_num(basket_close, nan=0.0)
    # Same cash shift as _gather_einsum (based on close baseline) applied to all four
    abs_w = np.abs(weights)
    gross0 = np.nan_to_num(np.einsum('bi,bi->b', abs_w, close_pivot[indices, 0]), nan=0.0)
    cash = (gross0 - basket_close[:, 0])[:, None]
    return {
        'open': np.nan_to_num(basket_open, nan=0.0) + cash,
        'high': np.nan_to_num(basket_high, nan=0.0) + cash,
        'low': np.nan_to_num(basket_low, nan=0.0) + cash,
        'close': basket_close + cash,
    }


def _supertrend_vec(h, l, c, period=14, multiplier=2.0):
    """ATR Trailing Stop for vectorized bulk use.
    Recursive trailing stop based on ATR, not HL2 bands.
    Returns dict of arrays. Convention: direction=1 → uptrend (stop below),
    direction=-1 → downtrend (stop above)."""
    n = len(c)
    if n < 2:
        return {'atr_signal': np.zeros(n, dtype=np.int32), 'atr_stop': np.full(n, np.nan),
                'atr_value': np.full(n, np.nan), 'atr_streak': np.zeros(n, dtype=np.int32),
                'atr_crossed_above': np.zeros(n, dtype=np.int32), 'atr_crossed_below': np.zeros(n, dtype=np.int32),
                'atr_multiplier': np.full(n, float(multiplier))}

    # True Range
    prev_c = np.empty(n, dtype=np.float64)
    prev_c[0] = c[0]
    prev_c[1:] = c[:-1]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))

    # Wilder's ATR
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    # Trailing stop computation
    st = np.full(n, np.nan)
    direction = np.zeros(n, dtype=np.int32)

    for i in range(n):
        if np.isnan(atr[i]):
            direction[i] = -1
            continue

        loss = multiplier * atr[i]
        prev_stop = st[i - 1] if i > 0 else np.nan
        prev_close = c[i - 1] if i > 0 else c[i]

        if np.isnan(prev_stop):
            # First valid bar - initialize
            direction[i] = -1
            st[i] = c[i] + loss
        elif c[i] > prev_stop and prev_close > prev_stop:
            # Bullish continuation - stop moves up
            new_stop = c[i] - loss
            st[i] = max(prev_stop, new_stop)
            direction[i] = 1
        elif c[i] < prev_stop and prev_close < prev_stop:
            # Bearish continuation - stop moves down
            new_stop = c[i] + loss
            st[i] = min(prev_stop, new_stop)
            direction[i] = -1
        elif c[i] > prev_stop and prev_close <= prev_stop:
            # Cross up - new bullish stop
            direction[i] = 1
            st[i] = c[i] - loss
        elif c[i] < prev_stop and prev_close >= prev_stop:
            # Cross down - new bearish stop
            direction[i] = -1
            st[i] = c[i] + loss
        else:
            # Should not happen, but default to previous
            direction[i] = direction[i - 1] if i > 0 else -1
            st[i] = prev_stop

    # Signals
    signal = np.zeros(n, dtype=np.int32)
    crossed_above = np.zeros(n, dtype=np.int32)
    crossed_below = np.zeros(n, dtype=np.int32)
    for i in range(1, n):
        if direction[i] == 1 and direction[i - 1] == -1:
            signal[i] = 1
            crossed_above[i] = 1
        elif direction[i] == -1 and direction[i - 1] == 1:
            signal[i] = -1
            crossed_below[i] = 1

    # Streak
    streak_arr = np.zeros(n, dtype=np.int32)
    for i in range(n):
        if direction[i] == 0:
            streak_arr[i] = 0
        elif i == 0 or direction[i] != direction[i - 1]:
            streak_arr[i] = 1 if direction[i] == 1 else -1
        else:
            streak_arr[i] = streak_arr[i - 1] + (1 if direction[i] == 1 else -1)

    return {'atr_signal': direction, 'atr_stop': st, 'atr_value': atr,
            'atr_streak': streak_arr, 'atr_crossed_above': crossed_above,
            'atr_crossed_below': crossed_below, 'atr_multiplier': np.full(n, float(multiplier))}


def _accel_vec(c):
    """Vectorized Accel for a single close series. Returns dict of arrays."""
    n = len(c)
    c_s = pd.Series(c, dtype=float)
    sma6 = c_s.rolling(6, min_periods=1).mean().values
    sma7 = c_s.rolling(7, min_periods=1).mean().values
    sma13 = c_s.rolling(13, min_periods=1).mean().values
    sma14 = c_s.rolling(14, min_periods=1).mean().values
    sma27 = c_s.rolling(27, min_periods=1).mean().values
    sma28 = c_s.rolling(28, min_periods=1).mean().values

    with np.errstate(divide='ignore', invalid='ignore'):
        a = np.where(sma7 != 0, sma28 * sma14 / (sma7 ** 2), 1.0)
        denom = 8.0 * (c + 6.0 * sma6) ** 2
        base = np.where(denom != 0, (c + 27.0 * sma27) * (c + 13.0 * sma13) / denom, 1.0)

    a = np.nan_to_num(a, nan=1.0)
    base = np.nan_to_num(base, nan=1.0)

    sig = np.where(a > base, 1, -1).astype(np.int32)
    prev_sig = np.roll(sig, 1)
    prev_sig[0] = 0

    crossed_up = ((sig == 1) & (prev_sig == -1)).astype(np.int32)
    crossed_down = ((sig == -1) & (prev_sig == 1)).astype(np.int32)

    accel_streak = np.zeros(n, dtype=np.int32)
    for i in range(1, n):
        if sig[i] == sig[i - 1]:
            accel_streak[i] = accel_streak[i - 1] + (1 if sig[i] == 1 else -1)
        else:
            accel_streak[i] = 1 if sig[i] == 1 else -1

    return {'accel_a': a.astype(np.float32), 'accel_base': base.astype(np.float32),
            'accel_signal': sig, 'accel_crossed_up': crossed_up,
            'accel_crossed_down': crossed_down, 'accel_streak': accel_streak}


if HAVE_NUMBA:
    @njit(cache=True, fastmath=True)
    def _supertrend_standalone(hi, lo, cl, period, multiplier):
        """ATR Trailing Stop on single series. Recursive stop logic.
        Returns 7 arrays as flat tuple."""
        n = len(cl)
        atr = np.full(n, np.nan, dtype=np.float64)
        st_stop = np.full(n, np.nan, dtype=np.float64)
        direction = np.zeros(n, dtype=np.int32)
        crossed_above = np.zeros(n, dtype=np.int32)
        crossed_below = np.zeros(n, dtype=np.int32)
        streak_arr = np.zeros(n, dtype=np.int32)

        if n < 2:
            return (direction, st_stop, atr, streak_arr, crossed_above, crossed_below, multiplier)

        # True Range
        tr = np.empty(n, dtype=np.float64)
        tr[0] = hi[0] - lo[0]
        for t in range(1, n):
            tr[t] = max(hi[t] - lo[t], abs(hi[t] - cl[t-1]), abs(lo[t] - cl[t-1]))

        # Wilder's ATR
        if n >= period:
            atr[period-1] = sum(tr[:period]) / period
            for t in range(period, n):
                atr[t] = (atr[t-1] * (period - 1) + tr[t]) / period

        # Trailing stop computation
        for i in range(n):
            if np.isnan(atr[i]):
                direction[i] = -1
                continue

            loss = multiplier * atr[i]
            prev_stop = st_stop[i - 1] if i > 0 else np.nan
            prev_close = cl[i - 1] if i > 0 else cl[i]

            if np.isnan(prev_stop):
                # First valid bar - initialize
                direction[i] = -1
                st_stop[i] = cl[i] + loss
            elif cl[i] > prev_stop and prev_close > prev_stop:
                # Bullish continuation - stop moves up
                new_stop = cl[i] - loss
                st_stop[i] = max(prev_stop, new_stop)
                direction[i] = 1
            elif cl[i] < prev_stop and prev_close < prev_stop:
                # Bearish continuation - stop moves down
                new_stop = cl[i] + loss
                st_stop[i] = min(prev_stop, new_stop)
                direction[i] = -1
            elif cl[i] > prev_stop and prev_close <= prev_stop:
                # Cross up - new bullish stop
                direction[i] = 1
                st_stop[i] = cl[i] - loss
            elif cl[i] < prev_stop and prev_close >= prev_stop:
                # Cross down - new bearish stop
                direction[i] = -1
                st_stop[i] = cl[i] + loss
            else:
                # Should not happen, but default to previous
                direction[i] = direction[i - 1] if i > 0 else -1
                st_stop[i] = prev_stop

        # Signals
        for t in range(1, n):
            if direction[t] == 1 and direction[t-1] == -1:
                crossed_above[t] = 1
            elif direction[t] == -1 and direction[t-1] == 1:
                crossed_below[t] = 1

        # Streak
        for t in range(n):
            if direction[t] == 0:
                streak_arr[t] = 0
            elif t == 0 or direction[t] != direction[t-1]:
                streak_arr[t] = 1 if direction[t] == 1 else -1
            else:
                streak_arr[t] = streak_arr[t-1] + (1 if direction[t] == 1 else -1)

        # Zero out pre-period
        for t in range(period - 1):
            st_stop[t] = np.nan
            atr[t] = np.nan
            streak_arr[t] = 0
            crossed_above[t] = 0
            crossed_below[t] = 0

        return (direction, st_stop, atr, streak_arr, crossed_above, crossed_below, multiplier)

    @njit(cache=True, fastmath=True)
    def _rolling_mean(cl, window):
        """Numba rolling mean."""
        n = len(cl)
        out = np.empty(n, dtype=np.float64)
        s = 0.0
        for t in range(min(window, n)):
            s += cl[t]
            out[t] = s / (t + 1)
        if n > window:
            s = 0.0
            for t in range(window):
                s += cl[t]
            out[window-1] = s / window
            for t in range(window, n):
                s += cl[t] - cl[t-window]
                out[t] = s / window
        return out

    @njit(cache=True, fastmath=True)
    def _accel_standalone(cl):
        """Numba Accel on single series. Returns 6 arrays as flat tuple."""
        n = len(cl)
        sma6 = _rolling_mean(cl, 6)
        sma7 = _rolling_mean(cl, 7)
        sma13 = _rolling_mean(cl, 13)
        sma14 = _rolling_mean(cl, 14)
        sma27 = _rolling_mean(cl, 27)
        sma28 = _rolling_mean(cl, 28)

        a = np.empty(n, dtype=np.float64)
        base = np.empty(n, dtype=np.float64)
        for t in range(n):
            if sma7[t] != 0.0:
                a[t] = sma28[t] * sma14[t] / (sma7[t] * sma7[t])
            else:
                a[t] = 1.0
            denom = 8.0 * (cl[t] + 6.0 * sma6[t]) ** 2
            if denom != 0.0:
                base[t] = (cl[t] + 27.0 * sma27[t]) * (cl[t] + 13.0 * sma13[t]) / denom
            else:
                base[t] = 1.0
            if np.isnan(a[t]): a[t] = 1.0
            if np.isnan(base[t]): base[t] = 1.0

        sig = np.zeros(n, dtype=np.int32)
        crossed_up = np.zeros(n, dtype=np.int32)
        crossed_down = np.zeros(n, dtype=np.int32)
        accel_streak = np.zeros(n, dtype=np.int32)

        for t in range(n):
            sig[t] = 1 if a[t] > base[t] else -1

        for t in range(1, n):
            if sig[t] == 1 and sig[t-1] == -1:
                crossed_up[t] = 1
            elif sig[t] == -1 and sig[t-1] == 1:
                crossed_down[t] = 1

        for t in range(1, n):
            if sig[t] == sig[t-1]:
                accel_streak[t] = accel_streak[t-1] + (1 if sig[t] == 1 else -1)
            else:
                accel_streak[t] = 1 if sig[t] == 1 else -1

        return (a.astype(np.float64), base.astype(np.float64), sig, crossed_up, crossed_down, accel_streak)


def _compute_basket_indicators(basket_ohlc, period=14, multiplier=2.0):
    """Compute SuperTrend and Accel for all baskets. Returns dict of (n_strings, n_dates) arrays.
    Uses numba prange parallelism when available (100x+ speedup).
    Processes in chunks to avoid memory spikes on large string sets."""
    n_strings, n_dates = basket_ohlc['close'].shape
    keys_st = ['atr_signal', 'atr_stop', 'atr_value', 'atr_streak',
               'atr_crossed_above', 'atr_crossed_below', 'atr_multiplier']
    keys_ac = ['accel_a', 'accel_base', 'accel_signal', 'accel_crossed_up',
               'accel_crossed_down', 'accel_streak']
    result = {k: np.zeros((n_strings, n_dates), dtype=np.float32) for k in keys_st + keys_ac}

    CHUNK = 5000
    if HAVE_NUMBA and n_strings > 100:
        for start in range(0, n_strings, CHUNK):
            end = min(start + CHUNK, n_strings)
            hi_chunk = basket_ohlc['high'][start:end].astype(np.float64)
            lo_chunk = basket_ohlc['low'][start:end].astype(np.float64)
            cl_chunk = basket_ohlc['close'][start:end].astype(np.float64)
            nc = end - start
            r_atr_sig = result['atr_signal'][start:end]
            r_atr_stop = result['atr_stop'][start:end]
            r_atr_val = result['atr_value'][start:end]
            r_atr_strk = result['atr_streak'][start:end]
            r_atr_ca = result['atr_crossed_above'][start:end]
            r_atr_cb = result['atr_crossed_below'][start:end]
            r_atr_mult = result['atr_multiplier'][start:end]
            r_ac_a = result['accel_a'][start:end]
            r_ac_base = result['accel_base'][start:end]
            r_ac_sig = result['accel_signal'][start:end]
            r_ac_cu = result['accel_crossed_up'][start:end]
            r_ac_cd = result['accel_crossed_down'][start:end]
            r_ac_strk = result['accel_streak'][start:end]
            _compute_all_numba(hi_chunk, lo_chunk, cl_chunk,
                               r_atr_sig, r_atr_stop, r_atr_val, r_atr_strk,
                               r_atr_ca, r_atr_cb, r_atr_mult,
                               r_ac_a, r_ac_base, r_ac_sig,
                               r_ac_cu, r_ac_cd, r_ac_strk,
                               nc, n_dates, period, multiplier)
            del hi_chunk, lo_chunk, cl_chunk
            logger.info(f"  Basket indicators chunk {end}/{n_strings}")
        logger.info(f"  Basket indicators computed with numba parallel ({n_strings} strings)")
    else:
        for i in range(n_strings):
            h = basket_ohlc['high'][i]
            l = basket_ohlc['low'][i]
            c = basket_ohlc['close'][i]
            st = _supertrend_vec(h, l, c, period, multiplier)
            ac = _accel_vec(c)
            for k in keys_st:
                result[k][i] = st[k].astype(np.float32)
            for k in keys_ac:
                result[k][i] = ac[k].astype(np.float32)
            if (i + 1) % 5000 == 0:
                logger.info(f"  Basket indicators: {i+1}/{n_strings}")

    return result


if HAVE_NUMBA:
    @njit(cache=True, fastmath=True, parallel=True)
    def _compute_all_numba(hi_all, lo_all, cl_all,
                           r_atr_signal, r_atr_stop, r_atr_value, r_atr_streak,
                           r_atr_ca, r_atr_cb, r_atr_mult,
                           r_accel_a, r_accel_base, r_accel_signal,
                           r_accel_cu, r_accel_cd, r_accel_streak,
                           n_strings, n_dates, period, multiplier):
        """Parallel SuperTrend + Accel for all strings via prange."""
        for i in prange(n_strings):
            hi = hi_all[i]
            lo = lo_all[i]
            cl = cl_all[i]

            (dir_arr, st_stop, atr_val, st_streak, ca, cb, mult) = _supertrend_standalone(hi, lo, cl, period, multiplier)
            (aa, ab, asig, acu, acd, astreak) = _accel_standalone(cl)

            for t in range(n_dates):
                r_atr_signal[i, t] = dir_arr[t]
                r_atr_stop[i, t] = st_stop[t]
                r_atr_value[i, t] = atr_val[t]
                r_atr_streak[i, t] = st_streak[t]
                r_atr_ca[i, t] = ca[t]
                r_atr_cb[i, t] = cb[t]
                r_atr_mult[i, t] = mult
                r_accel_a[i, t] = aa[t]
                r_accel_base[i, t] = ab[t]
                r_accel_signal[i, t] = asig[t]
                r_accel_cu[i, t] = acu[t]
                r_accel_cd[i, t] = acd[t]
                r_accel_streak[i, t] = astreak[t]


def _weighted_current(indices, weights, market, sym_list):
    """Current weighted metrics -> dict col -> 1D array (n_strings) using gather+einsum."""
    conn = get_db(market)
    try:
        out = {}
        df = _chunked_read(
            "SELECT symbol, " + ", ".join(STATS_COLS) + " FROM stats WHERE symbol IN (__PH__)",
            conn, sym_list)
        ai = _chunked_read(
            "SELECT symbol, " + ", ".join(AI_COLS) + " FROM ai_analysis WHERE symbol IN (__PH__)",
            conn, sym_list)
        df = df.set_index("symbol").reindex(sym_list).fillna(0)
        ai = ai.set_index("symbol").reindex(sym_list).fillna(0)
        weight_sums = np.abs(weights).sum(axis=1, keepdims=True)
        weight_sums[weight_sums == 0] = 1.0
        Wn = np.abs(weights) / weight_sums
        for col in STATS_COLS:
            vals = df[col].values.astype(np.float32)
            gathered = vals[indices]
            if col == "volume":
                out[col] = np.einsum('bi,bi->b', weights, gathered)
            else:
                out[col] = np.einsum('bi,bi->b', Wn, gathered)
        aim = pd.to_numeric(ai["ai_matrix"], errors="coerce").fillna(0).values.astype(np.float32)
        out["ai_matrix"] = np.einsum('bi,bi->b', Wn, aim[indices])
        for col in ["overall_score", "tech_score", "momentum_score",
                    "volume_score", "events_score", "volume_profile_score",
                    "trendline_score", "sentiment_score"]:
            vals = pd.to_numeric(ai[col], errors="coerce").fillna(0).values.astype(np.float32)
            out[f"ai_{col}"] = np.einsum('bi,bi->b', Wn, vals[indices])
        return out
    finally:
        conn.close()


def compute_current_metrics(market="US"):
    """Recompute string_screener_metrics for all strings (fast, matrix ops).
    SuperTrend and Accel are computed on the basket value itself, not averaged from components."""
    t0 = time.time()
    sids, sym_list, indices, weights = _load_composition(market)
    if not sids:
        logger.info(f"[{market}] no strings; generate universe first")
        return 0
    _, dates, close = _load_close_pivot(market, sym_list, date_limit=80)
    if close.shape[1] == 0:
        logger.warning(f"[{market}] no close data")
        return 0
    V = _gather_einsum(close, indices, weights)
    series = _series_metrics(V)
    wm = _weighted_current(indices, weights, market, sym_list)

    n = len(sids)
    Vn = series["V"]
    ret = series["ret"]
    n_dates = Vn.shape[1]
    price = Vn[:, -1].astype(np.float32)
    change_pct = ret[:, -1].astype(np.float32) if ret.shape[1] >= 1 else np.zeros(n, np.float32)
    next_day = ret[:, -1].astype(np.float32) if ret.shape[1] >= 2 else np.zeros(n, np.float32)
    if Vn.shape[1] >= 6:
        sub = Vn[:, -6:]
        next_5d = (((sub[:, -1] - sub[:, 0]) / np.where(sub[:, 0] == 0, 1e-9, sub[:, 0])) * 100.0).astype(np.float32)
    else:
        next_5d = np.zeros(n, np.float32)
    streak = series["streak_series"][:, -1].astype(np.float32) if series["streak_series"].shape[1] >= 1 else np.zeros(n, np.float32)
    volume = wm.get("volume", np.zeros(n, np.float32))
    wa = wm.get("weighted_alpha", np.zeros(n, np.float32))
    atrp = wm.get("atrp", np.zeros(n, np.float32))
    prob1 = wm.get("prob_up_1d", np.zeros(n, np.float32))
    prob5 = wm.get("prob_up_5d", np.zeros(n, np.float32))
    prob_st = wm.get("prob_up_st_cross", np.zeros(n, np.float32))
    confluence = wm.get("confluence", np.zeros(n, np.float32))
    atr_mult = np.ones(n, np.float32)

    r2_current = _r_squared_matrix(Vn, 90)[:, -1].astype(np.float32)

    ohlc = _load_ohlc_pivots(market, sym_list, date_limit=80)
    if ohlc is not None:
        high_p, low_p, open_p = ohlc
        basket_ohlc = _compute_basket_ohlc(close, high_p, low_p, open_p, indices, weights)
        basket_ind = _compute_basket_indicators(basket_ohlc, period=14, multiplier=2.0)
        atr_signal = basket_ind["atr_signal"][:, -1].astype(np.int32)
        atr_stop = basket_ind["atr_stop"][:, -1].astype(np.float32)
        atr_value = basket_ind["atr_value"][:, -1].astype(np.float32)
        atr_streak = basket_ind["atr_streak"][:, -1].astype(np.float32)
        atr_cross_up = basket_ind["atr_crossed_above"][:, -1].astype(np.int32)
        atr_cross_down = basket_ind["atr_crossed_below"][:, -1].astype(np.int32)
        accel_a = basket_ind["accel_a"][:, -1].astype(np.float32)
        accel_base = basket_ind["accel_base"][:, -1].astype(np.float32)
        accel_signal = basket_ind["accel_signal"][:, -1].astype(np.int32)
        accel_cross_up = basket_ind["accel_crossed_up"][:, -1].astype(np.int32)
        accel_cross_down = basket_ind["accel_crossed_down"][:, -1].astype(np.int32)
        accel_streak = basket_ind["accel_streak"][:, -1].astype(np.float32)
        # Compute bars_at_side from full signal series (vectorized 2D)
        _st_bas_full = bars_at_side(basket_ind["atr_signal"].astype(np.int32))
        _ac_bas_full = bars_at_side(basket_ind["accel_signal"].astype(np.int32))
        st_bars_below = np.where(atr_signal == 1, _st_bas_full[:, -1], 0).astype(np.int32)
        st_bars_above = np.where(atr_signal == -1, _st_bas_full[:, -1], 0).astype(np.int32)
        accel_bars_below = np.where(accel_signal == 1, _ac_bas_full[:, -1], 0).astype(np.int32)
        accel_bars_above = np.where(accel_signal == -1, _ac_bas_full[:, -1], 0).astype(np.int32)
    else:
        atr_signal = _majority_signal(wm.get("atr_signal", np.zeros(n, np.float32)))
        accel_signal = _majority_signal(wm.get("accel_signal", np.zeros(n, np.float32)))
        atr_cross_up = _cross_flag(wm.get("atr_crossed_above", np.zeros(n, np.float32)))
        atr_cross_down = _cross_flag(wm.get("atr_crossed_below", np.zeros(n, np.float32)))
        accel_cross_up = _cross_flag(wm.get("accel_crossed_up", np.zeros(n, np.float32)))
        accel_cross_down = _cross_flag(wm.get("accel_crossed_down", np.zeros(n, np.float32)))
        atr_stop = wm.get("atr_stop", np.zeros(n, np.float32))
        atr_value = wm.get("atr_value", np.zeros(n, np.float32))
        atr_streak = np.round(wm.get("atr_streak", np.zeros(n, np.float32))).astype(np.float32)
        accel_a = wm.get("accel_a", np.zeros(n, np.float32))
        accel_base = wm.get("accel_base", np.zeros(n, np.float32))
        accel_streak = np.round(wm.get("accel_streak", np.zeros(n, np.float32))).astype(np.float32)
        st_bars_below = np.zeros(n, dtype=np.int32)
        st_bars_above = np.zeros(n, dtype=np.int32)
        accel_bars_below = np.zeros(n, dtype=np.int32)
        accel_bars_above = np.zeros(n, dtype=np.int32)

    ai_matrix = wm.get("ai_matrix", np.zeros(n, np.float32))
    ai_overall = ai_matrix
    ai_bias = np.where(ai_matrix > 55, "bullish", np.where(ai_matrix < 45, "bearish", "neutral")).astype(object)
    ai_vol = wm.get("ai_volume_profile_score", np.zeros(n, np.float32))
    ai_trend = wm.get("ai_trendline_score", np.zeros(n, np.float32))
    ai_sent = wm.get("ai_sentiment_score", np.zeros(n, np.float32))
    ai_tech = wm.get("ai_tech_score", np.zeros(n, np.float32))
    ai_mom = wm.get("ai_momentum_score", np.zeros(n, np.float32))
    ai_volsc = wm.get("ai_volume_score", np.zeros(n, np.float32))
    ai_evt = wm.get("ai_events_score", np.zeros(n, np.float32))
    ai_concl = np.where(ai_matrix > 60, "BUY", np.where(ai_matrix < 40, "SELL", "HOLD")).astype(object)

    now = datetime.utcnow().isoformat()
    conn = get_db(market)
    try:
        def _safe_int(v):
            try:
                f = float(v)
                return 0 if not np.isfinite(f) else int(f)
            except (TypeError, ValueError):
                return 0
        def _safe_float(v):
            try:
                f = float(v)
                return 0.0 if not np.isfinite(f) else f
            except (TypeError, ValueError):
                return 0.0
        rows = []
        for i in range(n):
            rows.append((
                sids[i], market, sids[i], "BASKET", "basket",
                _safe_float(price[i]), _safe_float(change_pct[i]), _safe_float(volume[i]), _safe_float(wa[i]),
                _safe_float(atrp[i]), _safe_int(streak[i]), _safe_int(atr_signal[i]), _safe_float(atr_stop[i]),
                _safe_float(atr_value[i]), _safe_int(atr_streak[i]), _safe_int(atr_cross_up[i]), _safe_int(atr_cross_down[i]),
                _safe_float(atr_mult[i]), _safe_float(next_day[i]), _safe_float(next_5d[i]), _safe_float(prob1[i]), _safe_float(prob5[i]), _safe_float(prob_st[i]),
                None, None, None, None, None, 0, 0,
                _safe_float(accel_a[i]), _safe_float(accel_base[i]), _safe_int(accel_signal[i]), _safe_int(accel_cross_up[i]),
                _safe_int(accel_cross_down[i]), _safe_int(accel_streak[i]), _safe_float(confluence[i]),
                _safe_float(ai_overall[i]), str(ai_bias[i]), _safe_float(ai_tech[i]), _safe_float(ai_mom[i]),
                _safe_float(ai_volsc[i]), _safe_float(ai_evt[i]), _safe_float(ai_vol[i]), _safe_float(ai_trend[i]),
                _safe_float(ai_sent[i]), str(ai_concl[i]), _safe_float(ai_matrix[i]), now,
                _safe_int(st_bars_below[i]), _safe_int(st_bars_above[i]),
                _safe_int(accel_bars_below[i]), _safe_int(accel_bars_above[i]),
                _safe_float(r2_current[i]),
            ))
        cols = ["string_id", "market", "name", "exchange", "asset_class", "price", "change_pct",
                "volume", "weighted_alpha", "atrp", "streak", "atr_signal", "atr_stop", "atr_value",
                "atr_streak", "atr_crossed_above", "atr_crossed_below", "atr_multiplier",
                "next_day_return", "next_5d_return", "prob_up_1d", "prob_up_5d", "prob_up_st_cross",
                "pre_price", "pre_change_pct", "post_price", "post_change_pct", "profit_status",
                "fractionable", "marginable", "accel_a", "accel_base", "accel_signal",
                "accel_crossed_up", "accel_crossed_down", "accel_streak", "confluence",
                "ai_overall_score", "ai_bias", "ai_tech_score", "ai_momentum_score", "ai_volume_score",
                "ai_events_score", "ai_volume_profile_score", "ai_trendline_score", "ai_sentiment_score",
                "ai_conclusion", "ai_matrix", "updated_at",
                "st_bars_below", "st_bars_above", "accel_bars_below", "accel_bars_above",
                "r_squared"]
        placeholders = ",".join(["?"] * len(cols))
        conn.execute(f"DELETE FROM string_screener_metrics WHERE market=?", (market,))
        for j in range(0, len(rows), 5000):
            conn.executemany(
                f"INSERT OR REPLACE INTO string_screener_metrics ({','.join(cols)}) "
                f"VALUES ({placeholders})", rows[j:j + 5000])
        conn.commit()
        logger.info(f"[{market}] current string metrics done: {n} in {time.time()-t0:.1f}s")
        return n
    finally:
        conn.close()


def _majority_signal(vec):
    return np.sign(vec).astype(np.int32)


def _cross_flag(vec):
    return (vec > 0.25).astype(np.int32)


def generate_long_short_strings(market="US", n=25000):
    """Generate long+short strings. Each has 5 long (highest WA) + 5 short (lowest WA).
    Only stocks, marginable, shortable, volume >= 100000.
    Total 10 stocks per string. 60/40 allocation ensures positive initial basket value:
    $600 long (120/stock) + -$400 short (-80/stock) = $200 net initial."""
    ALLOCATION = 1000.0
    LONG_PCT = 0.60
    SHORT_PCT = 0.40
    LONG_N = 5
    SHORT_N = 5
    TARGET_STOCKS = LONG_N + SHORT_N
    conn = get_db(market)
    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM string_universe WHERE market=? AND string_id LIKE 'LS%'",
            (market,)).fetchone()[0]
        if existing >= n:
            logger.info(f"[{market}] ls_string_universe already has {existing} strings; skipping")
            return existing

        conn.execute("DELETE FROM string_constituents WHERE string_id IN "
                     "(SELECT string_id FROM string_universe WHERE market=? AND string_id LIKE 'LS%')",
                     (market,))
        conn.execute("DELETE FROM string_universe WHERE market=? AND string_id LIKE 'LS%'", (market,))
        conn.commit()

        syms = [r[0] for r in conn.execute(
            "SELECT a.symbol FROM assets a JOIN stats s ON s.symbol=a.symbol "
            "WHERE a.status='active' AND a.tradable=1 "
            "AND LOWER(COALESCE(a.asset_class,'')) = 'stock' "
            "AND COALESCE(a.marginable,0) = 1 "
            "AND COALESCE(a.shortable,0) = 1 "
            "AND COALESCE(s.volume,0) >= 100000 "
            "AND COALESCE(s.price,0) > 0").fetchall()]

        if len(syms) < TARGET_STOCKS * 2:
            logger.warning(f"[{market}] too few marginable+shortable symbols ({len(syms)})")
            return 0

        wa_rows = conn.execute(
            f"SELECT symbol, weighted_alpha, price FROM stats WHERE symbol IN ({','.join('?' * len(syms))})",
            syms).fetchall()
        wa_map = {r[0]: float(r[1] or 0) for r in wa_rows}
        price_map = {r[0]: float(r[2] or 0) for r in wa_rows}

        frac_rows = conn.execute(
            f"SELECT symbol, fractionable FROM assets WHERE symbol IN ({','.join('?' * len(syms))})",
            syms).fetchall()
        frac_map = {r[0]: bool(r[1]) for r in frac_rows}

        scored = [(s, wa_map.get(s, 0)) for s in syms if price_map.get(s, 0) > 0]
        scored.sort(key=lambda x: x[1], reverse=True)

        half = len(scored) // 2
        long_pool = scored[:half]
        short_pool = scored[half:]

        rng = np.random.default_rng(20240710)
        start = conn.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(string_id,3) AS INTEGER)),0) "
            "FROM string_universe WHERE string_id LIKE 'LS%'").fetchone()[0]
        count = 0
        batch_univ = []
        batch_cons = []

        long_per_stock = (ALLOCATION * LONG_PCT) / LONG_N
        short_per_stock = (ALLOCATION * SHORT_PCT) / SHORT_N

        for i in range(start + 1, start + 1 + n):
            long_picked = [long_pool[j] for j in rng.choice(len(long_pool), size=LONG_N, replace=False)]
            short_picked = [short_pool[j] for j in rng.choice(len(short_pool), size=SHORT_N, replace=False)]

            weights = np.zeros(TARGET_STOCKS)
            picked = []
            for j, (sym, _) in enumerate(long_picked):
                picked.append(sym)
                price = price_map[sym]
                raw_w = long_per_stock / price
                weights[j] = round(raw_w, 4)
            for j, (sym, _) in enumerate(short_picked):
                picked.append(sym)
                price = price_map[sym]
                raw_w = short_per_stock / price
                weights[LONG_N + j] = -round(raw_w, 4)

            weights = np.where(weights == 0, 0.001, weights)
            sid = f"LS{i:06d}"
            # Expression format: ticker*qty + ticker*qty - ticker*qty ... (minus = short)
            long_part = " + ".join(f"{picked[j]}*{abs(weights[j]):g}" for j in range(LONG_N))
            short_part = " - ".join(f"{picked[j]}*{abs(weights[j]):g}" for j in range(LONG_N, TARGET_STOCKS))
            expr = f"{long_part} - {short_part}"
            batch_univ.append((sid, market, TARGET_STOCKS, expr, datetime.utcnow().isoformat(), 1))
            for j in range(TARGET_STOCKS):
                batch_cons.append((sid, str(picked[j]), float(weights[j])))
            count += 1
            if len(batch_univ) >= 500:
                conn.executemany(
                    "INSERT OR REPLACE INTO string_universe "
                    "(string_id, market, num_stocks, expression, created_at, active) "
                    "VALUES (?,?,?,?,?,?)", batch_univ)
                conn.executemany(
                    "INSERT OR REPLACE INTO string_constituents (string_id, symbol, weight) "
                    "VALUES (?,?,?)", batch_cons)
                conn.commit()
                batch_univ.clear(); batch_cons.clear()
        if batch_univ:
            conn.executemany(
                "INSERT OR REPLACE INTO string_universe "
                "(string_id, market, num_stocks, expression, created_at, active) "
                "VALUES (?,?,?,?,?,?)", batch_univ)
            conn.executemany(
                "INSERT OR REPLACE INTO string_constituents (string_id, symbol, weight) "
                "VALUES (?,?,?)", batch_cons)
            conn.commit()
        logger.info(f"[{market}] generated {count} long+short strings")
        return count
    finally:
        conn.close()


def update_historical_string_screener(market="US", only_strings=None, force_rebuild=False,
                                       date_limit=None, progress_callback=None, only_latest=False,
                                       string_id_like=None):
    """Compute historical_string_screener for all dates.

    SPEED v2 optimizations:
    1. Load raw per-symbol metrics from historical_screener ONCE, not per chunk.
    2. Per-chunk only does fast numpy gather+einsum projection.
    3. Inner date loop builds all rows at once via numpy slicing (no per-date .tolist()).
    """
    t0 = time.time()
    sids, sym_list, indices, weights = _load_composition(market, only_strings)
    if not sids:
        logger.info(f"[{market}] no strings")
        return 0

    if string_id_like:
        import fnmatch
        fn_pattern = string_id_like.replace('%', '*')
        mask = [fnmatch.fnmatch(s, fn_pattern) for s in sids]
        keep = np.array(mask)
        sids = [s for s, m in zip(sids, mask) if m]
        indices = indices[keep]
        weights = weights[keep]
        if not sids:
            logger.info(f"[{market}] no strings matching {string_id_like}")
            return 0
        logger.info(f"[{market}] filtered to {len(sids)} strings matching {string_id_like}")

    sym_list, dates, close_pivot = _load_close_pivot(market, sym_list)
    logger.info(f"[{market}] close_pivot loaded: {close_pivot.shape}, dates={len(dates)}, sids={len(sids)}, sym_list={len(sym_list)}")
    if close_pivot.shape[1] == 0:
        logger.warning(f"[{market}] no dates in close_pivot")
        return 0

    if date_limit is not None:
        dates = dates[-date_limit:]
        close_pivot = close_pivot[:, -date_limit:]

    if only_latest and len(dates) > 50:
        dates = dates[-50:]
        close_pivot = close_pivot[:, -50:]
        logger.info(f"[{market}] only_latest mode: trimmed to last {len(dates)} dates for speed")

    n_dates = len(dates)
    n = len(sids)
    logger.info(f"[{market}] computing basket values: {n} strings x {n_dates} dates")

    ohlc = _load_ohlc_pivots(market, sym_list)
    if ohlc is not None:
        high_pivot, low_pivot, open_pivot = ohlc
        if date_limit is not None:
            high_pivot = high_pivot[:, -date_limit:]
            low_pivot = low_pivot[:, -date_limit:]
            open_pivot = open_pivot[:, -date_limit:]
        if only_latest and high_pivot.shape[1] > n_dates:
            high_pivot = high_pivot[:, -n_dates:]
            low_pivot = low_pivot[:, -n_dates:]
            open_pivot = open_pivot[:, -n_dates:]
    else:
        logger.warning(f"[{market}] no OHLC pivots cached; falling back to averaged signals (inaccurate)")

    conn = get_db(market)
    try:
        if only_strings is None and force_rebuild:
            conn.execute("DROP TABLE IF EXISTS historical_string_screener")
            conn.execute("""CREATE TABLE historical_string_screener (
                string_id TEXT, date TEXT, name TEXT, price REAL, change_pct REAL,
                volume REAL, weighted_alpha REAL, atrp REAL, streak INTEGER,
                atr_signal INTEGER, atr_stop REAL, atr_value REAL, atr_streak INTEGER,
                atr_crossed_above INTEGER, atr_crossed_below INTEGER, atr_multiplier REAL,
                next_day_return REAL, next_5d_return REAL, prob_up_1d REAL, prob_up_5d REAL,
                prob_up_st_cross REAL,
                pre_price REAL, pre_change_pct REAL, post_price REAL, post_change_pct REAL,
                accel_a REAL, accel_base REAL, accel_signal INTEGER, accel_crossed_up INTEGER,
                accel_crossed_down INTEGER, accel_streak INTEGER, confluence REAL,
                ai_overall_score REAL, ai_bias TEXT, ai_tech_score REAL, ai_momentum_score REAL,
                ai_volume_score REAL, ai_events_score REAL, ai_volume_profile_score REAL,
                ai_trendline_score REAL, ai_sentiment_score REAL, ai_conclusion TEXT, ai_matrix REAL,
                st_bars_below INTEGER DEFAULT 0, st_bars_above INTEGER DEFAULT 0,
                accel_bars_below INTEGER DEFAULT 0, accel_bars_above INTEGER DEFAULT 0,
                r_squared REAL DEFAULT 0,
                PRIMARY KEY (string_id, date))""")
            conn.commit()
            logger.info(f"[{market}] historical_string_screener table recreated (indexes deferred)")

        cols = ["string_id", "date", "name", "price", "change_pct", "volume", "weighted_alpha",
                "atrp", "streak", "atr_signal", "atr_stop", "atr_value", "atr_streak",
                "atr_crossed_above", "atr_crossed_below", "atr_multiplier", "next_day_return",
                "next_5d_return", "prob_up_1d", "prob_up_5d", "prob_up_st_cross", "pre_price", "pre_change_pct",
                "post_price", "post_change_pct", "accel_a", "accel_base", "accel_signal",
                "accel_crossed_up", "accel_crossed_down", "accel_streak", "confluence",
                "ai_overall_score", "ai_bias", "ai_tech_score", "ai_momentum_score", "ai_volume_score",
                "ai_events_score", "ai_volume_profile_score", "ai_trendline_score", "ai_sentiment_score",
                "ai_conclusion", "ai_matrix",
                "st_bars_below", "st_bars_above", "accel_bars_below", "accel_bars_above",
                "r_squared"]
        placeholders_str = ",".join(["?"] * len(cols))
        insert_sql = f"INSERT OR REPLACE INTO historical_string_screener ({','.join(cols)}) VALUES ({placeholders_str})"

        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA cache_size=-2000000")
        conn.execute("PRAGMA locking_mode=EXCLUSIVE")

        sids_list = list(sids)

        hist_dates_to_load = [dates[-1]] if only_latest else dates

        # OPTIMIZATION 1: Load raw per-symbol metrics ONCE for all dates.
        # Cached to disk (.cache/raw_metrics_{market}_{sym_hash}.npz) so crash restart skips the load.
        used_sym_indices = np.unique(indices)
        needed_syms = [sym_list[i] for i in used_sym_indices]

        # Bug 4: Key cache by hash of needed symbols, not just market.
        # Prevents stale data when called for different string types (S vs LEV vs LS).
        import hashlib
        sym_hash = hashlib.md5(",".join(sorted(needed_syms)).encode()).hexdigest()[:12]
        cache_path = os.path.join(_CACHE_DIR, f"raw_metrics_{market}_{sym_hash}.npz")
        raw_metrics = None
        if os.path.exists(cache_path):
            try:
                _t_load = time.time()
                loaded = np.load(cache_path, allow_pickle=True)
                raw_metrics = {k: loaded[k] for k in loaded.files}
                cache_sym_dim = raw_metrics[loaded.files[0]].shape[0] if loaded.files else 0
                if cache_sym_dim < len(needed_syms):
                    logger.info(f"[{market}] cache has {cache_sym_dim} symbols but {len(needed_syms)} needed; rebuilding")
                    raw_metrics = None
                else:
                    logger.info(f"[{market}] raw metrics loaded from cache in {time.time()-_t_load:.1f}s ({len(raw_metrics)} columns)")
            except Exception as e:
                logger.warning(f"[{market}] cache load failed: {e}; re-loading from DB")
                raw_metrics = None
        if raw_metrics is None:
            logger.info(f"[{market}] loading raw historical metrics ONCE for {len(needed_syms)}/{len(sym_list)} symbols x {len(hist_dates_to_load)} dates")
            _t_load = time.time()
            raw_metrics = _load_raw_hist_metrics(conn, needed_syms, hist_dates_to_load)
            logger.info(f"[{market}] raw metrics loaded in {time.time()-_t_load:.1f}s ({len(raw_metrics)} columns)")
            try:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                # Remove existing cache before saving
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                np.savez_compressed(cache_path, **raw_metrics)
                logger.info(f"[{market}] raw metrics cached to {cache_path}")
                # Clean up other raw_metrics caches for this market
                for f in os.listdir(_CACHE_DIR):
                    if (f.startswith(f"raw_metrics_{market}_")
                            and f.endswith(".npz")
                            and f != os.path.basename(cache_path)):
                        try:
                            os.remove(os.path.join(_CACHE_DIR, f))
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"[{market}] failed to cache raw metrics: {e}")

        # Map needed_syms indices back to sym_list indices for einsum
        needed_to_full = {i: full_i for full_i, i in enumerate(used_sym_indices)}
        # Create remapped indices: sym_list index -> needed_syms index
        full_to_needed = -np.ones(len(sym_list), dtype=np.int32)
        for needed_i, full_i in enumerate(used_sym_indices):
            full_to_needed[full_i] = needed_i
        remapped_indices = full_to_needed[indices]

        # Pre-compute Wn once for the full weight matrix
        weight_sums = np.abs(weights).sum(axis=1, keepdims=True)
        weight_sums[weight_sums == 0] = 1.0
        Wn_full = np.abs(weights) / weight_sums

        STR_CHUNK = 3000
        total_rows = 0

        for sc_start in range(0, n, STR_CHUNK):
            sc_end = min(sc_start + STR_CHUNK, n)
            sc_sids = sids_list[sc_start:sc_end]
            sc_indices = remapped_indices[sc_start:sc_end]
            sc_indices_full = indices[sc_start:sc_end]
            sc_weights = weights[sc_start:sc_end]
            sc_Wn = Wn_full[sc_start:sc_end]
            sc_n = sc_end - sc_start
            logger.info(f"[{market}] string chunk {sc_start}-{sc_end}/{n}")

            V = _gather_einsum(close_pivot, sc_indices_full, sc_weights)
            series = _series_metrics(V)
            Vn = series["V"]
            ret = series["ret"]
            streak_full = series["streak_series"]
            r2_full = _r_squared_matrix(Vn, 90)

            next_day_full = np.zeros((sc_n, n_dates), dtype=np.float32)
            next_day_full[:, :-1] = ret[:, 1:]
            next_5d_full = np.zeros((sc_n, n_dates), dtype=np.float32)
            for t in range(n_dates - 5):
                next_5d_full[:, t] = ((Vn[:, t+5] - Vn[:, t]) / np.where(Vn[:, t] == 0, 1e-9, Vn[:, t])) * 100.0
            price_full = Vn

            # OPTIMIZATION 2: Project raw metrics to basket-level via einsum (fast, no SQL)
            all_wm = _project_raw_to_basket(raw_metrics, sc_indices, sc_weights, sc_Wn)

            # Compute indicators for this chunk (not all 50K strings — avoids OOM)
            if ohlc is not None:
                chunk_basket_ohlc = _compute_basket_ohlc(close_pivot, high_pivot, low_pivot, open_pivot, sc_indices_full, sc_weights)
                chunk_basket_ind = _compute_basket_indicators(chunk_basket_ohlc, period=14, multiplier=2.0)
                atr_sig_full = chunk_basket_ind["atr_signal"].astype(np.int32)
                atr_cu_full = chunk_basket_ind["atr_crossed_above"].astype(np.int32)
                atr_cd_full = chunk_basket_ind["atr_crossed_below"].astype(np.int32)
                acc_sig_full = chunk_basket_ind["accel_signal"].astype(np.int32)
                acc_cu_full = chunk_basket_ind["accel_crossed_up"].astype(np.int32)
                acc_cd_full = chunk_basket_ind["accel_crossed_down"].astype(np.int32)
                basket_ind = chunk_basket_ind
                # Compute bars_at_side for full signal series
                n_dates = atr_sig_full.shape[1]
                st_bas_full = np.zeros((sc_n, n_dates), dtype=np.int32)
                ac_bas_full = np.zeros((sc_n, n_dates), dtype=np.int32)
                for si in range(sc_n):
                    st_bas_full[si] = bars_at_side(atr_sig_full[si])
                    ac_bas_full[si] = bars_at_side(acc_sig_full[si])
                del chunk_basket_ohlc
            else:
                _z = np.zeros((sc_n, n_dates), np.float32)
                atr_sig_full = np.sign(all_wm.get("atr_signal", _z)).astype(np.int32)
                acc_sig_full = np.sign(all_wm.get("accel_signal", _z)).astype(np.int32)
                atr_cu_full = (all_wm.get("atr_crossed_above", _z) > 0.25).astype(np.int32)
                atr_cd_full = (all_wm.get("atr_crossed_below", _z) > 0.25).astype(np.int32)
                acc_cu_full = (all_wm.get("accel_crossed_up", _z) > 0.25).astype(np.int32)
                acc_cd_full = (all_wm.get("accel_crossed_down", _z) > 0.25).astype(np.int32)
                basket_ind = None
                # Compute bars_at_side from projected signals
                n_dates = atr_sig_full.shape[1]
                st_bas_full = np.zeros((sc_n, n_dates), dtype=np.int32)
                ac_bas_full = np.zeros((sc_n, n_dates), dtype=np.int32)
                for si in range(sc_n):
                    st_bas_full[si] = bars_at_side(atr_sig_full[si])
                    ac_bas_full[si] = bars_at_side(acc_sig_full[si])

            ai_m_full = all_wm.get("ai_matrix", np.zeros((sc_n, n_dates), np.float32))
            ai_concl_full = np.where(ai_m_full > 60, "BUY", np.where(ai_m_full < 40, "SELL", "HOLD"))
            ai_bias_full = np.where(ai_m_full > 55, "bullish", np.where(ai_m_full < 45, "bearish", "neutral"))

            # OPTIMIZATION 3: Build all rows at once with numpy, avoid per-date Python loop
            # Pre-slice basket_ind arrays once for this chunk
            if ohlc is not None and basket_ind is not None:
                bi_atr_stop = basket_ind["atr_stop"]
                bi_atr_val = basket_ind["atr_value"]
                bi_atr_strk = basket_ind["atr_streak"]
                bi_ac_a = basket_ind["accel_a"]
                bi_ac_base = basket_ind["accel_base"]
                bi_ac_strk = basket_ind["accel_streak"]
            else:
                bi_atr_stop = all_wm.get("atr_stop", np.zeros((sc_n, n_dates), np.float32))
                bi_atr_val = all_wm.get("atr_value", np.zeros((sc_n, n_dates), np.float32))
                bi_atr_strk = all_wm.get("atr_streak", np.zeros((sc_n, n_dates), np.float32))
                bi_ac_a = all_wm.get("accel_a", np.zeros((sc_n, n_dates), np.float32))
                bi_ac_base = all_wm.get("accel_base", np.zeros((sc_n, n_dates), np.float32))
                bi_ac_strk = all_wm.get("accel_streak", np.zeros((sc_n, n_dates), np.float32))

            _z = np.zeros((sc_n, n_dates), np.float32)
            wm_vol = all_wm.get("volume", _z)
            wm_wa = all_wm.get("weighted_alpha", _z)
            wm_atrp = all_wm.get("atrp", _z)
            wm_p1d = all_wm.get("prob_up_1d", _z)
            wm_p5d = all_wm.get("prob_up_5d", _z)
            wm_pst = all_wm.get("prob_up_st_cross", _z)
            wm_conf = all_wm.get("confluence", _z)
            wm_ai_tech = all_wm.get("ai_tech_score", _z)
            wm_ai_mom = all_wm.get("ai_momentum_score", _z)
            wm_ai_vol = all_wm.get("ai_volume_score", _z)
            wm_ai_ev = all_wm.get("ai_events_score", _z)
            wm_ai_vp = all_wm.get("ai_volume_profile_score", _z)
            wm_ai_tl = all_wm.get("ai_trendline_score", _z)
            wm_ai_sent = all_wm.get("ai_sentiment_score", _z)

            def _flat(mat, d0, d1):
                """Slice (sc_n, d0:d1) and interleave to (sc_n*cd_len,): d0_s0..d0_sN, d1_s0..d1_sN."""
                return mat[:, d0:d1].T.reshape(-1)

            if only_latest:
                def _flat_last(mat):
                    return mat[:, -1].copy()

            if only_latest:
                loop_range = [n_dates - 1]
            else:
                chunk = 200
                loop_range = range(0, n_dates, chunk)

            for d0 in loop_range:
                d1 = min(d0 + chunk, n_dates) if not only_latest else d0 + 1
                cd_len = d1 - d0
                _t_chunk = time.time()

                if only_latest:
                    n_rows = sc_n
                    all_sids = list(sc_sids)
                    all_dates = [dates[-1]] * sc_n
                    _fl = _flat_last

                    price_rows = _fl(price_full).tolist()
                    ret_rows = _fl(ret).tolist()
                    vol_rows = _fl(wm_vol).tolist()
                    wa_rows = _fl(wm_wa).tolist()
                    atrp_rows = _fl(wm_atrp).tolist()
                    streak_rows = np.nan_to_num(_fl(streak_full), nan=0).astype(int).tolist()
                    atr_sig_rows = _fl(atr_sig_full).astype(int).tolist()
                    atr_stop_rows = _fl(bi_atr_stop).tolist()
                    atr_val_rows = _fl(bi_atr_val).tolist()
                    atr_strk_rows = np.nan_to_num(np.round(_fl(bi_atr_strk)), nan=0).astype(int).tolist()
                    atr_cu_rows = _fl(atr_cu_full).astype(int).tolist()
                    atr_cd_rows = _fl(atr_cd_full).astype(int).tolist()
                    nd_rows = _fl(next_day_full).tolist()
                    n5d_rows = _fl(next_5d_full).tolist()
                    p1d_rows = _fl(wm_p1d).tolist()
                    p5d_rows = _fl(wm_p5d).tolist()
                    pst_rows = _fl(wm_pst).tolist()
                    ac_a_rows = _fl(bi_ac_a).tolist()
                    ac_base_rows = _fl(bi_ac_base).tolist()
                    ac_sig_rows = _fl(acc_sig_full).astype(int).tolist()
                    ac_cu_rows = _fl(acc_cu_full).astype(int).tolist()
                    ac_cd_rows = _fl(acc_cd_full).astype(int).tolist()
                    ac_strk_rows = np.nan_to_num(np.round(_fl(bi_ac_strk)), nan=0).astype(int).tolist()
                    conf_rows = _fl(wm_conf).tolist()
                    ai_m_rows = _fl(ai_m_full).tolist()
                    r2_rows = _fl(r2_full).tolist()
                    ones_rows = [1.0] * sc_n
                    none_rows = [None] * sc_n
                    ai_bias_rows = [str(ai_bias_full[-1])] * sc_n
                    ai_concl_rows = [str(ai_concl_full[-1])] * sc_n
                    ai_tech_rows = _fl(wm_ai_tech).tolist()
                    ai_mom_rows = _fl(wm_ai_mom).tolist()
                    ai_vol_rows = _fl(wm_ai_vol).tolist()
                    ai_ev_rows = _fl(wm_ai_ev).tolist()
                    ai_vp_rows = _fl(wm_ai_vp).tolist()
                    ai_tl_rows = _fl(wm_ai_tl).tolist()
                    ai_sent_rows = _fl(wm_ai_sent).tolist()
                else:
                    n_rows = cd_len * sc_n
                    all_sids = list(sc_sids) * cd_len
                    all_dates = []
                    for dt in dates[d0:d1]:
                        all_dates.extend([dt] * sc_n)

                    price_rows = _flat(price_full, d0, d1).tolist()
                    ret_rows = _flat(ret, d0, d1).tolist()
                    vol_rows = _flat(wm_vol, d0, d1).tolist()
                    wa_rows = _flat(wm_wa, d0, d1).tolist()
                    atrp_rows = _flat(wm_atrp, d0, d1).tolist()
                    streak_rows = np.nan_to_num(_flat(streak_full, d0, d1), nan=0).astype(int).tolist()
                    atr_sig_rows = _flat(atr_sig_full, d0, d1).astype(int).tolist()
                    atr_stop_rows = _flat(bi_atr_stop, d0, d1).tolist()
                    atr_val_rows = _flat(bi_atr_val, d0, d1).tolist()
                    atr_strk_rows = np.nan_to_num(np.round(_flat(bi_atr_strk, d0, d1)), nan=0).astype(int).tolist()
                    atr_cu_rows = _flat(atr_cu_full, d0, d1).astype(int).tolist()
                    atr_cd_rows = _flat(atr_cd_full, d0, d1).astype(int).tolist()
                    nd_rows = _flat(next_day_full, d0, d1).tolist()
                    n5d_rows = _flat(next_5d_full, d0, d1).tolist()
                    p1d_rows = _flat(wm_p1d, d0, d1).tolist()
                    p5d_rows = _flat(wm_p5d, d0, d1).tolist()
                    pst_rows = _flat(wm_pst, d0, d1).tolist()
                    ac_a_rows = _flat(bi_ac_a, d0, d1).tolist()
                    ac_base_rows = _flat(bi_ac_base, d0, d1).tolist()
                    ac_sig_rows = _flat(acc_sig_full, d0, d1).astype(int).tolist()
                    ac_cu_rows = _flat(acc_cu_full, d0, d1).astype(int).tolist()
                    ac_cd_rows = _flat(acc_cd_full, d0, d1).astype(int).tolist()
                    ac_strk_rows = np.nan_to_num(np.round(_flat(bi_ac_strk, d0, d1)), nan=0).astype(int).tolist()
                    conf_rows = _flat(wm_conf, d0, d1).tolist()
                    ai_m_rows = _flat(ai_m_full, d0, d1).tolist()
                    r2_rows = _flat(r2_full, d0, d1).tolist()
                    ones_rows = [1.0] * n_rows
                    none_rows = [None] * n_rows
                    ai_bias_block = ai_bias_full[:, d0:d1]
                    ai_bias_rows = list(ai_bias_block.T.reshape(-1))
                    ai_concl_block = ai_concl_full[:, d0:d1]
                    ai_concl_rows = list(ai_concl_block.T.reshape(-1))
                    ai_tech_rows = _flat(wm_ai_tech, d0, d1).tolist()
                    ai_mom_rows = _flat(wm_ai_mom, d0, d1).tolist()
                    ai_vol_rows = _flat(wm_ai_vol, d0, d1).tolist()
                    ai_ev_rows = _flat(wm_ai_ev, d0, d1).tolist()
                    ai_vp_rows = _flat(wm_ai_vp, d0, d1).tolist()
                    ai_tl_rows = _flat(wm_ai_tl, d0, d1).tolist()
                    ai_sent_rows = _flat(wm_ai_sent, d0, d1).tolist()

                all_batch = list(zip(
                    all_sids, all_dates, all_sids,
                    price_rows, ret_rows, vol_rows, wa_rows, atrp_rows, streak_rows,
                    atr_sig_rows, atr_stop_rows, atr_val_rows, atr_strk_rows,
                    atr_cu_rows, atr_cd_rows, ones_rows,
                    nd_rows, n5d_rows, p1d_rows, p5d_rows, pst_rows,
                    none_rows, none_rows, none_rows, none_rows,
                    ac_a_rows, ac_base_rows, ac_sig_rows, ac_cu_rows, ac_cd_rows, ac_strk_rows,
                    conf_rows,
                    ai_m_rows, ai_bias_rows,
                    ai_tech_rows, ai_mom_rows, ai_vol_rows, ai_ev_rows,
                    ai_vp_rows, ai_tl_rows, ai_sent_rows,
                    ai_concl_rows, ai_m_rows,
                ))

                # Add bars_at_side columns for this date range
                if only_latest:
                    st_bas_last = st_bas_full[:, -1]
                    ac_bas_last = ac_bas_full[:, -1]
                    st_bb_rows = np.where(np.array(atr_sig_rows) == 1, st_bas_last, 0).astype(int).tolist()
                    st_ba_rows = np.where(np.array(atr_sig_rows) == -1, st_bas_last, 0).astype(int).tolist()
                    ac_bb_rows = np.where(np.array(ac_sig_rows) == 1, ac_bas_last, 0).astype(int).tolist()
                    ac_ba_rows = np.where(np.array(ac_sig_rows) == -1, ac_bas_last, 0).astype(int).tolist()
                else:
                    st_bas_chunk = _flat(st_bas_full, d0, d1).astype(int)
                    ac_bas_chunk = _flat(ac_bas_full, d0, d1).astype(int)
                    sig_chunk = np.array(atr_sig_rows)
                    acsig_chunk = np.array(ac_sig_rows)
                    st_bb_rows = np.where(sig_chunk == 1, st_bas_chunk, 0).tolist()
                    st_ba_rows = np.where(sig_chunk == -1, st_bas_chunk, 0).tolist()
                    ac_bb_rows = np.where(acsig_chunk == 1, ac_bas_chunk, 0).tolist()
                    ac_ba_rows = np.where(acsig_chunk == -1, ac_bas_chunk, 0).tolist()
                # Append bars_at_side values to each tuple
                all_batch = [row + (st_bb, st_ba, ac_bb, ac_ba, r2v) for row, st_bb, st_ba, ac_bb, ac_ba, r2v in
                             zip(all_batch, st_bb_rows, st_ba_rows, ac_bb_rows, ac_ba_rows, r2_rows)]

                for bi in range(0, len(all_batch), 250000):
                    conn.executemany(insert_sql, all_batch[bi:bi+250000])
                conn.commit()
                total_rows += len(all_batch)
                _elapsed = time.time() - t0
                _eta = (_elapsed / max(sc_end, 1)) * (n - sc_end) if sc_end > 0 else 0
                logger.info(f"[{market}] chunk {sc_start}-{sc_end}, dates {d0}-{d1}: {len(all_batch):,} rows in {time.time()-_t_chunk:.1f}s (total {total_rows:,}, ETA {int(_eta)}s)")
                if progress_callback:
                    progress_callback(int(sc_end / n * 100), f"Historical strings: {sc_end}/{n} strings, {total_rows:,} rows")

            del V, series, Vn, ret, streak_full, next_day_full, next_5d_full, price_full
            del ai_m_full, ai_concl_full, ai_bias_full, all_wm
            if ohlc is not None:
                del chunk_basket_ind, atr_sig_full, atr_cu_full, atr_cd_full, acc_sig_full, acc_cu_full, acc_cd_full, basket_ind

        del raw_metrics, Wn_full
        logger.info(f"[{market}] historical string screener done: {total_rows} rows in {time.time()-t0:.1f}s")
        logger.info(f"[{market}] creating indexes...")
        _t_idx = time.time()
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hs_sym_date ON historical_string_screener (string_id, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hs_date ON historical_string_screener (date)")
        conn.commit()
        logger.info(f"[{market}] indexes created in {time.time()-_t_idx:.1f}s")
        return total_rows
    finally:
        conn.close()


HIST_TEXT_COLS = {"ai_bias", "ai_conclusion"}


def _load_hist_metrics_chunk(conn, market, sym_list, chunk_dates, W=None, Wn=None, indices=None, weights=None):
    """Load ALL metric columns in ONE query (batched by 500 dates for SQLite limit), project via gather+einsum.
    Optimized: uses pd.read_sql_query for bulk load instead of per-row Python loops."""
    import pandas as pd
    num_cols = [c for c in HIST_COLS if c not in HIST_TEXT_COLS]
    cols_sql = ", ".join(num_cols)
    n_sym = len(sym_list)
    n_dates = len(chunk_dates)
    raw = {c: np.zeros((n_sym, n_dates), dtype=np.float32) for c in num_cols}
    date_idx = {d: i for i, d in enumerate(chunk_dates)}
    sym_idx = {s: i for i, s in enumerate(sym_list)}

    sql_batch = 500
    sym_batch = 400  # SQLite 999-variable limit: 400 symbols + 2 dates = 402 params
    all_dfs = []
    for sb in range(0, len(chunk_dates), sql_batch):
        batch_dates = chunk_dates[sb:sb+sql_batch]
        min_date = batch_dates[0]
        max_date = batch_dates[-1]
        for si in range(0, len(sym_list), sym_batch):
            batch_syms = sym_list[si:si+sym_batch]
            placeholders = ",".join(["?"] * len(batch_syms))
            q = (f"SELECT symbol, date, {cols_sql} FROM historical_screener "
                 f"WHERE date >= ? AND date <= ? AND symbol IN ({placeholders})")
            df = pd.read_sql_query(q, conn, params=[min_date, max_date] + list(batch_syms))
            all_dfs.append(df)
            del df

    if not all_dfs:
        out = {c: np.zeros((n_sym, n_dates), dtype=np.float32) for c in num_cols}
        return out

    rows_df = pd.concat(all_dfs, ignore_index=True)
    del all_dfs

    si = rows_df["symbol"].map(sym_idx).fillna(-1).astype(np.int32).values
    di = rows_df["date"].map(date_idx).fillna(-1).astype(np.int32).values
    valid = (si >= 0) & (di >= 0)
    si_v = si[valid]
    di_v = di[valid]

    for col in num_cols:
        if col in rows_df.columns:
            vals = rows_df[col].to_numpy(dtype=np.float32, na_value=np.nan)
        else:
            vals = np.zeros(len(rows_df), dtype=np.float32)
        vals_v = vals[valid]
        mask = np.isfinite(vals_v)
        raw[col][si_v[mask], di_v[mask]] = vals_v[mask]

    del rows_df

    out = {}
    if indices is not None and weights is not None:
        weight_sums = weights.sum(axis=1, keepdims=True)
        weight_sums[weight_sums == 0] = 1.0
        Wn_local = weights / weight_sums
        for col in num_cols:
            vals = raw[col]
            gathered = vals[indices]
            if col == "volume":
                out[col] = np.einsum('bij,bi->bj', gathered, weights)
            else:
                out[col] = np.einsum('bij,bi->bj', gathered, Wn_local)
    elif W is not None:
        weight_sums = np.array(W.sum(axis=1)).ravel().astype(np.float32)
        weight_sums[weight_sums == 0] = 1.0
        Wn_mat = W / weight_sums[:, None]
        for col in num_cols:
            vals = raw[col]
            if col == "volume":
                out[col] = W @ vals
            else:
                out[col] = Wn_mat @ vals
    return out


def _load_raw_hist_metrics(conn, sym_list, hist_dates):
    """Load raw per-symbol metrics from historical_screener ONCE.
    Returns dict of column_name -> np.array(n_sym, n_dates) float32.

    Uses pandas read_sql (C-optimized) with needed-symbols filter.
    """
    import pandas as pd
    num_cols = [c for c in HIST_COLS if c not in HIST_TEXT_COLS]
    cols_sql = ", ".join(num_cols)
    n_sym = len(sym_list)
    n_dates = len(hist_dates)
    raw = {c: np.zeros((n_sym, n_dates), dtype=np.float32) for c in num_cols}
    date_idx = {d: i for i, d in enumerate(hist_dates)}
    sym_idx = {s: i for i, s in enumerate(sym_list)}

    sym_batch = 400
    date_batch = 500
    total_fetched = 0

    for sb in range(0, len(hist_dates), date_batch):
        batch_dates = hist_dates[sb:sb+date_batch]
        min_date = batch_dates[0]
        max_date = batch_dates[-1]
        for si in range(0, len(sym_list), sym_batch):
            batch_syms = sym_list[si:si+sym_batch]
            placeholders = ",".join(["?"] * len(batch_syms))
            q = (f"SELECT symbol, date, {cols_sql} FROM historical_screener "
                 f"WHERE date >= ? AND date <= ? AND symbol IN ({placeholders})")
            df = pd.read_sql_query(q, conn, params=[min_date, max_date] + list(batch_syms))
            if df.empty:
                continue
            total_fetched += len(df)

            si_arr = df["symbol"].map(sym_idx).fillna(-1).astype(np.int32).values
            di_arr = df["date"].map(date_idx).fillna(-1).astype(np.int32).values
            valid = (si_arr >= 0) & (di_arr >= 0)
            si_v = si_arr[valid]
            di_v = di_arr[valid]

            for col in num_cols:
                if col in df.columns:
                    vals = df[col].to_numpy(dtype=np.float32, na_value=np.nan)
                else:
                    vals = np.zeros(len(df), dtype=np.float32)
                vals_v = vals[valid]
                mask = np.isfinite(vals_v)
                raw[col][si_v[mask], di_v[mask]] = vals_v[mask]

            del df

    logger.info(f"  Fetched {total_fetched:,} rows from historical_screener")
    return raw


def _project_raw_to_basket(raw_metrics, indices, weights, Wn):
    """Project raw per-symbol metrics to basket-level via gather+einsum.
    Same math as _load_hist_metrics_chunk but no SQL — uses pre-loaded raw arrays.
    raw_metrics: dict col -> (n_sym, n_dates)
    indices: (n_strings_this_chunk, 10)
    weights: (n_strings_this_chunk, 10)
    Wn: (n_strings_this_chunk, 10) normalized weights
    Returns dict col -> (n_strings_this_chunk, n_dates)
    """
    out = {}
    for col, vals in raw_metrics.items():
        gathered = vals[indices]
        if col == "volume":
            out[col] = np.einsum('bij,bi->bj', gathered, weights)
        else:
            out[col] = np.einsum('bij,bi->bj', gathered, Wn)
    return out


def get_string_screener(market="US", page=1, per_page=50, sort="weighted_alpha", sort_dir="desc",
                        search="", exchange="", asset_type="", date_cutoff="", args=None,
                        string_id_like=None):
    args = args or {}
    conn = get_db(market)
    try:
        if date_cutoff:
            where = ["h.date = ?", "h.string_id IN (SELECT string_id FROM string_universe WHERE market=?)"]
            params = [date_cutoff, market]
            if string_id_like:
                where.append(f"h.string_id LIKE ?"); params.append(string_id_like)
            if search:
                where.append("(h.string_id LIKE ? OR h.name LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])
            if exchange:
                where.append("'BASKET' = ?"); params.append(exchange)
            if asset_type:
                where.append("'basket' = ?"); params.append(asset_type)
            _apply_numeric_filters(where, params, args, "h.")
            _apply_signal_filters(where, params, args, "h.")
            where_str = " AND ".join(where)
            total = conn.execute(f"SELECT COUNT(*) FROM historical_string_screener h WHERE {where_str}", params).fetchone()[0]
            order_col = _map_sort(sort, "h.")
            direction = "DESC" if sort_dir == "desc" else "ASC"
            rows = conn.execute(
                f"SELECT h.string_id as symbol, h.name, 'BASKET' as exchange, 'basket' as asset_class, h.price, h.change_pct, "
                f"h.volume, h.weighted_alpha, h.atrp, h.streak, h.r_squared, h.atr_signal, h.atr_stop, h.atr_value, "
                f"h.atr_streak, h.atr_crossed_above, h.atr_crossed_below, h.atr_multiplier, "
                f"h.next_day_return, h.next_5d_return, h.prob_up_1d, h.prob_up_5d, h.prob_up_st_cross, h.pre_price, h.pre_change_pct, "
                f"h.post_price, h.post_change_pct, h.accel_a, h.accel_base, h.accel_signal, "
                f"h.accel_crossed_up, h.accel_crossed_down, h.accel_streak, h.confluence, "
                f"h.ai_overall_score, h.ai_bias, h.ai_tech_score, h.ai_momentum_score, "
                f"h.ai_volume_score, h.ai_events_score, h.ai_volume_profile_score, "
                f"h.ai_trendline_score, h.ai_sentiment_score, h.ai_conclusion, h.ai_matrix, "
                f"h.st_bars_below, h.st_bars_above, h.accel_bars_below, h.accel_bars_above, "
                f"h.date as last_updated "
                f"FROM historical_string_screener h WHERE {where_str} ORDER BY {order_col} {direction} "
                f"LIMIT ? OFFSET ?", params + [per_page, (page - 1) * per_page]).fetchall()
            data = [dict(r) for r in rows]
            return {"data": data, "total": total, "page": page, "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page, "historical": True, "date": date_cutoff}
        else:
            where = ["m.market = ?"]
            params = [market]
            if string_id_like:
                where.append(f"m.string_id LIKE ?"); params.append(string_id_like)
            if search:
                where.append("(m.string_id LIKE ? OR m.name LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])
            if exchange:
                where.append("m.exchange = ?"); params.append(exchange)
            if asset_type:
                where.append("m.asset_class = ?"); params.append(asset_type)
            _apply_numeric_filters(where, params, args, "m.")
            _apply_signal_filters(where, params, args, "m.")
            where_str = " AND ".join(where)
            total = conn.execute(
                f"SELECT COUNT(*) FROM string_screener_metrics m WHERE {where_str}", params).fetchone()[0]
            order_col = _map_sort(sort, "m.")
            direction = "DESC" if sort_dir == "desc" else "ASC"
            rows = conn.execute(
                f"SELECT m.string_id as symbol, m.name, m.exchange, m.asset_class, m.price, m.change_pct, "
                f"m.volume, m.weighted_alpha, m.atrp, m.streak, m.r_squared, m.atr_signal, m.atr_stop, m.atr_value, "
                f"m.atr_streak, m.atr_crossed_above, m.atr_crossed_below, m.atr_multiplier, "
                f"m.next_day_return, m.next_5d_return, m.prob_up_1d, m.prob_up_5d, m.prob_up_st_cross, m.pre_price, m.pre_change_pct, "
                f"m.post_price, m.post_change_pct, m.accel_a, m.accel_base, m.accel_signal, "
                f"m.accel_crossed_up, m.accel_crossed_down, m.accel_streak, m.confluence, "
                f"m.ai_overall_score, m.ai_bias, m.ai_tech_score, m.ai_momentum_score, "
                f"m.ai_volume_score, m.ai_events_score, m.ai_volume_profile_score, "
                f"m.ai_trendline_score, m.ai_sentiment_score, m.ai_conclusion, m.ai_matrix, "
                f"m.st_bars_below, m.st_bars_above, m.accel_bars_below, m.accel_bars_above, "
                f"m.updated_at as last_updated "
                f"FROM string_screener_metrics m WHERE {where_str} ORDER BY {order_col} {direction} "
                f"LIMIT ? OFFSET ?", params + [per_page, (page - 1) * per_page]).fetchall()
            data = [dict(r) for r in rows]
            return {"data": data, "total": total, "page": page, "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page, "historical": False}
    finally:
        conn.close()


def _apply_numeric_filters(where, params, args, pfx):
    m = {
        "min_price": "price", "max_price": "price", "min_wa": "weighted_alpha",
        "max_wa": "weighted_alpha", "min_change": "change_pct", "max_change": "change_pct",
        "min_streak": "streak", "min_volume": "volume",
    }
    for arg, col in m.items():
        v = args.get(arg)
        if v in (None, ""):
            continue
        v = float(v)
        if arg.startswith("min"):
            where.append(f"{pfx}{col} >= ?"); params.append(v)
        else:
            where.append(f"{pfx}{col} <= ?"); params.append(v)


def _apply_signal_filters(where, params, args, pfx):
    atr = args.get("atr_status", "")
    if atr == "above":
        where.append(f"{pfx}atr_signal = 1")
    elif atr == "below":
        where.append(f"{pfx}atr_signal = -1")
    elif atr == "crossed-above":
        where.append(f"{pfx}atr_crossed_above = 1")
    elif atr == "crossed-below":
        where.append(f"{pfx}atr_crossed_below = 1")
    accel = args.get("accel_status", "")
    if accel == "up":
        where.append(f"{pfx}accel_signal = 1")
    elif accel == "down":
        where.append(f"{pfx}accel_signal = -1")
    elif accel == "crossed-up":
        where.append(f"{pfx}accel_crossed_up = 1")
    elif accel == "crossed-down":
        where.append(f"{pfx}accel_crossed_down = 1")


def _map_sort(sort, pfx):
    allowed = {"symbol", "name", "price", "change_pct", "weighted_alpha", "volume", "streak",
               "r_squared",
               "atr_signal", "atr_stop", "atr_value", "atr_streak", "atrp",
               "atr_crossed_above", "atr_crossed_below", "prob_up_1d", "prob_up_5d", "prob_up_st_cross",
               "next_day_return", "next_5d_return", "confluence", "accel_a", "accel_base",
               "accel_signal", "accel_streak", "accel_crossed_up", "accel_crossed_down",
               "ai_overall_score", "ai_bias", "ai_tech_score", "ai_volume_profile_score",
               "ai_trendline_score", "ai_sentiment_score", "ai_conclusion", "ai_matrix"}
    if sort not in allowed:
        sort = "weighted_alpha"
    if sort == "symbol":
        sort = "string_id"
    return f"{pfx}{sort}"


def get_string_detail(string_id, market="US"):
    conn = get_db(market)
    try:
        univ = conn.execute(
            "SELECT string_id, market, num_stocks, expression, created_at FROM string_universe WHERE string_id=?",
            (string_id,)).fetchone()
        if not univ:
            return None
        cons = conn.execute(
            "SELECT symbol, weight FROM string_constituents WHERE string_id=?", (string_id,)).fetchall()
        metrics = conn.execute(
            "SELECT * FROM string_screener_metrics WHERE string_id=?", (string_id,)).fetchone()
        symbols = [c[0] for c in cons]
        contrib = []
        gross_exposure = 0.0
        net_exposure = 0.0
        long_exposure = 0.0
        short_exposure = 0.0
        is_ls = string_id.startswith("LS")
        if symbols:
            placeholders = ",".join("?" * len(symbols))
            rows = conn.execute(
                f"SELECT s.symbol, s.price, s.change_pct, s.weighted_alpha, s.atr_signal, s.prob_up_1d, a.ai_matrix "
                f"FROM stats s LEFT JOIN ai_analysis a ON s.symbol=a.symbol "
                f"WHERE s.symbol IN ({placeholders})", symbols).fetchall()
            smap = {r[0]: r for r in rows}
            for sym, w in cons:
                r = smap.get(sym)
                price = r[1] if r else 0
                change_pct = r[2] if r else 0
                position_value = abs(w) * (price or 0)
                integer_qty = int(abs(w)) if is_ls and w < 0 else None
                fractional_qty = abs(w)
                side = "long" if w > 0 else "short"
                gross_exposure += position_value
                net_exposure += w * (price or 0)
                if w > 0:
                    long_exposure += position_value
                else:
                    short_exposure += position_value
                c = {
                    "symbol": sym, "weight": w, "price": price, "change_pct": change_pct,
                    "side": side, "fractional_qty": round(fractional_qty, 4),
                    "position_value": round(position_value, 2),
                }
                if r:
                    c.update({"weighted_alpha": r[3], "atr_signal": r[4], "prob_up_1d": r[5], "ai_matrix": r[6]})
                if is_ls and w < 0:
                    c["integer_qty"] = integer_qty
                    c["min_valid_short"] = integer_qty >= 1
                contrib.append(c)
        hist = conn.execute(
            "SELECT date, price, change_pct, ai_matrix, atr_signal, weighted_alpha "
            "FROM historical_string_screener WHERE string_id=? ORDER BY date", (string_id,)).fetchall()
        result = {
            "universe": dict(univ),
            "constituents": [{"symbol": c[0], "weight": c[1]} for c in cons],
            "metrics": dict(metrics) if metrics else {},
            "contributions": contrib,
            "history": [dict(r) for r in hist],
        }
        if is_ls:
            result["exposure"] = {
                "long_exposure": round(long_exposure, 2),
                "short_exposure": round(short_exposure, 2),
                "gross_exposure": round(gross_exposure, 2),
                "net_exposure": round(net_exposure, 2),
                "is_long_short": True,
            }
        return result
    finally:
        conn.close()


STRING_COLUMN_REFERENCE = [
    {"key": "symbol", "label": "String ID", "current": "string_screener_metrics.string_id",
     "historical": "historical_string_screener.string_id",
     "meaning": "Unique basket string identifier (e.g. S000123)."},
    {"key": "name", "label": "Expression", "current": "string_screener_metrics.name",
     "historical": "historical_string_screener.name",
     "meaning": "Short basket expression; full expression on the detail page."},
    {"key": "exchange", "label": "Type", "current": "string_screener_metrics.exchange",
     "historical": "historical_string_screener.exchange", "meaning": "Always BASKET."},
    {"key": "asset_class", "label": "Class", "current": "string_screener_metrics.asset_class",
     "historical": "historical_string_screener.asset_class", "meaning": "basket."},
    {"key": "price", "label": "Value", "current": "string_screener_metrics.price",
     "historical": "historical_string_screener.price",
     "meaning": "Basket value index level (normalized to 100 at basket start)."},
    {"key": "change_pct", "label": "Chg%", "current": "string_screener_metrics.change_pct",
     "historical": "historical_string_screener.change_pct",
     "meaning": "Basket daily percent change (weighted basket return)."},
    {"key": "next_day_return", "label": "Next Day %", "current": "string_screener_metrics.next_day_return",
     "historical": "historical_string_screener.next_day_return",
     "meaning": "Realized next trading day basket return."},
    {"key": "next_5d_return", "label": "Next 5D %", "current": "string_screener_metrics.next_5d_return",
     "historical": "historical_string_screener.next_5d_return", "meaning": "5-day basket return."},
    {"key": "prob_up_1d", "label": "P(Up) 1D", "current": "string_screener_metrics.prob_up_1d",
     "historical": "historical_string_screener.prob_up_1d",
     "meaning": "Weighted average of constituent P(Up) 1D."},
     {"key": "prob_up_5d", "label": "P(Up) 5D", "current": "string_screener_metrics.prob_up_5d",
      "historical": "historical_string_screener.prob_up_5d", "meaning": "Weighted avg P(Up) 5D."},
     {"key": "prob_up_st_cross", "label": "P(Up) ST Cross", "current": "string_screener_metrics.prob_up_st_cross",
      "historical": "historical_string_screener.prob_up_st_cross",
      "meaning": "Weighted avg of constituent P(Up) after 14d/1x SuperTrend bullish cross."},
    {"key": "weighted_alpha", "label": "Wtd Alpha", "current": "string_screener_metrics.weighted_alpha",
     "historical": "historical_string_screener.weighted_alpha", "meaning": "Weighted avg of constituent weighted alpha."},
    {"key": "volume", "label": "Volume", "current": "string_screener_metrics.volume",
     "historical": "historical_string_screener.volume", "meaning": "Weighted sum of constituent volume."},
    {"key": "streak", "label": "Streak", "current": "string_screener_metrics.streak",
     "historical": "historical_string_screener.streak", "meaning": "Basket up/down streak from basket returns."},
    {"key": "confluence", "label": "Confluence", "current": "string_screener_metrics.confluence",
     "historical": "historical_string_screener.confluence", "meaning": "Weighted avg of constituent confluence."},
    {"key": "ai_overall_score", "label": "AI Score", "current": "string_screener_metrics.ai_overall_score",
     "historical": "historical_string_screener.ai_overall_score", "meaning": "Equals ai_matrix."},
    {"key": "ai_volume_profile_score", "label": "VP Score", "current": "string_screener_metrics.ai_volume_profile_score",
     "historical": "historical_string_screener.ai_volume_profile_score", "meaning": "Weighted avg VP score."},
    {"key": "ai_trendline_score", "label": "Trend Score", "current": "string_screener_metrics.ai_trendline_score",
     "historical": "historical_string_screener.ai_trendline_score", "meaning": "Weighted avg trend score."},
    {"key": "ai_sentiment_score", "label": "Sentiment", "current": "string_screener_metrics.ai_sentiment_score",
     "historical": "historical_string_screener.ai_sentiment_score", "meaning": "Weighted avg sentiment score."},
    {"key": "ai_conclusion", "label": "Conclusion", "current": "string_screener_metrics.ai_conclusion",
     "historical": "historical_string_screener.ai_conclusion", "meaning": "BUY/HOLD/SELL from ai_matrix."},
    {"key": "ai_matrix", "label": "AI Matrix", "current": "string_screener_metrics.ai_matrix",
     "historical": "historical_string_screener.ai_matrix",
     "meaning": "Weighted average of constituent ai_matrix (0-100 directional score)."},
    {"key": "atr_signal", "label": "ST Signal", "current": "string_screener_metrics.atr_signal",
     "historical": "historical_string_screener.atr_signal",
     "meaning": "Weighted-majority SuperTrend direction of constituents."},
    {"key": "atr_crossed_above", "label": "Cross Up", "current": "string_screener_metrics.atr_crossed_above",
     "historical": "historical_string_screener.atr_crossed_above", "meaning": "1 if >25% weighted constituents crossed up."},
    {"key": "atr_crossed_below", "label": "Cross Down", "current": "string_screener_metrics.atr_crossed_below",
     "historical": "historical_string_screener.atr_crossed_below", "meaning": "1 if >25% weighted constituents crossed down."},
    {"key": "atr_stop", "label": "ST Stop", "current": "string_screener_metrics.atr_stop",
     "historical": "historical_string_screener.atr_stop", "meaning": "Weighted sum of constituent ATR stop."},
    {"key": "atrp", "label": "ATR%", "current": "string_screener_metrics.atrp",
     "historical": "historical_string_screener.atrp", "meaning": "Weighted avg of constituent ATR%."},
    {"key": "accel_signal", "label": "Accel", "current": "string_screener_metrics.accel_signal",
     "historical": "historical_string_screener.accel_signal", "meaning": "Weighted-majority Accel direction."},
    {"key": "accel_crossed_up", "label": "Accel Up", "current": "string_screener_metrics.accel_crossed_up",
     "historical": "historical_string_screener.accel_crossed_up", "meaning": "1 if >25% weighted constituents accel crossed up."},
    {"key": "accel_crossed_down", "label": "Accel Down", "current": "string_screener_metrics.accel_crossed_down",
     "historical": "historical_string_screener.accel_crossed_down", "meaning": "1 if >25% weighted constituents accel crossed down."},
    {"key": "st_bars_below", "label": "ST Bars Below", "current": "string_screener_metrics.st_bars_below",
     "historical": "historical_string_screener.st_bars_below", "meaning": "Weighted avg bars below ST before cross-up."},
    {"key": "st_bars_above", "label": "ST Bars Above", "current": "string_screener_metrics.st_bars_above",
     "historical": "historical_string_screener.st_bars_above", "meaning": "Weighted avg bars above ST before cross-down."},
    {"key": "accel_bars_below", "label": "Accel Bars Below", "current": "string_screener_metrics.accel_bars_below",
     "historical": "historical_string_screener.accel_bars_below", "meaning": "Weighted avg bars below accel before cross-up."},
    {"key": "accel_bars_above", "label": "Accel Bars Above", "current": "string_screener_metrics.accel_bars_above",
     "historical": "historical_string_screener.accel_bars_above", "meaning": "Weighted avg bars above accel before cross-down."},
    {"key": "last_updated", "label": "Updated", "current": "string_screener_metrics.updated_at",
     "historical": "historical_string_screener.date", "meaning": "Current update time or selected as-of date."},
]


def build_leaderboard_cache(market="US"):
    """Build pre-aggregated leaderboard cache from historical_string_screener.
    Called during refresh so the leaderboard API can read from a small cache table."""
    t0 = time.time()
    conn = get_db(market)
    try:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='string_leaderboard_cache'"
        ).fetchone()
        if not exists:
            conn.execute("""CREATE TABLE IF NOT EXISTS string_leaderboard_cache (
                string_id TEXT, market TEXT, expression TEXT, n_dates INTEGER,
                win_rate REAL, avg_return REAL, total_return REAL, sharpe REAL,
                best_day REAL, worst_day REAL, avg_ai REAL,
                PRIMARY KEY (string_id, market))""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_slc_market ON string_leaderboard_cache(market)")
            conn.commit()

        hist_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='historical_string_screener'"
        ).fetchone()
        if not hist_exists:
            logger.info(f"[{market}] no historical_string_screener, skipping leaderboard cache")
            return 0

        rows = conn.execute(f"""
            SELECT string_id,
                COUNT(*) as n_dates,
                ROUND(AVG(CASE WHEN next_day_return > 0 THEN 100.0 ELSE 0 END), 2) as win_pct,
                ROUND(AVG(next_day_return), 4) as avg_ret,
                ROUND(MAX(next_day_return), 2) as best_day,
                ROUND(MIN(next_day_return), 2) as worst_day,
                ROUND(AVG(CAST(ai_matrix AS REAL)), 1) as avg_ai,
                MIN(price) as first_price,
                MAX(price) as last_price
            FROM historical_string_screener
            WHERE next_day_return IS NOT NULL
            GROUP BY string_id
            HAVING COUNT(*) >= 20
        """).fetchall()

        univ = conn.execute(
            "SELECT string_id, expression FROM string_universe WHERE market=?", (market,)
        ).fetchall()
        expr_map = {r[0]: r[1] for r in univ}

        conn.execute("DELETE FROM string_leaderboard_cache WHERE market=?", (market,))
        batch = []
        for r in rows:
            sid = r[0]
            n_dates = r[1]
            win_pct = r[2] or 0
            avg_ret = r[3] or 0
            best_day = r[4] or 0
            worst_day = r[5] or 0
            avg_ai = r[6] or 50
            fp = float(r[7]) if r[7] else 0
            lp = float(r[8]) if r[8] else 0
            total_ret = round(((lp / fp - 1) * 100), 2) if fp > 0 else 0
            sharpe = round(avg_ret * (win_pct / 50.0), 2)
            expr = expr_map.get(sid, sid)
            short_expr = expr[:60] + ("..." if len(expr) > 60 else "")
            batch.append((sid, market, short_expr, n_dates, win_pct, avg_ret,
                          total_ret, sharpe, best_day, worst_day, avg_ai))

        if batch:
            conn.executemany(
                "INSERT OR REPLACE INTO string_leaderboard_cache "
                "(string_id, market, expression, n_dates, win_rate, avg_return, "
                "total_return, sharpe, best_day, worst_day, avg_ai) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
            conn.commit()

        logger.info(f"[{market}] leaderboard cache built: {len(batch)} strings in {time.time()-t0:.1f}s")
        return len(batch)
    finally:
        conn.close()
