"""Delta Exchange India REST API client.

Handles products sync, ticker fetch, OHLC download, and authenticated
order/position/balance endpoints.
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from functools import lru_cache

import requests

from dumbmoney.config import (
    DELTA_BASE_URL, DELTA_API_KEY, DELTA_API_SECRET,
    CRYPTO_DB,
)

logger = logging.getLogger(__name__)

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "dumbmoney-crypto/1.0",
}


# ---------------------------------------------------------------------------
# Unauthenticated helpers
# ---------------------------------------------------------------------------

def _get(path, params=None):
    url = f"{DELTA_BASE_URL}{path}"
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        err = data.get("error", {})
        raise RuntimeError(f"Delta API error: {err}")
    return data.get("result", [])


def _post(path, body=None):
    url = f"{DELTA_BASE_URL}{path}"
    payload = json.dumps(body or {}, separators=(",", ":"))
    method = "POST"
    timestamp = str(int(time.time()))
    sig_data = method + timestamp + path + "" + payload
    signature = hmac.new(
        DELTA_API_SECRET.encode(), sig_data.encode(), hashlib.sha256
    ).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "api-key": DELTA_API_KEY,
        "timestamp": timestamp,
        "signature": signature,
    }
    r = requests.post(url, data=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def _delete(path, params=None):
    url = f"{DELTA_BASE_URL}{path}"
    method = "DELETE"
    timestamp = str(int(time.time()))
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items())) if params else ""
    sig_data = method + timestamp + path + "?" + query
    signature = hmac.new(
        DELTA_API_SECRET.encode(), sig_data.encode(), hashlib.sha256
    ).hexdigest()
    headers = {
        "api-key": DELTA_API_KEY,
        "timestamp": timestamp,
        "signature": signature,
    }
    r = requests.delete(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def fetch_products():
    """Fetch all products and upsert into crypto_products."""
    from dumbmoney.db import get_db
    products = _get("/v2/products")
    conn = get_db("CRYPTO")
    try:
        for p in products:
            # Columns must match the crypto_products schema exactly
            # (symbol, product_id, contract_type, tick_size, lot_size,
            #  default_leverage, initial_margin, state).
            conn.execute(
                """INSERT OR REPLACE INTO crypto_products
                   (symbol, product_id, contract_type, tick_size, lot_size,
                    default_leverage, initial_margin, state)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    p.get("symbol"),
                    p.get("id"),
                    p.get("contract_type"),
                    p.get("tick_size"),
                    p.get("lot_size"),
                    p.get("default_leverage"),
                    p.get("initial_margin"),
                    p.get("state", "live"),
                ),
            )
        conn.commit()
        logger.info(f"Synced {len(products)} Delta products")
        return len(products)
    finally:
        conn.close()


def get_all_products():
    """Return all live perpetual products from DB."""
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


# ---------------------------------------------------------------------------
# Tickers
# ---------------------------------------------------------------------------

def fetch_tickers():
    """Fetch live tickers for all products. Returns {symbol: ticker_dict}."""
    from dumbmoney.db import get_db
    tickers = _get("/v2/tickers")
    result = {}
    for t in tickers:
        sym = t.get("symbol")
        if not sym:
            continue
        result[sym] = {
            "symbol": sym,
            "product_id": t.get("product_id"),
            "mark_price": _f(t.get("mark_price")),
            "spot_price": _f(t.get("spot_price")),
            "best_bid": _f(t.get("best_bid")),
            "best_ask": _f(t.get("best_ask")),
            "best_bid_size": _f(t.get("best_bid_size")),
            "best_ask_size": _f(t.get("best_ask_size")),
            "volume": _f(t.get("volume_24h")),
            "oi": _f(t.get("oi")),
            "oi_value": _f(t.get("oi_value")),
            "funding_rate": _f(t.get("funding_rate")),
            "open": _f(t.get("open")),
            "high": _f(t.get("high")),
            "low": _f(t.get("low")),
            "close": _f(t.get("close")),
            "turnover": _f(t.get("turnover_24h")),
            "next_funding_time": t.get("next_funding_time"),
            "change_pct": _f(t.get("percentage_change_24h")),
        }
    return result


def update_live_columns(tickers=None):
    """Merge live ticker data (OI, funding, mark, bid/ask, 24h high/low) into
    crypto_stats. Prefers the warm WebSocket cache; falls back to a REST pull.
    These columns are displayed/filtered by the crypto screener and were
    previously never written after the initial backfill."""
    from dumbmoney.db import get_db
    if tickers is None:
        try:
            from dumbmoney import crypto_ws
            tickers = {k: dict(v) for k, v in crypto_ws.get_all_live_tickers().items()}
        except Exception:
            tickers = {}
    if not tickers:
        try:
            tickers = fetch_tickers()
        except Exception as e:
            logger.warning(f"ticker fetch for live columns failed: {e}")
            return 0
    conn = get_db("CRYPTO")
    updated = 0
    try:
        for sym, t in tickers.items():
            mark = _f(t.get("mark_price"))
            bid = _f(t.get("best_bid"))
            ask = _f(t.get("best_ask"))
            conn.execute(
                """UPDATE crypto_stats SET
                     oi=?, oi_value=?, funding_rate=?, mark_price=?,
                     bid=?, ask=?, spread=?,
                     high_24h=?, low_24h=?
                   WHERE symbol=?""",
                (
                    _f(t.get("oi")), _f(t.get("oi_value")),
                    _f(t.get("funding_rate")), mark,
                    bid, ask, (ask - bid) if (ask and bid) else 0.0,
                    _f(t.get("high")), _f(t.get("low")),
                    sym,
                ),
            )
            updated += 1
        conn.commit()
    finally:
        conn.close()
    return updated


def get_all_symbols():
    """Return list of all live perpetual symbols from DB."""
    from dumbmoney.db import get_db
    conn = get_db("CRYPTO")
    try:
        rows = conn.execute(
            "SELECT symbol FROM crypto_products WHERE state='live' AND contract_type='perpetual_futures' ORDER BY symbol"
        ).fetchall()
        return [r["symbol"] for r in rows]
    finally:
        conn.close()


def _f(v):
    """Safe float conversion."""
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# OHLC Candles
# ---------------------------------------------------------------------------

def download_candles(symbol, resolution="1d", days_back=730):
    """Download OHLC candles for a symbol. Paginates in 4000-candle chunks.
    Incremental: only downloads candles newer than the latest one in DB."""
    from dumbmoney.db import get_db
    conn = get_db("CRYPTO")
    try:
        # Find latest candle in DB for this symbol/timeframe.
        # Only fetch bars NEWER than what we already have.
        row = conn.execute(
            "SELECT MAX(date) FROM crypto_bars WHERE symbol=? AND timeframe=?",
            (symbol, resolution),
        ).fetchone()
        if row and row[0]:
            latest = row[0]
            try:
                if " " in latest:
                    dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
                else:
                    dt = datetime.strptime(latest, "%Y-%m-%d")
                start_ts = int(dt.timestamp()) + 1  # next bar after latest
            except Exception:
                start_ts = int(time.time()) - days_back * 86400
        else:
            start_ts = int(time.time()) - days_back * 86400

        now = int(time.time())
        # If already up to date (within 4 hours), skip entirely
        if now - start_ts < 14400:
            return 0

        end = now
        all_candles = []
        while True:
            params = {
                "symbol": symbol,
                "resolution": resolution,
                "start": start_ts,
                "end": end,
                "limit": 4000,
            }
            candles = _get("/v2/history/candles", params=params)
            if not candles:
                break
            all_candles.extend(candles)
            if len(candles) < 4000:
                break
            # Paginate: move end to oldest candle time - 1
            oldest_time = min(c.get("time", 0) for c in candles)
            if oldest_time <= 0:
                break
            end = oldest_time - 1
            # Safety: don't go before start_ts
            if end <= start_ts:
                break
        if not all_candles:
            return 0
        IST = timezone(timedelta(hours=5, minutes=30))
        rows = []
        for c in all_candles:
            ts = c.get("time", 0)
            if resolution in ("1d", "1w"):
                date_str = datetime.fromtimestamp(ts, tz=IST).strftime("%Y-%m-%d")
            else:
                date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            rows.append((
                symbol, resolution, date_str,
                c.get("open"), c.get("high"), c.get("low"), c.get("close"),
                c.get("volume", 0),
            ))
        conn.executemany(
            """INSERT OR REPLACE INTO crypto_bars
               (symbol, timeframe, date, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        logger.info(f"Downloaded {len(rows)} {resolution} candles for {symbol}")
        return len(rows)
    except Exception as e:
        logger.warning(f"Failed to download candles for {symbol} ({resolution}): {e}")
        return 0
    finally:
        conn.close()


# Max days_back per timeframe — API paginates, so these are generous upper bounds
TIMEFRAMES = {
    "1m": 365,    # ~1 year (556K+ candles for BTCUSD)
    "5m": 730,    # ~2 years
    "15m": 730,   # ~2 years
    "30m": 730,   # ~2 years
    "1h": 730,    # ~2 years
    "2h": 730,    # ~2 years
    "4h": 730,    # ~2 years
    "6h": 730,    # ~2 years
    "1d": 730,    # ~2 years (API has ~960 candles)
    "1w": 730,    # ~2 years (API has ~138 candles)
}


def rebuild_daily_ist():
    """Re-stamp all 1d and 1w candle dates from UTC to IST (UTC+5:30).
    Only changes dates that look like UTC (no time component, already YYYY-MM-DD).
    This is a one-time migration after switching to IST-based daily candles."""
    from dumbmoney.db import get_db
    IST = timezone(timedelta(hours=5, minutes=30))
    conn = get_db("CRYPTO")
    try:
        rows = conn.execute(
            "SELECT rowid, symbol, timeframe, date FROM crypto_bars WHERE timeframe IN ('1d','1w')"
        ).fetchall()
        if not rows:
            return 0
        updates = []
        for rowid, sym, tf, date_str in rows:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                dt_utc = dt.replace(tzinfo=timezone.utc)
                dt_ist = dt_utc.astimezone(IST)
                new_date = dt_ist.strftime("%Y-%m-%d")
                if new_date != date_str:
                    updates.append((new_date, rowid))
            except Exception:
                continue
        if updates:
            conn.executemany(
                "UPDATE crypto_bars SET date=? WHERE rowid=?",
                updates
            )
            conn.commit()
            logger.info(f"Re-stamped {len(updates)} 1d/1w candle dates from UTC to IST")
        return len(updates)
    finally:
        conn.close()


def backfill_all_timeframes(symbols=None, progress_callback=None):
    """Download all supported timeframes for all symbols. Returns (done, total)."""
    if symbols is None:
        symbols = get_all_symbols()
    if not symbols:
        return 0, 0
    total = len(symbols)
    done = 0
    for tf, days in TIMEFRAMES.items():
        for i, sym in enumerate(symbols):
            if progress_callback:
                progress_callback(
                    done / (total * len(TIMEFRAMES)) * 100,
                    f"Downloading {sym} {tf} ({days}d)"
                )
            download_candles(sym, resolution=tf, days_back=days)
            done += 1
    if progress_callback:
        progress_callback(100, f"Backfill complete: {done}/{total * len(TIMEFRAMES)}")
    return done, total * len(TIMEFRAMES)


# Hard floor for deep history: API retention ends well before this (probed ~Jan 2024)
HISTORY_FLOOR_TS = int(time.mktime(time.strptime("2018-01-01", "%Y-%m-%d")))
BACKFILL_RESOLUTIONS = ("1d", "1w")


def _backfill_symbol_history(symbol, resolutions=BACKFILL_RESOLUTIONS):
    """Extend one symbol's candles BACKWARD past the original days_back cap.
    Pages older-than-oldest-stored windows until the API returns nothing (its own
    retention floor). Returns number of new bars inserted."""
    from dumbmoney.db import get_db
    conn = get_db("CRYPTO")
    inserted = 0
    try:
        IST = timezone(timedelta(hours=5, minutes=30))
        for res in resolutions:
            row = conn.execute(
                "SELECT MIN(date) FROM crypto_bars WHERE symbol=? AND timeframe=?",
                (symbol, res),
            ).fetchone()
            if not row or not row[0]:
                continue  # no data yet; forward refresh seeds it first
            oldest = row[0]
            dt = (datetime.strptime(oldest, "%Y-%m-%d %H:%M:%S")
                  if " " in oldest else datetime.strptime(oldest, "%Y-%m-%d"))
            end_ts = int(dt.timestamp()) - 1
            while end_ts > HISTORY_FLOOR_TS:
                start_ts = max(HISTORY_FLOOR_TS, end_ts - 365 * 86400)
                try:
                    candles = _get("/v2/history/candles", params={
                        "symbol": symbol, "resolution": res,
                        "start": start_ts, "end": end_ts, "limit": 4000})
                except Exception:
                    break
                if not candles:
                    break
                rows = []
                for c in candles:
                    ts = c.get("time", 0)
                    if res in ("1d", "1w"):
                        date_str = datetime.fromtimestamp(ts, tz=IST).strftime("%Y-%m-%d")
                    else:
                        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    rows.append((symbol, res, date_str,
                                 c.get("open"), c.get("high"), c.get("low"),
                                 c.get("close"), c.get("volume", 0)))
                conn.executemany(
                    """INSERT OR REPLACE INTO crypto_bars
                       (symbol, timeframe, date, open, high, low, close, volume)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
                conn.commit()
                inserted += len(rows)
                oldest_time = min(c.get("time", 0) for c in candles)
                if len(candles) < 4000 or oldest_time <= start_ts + 60:
                    break  # page not full -> reached the API's floor
                end_ts = oldest_time - 1
        return inserted
    finally:
        conn.close()


def backfill_history(symbols=None, workers=6, progress_callback=None):
    """Deep-backfill daily+weekly history to the API's floor for every symbol.
    Threaded (each worker opens its own connection). Returns total bars added."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if symbols is None:
        symbols = get_all_symbols()
    if not symbols:
        return 0
    total_added = 0
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_backfill_symbol_history, s): s for s in symbols}
        for f in as_completed(futures):
            done += 1
            try:
                total_added += f.result()
            except Exception as e:
                logger.warning(f"history backfill failed for {futures[f]}: {e}")
            if progress_callback and done % 20 == 0:
                progress_callback(done / len(symbols) * 100,
                                  f"{done}/{len(symbols)} symbols (+{total_added} bars)")
    if progress_callback:
        progress_callback(100, f"history backfill: +{total_added} bars across {len(symbols)} symbols")
    return total_added


def get_chart_data(symbol, timeframe="1d", limit=500):
    """Return recent OHLC bars for charting."""
    from dumbmoney.db import get_db
    conn = get_db("CRYPTO")
    try:
        rows = conn.execute(
            """SELECT date, open, high, low, close, volume
               FROM crypto_bars WHERE symbol=? AND timeframe=?
               ORDER BY date DESC LIMIT ?""",
            (symbol, timeframe, limit),
        ).fetchall()
        return [{"time": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in reversed(rows)]
    finally:
        conn.close()


def get_available_timeframes(symbol):
    """Return list of timeframes available for a symbol."""
    from dumbmoney.db import get_db
    conn = get_db("CRYPTO")
    try:
        rows = conn.execute(
            "SELECT DISTINCT timeframe FROM crypto_bars WHERE symbol=? ORDER BY timeframe",
            (symbol,),
        ).fetchall()
        return [r["timeframe"] for r in rows]
    finally:
        conn.close()




def _get_auth(path, params=None):
    """Authenticated GET — signs request with api-key/timestamp/signature."""
    url = f"{DELTA_BASE_URL}{path}"
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items())) if params else ""
    timestamp = str(int(time.time()))
    sig_data = "GET" + timestamp + path + "?" + query
    signature = hmac.new(
        DELTA_API_SECRET.encode(), sig_data.encode(), hashlib.sha256
    ).hexdigest()
    headers = {
        **HEADERS,
        "api-key": DELTA_API_KEY,
        "timestamp": timestamp,
        "signature": signature,
    }
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        err = data.get("error", {})
        raise RuntimeError(f"Delta API error: {err}")
    return data.get("result", [])

# ---------------------------------------------------------------------------
# Authenticated endpoints (need API key)
# ---------------------------------------------------------------------------

def get_positions():
    """Get open positions (authenticated — /v2/positions is a private endpoint)."""
    return _get_auth("/v2/positions")


def get_balances():
    """Get wallet balances (authenticated — /v2/wallet/balances is private)."""
    return _get_auth("/v2/wallet/balances")


def get_open_orders():
    """Get currently open orders (authenticated)."""
    return _get_auth("/v2/orders", {"states": "open"})


def place_order(product_id, size, side, order_type="market_order",
                limit_price=None, stop_price=None, time_in_force="gtc",
                leverage=None):
    """Place an order. Returns order response."""
    body = {
        "product_id": product_id,
        "size": size,
        "side": side,
        "order_type": order_type,
        "time_in_force": time_in_force,
    }
    if limit_price:
        body["limit_price"] = str(limit_price)
    if stop_price:
        body["stop_price"] = str(stop_price)
    if leverage:
        body["leverage"] = str(leverage)
    return _post("/v2/orders", body)


def cancel_order(order_id, product_id):
    """Cancel an order."""
    return _delete("/v2/orders", {"id": order_id, "product_id": product_id})


def get_order_history(product_id=None):
    """Get order history."""
    params = {}
    if product_id:
        params["product_id"] = product_id
    return _get_auth("/v2/orders", params)


# ---------------------------------------------------------------------------
# Authenticated endpoints (extended)
# ---------------------------------------------------------------------------

def get_trade_history(product_id=None, limit=50):
    """Get trade/order history. Returns list of orders."""
    params = {"limit": min(int(limit), 200)}
    if product_id:
        params["product_id"] = product_id
    return _get_auth("/v2/orders", params=params)


def get_account_info():
    """Get Delta Exchange account overview."""
    return _get_auth("/v2/profile")
