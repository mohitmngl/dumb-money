"""Crypto screener — thin SQL query layer reading from pre-computed tables.
Mirrors USA screener architecture: stats table for current mode, historical_screener for date mode.
All computation happens during refresh/startup via ProcessPoolExecutor in engine.py."""
import logging
import time
from dumbmoney.data_crypto import get_all_symbols, get_chart_data

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Current mode — reads from crypto_stats (instant SQL)
# ---------------------------------------------------------------------------

def _build_crypto_stats_query(conn, search, sort, sort_dir, page, per_page, args):
    """Build SQL query for current crypto_stats table. Mirrors USA _build_stats_query."""
    where = ["1=1"]
    params = []

    if search:
        where.append("symbol LIKE ?")
        params.append(f"%{search}%")

    min_price = args.get("min_price")
    max_price = args.get("max_price")
    if min_price:
        where.append("price >= ?")
        params.append(float(min_price))
    if max_price:
        where.append("price <= ?")
        params.append(float(max_price))

    min_change = args.get("min_change")
    max_change = args.get("max_change")
    if min_change:
        where.append("change_pct >= ?")
        params.append(float(min_change))
    if max_change:
        where.append("change_pct <= ?")
        params.append(float(max_change))

    min_wa = args.get("min_wa")
    max_wa = args.get("max_wa")
    if min_wa:
        where.append("weighted_alpha >= ?")
        params.append(float(min_wa))
    if max_wa:
        where.append("weighted_alpha <= ?")
        params.append(float(max_wa))

    min_streak = args.get("min_streak")
    if min_streak:
        where.append("streak >= ?")
        params.append(int(min_streak))

    min_volume = args.get("min_volume")
    if min_volume:
        where.append("volume >= ?")
        params.append(int(min_volume))

    atr_status = args.get("atr_status")
    if atr_status:
        if atr_status == "above":
            where.append("atr_signal = 1")
        elif atr_status == "below":
            where.append("atr_signal = -1")
        elif atr_status == "crossed-above":
            where.append("atr_crossed_above = 1")
        elif atr_status == "crossed-below":
            where.append("atr_crossed_below = 1")

    atr_status_w = args.get("atr_status_w")
    if atr_status_w:
        if atr_status_w == "above":
            where.append("atr_signal_w = 1")
        elif atr_status_w == "below":
            where.append("atr_signal_w = -1")
        elif atr_status_w == "crossed-above":
            where.append("atr_crossed_above_w = 1")
        elif atr_status_w == "crossed-below":
            where.append("atr_crossed_below_w = 1")

    atr_status_m = args.get("atr_status_m")
    if atr_status_m:
        if atr_status_m == "above":
            where.append("atr_signal_m = 1")
        elif atr_status_m == "below":
            where.append("atr_signal_m = -1")
        elif atr_status_m == "crossed-above":
            where.append("atr_crossed_above_m = 1")
        elif atr_status_m == "crossed-below":
            where.append("atr_crossed_below_m = 1")

    accel_status = args.get("accel_status")
    if accel_status:
        if accel_status == "up":
            where.append("accel_signal = 1")
        elif accel_status == "down":
            where.append("accel_signal = -1")
        elif accel_status == "crossed-up":
            where.append("accel_crossed_up = 1")
        elif accel_status == "crossed-down":
            where.append("accel_crossed_down = 1")

    min_st_bars_below = args.get("min_st_bars_below")
    if min_st_bars_below:
        where.append("st_bars_below >= ?")
        params.append(int(min_st_bars_below))
    min_st_bars_above = args.get("min_st_bars_above")
    if min_st_bars_above:
        where.append("st_bars_above >= ?")
        params.append(int(min_st_bars_above))
    min_accel_bars_below = args.get("min_accel_bars_below")
    if min_accel_bars_below:
        where.append("accel_bars_below >= ?")
        params.append(int(min_accel_bars_below))
    min_accel_bars_above = args.get("min_accel_bars_above")
    if min_accel_bars_above:
        where.append("accel_bars_above >= ?")
        params.append(int(min_accel_bars_above))

    min_oi = args.get("min_oi")
    if min_oi:
        where.append("oi >= ?")
        params.append(float(min_oi))
    min_funding_rate = args.get("min_funding_rate")
    if min_funding_rate:
        where.append("funding_rate >= ?")
        params.append(float(min_funding_rate))
    new_ath = args.get("new_ath")
    if new_ath:
        where.append("new_ath = ?")
        params.append(1 if new_ath == "yes" else 0)
    new_atl = args.get("new_atl")
    if new_atl:
        where.append("new_atl = ?")
        params.append(1 if new_atl == "yes" else 0)

    where_str = " AND ".join(where)

    total = conn.execute(f"SELECT COUNT(*) FROM crypto_stats WHERE {where_str}", params).fetchone()[0]

    allowed_sorts = {
        "symbol", "price", "change_pct", "weighted_alpha", "volume", "streak", "confluence",
        "atr_signal", "atr_stop", "atr_value", "atr_streak", "atrp",
        "atr_crossed_above", "atr_crossed_below", "r_squared",
        "ath", "atl", "new_ath", "new_atl",
        "prob_up_1d", "prob_up_5d", "prob_up_st_cross", "prob_up_1w", "prob_up_1m",
        "next_day_return", "accel_a", "accel_base", "accel_signal", "accel_crossed_up", "accel_crossed_down",
        "st_bars_below", "st_bars_above", "accel_bars_below", "accel_bars_above",
        "atr_signal_w", "atr_stop_w", "atr_crossed_above_w", "atr_crossed_below_w",
        "atr_signal_m", "atr_stop_m", "atr_crossed_above_m", "atr_crossed_below_m",
        "oi", "oi_value", "funding_rate", "mark_price", "bid", "ask", "spread",
        "ai_overall_score", "ai_bias", "ai_tech_score", "ai_volume_profile_score",
        "ai_trendline_score", "ai_sentiment_score", "ai_conclusion", "ai_matrix",
    }
    if sort not in allowed_sorts:
        sort = "volume"
    direction = "DESC" if sort_dir == "desc" else "ASC"

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT * FROM crypto_stats WHERE {where_str} "
        f"ORDER BY {sort} {direction} NULLS LAST "
        f"LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM crypto_stats LIMIT 0").description]
    page_rows = [dict(zip(cols, r)) for r in rows]

    pages = max(1, (total + per_page - 1) // per_page)
    return {
        "data": page_rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": pages,
        "historical": False,
        "date": "",
    }


# ---------------------------------------------------------------------------
# Historical mode — reads from crypto_historical_screener (instant SQL)
# ---------------------------------------------------------------------------

def _build_crypto_hist_query(conn, date_cutoff, search, sort, sort_dir, page, per_page, args):
    """Build SQL query for crypto_historical_screener table. Mirrors USA _build_historical_query."""
    where = ["h.date = ?"]
    params = [date_cutoff]

    if search:
        where.append("h.symbol LIKE ?")
        params.append(f"%{search}%")

    min_price = args.get("min_price")
    max_price = args.get("max_price")
    if min_price:
        where.append("h.price >= ?")
        params.append(float(min_price))
    if max_price:
        where.append("h.price <= ?")
        params.append(float(max_price))

    min_change = args.get("min_change")
    max_change = args.get("max_change")
    if min_change:
        where.append("h.change_pct >= ?")
        params.append(float(min_change))
    if max_change:
        where.append("h.change_pct <= ?")
        params.append(float(max_change))

    min_wa = args.get("min_wa")
    max_wa = args.get("max_wa")
    if min_wa:
        where.append("h.weighted_alpha >= ?")
        params.append(float(min_wa))
    if max_wa:
        where.append("h.weighted_alpha <= ?")
        params.append(float(max_wa))

    min_streak = args.get("min_streak")
    if min_streak:
        where.append("h.streak >= ?")
        params.append(int(min_streak))

    min_volume = args.get("min_volume")
    if min_volume:
        where.append("h.volume >= ?")
        params.append(int(min_volume))

    atr_status = args.get("atr_status")
    if atr_status:
        if atr_status == "above":
            where.append("h.atr_signal = 1")
        elif atr_status == "below":
            where.append("h.atr_signal = -1")
        elif atr_status == "crossed-above":
            where.append("h.atr_crossed_above = 1")
        elif atr_status == "crossed-below":
            where.append("h.atr_crossed_below = 1")

    atr_status_w = args.get("atr_status_w")
    if atr_status_w:
        if atr_status_w == "above":
            where.append("h.atr_signal_w = 1")
        elif atr_status_w == "below":
            where.append("h.atr_signal_w = -1")
        elif atr_status_w == "crossed-above":
            where.append("h.atr_crossed_above_w = 1")
        elif atr_status_w == "crossed-below":
            where.append("h.atr_crossed_below_w = 1")

    atr_status_m = args.get("atr_status_m")
    if atr_status_m:
        if atr_status_m == "above":
            where.append("h.atr_signal_m = 1")
        elif atr_status_m == "below":
            where.append("h.atr_signal_m = -1")
        elif atr_status_m == "crossed-above":
            where.append("h.atr_crossed_above_m = 1")
        elif atr_status_m == "crossed-below":
            where.append("h.atr_crossed_below_m = 1")

    accel_status = args.get("accel_status")
    if accel_status:
        if accel_status == "up":
            where.append("h.accel_signal = 1")
        elif accel_status == "down":
            where.append("h.accel_signal = -1")
        elif accel_status == "crossed-up":
            where.append("h.accel_crossed_up = 1")
        elif accel_status == "crossed-down":
            where.append("h.accel_crossed_down = 1")

    min_st_bars_below = args.get("min_st_bars_below")
    if min_st_bars_below:
        where.append("h.st_bars_below >= ?")
        params.append(int(min_st_bars_below))
    min_st_bars_above = args.get("min_st_bars_above")
    if min_st_bars_above:
        where.append("h.st_bars_above >= ?")
        params.append(int(min_st_bars_above))
    min_accel_bars_below = args.get("min_accel_bars_below")
    if min_accel_bars_below:
        where.append("h.accel_bars_below >= ?")
        params.append(int(min_accel_bars_below))
    min_accel_bars_above = args.get("min_accel_bars_above")
    if min_accel_bars_above:
        where.append("h.accel_bars_above >= ?")
        params.append(int(min_accel_bars_above))

    new_ath = args.get("new_ath")
    if new_ath:
        where.append("h.new_ath = ?")
        params.append(1 if new_ath == "yes" else 0)
    new_atl = args.get("new_atl")
    if new_atl:
        where.append("h.new_atl = ?")
        params.append(1 if new_atl == "yes" else 0)

    where_str = " AND ".join(where)

    total = conn.execute(
        f"SELECT COUNT(*) FROM crypto_historical_screener h WHERE {where_str}", params
    ).fetchone()[0]

    allowed_sorts = {
        "symbol", "price", "change_pct", "weighted_alpha", "volume", "streak", "confluence",
        "atr_signal", "atr_stop", "atr_value", "atr_streak", "atrp",
        "atr_crossed_above", "atr_crossed_below", "r_squared",
        "ath", "atl", "new_ath", "new_atl",
        "prob_up_1d", "prob_up_5d", "prob_up_st_cross", "prob_up_1w", "prob_up_1m",
        "next_day_return", "accel_a", "accel_base", "accel_signal", "accel_crossed_up", "accel_crossed_down",
        "st_bars_below", "st_bars_above", "accel_bars_below", "accel_bars_above",
        "atr_signal_w", "atr_stop_w", "atr_crossed_above_w", "atr_crossed_below_w",
        "atr_signal_m", "atr_stop_m", "atr_crossed_above_m", "atr_crossed_below_m",
        "ai_overall_score", "ai_bias", "ai_tech_score", "ai_volume_profile_score",
        "ai_trendline_score", "ai_sentiment_score", "ai_conclusion", "ai_matrix",
    }
    if sort not in allowed_sorts:
        sort = "volume"
    direction = "DESC" if sort_dir == "desc" else "ASC"

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT h.* FROM crypto_historical_screener h WHERE {where_str} "
        f"ORDER BY h.{sort} {direction} NULLS LAST "
        f"LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM crypto_historical_screener LIMIT 0").description]
    page_rows = [dict(zip(cols, r)) for r in rows]

    pages = max(1, (total + per_page - 1) // per_page)
    return {
        "data": page_rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": pages,
        "historical": True,
        "date": date_cutoff,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_crypto_screener(page=1, per_page=50, sort="volume", sort_dir="desc",
                        search="", force=False, date_cutoff="", args=None):
    """Return paginated screener rows. Reads from pre-computed tables only.
    If date_cutoff is set, reads from crypto_historical_screener.
    Otherwise reads from crypto_stats."""
    from dumbmoney.db import get_db

    if args is None:
        args = {}
    if search:
        args["_search"] = search

    conn = get_db("CRYPTO")
    try:
        if date_cutoff:
            return _build_crypto_hist_query(conn, date_cutoff, search, sort, sort_dir, page, per_page, args)
        else:
            return _build_stats_query(conn, search, sort, sort_dir, page, per_page, args)
    finally:
        conn.close()


def _build_stats_query(conn, search, sort, sort_dir, page, per_page, args):
    """Alias for _build_crypto_stats_query used by get_crypto_screener."""
    return _build_crypto_stats_query(conn, search, sort, sort_dir, page, per_page, args)


def get_crypto_chart(symbol, timeframe='1d', limit=500):
    """Return OHLC candles for charting."""
    return get_chart_data(symbol, timeframe=timeframe, limit=limit)


def get_crypto_products():
    """Return all products from DB."""
    from dumbmoney.db import get_db
    conn = get_db("CRYPTO")
    try:
        rows = conn.execute(
            "SELECT symbol, product_id, contract_type, default_leverage, initial_margin, state"
            " FROM crypto_products WHERE state='live' ORDER BY symbol"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def trigger_backfill(resolution='1d', days_back=365, symbols=None, progress_callback=None):
    """Download historical candles. Returns (done, total)."""
    from dumbmoney.data_crypto import download_candles
    if symbols is None:
        symbols = get_all_symbols()
    if not symbols:
        return 0, 0
    total = len(symbols)
    for i, sym in enumerate(symbols):
        if progress_callback:
            progress_callback(i / total * 100, f"Downloading {sym} {resolution}")
        download_candles(sym, resolution=resolution, days_back=days_back)
    if progress_callback:
        progress_callback(100, f"Backfill complete: {total}/{total}")
    return total, total


def get_crypto_screener_columns():
    """Return column reference for crypto screener (mirrors USA SCREENER_COLUMN_REFERENCE)."""
    return [
        {"key": "symbol", "label": "Symbol", "current": "crypto_stats.symbol", "historical": "crypto_historical_screener.symbol", "meaning": "Ticker identifier."},
        {"key": "price", "label": "Price", "current": "crypto_stats.price", "historical": "crypto_historical_screener.price", "meaning": "Current mode latest close; date mode close on the selected date."},
        {"key": "change_pct", "label": "Chg%", "current": "crypto_stats.change_pct", "historical": "crypto_historical_screener.change_pct", "meaning": "Close-to-previous-close percent change."},
        {"key": "next_day_return", "label": "Next Day %", "current": "crypto_stats.next_day_return", "historical": "crypto_historical_screener.next_day_return", "meaning": "Realized next-day return."},
        {"key": "prob_up_1d", "label": "P(Up) 1D", "current": "crypto_stats.prob_up_1d", "historical": "crypto_historical_screener.prob_up_1d", "meaning": "Trailing probability next 1-day close is up."},
        {"key": "prob_up_5d", "label": "P(Up) 5D", "current": "crypto_stats.prob_up_5d", "historical": "crypto_historical_screener.prob_up_5d", "meaning": "Trailing probability next 5-day close is up."},
        {"key": "prob_up_1w", "label": "P(Up) 1W", "current": "crypto_stats.prob_up_1w", "historical": "crypto_historical_screener.prob_up_1w", "meaning": "Trailing probability next week close is up."},
        {"key": "prob_up_1m", "label": "P(Up) 1M", "current": "crypto_stats.prob_up_1m", "historical": "crypto_historical_screener.prob_up_1m", "meaning": "Trailing probability next month close is up."},
        {"key": "prob_up_st_cross", "label": "P(Up) ST Cross", "current": "crypto_stats.prob_up_st_cross", "historical": "crypto_historical_screener.prob_up_st_cross", "meaning": "Expanding probability next day up after ST cross."},
        {"key": "weighted_alpha", "label": "Wtd Alpha", "current": "crypto_stats.weighted_alpha", "historical": "crypto_historical_screener.weighted_alpha", "meaning": "Weighted price performance over past year."},
        {"key": "r_squared", "label": "R²", "current": "crypto_stats.r_squared", "historical": "crypto_historical_screener.r_squared", "meaning": "Signed R² of a linear fit on log(close) over the last 90 bars: +1 = perfectly straight uptrend, -1 = perfectly straight downtrend. Sort descending for the straightest uptrending charts."},
        {"key": "ath", "label": "ATH", "current": "crypto_stats.ath", "historical": "crypto_historical_screener.ath", "meaning": "All-time high: highest daily bar high from the first stored bar through the row date."},
        {"key": "atl", "label": "ATL", "current": "crypto_stats.atl", "historical": "crypto_historical_screener.atl", "meaning": "All-time low: lowest daily bar low from the first stored bar through the row date."},
        {"key": "volume", "label": "Volume", "current": "crypto_stats.volume", "historical": "crypto_historical_screener.volume", "meaning": "Daily bar volume."},
        {"key": "oi", "label": "Open Int", "current": "crypto_stats.oi", "historical": "NULL", "meaning": "Current open interest (current mode only)."},
        {"key": "oi_value", "label": "OI Value", "current": "crypto_stats.oi_value", "historical": "NULL", "meaning": "Current OI in USD (current mode only)."},
        {"key": "funding_rate", "label": "Funding %", "current": "crypto_stats.funding_rate", "historical": "NULL", "meaning": "Current funding rate (current mode only)."},
        {"key": "streak", "label": "Streak", "current": "crypto_stats.streak", "historical": "crypto_historical_screener.streak", "meaning": "Consecutive up/down close streak."},
        {"key": "confluence", "label": "Confluence", "current": "crypto_stats.confluence", "historical": "crypto_historical_screener.confluence", "meaning": "Combined technical score 0-100."},
        {"key": "ai_overall_score", "label": "AI Score", "current": "crypto_stats.ai_overall_score", "historical": "crypto_historical_screener.ai_overall_score", "meaning": "Local vectorized AI score 0-100."},
        {"key": "ai_volume_profile_score", "label": "VP Score", "current": "crypto_stats.ai_volume_profile_score", "historical": "crypto_historical_screener.ai_volume_profile_score", "meaning": "Volume profile score."},
        {"key": "ai_trendline_score", "label": "Trend Score", "current": "crypto_stats.ai_trendline_score", "historical": "crypto_historical_screener.ai_trendline_score", "meaning": "Trendline score."},
        {"key": "ai_sentiment_score", "label": "Sentiment", "current": "crypto_stats.ai_sentiment_score", "historical": "crypto_historical_screener.ai_sentiment_score", "meaning": "Sentiment score."},
        {"key": "ai_conclusion", "label": "Conclusion", "current": "crypto_stats.ai_conclusion", "historical": "crypto_historical_screener.ai_conclusion", "meaning": "BUY/HOLD/SELL label."},
        {"key": "ai_matrix", "label": "AI Matrix", "current": "crypto_stats.ai_matrix", "historical": "crypto_historical_screener.ai_matrix", "meaning": "Sigmoid-based directional prediction 0-100."},
        {"key": "atr_signal", "label": "ST Signal", "current": "crypto_stats.atr_signal", "historical": "crypto_historical_screener.atr_signal", "meaning": "ATR Trailing Stop direction: 1 up, -1 down, 0 neutral."},
        {"key": "atr_crossed_above", "label": "Cross Up", "current": "crypto_stats.atr_crossed_above", "historical": "crypto_historical_screener.atr_crossed_above", "meaning": "ATR crossed from bearish to bullish."},
        {"key": "atr_crossed_below", "label": "Cross Down", "current": "crypto_stats.atr_crossed_below", "historical": "crypto_historical_screener.atr_crossed_below", "meaning": "ATR crossed from bullish to bearish."},
        {"key": "atr_stop", "label": "ST Stop 14x2", "current": "crypto_stats.atr_stop", "historical": "crypto_historical_screener.atr_stop", "meaning": "ATR Trailing Stop line."},
        {"key": "atr_signal_w", "label": "ST W", "current": "crypto_stats.atr_signal_w", "historical": "crypto_historical_screener.atr_signal_w", "meaning": "Rolling weekly ATR direction."},
        {"key": "atr_crossed_above_w", "label": "Cross Up W", "current": "crypto_stats.atr_crossed_above_w", "historical": "crypto_historical_screener.atr_crossed_above_w", "meaning": "Weekly ATR crossed up."},
        {"key": "atr_crossed_below_w", "label": "Cross Down W", "current": "crypto_stats.atr_crossed_below_w", "historical": "crypto_historical_screener.atr_crossed_below_w", "meaning": "Weekly ATR crossed down."},
        {"key": "atr_stop_w", "label": "ST Stop W", "current": "crypto_stats.atr_stop_w", "historical": "crypto_historical_screener.atr_stop_w", "meaning": "Weekly ATR stop line."},
        {"key": "atr_signal_m", "label": "ST M", "current": "crypto_stats.atr_signal_m", "historical": "crypto_historical_screener.atr_signal_m", "meaning": "Rolling monthly ATR direction."},
        {"key": "atr_crossed_above_m", "label": "Cross Up M", "current": "crypto_stats.atr_crossed_above_m", "historical": "crypto_historical_screener.atr_crossed_above_m", "meaning": "Monthly ATR crossed up."},
        {"key": "atr_crossed_below_m", "label": "Cross Down M", "current": "crypto_stats.atr_crossed_below_m", "historical": "crypto_historical_screener.atr_crossed_below_m", "meaning": "Monthly ATR crossed down."},
        {"key": "atr_stop_m", "label": "ST Stop M", "current": "crypto_stats.atr_stop_m", "historical": "crypto_historical_screener.atr_stop_m", "meaning": "Monthly ATR stop line."},
        {"key": "atrp", "label": "ATR%", "current": "crypto_stats.atrp", "historical": "crypto_historical_screener.atrp", "meaning": "ATR percent."},
        {"key": "accel_signal", "label": "Accel", "current": "crypto_stats.accel_signal", "historical": "crypto_historical_screener.accel_signal", "meaning": "Accel trend: 1 up, -1 down."},
        {"key": "accel_crossed_up", "label": "Accel Up", "current": "crypto_stats.accel_crossed_up", "historical": "crypto_historical_screener.accel_crossed_up", "meaning": "Accel crossed up."},
        {"key": "accel_crossed_down", "label": "Accel Down", "current": "crypto_stats.accel_crossed_down", "historical": "crypto_historical_screener.accel_crossed_down", "meaning": "Accel crossed down."},
        {"key": "st_bars_below", "label": "ST Bars Below", "current": "crypto_stats.st_bars_below", "historical": "crypto_historical_screener.st_bars_below", "meaning": "Bars below ATR before cross-up."},
        {"key": "st_bars_above", "label": "ST Bars Above", "current": "crypto_stats.st_bars_above", "historical": "crypto_historical_screener.st_bars_above", "meaning": "Bars above ATR before cross-down."},
        {"key": "accel_bars_below", "label": "Accel Bars Below", "current": "crypto_stats.accel_bars_below", "historical": "crypto_historical_screener.accel_bars_below", "meaning": "Bars below Accel before cross-up."},
        {"key": "accel_bars_above", "label": "Accel Bars Above", "current": "crypto_stats.accel_bars_above", "historical": "crypto_historical_screener.accel_bars_above", "meaning": "Bars above Accel before cross-down."},
        {"key": "mark_price", "label": "Mark", "current": "crypto_stats.mark_price", "historical": "NULL", "meaning": "Current mark price (current mode only)."},
        {"key": "bid", "label": "Bid", "current": "crypto_stats.bid", "historical": "NULL", "meaning": "Current best bid (current mode only)."},
        {"key": "ask", "label": "Ask", "current": "crypto_stats.ask", "historical": "NULL", "meaning": "Current best ask (current mode only)."},
        {"key": "spread", "label": "Spread", "current": "crypto_stats.spread", "historical": "NULL", "meaning": "Current bid-ask spread (current mode only)."},
        {"key": "high_24h", "label": "24h High", "current": "crypto_stats.high_24h", "historical": "NULL", "meaning": "24h high (current mode only)."},
        {"key": "low_24h", "label": "24h Low", "current": "crypto_stats.low_24h", "historical": "NULL", "meaning": "24h low (current mode only)."},
    ]
