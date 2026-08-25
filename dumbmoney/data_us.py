import requests
import time
import logging
import threading
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dumbmoney.config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_DATA_URL, ALPACA_BASE_URL

logger = logging.getLogger(__name__)

_yf_session_lock = threading.Lock()
_yf_session_data = None


def _make_yf_session():
    """Create a single authenticated Yahoo Finance session with cookie + crumb."""
    global _yf_session_data
    with _yf_session_lock:
        if _yf_session_data is not None:
            return _yf_session_data
        s = requests.Session()
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10,
                              max_retries=Retry(total=2, backoff_factor=0.1,
                                                status_forcelist=[429, 500, 502, 503, 504]))
        s.mount('https://', adapter)
        s.get('https://fc.yahoo.com', timeout=5)
        r = s.get('https://query2.finance.yahoo.com/v1/test/getcrumb', timeout=5)
        _yf_session_data = (s, r.text)
        return _yf_session_data

_session = requests.Session()
_session.headers.update({
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
})


class RateLimiter:
    def __init__(self, max_requests=180, window=60):
        self.max_requests = max_requests
        self.window = window
        self.timestamps = []

    def wait(self):
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < self.window]
        if len(self.timestamps) >= self.max_requests:
            sleep_time = self.window - (now - self.timestamps[0]) + 0.5
            if sleep_time > 0:
                time.sleep(sleep_time)
        self.timestamps.append(time.time())


_rate_limiter = RateLimiter(max_requests=190, window=60)


def _api_get(url, params=None, timeout=30):
    _rate_limiter.wait()
    try:
        resp = _session.get(url, params=params, timeout=timeout)
        if resp.status_code == 429:
            time.sleep(5)
            resp = _session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Alpaca API error: {url} - {e}")
        return None


def sync_assets(force=False, cache_max_age_days=7):
    """Fetch US assets from Alpaca and upsert into assets table.
    Normal refresh reuses today's universe because bars, stats, and history are the
    expensive freshness path. Use force=True for an explicit universe refresh.
    """
    from dumbmoney.db import get_db
    conn = get_db("US")
    try:
        row = conn.execute(
            "SELECT COUNT(*), MAX(last_updated) FROM assets WHERE status='active'"
        ).fetchone()
        if not force and row and row[0] and row[1]:
            try:
                last_dt = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00")).replace(tzinfo=None)
                age_days = (datetime.utcnow() - last_dt).total_seconds() / 86400
                if age_days <= cache_max_age_days:
                    return int(row[0])
            except Exception:
                pass
    finally:
        conn.close()

    assets = []
    params = {"status": "active", "asset_class": "us_equity"}
    url = f"{ALPACA_BASE_URL}/v2/assets"
    for _ in range(200):
        data = _api_get(url, params=params)
        if not data:
            break
        assets.extend(data)
        if len(data) < 100:
            break
        params["page_token"] = data[-1].get("id", "")
        if not params.get("page_token"):
            break

    junk_patterns = [".W", ".R", ".U", ".P", ".C", ".D", ".E", ".F", "WARRANT",
                     "RIGHT", "UNIT", "PREFERRED", "BOND", "NOTE", "DEBT"]
    etf_name_keywords = [" etf", "etf ", " index fund", " index etf",
                         "spdr ", "ishares ", "proshares ", "first trust ",
                         "global x ", "flexshares ", "powershares ", "rydex ",
                         "dimensional ", "wisdomtree "]
    cef_keywords = ["closed-end", "closed end"]
    bond_etf_name_keywords = ["treasury", "bond", "aggregate", "fixed income",
                              "mortgage-backed", "tips", "inflation-protected"]
    bond_etf_exact_syms = {
        "TLT", "TBT", "TMF", "TMO", "TYD", "TYO", "UST", "DLBS", "ILTB",
        "IEF", "SHY", "IEI", "VGIT", "VGLT", "VGSH", "SGOV", "BIL", "SHV",
        "AGG", "BND", "BNDX", "SCHZ", "VCSH", "VCIT", "LQD", "HYG",
        "MBB", "MBB", "TLT", "TIP", "TIPX", "SCHP", "VTIP",
        "USHY", "HYLB", "USHY", "JNK", "HYG", "USHY",
        "BKLN", "SRLN", "FLRN",
        "VGSR", "VGUS", "TOTL", "TUA",
        "MUB", "VTEB", "TFI", "PZA", "PZT",
        "SHV", "BIL", "SGOV", "VGSH", "UBIL", "GBIL",
    }
    etf_exact_syms = {
        "SPY", "QQQ", "IVV", "VOO", "DIA", "USO", "GLD", "SLV",
        "VNQ", "EWJ", "EWW",
        "EFA", "VWO", "FXI", "KWEB", "GDX", "GDXJ",
        "XLF", "XLE", "XLU", "XLK", "XLB", "XLP", "XLI", "XLY", "XLRE",
        "ARKK", "ARKG", "ARKF", "ARKW", "ARKQ", "ARKB", "ARKX",
        "SOXX", "SMH", "IWM", "MDY", "EEM", "VEA", "VGK",
        "IWO", "IWF", "IWD", "IWB",
        "SCHD", "VYM", "HDV", "DGRO", "SCHX",
        "VTI", "VXUS", "IEFA", "IEMG",
        "SPHD", "SPLV", "NOBL", "VIG", "SCHV", "MTUM", "QUAL",
        "RPV", "RPG", "VLUE", "USMV",
        "XME", "XHB", "XRT", "XOP", "XBI", "XSD",
        "ITA", "PPA", "VIS", "IYC", "IYK", "IYH", "IYZ",
        "IYR", "IYJ", "IYM", "IYE", "IAU", "GLDM", "SGOL",
        "DBC", "PDBC", "UVIX", "VXX", "VIXY",
        "UGL", "GLL", "ZSL", "AGQ", "SIVR",
        "UUP", "UDN", "FXE", "FXY", "FXB", "FXA", "FXC",
        "URNM", "URNJ", "URA",
        "VAW", "VB", "VBK", "VBR", "VCR", "VDC", "VEGI",
        "VEGN", "VEU", "VFLO", "VFQY", "VFVA",
        "UYLD", "BITO", "IBIT", "GBTC", "ETHE",
    }

    filtered = []
    for a in assets:
        sym = a.get("symbol", "")
        name = a.get("name", "")
        skip = False
        for pat in junk_patterns:
            if pat in sym.upper() or pat in name.upper():
                skip = True
                break
        if not skip:
            filtered.append(a)

    def classify_asset(a):
        name_lower = a.get("name", "").lower()
        sym_upper = a.get("symbol", "").upper()
        alpaca_class = a.get("class", "us_equity")
        if sym_upper in bond_etf_exact_syms:
            return "bond_etf"
        for kw in bond_etf_name_keywords:
            if kw in name_lower:
                return "bond_etf"
        if alpaca_class == "etf":
            return "etf"
        if sym_upper in etf_exact_syms:
            return "etf"
        for kw in cef_keywords:
            if kw in name_lower:
                return "cef"
        for pat in etf_name_keywords:
            if pat in name_lower:
                return "etf"
        return "stock"

    conn = get_db("US")
    now = datetime.utcnow().isoformat()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO assets (symbol, name, asset_class, exchange, status,
               tradable, fractionable, marginable, shortable, margin_requirement_long,
               margin_requirement_short, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(a["symbol"], a.get("name", ""), classify_asset(a),
              a.get("exchange", ""), a.get("status", "active"),
              1 if a.get("tradable") else 0,
              1 if a.get("fractionable") else 0,
              1 if a.get("marginable") else 0,
              1 if a.get("shortable") else 0,
              str(a.get("margin", {}).get("long", "") if isinstance(a.get("margin"), dict) else ""),
              str(a.get("margin", {}).get("short", "") if isinstance(a.get("margin"), dict) else ""),
              now) for a in filtered]
        )
        conn.commit()
    finally:
        conn.close()
    return len(filtered)


def download_bars(symbols, start_date=None, timeframe="1Day", batch_size=2000, max_workers=8, incremental=False, progress_callback=None, cancel_check=None, adjustment="split"):
    """Download daily bars for US symbols using Alpaca multi-symbol endpoint.
    Optimized: large batches, parallel downloads, bulk DB writes.
    incremental=True: skip pagination (1 page per batch, ~3 bars/symbol).
    adjustment: "split" (default) or "raw" — reverse-split+spin-off survivors
    are stored raw because split-adjustment inflates their pre-event history.
    cancel_check: fn() -> bool — aborts pending batches/pages when it returns True."""
    from dumbmoney.db import get_db
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if not symbols:
        return 0

    if start_date is None:
        start_date = "1970-01-01"

    def _fetch_batch(batch):
        symbols_str = ",".join(batch)
        params = {
            "symbols": symbols_str,
            "timeframe": timeframe,
            "start": start_date,
            "limit": 10000,
            "adjustment": adjustment,
            "feed": "iex",
            "sort": "asc"
        }
        all_bars = []
        data = _api_get(f"{ALPACA_DATA_URL}/v2/stocks/bars", params=params)
        if not data or "bars" not in data:
            return all_bars

        for sym, bars in data["bars"].items():
            for bar in bars:
                all_bars.append((
                    sym, timeframe, bar["t"][:10],
                    bar["o"], bar["h"], bar["l"], bar["c"], int(bar["v"])
                ))

        if not incremental:
            while data.get("next_page_token"):
                if cancel_check and cancel_check():
                    return all_bars
                params["page_token"] = data["next_page_token"]
                data = _api_get(f"{ALPACA_DATA_URL}/v2/stocks/bars", params=params)
                if not data or "bars" not in data:
                    break
                for sym, bars in data["bars"].items():
                    for bar in bars:
                        all_bars.append((
                            sym, timeframe, bar["t"][:10],
                            bar["o"], bar["h"], bar["l"], bar["c"], int(bar["v"])
                        ))
        return all_bars

    batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    total_written = 0
    done_batches = 0
    total_batches = len(batches)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_batch, b): b for b in batches}
        conn = get_db("US")
        try:
            cancelled = False
            for future in as_completed(futures):
                if cancelled:
                    break
                try:
                    bars = future.result()
                    if bars:
                        conn.executemany(
                            """INSERT OR REPLACE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            bars
                        )
                        conn.commit()
                        total_written += len(bars)
                except Exception as e:
                    logger.warning(f"Download batch error: {e}")
                done_batches += 1
                if progress_callback and done_batches % 2 == 0:
                    progress_callback(done_batches, total_batches)
                if cancel_check and cancel_check():
                    cancelled = True
        finally:
            conn.close()

    return total_written


def get_snapshots(symbols, batch_size=200):
    """Get latest snapshots for many symbols in ONE call."""
    all_snapshots = {}
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        symbols_str = ",".join(batch)
        data = _api_get(f"{ALPACA_DATA_URL}/v2/stocks/snapshots", params={"symbols": symbols_str})
        if data:
            for sym, snap in data.items():
                if snap:
                    all_snapshots[sym] = snap
    return all_snapshots


def get_stock_info(symbol):
    """Get asset details for a single stock."""
    data = _api_get(f"{ALPACA_BASE_URL}/v2/assets/{symbol}")
    return data


def get_options_chain(symbol):
    """Get options expiries + calls/puts for US symbol."""
    data = _api_get(f"{ALPACA_DATA_URL}/v1beta1/options/snapshots/{symbol}", params={"feed": "indicative"})
    if not data:
        return {"expiries": [], "calls": [], "puts": []}

    expiries = set()
    calls = []
    puts = []

    for contract_id, snap in data.get("snapshots", {}).items():
        parts = contract_id.split()
        if len(parts) < 3:
            continue
        exp = parts[1]
        opt_type = parts[2][0] if len(parts[2]) > 0 else ""
        expiries.add(exp)

        opt_data = {
            "symbol": contract_id,
            "expiry": exp,
            "strike": float(parts[2][1:]) if len(parts[2]) > 1 else 0,
            "bid": snap.get("latestTrade", {}).get("p", 0),
            "ask": snap.get("latestTrade", {}).get("p", 0),
            "last": snap.get("latestTrade", {}).get("p", 0),
            "volume": snap.get("dailyBar", {}).get("v", 0),
            "open_interest": 0,
            "implied_volatility": snap.get("impliedVolatility", 0),
        }
        if opt_type == "C":
            calls.append(opt_data)
        elif opt_type == "P":
            puts.append(opt_data)

    return {
        "expiries": sorted(expiries),
        "calls": sorted(calls, key=lambda x: x.get("strike", 0)),
        "puts": sorted(puts, key=lambda x: x.get("strike", 0))
    }


def get_news(symbol, limit=20):
    """Get news for a US symbol from Alpaca."""
    data = _api_get(f"{ALPACA_DATA_URL}/v1beta1/news", params={"symbols": symbol, "limit": limit})
    if not data:
        return []
    articles = []
    for item in data.get("news", []):
        articles.append({
            "id": item.get("id", ""),
            "headline": item.get("headline", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "created_at": item.get("created_at", ""),
            "symbols": item.get("symbols", []),
        })
    return articles


def get_news_search(query, limit=20):
    """Search news across all symbols."""
    data = _api_get(f"{ALPACA_DATA_URL}/v1beta1/news", params={"q": query, "limit": limit})
    if not data:
        return []
    articles = []
    for item in data.get("news", []):
        articles.append({
            "id": item.get("id", ""),
            "headline": item.get("headline", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "created_at": item.get("created_at", ""),
            "symbols": item.get("symbols", []),
        })
    return articles


def get_corporate_events(symbol, start=None, end=None):
    """Get corporate events for a symbol."""
    if start is None:
        start = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
    if end is None:
        end = (datetime.utcnow() + timedelta(days=90)).strftime("%Y-%m-%d")
    data = _api_get(f"{ALPACA_BASE_URL}/v1CorporateEvents/{symbol}", params={"start": start, "end": end})
    if not data:
        return []
    events = []
    for evt in data.get("corporate_actions", []):
        events.append({
            "symbol": symbol,
            "event_type": evt.get("type", ""),
            "event_date": evt.get("ex_date", ""),
            "description": evt.get("description", "")
        })
    return events


def download_corporate_events(symbols, conn):
    """Download and store corporate events for symbols."""
    now = datetime.utcnow().isoformat()
    for sym in symbols[:500]:
        events = get_corporate_events(sym)
        for evt in events:
            conn.execute(
                """INSERT OR IGNORE INTO corporate_events (symbol, event_type, event_date, description)
                   VALUES (?, ?, ?, ?)""",
                (evt["symbol"], evt["event_type"], evt["event_date"], evt["description"])
            )
        time.sleep(0.1)
    conn.commit()


def get_alpaca_news(symbol, limit=20):
    return get_news(symbol, limit)


def get_live_prices(symbols):
    """Batched live prices."""
    snapshots = get_snapshots(symbols)
    prices = {}
    for sym, snap in snapshots.items():
        daily = snap.get("dailyBar", {})
        prev = snap.get("prevDailyBar", {})
        price = daily.get("c", 0)
        prev_close = prev.get("c", 0) if prev else 0
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0
        prices[sym] = {
            "price": price,
            "change_pct": round(change_pct, 2),
            "volume": daily.get("v", 0),
            "open": daily.get("o", 0),
            "high": daily.get("h", 0),
            "low": daily.get("l", 0),
        }
    return prices


def update_pre_post_prices(market="US", progress_callback=None, symbols=None):
    """Update pre_price, pre_change_pct, post_price, post_change_pct from Alpaca snapshots.
    pre_price = today's open (price at market open / pre-market start).
    post_price = today's close (latest close / after-hours).
    pre_change_pct = (open - prev_close) / prev_close * 100.
    post_change_pct = (close - prev_close) / prev_close * 100."""
    from dumbmoney.db import get_db
    conn = get_db(market)
    try:
        if symbols is None:
            symbols = [r[0] for r in conn.execute(
                "SELECT symbol FROM stats WHERE asset_class IN ('stock','etf') OR asset_class IS NULL LIMIT 5000"
            ).fetchall()]
        else:
            symbols = sorted(set(symbols))
        if not symbols:
            if progress_callback:
                progress_callback(100, "No pre/post symbols changed")
            return
        total = len(symbols)
        batch_size = 200
        updated = 0
        for i in range(0, total, batch_size):
            batch = symbols[i:i + batch_size]
            if progress_callback:
                progress_callback(round(i / total * 100), f"Fetching snapshots {i+len(batch)}/{total}...")
            snapshots = get_snapshots(batch)
            for sym, snap in snapshots.items():
                daily = snap.get("dailyBar", {})
                prev = snap.get("prevDailyBar", {})
                prev_close = prev.get("c", 0) if prev else 0
                open_price = daily.get("o", 0)
                close_price = daily.get("c", 0)
                pre_change = ((open_price - prev_close) / prev_close * 100) if prev_close > 0 and open_price > 0 else 0
                post_change = ((close_price - prev_close) / prev_close * 100) if prev_close > 0 and close_price > 0 else 0
                conn.execute(
                    "UPDATE stats SET pre_price=?, pre_change_pct=?, post_price=?, post_change_pct=? WHERE symbol=?",
                    (open_price, round(pre_change, 4), close_price, round(post_change, 4), sym)
                )
                updated += 1
            conn.commit()
        if progress_callback:
            progress_callback(100, f"Updated pre/post for {updated} symbols")
    finally:
        conn.close()


def place_paper_order(symbol, qty, side, order_type="market"):
    """Place an order in the Alpaca paper account."""
    data = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": "day"
    }
    resp = _session.post(f"{ALPACA_BASE_URL}/v2/orders", json=data, timeout=10)
    if resp.status_code in (200, 201):
        return resp.json()
    return None


def get_positions():
    """Get current paper account positions."""
    data = _api_get(f"{ALPACA_BASE_URL}/v2/positions")
    if not data:
        return []
    positions = []
    for pos in data:
        positions.append({
            "symbol": pos.get("symbol", ""),
            "qty": float(pos.get("qty", 0)),
            "avg_entry_price": float(pos.get("avg_entry_price", 0)),
            "current_price": float(pos.get("current_price", 0)),
            "market_value": float(pos.get("market_value", 0)),
            "unrealized_pl": float(pos.get("unrealized_pl", 0)),
            "unrealized_plpc": float(pos.get("unrealized_plpc", 0)),
            "side": pos.get("side", "long"),
        })
    return positions


def get_account():
    """Get paper account info."""
    data = _api_get(f"{ALPACA_BASE_URL}/v2/account")
    if not data:
        return {}
    return {
        "equity": float(data.get("equity", 0)),
        "cash": float(data.get("cash", 0)),
        "buying_power": float(data.get("buying_power", 0)),
        "portfolio_value": float(data.get("portfolio_value", 0)),
        "status": data.get("status", ""),
    }


def fetch_earnings_yahoo(symbol, session=None, crumb=None):
    """Fetch latest earnings data from Yahoo Finance for a US symbol."""
    try:
        if session is None:
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            session.get("https://fc.yahoo.com", timeout=5)
            crumb_resp = session.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=5)
            crumb = crumb_resp.text

        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
        params = {"modules": "earningsHistory,earningsTrend", "crumb": crumb}
        resp = session.get(url, params=params, timeout=(3, 8))
        if resp.status_code != 200:
            return None
        data = resp.json()
        result = data.get("quoteSummary", {}).get("result", [{}])
        if not result:
            return None
        result = result[0]

        earnings_history = result.get("earningsHistory", {})
        history = earnings_history.get("history", [])
        if not history:
            return None

        latest = history[0]
        eps_actual = latest.get("epsActual", {}).get("raw")
        eps_estimate = latest.get("epsEstimate", {}).get("raw")
        surprise_pct_raw = latest.get("surprisePercent", {}).get("raw")

        profit_status = None
        profit_last_qtr_pct = None
        profit_millions = None
        profit_expectations = None

        if surprise_pct_raw is not None:
            profit_last_qtr_pct = round(surprise_pct_raw * 100, 2)
            if surprise_pct_raw > 0:
                profit_status = "beat"
            elif surprise_pct_raw < 0:
                profit_status = "miss"
            else:
                profit_status = "in-line"

        if eps_actual is not None:
            profit_millions = round(eps_actual, 2)

        earnings_trend = result.get("earningsTrend", {}).get("trend", [])
        for trend in earnings_trend:
            if trend.get("period") == "0q":
                earnings_est = trend.get("earningsEstimate", {}).get("avg", {})
                if earnings_est and earnings_est.get("raw") is not None:
                    profit_expectations = f"Est ${earnings_est['raw']:.2f}/share ({trend.get('endDate', '')})"
                break

        return {
            "profit_status": profit_status,
            "profit_last_qtr_pct": profit_last_qtr_pct,
            "profit_millions": profit_millions,
            "profit_expectations": profit_expectations,
        }
    except Exception:
        return None


def update_profit_data(market="US", symbols=None, progress_callback=None):
    """Fetch and update profit/earnings data from Yahoo Finance for given symbols.
    Uses parallel workers with a pool of Yahoo sessions."""
    from dumbmoney.db import get_db
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    import queue

    conn = get_db(market)
    try:
        if symbols is None:
            symbols = [r[0] for r in conn.execute(
                "SELECT symbol FROM stats WHERE asset_class IN ('stock','etf') OR asset_class IS NULL"
            ).fetchall()]
        else:
            symbols = sorted(set(symbols))
        total = len(symbols)
        if total == 0:
            return

        session_pool = queue.Queue()
        pool_size = 40
        failed_count = [0]
        _pool_lock = threading.Lock()

        def _create_pool():
            for _ in range(pool_size):
                try:
                    session_pool.put(_make_yf_session())
                except Exception:
                    pass

        try:
            _create_pool()
        except Exception as e:
            logger.warning(f"Failed to create Yahoo sessions for earnings: {e}")
            if progress_callback:
                progress_callback(100, "Skipped earnings (no Yahoo session)")
            return

        if session_pool.empty():
            logger.warning("No Yahoo sessions created for earnings")
            if progress_callback:
                progress_callback(100, "Skipped earnings (no Yahoo session)")
            return

        done_count = [0]
        updated_count = [0]
        _done_lock = threading.Lock()

        def _fetch_one(sym):
            session_tuple = session_pool.get()
            try:
                session, crumb = session_tuple
                info = fetch_earnings_yahoo(sym, session=session, crumb=crumb)
                if info is None:
                    try:
                        session_tuple = _make_yf_session()
                        info = fetch_earnings_yahoo(sym, session=session_tuple[0], crumb=session_tuple[1])
                    except Exception:
                        pass
            except Exception:
                info = None
                try:
                    session_tuple = _make_yf_session()
                except Exception:
                    pass

            session_pool.put(session_tuple)

            with _done_lock:
                done_count[0] += 1
                if info:
                    updated_count[0] += 1
                if done_count[0] % 200 == 0:
                    if progress_callback:
                        progress_callback(round(done_count[0] / total * 100, 1),
                                          f"Fetching earnings {done_count[0]}/{total}...")
            return sym, info

        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            futures = {executor.submit(_fetch_one, s): s for s in symbols}
            batch = []
            for f in as_completed(futures):
                try:
                    sym, info = f.result()
                    if info:
                        batch.append((
                            info["profit_status"], info["profit_last_qtr_pct"],
                            info["profit_millions"], info["profit_expectations"], sym
                        ))
                        if len(batch) >= 500:
                            conn.executemany(
                                """UPDATE stats SET profit_status=?, profit_last_qtr_pct=?,
                                   profit_millions=?, profit_expectations=? WHERE symbol=?""",
                                batch
                            )
                            conn.commit()
                            batch = []
                except Exception:
                    pass

            if batch:
                conn.executemany(
                    """UPDATE stats SET profit_status=?, profit_last_qtr_pct=?,
                       profit_millions=?, profit_expectations=? WHERE symbol=?""",
                    batch
                )
                conn.commit()

        if progress_callback:
            progress_callback(100, f"Updated profit data for {updated_count[0]}/{total} symbols")
    finally:
        conn.close()


def _us_snapshot_constituents(table_name, current_syms, label):
    """Generic SCD-Type-2 snapshot for US constituents tables."""
    from dumbmoney.db import get_db
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_db("US")
    try:
        existing = set(
            r[0] for r in conn.execute(
                f"SELECT symbol FROM {table_name} WHERE to_date = '9999-12-31'"
            ).fetchall()
        )
        removed = existing - current_syms
        added = current_syms - existing

        if removed:
            conn.executemany(
                f"UPDATE {table_name} SET to_date = ? WHERE symbol = ? AND to_date = '9999-12-31'",
                [(today, s) for s in removed]
            )
        if added:
            for sym in added:
                earliest = conn.execute(
                    "SELECT MIN(date) FROM bars WHERE symbol = ? AND timeframe = '1Day'",
                    (sym,)
                ).fetchone()[0]
                from_date = earliest or '2015-01-01'
                conn.execute(
                    f"INSERT OR IGNORE INTO {table_name} (symbol, from_date, to_date) VALUES (?, ?, '9999-12-31')",
                    (sym, from_date)
                )
        conn.commit()
        logger.info(f"{label} snapshot: {len(added)} added, {len(removed)} removed (total active: {len(current_syms)})")
        return len(added), len(removed)
    finally:
        conn.close()


_INDEX_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".cache")
_INDEX_CACHE_TTL_DAYS = 7


def _get_index_cache_path(table_name):
    os.makedirs(_INDEX_CACHE_DIR, exist_ok=True)
    return os.path.join(_INDEX_CACHE_DIR, f"index_{table_name}.json")


def _load_index_cache(table_name):
    import json, time
    path = _get_index_cache_path(table_name)
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                entry = json.load(f)
            age_days = (time.time() - entry.get("ts", 0)) / 86400
            if age_days <= _INDEX_CACHE_TTL_DAYS:
                return entry.get("syms", [])
    except Exception:
        pass
    return None


def _save_index_cache(table_name, syms):
    import json, time
    path = _get_index_cache_path(table_name)
    try:
        with open(path, "w") as f:
            json.dump({"ts": time.time(), "syms": sorted(syms)}, f)
    except Exception:
        pass


def _fetch_sp500_remote():
    import pandas as pd
    from io import StringIO
    from curl_cffi import requests as cffi_req
    session = cffi_req.Session(impersonate="chrome120")
    resp = session.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        timeout=15)
    if resp.status_code != 200:
        logger.warning(f"S&P 500 Wikipedia returned status {resp.status_code}")
        return None
    tables = pd.read_html(StringIO(resp.text))
    df = tables[0]
    current_syms = set()
    for s in df["Symbol"].tolist():
        sym = s.replace(".", "-").strip()
        if sym:
            current_syms.add(sym)
    return current_syms if current_syms else None


def update_sp500_constituents():
    """Fetch current S&P 500 list from Wikipedia and snapshot."""
    table_name = "sp500_constituents"
    cached = _load_index_cache(table_name)
    if cached is not None:
        return _us_snapshot_constituents(table_name, set(cached), "S&P 500")
    current_syms = _fetch_sp500_remote()
    if current_syms is None:
        logger.warning("S&P 500 Wikipedia returned 0 symbols")
        return -1, -1
    _save_index_cache(table_name, current_syms)
    return _us_snapshot_constituents(table_name, current_syms, "S&P 500")


def update_nasdaq100_constituents():
    """Fetch current Nasdaq 100 list from stockanalysis.com and snapshot."""
    table_name = "nasdaq100_constituents"
    cached = _load_index_cache(table_name)
    if cached is not None:
        return _us_snapshot_constituents(table_name, set(cached), "Nasdaq 100")
    try:
        import pandas as pd
        from io import StringIO
        from curl_cffi import requests as cffi_req
        session = cffi_req.Session(impersonate="chrome120")
        resp = session.get(
            "https://stockanalysis.com/list/nasdaq-100-stocks/",
            timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Nasdaq 100 page returned status {resp.status_code}")
            return -1, -1
        tables = pd.read_html(StringIO(resp.text))
        df = tables[0]
        current_syms = set()
        for s in df["Symbol"].tolist():
            sym = s.replace(".", "-").strip()
            if sym:
                current_syms.add(sym)
        if not current_syms:
            logger.warning("Nasdaq 100 page returned 0 symbols")
            return -1, -1
    except Exception as e:
        logger.warning(f"Failed to fetch Nasdaq 100: {e}")
        return -1, -1
    _save_index_cache(table_name, current_syms)
    return _us_snapshot_constituents(table_name, current_syms, "Nasdaq 100")


def update_russell2000_constituents():
    """Fetch Russell 2000 list from GitHub and snapshot."""
    table_name = "russell2000_constituents"
    cached = _load_index_cache(table_name)
    if cached is not None:
        return _us_snapshot_constituents(table_name, set(cached), "Russell 2000")
    try:
        import pandas as pd
        from io import StringIO
        from curl_cffi import requests as cffi_req
        session = cffi_req.Session(impersonate="chrome120")
        resp = session.get(
            "https://raw.githubusercontent.com/ikoniaris/Russell2000/master/russell_2000_components.csv",
            timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Russell 2000 CSV returned status {resp.status_code}")
            return -1, -1
        df = pd.read_csv(StringIO(resp.text))
        current_syms = set()
        for s in df["Ticker"].tolist():
            sym = str(s).replace(".", "-").strip()
            if sym and sym != "nan":
                current_syms.add(sym)
        if not current_syms:
            logger.warning("Russell 2000 CSV returned 0 symbols")
            return -1, -1
    except Exception as e:
        logger.warning(f"Failed to fetch Russell 2000: {e}")
        return -1, -1
    _save_index_cache(table_name, current_syms)
    return _us_snapshot_constituents(table_name, current_syms, "Russell 2000")


def update_dow30_constituents():
    """Fetch Dow Jones 30 list from Wikipedia and snapshot."""
    table_name = "dow30_constituents"
    cached = _load_index_cache(table_name)
    if cached is not None:
        return _us_snapshot_constituents(table_name, set(cached), "Dow Jones 30")
    try:
        import pandas as pd
        from io import StringIO
        from curl_cffi import requests as cffi_req
        session = cffi_req.Session(impersonate="chrome120")
        resp = session.get(
            "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
            timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Dow Jones Wikipedia returned status {resp.status_code}")
            return -1, -1
        tables = pd.read_html(StringIO(resp.text))
        current_syms = set()
        for t in tables:
            if "Symbol" in t.columns and len(t) == 30:
                for s in t["Symbol"].tolist():
                    sym = s.replace(".", "-").strip()
                    if sym:
                        current_syms.add(sym)
                break
        if not current_syms:
            logger.warning("Dow Jones Wikipedia returned 0 symbols")
            return -1, -1
    except Exception as e:
        logger.warning(f"Failed to fetch Dow Jones 30: {e}")
        return -1, -1
    _save_index_cache(table_name, current_syms)
    return _us_snapshot_constituents(table_name, current_syms, "Dow Jones 30")
