import os
import time
import logging
import requests
from datetime import datetime, timedelta, timezone
from intraday_backtest.config import (
    get_db, init_db, ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_DATA_URL, BASE_DIR
)

logger = logging.getLogger(__name__)

_session = requests.Session()
_session.headers.update({
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
})

# Rate limiter: Alpaca free tier ~200 req/min
_last_request_time = 0
MIN_INTERVAL = 0.35


def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _api_get(url, params, retries=3):
    for attempt in range(retries):
        _rate_limit()
        try:
            r = _session.get(url, params=params, timeout=20)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 60))
                logger.warning(f"Rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries - 1:
                logger.error(f"API error after {retries} attempts: {e}")
                return None
            time.sleep(2 ** attempt)
    return None


def fetch_available_timeframes(symbol="AAPL"):
    """Check how many bars are available for each timeframe."""
    results = {}
    for tf in ["1Min", "5Min", "15Min", "30Min", "1Hour", "1Day"]:
        params = {
            "symbols": symbol,
            "timeframe": tf,
            "start": "2020-01-01T00:00:00Z",
            "limit": 1,
            "adjustment": "split",
            "feed": "iex",
            "sort": "asc",
        }
        data = _api_get(f"{ALPACA_DATA_URL}/v2/stocks/bars", params)
        if data and "bars" in data and data["bars"].get(symbol):
            bars = data["bars"][symbol]
            if bars:
                first = bars[0]["t"]
                results[tf] = {"first": first}
            else:
                results[tf] = {"first": None}
        else:
            results[tf] = {"first": None, "error": str(data)[:100] if data else "no data"}
    return results


def download_bars(symbols, timeframe, start_date, end_date=None, progress_callback=None):
    """Download bars for multiple symbols from Alpaca.
    Skips symbols that already have fresh cached data.
    Returns total bar count written to DB."""
    init_db()
    conn = get_db()
    total_written = 0
    total_symbols = len(symbols)

    if end_date is None:
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for sym_idx, symbol in enumerate(symbols):
        # Skip if we already have bars for this symbol/timeframe
        existing = conn.execute(
            "SELECT COUNT(*) FROM bars WHERE symbol=? AND timeframe=?",
            (symbol, timeframe)
        ).fetchone()
        if existing and existing[0] > 0:
            total_symbols -= 1
            continue

        if progress_callback:
            progress_callback(sym_idx / total_symbols, f"Downloading {symbol} ({sym_idx+1}/{total_symbols})")

        page_token = None
        sym_written = 0

        while True:
            params = {
                "symbols": symbol,
                "timeframe": timeframe,
                "start": start_date,
                "end": end_date,
                "limit": 10000,
                "adjustment": "split",
                "feed": "iex",
                "sort": "asc",
            }
            if page_token:
                params["page_token"] = page_token

            data = _api_get(f"{ALPACA_DATA_URL}/v2/stocks/bars", params)
            if not data or "bars" not in data:
                break

            bars = data["bars"].get(symbol, [])
            if not bars:
                break

            rows = []
            for bar in bars:
                ts = bar["t"]
                rows.append((
                    symbol, timeframe, ts,
                    bar["o"], bar["h"], bar["l"], bar["c"], int(bar.get("v", 0))
                ))

            conn.executemany(
                "INSERT OR REPLACE INTO bars (symbol, timeframe, timestamp, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows
            )
            conn.commit()
            sym_written += len(rows)

            page_token = data.get("next_page_token")
            if not page_token:
                break

        total_written += sym_written

    conn.close()
    if progress_callback:
        progress_callback(1.0, f"Download complete: {total_written} bars")
    return total_written


def get_top_liquid_symbols(n=200):
    """Get top N most volatile and liquid US stocks from screener.db stats.
    Score = atrp (volatility) * volume (liquidity)."""
    init_db()
    conn = get_db()

    # Check cache
    row = conn.execute("SELECT COUNT(*) FROM symbols WHERE avg_volume > 0").fetchone()
    if row[0] >= n:
        syms = conn.execute(
            "SELECT symbol FROM symbols WHERE avg_volume > 0 ORDER BY avg_volume DESC LIMIT ?", (n,)
        ).fetchall()
        if len(syms) >= n:
            conn.close()
            return [s[0] for s in syms]

    # Pull from screener.db stats: filter liquid stocks, sort by volatility
    try:
        import sqlite3 as sql3
        screener_path = os.path.join(BASE_DIR, "screener.db")
        if os.path.exists(screener_path):
            sc = sql3.connect(screener_path)
            rows = sc.execute(
                "SELECT symbol, atrp, volume FROM stats "
                "WHERE asset_class='stock' AND volume > 500000 AND atrp > 0 "
                "AND LENGTH(symbol) <= 5 AND symbol NOT LIKE '%.%'"
            ).fetchall()
            sc.close()
            if rows:
                scored = [(r[0], r[1] * r[2]) for r in rows]
                scored.sort(key=lambda x: x[1], reverse=True)
                top = [s[0] for s in scored[:n]]
                for s, score in scored[:n]:
                    conn.execute(
                        "INSERT OR REPLACE INTO symbols (symbol, avg_volume) VALUES (?, ?)",
                        (s, score)
                    )
                conn.commit()
                conn.close()
                logger.info(f"Selected top {len(top)} stocks by volatility*volume")
                return top
    except Exception as e:
        logger.warning(f"screener.db selection failed: {e}")

    # Fallback: hardcoded list
    LIQUID = [
        "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "UNH", "JNJ",
        "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "LLY", "AVGO",
        "PEP", "KO", "COST", "WMT", "MCD", "CSCO", "TMO", "ABT", "ACN", "DHR",
        "VZ", "NEE", "TXN", "PM", "UNP", "LOW", "HON", "AMGN", "IBM", "QCOM",
        "SPGI", "CAT", "BA", "GE", "ISRG", "MDT", "BLK", "GILD", "SYK", "ADP",
        "VRTX", "ADI", "CB", "MMC", "CI", "CME", "SO", "DUK", "BMY", "SCHW",
        "PLD", "ZTS", "BSX", "REGN", "KLAC", "SLB", "EQIX", "APD", "ITW",
        "SHW", "HUM", "MCK", "CL", "FCX", "NSC", "PNC", "TFC", "USB", "COF",
        "AON", "ICE", "CMI", "WM", "EMR", "ADBE", "ORCL", "CRM", "INTU", "AMAT",
        "MU", "LRCX", "KLAC", "MCHP", "NXPI", "FTNT", "PANW", "WDAY", "DDOG", "SNOW",
        "CRWD", "NET", "ZS", "TEAM", "ABNB", "COIN", "PLTR", "RIVN", "LCID", "SOFI",
        "UPST", "AFRM", "HOOD", "RBLX", "U", "DKNG", "MARA", "RIOT", "SQ",
        "PYPL", "SHOP", "SE", "MELI", "VIPS", "BABA", "JD", "PDD", "NIO", "XPEV",
        "LI", "BYD", "TM", "HMC", "F", "GM", "STLA", "RACE", "TSM",
        "AVGO", "MRVL", "ON", "SMCI", "ARM", "AMD", "INTC", "TOST", "PAYX",
        "ADSK", "CDNS", "SNPS", "ANET", "DELL", "HPE", "HPQ", "WDC",
        "NTAP", "TDC", "INFY", "WIT", "CTSH", "EPAM", "GLW",
    ]
    seen = set()
    unique = []
    for s in LIQUID:
        if s not in seen and len(s) <= 5:
            seen.add(s)
            unique.append(s)
    top = unique[:n]

    vol_map = _get_avg_volumes(top)
    for s in top:
        conn.execute(
            "INSERT OR REPLACE INTO symbols (symbol, avg_volume) VALUES (?, ?)",
            (s, vol_map.get(s, 0))
        )
    conn.commit()
    conn.close()
    return top


def _get_avg_volumes(symbols, batch_size=100):
    """Get average daily volume for symbols."""
    vol_map = {}
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        params = {
            "symbols": ",".join(batch),
            "timeframe": "1Day",
            "start": start,
            "end": end,
            "limit": 10000,
            "adjustment": "split",
            "feed": "iex",
            "sort": "desc",
        }
        data = _api_get(f"{ALPACA_DATA_URL}/v2/stocks/bars", params)
        if data and "bars" in data:
            for sym, bars in data["bars"].items():
                if bars:
                    total_vol = sum(int(b.get("v", 0)) for b in bars)
                    vol_map[sym] = total_vol / len(bars) if bars else 0
    return vol_map


def get_cached_bars(symbols, timeframe, conn=None):
    """Load cached bars from DB as dict of symbol -> list of (timestamp, close)."""
    own_conn = conn is None
    if own_conn:
        conn = get_db()
    try:
        result = {}
        for sym in symbols:
            rows = conn.execute(
                "SELECT timestamp, close FROM bars WHERE symbol=? AND timeframe=? ORDER BY timestamp ASC",
                (sym, timeframe)
            ).fetchall()
            if rows:
                result[sym] = rows
        return result
    finally:
        if own_conn:
            conn.close()


def get_bar_dates(symbols, timeframe, days_back=None):
    """Get sorted list of common timestamps across symbols.
    Also returns the subset of symbols that were used.
    If days_back is set, only return timestamps from the last N days.
    Returns (timestamps, used_symbols)."""
    from datetime import datetime, timedelta, timezone
    init_db()
    conn = get_db()

    # Min timestamps needed for Weighted Alpha (WA_LOOKBACK=250 + WA_SMOOTH=26)
    min_needed = 276
    if timeframe == "1Min":
        min_needed = 100  # 1Min data is sparse, relax requirement
    elif timeframe == "1Hour":
        min_needed = 150
    elif timeframe == "1Day":
        min_needed = 100  # Daily bars: fewer needed

    try:
        # First: find which symbols actually have data for this timeframe
        available = []
        for sym in symbols:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM bars WHERE symbol=? AND timeframe=?",
                (sym, timeframe)
            ).fetchone()[0]
            if cnt > 0:
                available.append(sym)

        if not available:
            return [], []

        # Use all available symbols (not just top N)
        use_syms = available[:200]

        # Try decreasing thresholds on symbol overlap
        for threshold_pct in [0.5, 0.3, 0.2, 0.1, 0.05]:
            min_count = max(int(len(use_syms) * threshold_pct), 3)
            rows = conn.execute(
                "SELECT timestamp, COUNT(DISTINCT symbol) as cnt FROM bars "
                "WHERE timeframe=? AND symbol IN ({}) "
                "GROUP BY timestamp HAVING cnt >= ? ORDER BY timestamp ASC".format(
                    ",".join("?" * len(use_syms))
                ),
                [timeframe] + use_syms + [min_count]
            ).fetchall()
            timestamps = [r[0] for r in rows]
            if days_back and timestamps:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
                timestamps = [t for t in timestamps if t >= cutoff]
            if len(timestamps) >= min_needed:
                # Filter to only symbols that have data at these timestamps
                ts_set = set(timestamps)
                coverage_threshold = 0.5 if timeframe in ("1Min", "1Hour") else 0.8
                good_syms = []
                for sym in use_syms:
                    sym_ts = set(r[0] for r in conn.execute(
                        "SELECT timestamp FROM bars WHERE symbol=? AND timeframe=?",
                        (sym, timeframe)
                    ).fetchall())
                    if len(sym_ts & ts_set) >= len(timestamps) * coverage_threshold:
                        good_syms.append(sym)
                return timestamps, good_syms[:200]

        # Last resort: just return whatever we have, pick symbols with most data
        sym_counts = [(s, conn.execute(
            "SELECT COUNT(*) FROM bars WHERE symbol=? AND timeframe=?", (s, timeframe)
        ).fetchone()[0]) for s in use_syms]
        sym_counts.sort(key=lambda x: x[1], reverse=True)
        top_syms = [s[0] for s in sym_counts if s[1] > 0][:50]

        if top_syms:
            min_count = max(int(len(top_syms) * 0.05), 2)
            rows = conn.execute(
                "SELECT timestamp, COUNT(DISTINCT symbol) as cnt FROM bars "
                "WHERE timeframe=? AND symbol IN ({}) "
                "GROUP BY timestamp HAVING cnt >= ? ORDER BY timestamp ASC".format(
                    ",".join("?" * len(top_syms))
                ),
                [timeframe] + top_syms + [min_count]
            ).fetchall()
            timestamps = [r[0] for r in rows]
            if days_back and timestamps:
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
                timestamps = [t for t in timestamps if t >= cutoff]
            if timestamps:
                used = conn.execute(
                    "SELECT DISTINCT symbol FROM bars WHERE timeframe=? AND symbol IN ({})".format(
                        ",".join("?" * len(top_syms))
                    ),
                    [timeframe] + top_syms
                ).fetchall()
                return timestamps, [r[0] for r in used]

        return [], []
    finally:
        conn.close()
