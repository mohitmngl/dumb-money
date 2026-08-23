import pandas as pd
import numpy as np
import logging
import os
import sys
import threading
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dumbmoney.db import get_db
from dumbmoney.data_us import get_snapshots
from dumbmoney.indicators import (
    supertrend, atr_trailing_stop, weighted_alpha, accel, prob_up, prob_up_after_st_cross_up,
    next_day_return, streak_vectorized, atrp, ai_score_latest, compute_confluence, rsi_wilder,
    compute_signal_prob_matrix, _compute_ai_matrix_score, compute_confluence_vectorized,
    bars_at_side, compute_rolling_atr_trailing_stop, compute_rolling_atr_batch, r_squared
)

logger = logging.getLogger(__name__)

# ATR trailing stop multiplier used across ALL markets, timeframes, charts,
# portfolios and metrics. Changed 1.0 -> 2.0 per owner decision (2026-08-23).
ATR_MULTIPLIER = 2.0

# Rolling window (bars) for the R² straight-trend column.
R_SQUARED_WINDOW = 90


def _compute_symbol_stats_worker(args):
    """Worker function for parallel stats computation. Runs in a subprocess."""
    sym, dates, opens, highs, lows, closes, volumes = args
    try:
        import numpy as np
        import pandas as pd
        from dumbmoney.indicators import (
            supertrend, atr_trailing_stop, weighted_alpha, accel, prob_up, prob_up_after_st_cross_up,
            next_day_return, streak_vectorized, atrp, ai_score_latest, compute_confluence,
            bars_at_side
        )

        def _safe_int(v):
            try:
                import math
                f = float(v)
                return 0 if math.isnan(f) or math.isinf(f) else int(f)
            except (TypeError, ValueError):
                return 0

        def _safe_float(v):
            try:
                import math
                f = float(v)
                return 0.0 if math.isnan(f) or math.isinf(f) else f
            except (TypeError, ValueError):
                return 0.0

        n = len(closes)
        if n < 2:
            return None

        c = pd.Series(closes, dtype=float)
        h = pd.Series(highs, dtype=float)
        l = pd.Series(lows, dtype=float)
        v = pd.Series(volumes, dtype=float)
        o = pd.Series(opens, dtype=float)

        last_close = c.iloc[-1]
        prev_close = c.iloc[-2] if n >= 2 else last_close
        change_pct = ((last_close - prev_close) / prev_close * 100) if prev_close > 0 else 0

        grp = pd.DataFrame({"date": pd.to_datetime(dates), "open": o, "high": h, "low": l, "close": c, "volume": v})

        wa = weighted_alpha(grp)
        wa_val = wa.iloc[-1] if len(wa) > 0 else 0

        st_result = atr_trailing_stop(grp, period=14, multiplier=ATR_MULTIPLIER)
        st_trend = _safe_int(st_result["trend"].iloc[-1]) if len(st_result) > 0 else 0
        st_signal = st_trend
        st_stop = _safe_float(st_result["stop"].iloc[-1]) if len(st_result) > 0 else 0
        st_atr = _safe_float(st_result["atr_value"].iloc[-1]) if len(st_result) > 0 else 0
        st_streak = _safe_int(st_result["streak"].iloc[-1]) if len(st_result) > 0 else 0
        st_cross_up = _safe_int(st_result["crossed_above"].iloc[-1]) if len(st_result) > 0 else 0
        st_cross_down = _safe_int(st_result["crossed_below"].iloc[-1]) if len(st_result) > 0 else 0

        ac = accel(grp)
        accel_a_val = _safe_float(ac["accel_a"].iloc[-1]) if len(ac) > 0 else 0
        accel_base_val = _safe_float(ac["accel_base"].iloc[-1]) if len(ac) > 0 else 0
        accel_signal_val = _safe_int(ac["accel_signal"].iloc[-1]) if len(ac) > 0 else 0
        accel_cross_up = _safe_int(ac["accel_crossed_up"].iloc[-1]) if len(ac) > 0 else 0
        accel_cross_down = _safe_int(ac["accel_crossed_down"].iloc[-1]) if len(ac) > 0 else 0
        accel_streak_val = _safe_int(ac["accel_streak"].iloc[-1]) if len(ac) > 0 else 0

        st_sig_full = st_result["trend"].fillna(0).astype(int).values if len(st_result) > 0 else np.zeros(1, dtype=int)
        ac_sig_full = ac["accel_signal"].fillna(0).astype(int).values if len(ac) > 0 else np.zeros(1, dtype=int)
        st_bas = bars_at_side(st_sig_full)
        ac_bas = bars_at_side(ac_sig_full)
        _st_bas_last = _safe_int(st_bas[-1]) if len(st_bas) > 0 else 0
        _ac_bas_last = _safe_int(ac_bas[-1]) if len(ac_bas) > 0 else 0
        st_bars_below_val = _st_bas_last if st_signal == 1 else 0
        st_bars_above_val = _st_bas_last if st_signal == -1 else 0
        accel_bars_below_val = _ac_bas_last if accel_signal_val == 1 else 0
        accel_bars_above_val = _ac_bas_last if accel_signal_val == -1 else 0

        atrp_val = _safe_float(atrp(h, l, c).iloc[-1]) if len(h) > 0 else 0
        p1d = prob_up(c, 1)
        p5d = prob_up(c, 5)
        p1w = prob_up(c, 5)
        p1m = prob_up(c, 22)
        prob_1d = _safe_float(p1d.iloc[-1]) if len(p1d) > 0 else 50.0
        prob_5d = _safe_float(p5d.iloc[-1]) if len(p5d) > 0 else 50.0
        prob_1w = _safe_float(p1w.iloc[-1]) if len(p1w) > 0 else 50.0
        prob_1m = _safe_float(p1m.iloc[-1]) if len(p1m) > 0 else 50.0
        prob_st_cross_arr = prob_up_after_st_cross_up(
            st_result["crossed_above"].fillna(0).astype(int).values,
            next_day_return(c).values,
        )
        prob_st_cross = _safe_float(prob_st_cross_arr[-1]) if len(prob_st_cross_arr) > 0 else 50.0
        ndr = next_day_return(c)
        ndr_val = _safe_float(ndr.iloc[-2]) if len(ndr) >= 2 else 0
        streak_val = _safe_int(streak_vectorized(c)[-1]) if n > 1 else 0

        ai = ai_score_latest(grp, precomputed={
            "st_result": st_result, "ac_result": ac,
            "wa_val": wa_val, "streak_val": streak_val, "prob_1d_val": prob_1d
        })

        row = {
            "symbol": sym,
            "price": float(last_close),
            "volume": _safe_int(v.iloc[-1]),
            "change_pct": round(change_pct, 4),
            "weighted_alpha": round(wa_val, 4),
            "atr_signal": st_signal,
            "atr_stop": round(st_stop, 4),
            "atr_value": round(st_atr, 4),
            "atr_streak": st_streak,
            "atr_crossed_above": st_cross_up,
            "atr_crossed_below": st_cross_down,
            "atr_multiplier": 1.0,
            "streak": streak_val,
            "next_day_return": round(ndr_val, 4),
            "prob_up_1d": round(prob_1d, 2),
            "prob_up_5d": round(prob_5d, 2),
            "prob_up_st_cross": round(prob_st_cross, 2),
            "prob_up_1w": round(prob_1w, 2),
            "prob_up_1m": round(prob_1m, 2),
            "atrp": round(atrp_val, 4),
            "accel_a": round(accel_a_val, 6),
            "accel_base": round(accel_base_val, 6),
            "accel_signal": accel_signal_val,
            "accel_crossed_up": accel_cross_up,
            "accel_crossed_down": accel_cross_down,
            "accel_streak": accel_streak_val,
            "st_bars_below": st_bars_below_val,
            "st_bars_above": st_bars_above_val,
            "accel_bars_below": accel_bars_below_val,
            "accel_bars_above": accel_bars_above_val,
            "last_updated": datetime.utcnow().isoformat(),
            "oldest_data": str(dates[0])[:10] if dates else "",
            "ai_overall_score": ai["overall_score"],
            "ai_bias": ai["bias"],
            "ai_tech_score": ai["tech_score"],
            "ai_momentum_score": ai["momentum_score"],
            "ai_volume_score": ai["volume_score"],
            "ai_events_score": ai["events_score"],
            "ai_volume_profile_score": ai["volume_profile_score"],
            "ai_trendline_score": ai["trendline_score"],
            "ai_sentiment_score": ai["sentiment_score"],
            "ai_conclusion": ai["conclusion"],
            "ai_matrix": ai["ai_matrix"],
        }
        row["confluence"] = compute_confluence(row)

        return row
    except Exception as e:
        return {"symbol": sym, "_error": str(e)}



HISTORICAL_SCREENER_VERSION = "asof-v3"

HISTORICAL_SCREENER_COLUMNS = [
    "symbol", "date", "price", "change_pct", "volume",
    "weighted_alpha", "atrp", "streak", "atr_value", "atr_stop", "atr_signal",
    "atr_crossed_above", "atr_crossed_below", "atr_streak", "atr_multiplier",
    "ai_overall_score", "ai_bias", "ai_tech_score", "ai_momentum_score",
    "ai_volume_score", "ai_events_score", "ai_volume_profile_score",
    "ai_trendline_score", "ai_sentiment_score", "ai_conclusion", "ai_matrix",
    "next_day_return", "next_5d_return", "prob_up_1d", "prob_up_5d", "prob_up_st_cross",
    "prob_up_1w", "prob_up_1m", "r_squared",
    "accel_a", "accel_base", "accel_signal", "accel_crossed_up",
    "accel_crossed_down", "confluence",
    "st_bars_below", "st_bars_above", "accel_bars_below", "accel_bars_above",
    "atr_signal_w", "atr_stop_w", "atr_crossed_above_w", "atr_crossed_below_w",
    "atr_streak_w", "st_bars_below_w", "st_bars_above_w",
    "atr_signal_m", "atr_stop_m", "atr_crossed_above_m", "atr_crossed_below_m",
    "atr_streak_m", "st_bars_below_m", "st_bars_above_m",
]


def _compute_stats_batch(batch_args):
    """Standalone worker for ProcessPoolExecutor. Computes stats for a batch of symbols.
    Each worker opens its own DB connection (WAL allows concurrent readers)."""
    symbol_list, market, db_path = batch_args

    import math
    import sqlite3 as _sqlite3
    import pandas as _pd
    import numpy as _np

    from dumbmoney.indicators import (
        supertrend as _supertrend, accel as _accel, weighted_alpha as _weighted_alpha,
        prob_up as _prob_up, prob_up_after_st_cross_up as _prob_up_after_st_cross_up,
        streak_vectorized as _streak_vectorized, atrp as _atrp,
        bars_at_side as _bars_at_side, next_day_return as _next_day_return,
        compute_confluence as _compute_confluence, atr_trailing_stop as _atr_trailing_stop,
        compute_rolling_atr_trailing_stop as _compute_rolling_atr_trailing_stop,
        r_squared as _r_squared,
    )

    def _si(v):
        try:
            f = float(v)
            return 0 if math.isnan(f) or math.isinf(f) else int(f)
        except (TypeError, ValueError):
            return 0

    def _sf(v):
        try:
            f = float(v)
            return 0.0 if math.isnan(f) or math.isinf(f) else f
        except (TypeError, ValueError):
            return 0.0

    conn = _sqlite3.connect(db_path, timeout=30)
    conn.row_factory = _sqlite3.Row
    try:
        placeholders = ",".join(["?"] * len(symbol_list))
        df = _pd.read_sql(
            f"SELECT symbol, date, open, high, low, close, volume FROM bars "
            f"WHERE timeframe='1Day' AND symbol IN ({placeholders}) ORDER BY symbol, date",
            conn, parse_dates=["date"], params=symbol_list
        )
    finally:
        conn.close()

    if df.empty:
        return []

    df["close"] = _pd.to_numeric(df["close"], errors="coerce")
    df["open"] = _pd.to_numeric(df["open"], errors="coerce")
    df["high"] = _pd.to_numeric(df["high"], errors="coerce")
    df["low"] = _pd.to_numeric(df["low"], errors="coerce")
    df["volume"] = _pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)

    now = datetime.utcnow().isoformat()
    results = []

    for sym, grp in df.groupby("symbol", observed=True):
        grp = grp.sort_values("date").reset_index(drop=True)
        if len(grp) < 2:
            if len(grp) == 1:
                row = grp.iloc[0]
                results.append({"symbol": sym, "name": "", "price": float(row["close"]),
                    "volume": int(row["volume"]), "change_pct": 0.0,
                    "weighted_alpha": 0.0, "atr_signal": 0, "atr_stop": 0.0,
                    "atr_value": 0.0, "atr_streak": 0, "atr_crossed_above": 0,
                    "atr_crossed_below": 0, "atr_multiplier": ATR_MULTIPLIER, "streak": 0,
                    "next_day_return": 0.0, "prob_up_1d": 0.0, "prob_up_5d": 0.0,
                    "prob_up_st_cross": 0.0, "prob_up_1w": 50.0, "prob_up_1m": 50.0,
                    "pre_price": 0.0, "pre_change_pct": 0.0, "post_price": 0.0,
                    "post_change_pct": 0.0, "atrp": 0.0, "confluence": 0.0,
                    "accel_a": 0.0, "accel_base": 0.0, "accel_signal": 0,
                    "accel_crossed_up": 0, "accel_crossed_down": 0, "accel_streak": 0,
                    "st_bars_below": 0, "st_bars_above": 0,
                    "accel_bars_below": 0, "accel_bars_above": 0,
                    "atr_signal_w": 0, "atr_stop_w": 0.0, "atr_crossed_above_w": 0,
                    "atr_crossed_below_w": 0, "atr_streak_w": 0,
                    "st_bars_below_w": 0, "st_bars_above_w": 0,
                    "atr_signal_m": 0, "atr_stop_m": 0.0, "atr_crossed_above_m": 0,
                    "atr_crossed_below_m": 0, "atr_streak_m": 0,
                    "st_bars_below_m": 0, "st_bars_above_m": 0,
                    "last_updated": now,
                    "oldest_data": grp["date"].iloc[0].strftime("%Y-%m-%d") if hasattr(grp["date"].iloc[0], "strftime") else str(grp["date"].iloc[0])[:10],
                    "r_squared": 0.0,
                    "ai_overall_score": 0, "ai_bias": "neutral",
                    "ai_tech_score": 0, "ai_momentum_score": 0,
                    "ai_volume_score": 0, "ai_events_score": 0,
                    "ai_volume_profile_score": 0, "ai_trendline_score": 0,
                    "ai_sentiment_score": 0, "ai_conclusion": "HOLD", "ai_matrix": 0.0})
            continue

        try:
            c = grp["close"].astype(float)
            h = grp["high"].astype(float)
            l = grp["low"].astype(float)
            v = grp["volume"].astype(float)

            last_close = c.iloc[-1]
            prev_close = c.iloc[-2] if len(c) >= 2 else last_close
            change_pct = ((last_close - prev_close) / prev_close * 100) if prev_close > 0 else 0

            wa = _weighted_alpha(grp)
            wa_val = wa.iloc[-1] if len(wa) > 0 else 0

            st_result = _atr_trailing_stop(grp, period=14, multiplier=ATR_MULTIPLIER)
            st_trend = _si(st_result["trend"].iloc[-1]) if len(st_result) > 0 else 0
            st_signal = st_trend
            st_stop = _sf(st_result["stop"].iloc[-1]) if len(st_result) > 0 else 0
            st_atr = _sf(st_result["atr_value"].iloc[-1]) if len(st_result) > 0 else 0
            st_streak = _si(st_result["streak"].iloc[-1]) if len(st_result) > 0 else 0
            st_cross_up = _si(st_result["crossed_above"].iloc[-1]) if len(st_result) > 0 else 0
            st_cross_down = _si(st_result["crossed_below"].iloc[-1]) if len(st_result) > 0 else 0

            st_w_signal, st_w_stop, st_w_cross_up, st_w_cross_down = 0, 0.0, 0, 0
            st_w_streak, st_w_bars_below, st_w_bars_above = 0, 0, 0
            if len(grp) >= 7:
                try:
                    dates_arr = grp["date"].values
                    opens_arr = grp["open"].astype(float).values
                    highs_arr = grp["high"].astype(float).values
                    lows_arr = grp["low"].astype(float).values
                    closes_arr = grp["close"].astype(float).values
                    r = _compute_rolling_atr_trailing_stop(
                        dates_arr, opens_arr, highs_arr, lows_arr, closes_arr,
                        len(dates_arr) - 1, 5, period=14, multiplier=ATR_MULTIPLIER)
                    st_w_signal = r['trend']; st_w_stop = r['stop']
                    st_w_cross_up = r['crossed_above']; st_w_cross_down = r['crossed_below']
                    st_w_streak = r['streak']; st_w_bars_below = r['bars_below']
                    st_w_bars_above = r['bars_above']
                except Exception:
                    pass

            st_m_signal, st_m_stop, st_m_cross_up, st_m_cross_down = 0, 0.0, 0, 0
            st_m_streak, st_m_bars_below, st_m_bars_above = 0, 0, 0
            if len(grp) >= 24:
                try:
                    dates_arr = grp["date"].values
                    opens_arr = grp["open"].astype(float).values
                    highs_arr = grp["high"].astype(float).values
                    lows_arr = grp["low"].astype(float).values
                    closes_arr = grp["close"].astype(float).values
                    r = _compute_rolling_atr_trailing_stop(
                        dates_arr, opens_arr, highs_arr, lows_arr, closes_arr,
                        len(dates_arr) - 1, 22, period=14, multiplier=ATR_MULTIPLIER)
                    st_m_signal = r['trend']; st_m_stop = r['stop']
                    st_m_cross_up = r['crossed_above']; st_m_cross_down = r['crossed_below']
                    st_m_streak = r['streak']; st_m_bars_below = r['bars_below']
                    st_m_bars_above = r['bars_above']
                except Exception:
                    pass

            ac = _accel(grp)
            accel_a_val = _sf(ac["accel_a"].iloc[-1]) if len(ac) > 0 else 0
            accel_base_val = _sf(ac["accel_base"].iloc[-1]) if len(ac) > 0 else 0
            accel_signal_val = _si(ac["accel_signal"].iloc[-1]) if len(ac) > 0 else 0
            accel_cross_up = _si(ac["accel_crossed_up"].iloc[-1]) if len(ac) > 0 else 0
            accel_cross_down = _si(ac["accel_crossed_down"].iloc[-1]) if len(ac) > 0 else 0
            accel_streak_val = _si(ac["accel_streak"].iloc[-1]) if len(ac) > 0 else 0

            st_sig_full = st_result["trend"].fillna(0).astype(int).values if len(st_result) > 0 else _np.zeros(1, dtype=int)
            ac_sig_full = ac["accel_signal"].fillna(0).astype(int).values if len(ac) > 0 else _np.zeros(1, dtype=int)
            st_bas = _bars_at_side(st_sig_full)
            ac_bas = _bars_at_side(ac_sig_full)
            _st_bas_last = _si(st_bas[-1]) if len(st_bas) > 0 else 0
            _ac_bas_last = _si(ac_bas[-1]) if len(ac_bas) > 0 else 0
            st_bars_below_val = _st_bas_last if st_signal == 1 else 0
            st_bars_above_val = _st_bas_last if st_signal == -1 else 0
            accel_bars_below_val = _ac_bas_last if accel_signal_val == 1 else 0
            accel_bars_above_val = _ac_bas_last if accel_signal_val == -1 else 0

            atrp_val = _sf(_atrp(h, l, c).iloc[-1]) if len(h) > 0 else 0

            p1d = _prob_up(c, 1); p5d = _prob_up(c, 5)
            p1w = _prob_up(c, 5); p1m = _prob_up(c, 22)
            prob_1d = _sf(p1d.iloc[-1]) if len(p1d) > 0 else 50.0
            prob_5d = _sf(p5d.iloc[-1]) if len(p5d) > 0 else 50.0
            prob_1w = _sf(p1w.iloc[-1]) if len(p1w) > 0 else 50.0
            prob_1m = _sf(p1m.iloc[-1]) if len(p1m) > 0 else 50.0
            prob_st_cross_arr = _prob_up_after_st_cross_up(
                st_result["crossed_above"].fillna(0).astype(int).values,
                _next_day_return(c).values)
            prob_st_cross = _sf(prob_st_cross_arr[-1]) if len(prob_st_cross_arr) > 0 else 50.0

            ndr = _next_day_return(c)
            ndr_val = _sf(ndr.iloc[-2]) if len(ndr) >= 2 else 0
            streak_val = _si(_streak_vectorized(c)[-1]) if len(c) > 1 else 0
            r2_val = _sf(_r_squared(c, R_SQUARED_WINDOW).iloc[-1]) if len(c) > 1 else 0.0

            # Real vectorized AI scores (same model as historical/crypto rows)
            try:
                ai = _historical_ai_columns(grp)
                ai_overall = _sf(ai["ai_overall_score"].iloc[-1]) if len(ai) else 0.0
                ai_bias = str(ai["ai_bias"].iloc[-1]) if len(ai) else "neutral"
                ai_tech = _sf(ai["ai_tech_score"].iloc[-1]) if len(ai) else 0.0
                ai_mom = _sf(ai["ai_momentum_score"].iloc[-1]) if len(ai) else 0.0
                ai_vol = _sf(ai["ai_volume_score"].iloc[-1]) if len(ai) else 0.0
                ai_evt = _sf(ai["ai_events_score"].iloc[-1]) if len(ai) else 0.0
                ai_vp = _sf(ai["ai_volume_profile_score"].iloc[-1]) if len(ai) else 0.0
                ai_tl = _sf(ai["ai_trendline_score"].iloc[-1]) if len(ai) else 0.0
                ai_sent = _sf(ai["ai_sentiment_score"].iloc[-1]) if len(ai) else 0.0
                ai_conc = str(ai["ai_conclusion"].iloc[-1]) if len(ai) else "HOLD"
                ai_mat = ai["ai_matrix"].iloc[-1] if len(ai) else 0.0
            except Exception:
                (ai_overall, ai_bias, ai_tech, ai_mom, ai_vol, ai_evt,
                 ai_vp, ai_tl, ai_sent, ai_conc, ai_mat) = (
                    0.0, "neutral", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "HOLD", 0.0)

            row = {
                "symbol": sym, "price": float(last_close), "volume": _si(v.iloc[-1]),
                "change_pct": round(change_pct, 4), "weighted_alpha": round(wa_val, 4),
                "atr_signal": st_signal, "atr_stop": round(st_stop, 4),
                "atr_value": round(st_atr, 4), "atr_streak": st_streak,
                "atr_crossed_above": st_cross_up, "atr_crossed_below": st_cross_down,
                "atr_multiplier": ATR_MULTIPLIER, "streak": streak_val,
                "next_day_return": round(ndr_val, 4),
                "prob_up_1d": round(prob_1d, 2), "prob_up_5d": round(prob_5d, 2),
                "prob_up_st_cross": round(prob_st_cross, 2),
                "prob_up_1w": round(prob_1w, 2), "prob_up_1m": round(prob_1m, 2),
                "atrp": round(atrp_val, 4),
                "accel_a": round(accel_a_val, 6), "accel_base": round(accel_base_val, 6),
                "accel_signal": accel_signal_val, "accel_crossed_up": accel_cross_up,
                "accel_crossed_down": accel_cross_down, "accel_streak": accel_streak_val,
                "st_bars_below": st_bars_below_val, "st_bars_above": st_bars_above_val,
                "atr_signal_w": st_w_signal, "atr_stop_w": round(st_w_stop, 4),
                "atr_crossed_above_w": st_w_cross_up, "atr_crossed_below_w": st_w_cross_down,
                "atr_streak_w": st_w_streak, "st_bars_below_w": st_w_bars_below,
                "st_bars_above_w": st_w_bars_above,
                "atr_signal_m": st_m_signal, "atr_stop_m": round(st_m_stop, 4),
                "atr_crossed_above_m": st_m_cross_up, "atr_crossed_below_m": st_m_cross_down,
                "atr_streak_m": st_m_streak, "st_bars_below_m": st_m_bars_below,
                "st_bars_above_m": st_m_bars_above,
                "accel_bars_below": accel_bars_below_val, "accel_bars_above": accel_bars_above_val,
                "last_updated": now,
                "oldest_data": grp["date"].iloc[0].strftime("%Y-%m-%d") if hasattr(grp["date"].iloc[0], "strftime") else str(grp["date"].iloc[0])[:10],
                "r_squared": round(r2_val, 4),
                "ai_overall_score": ai_overall, "ai_bias": ai_bias,
                "ai_tech_score": ai_tech, "ai_momentum_score": ai_mom,
                "ai_volume_score": ai_vol, "ai_events_score": ai_evt,
                "ai_volume_profile_score": ai_vp, "ai_trendline_score": ai_tl,
                "ai_sentiment_score": ai_sent, "ai_conclusion": ai_conc,
                "ai_matrix": ai_mat,
            }
            row["confluence"] = _compute_confluence(row)
            results.append(row)
        except Exception:
            continue

    return results


def vectorized_stats_pass(market="US", only_symbols=None, progress_callback=None):
    """ONE vectorized pass over all daily bars to compute ALL stats columns.
    Uses ProcessPoolExecutor for true parallelism (bypasses GIL).
    If only_symbols is provided, only recompute those symbols (incremental).
    progress_callback(done, total) is called periodically."""

    from dumbmoney.indicators import compute_confluence

    conn = get_db(market)
    db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    try:
        if only_symbols is not None:
            if not only_symbols:
                return 0
            symbols = only_symbols
        else:
            symbols = [r[0] for r in conn.execute(
                "SELECT DISTINCT symbol FROM bars WHERE timeframe='1Day'"
            ).fetchall()]
    finally:
        conn.close()

    if not symbols:
        return 0

    total_groups = len(symbols)
    if progress_callback:
        progress_callback(0, total_groups)

    import multiprocessing as _mp
    n_workers = min(_mp.cpu_count(), 8)
    chunk_size = max(1, (len(symbols) + n_workers - 1) // n_workers)
    batches = []
    for i in range(0, len(symbols), chunk_size):
        batches.append((symbols[i:i+chunk_size], market, db_path))

    results = []
    batch_errors = []
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_compute_stats_batch, batch): batch for batch in batches}
        done = 0
        for f in as_completed(futures):
            try:
                batch_results = f.result()
                if batch_results:
                    results.extend(batch_results)
            except Exception as e:
                batch_errors.append(str(e))
                logger.warning(f"Stats batch worker failed: {e}")
            done += 1
            if progress_callback:
                progress_callback(done * chunk_size, total_groups)

    if progress_callback:
        progress_callback(total_groups, total_groups)

    if not results:
        if batch_errors:
            logger.error(f"All {len(batch_errors)} stats batches failed: {'; '.join(batch_errors[:3])}")
        return 0

    now = datetime.utcnow().isoformat()
    conn = get_db(market)
    try:
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA journal_size_limit = 67108864")

        batch_size = 2000
        for start in range(0, len(results), batch_size):
            chunk = results[start:start + batch_size]
            records = []
            for r in chunk:
                records.append((
                    r.get("symbol"), r.get("name", ""), r.get("price", 0), r.get("volume", 0),
                    r.get("change_pct", 0), r.get("atrp", 0), r.get("weighted_alpha", 0),
                    r.get("atr_signal", 0), r.get("atr_stop", 0), r.get("atr_value", 0),
                    r.get("atr_streak", 0), r.get("atr_crossed_above", 0), r.get("atr_crossed_below", 0),
                    r.get("atr_multiplier", ATR_MULTIPLIER), r.get("streak", 0),
                    r.get("next_day_return", 0), r.get("prob_up_1d", 50), r.get("prob_up_5d", 50),
                    r.get("prob_up_st_cross", 50), r.get("prob_up_1w", 50), r.get("prob_up_1m", 50),
                    now, r.get("oldest_data", ""),
                    r.get("accel_a", 0), r.get("accel_base", 0), r.get("accel_signal", 0),
                    r.get("accel_crossed_up", 0), r.get("accel_crossed_down", 0), r.get("accel_streak", 0),
                    r.get("confluence", 0),
                    r.get("st_bars_below", 0), r.get("st_bars_above", 0),
                    r.get("accel_bars_below", 0), r.get("accel_bars_above", 0),
                    r.get("atr_signal_w", 0), r.get("atr_stop_w", 0), r.get("atr_crossed_above_w", 0), r.get("atr_crossed_below_w", 0),
                    r.get("atr_streak_w", 0), r.get("st_bars_below_w", 0), r.get("st_bars_above_w", 0),
                    r.get("atr_signal_m", 0), r.get("atr_stop_m", 0), r.get("atr_crossed_above_m", 0), r.get("atr_crossed_below_m", 0),
                    r.get("atr_streak_m", 0), r.get("st_bars_below_m", 0), r.get("st_bars_above_m", 0),
                    r.get("r_squared", 0),
                ))
            # Upsert ONLY the indicator columns. A bare INSERT OR REPLACE used to
            # delete each row and re-insert it, wiping profit_*, pre/post prices,
            # asset metadata and pattern columns that other steps own.
            conn.executemany(
                """INSERT INTO stats (
                    symbol, name, price, volume, change_pct, atrp, weighted_alpha,
                    atr_signal, atr_stop, atr_value, atr_streak, atr_crossed_above, atr_crossed_below,
                    atr_multiplier, streak,
                    next_day_return, prob_up_1d, prob_up_5d, prob_up_st_cross, prob_up_1w, prob_up_1m,
                    last_updated, oldest_data,
                    accel_a, accel_base, accel_signal, accel_crossed_up, accel_crossed_down, accel_streak,
                    confluence,
                    st_bars_below, st_bars_above, accel_bars_below, accel_bars_above,
                    atr_signal_w, atr_stop_w, atr_crossed_above_w, atr_crossed_below_w, atr_streak_w, st_bars_below_w, st_bars_above_w,
                    atr_signal_m, atr_stop_m, atr_crossed_above_m, atr_crossed_below_m, atr_streak_m, st_bars_below_m, st_bars_above_m,
                    r_squared
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol) DO UPDATE SET
                    price=excluded.price, volume=excluded.volume, change_pct=excluded.change_pct,
                    atrp=excluded.atrp, weighted_alpha=excluded.weighted_alpha,
                    atr_signal=excluded.atr_signal, atr_stop=excluded.atr_stop, atr_value=excluded.atr_value,
                    atr_streak=excluded.atr_streak, atr_crossed_above=excluded.atr_crossed_above,
                    atr_crossed_below=excluded.atr_crossed_below, atr_multiplier=excluded.atr_multiplier,
                    streak=excluded.streak, next_day_return=excluded.next_day_return,
                    prob_up_1d=excluded.prob_up_1d, prob_up_5d=excluded.prob_up_5d,
                    prob_up_st_cross=excluded.prob_up_st_cross, prob_up_1w=excluded.prob_up_1w,
                    prob_up_1m=excluded.prob_up_1m,
                    last_updated=excluded.last_updated, oldest_data=excluded.oldest_data,
                    accel_a=excluded.accel_a, accel_base=excluded.accel_base, accel_signal=excluded.accel_signal,
                    accel_crossed_up=excluded.accel_crossed_up, accel_crossed_down=excluded.accel_crossed_down,
                    accel_streak=excluded.accel_streak, confluence=excluded.confluence,
                    st_bars_below=excluded.st_bars_below, st_bars_above=excluded.st_bars_above,
                    accel_bars_below=excluded.accel_bars_below, accel_bars_above=excluded.accel_bars_above,
                    atr_signal_w=excluded.atr_signal_w, atr_stop_w=excluded.atr_stop_w,
                    atr_crossed_above_w=excluded.atr_crossed_above_w, atr_crossed_below_w=excluded.atr_crossed_below_w,
                    atr_streak_w=excluded.atr_streak_w, st_bars_below_w=excluded.st_bars_below_w, st_bars_above_w=excluded.st_bars_above_w,
                    atr_signal_m=excluded.atr_signal_m, atr_stop_m=excluded.atr_stop_m,
                    atr_crossed_above_m=excluded.atr_crossed_above_m, atr_crossed_below_m=excluded.atr_crossed_below_m,
                    atr_streak_m=excluded.atr_streak_m, st_bars_below_m=excluded.st_bars_below_m, st_bars_above_m=excluded.st_bars_above_m,
                    r_squared=excluded.r_squared""",
                records
            )
            conn.commit()

        ai_batch_size = 2000
        for start in range(0, len(results), ai_batch_size):
            chunk = results[start:start + ai_batch_size]
            ai_records = [
                (r.get("symbol"), r.get("ai_overall_score", 0), r.get("ai_bias", "neutral"),
                 r.get("ai_tech_score", 0), r.get("ai_momentum_score", 0),
                 r.get("ai_volume_score", 0), r.get("ai_events_score", 0),
                 r.get("ai_volume_profile_score", 0), r.get("ai_trendline_score", 0),
                 r.get("ai_sentiment_score", 0), r.get("ai_conclusion", "HOLD"),
                 r.get("ai_matrix", ""), now)
                for r in chunk
            ]
            try:
                conn.executemany(
                    """INSERT OR REPLACE INTO ai_analysis (symbol, overall_score, bias, tech_score,
                       momentum_score, volume_score, events_score, volume_profile_score,
                       trendline_score, sentiment_score, conclusion, ai_matrix, computed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ai_records
                )
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()

    return len(results)


def update_asset_info(market="US", progress_callback=None, only_symbols=None):
    """Update asset info from assets table into stats."""
    conn = get_db(market)
    try:
        if only_symbols is not None and not only_symbols:
            if progress_callback:
                progress_callback(100, "No asset info changes")
            return
        if progress_callback:
            progress_callback(0, "Updating asset info...")

        if only_symbols is not None:
            requested = sorted(set(only_symbols))
            placeholders = ",".join("?" * len(requested))
            asset_rows = conn.execute(
                f"SELECT symbol, name, asset_class, exchange, status, tradable, fractionable, marginable "
                f"FROM assets WHERE symbol IN ({placeholders})",
                requested,
            ).fetchall()
            target_syms = requested
        else:
            asset_rows = conn.execute(
                "SELECT symbol, name, asset_class, exchange, status, tradable, fractionable, marginable FROM assets"
            ).fetchall()
            target_syms = [r[0] for r in conn.execute("SELECT symbol FROM stats").fetchall()]

        asset_map = {r[0]: r for r in asset_rows}
        records = []
        for sym in target_syms:
            a = asset_map.get(sym)
            if a:
                records.append((
                    a[1], a[2], a[3], a[4], a[5], a[6], a[7], sym
                ))

        if records:
            conn.executemany(
                """UPDATE stats SET
                    name = ?, asset_class = ?, exchange = ?, status = ?,
                    tradable = ?, fractionable = ?, marginable = ?
                   WHERE symbol = ?""",
                records
            )
            conn.commit()
        if progress_callback:
            progress_callback(100, "Asset info updated")
    finally:
        conn.close()


def _weighted_alpha_history(close_values, lookback=252):
    """Weighted Alpha for historical screener using Codex formula.

    4-bar SMA smoothing, 250 returns clipped to -6%/+5%, linear weights.
    Returns expanding-window array: each bar has WA computed using data up to that bar.
    For positions with fewer than 250 returns available, uses shorter lookback.
    """
    close = np.asarray(close_values, dtype=float)
    n = len(close)
    smooth = 4
    lb = 250
    if n < smooth + 2:
        return np.zeros(n, dtype=float)
    result = np.zeros(n, dtype=float)
    try:
        sma = np.convolve(close, np.ones(smooth) / smooth, mode="valid")
        if len(sma) < 2:
            return result
        rets = sma[1:] / sma[:-1] - 1.0
        effective_lb = min(lb, len(rets))
        if effective_lb < 2:
            return result
        clipped = np.clip(rets, -0.06, 0.05)
        scale = 100.0 / 0.75
        offset = effective_lb + smooth - 1
        full_w = np.linspace(0.5, 1.0, effective_lb)
        full_wn = full_w / full_w.mean()
        conv = np.convolve(clipped, full_wn, mode="valid")
        for j in range(len(conv)):
            pos = j + offset
            if pos < n:
                result[pos] = float(conv[j]) * scale
        for i in range(smooth, min(offset, n)):
            avail = i - smooth + 1
            if avail < 2:
                continue
            lb_use = min(lb, avail)
            r = clipped[avail - lb_use:avail]
            w = np.linspace(0.5, 1.0, lb_use)
            wn = w / w.mean()
            result[i] = float(np.dot(r, wn)) * scale
    except Exception:
        pass
    return result


def _sigmoid_map_vec(raw, steepness=5.0):
    """Vectorized sigmoid mapping: raw in [-1, 1] -> score in [0, 100]."""
    raw = np.asarray(raw, dtype=float)
    return pd.Series((1 / (1 + np.exp(-steepness * raw)) * 100).clip(0, 100))


def _historical_ai_columns(grp):
    if len(grp) < 30:
        return pd.DataFrame({
            "ai_overall_score": 0.0,
            "ai_bias": "neutral",
            "ai_tech_score": 0.0,
            "ai_momentum_score": 0.0,
            "ai_volume_score": 0.0,
            "ai_events_score": 0.0,
            "ai_volume_profile_score": 0.0,
            "ai_trendline_score": 0.0,
            "ai_sentiment_score": 0.0,
            "ai_conclusion": "HOLD",
        }, index=grp.index)

    c = grp["close"].astype(float)
    o = grp["open"].astype(float) if "open" in grp.columns else c
    h = grp["high"].astype(float)
    l = grp["low"].astype(float)
    v = grp["volume"].astype(float).replace(0, np.nan)

    rsi = rsi_wilder(c, 14)
    sma20 = c.rolling(20, min_periods=1).mean()
    sma50 = c.rolling(50, min_periods=1).mean()

    sma20_pct = (c - sma20) / (sma20 + 1e-10) * 100
    sma50_pct = (c - sma50) / (sma50 + 1e-10) * 100
    sma_spread = (sma20 - sma50) / (sma50 + 1e-10) * 100

    trend_raw = np.clip(
        0.4 * np.tanh(sma20_pct / 5.0) +
        0.3 * np.tanh(sma50_pct / 5.0) +
        0.3 * np.tanh(sma_spread / 3.0),
        -1, 1
    )
    rsi_raw = np.clip((rsi - 50.0) / 30.0, -1, 1)
    rsi_raw = np.where(rsi > 80, -0.3, np.where(rsi < 20, -0.2, rsi_raw))
    tech_raw = 0.6 * trend_raw + 0.4 * rsi_raw
    tech = _sigmoid_map_vec(tech_raw, 4.5)

    pct_3d = c.pct_change(3).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
    pct_5d = c.pct_change(5).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
    pct_20d = c.pct_change(20).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
    recent_up = (c.diff() > 0).rolling(10, min_periods=1).mean()

    mom_raw = np.clip(
        0.25 * np.tanh(pct_3d / 3.0) +
        0.30 * np.tanh(pct_5d / 5.0) +
        0.25 * np.tanh(pct_20d / 10.0) +
        0.20 * (recent_up - 0.5) * 2.0,
        -1, 1
    )
    momentum = _sigmoid_map_vec(mom_raw, 4.5)

    vol_avg_20 = v.rolling(20, min_periods=1).mean()
    vol_avg_5 = v.rolling(5, min_periods=1).mean()
    vol_ratio = vol_avg_5 / (vol_avg_20 + 1e-10)
    price_up = c > c.shift(1)
    vol_direction = np.tanh((vol_ratio - 1.0) * 3.0) * np.where(price_up, 1.0, -0.6)
    vol_raw = np.clip(vol_direction, -1, 1)
    volume_score = _sigmoid_map_vec(vol_raw, 4.5)

    low20 = l.rolling(20, min_periods=1).min()
    high20 = h.rolling(20, min_periods=1).max()
    price_pos = ((c - low20) / (high20 - low20 + 1e-10)).fillna(0.5)
    vp_raw = np.clip(price_pos * 2.0 - 1.0, -1, 1)
    volume_profile = _sigmoid_map_vec(vp_raw, 4.0)

    hh = h.rolling(20, min_periods=1).max()
    ll = l.rolling(20, min_periods=1).min()
    hl = l.rolling(20, min_periods=1).max()
    trend_raw2 = np.clip(
        np.tanh((hh - hh.shift(19).fillna(hh)) / (hh + 1e-10) * 100) * 0.5 +
        np.tanh((ll - ll.shift(19).fillna(ll)) / (ll + 1e-10) * 100) * 0.5,
        -1, 1
    )
    trendline = _sigmoid_map_vec(trend_raw2, 4.0)

    sentiment = _sigmoid_map_vec(np.clip(
        0.5 * np.tanh((rsi - 55) / 15) + 0.5 * np.tanh((vol_ratio - 1.0) * 2) * np.sign(pct_5d),
        -1, 1
    ), 4.0)

    events_score = pd.Series(50.0, index=grp.index)
    overall = (
        tech * 0.20 + momentum * 0.25 + volume_score * 0.15 +
        volume_profile * 0.10 + trendline * 0.10 + sentiment * 0.10 + events_score * 0.10
    ).clip(0, 100)
    bias = np.where(overall > 65, "bullish", np.where(overall < 35, "bearish", "neutral"))
    conclusion = np.where(overall > 65, "BUY", np.where(overall < 35, "SELL", "HOLD"))

    return pd.DataFrame({
        "ai_overall_score": overall.round(2),
        "ai_bias": bias,
        "ai_tech_score": tech.round(2),
        "ai_momentum_score": momentum.round(2),
        "ai_volume_score": volume_score.round(2),
        "ai_events_score": events_score.round(2),
        "ai_volume_profile_score": volume_profile.round(2),
        "ai_trendline_score": trendline.round(2),
        "ai_sentiment_score": sentiment.round(2),
        "ai_conclusion": conclusion,
        "ai_matrix": [
            "T{}_V{}_M{}_S{}".format(
                int(t) if not np.isnan(t) else 0,
                int(v) if not np.isnan(v) else 0,
                int(m) if not np.isnan(m) else 0,
                int(s) if not np.isnan(s) else 0,
            )
            for t, v, m, s in zip(tech.round(0), volume_profile.round(0), momentum.round(0), sentiment.round(0))
        ],
    })


def _compute_historical_symbol_frame(grp):
    grp = grp.sort_values("date").reset_index(drop=True).copy()
    c = grp["close"].astype(float)
    h = grp["high"].astype(float)
    l = grp["low"].astype(float)
    v = grp["volume"].replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)
    st = atr_trailing_stop(grp, period=14, multiplier=ATR_MULTIPLIER)
    ac = accel(grp)
    ai = _historical_ai_columns(grp)

    out = pd.DataFrame({
        "symbol": grp["symbol"],
        "date": pd.to_datetime(grp["date"]).dt.strftime("%Y-%m-%d"),
        "price": c,
        "change_pct": c.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0) * 100,
        "volume": v,
        "weighted_alpha": _weighted_alpha_history(c.values),
        "atrp": atrp(h, l, c),
        "streak": streak_vectorized(c),
        "atr_value": st["atr_value"].fillna(0),
        "atr_stop": st["stop"].fillna(0),
        "atr_signal": st["trend"].fillna(0).replace([np.inf, -np.inf], np.nan).fillna(0).astype(int),
        "atr_crossed_above": st["crossed_above"].fillna(0).replace([np.inf, -np.inf], np.nan).fillna(0).astype(int),
        "atr_crossed_below": st["crossed_below"].fillna(0).replace([np.inf, -np.inf], np.nan).fillna(0).astype(int),
        "atr_streak": st["streak"].fillna(0).replace([np.inf, -np.inf], np.nan).fillna(0).astype(int),
        "atr_multiplier": ATR_MULTIPLIER,
    })
    out = pd.concat([out, ai], axis=1)
    # prob_up_st_cross must come before accel columns to match HISTORICAL_SCREENER_COLUMNS order
    out["next_day_return"] = c.shift(-1).sub(c).div(c).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
    out["next_5d_return"] = c.shift(-5).sub(c).div(c).replace([np.inf, -np.inf], np.nan).fillna(0) * 100
    out["prob_up_1d"] = prob_up(c, 1).fillna(50.0)
    out["prob_up_5d"] = prob_up(c, 5).fillna(50.0)
    out["prob_up_1w"] = prob_up(c, 5).fillna(50.0)
    out["prob_up_1m"] = prob_up(c, 22).fillna(50.0)
    out["prob_up_st_cross"] = prob_up_after_st_cross_up(
        st["crossed_above"].fillna(0).values,
        out["next_day_return"].values,
    )
    out["r_squared"] = r_squared(c, R_SQUARED_WINDOW)
    out["accel_a"] = ac["accel_a"].fillna(0)
    out["accel_base"] = ac["accel_base"].fillna(0)
    out["accel_signal"] = ac["accel_signal"].fillna(0).replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)
    out["accel_crossed_up"] = ac["accel_crossed_up"].fillna(0).replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)
    out["accel_crossed_down"] = ac["accel_crossed_down"].fillna(0).replace([np.inf, -np.inf], np.nan).fillna(0).astype(int)
    # Compute bars_at_side for historical data
    _st_sig = out["atr_signal"].values.astype(np.int32)
    _ac_sig = out["accel_signal"].values.astype(np.int32)
    _st_bas = bars_at_side(_st_sig)
    _ac_bas = bars_at_side(_ac_sig)
    out["st_bars_below"] = np.where(_st_sig == 1, _st_bas, 0).astype(int)
    out["st_bars_above"] = np.where(_st_sig == -1, _st_bas, 0).astype(int)
    out["accel_bars_below"] = np.where(_ac_sig == 1, _ac_bas, 0).astype(int)
    out["accel_bars_above"] = np.where(_ac_sig == -1, _ac_bas, 0).astype(int)

    # Anchored rolling weekly (5 sessions) and monthly (22 sessions)
    for sessions, suffix in [(5, "_w"), (22, "_m")]:
        try:
            dates_arr = grp["date"].values
            opens_arr = grp["open"].astype(float).values
            highs_arr = grp["high"].astype(float).values
            lows_arr = grp["low"].astype(float).values
            closes_arr = grp["close"].astype(float).values

            w_trends, w_stops, w_atrs, w_streaks, w_cross_above, w_cross_below, w_bars_bl, w_bars_ab = \
                compute_rolling_atr_batch(dates_arr, opens_arr, highs_arr, lows_arr, closes_arr,
                                          sessions, period=14, multiplier=ATR_MULTIPLIER)

            out[f"atr_signal{suffix}"] = w_trends
            out[f"atr_stop{suffix}"] = w_stops
            out[f"atr_crossed_above{suffix}"] = w_cross_above
            out[f"atr_crossed_below{suffix}"] = w_cross_below
            out[f"atr_streak{suffix}"] = w_streaks
            out[f"st_bars_below{suffix}"] = w_bars_bl
            out[f"st_bars_above{suffix}"] = w_bars_ab
        except Exception:
            for col in ["atr_signal", "atr_stop", "atr_crossed_above", "atr_crossed_below", "atr_streak", "st_bars_below", "st_bars_above"]:
                out[f"{col}{suffix}"] = 0

    out["confluence"] = compute_confluence_vectorized(
        out["atr_signal"].values, out["accel_signal"].values,
        out["weighted_alpha"].values, out["streak"].values, out["prob_up_1d"].values
    )
    sma20 = c.rolling(20, min_periods=1).mean()
    sma50 = c.rolling(50, min_periods=1).mean()
    vol_avg20 = v.astype(float).rolling(20, min_periods=1).mean()
    vol_avg5 = v.astype(float).rolling(5, min_periods=1).mean()
    vol_ratio = (vol_avg5 / (vol_avg20 + 1e-10)).fillna(1.0)
    vol_spike = (v.astype(float) > 3.0 * vol_avg20).fillna(False)
    h20 = h.rolling(20, min_periods=1).max()
    l20 = l.rolling(20, min_periods=1).min()
    # Vectorized AI matrix score (replaces row-by-row _compute_ai_matrix_score loop)
    rsi_vec = rsi_wilder(c, 14).fillna(50).values.astype(float)
    wa_vec = out["weighted_alpha"].fillna(0).values.astype(float)
    sk_vec = out["streak"].fillna(0).values.astype(float)
    st_sig = out["atr_signal"].fillna(0).values.astype(float)
    ac_sig = out["accel_signal"].fillna(0).values.astype(float)
    st_xa = out["atr_crossed_above"].fillna(0).values.astype(bool)
    st_xb = out["atr_crossed_below"].fillna(0).values.astype(bool)
    ac_cu = out["accel_crossed_up"].fillna(0).values.astype(bool)
    ac_cd = out["accel_crossed_down"].fillna(0).values.astype(bool)
    at_vec = out["atrp"].fillna(0).values.astype(float)
    p1_vec = out["prob_up_1d"].fillna(50).values.astype(float)
    vr_vec = vol_ratio.values.astype(float)
    vs_vec = vol_spike.values.astype(bool)
    pr_vec = c.values.astype(float)
    hh_vec = h20.values.astype(float)
    ll_vec = l20.values.astype(float)
    s20_vec = sma20.values.astype(float)
    s50_vec = sma50.values.astype(float)

    _clip = np.clip
    _tanh = np.tanh
    _log = np.log
    _sig_v = lambda x: 1.0 / (1.0 + np.exp(_clip(x, -500.0, 500.0)))

    # D — Directional
    wa_norm = _tanh(wa_vec / 15.0)
    streak_amp = 1.0 + 0.3 * _tanh(sk_vec / 3.0)
    wa_component = wa_norm * streak_amp
    trend_component = (st_sig + ac_sig) * 0.5
    rsi_component = (rsi_vec - 50.0) / 20.0
    D = (wa_component + trend_component + rsi_component) / 3.0

    # X — Crossover freshness
    raw_cross = st_sig + ac_sig
    any_cross = st_xa | st_xb | ac_cu | ac_cd
    boost = 1.0 + 0.5 * any_cross.astype(float)
    X = raw_cross * 0.5 * boost

    # V — Volume confirmation
    log_ratio = _log(np.maximum(vr_vec, 0.01))
    spike_impulse = 0.3 * vs_vec.astype(float)
    V = _tanh((log_ratio + spike_impulse) * 2.0)

    # B — Oversold bounce
    oversold = _sig_v((50.0 - rsi_vec) / 10.0)
    vol_confirm = _sig_v((at_vec - 3.0) / 1.5)
    B = oversold * vol_confirm * 2.0 - 1.0

    # P — Probability log-odds
    p_clipped = _clip(p1_vec / 100.0, 1e-6, 1.0 - 1e-6)
    P = np.log(p_clipped / (1.0 - p_clipped))

    # Weighted sum
    z = 1.20 * D + 0.40 * X + 0.35 * V + 0.25 * B + 0.30 * P

    # MA trend bias
    ma_valid = (s20_vec > 0) & (s50_vec > 0)
    z = np.where(ma_valid, z + 0.15 * _tanh((s20_vec - s50_vec) / (0.05 * s50_vec + 1e-9)), z)

    # Price position reinforcement
    rng_valid = (hh_vec > ll_vec) & (pr_vec > 0)
    pos = np.where(rng_valid, (pr_vec - ll_vec) / (hh_vec - ll_vec + 1e-9), 0.0)
    range_hint = 0.10 * (pos - 0.5) * 2.0
    aligned = ((wa_vec > 0) & (pos > 0.5)) | ((wa_vec < 0) & (pos < 0.5))
    z = np.where(rng_valid & aligned, z + range_hint, z)
    z = np.where(rng_valid & ~aligned, z - range_hint * 0.5, z)

    out["ai_matrix"] = np.round(100.0 * _sig_v(z), 2)
    numeric_cols = [cname for cname in out.columns if cname not in {"symbol", "date", "ai_bias", "ai_conclusion", "ai_matrix"}]
    out[numeric_cols] = out[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
    return out[HISTORICAL_SCREENER_COLUMNS]


def _compute_symbol_batch(args):
    """Top-level worker function for multiprocessing. Process a batch of symbols."""
    batch_syms, db_path, existing_map, requested, version_mismatch, force_rebuild = args
    import sqlite3 as _sqlite3
    import pandas as _pd
    from datetime import timedelta

    conn = _sqlite3.connect(db_path, timeout=30)
    try:
        incremental_syms = []
        full_rebuild_syms = []
        for sym in batch_syms:
            if version_mismatch or force_rebuild or not existing_map.get(sym):
                full_rebuild_syms.append(sym)
            else:
                incremental_syms.append(sym)

        bars = _pd.DataFrame()
        if full_rebuild_syms:
            placeholders_f = ",".join("?" * len(full_rebuild_syms))
            bars_full = _pd.read_sql(
                f"""SELECT symbol, date, open, high, low, close, volume FROM bars
                    WHERE timeframe='1Day' AND symbol IN ({placeholders_f})
                    ORDER BY symbol, date""",
                conn, params=full_rebuild_syms,
            )
            bars = bars_full if bars.empty else _pd.concat([bars, bars_full], ignore_index=True)

        if incremental_syms:
            warmup_cutoffs = []
            for sym in incremental_syms:
                last_hist = existing_map.get(sym, "")
                if last_hist:
                    try:
                        dt = datetime.strptime(last_hist, "%Y-%m-%d")
                        cutoff = (dt - timedelta(days=500)).strftime("%Y-%m-%d")
                    except Exception:
                        cutoff = "1970-01-01"
                else:
                    cutoff = "1970-01-01"
                warmup_cutoffs.append(cutoff)
            batch_cutoff = min(warmup_cutoffs) if warmup_cutoffs else "1970-01-01"
            placeholders_i = ",".join("?" * len(incremental_syms))
            bars_incr = _pd.read_sql(
                f"""SELECT symbol, date, open, high, low, close, volume FROM bars
                    WHERE timeframe='1Day' AND symbol IN ({placeholders_i})
                    AND date > ?
                    ORDER BY symbol, date""",
                conn, params=incremental_syms + [batch_cutoff],
            )
            bars = bars_incr if bars.empty else _pd.concat([bars, bars_incr], ignore_index=True)

        if bars.empty:
            return []
        records = []
        for _, grp in bars.groupby("symbol", sort=False):
            if len(grp) < 2:
                continue
            sym = str(grp["symbol"].iloc[0])
            try:
                last_hist_date = existing_map.get(sym)
                if not version_mismatch and not force_rebuild and last_hist_date:
                    new_bars = grp[grp["date"] > last_hist_date]
                    if new_bars.empty:
                        continue
                    num_new = len(new_bars)
                    grp_sliced = grp.tail(num_new + 320).copy()
                    hist = _compute_historical_symbol_frame(grp_sliced)
                    # Look back 5 days to recompute next_day_return for recent rows
                    # (new bars may change the next_day_return of the previous day)
                    from datetime import timedelta as _td, datetime as _dt
                    try:
                        _ld = _dt.strptime(str(last_hist_date)[:10], "%Y-%m-%d")
                        lookback = (_ld - _td(days=5)).strftime("%Y-%m-%d")
                    except Exception:
                        lookback = str(last_hist_date)[:10]
                    hist = hist[hist["date"] >= lookback]
                else:
                    hist = _compute_historical_symbol_frame(grp)
                if not hist.empty:
                    records.extend([tuple(r) for r in hist.itertuples(index=False, name=None)])
            except Exception:
                continue
        return records
    finally:
        conn.close()


def update_historical_screener(market="US", progress_callback=None, only_symbols=None, force_rebuild=False, cancel_check=None, parallel=None):
    """Fill historical_screener with true as-of-date indicator values."""
    conn = get_db(market)
    try:
        if progress_callback:
            progress_callback(0, "Checking historical screener state...")

        requested = None
        if only_symbols is not None:
            requested = sorted(set(only_symbols))
            if not requested:
                if progress_callback:
                    progress_callback(100, "Historical screener already current")
                return

        version_row = conn.execute(
            "SELECT value FROM settings WHERE key='historical_screener_version'"
        ).fetchone()
        version_mismatch = not version_row or version_row[0] != HISTORICAL_SCREENER_VERSION
        needs_rebuild = force_rebuild or (version_mismatch and only_symbols is None)

        if needs_rebuild:
            conn.execute("DELETE FROM historical_screener")
            conn.execute("DELETE FROM signal_prob_matrix")
            conn.commit()

        if requested:
            placeholders_req = ",".join("?" * len(requested))
            existing = conn.execute(
                f"""SELECT symbol, MAX(date) as max_date
                    FROM historical_screener
                    WHERE symbol IN ({placeholders_req})
                    GROUP BY symbol""",
                requested,
            ).fetchall()
        else:
            existing = conn.execute(
                "SELECT symbol, MAX(date) as max_date FROM historical_screener GROUP BY symbol"
            ).fetchall()
        existing_map = {row[0]: row[1] for row in existing}

        if requested:
            placeholders2 = ",".join("?" * len(requested))
            max_rows = conn.execute(
                f"""SELECT symbol, MAX(date)
                    FROM bars
                    WHERE timeframe='1Day' AND symbol IN ({placeholders2})
                    GROUP BY symbol""",
                requested,
            ).fetchall()
            all_symbols = [
                row[0] for row in max_rows
                if version_mismatch or force_rebuild or existing_map.get(row[0]) != row[1]
            ]
        else:
            max_rows = conn.execute(
                "SELECT symbol, MAX(date) FROM bars WHERE timeframe='1Day' GROUP BY symbol"
            ).fetchall()
            all_symbols = [
                row[0] for row in max_rows
                if needs_rebuild or existing_map.get(row[0]) != row[1]
            ]

        if not all_symbols:
            if progress_callback:
                progress_callback(100, "Historical screener already current")
            return

        total_syms = len(all_symbols)
        total_rows = 0
        batch_size = 200
        cols_str = ", ".join(HISTORICAL_SCREENER_COLUMNS)
        placeholders = ",".join(["?"] * len(HISTORICAL_SCREENER_COLUMNS))
        insert_sql = f"INSERT OR REPLACE INTO historical_screener ({cols_str}) VALUES ({placeholders})"

        if progress_callback:
            mode = "full rebuild" if needs_rebuild else "incremental"
            progress_callback(5, f"Historical screener {mode}: {total_syms} symbols")

        num_workers = min(os.cpu_count() or 4, 8)
        if parallel is not None:
            use_parallel = parallel
        else:
            use_parallel = True  # Default: use parallel on all platforms

        if use_parallel:
            import multiprocessing
            try:
                multiprocessing.set_start_method("spawn", force=True)
            except RuntimeError:
                pass
            from dumbmoney.config import DB_PATHS
            db_path = DB_PATHS.get(market, DB_PATHS["US"])
            batches = [all_symbols[i:i + batch_size] for i in range(0, total_syms, batch_size)]
            total_batches = len(batches)
            batch_args = [
                (batch, db_path, existing_map, requested, version_mismatch, force_rebuild)
                for batch in batches
            ]

            done_batches = 0
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(_compute_symbol_batch, a) for a in batch_args]
                for future in as_completed(futures):
                    if cancel_check and cancel_check():
                        executor.shutdown(wait=False, cancel_futures=True)
                        if progress_callback:
                            progress_callback(100, "Cancelled")
                        return
                    done_batches += 1
                    try:
                        records = future.result(timeout=600)
                        if records:
                            for j in range(0, len(records), 50000):
                                conn.executemany(insert_sql, records[j:j + 50000])
                                conn.commit()
                            total_rows += len(records)
                    except Exception as e:
                        logger.warning(f"Worker batch error: {e}")
                    if progress_callback and done_batches % max(1, total_batches // 20) == 0:
                        progress_callback(15 + round(done_batches / total_batches * 75), f"Processing: {done_batches}/{total_batches} batches ({total_rows:,} rows)")
        else:
            for i in range(0, total_syms, batch_size):
                if cancel_check and cancel_check():
                    if progress_callback:
                        progress_callback(100, "Cancelled")
                    return
                batch_syms = all_symbols[i:i + batch_size]
                done = min(i + batch_size, total_syms)
                if progress_callback:
                    progress_callback(15 + round(done / total_syms * 75), f"Processing: {done}/{total_syms} symbols ({total_rows:,} rows)")

                incremental_in_batch = []
                full_rebuild_in_batch = []
                for sym in batch_syms:
                    if version_mismatch or force_rebuild or not existing_map.get(sym):
                        full_rebuild_in_batch.append(sym)
                    else:
                        incremental_in_batch.append(sym)

                bars = pd.DataFrame()
                if full_rebuild_in_batch:
                    placeholders_f = ",".join("?" * len(full_rebuild_in_batch))
                    bars_full = pd.read_sql(
                        f"""SELECT symbol, date, open, high, low, close, volume FROM bars
                            WHERE timeframe='1Day' AND symbol IN ({placeholders_f})
                            ORDER BY symbol, date""",
                        conn, params=full_rebuild_in_batch,
                    )
                    bars = bars_full if bars.empty else pd.concat([bars, bars_full], ignore_index=True)

                if incremental_in_batch:
                    warmup_cutoffs = []
                    for sym in incremental_in_batch:
                        last_hist = existing_map.get(sym, "")
                        if last_hist:
                            try:
                                dt = datetime.strptime(last_hist, "%Y-%m-%d")
                                from datetime import timedelta
                                cutoff = (dt - timedelta(days=500)).strftime("%Y-%m-%d")
                            except Exception:
                                cutoff = "1970-01-01"
                        else:
                            cutoff = "1970-01-01"
                        warmup_cutoffs.append(cutoff)
                    batch_cutoff = min(warmup_cutoffs) if warmup_cutoffs else "1970-01-01"
                    placeholders_i = ",".join("?" * len(incremental_in_batch))
                    bars_incr = pd.read_sql(
                        f"""SELECT symbol, date, open, high, low, close, volume FROM bars
                            WHERE timeframe='1Day' AND symbol IN ({placeholders_i})
                            AND date > ?
                            ORDER BY symbol, date""",
                        conn, params=incremental_in_batch + [batch_cutoff],
                    )
                    bars = bars_incr if bars.empty else pd.concat([bars, bars_incr], ignore_index=True)

                if bars.empty:
                    continue

                records = []
                for _, grp in bars.groupby("symbol", sort=False):
                    if len(grp) < 2:
                        continue
                    sym = str(grp["symbol"].iloc[0])
                    try:
                        last_hist_date = existing_map.get(sym)
                        if not version_mismatch and not force_rebuild and last_hist_date:
                            # Incremental: only compute new bars
                            new_bars = grp[grp["date"] > last_hist_date]
                            if new_bars.empty:
                                continue
                            num_new = len(new_bars)
                            grp_sliced = grp.tail(num_new + 320).copy()
                            hist = _compute_historical_symbol_frame(grp_sliced)
                            # Look back 5 days to recompute next_day_return for recent rows
                            from datetime import timedelta as _td2, datetime as _dt2
                            try:
                                _ld2 = _dt2.strptime(str(last_hist_date)[:10], "%Y-%m-%d")
                                lookback2 = (_ld2 - _td2(days=5)).strftime("%Y-%m-%d")
                            except Exception:
                                lookback2 = str(last_hist_date)[:10]
                            hist = hist[hist["date"] >= lookback2]
                        else:
                            # Full compute (first time or version mismatch)
                            hist = _compute_historical_symbol_frame(grp)

                        if not hist.empty:
                            records.extend([tuple(r) for r in hist.itertuples(index=False, name=None)])
                    except Exception as e:
                        logger.warning(f"Error computing historical stats for {sym}: {e}")
                        continue

                if records:
                    for j in range(0, len(records), 50000):
                        conn.executemany(insert_sql, records[j:j + 50000])
                        conn.commit()
                    total_rows += len(records)

        if only_symbols is None:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('historical_screener_version', ?)",
                (HISTORICAL_SCREENER_VERSION,),
            )
            conn.commit()

        if progress_callback:
            progress_callback(100, f"History filled ({total_rows:,} rows)")
    finally:
        conn.close()


def update_signal_prob_matrix(market="US", progress_callback=None):
    """Recompute signal probability matrix from historical_screener."""
    conn = get_db(market)
    try:
        if progress_callback:
            progress_callback(0, "Computing signal probabilities...")
        rows = conn.execute(
            """
            WITH src AS (
              SELECT
                CASE
                  WHEN atr_signal = 1 THEN 'cross_up'
                  WHEN atr_signal = -1 THEN 'cross_down'
                  WHEN atr_signal = 0 AND atr_streak > 0 THEN 'in_uptrend'
                  WHEN atr_signal = 0 AND atr_streak < 0 THEN 'in_downtrend'
                  ELSE 'neutral'
                END AS st_state,
                CASE
                  WHEN accel_crossed_up = 1 THEN 'cross_up'
                  WHEN accel_crossed_down = 1 THEN 'cross_down'
                  WHEN accel_signal = 1 THEN 'accel_up'
                  WHEN accel_signal = -1 THEN 'accel_down'
                  ELSE 'neutral'
                END AS accel_state,
                CASE
                  WHEN weighted_alpha > 50 THEN '>50'
                  WHEN weighted_alpha > 20 AND weighted_alpha <= 50 THEN '20-50'
                  WHEN weighted_alpha > 0 AND weighted_alpha <= 20 THEN '0-20'
                  ELSE '<0'
                END AS wa_bucket,
                next_day_return AS ndr
              FROM historical_screener
              WHERE next_day_return IS NOT NULL
            )
            SELECT st_state, accel_state, wa_bucket,
                   COUNT(*) AS sample_count,
                   AVG(CASE WHEN ndr > 0 THEN 1.0 ELSE 0.0 END) * 100.0 AS prob_up_1d,
                   AVG(CASE WHEN ndr > 1 THEN 1.0 ELSE 0.0 END) * 100.0 AS prob_up_1pct,
                   AVG(CASE WHEN ndr > 2 THEN 1.0 ELSE 0.0 END) * 100.0 AS prob_up_2pct,
                   AVG(CASE WHEN ndr < -2 THEN 1.0 ELSE 0.0 END) * 100.0 AS prob_down_2pct,
                   AVG(ndr) AS avg_next_day_return,
                   AVG(ndr * ndr) AS avg_square_return
            FROM src
            GROUP BY st_state, accel_state, wa_bucket
            HAVING COUNT(*) >= 10
            """
        ).fetchall()
        if not rows:
            return
        if progress_callback:
            progress_callback(70, "Saving probability matrix...")
        conn.execute("DELETE FROM signal_prob_matrix")
        out_rows = []
        for row in rows:
            st_state, accel_state, wa_bucket, sample_count, p_up, p_up1, p_up2, p_dn2, avg_ret, avg_sq = row
            variance = max(float(avg_sq or 0) - float(avg_ret or 0) ** 2, 0.0)
            sharpe = float(avg_ret or 0) / (float(np.sqrt(variance)) + 1e-10)
            out_rows.append((
                st_state, accel_state, wa_bucket,
                round(float(p_up or 0), 2),
                round(float(p_up1 or 0), 2),
                round(float(p_up2 or 0), 2),
                round(float(p_dn2 or 0), 2),
                int(sample_count),
                round(float(avg_ret or 0), 4),
                round(sharpe, 4),
            ))
        conn.executemany(
            """INSERT OR REPLACE INTO signal_prob_matrix (st_state, accel_state, wa_bucket,
               prob_up_1d, prob_up_1pct, prob_up_2pct, prob_down_2pct,
               sample_count, avg_next_day_return, sharpe)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            out_rows
        )
        conn.commit()
        if progress_callback:
            progress_callback(100, "Signal probability matrix updated")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CRYPTO screener batch computation (mirrors USA vectorized_stats_pass)
# ---------------------------------------------------------------------------

CRYPTO_HISTORICAL_SCREENER_COLUMNS = [
    "symbol", "date", "price", "change_pct", "volume",
    "weighted_alpha", "atrp", "streak", "atr_value", "atr_stop", "atr_signal",
    "atr_crossed_above", "atr_crossed_below", "atr_streak",
    "next_day_return", "prob_up_1d", "prob_up_5d", "prob_up_1w", "prob_up_1m",
    "prob_up_st_cross",
    "accel_a", "accel_base", "accel_signal", "accel_crossed_up", "accel_crossed_down",
    "confluence",
    "st_bars_below", "st_bars_above", "accel_bars_below", "accel_bars_above",
    "atr_signal_w", "atr_stop_w", "atr_crossed_above_w", "atr_crossed_below_w", "atr_streak_w",
    "atr_signal_m", "atr_stop_m", "atr_crossed_above_m", "atr_crossed_below_m", "atr_streak_m",
    "ai_overall_score", "ai_bias", "ai_tech_score", "ai_momentum_score",
    "ai_volume_score", "ai_events_score", "ai_volume_profile_score",
    "ai_trendline_score", "ai_sentiment_score", "ai_conclusion", "ai_matrix",
]

# crypto-v2: ATR trailing stop multiplier 1.0 -> 2.0 (matches equities)
CRYPTO_STATS_VERSION = "crypto-v2"


def _compute_crypto_stats_batch(batch_args):
    """Worker for ProcessPoolExecutor. Computes all stats for a batch of crypto symbols.
    Each worker opens its own DB connection (WAL allows concurrent readers)."""
    symbol_list, db_path = batch_args

    import math
    import sqlite3 as _sqlite3
    import pandas as _pd
    import numpy as _np
    from datetime import datetime as _dt

    from dumbmoney.indicators import (
        atr_trailing_stop as _atr_trailing_stop, accel as _accel,
        weighted_alpha as _weighted_alpha, prob_up as _prob_up,
        prob_up_after_st_cross_up as _prob_up_after_st_cross_up,
        streak_vectorized as _streak_vectorized, atrp as _atrp,
        bars_at_side as _bars_at_side,
        compute_confluence as _compute_confluence,
        compute_rolling_atr_trailing_stop as _compute_rolling_atr_trailing_stop,
    )

    def _si(v):
        try:
            f = float(v)
            return 0 if math.isnan(f) or math.isinf(f) else int(f)
        except (TypeError, ValueError):
            return 0

    def _sf(v):
        try:
            f = float(v)
            return 0.0 if math.isnan(f) or math.isinf(f) else f
        except (TypeError, ValueError):
            return 0.0

    conn = _sqlite3.connect(db_path, timeout=30)
    conn.row_factory = _sqlite3.Row
    try:
        placeholders = ",".join(["?"] * len(symbol_list))
        df = _pd.read_sql(
            f"SELECT symbol, date, open, high, low, close, volume FROM crypto_bars "
            f"WHERE timeframe='1d' AND symbol IN ({placeholders}) ORDER BY symbol, date",
            conn, parse_dates=["date"], params=symbol_list
        )
    finally:
        conn.close()

    if df.empty:
        return []

    df["close"] = _pd.to_numeric(df["close"], errors="coerce")
    df["open"] = _pd.to_numeric(df["open"], errors="coerce")
    df["high"] = _pd.to_numeric(df["high"], errors="coerce")
    df["low"] = _pd.to_numeric(df["low"], errors="coerce")
    df["volume"] = _pd.to_numeric(df["volume"], errors="coerce").fillna(0)

    now = _dt.utcnow().isoformat()
    results = []

    for sym, grp in df.groupby("symbol", observed=True):
        grp = grp.sort_values("date").reset_index(drop=True)
        if len(grp) < 2:
            continue

        try:
            c = grp["close"].astype(float)
            h = grp["high"].astype(float)
            l = grp["low"].astype(float)
            v = grp["volume"].astype(float)

            last_close = c.iloc[-1]
            prev_close = c.iloc[-2] if len(c) >= 2 else last_close
            change_pct = ((last_close - prev_close) / prev_close * 100) if prev_close > 0 else 0

            wa = _weighted_alpha(grp)
            wa_val = wa.iloc[-1] if len(wa) > 0 else 0

            st_result = _atr_trailing_stop(grp, period=14, multiplier=ATR_MULTIPLIER)
            st_signal = _si(st_result["trend"].iloc[-1]) if len(st_result) > 0 else 0
            st_stop = _sf(st_result["stop"].iloc[-1]) if len(st_result) > 0 else 0
            st_atr = _sf(st_result["atr_value"].iloc[-1]) if len(st_result) > 0 else 0
            st_streak = _si(st_result["streak"].iloc[-1]) if len(st_result) > 0 else 0
            st_cross_up = _si(st_result["crossed_above"].iloc[-1]) if len(st_result) > 0 else 0
            st_cross_down = _si(st_result["crossed_below"].iloc[-1]) if len(st_result) > 0 else 0

            st_w_signal, st_w_stop, st_w_cross_up, st_w_cross_down = 0, 0.0, 0, 0
            st_w_streak = 0
            if len(grp) >= 7:
                try:
                    dates_arr = grp["date"].values
                    opens_arr = grp["open"].astype(float).values
                    highs_arr = grp["high"].astype(float).values
                    lows_arr = grp["low"].astype(float).values
                    closes_arr = grp["close"].astype(float).values
                    r = _compute_rolling_atr_trailing_stop(
                        dates_arr, opens_arr, highs_arr, lows_arr, closes_arr,
                        len(dates_arr) - 1, 5, period=14, multiplier=ATR_MULTIPLIER)
                    st_w_signal = r['trend']; st_w_stop = r['stop']
                    st_w_cross_up = r['crossed_above']; st_w_cross_down = r['crossed_below']
                    st_w_streak = r['streak']
                except Exception:
                    pass

            st_m_signal, st_m_stop, st_m_cross_up, st_m_cross_down = 0, 0.0, 0, 0
            st_m_streak = 0
            if len(grp) >= 24:
                try:
                    dates_arr = grp["date"].values
                    opens_arr = grp["open"].astype(float).values
                    highs_arr = grp["high"].astype(float).values
                    lows_arr = grp["low"].astype(float).values
                    closes_arr = grp["close"].astype(float).values
                    r = _compute_rolling_atr_trailing_stop(
                        dates_arr, opens_arr, highs_arr, lows_arr, closes_arr,
                        len(dates_arr) - 1, 22, period=14, multiplier=ATR_MULTIPLIER)
                    st_m_signal = r['trend']; st_m_stop = r['stop']
                    st_m_cross_up = r['crossed_above']; st_m_cross_down = r['crossed_below']
                    st_m_streak = r['streak']
                except Exception:
                    pass

            ac = _accel(grp)
            accel_a_val = _sf(ac["accel_a"].iloc[-1]) if len(ac) > 0 else 0
            accel_base_val = _sf(ac["accel_base"].iloc[-1]) if len(ac) > 0 else 0
            accel_signal_val = _si(ac["accel_signal"].iloc[-1]) if len(ac) > 0 else 0
            accel_cross_up = _si(ac["accel_crossed_up"].iloc[-1]) if len(ac) > 0 else 0
            accel_cross_down = _si(ac["accel_crossed_down"].iloc[-1]) if len(ac) > 0 else 0

            st_sig_full = st_result["trend"].fillna(0).astype(int).values if len(st_result) > 0 else _np.zeros(1, dtype=int)
            ac_sig_full = ac["accel_signal"].fillna(0).astype(int).values if len(ac) > 0 else _np.zeros(1, dtype=int)
            st_bas = _bars_at_side(st_sig_full)
            ac_bas = _bars_at_side(ac_sig_full)
            _st_bas_last = _si(st_bas[-1]) if len(st_bas) > 0 else 0
            _ac_bas_last = _si(ac_bas[-1]) if len(ac_bas) > 0 else 0
            st_bars_below_val = _st_bas_last if st_signal == 1 else 0
            st_bars_above_val = _st_bas_last if st_signal == -1 else 0
            accel_bars_below_val = _ac_bas_last if accel_signal_val == 1 else 0
            accel_bars_above_val = _ac_bas_last if accel_signal_val == -1 else 0

            atrp_val = _sf(_atrp(h, l, c).iloc[-1]) if len(h) > 0 else 0

            p1d = _prob_up(c, 1); p5d = _prob_up(c, 5)
            p1w = _prob_up(c, 5); p1m = _prob_up(c, 22)
            prob_1d = _sf(p1d.iloc[-1]) if len(p1d) > 0 else 50.0
            prob_5d = _sf(p5d.iloc[-1]) if len(p5d) > 0 else 50.0
            prob_1w = _sf(p1w.iloc[-1]) if len(p1w) > 0 else 50.0
            prob_1m = _sf(p1m.iloc[-1]) if len(p1m) > 0 else 50.0
            prob_st_cross_arr = _prob_up_after_st_cross_up(
                st_result["crossed_above"].fillna(0).astype(int).values,
                ((c.shift(-1) - c) / c * 100).fillna(0.0).values)
            prob_st_cross = _sf(prob_st_cross_arr[-1]) if len(prob_st_cross_arr) > 0 else 50.0

            ndr = ((c.shift(-1) - c) / c * 100).fillna(0.0)
            ndr_val = _sf(ndr.iloc[-2]) if len(ndr) >= 2 else 0
            streak_val = _si(_streak_vectorized(c)[-1]) if len(c) > 1 else 0

            # AI scores — vectorized (same as _historical_ai_columns)
            grp_df = grp.copy()
            ai = _historical_ai_columns(grp_df)
            ai_overall = float(ai["ai_overall_score"].iloc[-1]) if len(ai) > 0 else 0
            ai_bias = str(ai["ai_bias"].iloc[-1]) if len(ai) > 0 else "neutral"
            ai_tech = float(ai["ai_tech_score"].iloc[-1]) if len(ai) > 0 else 0
            ai_mom = float(ai["ai_momentum_score"].iloc[-1]) if len(ai) > 0 else 0
            ai_vol = float(ai["ai_volume_score"].iloc[-1]) if len(ai) > 0 else 0
            ai_evt = float(ai["ai_events_score"].iloc[-1]) if len(ai) > 0 else 0
            ai_vp = float(ai["ai_volume_profile_score"].iloc[-1]) if len(ai) > 0 else 0
            ai_tl = float(ai["ai_trendline_score"].iloc[-1]) if len(ai) > 0 else 0
            ai_sent = float(ai["ai_sentiment_score"].iloc[-1]) if len(ai) > 0 else 0
            ai_conc = str(ai["ai_conclusion"].iloc[-1]) if len(ai) > 0 else "HOLD"
            ai_mat = float(ai["ai_matrix"].iloc[-1]) if len(ai) > 0 and "ai_matrix" in ai.columns else 0

            row = {
                "symbol": sym, "price": float(last_close), "volume": _si(v.iloc[-1]),
                "change_pct": round(change_pct, 4), "weighted_alpha": round(wa_val, 4),
                "atr_signal": st_signal, "atr_stop": round(st_stop, 4),
                "atr_value": round(st_atr, 4), "atr_streak": st_streak,
                "atr_crossed_above": st_cross_up, "atr_crossed_below": st_cross_down,
                "streak": streak_val,
                "next_day_return": round(ndr_val, 4),
                "prob_up_1d": round(prob_1d, 2), "prob_up_5d": round(prob_5d, 2),
                "prob_up_st_cross": round(prob_st_cross, 2),
                "prob_up_1w": round(prob_1w, 2), "prob_up_1m": round(prob_1m, 2),
                "atrp": round(atrp_val, 4),
                "accel_a": round(accel_a_val, 6), "accel_base": round(accel_base_val, 6),
                "accel_signal": accel_signal_val, "accel_crossed_up": accel_cross_up,
                "accel_crossed_down": accel_cross_down,
                "st_bars_below": st_bars_below_val, "st_bars_above": st_bars_above_val,
                "atr_signal_w": st_w_signal, "atr_stop_w": round(st_w_stop, 4),
                "atr_crossed_above_w": st_w_cross_up, "atr_crossed_below_w": st_w_cross_down,
                "atr_streak_w": st_w_streak,
                "atr_signal_m": st_m_signal, "atr_stop_m": round(st_m_stop, 4),
                "atr_crossed_above_m": st_m_cross_up, "atr_crossed_below_m": st_m_cross_down,
                "atr_streak_m": st_m_streak,
                "accel_bars_below": accel_bars_below_val, "accel_bars_above": accel_bars_above_val,
                "ai_overall_score": round(ai_overall, 2), "ai_bias": ai_bias,
                "ai_tech_score": round(ai_tech, 2), "ai_momentum_score": round(ai_mom, 2),
                "ai_volume_score": round(ai_vol, 2), "ai_events_score": round(ai_evt, 2),
                "ai_volume_profile_score": round(ai_vp, 2), "ai_trendline_score": round(ai_tl, 2),
                "ai_sentiment_score": round(ai_sent, 2), "ai_conclusion": ai_conc,
                "ai_matrix": round(ai_mat, 2) if isinstance(ai_mat, float) else ai_mat,
            }
            row["confluence"] = _compute_confluence(row)
            results.append(row)
        except Exception:
            continue

    return results


def compute_crypto_stats_batch(only_symbols=None, progress_callback=None):
    """ONE vectorized pass over all crypto daily bars to compute ALL stats columns.
    Uses ProcessPoolExecutor for true parallelism (bypasses GIL).
    Mirrors USA's vectorized_stats_pass but for CRYPTO."""
    from dumbmoney.config import DB_PATHS

    conn = get_db("CRYPTO")
    db_path = DB_PATHS["CRYPTO"]
    try:
        if only_symbols is not None:
            if not only_symbols:
                return 0
            symbols = only_symbols
        else:
            symbols = [r[0] for r in conn.execute(
                "SELECT DISTINCT symbol FROM crypto_bars WHERE timeframe='1d'"
            ).fetchall()]
    finally:
        conn.close()

    if not symbols:
        return 0

    total_groups = len(symbols)
    if progress_callback:
        progress_callback(0, total_groups)

    import multiprocessing as _mp
    n_workers = min(_mp.cpu_count() or 4, 8)
    chunk_size = max(1, (len(symbols) + n_workers - 1) // n_workers)
    batches = []
    for i in range(0, len(symbols), chunk_size):
        batches.append((symbols[i:i+chunk_size], db_path))

    results = []
    batch_errors = []
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_compute_crypto_stats_batch, batch): batch for batch in batches}
        done = 0
        for f in as_completed(futures):
            try:
                batch_results = f.result()
                if batch_results:
                    results.extend(batch_results)
            except Exception as e:
                batch_errors.append(str(e))
                logger.warning(f"Crypto stats batch worker failed: {e}")
            done += 1
            if progress_callback:
                progress_callback(done * chunk_size, total_groups)

    if progress_callback:
        progress_callback(total_groups, total_groups)

    if not results:
        if batch_errors:
            logger.error(f"All {len(batch_errors)} crypto stats batches failed: {'; '.join(batch_errors[:3])}")
        return 0

    now = datetime.utcnow().isoformat()
    conn = get_db("CRYPTO")
    try:
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA journal_size_limit = 67108864")

        batch_size = 2000
        for start in range(0, len(results), batch_size):
            chunk = results[start:start + batch_size]
            records = []
            for r in chunk:
                records.append((
                    r.get("symbol"), r.get("price", 0), r.get("volume", 0),
                    r.get("change_pct", 0), r.get("atrp", 0), r.get("weighted_alpha", 0),
                    r.get("atr_signal", 0), r.get("atr_stop", 0), r.get("atr_value", 0),
                    r.get("atr_streak", 0), r.get("atr_crossed_above", 0), r.get("atr_crossed_below", 0),
                    r.get("streak", 0),
                    r.get("next_day_return", 0), r.get("prob_up_1d", 50), r.get("prob_up_5d", 50),
                    r.get("prob_up_st_cross", 50), r.get("prob_up_1w", 50), r.get("prob_up_1m", 50),
                    r.get("accel_a", 0), r.get("accel_base", 0), r.get("accel_signal", 0),
                    r.get("accel_crossed_up", 0), r.get("accel_crossed_down", 0),
                    r.get("confluence", 0),
                    r.get("st_bars_below", 0), r.get("st_bars_above", 0),
                    r.get("accel_bars_below", 0), r.get("accel_bars_above", 0),
                    r.get("atr_signal_w", 0), r.get("atr_stop_w", 0), r.get("atr_crossed_above_w", 0), r.get("atr_crossed_below_w", 0), r.get("atr_streak_w", 0),
                    r.get("atr_signal_m", 0), r.get("atr_stop_m", 0), r.get("atr_crossed_above_m", 0), r.get("atr_crossed_below_m", 0), r.get("atr_streak_m", 0),
                    r.get("ai_overall_score", 0), r.get("ai_bias", "neutral"),
                    r.get("ai_tech_score", 0), r.get("ai_momentum_score", 0),
                    r.get("ai_volume_score", 0), r.get("ai_events_score", 0),
                    r.get("ai_volume_profile_score", 0), r.get("ai_trendline_score", 0),
                    r.get("ai_sentiment_score", 0), r.get("ai_conclusion", "HOLD"),
                    r.get("ai_matrix", ""), now,
                ))
            conn.executemany(
                """INSERT OR REPLACE INTO crypto_stats (
                    symbol, price, volume, change_pct, atrp, weighted_alpha,
                    atr_signal, atr_stop, atr_value, atr_streak, atr_crossed_above, atr_crossed_below,
                    streak,
                    next_day_return, prob_up_1d, prob_up_5d, prob_up_st_cross, prob_up_1w, prob_up_1m,
                    accel_a, accel_base, accel_signal, accel_crossed_up, accel_crossed_down,
                    confluence,
                    st_bars_below, st_bars_above, accel_bars_below, accel_bars_above,
                    atr_signal_w, atr_stop_w, atr_crossed_above_w, atr_crossed_below_w, atr_streak_w,
                    atr_signal_m, atr_stop_m, atr_crossed_above_m, atr_crossed_below_m, atr_streak_m,
                    ai_overall_score, ai_bias, ai_tech_score, ai_momentum_score,
                    ai_volume_score, ai_events_score, ai_volume_profile_score,
                    ai_trendline_score, ai_sentiment_score, ai_conclusion, ai_matrix,
                    last_updated
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                records
            )
            conn.commit()

        # Store version
        conn.execute(
            "INSERT OR REPLACE INTO crypto_settings (key, value) VALUES ('stats_version', ?)",
            (CRYPTO_STATS_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()

    return len(results)


def update_crypto_historical_screener(only_symbols=None, progress_callback=None, force_rebuild=False):
    """Fill crypto_historical_screener with true as-of-date indicator values.
    Mirrors USA's update_historical_screener but for CRYPTO."""
    from dumbmoney.config import DB_PATHS

    conn = get_db("CRYPTO")
    db_path = DB_PATHS["CRYPTO"]
    try:
        if progress_callback:
            progress_callback(0, "Checking crypto historical screener state...")

        requested = None
        if only_symbols is not None:
            requested = sorted(set(only_symbols))
            if not requested:
                if progress_callback:
                    progress_callback(100, "Crypto historical screener already current")
                return

        version_row = conn.execute(
            "SELECT value FROM crypto_settings WHERE key='historical_screener_version'"
        ).fetchone()
        version_mismatch = not version_row or version_row[0] != CRYPTO_STATS_VERSION
        needs_rebuild = force_rebuild or (version_mismatch and only_symbols is None)

        if needs_rebuild:
            conn.execute("DELETE FROM crypto_historical_screener")
            conn.commit()

        if requested:
            placeholders_req = ",".join("?" * len(requested))
            existing = conn.execute(
                f"""SELECT symbol, MAX(date) as max_date
                    FROM crypto_historical_screener
                    WHERE symbol IN ({placeholders_req})
                    GROUP BY symbol""",
                requested,
            ).fetchall()
        else:
            existing = conn.execute(
                "SELECT symbol, MAX(date) as max_date FROM crypto_historical_screener GROUP BY symbol"
            ).fetchall()
        existing_map = {row[0]: row[1] for row in existing}

        if requested:
            placeholders2 = ",".join("?" * len(requested))
            max_rows = conn.execute(
                f"""SELECT symbol, MAX(date)
                    FROM crypto_bars
                    WHERE timeframe='1d' AND symbol IN ({placeholders2})
                    GROUP BY symbol""",
                requested,
            ).fetchall()
            all_symbols = [
                row[0] for row in max_rows
                if version_mismatch or force_rebuild or existing_map.get(row[0]) != row[1]
            ]
        else:
            max_rows = conn.execute(
                "SELECT symbol, MAX(date) FROM crypto_bars WHERE timeframe='1d' GROUP BY symbol"
            ).fetchall()
            all_symbols = [
                row[0] for row in max_rows
                if needs_rebuild or existing_map.get(row[0]) != row[1]
            ]

        if not all_symbols:
            if progress_callback:
                progress_callback(100, "Crypto historical screener already current")
            return

        total_syms = len(all_symbols)
        total_rows = 0
        batch_size = 200
        cols_str = ", ".join(CRYPTO_HISTORICAL_SCREENER_COLUMNS)
        placeholders = ",".join(["?"] * len(CRYPTO_HISTORICAL_SCREENER_COLUMNS))
        insert_sql = f"INSERT OR REPLACE INTO crypto_historical_screener ({cols_str}) VALUES ({placeholders})"

        if progress_callback:
            mode = "full rebuild" if needs_rebuild else "incremental"
            progress_callback(5, f"Crypto historical screener {mode}: {total_syms} symbols")

        import multiprocessing
        try:
            multiprocessing.set_start_method("spawn", force=True)
        except RuntimeError:
            pass

        num_workers = min(os.cpu_count() or 4, 8)
        batches = [all_symbols[i:i + batch_size] for i in range(0, total_syms, batch_size)]
        total_batches = len(batches)
        batch_args = [
            (batch, db_path, existing_map, requested, version_mismatch, force_rebuild)
            for batch in batches
        ]

        done_batches = 0
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(_compute_crypto_symbol_batch, a) for a in batch_args]
            for future in as_completed(futures):
                if progress_callback and done_batches % max(1, total_batches // 20) == 0:
                    progress_callback(15 + round(done_batches / total_batches * 75),
                                     f"Processing: {done_batches}/{total_batches} batches ({total_rows:,} rows)")
                done_batches += 1
                try:
                    records = future.result(timeout=600)
                    if records:
                        for j in range(0, len(records), 50000):
                            conn.executemany(insert_sql, records[j:j + 50000])
                            conn.commit()
                        total_rows += len(records)
                except Exception as e:
                    logger.warning(f"Crypto worker batch error: {e}")

        if only_symbols is None:
            conn.execute(
                "INSERT OR REPLACE INTO crypto_settings (key, value) VALUES ('historical_screener_version', ?)",
                (CRYPTO_STATS_VERSION,),
            )
            conn.commit()

        if progress_callback:
            progress_callback(100, f"Crypto history filled ({total_rows:,} rows)")
    finally:
        conn.close()


def _compute_crypto_symbol_batch(args):
    """Top-level worker function for crypto historical screener multiprocessing."""
    batch_syms, db_path, existing_map, requested, version_mismatch, force_rebuild = args
    import sqlite3 as _sqlite3
    import pandas as _pd
    import numpy as _np
    from datetime import timedelta

    conn = _sqlite3.connect(db_path, timeout=30)
    try:
        incremental_syms = []
        full_rebuild_syms = []
        for sym in batch_syms:
            if version_mismatch or force_rebuild or not existing_map.get(sym):
                full_rebuild_syms.append(sym)
            else:
                incremental_syms.append(sym)

        bars = _pd.DataFrame()
        if full_rebuild_syms:
            placeholders_f = ",".join("?" * len(full_rebuild_syms))
            bars_full = _pd.read_sql(
                f"""SELECT symbol, date, open, high, low, close, volume FROM crypto_bars
                    WHERE timeframe='1d' AND symbol IN ({placeholders_f})
                    ORDER BY symbol, date""",
                conn, params=full_rebuild_syms,
            )
            bars = bars_full if bars.empty else _pd.concat([bars, bars_full], ignore_index=True)

        if incremental_syms:
            warmup_cutoffs = []
            for sym in incremental_syms:
                last_hist = existing_map.get(sym, "")
                if last_hist:
                    try:
                        dt = datetime.strptime(last_hist, "%Y-%m-%d")
                        cutoff = (dt - timedelta(days=500)).strftime("%Y-%m-%d")
                    except Exception:
                        cutoff = "1970-01-01"
                else:
                    cutoff = "1970-01-01"
                warmup_cutoffs.append(cutoff)
            batch_cutoff = min(warmup_cutoffs) if warmup_cutoffs else "1970-01-01"
            placeholders_i = ",".join("?" * len(incremental_syms))
            bars_incr = _pd.read_sql(
                f"""SELECT symbol, date, open, high, low, close, volume FROM crypto_bars
                    WHERE timeframe='1d' AND symbol IN ({placeholders_i})
                    AND date > ?
                    ORDER BY symbol, date""",
                conn, params=incremental_syms + [batch_cutoff],
            )
            bars = bars_incr if bars.empty else _pd.concat([bars, bars_incr], ignore_index=True)

        if bars.empty:
            return []

        records = []
        for _, grp in bars.groupby("symbol", sort=False):
            if len(grp) < 2:
                continue
            sym = str(grp["symbol"].iloc[0])
            try:
                last_hist_date = existing_map.get(sym)
                if not version_mismatch and not force_rebuild and last_hist_date:
                    new_bars = grp[grp["date"] > last_hist_date]
                    if new_bars.empty:
                        continue
                    num_new = len(new_bars)
                    grp_sliced = grp.tail(num_new + 320).copy()
                    hist = _compute_historical_crypto_frame(grp_sliced)
                    try:
                        _ld = datetime.strptime(str(last_hist_date)[:10], "%Y-%m-%d")
                        lookback = (_ld - timedelta(days=5)).strftime("%Y-%m-%d")
                    except Exception:
                        lookback = str(last_hist_date)[:10]
                    hist = hist[hist["date"] >= lookback]
                else:
                    hist = _compute_historical_crypto_frame(grp)

                if not hist.empty:
                    records.extend([tuple(r) for r in hist.itertuples(index=False, name=None)])
            except Exception:
                continue
        return records
    finally:
        conn.close()


def _compute_historical_crypto_frame(grp):
    """Compute historical screener columns for one crypto symbol (vectorized).
    Mirrors _compute_historical_symbol_frame but for CRYPTO."""
    import numpy as _np
    import pandas as _pd
    grp = grp.sort_values("date").reset_index(drop=True).copy()
    c = grp["close"].astype(float)
    h = grp["high"].astype(float)
    l = grp["low"].astype(float)
    v = grp["volume"].replace([_np.inf, -_np.inf], _np.nan).fillna(0)
    st = atr_trailing_stop(grp, period=14, multiplier=ATR_MULTIPLIER)
    ac = accel(grp)
    ai = _historical_ai_columns(grp)

    out = _pd.DataFrame({
        "symbol": grp["symbol"],
        "date": _pd.to_datetime(grp["date"]).dt.strftime("%Y-%m-%d"),
        "price": c,
        "change_pct": c.pct_change().replace([_np.inf, -_np.inf], _np.nan).fillna(0) * 100,
        "volume": v,
        "weighted_alpha": _weighted_alpha_history(c.values),
        "atrp": atrp(h, l, c),
        "streak": streak_vectorized(c),
        "atr_value": st["atr_value"].fillna(0),
        "atr_stop": st["stop"].fillna(0),
        "atr_signal": st["trend"].fillna(0).replace([_np.inf, -_np.inf], _np.nan).fillna(0).astype(int),
        "atr_crossed_above": st["crossed_above"].fillna(0).replace([_np.inf, -_np.inf], _np.nan).fillna(0).astype(int),
        "atr_crossed_below": st["crossed_below"].fillna(0).replace([_np.inf, -_np.inf], _np.nan).fillna(0).astype(int),
        "atr_streak": st["streak"].fillna(0).replace([_np.inf, -_np.inf], _np.nan).fillna(0).astype(int),
    })
    out = _pd.concat([out, ai], axis=1)
    out["next_day_return"] = c.shift(-1).sub(c).div(c).replace([_np.inf, -_np.inf], _np.nan).fillna(0) * 100
    out["prob_up_1d"] = prob_up(c, 1).fillna(50.0)
    out["prob_up_5d"] = prob_up(c, 5).fillna(50.0)
    out["prob_up_1w"] = prob_up(c, 5).fillna(50.0)
    out["prob_up_1m"] = prob_up(c, 22).fillna(50.0)
    out["prob_up_st_cross"] = prob_up_after_st_cross_up(
        st["crossed_above"].fillna(0).values,
        out["next_day_return"].values,
    )
    out["accel_a"] = ac["accel_a"].fillna(0)
    out["accel_base"] = ac["accel_base"].fillna(0)
    out["accel_signal"] = ac["accel_signal"].fillna(0).replace([_np.inf, -_np.inf], _np.nan).fillna(0).astype(int)
    out["accel_crossed_up"] = ac["accel_crossed_up"].fillna(0).replace([_np.inf, -_np.inf], _np.nan).fillna(0).astype(int)
    out["accel_crossed_down"] = ac["accel_crossed_down"].fillna(0).replace([_np.inf, -_np.inf], _np.nan).fillna(0).astype(int)
    _st_sig = out["atr_signal"].values.astype(_np.int32)
    _ac_sig = out["accel_signal"].values.astype(_np.int32)
    _st_bas = bars_at_side(_st_sig)
    _ac_bas = bars_at_side(_ac_sig)
    out["st_bars_below"] = _np.where(_st_sig == 1, _st_bas, 0).astype(int)
    out["st_bars_above"] = _np.where(_st_sig == -1, _st_bas, 0).astype(int)
    out["accel_bars_below"] = _np.where(_ac_sig == 1, _ac_bas, 0).astype(int)
    out["accel_bars_above"] = _np.where(_ac_sig == -1, _ac_bas, 0).astype(int)

    for sessions, suffix in [(5, "_w"), (22, "_m")]:
        try:
            dates_arr = grp["date"].values
            opens_arr = grp["open"].astype(float).values
            highs_arr = grp["high"].astype(float).values
            lows_arr = grp["low"].astype(float).values
            closes_arr = grp["close"].astype(float).values

            w_trends, w_stops, w_atrs, w_streaks, w_cross_above, w_cross_below, w_bars_bl, w_bars_ab = \
                compute_rolling_atr_batch(dates_arr, opens_arr, highs_arr, lows_arr, closes_arr,
                                          sessions, period=14, multiplier=ATR_MULTIPLIER)

            out[f"atr_signal{suffix}"] = w_trends
            out[f"atr_stop{suffix}"] = w_stops
            out[f"atr_crossed_above{suffix}"] = w_cross_above
            out[f"atr_crossed_below{suffix}"] = w_cross_below
            out[f"atr_streak{suffix}"] = w_streaks
        except Exception:
            for col in ["atr_signal", "atr_stop", "atr_crossed_above", "atr_crossed_below", "atr_streak"]:
                out[f"{col}{suffix}"] = 0

    out["confluence"] = compute_confluence_vectorized(
        out["atr_signal"].values, out["accel_signal"].values,
        out["weighted_alpha"].values, out["streak"].values, out["prob_up_1d"].values
    )

    numeric_cols = [cname for cname in out.columns if cname not in {"symbol", "date", "ai_bias", "ai_conclusion", "ai_matrix"}]
    out[numeric_cols] = out[numeric_cols].replace([_np.inf, -_np.inf], _np.nan).fillna(0)
    return out[CRYPTO_HISTORICAL_SCREENER_COLUMNS]
