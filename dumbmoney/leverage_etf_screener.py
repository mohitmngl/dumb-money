"""Leverage ETF Screener - basket strings of leveraged ETFs only.

Clone of basket_screener but restricted to leveraged ETFs.
Uses LEV-prefixed string IDs stored in the same tables.
Equal dollar allocation per ETF; non-fractionable = 1 qty.
"""

import logging
import numpy as np
from datetime import datetime

from dumbmoney.db import get_db

logger = logging.getLogger(__name__)

STRING_COUNT = 25000
TARGET_ETFS = 10
ALLOCATION = 1000.0

LEV_LEVERAGED_SQL = (
    # Leverage ratio in name
    "(a.name LIKE '%2x%' OR a.name LIKE '%3x%' OR a.name LIKE '%4x%' OR a.name LIKE '%5x%'"
    " OR a.name LIKE '%2X%' OR a.name LIKE '%3X%' OR a.name LIKE '%4X%' OR a.name LIKE '%5X%'"
    # ProShares families
    " OR a.name LIKE '%UltraPro%' OR a.name LIKE '%Ultra Bull%' OR a.name LIKE '%Ultra Bear%'"
    " OR a.name LIKE '%Ultra Short%' OR a.name LIKE '%Ultra VIX%'"
    " OR a.name LIKE '%ProShares Ultra%' OR a.name LIKE '%ProShares Short%'"
    # Direxion Daily
    " OR a.name LIKE '%Direxion Daily%'"
    # Broad keywords
    " OR a.name LIKE '%Leveraged%' OR a.name LIKE '%Inverse%'"
    # Single-letter bear/short ETFs (ProShares Short*, Direxion *Bear*)
    " OR a.name LIKE '%Bear%' OR a.name LIKE '%Short%')"
)


def eligible_leveraged_etfs(market="US"):
    """Return active leveraged ETF symbols. No volume filter."""
    conn = get_db(market)
    try:
        rows = conn.execute(
            f"SELECT a.symbol FROM assets a JOIN stats s ON s.symbol=a.symbol "
            f"WHERE a.status='active' AND a.tradable=1 "
            f"AND LOWER(COALESCE(a.asset_class,'')) = 'etf' "
            f"AND {LEV_LEVERAGED_SQL}"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def generate_leveraged_etf_universe(market="US", n=STRING_COUNT, force=False):
    """Generate basket strings of 10 leveraged ETFs each.
    Equal $1000 allocation. Non-fractionable = 1 whole share."""
    conn = get_db(market)
    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM string_universe WHERE market=? AND string_id LIKE 'LEV%'",
            (market,)).fetchone()[0]
        if existing >= n and not force:
            logger.info(f"[{market}] LEV universe already has {existing} strings; skipping")
            return existing
        if force:
            conn.execute("DELETE FROM string_constituents WHERE string_id IN "
                         "(SELECT string_id FROM string_universe WHERE market=? AND string_id LIKE 'LEV%')",
                         (market,))
            conn.execute("DELETE FROM string_universe WHERE market=? AND string_id LIKE 'LEV%'",
                         (market,))
            conn.commit()

        syms = eligible_leveraged_etfs(market)
        if len(syms) < TARGET_ETFS:
            logger.warning(f"[{market}] too few leveraged ETFs ({len(syms)})")
            return 0

        price_rows = conn.execute(
            f"SELECT symbol, price FROM stats WHERE symbol IN ({','.join('?' * len(syms))})",
            syms).fetchall()
        price_map = {r[0]: float(r[1]) for r in price_rows if r[1] and float(r[1]) > 0}

        frac_rows = conn.execute(
            f"SELECT symbol, fractionable FROM assets WHERE symbol IN ({','.join('?' * len(syms))})",
            syms).fetchall()
        frac_map = {r[0]: bool(r[1]) for r in frac_rows}

        priced_syms = [s for s in syms if s in price_map]
        if len(priced_syms) < TARGET_ETFS:
            logger.warning(f"[{market}] too few leveraged ETFs with prices ({len(priced_syms)})")
            return 0

        rng = np.random.default_rng(20240715)
        sym_arr = np.array(priced_syms, dtype=object)

        start = conn.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(string_id,4) AS INTEGER)),0) "
            "FROM string_universe WHERE string_id LIKE 'LEV%'").fetchone()[0]
        count = 0
        batch_univ = []
        batch_cons = []
        per_etf = ALLOCATION / TARGET_ETFS

        for i in range(start + 1, start + 1 + n):
            idx = rng.choice(len(sym_arr), size=TARGET_ETFS, replace=False)
            picked = sym_arr[idx]

            weights = np.zeros(TARGET_ETFS)
            for j in range(TARGET_ETFS):
                sym = str(picked[j])
                price = price_map[sym]
                is_frac = frac_map.get(sym, False)
                raw_w = per_etf / price
                if not is_frac:
                    weights[j] = max(1.0, round(raw_w))
                else:
                    weights[j] = round(raw_w, 4)

            weights = np.maximum(weights, 0.001)
            sid = f"LEV{i:06d}"
            expr = " + ".join(f"{picked[j]}*{weights[j]:g}" for j in range(TARGET_ETFS))
            batch_univ.append((sid, market, TARGET_ETFS, expr, datetime.utcnow().isoformat(), 1))
            for j in range(TARGET_ETFS):
                batch_cons.append((sid, str(picked[j]), float(weights[j])))
            count += 1
            if len(batch_univ) >= 2000:
                conn.executemany(
                    "INSERT OR REPLACE INTO string_universe "
                    "(string_id, market, num_stocks, expression, created_at, active) "
                    "VALUES (?,?,?,?,?,?)", batch_univ)
                conn.executemany(
                    "INSERT OR REPLACE INTO string_constituents (string_id, symbol, weight) "
                    "VALUES (?,?,?)", batch_cons)
                conn.commit()
                batch_univ.clear()
                batch_cons.clear()

        if batch_univ:
            conn.executemany(
                "INSERT OR REPLACE INTO string_universe "
                "(string_id, market, num_stocks, expression, created_at, active) "
                "VALUES (?,?,?,?,?,?)", batch_univ)
            conn.executemany(
                "INSERT OR REPLACE INTO string_constituents (string_id, symbol, weight) "
                "VALUES (?,?,?)", batch_cons)
            conn.commit()

        logger.info(f"[{market}] generated {count} leveraged ETF strings")
        return count
    finally:
        conn.close()


def compute_leveraged_etf_current_metrics(market="US"):
    """Compute current metrics for LEV strings using basket_screener engine."""
    from dumbmoney.basket_screener import (
        _load_composition, _load_close_pivot, _gather_einsum, _series_metrics,
        _weighted_current, _load_ohlc_pivots, _compute_basket_ohlc,
        _compute_basket_indicators, _majority_signal, _cross_flag
    )
    from dumbmoney.db import get_db as _get_db

    conn = _get_db(market)
    try:
        sids = [r[0] for r in conn.execute(
            "SELECT string_id FROM string_universe WHERE market=? AND string_id LIKE 'LEV%'",
            (market,)).fetchall()]
        if not sids:
            return 0

        sid_arr, sym_list, indices, weights = _load_composition(market, string_ids=sids)
        if not len(sym_list):
            return 0

        sym_list_used, dates_all, close_all = _load_close_pivot(market, sym_list)
        if close_all.shape[1] == 0:
            return 0

        window = min(80, close_all.shape[1])
        close_w = close_all[:, -window:]
        dates_w = dates_all[-window:]

        V = _gather_einsum(close_w, indices, weights)
        sm = _series_metrics(V)

        current_metrics = _weighted_current(indices, weights, market, sym_list)

        high_all, low_all, open_all = _load_ohlc_pivots(market, sym_list)
        if high_all is not None:
            basket_ohlc = _compute_basket_ohlc(close_all, high_all, low_all, open_all, indices, weights)
            indicators = _compute_basket_indicators(basket_ohlc)
        else:
            last_ret = sm["ret"][:, -1] if sm["ret"].shape[1] > 0 else np.zeros(len(sids))
            indicators = {
                "atr_signal": _majority_signal(last_ret),
                "atr_stop": np.zeros(len(sids)), "atr_value": np.zeros(len(sids)),
                "atr_streak": np.zeros(len(sids), dtype=int),
                "atr_crossed_above": np.zeros(len(sids), dtype=int),
                "atr_crossed_below": np.zeros(len(sids), dtype=int),
                "accel_a": np.zeros(len(sids)), "accel_base": np.zeros(len(sids)),
                "accel_signal": _majority_signal(last_ret),
                "accel_crossed_up": np.zeros(len(sids), dtype=int),
                "accel_crossed_down": np.zeros(len(sids), dtype=int),
                "accel_streak": np.zeros(len(sids), dtype=int),
            }

        rows = []
        for i, sid in enumerate(sid_arr):
            def _v(key, default=0):
                val = current_metrics.get(key, default)
                if isinstance(val, np.ndarray):
                    return float(val[i]) if i < len(val) else float(default)
                return float(val)
            def _s(key, default=""):
                val = current_metrics.get(key, default)
                if isinstance(val, np.ndarray):
                    return str(val[i]) if i < len(val) else str(default)
                return str(val)
            rows.append((
                sid, market, "", "", "etf", float(sm["V"][i, -1]) if sm["V"][i, -1] else 0,
                float(sm["ret"][i, -1]) if sm["ret"].shape[1] > 0 else 0,
                _v("volume"), _v("weighted_alpha"), _v("atrp"),
                int(sm["streak_series"][i, -1]) if sm["streak_series"].shape[1] > 0 else 0,
                int(indicators["atr_signal"][i, -1]),
                float(indicators["atr_stop"][i, -1]),
                float(indicators["atr_value"][i, -1]),
                int(indicators["atr_streak"][i, -1]),
                int(indicators["atr_crossed_above"][i, -1]),
                int(indicators["atr_crossed_below"][i, -1]),
                1.0,
                _v("next_day_return"), 0,
                _v("prob_up_1d"), _v("prob_up_5d"),
                0, 0, 0, 0,
                _s("profit_status"),
                0, 0,
                float(indicators["accel_a"][i, -1]),
                float(indicators["accel_base"][i, -1]),
                int(indicators["accel_signal"][i, -1]),
                int(indicators["accel_crossed_up"][i, -1]),
                int(indicators["accel_crossed_down"][i, -1]),
                int(indicators["accel_streak"][i, -1]),
                0,
                _v("ai_overall_score"), _s("ai_bias", "neutral"),
                _v("ai_tech_score"), _v("ai_momentum_score"),
                _v("ai_volume_score"), _v("ai_events_score"),
                _v("ai_volume_profile_score"), _v("ai_trendline_score"),
                _v("ai_sentiment_score"), _s("ai_conclusion", "HOLD"),
                _s("ai_matrix", ""),
                datetime.utcnow().isoformat(),
            ))

        conn2 = _get_db(market)
        try:
            conn2.execute("DELETE FROM string_screener_metrics WHERE market=? AND string_id LIKE 'LEV%'", (market,))
            conn2.executemany(
                "INSERT OR REPLACE INTO string_screener_metrics "
                "(string_id, market, name, exchange, asset_class, price, change_pct, volume, "
                "weighted_alpha, atrp, streak, atr_signal, atr_stop, atr_value, atr_streak, "
                "atr_crossed_above, atr_crossed_below, atr_multiplier, "
                "next_day_return, next_5d_return, prob_up_1d, prob_up_5d, "
                "pre_price, pre_change_pct, post_price, post_change_pct, "
                "profit_status, fractionable, marginable, "
                "accel_a, accel_base, accel_signal, accel_crossed_up, accel_crossed_down, accel_streak, "
                "confluence, ai_overall_score, ai_bias, ai_tech_score, ai_momentum_score, "
                "ai_volume_score, ai_events_score, ai_volume_profile_score, "
                "ai_trendline_score, ai_sentiment_score, ai_conclusion, ai_matrix, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows)
            conn2.commit()
        finally:
            conn2.close()

        logger.info(f"[{market}] computed current metrics for {len(rows)} LEV strings")
        return len(rows)
    finally:
        conn.close()


def update_leveraged_etf_historical(market="US", force_rebuild=False, progress_callback=None):
    """Build historical_string_screener for LEV strings only."""
    from dumbmoney.basket_screener import update_historical_string_screener
    return update_historical_string_screener(
        market, force_rebuild=force_rebuild, progress_callback=progress_callback,
        string_id_like="LEV%")


def get_lev_screener(market="US", page=1, per_page=50, sort="weighted_alpha",
                     sort_dir="desc", search="", date_cutoff="", args=None):
    """Query LEV string screener results."""
    from dumbmoney.basket_screener import get_string_screener
    return get_string_screener(market, page, per_page, sort, sort_dir, search,
                               "", "", date_cutoff, args or {}, string_id_like="LEV%")


def get_lev_detail(string_id, market="US"):
    """Get full detail for one LEV string."""
    from dumbmoney.basket_screener import get_string_detail
    return get_string_detail(string_id, market)
