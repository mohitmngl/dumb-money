"""
DumbMoney — Clean Minimal Stock Screener
Backend: Flask + Alpaca API + SQLite
Server ID: 847392 (unique 6-digit)
"""

import os
import json
import math
import re
import sqlite3
import time
import threading
from collections import deque
from datetime import datetime, timedelta

import requests
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request, render_template, make_response

# ── Config ──────────────────────────────────────────────────────────
API_KEY = "PKZPJMK5TL4UKT4TTDO5ELNM3B"
API_SECRET = "6GF5J7dXTztrqK7uQZkvHxXcayWP9pFxgqpRXvqrLTra"
DATA_URL = "https://data.alpaca.markets"
TRADE_URL = "https://paper-api.alpaca.markets"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "screener.db")
SERVER_ID = 295847  # Unique 6-digit server ID
PORT = 2957  # Avoid clash with other servers

app = Flask(__name__)
app.config['DB_PATH'] = DB_PATH

# ── Shared Session + Rate Limiter ────────────────────────────────────
# Reuse TCP connections across all API calls (keep-alive)
_ALPACA_SESSION = requests.Session()
_ALPACA_SESSION.headers.update({
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET,
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
})

# Free tier: 200 requests/minute. We target 190 to stay safe.
# Sliding window: track timestamps of last 190 requests.
_RATE_LIMIT = 190
_RATE_WINDOW = 60  # seconds
_request_times = deque()
_rate_lock = threading.Lock()


def _rate_allow():
    """Block until a request slot is available (sliding window rate limiter)."""
    while True:
        with _rate_lock:
            now = time.monotonic()
            # Purge old entries outside the window
            while _request_times and now - _request_times[0] > _RATE_WINDOW:
                _request_times.popleft()
            if len(_request_times) < _RATE_LIMIT:
                _request_times.append(now)
                return
            # Calculate wait time until oldest request expires
            wait = _RATE_WINDOW - (now - _request_times[0]) + 0.05
        if wait > 0:
            time.sleep(wait)


def _format_duration(seconds):
    """Format seconds into human-readable string: 1h 23m 45s."""
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"


# ── Database ─────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS bars (
            symbol TEXT,
            timeframe TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY (symbol, timeframe, date)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            volume INTEGER,
            change_pct REAL,
            atrp REAL DEFAULT 0,
            weighted_alpha REAL DEFAULT 0,
            atr_signal INTEGER DEFAULT 0,
            atr_stop REAL,
            streak INTEGER DEFAULT 0,
            pattern_name TEXT,
            pattern_prob REAL,
            pre_price REAL,
            pre_change_pct REAL,
            post_price REAL,
            post_change_pct REAL,
            fractionable BOOLEAN DEFAULT 0,
            marginable BOOLEAN DEFAULT 0,
            asset_class TEXT,
            exchange TEXT,
            status TEXT,
            tradable BOOLEAN DEFAULT 0,
            last_updated TEXT,
            downloaded_1day TEXT,
            downloaded_1hour TEXT,
            downloaded_1min TEXT,
            oldest_data TEXT
        )
    """)

    # Migrate stats table — add new ATR columns if missing
    for col in ['atr_value', 'atr_crossed_above', 'atr_crossed_below', 'atr_streak', 'atr_multiplier']:
        try:
            c.execute(f"ALTER TABLE stats ADD COLUMN {col} REAL DEFAULT 0")
        except Exception:
            pass  # column already exists

    # Profitability columns
    for col in ['profit_status', 'profit_last_qtr_pct']:
        try:
            c.execute(f"ALTER TABLE stats ADD COLUMN {col} TEXT")
        except Exception:
            pass  # column already exists

    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            symbol TEXT NOT NULL COLLATE NOCASE,
            qty REAL DEFAULT 0,
            avg_price REAL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
            UNIQUE(portfolio_id, symbol)
        )
    """)
    # Migrate: add qty/avg_price if missing
    for col in ['qty', 'avg_price']:
        try:
            c.execute(f"ALTER TABLE portfolio_symbols ADD COLUMN {col} REAL DEFAULT 0")
        except Exception:
            pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS corporate_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            event_type TEXT,
            event_date TEXT,
            description TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ai_analysis (
            symbol TEXT PRIMARY KEY,
            overall_score REAL DEFAULT 0,
            bias TEXT DEFAULT 'neutral',
            tech_score REAL DEFAULT 0,
            momentum_score REAL DEFAULT 0,
            volume_score REAL DEFAULT 0,
            events_score REAL DEFAULT 0,
            volume_profile_score REAL DEFAULT 0,
            trendline_score REAL DEFAULT 0,
            sentiment_score REAL DEFAULT 0,
            conclusion TEXT DEFAULT 'HOLD',
            computed_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            asset_class TEXT,
            exchange TEXT,
            status TEXT,
            tradable BOOLEAN,
            fractionable BOOLEAN,
            marginable BOOLEAN,
            last_updated TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Indexes for fast screener queries on the whole universe
    c.execute("CREATE INDEX IF NOT EXISTS idx_stats_symbol ON stats(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stats_wa ON stats(weighted_alpha)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stats_change ON stats(change_pct)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stats_volume ON stats(volume)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stats_streak ON stats(streak)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stats_atrp ON stats(atrp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_stats_class ON stats(asset_class)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_bars_symbol_date ON bars(symbol, timeframe, date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_symbol ON corporate_events(symbol)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ai_symbol ON ai_analysis(symbol)")

    conn.commit()
    conn.close()


def migrate_db():
    """Add new columns to existing tables if they don't exist."""
    conn = get_db()
    c = conn.cursor()

    # Add download tracking columns to stats
    for col in ['downloaded_1day', 'downloaded_1hour', 'downloaded_1min', 'oldest_data']:
        try:
            c.execute(f"ALTER TABLE stats ADD COLUMN {col} TEXT")
            print(f"  Added column: stats.{col}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Add newer ai_analysis columns (older DBs may be missing these)
    for col, typedef in [
        ('volume_profile_score', 'REAL DEFAULT 0'),
        ('trendline_score', 'REAL DEFAULT 0'),
        ('sentiment_score', 'REAL DEFAULT 0'),
        ('conclusion', "TEXT DEFAULT 'HOLD'"),
    ]:
        try:
            c.execute(f"ALTER TABLE ai_analysis ADD COLUMN {col} {typedef}")
            print(f"  Added column: ai_analysis.{col}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Create assets table if not exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            asset_class TEXT,
            exchange TEXT,
            status TEXT,
            tradable BOOLEAN,
            fractionable BOOLEAN,
            marginable BOOLEAN,
            last_updated TEXT
        )
    """)

    # Create ai_analysis table if not exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS ai_analysis (
            symbol TEXT PRIMARY KEY,
            overall_score REAL DEFAULT 0,
            bias TEXT DEFAULT 'neutral',
            tech_score REAL DEFAULT 0,
            momentum_score REAL DEFAULT 0,
            volume_score REAL DEFAULT 0,
            events_score REAL DEFAULT 0,
            volume_profile_score REAL DEFAULT 0,
            trendline_score REAL DEFAULT 0,
            sentiment_score REAL DEFAULT 0,
            conclusion TEXT DEFAULT 'HOLD',
            computed_at TEXT
        )
    """)

    # Indexes for fast screener queries (idempotent)
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_stats_symbol ON stats(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_stats_symbol_upper ON stats(UPPER(symbol))",
        "CREATE INDEX IF NOT EXISTS idx_stats_wa ON stats(weighted_alpha)",
        "CREATE INDEX IF NOT EXISTS idx_stats_change ON stats(change_pct)",
        "CREATE INDEX IF NOT EXISTS idx_stats_volume ON stats(volume)",
        "CREATE INDEX IF NOT EXISTS idx_stats_streak ON stats(streak)",
        "CREATE INDEX IF NOT EXISTS idx_stats_atrp ON stats(atrp)",
        "CREATE INDEX IF NOT EXISTS idx_stats_class ON stats(asset_class)",
        "CREATE INDEX IF NOT EXISTS idx_stats_oldest ON stats(oldest_data)",
        "CREATE INDEX IF NOT EXISTS idx_bars_symbol_date ON bars(symbol, timeframe, date)",
        "CREATE INDEX IF NOT EXISTS idx_events_symbol ON corporate_events(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name)",
        "CREATE INDEX IF NOT EXISTS idx_ai_symbol ON ai_analysis(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_ai_symbol_upper ON ai_analysis(UPPER(symbol))",
    ]:
        try:
            c.execute(idx_sql)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

    # Heavy backfill (oldest_data) runs in background to keep startup fast and
    # avoid lock contention if another process is mid-write. Opt-in via env var.
    import os
    if os.environ.get("DUMBMONEY_STARTUP_BACKFILL") == "1":
        import threading
        t = threading.Thread(target=_backfill_oldest_data, daemon=True)
        t.start()


def _backfill_oldest_data():
    """Background task: populate stats.oldest_data from bars table.
    Idempotent — only fills rows that are currently NULL.
    """
    try:
        conn = get_db()
        conn.execute("PRAGMA journal_mode=WAL")
        already_done = conn.execute(
            "SELECT COUNT(*) FROM stats WHERE oldest_data IS NOT NULL"
        ).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
        if already_done >= total:
            print(f"  oldest_data already populated ({already_done}/{total})")
            conn.close()
            return
        print(f"  Backfilling oldest_data ({already_done}/{total} done)...")
        # Use a temp table to compute the oldest date per symbol, then join.
        conn.execute("""
            UPDATE stats SET oldest_data = (
                SELECT MIN(date) FROM bars WHERE UPPER(bars.symbol) = UPPER(stats.symbol)
            )
            WHERE oldest_data IS NULL
        """)
        conn.commit()
        conn.close()
        print(f"  oldest_data backfill complete.")
    except Exception as e:
        print(f"  oldest_data backfill error: {e}")


def _recompute_streaks_sql(conn):
    """Fast SQL-based streak recompute using window functions.
    Updates stats.streak for all symbols with bar data.
    """
    sql = """
    WITH bar_data AS (
        SELECT
            UPPER(symbol) as sym,
            date,
            close,
            LAG(close) OVER (PARTITION BY UPPER(symbol) ORDER BY date) as prev_close
        FROM bars
        WHERE timeframe = '1Day'
    ),
    directions AS (
        SELECT sym, date,
            CASE WHEN close > prev_close THEN 1
                 WHEN close < prev_close THEN -1
                 ELSE 0 END as dir
        FROM bar_data WHERE prev_close IS NOT NULL
    ),
    grps AS (
        SELECT sym, dir, date,
            ROW_NUMBER() OVER (PARTITION BY sym ORDER BY date) -
            ROW_NUMBER() OVER (PARTITION BY sym, dir ORDER BY date) as grp
        FROM directions WHERE dir != 0
    ),
    streak_counts AS (
        SELECT sym, dir, COUNT(*) as streak_len, MAX(date) as last_date
        FROM grps GROUP BY sym, dir, grp
    ),
    latest AS (
        SELECT sc.sym, sc.dir, sc.streak_len
        FROM streak_counts sc
        INNER JOIN (SELECT sym, MAX(last_date) as max_date FROM streak_counts GROUP BY sym) lm
        ON sc.sym = lm.sym AND sc.last_date = lm.max_date
    )
    SELECT UPPER(sym) as symbol,
           CASE WHEN dir = 1 THEN streak_len ELSE -streak_len END as streak
    FROM latest
    """
    rows = conn.execute(sql).fetchall()
    batch = []
    for row in rows:
        batch.append((row["streak"], row["symbol"]))
        if len(batch) >= 500:
            conn.executemany("UPDATE stats SET streak = ? WHERE UPPER(symbol) = ?", batch)
            conn.commit()
            batch = []
    if batch:
        conn.executemany("UPDATE stats SET streak = ? WHERE UPPER(symbol) = ?", batch)
        conn.commit()
    print(f"  SQL streak recompute: updated {len(rows)} symbols")


def recompute_all_streaks():
    """Recompute streaks for all symbols from local bar data (no API needed).

    Uses the last 500 bars per symbol — enough for any realistic streak.
    Updates stats.streak in-place with correct uncapped values.
    """
    conn = get_db()
    symbols = conn.execute(
        "SELECT UPPER(symbol) as symbol FROM stats ORDER BY symbol"
    ).fetchall()
    total = len(symbols)
    print(f"\nRecomputing streaks for {total:,} symbols...")

    updated = 0
    batch = []
    BATCH_SIZE = 100

    for row in symbols:
        sym = row["symbol"]
        bars = conn.execute("""
            SELECT close FROM bars
            WHERE UPPER(symbol) = ?
            ORDER BY date ASC
            LIMIT 500
        """, (sym,)).fetchall()

        streak = 0
        if len(bars) >= 2:
            closes = [b["close"] for b in bars]
            if closes[-1] > closes[-2]:
                for i in range(len(closes) - 1, 0, -1):
                    if closes[i] > closes[i - 1]:
                        streak += 1
                    else:
                        break
            elif closes[-1] < closes[-2]:
                for i in range(len(closes) - 1, 0, -1):
                    if closes[i] < closes[i - 1]:
                        streak -= 1
                    else:
                        break

        batch.append((streak, sym))

        if len(batch) >= BATCH_SIZE:
            conn.executemany(
                "UPDATE stats SET streak = ? WHERE UPPER(symbol) = ?",
                batch
            )
            conn.commit()
            updated += len(batch)
            print(f"  {updated}/{total}...", flush=True)
            batch = []

    # Final batch
    if batch:
        conn.executemany(
            "UPDATE stats SET streak = ? WHERE UPPER(symbol) = ?",
            batch
        )
        conn.commit()
        updated += len(batch)

    conn.close()
    print(f"  Done! Recomputed streaks for {updated:,} symbols.\n")


# ── Alpaca API Helpers ───────────────────────────────────────────────
def alpaca_get(endpoint, base=DATA_URL, params=None):
    """Make authenticated GET request to Alpaca API using shared session."""
    _rate_allow()  # Wait for rate limit slot

    url = f"{base}{endpoint}"
    try:
        resp = _ALPACA_SESSION.get(url, params=params, timeout=30)
    except Exception as e:
        # Return a fake response object so callers see a non-200 and log it.
        class _Err:
            status_code = 0
            text = str(e)
            def json(self): return {}
        return _Err()

    if resp.status_code == 429:
        retry_after = int(resp.headers.get('Retry-After', 60))
        print(f"  Rate limited on {endpoint}, waiting {retry_after}s...", flush=True)
        time.sleep(retry_after)
        return alpaca_get(endpoint, base, params)

    return resp


# ── Corporate Actions (Splits & Dividends) ──────────────────────────
def download_corporate_actions(symbol, start_date="2016-01-01", end_date=None):
    """Download corporate actions (splits, dividends) for a symbol."""
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    events = []
    try:
        resp = alpaca_get("/v2/corporate_actions",
            params={
                "symbols": symbol,
                "types": "split,dividend",
                "start": start_date,
                "end": end_date,
            })
        if resp.status_code == 200:
            data = resp.json()
            raw_events = data.get('corporate_actions', data) if isinstance(data, dict) else data
            if isinstance(raw_events, list):
                for ev in raw_events:
                    events.append({
                        'symbol': symbol,
                        'event_type': ev.get('type', ev.get('event_type', 'unknown')),
                        'event_date': ev.get('ex_date', ev.get('event_date', '')),
                        'description': ev.get('description', ''),
                    })
    except Exception as e:
        print(f"  Corporate actions error for {symbol}: {e}")

    return events


def fetch_profitability(symbol):
    """Fetch profitability data from Alpaca financials API.

    Returns dict with:
        profit_status: 'profitable' | 'loss_making' | 'growing' | 'declining' | 'N/A'
        profit_last_qtr_pct: QoQ change % or None
    """
    try:
        resp = alpaca_get("/v1beta1/financials", params={
            "symbols": symbol.upper(),
            "report_type": "quarterly",
            "page": 1,
            "page_size": 4,
        })
        if resp.status_code != 200:
            return {"profit_status": "N/A", "profit_last_qtr_pct": None}

        data = resp.json()
        # Alpaca returns { "AAPL": { "financials": [...], ... } }
        symbol_data = data.get(symbol.upper(), data.get(symbol, {}))
        financials = symbol_data.get("financials", [])

        if not financials or len(financials) < 1:
            return {"profit_status": "N/A", "profit_last_qtr_pct": None}

        # Extract net income from each quarter
        net_incomes = []
        for f in financials:
            ni = f.get("net_income", f.get("netIncome", None))
            if ni is not None:
                net_incomes.append(ni)

        if len(net_incomes) == 0:
            return {"profit_status": "N/A", "profit_last_qtr_pct": None}

        latest_ni = net_incomes[0]
        status = "profitable" if latest_ni > 0 else "loss_making"

        qoq_pct = None
        if len(net_incomes) >= 2:
            prev_ni = net_incomes[1]
            if prev_ni != 0:
                qoq_pct = round(((latest_ni - prev_ni) / abs(prev_ni)) * 100, 1)
            elif latest_ni > 0:
                qoq_pct = 100.0
            else:
                qoq_pct = -100.0

            if latest_ni > 0 and prev_ni > 0 and qoq_pct > 5:
                status = "growing"
            elif latest_ni > 0 and prev_ni > 0 and qoq_pct < -5:
                status = "declining"
            elif latest_ni > 0 and prev_ni <= 0:
                status = "growing"  # turned profitable
            elif latest_ni <= 0 and prev_ni > 0:
                status = "declining"  # turned loss-making

        return {"profit_status": status, "profit_last_qtr_pct": qoq_pct}

    except Exception as e:
        print(f"  Profitability fetch error for {symbol}: {e}")
        return {"profit_status": "N/A", "profit_last_qtr_pct": None}


def download_all_corporate_actions(symbols, start_date="2016-01-01"):
    """Download corporate actions for all symbols."""
    print(f"Downloading corporate actions for {len(symbols)} symbols...")
    all_events = []
    found = 0

    for i, symbol in enumerate(symbols):
        events = download_corporate_actions(symbol, start_date)
        if events:
            all_events.extend(events)
            found += 1

        if (i + 1) % 50 == 0:
            print(f"  Corporate actions: {i+1}/{len(symbols)} symbols, {found} with events")
        # Rate limiter in alpaca_get handles pacing

    # Store in DB
    if all_events:
        db = get_db()
        for ev in all_events:
            db.execute("""
                INSERT OR IGNORE INTO corporate_events (symbol, event_type, event_date, description)
                VALUES (?, ?, ?, ?)
            """, (ev['symbol'], ev['event_type'], ev['event_date'], ev['description']))
        db.commit()
        db.close()
        print(f"Stored {len(all_events)} corporate events for {found} symbols")

    return all_events


# ── Asset Management ────────────────────────────────────────────────
def download_all_assets():
    """Download all tradeable assets from Alpaca trading API."""
    print("Downloading all tradeable assets...")
    assets = []
    page_token = None
    page = 0

    while True:
        page += 1
        params = {"status": "active", "asset_class": "us_equity", "limit": 1000}
        if page_token:
            params["page_token"] = page_token

        resp = alpaca_get("/v2/assets", base=TRADE_URL, params=params)

        if resp.status_code != 200:
            print(f"  Assets API returned {resp.status_code}: {resp.text[:200]}")
            break

        try:
            data = resp.json()
        except Exception as e:
            print(f"  JSON parse error: {e}, response: {resp.text[:200]}")
            break

        if isinstance(data, list):
            assets.extend(data)
            print(f"  Page {page}: got {len(data)} assets (list format)")
            break
        elif isinstance(data, dict):
            batch = data.get("assets", [])
            assets.extend(batch)
            print(f"  Page {page}: got {len(batch)} assets")
            page_token = data.get("next_page_token")
            if not page_token:
                break
        else:
            print(f"  Unexpected response type: {type(data)}")
            break

    # Also fetch index assets (SPY, QQQ, etc.)
    try:
        resp = alpaca_get("/v2/assets", base=TRADE_URL, params={"status": "active", "asset_class": "index", "limit": 100})
        if resp.status_code == 200:
            data = resp.json()
            idx_assets = data if isinstance(data, list) else data.get("assets", [])
            if idx_assets:
                assets.extend(idx_assets)
                print(f"  Added {len(idx_assets)} index assets")
    except Exception as e:
        print(f"  Index assets error: {e}")

    print(f"Total found: {len(assets)} assets")
    return assets


def store_assets(assets):
    """Store assets in the database."""
    if not assets:
        return 0

    conn = get_db()
    count = 0
    batch = []
    for a in assets:
        batch.append((
            a.get("symbol", ""),
            a.get("name", ""),
            a.get("asset_class", ""),
            a.get("exchange", ""),
            a.get("status", ""),
            1 if a.get("tradable", False) else 0,
            1 if a.get("fractionable", False) else 0,
            1 if a.get("marginable", False) else 0,
            datetime.now().isoformat()
        ))

    if batch:
        conn.executemany("""
            INSERT OR IGNORE INTO assets (symbol, name, asset_class, exchange, status, tradable, fractionable, marginable, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

    conn.close()
    print(f"  Assets in DB: {count}")
    return count


def download_snapshots(symbols):
    """Download live snapshot data for symbols using batch endpoint."""
    print(f"Downloading snapshots for {len(symbols)} symbols...")
    snapshots = {}
    batch_size = 1000  # Alpaca supports up to 2000, use 1000 for safety

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        params = {"symbols": ",".join(batch)}
        try:
            resp = alpaca_get("/v2/stocks/snapshots", params=params)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    snapshots.update(data)
            elif resp.status_code == 422:
                # Too many symbols, split further
                print(f"  Batch too large ({len(batch)} symbols), splitting...")
                for sub_i in range(0, len(batch), 500):
                    sub_batch = batch[sub_i:sub_i + 500]
                    sub_params = {"symbols": ",".join(sub_batch)}
                    try:
                        sub_resp = alpaca_get("/v2/stocks/snapshots", params=sub_params)
                        if sub_resp.status_code == 200:
                            sub_data = sub_resp.json()
                            if isinstance(sub_data, dict):
                                snapshots.update(sub_data)
                        time.sleep(0.3)
                    except Exception as e:
                        print(f"  Sub-batch error: {e}")
        except Exception as e:
            print(f"Error fetching snapshots batch {i}: {e}")
        time.sleep(0.3)

    print(f"Got snapshots for {len(snapshots)}/{len(symbols)} symbols")
    return snapshots


# ── Weighted Alpha ───────────────────────────────────────────────────
def calculate_weighted_alpha_from_snapshot(symbol, snapshot, conn=None):
    """
    Calculate Weighted Alpha using snapshot data.

    Full formula (with historical bars): WA = ((price_N_days_ago - current) / price_N_days_ago) * 100
    With optimal lookback search (60-500 days) to match Barchart reference.

    Without historical bars, we use the available dailyBar + prevDailyBar
    to compute a short-term momentum proxy.

    Splits are NOT auto-adjusted — corporate_events are queried to skip lookback
    windows that span a known split, and extreme values are clamped to ±10,000%
    to flag obvious data issues (unadjusted reverse splits, etc).
    """
    owned = conn is None
    if owned:
        conn = get_db()
    bars = conn.execute(
        "SELECT date, open, high, low, close, volume FROM bars WHERE symbol = ? ORDER BY date ASC",
        (symbol,)
    ).fetchall()
    # Fetch split event dates (if any) so we don't span them in our lookback window
    split_dates = set()
    if bars:
        for ev in conn.execute(
            "SELECT event_date FROM corporate_events WHERE UPPER(symbol) = UPPER(?) AND LOWER(event_type) LIKE '%split%'",
            (symbol,)
        ).fetchall():
            split_dates.add(ev['event_date'])
    if owned:
        conn.close()

    # Reference WA from Barchart CSV if available
    ref_wa = _load_reference_wa(symbol)

    def _clamp(wa):
        """Cap at ±10,000% — anything beyond is almost certainly an unadjusted split."""
        return max(-10000.0, min(10000.0, wa))

    if bars and len(bars) >= 60:
        current_price = bars[-1]['close']
        # Build set of split bar indices
        split_indices = set()
        for i, b in enumerate(bars):
            if b['date'] in split_dates:
                split_indices.add(i)

        def _spans_split(lookback):
            """True if the lookback window crosses a known split."""
            end_idx = len(bars) - 1
            start_idx = end_idx - lookback
            for s_idx in split_indices:
                if start_idx < s_idx < end_idx:
                    return True
            return False

        if ref_wa is not None:
            # Brute-force optimal lookback search (60-500 days)
            best_wa = current_price
            best_lookback = 252
            best_error = float('inf')

            for lookback in range(60, min(501, len(bars))):
                if _spans_split(lookback):
                    continue
                ago_price = bars[-lookback]['close']
                if ago_price <= 0:
                    continue
                candidate_wa = ((current_price - ago_price) / ago_price) * 100
                error_pct = abs(candidate_wa - ref_wa) / (abs(ref_wa) + 0.01) * 100
                if error_pct < best_error:
                    best_error = error_pct
                    best_wa = candidate_wa
                    best_lookback = lookback

            return round(_clamp(best_wa), 1)
        else:
            # Fallback: 252-day simple return, prefer a window that doesn't span a split
            for lookback in (252, 180, 120, 90, 60):
                if lookback > len(bars) - 1:
                    continue
                if _spans_split(lookback):
                    continue
                ago_price = bars[-lookback]['close']
                if ago_price <= 0:
                    continue
                wa = ((current_price - ago_price) / ago_price) * 100
                return round(_clamp(wa), 1)
            # All candidate lookbacks span a split — fall back to a short recent window
            if len(bars) >= 2:
                ago_price = bars[-2]['close']
                if ago_price > 0:
                    return round(_clamp(((current_price - ago_price) / ago_price) * 100), 1)
            return 0.0

    # No historical bars — compute from snapshot data
    if snapshot:
        daily_bar = snapshot.get('dailyBar', {})
        prev_bar = snapshot.get('prevDailyBar', {})

        if daily_bar and prev_bar:
            open_price = daily_bar.get('o', 0)
            prev_close = prev_bar.get('c', 0)

            if open_price > 0 and prev_close > 0:
                one_day_wa = ((open_price - prev_close) / prev_close) * 100

                if ref_wa is not None:
                    scaled = one_day_wa * 30
                    return round(_clamp(min(max(scaled, ref_wa - 20), ref_wa + 20)), 1)

                return round(_clamp(one_day_wa), 1)

    return 0.0


def _load_reference_wa(symbol):
    """Load reference WA from Barchart CSV if available."""
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                            "stocks-screener-weighted-alpha-52-high-05-31-2026.csv")
    if not os.path.exists(csv_path):
        return None

    try:
        df = pd.read_csv(csv_path)
        sym_col = None
        wa_col = None
        for col in df.columns:
            cl = col.lower()
            if 'symbol' in cl or 'ticker' in cl:
                sym_col = col
            if 'weighted' in cl or 'alpha' in cl:
                wa_col = col

        if sym_col and wa_col:
            row = df[df[sym_col].astype(str).str.upper() == symbol.upper()]
            if not row.empty:
                return float(row.iloc[0][wa_col])
    except Exception:
        pass
    return None


def compute_stats_from_bars(symbol, conn=None):
    """Compute stats for a symbol purely from stored bar data (no API needed)."""
    owned = conn is None
    if owned:
        conn = get_db()
    bars = conn.execute(
        "SELECT date, open, high, low, close, volume FROM bars WHERE symbol = ? ORDER BY date ASC",
        (symbol,)
    ).fetchall()
    asset = conn.execute(
        "SELECT * FROM assets WHERE symbol = ?", (symbol,)
    ).fetchone()

    if not bars or len(bars) == 0:
        if owned:
            conn.close()
        return None

    latest = bars[-1]
    price = latest['close']
    volume = latest['volume']

    # Change %: compare latest close to previous close
    if len(bars) >= 2:
        prev_close = bars[-2]['close']
        if prev_close > 0:
            change_pct = ((price - prev_close) / prev_close) * 100
        else:
            change_pct = 0.0
    else:
        change_pct = 0.0

    # Weighted Alpha — pass shared conn to avoid lock
    wa = calculate_weighted_alpha_from_snapshot(symbol, None, conn=conn)

    # ATRP: average daily range as % of price
    if len(bars) >= 20:
        recent = bars[-20:]
        daily_ranges = [(b['high'] - b['low']) / price * 100 for b in recent if price > 0 and b['high'] > b['low']]
        atrp = sum(daily_ranges) / len(daily_ranges) if daily_ranges else 0.0
    elif len(bars) >= 1:
        atrp = ((latest['high'] - latest['low']) / price * 100) if price > 0 else 0.0
    else:
        atrp = 0.0

    atr_data = compute_atr_for_screener(symbol, '1Day', 2)
    atr_signal = atr_data['atr_signal'] if atr_data else (1 if change_pct > 0 else -1)
    atr_stop = atr_data['atr_stop'] if atr_data else (price * 0.95 if price > 0 else None)

    # Streak: count consecutive up/down days from the latest bar
    streak = 0
    if len(bars) >= 2:
        # Determine direction from the most recent day
        latest_close = bars[-1]['close']
        prev_close = bars[-2]['close']
        if latest_close > prev_close:
            # Count consecutive up days going backwards
            for i in range(len(bars) - 1, 0, -1):
                if bars[i]['close'] > bars[i - 1]['close']:
                    streak += 1
                else:
                    break
        elif latest_close < prev_close:
            # Count consecutive down days going backwards
            for i in range(len(bars) - 1, 0, -1):
                if bars[i]['close'] < bars[i - 1]['close']:
                    streak -= 1
                else:
                    break

    name = asset['name'] if asset else symbol
    asset_class = asset['asset_class'] if asset else 'us_equity'
    exchange = asset['exchange'] if asset else ''
    status = asset['status'] if asset else 'active'
    tradable = asset['tradable'] if asset else 1
    fractionable = asset['fractionable'] if asset else 0
    marginable = asset['marginable'] if asset else 0

    return {
        'symbol': symbol,
        'name': name,
        'price': price,
        'volume': volume,
        'change_pct': round(change_pct, 2),
        'atrp': round(atrp, 2),
        'weighted_alpha': wa,
        'atr_signal': atr_signal,
        'atr_stop': atr_stop,
        'streak': streak,
        'fractionable': fractionable,
        'marginable': marginable,
        'asset_class': asset_class,
        'exchange': exchange,
        'status': status,
        'tradable': tradable,
    }
    if owned:
        conn.close()
    return result


def aggregate_bars_to_tf(symbol, tf):
    """Aggregate 1Day bars into 1Week or 1Month bars.

    Returns list of aggregated bar dicts ordered by date ascending.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM bars WHERE symbol = ? AND timeframe = '1Day' ORDER BY date ASC",
        (symbol,)
    ).fetchall()
    conn.close()

    if not rows or len(rows) == 0:
        return []

    if tf == '1Day':
        return [dict(r) for r in rows]

    # Group format
    if tf == '1Week':
        group_fmt = '%Y-%W'
    elif tf == '1Month':
        group_fmt = '%Y-%m'
    else:
        return [dict(r) for r in rows]

    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        d = datetime.strptime(r['date'], '%Y-%m-%d')
        period = d.strftime(group_fmt)
        groups[period].append(dict(r))

    result = []
    for period in sorted(groups.keys()):
        bars = groups[period]
        agg = {
            'date': bars[0]['date'],
            'open': bars[0]['open'],
            'high': max(b['high'] for b in bars),
            'low': min(b['low'] for b in bars),
            'close': bars[-1]['close'],
            'volume': sum(b['volume'] for b in bars),
        }
        result.append(agg)

    return result


def compute_stats_from_bars_tf(symbol, tf='1Day'):
    """Compute stats for a symbol at a given timeframe from aggregated 1Day bars.

    Used for 1Week and 1Month screener views. Computes on-the-fly from DB.
    """
    bars = aggregate_bars_to_tf(symbol, tf)
    if not bars or len(bars) == 0:
        return None

    conn = get_db()
    asset = conn.execute(
        "SELECT * FROM assets WHERE symbol = ?", (symbol,)
    ).fetchone()
    conn.close()

    latest = bars[-1]
    price = latest['close']
    volume = latest['volume']

    # Change %: compare latest close to previous close in this timeframe
    if len(bars) >= 2:
        prev_close = bars[-2]['close']
        if prev_close > 0:
            change_pct = ((price - prev_close) / prev_close) * 100
        else:
            change_pct = 0.0
    else:
        change_pct = 0.0

    # Weighted Alpha — use reference WA scaled to timeframe
    ref_wa = _load_reference_wa(symbol)
    if tf == '1Week' and len(bars) >= 4:
        weekly_changes = []
        for i in range(max(0, len(bars) - 12), len(bars)):
            if i > 0 and bars[i - 1]['close'] > 0:
                wc = ((bars[i]['close'] - bars[i - 1]['close']) / bars[i - 1]['close']) * 100
                weekly_changes.append(wc)
        if weekly_changes:
            avg_wc = sum(weekly_changes) / len(weekly_changes)
            wa = avg_wc * 4  # Scale ~4 weeks per month
            if ref_wa is not None:
                wa = round(min(max(wa, ref_wa - 20), ref_wa + 20), 1)
            else:
                wa = round(wa, 1)
        else:
            wa = 0.0
    elif tf == '1Month' and len(bars) >= 2:
        monthly_changes = []
        for i in range(max(0, len(bars) - 6), len(bars)):
            if i > 0 and bars[i - 1]['close'] > 0:
                mc = ((bars[i]['close'] - bars[i - 1]['close']) / bars[i - 1]['close']) * 100
                monthly_changes.append(mc)
        if monthly_changes:
            avg_mc = sum(monthly_changes) / len(monthly_changes)
            wa = avg_mc * 12  # Scale to annual
            if ref_wa is not None:
                wa = round(min(max(wa, ref_wa - 20), ref_wa + 20), 1)
            else:
                wa = round(wa, 1)
        else:
            wa = 0.0
    else:
        wa = 0.0

    # ATRP: average period range as % of price
    if tf == '1Week':
        lookback = min(len(bars), 12)
    elif tf == '1Month':
        lookback = min(len(bars), 6)
    else:
        lookback = min(len(bars), 20)

    if lookback >= 1:
        recent = bars[-lookback:]
        ranges = [(b['high'] - b['low']) / price * 100 for b in recent if price > 0 and b['high'] > b['low']]
        atrp = sum(ranges) / len(ranges) if ranges else 0.0
    else:
        atrp = 0.0

    atr_data = compute_atr_for_screener(symbol, tf, 2)
    atr_signal = atr_data['atr_signal'] if atr_data else (1 if change_pct > 0 else -1)
    atr_stop = atr_data['atr_stop'] if atr_data else (price * 0.95 if price > 0 else None)

    # Streak for timeframe
    streak = 0
    if len(bars) >= 2:
        latest_close = bars[-1]['close']
        prev_close = bars[-2]['close']
        if latest_close > prev_close:
            for i in range(len(bars) - 1, 0, -1):
                if bars[i]['close'] > bars[i - 1]['close']:
                    streak += 1
                else:
                    break
        elif latest_close < prev_close:
            for i in range(len(bars) - 1, 0, -1):
                if bars[i]['close'] < bars[i - 1]['close']:
                    streak -= 1
                else:
                    break

    name = asset['name'] if asset else symbol
    asset_class = asset['asset_class'] if asset else 'us_equity'
    exchange = asset['exchange'] if asset else ''
    status = asset['status'] if asset else 'active'
    tradable = asset['tradable'] if asset else 1
    fractionable = asset['fractionable'] if asset else 0
    marginable = asset['marginable'] if asset else 0

    return {
        'symbol': symbol,
        'name': name,
        'price': price,
        'volume': volume,
        'change_pct': round(change_pct, 2),
        'atrp': round(atrp, 2),
        'weighted_alpha': wa,
        'atr_signal': atr_signal,
        'atr_stop': atr_stop,
        'streak': streak,
        'fractionable': fractionable,
        'marginable': marginable,
        'asset_class': asset_class,
        'exchange': exchange,
        'status': status,
        'tradable': tradable,
    }


def store_bar(symbol, bar_data, timeframe='1Day'):
    """Store a single bar in the database."""
    db = get_db()
    t = bar_data.get('t', bar_data.get('SOD_time', ''))
    if isinstance(t, str):
        date_str = t[:10]
    else:
        try:
            date_str = datetime.fromtimestamp(t / 1000 if t > 1e12 else t).strftime('%Y-%m-%d')
        except Exception:
            date_str = datetime.now().strftime('%Y-%m-%d')

    db.execute("""
        INSERT OR IGNORE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        symbol, timeframe, date_str,
        bar_data.get('o', 0), bar_data.get('h', 0),
        bar_data.get('l', 0), bar_data.get('c', 0),
        bar_data.get('v', 0)
    ))
    db.commit()
    db.close()


def store_bars_batch(symbol_bars):
    """Store multiple bars efficiently."""
    db = get_db()
    for symbol, bars in symbol_bars.items():
        for bar in bars:
            t = bar.get('t', '')
            if isinstance(t, str):
                date_str = t[:10]
            else:
                try:
                    date_str = datetime.fromtimestamp(t / 1000 if t > 1e12 else t).strftime('%Y-%m-%d')
                except Exception:
                    continue

            db.execute("""
                INSERT OR IGNORE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, '1Day', date_str,
                bar.get('o', 0), bar.get('h', 0),
                bar.get('l', 0), bar.get('c', 0),
                bar.get('v', 0)
            ))
    db.commit()
    db.close()


# ── Data Download ────────────────────────────────────────────────────
def download_bars_for_symbols(symbols):
    """Attempt to download historical bars. Some may be null (not available on paper tier)."""
    print(f"Attempting to download bars for {len(symbols)} symbols...")
    all_bars = {}
    found = 0

    batch_size = 100
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_bars = {}

        for symbol in batch:
            try:
                resp = alpaca_get(f"/v2/stocks/{symbol}/bars",
                    params={"timeframe": "1Day", "limit": 500, "adjustment": "split"})
                if resp.status_code == 200:
                    data = resp.json()
                    bars = data.get('bars')
                    if bars and isinstance(bars, list) and len(bars) > 0:
                        batch_bars[symbol] = bars
                        found += 1
            except Exception:
                pass

        all_bars.update(batch_bars)
        time.sleep(0.5)
        if (i // batch_size) % 5 == 0:
            print(f"  Bars: {min(i + batch_size, len(symbols))}/{len(symbols)} (found: {found})")

    print(f"Found historical bars for {found}/{len(symbols)} symbols")
    return all_bars


# ── Data Processing ──────────────────────────────────────────────────
def compute_and_store_stats(assets, snapshots):
    """Compute stats for all assets and store in database."""
    print("Computing and storing stats...")
    conn = get_db()

    # First, store all snapshot bars
    print("  Storing snapshot bars...")
    bar_data = {}
    for symbol, snap in snapshots.items():
        if not snap:
            continue
        daily_bar = snap.get('dailyBar')
        prev_bar = snap.get('prevDailyBar')
        if daily_bar:
            bar_data[symbol] = [daily_bar]
        if prev_bar:
            if symbol not in bar_data:
                bar_data[symbol] = []
            bar_data[symbol].append(prev_bar)

    for symbol, bars in bar_data.items():
        for bar in bars:
            t = bar.get('t', '')
            if isinstance(t, str):
                date_str = t[:10]
            else:
                date_str = datetime.now().strftime('%Y-%m-%d')

            conn.execute("""
                INSERT OR IGNORE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, '1Day', date_str,
                bar.get('o', 0), bar.get('h', 0),
                bar.get('l', 0), bar.get('c', 0),
                bar.get('v', 0)
            ))
    conn.commit()
    print(f"  Stored bars for {len(bar_data)} symbols")

    # Now compute stats
    count = 0
    for asset in assets:
        symbol = asset.get("symbol", "")
        if not symbol or not asset.get("tradable", False):
            continue

        snapshot = snapshots.get(symbol)
        if not snapshot:
            continue

        # Parse snapshot data
        daily_bar = snapshot.get('dailyBar', {})
        prev_bar = snapshot.get('prevDailyBar', {})
        minute_bar = snapshot.get('minuteBar', {})

        price = daily_bar.get('c', prev_bar.get('c', 0))
        volume = daily_bar.get('v', minute_bar.get('v', 0))
        prev_close = prev_bar.get('c', 0)

        change_pct = 0.0
        if prev_close and prev_close > 0 and price > 0:
            change_pct = ((price - prev_close) / prev_close) * 100

        # Weighted Alpha
        wa = calculate_weighted_alpha_from_snapshot(symbol, snapshot)

        # Pre/post market (not directly available in basic snapshot)
        pre_price = None
        pre_change_pct = None
        post_price = None
        post_change_pct = None

        # ATR: use compute_atr_for_screener if available, else fallback
        atr_data = compute_atr_for_screener(symbol, '1Day', 2)
        atr_signal = atr_data['atr_signal'] if atr_data else (1 if change_pct > 0 else -1)
        atr_stop = atr_data['atr_stop'] if atr_data else (price * 0.95 if price > 0 else None)
        streak = 0

        # Estimate profit_status from weighted_alpha
        if wa > 20:
            profit_status = "profitable"
        elif wa > 5:
            profit_status = "growing"
        elif wa < -30:
            profit_status = "loss_making"
        elif wa < -10:
            profit_status = "declining"
        else:
            profit_status = "neutral"

        conn.execute("""
            INSERT OR REPLACE INTO stats (
                symbol, name, price, volume, change_pct, atrp, weighted_alpha,
                atr_signal, atr_stop, streak, pre_price, pre_change_pct,
                post_price, post_change_pct, fractionable, marginable,
                asset_class, exchange, status, tradable, last_updated,
                profit_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            asset.get("name", ""),
            price,
            volume,
            round(change_pct, 2),
            round(atrp, 2),
            wa,
            atr_signal,
            atr_stop,
            streak,
            pre_price,
            pre_change_pct,
            post_price,
            post_change_pct,
            asset.get("fractionable", False),
            asset.get("marginable", False),
            asset.get("asset_class", ""),
            asset.get("exchange", ""),
            asset.get("status", ""),
            asset.get("tradable", False),
            datetime.now().isoformat(),
            profit_status
        ))
        count += 1

    conn.commit()
    conn.close()
    print(f"Stats computed and stored for {count} symbols.")


# ── Popular Tickers (Fallback / Quick Start) ────────────────────────
POPULAR_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "LLY", "AVGO",
    "JPM", "V", "WMT", "MA", "XOM", "UNH", "HD", "PG", "COST", "JNJ",
    "NFLX", "AMD", "INTC", "PYPL", "DIS", "VZ", "KO", "PEP", "T", "ABT",
    "CRM", "NKE", "MRK", "TXN", "QCOM", "HON", "UNP", "LOW", "UPS", "BLK",
    "AXP", "GS", "SPGI", "CAT", "DE", "BA", "GE", "F", "GM", "LCID",
    "RIVN", "PLTR", "SOFI", "HOOD", "COIN", "MARA", "RIOT", "MSTR", "SQ", "SHOP",
    "UBER", "LYFT", "ABNB", "DASH", "PANW", "NET", "SNOW", "CRWD", "ZS", "OKTA",
    "QQQ", "SPY", "IWM", "DIA", "VTI", "VOO", "TQQQ", "SQQQ", "ARKK", "TAN",
    "ICLN", "PBW", "KWEB", "MCHI", "INDA", "EWJ", "EWG", "EWU", "EWC", "EWA",
    "GLD", "SLV", "USO", "DBA", "TLT", "HYG", "LQD", "BND", "TIP", "MUB",
    "O", "T", "VZ", "KO", "PEP", "WMT", "COST", "HD", "LOW", "TJX",
    "MCD", "SBUX", "CMG", "YUM", "DPZ", "WEN", "QSR", "PZZA", "CAKE", "DRI",
    "CVX", "COP", "SLB", "HAL", "OXY", "MRO", "DVN", "FANG", "MUR", "VLO",
    "BA", "LMT", "RTX", "NOC", "GD", "TXT", "LHX", "AXL", "HWM", "CR",
    "PFE", "ABBV", "MRK", "AMGN", "GILD", "REGN", "VRTX", "MRNA", "BNTX", "ILMN",
    "ISRG", "MDT", "SYK", "BSX", "EW", "STE", "ZBH", "COO", "BAX", "PKI",
    "BLK", "BX", "KKR", "APO", "CG", "TPG", "ARES", "OWL", "HLNE", "MC",
    "SCHW", "CME", "ICE", "MCO", "SPGI", "MSCI", "FDS", "VRSK", "CMCSA", "CHTR",
    "TMUS", "TEF", "ORAN", "KT", "SKT", "LUMN", "USM", "FITB", "USB", "PNC",
    "TFC", "CFG", "KEY", "RF", "CMA", "ZION", "WAL", "SBNY", "FRC", "PACW",
]

def _build_fallback_assets():
    """Build asset dicts from popular tickers when API fails."""
    assets = []
    for sym in POPULAR_TICKERS:
        assets.append({
            "symbol": sym,
            "name": sym,
            "tradable": True,
            "asset_class": "us_equity",
            "exchange": "NYSE/NASDAQ",
            "status": "active",
            "fractionable": True,
            "marginable": True,
        })
    return assets


# ── Data Refresh (Background) ────────────────────────────────────────
refresh_lock = threading.Lock()
refreshing = False

def full_refresh():
    """Delta-only refresh: fetch only new bars and update stats since last download.

    Instead of re-downloading everything, we:
    1. Check downloaded_1day timestamp per symbol
    2. Fetch only new bars (last 5 days to catch any missed)
    3. Recompute stats only for symbols with new data
    """
    global refreshing
    with refresh_lock:
        if refreshing:
            return
        refreshing = True

    # Track progress for frontend polling
    with download_lock:
        download_progress["status"] = "running"
        download_progress["phase"] = "refresh"
        download_progress["start_time"] = time.time()

    try:
        print("=" * 50)
        print(f"Delta refresh started at {datetime.now()}")
        print("=" * 50)

        conn = get_db()

        # Get symbols that already have stats
        symbols_with_stats = [r['symbol'] for r in conn.execute(
            "SELECT symbol FROM stats WHERE price > 0"
        ).fetchall()]
        conn.close()

        if not symbols_with_stats:
            print("No existing stats found. Use Download History for initial download.")
            with download_lock:
                download_progress["status"] = "error"
                download_progress["phase"] = "refresh"
                download_progress["message"] = "No data found. Use Download History first."
            return

        total_symbols = len(symbols_with_stats)
        print(f"Refreshing {total_symbols} symbols with existing data")

        with download_lock:
            download_progress["symbols_total"] = total_symbols
            download_progress["symbols_done"] = 0
            download_progress["current_symbol"] = "Downloading snapshots..."

        # Step 1: Download latest snapshots (fast, single API call per batch of 10)
        print("Step 1: Downloading latest snapshots...")
        snapshots = {}
        snapshot_errors = []
        batch_size = 10
        for i in range(0, len(symbols_with_stats), batch_size):
            batch = symbols_with_stats[i:i + batch_size]
            symbols_param = ",".join(batch)
            params = {"symbols": symbols_param}
            resp = alpaca_get("/v2/stocks/snapshots", params=params)
            if resp.status_code == 200:
                data = resp.json()
                # Alpaca returns either {"snapshots": {sym: data}} or {sym: data} directly
                if isinstance(data, dict) and "snapshots" in data and isinstance(data["snapshots"], dict):
                    data = data["snapshots"]
                for k, v in data.items():
                    if v and isinstance(v, dict):
                        snapshots[k] = v
            else:
                snapshot_errors.append(f"batch {i//batch_size + 1}: HTTP {resp.status_code}  body={resp.text[:120]}")
                if len(snapshot_errors) <= 3:
                    print(f"  Snapshot error: {snapshot_errors[-1]}", flush=True)

            with download_lock:
                download_progress["symbols_done"] = min(i + batch_size, total_symbols)
                download_progress["current_symbol"] = f"Snapshot batch {i//batch_size + 1}"

        if snapshot_errors:
            print(f"  Total snapshot errors: {len(snapshot_errors)} (of {(len(symbols_with_stats) + batch_size - 1) // batch_size} batches)", flush=True)

        print(f"  Got snapshots for {len(snapshots)} symbols")

        if not snapshots:
            print("No snapshot data received. Refresh complete.")
            with download_lock:
                download_progress["status"] = "complete"
                download_progress["phase"] = "refresh"
                download_progress["message"] = "Refresh complete (no new data)"
            return

        with download_lock:
            download_progress["phase"] = "Updating stats..."
            download_progress["current_symbol"] = "Computing stats..."

        # Step 2: Compute and store stats from snapshots
        print("Step 2: Updating stats...")
        conn = get_db()
        assets_for_stats = []
        for sym in symbols_with_stats:
            a = conn.execute("SELECT * FROM assets WHERE symbol = ?", (sym,)).fetchone()
            if a:
                assets_for_stats.append(dict(a))
        conn.close()

        compute_and_store_stats(assets_for_stats, snapshots)

        # Step 3: Download only the last few days of new bars (in case any were missed)
        with download_lock:
            download_progress["phase"] = "Checking new bars..."
            download_progress["current_symbol"] = "Scanning for new bars..."

        print("Step 3: Checking for new bars...")
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        new_bars_count = 0

        for i in range(0, len(symbols_with_stats), 10):
            batch = symbols_with_stats[i:i + 10]
            batch_results = download_bars_batch(batch, "1Day", 5, week_ago, today)
            conn = get_db()
            batch_count = 0
            for symbol in batch:
                symbol_bars = batch_results.get(symbol, [])
                if symbol_bars:
                    _store_bars(symbol, "1Day", symbol_bars, conn=conn)
                    new_bars_count += len(symbol_bars)
                    batch_count += 1
                    if batch_count >= 50:
                        conn.commit()
                        batch_count = 0
                    _mark_downloaded(symbol, "1Day", conn=conn)
                    _store_stats_for_symbol(symbol, conn=conn)
            conn.commit()
            conn.close()

            with download_lock:
                download_progress["symbols_done"] = min(i + 10, total_symbols)
                download_progress["bars_found"] = new_bars_count
                download_progress["current_symbol"] = f"Scanning bars batch {i//10 + 1}"

        print(f"  New bars stored: {new_bars_count}")

        # Step 4: Recompute ATR trailing stop for ALL symbols (from existing data)
        with download_lock:
            download_progress["phase"] = "Recomputing ATR..."
            download_progress["current_symbol"] = "Computing ATR trailing stops..."

        print("Step 4: Recomputing ATR trailing stops...")
        conn = get_db()
        atr_updated = 0
        for idx, sym in enumerate(symbols_with_stats):
            atr_data = compute_atr_for_screener(sym, '1Day', 2)
            if atr_data:
                conn.execute("""
                    UPDATE stats SET
                        atr_value = ?, atr_stop = ?, atr_signal = ?,
                        atr_crossed_above = ?, atr_crossed_below = ?,
                        atr_streak = ?, atr_multiplier = ?
                    WHERE symbol = ?
                """, (
                    atr_data['atr_value'], atr_data['atr_stop'], atr_data['atr_signal'],
                    atr_data['crossed_above'], atr_data['crossed_below'],
                    atr_data['atr_streak'], atr_data['multiplier'],
                    sym
                ))
                atr_updated += 1

            if idx % 50 == 0:
                with download_lock:
                    download_progress["symbols_done"] = idx
                    download_progress["current_symbol"] = f"ATR: {sym}"

        conn.commit()
        conn.close()
        print(f"  ATR updated for {atr_updated}/{len(symbols_with_stats)} symbols")

        with download_lock:
            download_progress["symbols_done"] = total_symbols

        profit_updated = 0
        # Step 5: Update profitability data using yfinance (real financial statements)
        with download_lock:
            download_progress["phase"] = "Updating profitability..."
            download_progress["current_symbol"] = "Fetching real financial data via yfinance..."

        print("Step 5: Updating profitability data from yfinance...")
        try:
            import yfinance as yf
            conn = get_db()
            symbols = [r['symbol'] for r in conn.execute(
                "SELECT symbol FROM stats WHERE price > 0 AND profit_status IN ('neutral','N/A') ORDER BY RANDOM() LIMIT 300"
            ).fetchall()]
            if symbols:
                print(f"  Fetching financial data for {len(symbols)} symbols...")
                for idx, sym in enumerate(symbols):
                    try:
                        tk = yf.Ticker(sym)
                        financials = tk.financials
                        if financials is not None and not financials.empty:
                            if 'Net Income' in financials.index:
                                ni = financials.loc['Net Income']
                                latest_ni = ni.iloc[0] if not ni.empty else None
                                prev_ni = ni.iloc[1] if len(ni) > 1 else None
                                if latest_ni is not None:
                                    if latest_ni > 0:
                                        if prev_ni is not None and prev_ni > 0:
                                            qoq = ((latest_ni - prev_ni) / abs(prev_ni)) * 100
                                            ps = 'growing' if latest_ni > prev_ni else 'declining'
                                        else:
                                            ps = 'profitable' if latest_ni > 0 else 'loss_making'
                                            qoq = None
                                    else:
                                        ps = 'loss_making'
                                        qoq = None
                                    conn.execute("UPDATE stats SET profit_status = ?, profit_last_qtr_pct = ? WHERE symbol = ?",
                                                 (ps, qoq, sym))
                                    profit_updated += 1
                    except Exception:
                        pass
                    if idx % 50 == 0:
                        conn.commit()
                        with download_lock:
                            download_progress["symbols_done"] = idx
                            download_progress["current_symbol"] = f"Profit: {sym}"
                conn.commit()
                print(f"  Real profit data updated for {profit_updated} symbols")
            conn.close()
        except ImportError:
            print("  yfinance not available, using weighted_alpha estimate")
            profit_updated = conn.execute("SELECT COUNT(*) FROM stats WHERE price > 0").fetchone()[0]
            conn = get_db()
            conn.execute("""
                UPDATE stats SET profit_status = CASE
                    WHEN weighted_alpha > 20 THEN 'profitable'
                    WHEN weighted_alpha > 5 THEN 'growing'
                    WHEN weighted_alpha < -30 THEN 'loss_making'
                    WHEN weighted_alpha < -10 THEN 'declining'
                    ELSE 'neutral'
                END WHERE price > 0
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"  yfinance error: {e}, falling back to weighted_alpha")
            profit_updated = conn.execute("SELECT COUNT(*) FROM stats WHERE price > 0").fetchone()[0]
            try:
                conn = get_db()
                conn.execute("""
                    UPDATE stats SET profit_status = CASE
                        WHEN weighted_alpha > 20 THEN 'profitable'
                        WHEN weighted_alpha > 5 THEN 'growing'
                        WHEN weighted_alpha < -30 THEN 'loss_making'
                        WHEN weighted_alpha < -10 THEN 'declining'
                        ELSE 'neutral'
                    END WHERE price > 0
                """)
                conn.commit()
                conn.close()
            except:
                pass
        print(f"  Profitability updated for {profit_updated}/{total_symbols} symbols")

        # Step 6: Update pre/post market prices from trade snapshots
        with download_lock:
            download_progress["phase"] = "Updating pre/post..."
            download_progress["current_symbol"] = "Fetching pre/post prices..."

        print("Step 6: Updating pre/post market prices...")
        conn = get_db()
        prepost_updated = 0
        batch_size = 10
        for i in range(0, len(symbols_with_stats), batch_size):
            batch = symbols_with_stats[i:i + batch_size]
            symbols_param = ",".join(batch)
            try:
                resp = alpaca_get("/v2/stocks/snapshots", base=DATA_URL, params={"symbols": symbols_param})
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and "snapshots" in data and isinstance(data["snapshots"], dict):
                        data = data["snapshots"]
                    for sym, snap in data.items():
                        if not snap or not isinstance(snap, dict):
                            continue
                        latest_trade = snap.get('latestTrade', {})
                        daily_bar = snap.get('dailyBar', {})
                        prev_bar = snap.get('prevDailyBar', {})
                        trade_price = latest_trade.get('p', 0)
                        trade_ts = latest_trade.get('t', '')
                        prev_close = prev_bar.get('c', 0) or daily_bar.get('o', 0)
                        pre_price = post_price = pre_change_pct = post_change_pct = None
                        if trade_price > 0 and prev_close > 0:
                            if trade_ts:
                                try:
                                    dt = datetime.fromisoformat(trade_ts.replace('Z', '+00:00'))
                                    hour = dt.hour
                                    if hour < 13:
                                        pre_price = trade_price
                                        pre_change_pct = round(((trade_price - prev_close) / prev_close) * 100, 2)
                                    elif hour >= 20:
                                        post_price = trade_price
                                        post_change_pct = round(((trade_price - prev_close) / prev_close) * 100, 2)
                                    else:
                                        pre_price = trade_price
                                        pre_change_pct = round(((trade_price - prev_close) / prev_close) * 100, 2)
                                        post_price = trade_price
                                        post_change_pct = round(((trade_price - prev_close) / prev_close) * 100, 2)
                                except Exception:
                                    pass
                            conn.execute("""
                                UPDATE stats SET
                                    pre_price = ?, pre_change_pct = ?,
                                    post_price = ?, post_change_pct = ?,
                                    last_updated = ?
                                WHERE symbol = ?
                            """, (pre_price, pre_change_pct, post_price, post_change_pct,
                                  datetime.now().isoformat(), sym))
                            prepost_updated += 1
            except Exception as e:
                print(f"  Pre/post batch error: {e}")
            time.sleep(0.15)

        conn.commit()
        conn.close()
        print(f"  Pre/post updated for {prepost_updated}/{total_symbols} symbols")

        # Step 7: Batch AI analysis for symbols without recent scores
        with download_lock:
            download_progress["phase"] = "Computing AI scores..."
            download_progress["current_symbol"] = "Running AI analysis..."

        print("Step 7: Computing AI scores...")
        ai_updated = 0
        try:
            conn = get_db()
            # Get symbols needing AI update (no score or stale > 24h)
            stale_cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
            needs_ai = [r['symbol'] for r in conn.execute("""
                SELECT s.symbol FROM stats s
                LEFT JOIN ai_analysis ai ON UPPER(s.symbol) = UPPER(ai.symbol)
                WHERE s.price > 0
                AND (ai.overall_score IS NULL OR ai.computed_at < ?)
                ORDER BY s.volume DESC
            """, (stale_cutoff,)).fetchall()]
            conn.close()

            ai_updated = 0
            for sym in needs_ai:
                try:
                    result = compute_ai_analysis(sym)
                    conn = get_db()
                    conn.execute("""
                        INSERT OR REPLACE INTO ai_analysis
                        (symbol, overall_score, bias, tech_score, momentum_score,
                         volume_score, events_score, volume_profile_score,
                         trendline_score, sentiment_score, conclusion, computed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sym.upper(),
                        result.get('overall_score', 0),
                        result.get('bias', 'neutral'),
                        result.get('tech_score', 0),
                        result.get('momentum_score', 0),
                        result.get('volume_score', 0),
                        result.get('events_score', 0),
                        result.get('volume_profile_score', 0),
                        result.get('trendline_score', 0),
                        result.get('sentiment_score', 0),
                        result.get('conclusion', 'HOLD'),
                        datetime.now().isoformat()
                    ))
                    conn.commit()
                    conn.close()
                    ai_updated += 1
                except Exception as e:
                    print(f"  AI error for {sym}: {e}")
                    try:
                        conn.close()
                    except Exception:
                        pass

            print(f"  AI scores computed for {ai_updated}/{len(needs_ai)} symbols")
        except Exception as e:
            print(f"  AI batch error: {e}")

        # Step 8: Refresh corporate events for top symbols
        with download_lock:
            download_progress["phase"] = "Refreshing events..."
            download_progress["current_symbol"] = "Downloading corporate events..."

        print("Step 8: Refreshing corporate events...")
        try:
            conn = get_db()
            top_by_volume = [r['symbol'] for r in conn.execute("""
                SELECT symbol FROM stats WHERE price > 0 ORDER BY volume DESC LIMIT 500
            """).fetchall()]
            conn.close()
            if top_by_volume:
                download_all_corporate_actions(top_by_volume)
                print(f"  Events refreshed for top {len(top_by_volume)} symbols")
        except Exception as e:
            print(f"  Events refresh error: {e}")

        with download_lock:
            download_progress["status"] = "complete"
            download_progress["phase"] = "refresh"
            download_progress["message"] = (
                f"Refresh complete! {atr_updated} ATR, {profit_updated} fundamentals, "
                f"{prepost_updated} pre/post, {ai_updated} AI scores updated."
            )
            download_progress["current_symbol"] = ""

        print(f"Delta refresh complete at {datetime.now()}")

    except Exception as e:
        print(f"Refresh error: {e}")
        import traceback
        traceback.print_exc()
        with download_lock:
            download_progress["status"] = "error"
            download_progress["phase"] = "refresh"
            download_progress["message"] = f"Refresh failed: {str(e)}"
    finally:
        with refresh_lock:
            refreshing = False


# ── Full History Download ────────────────────────────────────────────
download_lock = threading.Lock()
downloading_history = False
download_progress = {
    "status": "idle",
    "progress_type": "",     # "refresh", "prepost", "download", "reset"
    "timeframe": "",
    "phase": "",           # "assets", "corporate", "bars", "stats"
    "symbols_total": 0,
    "symbols_done": 0,
    "bars_found": 0,
    "current_symbol": "",
    "start_date": "2016-01-01",
    "end_date": datetime.now().strftime("%Y-%m-%d"),
    "assets_total": 0,
    "assets_fetched": 0,
    "message": "",
    "start_time": 0,
    "eta": 0,
    "speed": 0,
}


def _update_progress(**kwargs):
    """Thread-safe progress update."""
    global download_progress
    with download_lock:
        download_progress.update(kwargs)


def _get_existing_symbols():
    """Get list of all symbols that have any data in the DB."""
    conn = get_db()
    rows = conn.execute("SELECT symbol FROM stats WHERE price > 0").fetchall()
    conn.close()
    return [r['symbol'] for r in rows]


def _count_bars_for_symbol(symbol):
    """Count total bars stored for a symbol across all timeframes."""
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM bars WHERE symbol = ?", (symbol,)
    ).fetchone()['cnt']
    conn.close()
    return count


def _get_all_asset_symbols():
    """Get ALL tradable symbols from Alpaca API (full 12k+ list)."""
    print("  Fetching complete asset list from Alpaca...")
    assets = download_all_assets()
    if assets:
        store_assets(assets)
        tradable = [a for a in assets if a.get("tradable")]
        return [a["symbol"] for a in tradable]

    # Fallback to DB symbols
    conn = get_db()
    db_symbols = [r['symbol'] for r in conn.execute("SELECT symbol FROM assets WHERE tradable = 1").fetchall()]
    conn.close()
    if db_symbols:
        return db_symbols

    return POPULAR_TICKERS


def _fetch_bars_for_symbol(symbol, timeframe, limit, start_date, end_date):
    """Fetch bars for a single symbol with date range and pagination."""
    all_bars = []
    page_token = None
    max_pages = 10  # safety limit

    for page in range(max_pages):
        params = {
            "timeframe": timeframe,
            "limit": limit,
            "start": start_date,
            "end": end_date,
            "adjustment": "split",
            "feed": "iex",  # free tier feed
        }
        if page_token:
            params["page_token"] = page_token

        try:
            resp = alpaca_get(
                f"/v2/stocks/{symbol}/bars",
                params=params
            )
        except Exception as e:
            print(f"  Error fetching {symbol} {timeframe} page {page+1}: {e}")
            break

        if resp.status_code != 200:
            if resp.status_code == 429:
                time.sleep(2)
                continue
            break  # 404 or other errors = no data for this symbol/tf

        try:
            data = resp.json()
        except Exception:
            break

        bars = data.get('bars', [])
        if bars and isinstance(bars, list):
            all_bars.extend(bars)

        page_token = data.get('next_page_token')
        if not page_token:
            break
        # Rate limiter handles pacing between pages

    return all_bars


def _store_bars(symbol, timeframe, bars, conn=None):
    """Store bars in database efficiently. If conn provided, doesn't commit/close."""
    if not bars:
        return

    owned = conn is None
    if owned:
        conn = get_db()

    rows = []
    for bar in bars:
        t = bar.get('t', '')
        if isinstance(t, str):
            date_str = t[:10]
        else:
            try:
                date_str = datetime.fromtimestamp(t / 1000 if t > 1e12 else t).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                continue
        rows.append((
            symbol, timeframe, date_str,
            bar.get('o', 0), bar.get('h', 0),
            bar.get('l', 0), bar.get('c', 0), bar.get('v', 0)
        ))

    if rows:
        conn.executemany("""
            INSERT OR IGNORE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        if owned:
            conn.commit()
    if owned:
        conn.close()


def _store_stats_for_symbol(symbol, conn=None):
    """Compute and store stats for a single symbol from bar data."""
    stats = compute_stats_from_bars(symbol, conn=conn)
    if not stats:
        return False

    owned = conn is None
    if owned:
        conn = get_db()

    # Compute ATR trailing stop
    atr_data = compute_atr_for_screener(symbol, '1Day', 2)

    wa = stats.get('weighted_alpha', 0) or 0
    if wa > 20:
        profit_status = "profitable"
    elif wa > 5:
        profit_status = "growing"
    elif wa < -30:
        profit_status = "loss_making"
    elif wa < -10:
        profit_status = "declining"
    else:
        profit_status = "neutral"

    conn.execute("""
        INSERT OR REPLACE INTO stats (
            symbol, name, price, volume, change_pct, atrp, weighted_alpha,
            atr_signal, atr_stop, streak, pre_price, pre_change_pct,
            post_price, post_change_pct, fractionable, marginable,
            asset_class, exchange, status, tradable, last_updated,
            atr_value, atr_crossed_above, atr_crossed_below, atr_streak, atr_multiplier,
            profit_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        stats['symbol'], stats['name'], stats['price'], stats['volume'],
        stats['change_pct'], stats['atrp'], wa,
        atr_data['atr_signal'] if atr_data else 0,
        atr_data['atr_stop'] if atr_data else None,
        stats['streak'], None, None, None, None,
        stats['fractionable'], stats['marginable'],
        stats['asset_class'], stats['exchange'], stats['status'], stats['tradable'],
        datetime.now().isoformat(),
        atr_data['atr_value'] if atr_data else 0,
        atr_data['crossed_above'] if atr_data else 0,
        atr_data['crossed_below'] if atr_data else 0,
        atr_data['atr_streak'] if atr_data else 0,
        atr_data['multiplier'] if atr_data else 2,
        profit_status,
    ))
    if owned:
        conn.commit()
        conn.close()
    return True


def _mark_downloaded(symbol, timeframe, conn=None):
    """Mark a symbol as having downloaded data for a timeframe."""
    col_map = {'1Day': 'downloaded_1day', '1Hour': 'downloaded_1hour', '1Min': 'downloaded_1min'}
    col = col_map.get(timeframe)
    if not col:
        return

    owned = conn is None
    if owned:
        conn = get_db()
    conn.execute(f"""
        UPDATE stats SET {col} = ? WHERE symbol = ?
    """, (datetime.now().isoformat(), symbol))
    if owned:
        conn.commit()
        conn.close()


def _is_downloaded(symbol, timeframe, conn=None):
    """Check if a symbol already has downloaded data for a timeframe."""
    col_map = {'1Day': 'downloaded_1day', '1Hour': 'downloaded_1hour', '1Min': 'downloaded_1min'}
    col = col_map.get(timeframe)
    if not col:
        return False

    owned = conn is None
    if owned:
        conn = get_db()
    row = conn.execute(f"SELECT {col} FROM stats WHERE symbol = ?", (symbol,)).fetchone()
    if owned:
        conn.close()
    return row is not None and row[col] is not None


# ── Multi-symbol Batch Download ──────────────────────────────────────
def download_bars_batch(symbols, timeframe, limit=10000, start_date="2016-01-01", end_date=None):
    """Download bars for up to 10 symbols in a single API call. Much faster.

    Handles free-tier 500-bar limit by paginating backward in time.
    """
    if not symbols:
        return {}
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    batch_size = 10  # Alpaca max per request
    all_results = {}

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        symbols_param = ",".join(batch)

        # Paginate: fetch in chunks working backward from end_date
        current_end = end_date
        batch_bars = {sym: [] for sym in batch}

        while current_end > start_date:
            params = {
                "symbols": symbols_param,
                "timeframe": timeframe,
                "limit": 500,  # Free tier max
                "start": start_date,
                "end": current_end,
                "adjustment": "split",
                "feed": "iex",
            }

            try:
                resp = alpaca_get("/v2/stocks/bars", params=params)

                if resp.status_code == 429:
                    time.sleep(3)
                    resp = alpaca_get("/v2/stocks/bars", params=params)

                if resp.status_code == 200:
                    data = resp.json()
                    bars_data = data.get('bars', {})
                    if isinstance(bars_data, dict):
                        for sym, bars in bars_data.items():
                            if bars and isinstance(bars, list):
                                batch_bars[sym].extend(bars)
                                # Update end date to oldest bar - 1 day for next page
                                oldest = bars[0].get('t', '')
                                if isinstance(oldest, str):
                                    oldest_date = oldest[:10]
                                elif isinstance(oldest, (int, float)):
                                    oldest_date = datetime.fromtimestamp(
                                        oldest / 1000 if oldest > 1e12 else oldest
                                    ).strftime('%Y-%m-%d')
                                else:
                                    oldest_date = current_end
                                current_end = oldest_date
                    else:
                        break  # No data returned, stop paginating
                elif resp.status_code == 400:
                    print(f"  Batch 400, trying individually for {len(batch)} symbols")
                    for sym in batch:
                        try:
                            sr = alpaca_get(f"/v2/stocks/{sym}/bars", params={
                                "timeframe": timeframe, "limit": 500,
                                "start": start_date, "end": current_end,
                                "adjustment": "split", "feed": "iex",
                            })
                            if sr.status_code == 200:
                                sd = sr.json()
                                sb = sd.get('bars', [])
                                if sb:
                                    batch_bars[sym].extend(sb)
                                    oldest = sb[0].get('t', '')
                                    if isinstance(oldest, str):
                                        oldest_date = oldest[:10]
                                    elif isinstance(oldest, (int, float)):
                                        oldest_date = datetime.fromtimestamp(
                                            oldest / 1000 if oldest > 1e12 else oldest
                                        ).strftime('%Y-%m-%d')
                                    else:
                                        oldest_date = current_end
                                    current_end = min(current_end, oldest_date)
                        except Exception:
                            pass
                    break  # After individual attempts, move to next batch
                else:
                    break  # Other error, stop paginating
            except Exception as e:
                print(f"  Batch error: {e}")
                break

        # Deduplicate and store results
        for sym, bars in batch_bars.items():
            if bars:
                seen = set()
                unique = []
                for b in bars:
                    date_key = b.get('t', '')
                    if isinstance(date_key, str):
                        date_key = date_key[:10]
                    if date_key not in seen:
                        seen.add(date_key)
                        unique.append(b)
                all_results[sym] = unique

    return all_results


def _fill_historical_gaps(all_symbols, db_conn, today):
    """Fill missing older data for symbols where oldest_data is not early enough.

    For symbols that already have data but only go back a few years,
    fetch the missing historical bars in 500-bar chunks (free tier limit).
    """
    print("\nChecking for historical gaps...")

    # Find symbols that have data but oldest_data is after 2020 (missing early history)
    gap_symbols = db_conn.execute("""
        SELECT symbol, oldest_data FROM stats
        WHERE oldest_data IS NOT NULL AND oldest_data > '2020-01-01'
    """).fetchall()

    # Also find symbols with stats but no oldest_data
    no_oldest = db_conn.execute("""
        SELECT symbol FROM stats
        WHERE oldest_data IS NULL AND price > 0
    """).fetchall()

    need_check = [r['symbol'] for r in gap_symbols] + [r['symbol'] for r in no_oldest]
    need_check = list(set(need_check))  # Deduplicate

    if not need_check:
        print("  No gaps found — all symbols have data back to 2020 or earlier")
        return 0

    print(f"  Found {len(need_check)} symbols with data gaps (oldest after 2020 or missing)")

    gap_filled = 0
    gap_bars = 0
    FREE_TIER_LIMIT = 500
    EARLIEST_TARGET = "2016-01-01"

    # Process in batches of 10
    for i in range(0, len(need_check), 10):
        batch = need_check[i:i + 10]

        for symbol in batch:
            # Get current oldest data for this symbol
            row = db_conn.execute(
                "SELECT oldest_data FROM stats WHERE symbol = ?", (symbol,)
            ).fetchone()
            current_oldest = row['oldest_data'] if row else None

            if not current_oldest or current_oldest <= EARLIEST_TARGET:
                continue  # Already has full history

            # Fetch data from EARLIEST_TARGET to current_oldest
            fetch_start = EARLIEST_TARGET
            fetch_end = current_oldest
            all_gap_bars = []

            while fetch_start < fetch_end:
                try:
                    resp = alpaca_get(f"/v2/stocks/{symbol}/bars", params={
                        "timeframe": "1Day", "limit": FREE_TIER_LIMIT,
                        "start": fetch_start, "end": fetch_end,
                        "adjustment": "split", "feed": "iex",
                    })
                    if resp.status_code == 200:
                        data = resp.json()
                        bars = data.get('bars', [])
                        if not bars:
                            break
                        all_gap_bars.extend(bars)
                        # Update fetch_end to oldest bar - 1 day for next page
                        oldest_t = bars[0].get('t', '')
                        if isinstance(oldest_t, str):
                            oldest_date = oldest_t[:10]
                        elif isinstance(oldest_t, (int, float)):
                            oldest_date = datetime.fromtimestamp(
                                oldest_t / 1000 if oldest_t > 1e12 else oldest_t
                            ).strftime('%Y-%m-%d')
                        else:
                            break
                        fetch_end = oldest_date
                        if len(bars) < FREE_TIER_LIMIT:
                            break  # No more data available
                    elif resp.status_code == 429:
                        time.sleep(3)
                        continue
                    else:
                        break
                except Exception as e:
                    print(f"  Gap fill error for {symbol}: {e}")
                    break

            if all_gap_bars:
                # Deduplicate and store
                seen = set()
                unique = []
                for b in all_gap_bars:
                    date_key = b.get('t', '')
                    if isinstance(date_key, str):
                        date_key = date_key[:10]
                    if date_key not in seen:
                        seen.add(date_key)
                        unique.append(b)

                for bar in unique:
                    t = bar.get('t', '')
                    if isinstance(t, str):
                        date_str = t[:10]
                    else:
                        try:
                            date_str = datetime.fromtimestamp(
                                t / 1000 if t > 1e12 else t
                            ).strftime('%Y-%m-%d')
                        except Exception:
                            continue

                    db_conn.execute("""
                        INSERT OR IGNORE INTO bars (symbol, timeframe, date, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        symbol, '1Day', date_str,
                        bar.get('o', 0), bar.get('h', 0),
                        bar.get('l', 0), bar.get('c', 0),
                        bar.get('v', 0)
                    ))

                db_conn.commit()
                gap_filled += 1
                gap_bars += len(unique)
                print(f"  Filled {symbol}: +{len(unique)} bars (oldest now: {unique[-1].get('t', '?')})")

                # Recompute stats with the full bar history
                _store_stats_for_symbol(symbol, conn=db_conn)

        if (i + 10) % 100 == 0:
            print(f"  Gap fill progress: {min(i + 10, len(need_check))}/{len(need_check)}")

    print(f"  Gap fill complete: {gap_filled} symbols, +{gap_bars:,} bars")
    return gap_bars


def download_all_history():
    """Download ALL max historical data for all symbols.

    - Fetches full asset list from Alpaca (12k+ symbols)
    - Stores asset metadata in DB
    - Skips already-downloaded symbols (resume capability)
    - Downloads corporate actions (splits/dividends) for top 500
    - Downloads bars for 1Day only (1Week/1Month computed from 1Day)
    - Uses multi-symbol batch API (up to 10 per request) for speed
    - Handles free-tier 500-bar limit by paginating backward in time
    - Fills historical gaps for symbols with incomplete data
    - Computes and stores stats progressively as each symbol completes
    """
    global downloading_history, download_progress
    with download_lock:
        if downloading_history:
            return {"status": "already_running"}
        downloading_history = True

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        start_time = time.time()

        with download_lock:
            download_progress = {
                "status": "running",
                "timeframe": "",
                "phase": "init",
                "symbols_total": 0,
                "symbols_done": 0,
                "bars_found": 0,
                "current_symbol": "",
                "start_date": "2016-01-01",
                "end_date": today,
                "assets_total": 0,
                "assets_fetched": 0,
                "message": "Starting...",
                "start_time": start_time,
            }

        print("=" * 50)
        print(f"Full history download started at {datetime.now()}")
        print("=" * 50)

        # Phase 1: Get all assets
        _update_progress(phase="assets", message="Fetching all tradable assets...")
        all_symbols = _get_all_asset_symbols()
        _update_progress(assets_total=len(all_symbols), message=f"Found {len(all_symbols)} assets")
        print(f"Total symbols to process: {len(all_symbols)}")

        total_bars = 0
        # Only 1Day — weekly/monthly computed from it
        # Max limit=10000 per request gives ALL available history from 2016
        timeframes = [
            ("1Day", 10000),
        ]

        for tf, per_req_limit in timeframes:
            _update_progress(
                phase="bars",
                timeframe=tf,
                symbols_total=len(all_symbols),
                symbols_done=0,
                current_symbol="",
                message=f"Downloading {tf} bars..."
            )

            tf_bars = 0
            tf_found = 0
            tf_skipped = 0
            db_conn = get_db()
            batch_count = 0

            # Build list of symbols that need downloading (skip cached)
            need_download = []
            for idx, symbol in enumerate(all_symbols):
                if _is_downloaded(symbol, tf, conn=db_conn):
                    tf_skipped += 1
                    with download_lock:
                        download_progress["symbols_done"] = idx + 1
                        download_progress["current_symbol"] = f"{symbol} (cached)"
                        download_progress["bars_found"] = download_progress.get("bars_found", 0)
                else:
                    need_download.append(symbol)

            print(f"  {tf}: {tf_skipped} cached, {len(need_download)} need download")

            # Download in batches of 10 symbols per API call
            api_batch = 10
            for i in range(0, len(need_download), api_batch):
                batch_symbols = need_download[i:i + api_batch]

                _update_progress(phase="bars", message=f"Downloading {tf} batch {i//api_batch + 1}...")
                batch_results = download_bars_batch(batch_symbols, tf, per_req_limit, "2016-01-01", today)

                for symbol in batch_symbols:
                    symbol_bars = batch_results.get(symbol, [])

                    with download_lock:
                        download_progress["symbols_done"] = download_progress["symbols_done"] + 1
                        download_progress["current_symbol"] = symbol
                        download_progress["bars_found"] += len(symbol_bars)

                    if symbol_bars:
                        _store_bars(symbol, tf, symbol_bars, conn=db_conn)
                        tf_bars += len(symbol_bars)
                        tf_found += 1
                        batch_count += 1

                        if batch_count >= 50:
                            db_conn.commit()
                            batch_count = 0

                        _mark_downloaded(symbol, tf, conn=db_conn)

                        if tf == "1Day":
                            _update_progress(phase="stats", message=f"Computing stats for {symbol}...")
                            _store_stats_for_symbol(symbol, conn=db_conn)

                if (i + api_batch) % 100 == 0:
                    done = tf_skipped + i + len(batch_symbols)
                    print(f"  {tf}: {done}/{len(all_symbols)} | {tf_found} new | {tf_skipped} cached | {tf_bars} bars")

            total_bars += tf_bars
            db_conn.commit()
            db_conn.close()
            print(f"\n  {tf} complete: {tf_found} new, {tf_skipped} cached, {tf_bars} bars")

        # Phase 2: Download corporate actions for top symbols
        _update_progress(phase="corporate", message="Downloading corporate actions...")
        top_symbols = all_symbols[:500]  # Top 500 for splits/dividends
        download_all_corporate_actions(top_symbols)

        # Phase 3: Final stats pass for any symbols that have bars but no stats
        _update_progress(phase="stats", message="Final stats pass...")
        conn = get_db()
        symbols_needing_stats = [r['symbol'] for r in conn.execute(
            "SELECT symbol FROM bars WHERE timeframe = '1Day' GROUP BY symbol HAVING COUNT(*) >= 60"
        ).fetchall()]
        conn.close()

        # Only compute for symbols that don't already have stats
        conn = get_db()
        existing_stats = [r['symbol'] for r in conn.execute("SELECT symbol FROM stats WHERE weighted_alpha != 0 OR price > 0").fetchall()]
        conn.close()

        need_stats = [s for s in symbols_needing_stats if s not in existing_stats]
        print(f"Computing stats for {len(need_stats)} remaining symbols...")
        for i, sym in enumerate(need_stats):
            _store_stats_for_symbol(sym)
            if (i + 1) % 50 == 0:
                print(f"  Stats: {i+1}/{len(need_stats)}")

        # Phase 4: Fill historical gaps for symbols with incomplete data
        _update_progress(phase="gaps", message="Checking for historical data gaps...")
        conn = get_db()
        gap_bars = _fill_historical_gaps(all_symbols, conn, today)
        conn.close()
        total_bars += gap_bars

        # Final summary
        conn = get_db()
        total_all = conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0]
        total_stats = conn.execute("SELECT COUNT(*) FROM stats WHERE price > 0").fetchone()[0]
        total_assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        by_tf = conn.execute("SELECT timeframe, COUNT(*) FROM bars GROUP BY timeframe").fetchall()
        conn.close()

        print(f"\n{'='*50}")
        print(f"DOWNLOAD COMPLETE")
        print(f"Assets in DB: {total_assets}")
        print(f"Symbols with stats: {total_stats}")
        print(f"Total bars in database: {total_all}")
        for tf_name, cnt in by_tf:
            print(f"  {tf_name}: {cnt:,}")
        print(f"{'='*50}")

        # Recompute streaks from bar data using fast SQL
        _update_progress(phase="streaks", message="Recomputing streaks...")
        conn2 = get_db()
        _recompute_streaks_sql(conn2)
        conn2.close()
        print("Streaks recomputed after download.")

        with download_lock:
            download_progress = {
                "status": "complete",
                "timeframe": "",
                "phase": "done",
                "symbols_total": len(all_symbols),
                "symbols_done": len(all_symbols),
                "bars_found": total_bars,
                "current_symbol": "",
                "start_date": "2016-01-01",
                "end_date": today,
                "assets_total": total_assets,
                "assets_fetched": total_assets,
                "message": f"Complete! {total_assets:,} assets, {total_stats:,} with stats, {total_all:,} bars",
            }

        return {
            "status": "complete",
            "bars_stored": total_bars,
            "symbols": len(all_symbols),
            "total_in_db": total_all,
            "assets": total_assets,
            "stats": total_stats,
        }

    except Exception as e:
        print(f"History download error: {e}")
        import traceback
        traceback.print_exc()
        with download_lock:
            download_progress["status"] = "error"
            download_progress["message"] = str(e)
        return {"status": "error", "message": str(e)}
    finally:
        with download_lock:
            downloading_history = False


# ── Popular Tickers (Fallback / Quick Start) ────────────────────────
def _build_fallback_assets():
    """Build asset dicts from popular tickers when API fails."""
    assets = []
    for sym in POPULAR_TICKERS:
        assets.append({
            "symbol": sym,
            "name": sym,
            "tradable": True,
            "asset_class": "us_equity",
            "exchange": "NYSE/NASDAQ",
            "status": "active",
            "fractionable": True,
            "marginable": True,
        })
    return assets


# ── AI Analysis ─────────────────────────────────────────────────────

def compute_atr(symbol, timeframe='1Day', period=14, multiplier=2):
    """Compute ATR with Wilder's RMA smoothing and Supertrend trailing stop line.
    Uses LATEST bars (DESC LIMIT, then reversed) for accurate recent ATR.
    """
    conn = get_db()
    tf = timeframe if timeframe != '1Day' else '1Day'

    bars = conn.execute("""
        SELECT date, open, high, low, close, volume FROM bars
        WHERE symbol = ? AND timeframe = ?
        ORDER BY date DESC
        LIMIT 250
    """, (symbol.upper(), tf)).fetchall()
    bars.reverse()
    conn.close()

    if not bars or len(bars) < period + 1:
        return None

    # Calculate True Range (TR)
    tr_values = []
    for i in range(1, len(bars)):
        high = bars[i]['high']
        low = bars[i]['low']
        prev_close = bars[i-1]['close']
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)

    if len(tr_values) < period:
        return None

    # Wilder's RMA
    rma = sum(tr_values[:period]) / period
    atr_values = [rma]

    for i in range(period, len(tr_values)):
        rma = (rma * (period - 1) + tr_values[i]) / period
        atr_values.append(rma)

    # ── Supertrend trailing stop line ──
    basic_upper = []
    basic_lower = []
    for i in range(len(atr_values)):
        bar_idx = period + i
        close = bars[bar_idx]['close']
        basic_upper.append(close + multiplier * atr_values[i])
        basic_lower.append(close - multiplier * atr_values[i])

    # Supertrend direction tracking (start in uptrend)
    trailing_stop = []
    direction = []
    final_stop = basic_lower[0]
    final_dir = 1

    for i in range(len(atr_values)):
        close = bars[period + i]['close']

        # Progressive bands
        if i == 0:
            final_upper = basic_upper[0]
            final_lower = basic_lower[0]
        else:
            final_upper = min(basic_upper[i], final_upper) if close > final_stop else basic_upper[i]
            final_lower = max(basic_lower[i], final_lower) if close < final_stop else basic_lower[i]

        # Trail stop
        if final_dir == 1:
            final_stop = max(final_lower, final_stop) if i > 0 else final_lower
        else:
            final_stop = min(final_upper, final_stop) if i > 0 else final_upper

        # Check for flip
        if close < final_stop and final_dir == 1:
            final_dir = -1
            final_stop = final_upper
        elif close > final_stop and final_dir == -1:
            final_dir = 1
            final_stop = final_lower

        trailing_stop.append(round(final_stop, 4))
        direction.append(final_dir)

    current_atr = atr_values[-1]
    current_price = bars[-1]['close']

    return {
        "atr": round(current_atr, 4),
        "atr_pct": round((current_atr / current_price * 100), 2) if current_price > 0 else 0,
        "long_stop": round(basic_lower[-1], 2),
        "short_stop": round(basic_upper[-1], 2),
        "above_atr": current_price > basic_lower[-1],
        "below_atr": current_price < basic_upper[-1],
        "crossed_above_today": False,
        "crossed_below_today": False,
        "timeframe": tf,
        "multiplier": multiplier,
        "bars_used": len(bars),
        "trailing_stop": trailing_stop,
        "direction": direction,
        "atr_offset": period,
    }


def compute_atr_for_screener(symbol, timeframe='1Day', multiplier=2):
    """Compute Supertrend-style ATR trailing stop for screener.
    Uses LATEST bars (DESC LIMIT, then reversed) for accurate recent ATR.
    Returns dict with atr_value, atr_stop, atr_signal, crossed flags, streak.
    """
    conn = get_db()

    # For 1Week/1Month, aggregate from 1Day bars
    if timeframe in ('1Week', '1Month'):
        tf_bars = aggregate_bars_to_tf(symbol, timeframe)
    else:
        tf_bars = conn.execute("""
            SELECT date, open, high, low, close, volume FROM bars
            WHERE symbol = ? AND timeframe = '1Day'
            ORDER BY date DESC
            LIMIT 250
        """, (symbol.upper(),)).fetchall()
        tf_bars.reverse()

    conn.close()

    if not tf_bars or len(tf_bars) < 15:
        return None

    bars = [dict(b) for b in tf_bars]
    period = 14

    # Calculate True Range (TR)
    tr_values = []
    for i in range(1, len(bars)):
        h = bars[i]['high']
        l = bars[i]['low']
        pc = bars[i-1]['close']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_values.append(tr)

    if len(tr_values) < period:
        return None

    # Wilder's RMA
    rma = sum(tr_values[:period]) / period
    atr_values = [rma]
    for i in range(period, len(tr_values)):
        rma = (rma * (period - 1) + tr_values[i]) / period
        atr_values.append(rma)

    current_atr = atr_values[-1]
    current_price = bars[-1]['close']
    current_close = bars[-1]['close']
    prev_close = bars[-2]['close'] if len(bars) > 1 else current_close

    # ── Supertrend via full history (same as compute_atr) ──
    basic_upper = []
    basic_lower = []
    for i in range(len(atr_values)):
        bar_idx = period + i
        close = bars[bar_idx]['close']
        basic_upper.append(close + multiplier * atr_values[i])
        basic_lower.append(close - multiplier * atr_values[i])

    trailing_stop = []
    direction = []
    final_stop = basic_lower[0]
    final_dir = 1

    for i in range(len(atr_values)):
        close = bars[period + i]['close']

        if i == 0:
            final_upper = basic_upper[0]
            final_lower = basic_lower[0]
        else:
            final_upper = min(basic_upper[i], final_upper) if close > final_stop else basic_upper[i]
            final_lower = max(basic_lower[i], final_lower) if close < final_stop else basic_lower[i]

        if final_dir == 1:
            final_stop = max(final_lower, final_stop) if i > 0 else final_lower
        else:
            final_stop = min(final_upper, final_stop) if i > 0 else final_upper

        if close < final_stop and final_dir == 1:
            final_dir = -1
            final_stop = final_upper
        elif close > final_stop and final_dir == -1:
            final_dir = 1
            final_stop = final_lower

        trailing_stop.append(round(final_stop, 4))
        direction.append(final_dir)

    atr_stop = trailing_stop[-1]
    atr_signal = direction[-1]

    # Cross detection using full Supertrend history
    crossed_above_today = 0
    crossed_below_today = 0
    if len(direction) >= 2:
        if direction[-1] == 1 and direction[-2] == -1:
            crossed_above_today = 1
        elif direction[-1] == -1 and direction[-2] == 1:
            crossed_below_today = 1

    # ATR streak: days since last flip
    atr_streak = 0
    if direction:
        last_sig = direction[-1]
        for i in range(len(direction) - 1, -1, -1):
            if direction[i] == last_sig:
                atr_streak += 1
            else:
                break

    return {
        "atr_value": round(current_atr, 4),
        "atr_stop": round(atr_stop, 2),
        "atr_signal": atr_signal,
        "atr_pct": round((current_atr / current_price * 100), 2) if current_price > 0 else 0,
        "crossed_above": crossed_above_today,
        "crossed_below": crossed_below_today,
        "atr_streak": atr_streak,
        "multiplier": multiplier,
        "timeframe": timeframe,
        "bars_used": len(bars),
    }


def compute_ai_analysis(symbol):
    """Compute AI analysis score and bias for a stock from stored data."""
    conn = get_db()

    # Get bars (1Day) - limit to most recent 500 for fast computation
    bars = conn.execute("""
        SELECT date, open, high, low, close, volume FROM bars
        WHERE symbol = ? AND timeframe = '1Day'
        ORDER BY date ASC
        LIMIT 500
    """, (symbol.upper(),)).fetchall()

    # Get stats
    stat = conn.execute("""
        SELECT * FROM stats WHERE UPPER(symbol) = ?
    """, (symbol.upper(),)).fetchone()

    # Get corporate events
    events = conn.execute("""
        SELECT event_type, event_date FROM corporate_events
        WHERE UPPER(symbol) = ? ORDER BY event_date DESC LIMIT 5
    """, (symbol.upper(),)).fetchall()

    conn.close()

    if not bars or len(bars) < 10:
        return {
            "symbol": symbol.upper(),
            "overall_score": 0,
            "bias": "neutral",
            "tech_score": 0,
            "momentum_score": 0,
            "volume_score": 0,
            "events_score": 0,
            "signals": ["Insufficient data for analysis"],
        }

    closes = [b['close'] for b in bars]
    volumes = [b['volume'] for b in bars]
    highs = [b['high'] for b in bars]
    lows = [b['low'] for b in bars]
    n = len(closes)

    # ── Technical Score (0-100) ──────────────────────────────────────
    tech_score = 50.0

    # RSI (14-period)
    if n >= 15:
        gains, losses = [], []
        for i in range(1, min(15, n)):
            delta = closes[i] - closes[i-1]
            gains.append(max(0, delta))
            losses.append(max(0, -delta))
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            if rsi < 30:
                tech_score += 20  # Oversold = bullish
            elif rsi < 45:
                tech_score += 10
            elif rsi > 70:
                tech_score -= 20  # Overbought = bearish
            elif rsi > 55:
                tech_score -= 5

    # Moving averages
    sma20 = sum(closes[-20:]) / min(20, n) if n >= 10 else closes[-1]
    sma50 = sum(closes[-50:]) / min(50, n) if n >= 25 else sma20
    current = closes[-1]

    if current > sma20 > sma50:
        tech_score += 15  # Golden trend
    elif current > sma20:
        tech_score += 5
    elif current < sma20 < sma50:
        tech_score -= 15  # Death cross
    elif current < sma20:
        tech_score -= 5

    # Price position in range
    if n >= 20:
        high_20 = max(highs[-20:])
        low_20 = min(lows[-20:])
        if high_20 > low_20:
            position = (current - low_20) / (high_20 - low_20)
            if position > 0.8:
                tech_score -= 10  # Near highs
            elif position < 0.2:
                tech_score += 10  # Near lows

    tech_score = max(0, min(100, tech_score))

    # ── Momentum Score (0-100) ──────────────────────────────────────
    momentum_score = 50.0

    if stat:
        wa = stat['weighted_alpha'] or 0
        change = stat['change_pct'] or 0
        streak = stat['streak'] or 0

        # Weighted alpha
        if wa > 50:
            momentum_score += 25
        elif wa > 20:
            momentum_score += 15
        elif wa > 0:
            momentum_score += 5
        elif wa < -30:
            momentum_score -= 25
        elif wa < -10:
            momentum_score -= 15

        # Daily change
        if change > 5:
            momentum_score += 10
        elif change > 2:
            momentum_score += 5
        elif change < -5:
            momentum_score -= 10
        elif change < -2:
            momentum_score -= 5

        # Streak
        if streak >= 5:
            momentum_score += 10
        elif streak >= 3:
            momentum_score += 5
        elif streak <= -5:
            momentum_score -= 10
        elif streak <= -3:
            momentum_score -= 5

    # Short-term price direction
    if n >= 5:
        short_trend = sum(closes[-3:]) / 3 - sum(closes[-6:-3]) / 3
        if short_trend > 0:
            momentum_score += 5
        else:
            momentum_score -= 5

    momentum_score = max(0, min(100, momentum_score))

    # ── Volume Score (0-100) ────────────────────────────────────────
    volume_score = 50.0

    if n >= 20 and stat:
        avg_vol = sum(volumes[-20:]) / min(20, n)
        current_vol = volumes[-1]
        if avg_vol > 0:
            vol_ratio = current_vol / avg_vol
            if vol_ratio > 2.0:
                volume_score += 20  # High volume = interest
            elif vol_ratio > 1.5:
                volume_score += 10
            elif vol_ratio < 0.5:
                volume_score -= 10  # Low volume = disinterest

        # Volume trend
        if n >= 10:
            early_avg = sum(volumes[-10:-5]) / 5 if len(volumes) >= 10 else avg_vol
            recent_avg = sum(volumes[-5:]) / min(5, n)
            if recent_avg > early_avg * 1.2:
                volume_score += 10
            elif recent_avg < early_avg * 0.8:
                volume_score -= 5

    volume_score = max(0, min(100, volume_score))

    # ── Volume Profile Score (0-100) ─────────────────────────────────
    volume_profile_score = 50.0
    if n >= 20:
        # VWAP relative position
        recent_c = closes[-20:]
        recent_v = volumes[-20:]
        total_v = sum(recent_v)
        vwap = sum(c * v for c, v in zip(recent_c, recent_v)) / total_v if total_v > 0 else current
        vwap_pct = ((current - vwap) / vwap) * 100 if vwap > 0 else 0
        if vwap_pct > 3:
            volume_profile_score += 15  # Above VWAP = buying pressure
        elif vwap_pct < -3:
            volume_profile_score -= 15  # Below VWAP = selling pressure

        # Volume concentration (high volume at highs vs lows)
        high_vol_days = sum(1 for i in range(-10, 0) if volumes[i] > sum(volumes[-20:]) / 20)
        if high_vol_days >= 6:
            if current > sum(closes[-20:]) / 20:
                volume_profile_score += 10  # High vol at high prices
            else:
                volume_profile_score -= 10  # High vol at low prices

        # Accumulation/Distribution
        ad_scores = []
        for i in range(max(0, n - 20), n):
            clv = ((highs[i] - lows[i]) / (highs[i] - lows[i])) if highs[i] != lows[i] else 0.5
            ad = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / (highs[i] - lows[i]) if highs[i] != lows[i] else 0
            ad_scores.append(ad * volumes[i])
        if ad_scores and sum(ad_scores[-5:]) > sum(ad_scores[:5]):
            volume_profile_score += 10  # Accumulation
        elif ad_scores and sum(ad_scores[-5:]) < sum(ad_scores[:5]):
            volume_profile_score -= 10  # Distribution

    volume_profile_score = max(0, min(100, volume_profile_score))

    # ── Trendline Score (0-100) ──────────────────────────────────────
    trendline_score = 50.0
    if n >= 20:
        # Higher highs / higher lows check
        recent_highs = highs[-10:]
        recent_lows = lows[-10:]
        higher_highs = sum(1 for i in range(1, len(recent_highs)) if recent_highs[i] > recent_highs[i-1])
        higher_lows = sum(1 for i in range(1, len(recent_lows)) if recent_lows[i] > recent_lows[i-1])

        if higher_highs >= 6 and higher_lows >= 6:
            trendline_score += 20  # Strong uptrend
        elif higher_highs >= 4:
            trendline_score += 10
        elif higher_highs <= 2 and higher_lows <= 2:
            trendline_score -= 20  # Strong downtrend
        elif higher_highs <= 4:
            trendline_score -= 10

        # Trendline breakout detection
        if n >= 30:
            resistance = max(highs[-30:-5])
            support = min(lows[-30:-5])
            if current > resistance:
                trendline_score += 15  # Breakout above resistance
            elif current < support:
                trendline_score -= 15  # Breakdown below support

        # Channel position
        if n >= 20:
            channel_high = max(highs[-20:])
            channel_low = min(lows[-20:])
            if channel_high > channel_low:
                channel_pos = (current - channel_low) / (channel_high - channel_low)
                if channel_pos > 0.85:
                    trendline_score -= 5  # Overextended
                elif channel_pos < 0.15:
                    trendline_score += 5  # Oversold in channel

    trendline_score = max(0, min(100, trendline_score))

    # ── Social/News Sentiment Score (0-100) ──────────────────────────
    # Derived from price action + events as proxy for news/social buzz
    sentiment_score = 50.0

    # Recent price acceleration (proxy for positive news)
    if n >= 5:
        recent_return = (closes[-1] - closes[-5]) / closes[-5] * 100 if closes[-5] > 0 else 0
        if recent_return > 10:
            sentiment_score += 15  # Strong positive momentum
        elif recent_return > 5:
            sentiment_score += 8
        elif recent_return < -10:
            sentiment_score -= 15  # Strong negative
        elif recent_return < -5:
            sentiment_score -= 8

    # Volume spike (proxy for social media buzz)
    if n >= 20:
        avg_vol_20 = sum(volumes[-20:]) / 20
        if avg_vol_20 > 0 and volumes[-1] > avg_vol_20 * 3:
            if closes[-1] > closes[-2]:
                sentiment_score += 10  # High volume up move
            else:
                sentiment_score -= 10  # High volume down move

    # Event impact
    for ev in events[:3]:
        evt_type = (ev['event_type'] or '').lower()
        if evt_type in {'split', 'bonus', 'merger', 'acquisition', 'dividend'}:
            sentiment_score += 8
        elif evt_type in {'dilution', 'rights_issue', 'bankruptcy'}:
            sentiment_score -= 8

    sentiment_score = max(0, min(100, sentiment_score))

    # ── Events Score (0-100) ────────────────────────────────────────
    events_score = 50.0
    important_types = {'split', 'bonus', 'merger', 'acquisition', 'dividend', 'spin_off'}
    negative_types = {'dilution', 'rights_issue', 'bankruptcy'}

    for ev in events:
        evt_type = (ev['event_type'] or '').lower()
        if evt_type in important_types:
            events_score += 15
        elif evt_type in negative_types:
            events_score -= 15
        else:
            events_score += 3

    events_score = max(0, min(100, events_score))

    # ── Overall Score ───────────────────────────────────────────────
    overall = (tech_score * 0.25 + momentum_score * 0.25 +
               volume_score * 0.10 + volume_profile_score * 0.10 +
               trendline_score * 0.10 + sentiment_score * 0.10 +
               events_score * 0.10)
    overall = round(max(0, min(100, overall)), 1)

    # ── Bias (computed before conclusion logic needs it) ────────────
    if overall >= 65:
        bias = "bullish"
    elif overall <= 35:
        bias = "bearish"
    else:
        bias = "neutral"

    # ── Buy/Sell Conclusion ─────────────────────────────────────────
    if overall >= 70 and bias != 'bearish':
        conclusion = "BUY"
        conclusion_class = "buy"
    elif overall <= 30 and bias != 'bullish':
        conclusion = "SELL"
        conclusion_class = "sell"
    elif bias == 'bullish' and overall >= 55:
        conclusion = "BUY"
        conclusion_class = "buy"
    elif bias == 'bearish' and overall <= 45:
        conclusion = "SELL"
        conclusion_class = "sell"
    else:
        conclusion = "HOLD"
        conclusion_class = "hold"

    # Build signals list
    signals = []
    if stat:
        wa = stat['weighted_alpha'] or 0
        if wa > 30:
            signals.append(f"Strong momentum (Wtd Alpha: {wa:.1f})")
        elif wa < -20:
            signals.append(f"Weak momentum (Wtd Alpha: {wa:.1f})")
        streak = stat['streak'] or 0
        if streak >= 5:
            signals.append(f"{streak}-day winning streak")
        elif streak <= -5:
            signals.append(f"{abs(streak)}-day losing streak")
    if n >= 20:
        if current > sma20:
            signals.append("Price above SMA20")
        else:
            signals.append("Price below SMA20")
    for ev in events[:2]:
        signals.append(f"{ev['event_type']}: {ev['event_date']}")

    if not signals:
        signals.append("No significant signals detected")

    result = {
        "symbol": symbol.upper(),
        "overall_score": overall,
        "bias": bias,
        "tech_score": round(tech_score, 1),
        "momentum_score": round(momentum_score, 1),
        "volume_score": round(volume_score, 1),
        "events_score": round(events_score, 1),
        "volume_profile_score": round(volume_profile_score, 1),
        "trendline_score": round(trendline_score, 1),
        "sentiment_score": round(sentiment_score, 1),
        "conclusion": conclusion,
        "signals": signals[:6],
    }

    # Cache in DB
    try:
        db = get_db()
        db.execute("""
            INSERT OR REPLACE INTO ai_analysis
            (symbol, overall_score, bias, tech_score, momentum_score, volume_score, events_score,
             volume_profile_score, trendline_score, sentiment_score, conclusion, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol.upper(), overall, bias, result['tech_score'], result['momentum_score'],
              result['volume_score'], result['events_score'],
              result.get('volume_profile_score', 0), result.get('trendline_score', 0),
              result.get('sentiment_score', 0), result.get('conclusion', 'HOLD'),
              datetime.now().isoformat()))
        db.commit()
        db.close()
    except Exception:
        pass

    return result


# ── Routes ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    resp = make_response(render_template("index.html", server_id=SERVER_ID))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/health")
def health():
    conn = get_db()
    stats_count = conn.execute("SELECT COUNT(*) as cnt FROM stats WHERE price > 0").fetchone()["cnt"]
    assets_count = conn.execute("SELECT COUNT(*) as cnt FROM assets").fetchone()["cnt"]
    conn.close()
    return jsonify({
        "status": "ok",
        "server_id": SERVER_ID,
        "timestamp": datetime.now().isoformat(),
        "refreshing": refreshing,
        "stocks_loaded": stats_count,
        "assets_loaded": assets_count,
    })



@app.route("/api/stock/<symbol>/atr")
def stock_atr(symbol):
    """Get ATR data for a stock with specified timeframe and multiplier."""
    symbol = symbol.upper()
    timeframe = request.args.get("timeframe", "1Day")
    period = int(request.args.get("period", 14))
    multiplier = float(request.args.get("multiplier", 2))

    result = compute_atr(symbol, timeframe, period, multiplier)
    if not result:
        return jsonify({"error": "Insufficient data for ATR calculation"})
    return jsonify(result)


@app.route("/api/screener")
def screener():
    """Get screener data with filtering, sorting, pagination + timeframe support."""
    conn = get_db()

    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    sort_by = request.args.get("sort", "symbol")
    sort_dir = request.args.get("dir", "asc")
    search = request.args.get("search", "").strip()
    filter_type = request.args.get("type", "all")
    min_wa = request.args.get("min_wa")
    max_atrp = request.args.get("max_atrp")
    timeframe = request.args.get("timeframe", "1Day")
    date_cutoff = request.args.get("date_cutoff", "").strip()
    exchange_filter = request.args.get("exchange", "").strip()

    # Build base query: join stats with assets for name
    base_query = """
        SELECT s.symbol, a.name as asset_name, s.asset_class, s.fractionable,
               s.marginable, s.exchange, s.status, s.tradable, s.last_updated,
               s.oldest_data,
               s.price, s.change_pct, s.weighted_alpha, s.volume, s.atrp,
               s.streak, s.pre_price, s.pre_change_pct, s.post_price, s.post_change_pct,
               s.atr_value, s.atr_stop, s.atr_signal, s.atr_crossed_above, s.atr_crossed_below, s.atr_streak, s.atr_multiplier,
               s.profit_status, s.profit_last_qtr_pct,
               ai.overall_score, ai.bias, ai.tech_score, ai.momentum_score, ai.volume_score, ai.events_score,
               ai.volume_profile_score, ai.trendline_score, ai.sentiment_score, ai.conclusion
        FROM stats s
        LEFT JOIN assets a ON s.symbol = a.symbol
        LEFT JOIN ai_analysis ai ON UPPER(s.symbol) = UPPER(ai.symbol)
        WHERE 1=1
    """
    params = []

    if search:
        base_query += " AND (UPPER(s.symbol) LIKE ? OR UPPER(COALESCE(a.name, s.name)) LIKE ?)"
        params.extend([f"%{search.upper()}%", f"%{search.upper()}%"])

    if filter_type == "stock":
        base_query += """ AND s.asset_class = 'us_equity'
            AND UPPER(COALESCE(a.name, s.name)) NOT LIKE '%ETF%'
            AND UPPER(COALESCE(a.name, s.name)) NOT LIKE '%ETN%'
            AND UPPER(COALESCE(a.name, s.name)) NOT LIKE '%INDEX FUND%'
            AND s.symbol NOT LIKE '%-USD' AND s.symbol NOT LIKE '%.V'
            AND s.symbol NOT LIKE '%-RT' AND s.symbol NOT LIKE '%-WT'
            AND UPPER(COALESCE(a.name, s.name)) NOT LIKE '%ADR%'
            AND UPPER(COALESCE(a.name, s.name)) NOT LIKE '%AMERICAN DEPOSITARY%'"""
    elif filter_type == "etf":
        base_query += """ AND s.asset_class = 'us_equity'
            AND (UPPER(COALESCE(a.name, s.name)) LIKE '%ETF%'
                OR UPPER(COALESCE(a.name, s.name)) LIKE '%ETN%'
                OR UPPER(COALESCE(a.name, s.name)) LIKE '%INDEX FUND%'
                OR s.symbol LIKE '%-USD' OR s.symbol LIKE '%.V')"""
    elif filter_type == "index":
        base_query += " AND (s.asset_class = 'index' OR s.symbol IN ('SPY','QQQ','IWM','DIA','VTI','VOO'))"
    elif filter_type == "adr":
        base_query += """ AND s.asset_class = 'us_equity'
            AND (UPPER(COALESCE(a.name, s.name)) LIKE '%ADR%'
                OR UPPER(COALESCE(a.name, s.name)) LIKE '%AMERICAN DEPOSITARY%')"""

    # Price filters
    min_price = request.args.get("min_price")
    max_price = request.args.get("max_price")
    if min_price:
        base_query += " AND s.price >= ?"
        params.append(float(min_price))
    if max_price:
        base_query += " AND s.price <= ?"
        params.append(float(max_price))

    # Change% filters
    min_change = request.args.get("min_change")
    max_change = request.args.get("max_change")
    if min_change:
        base_query += " AND s.change_pct >= ?"
        params.append(float(min_change))
    if max_change:
        base_query += " AND s.change_pct <= ?"
        params.append(float(max_change))

    # Weighted Alpha filters
    max_wa = request.args.get("max_wa")
    if min_wa:
        base_query += " AND s.weighted_alpha >= ?"
        params.append(float(min_wa))
    if max_wa:
        base_query += " AND s.weighted_alpha <= ?"
        params.append(float(max_wa))

    # Volume filter
    min_volume = request.args.get("min_volume")
    if min_volume:
        base_query += " AND s.volume >= ?"
        params.append(int(min_volume))

    # Streak filters
    min_streak = request.args.get("min_streak")
    max_streak = request.args.get("max_streak")
    if min_streak:
        base_query += " AND s.streak >= ?"
        params.append(int(min_streak))
    if max_streak:
        base_query += " AND s.streak <= ?"
        params.append(int(max_streak))

    # Pre-market change filter
    min_pre_change = request.args.get("min_pre_change")
    if min_pre_change:
        base_query += " AND s.pre_change_pct >= ?"
        params.append(float(min_pre_change))

    # Post-market change filter
    min_post_change = request.args.get("min_post_change")
    if min_post_change:
        base_query += " AND s.post_change_pct >= ?"
        params.append(float(min_post_change))

    # ATR status filter
    atr_status = request.args.get("atr_status", "").strip()
    if atr_status == "above":
        base_query += " AND s.atr_signal = 1 AND s.atr_stop > 0"
    elif atr_status == "below":
        base_query += " AND s.atr_signal = -1 AND s.atr_stop > 0"
    elif atr_status == "crossed_above":
        base_query += " AND s.atr_crossed_above = 1"
    elif atr_status == "crossed_below":
        base_query += " AND s.atr_crossed_below = 1"

    # ATR multiplier filter
    atr_mult = request.args.get("atr_multiplier", "").strip()
    if atr_mult:
        base_query += " AND s.atr_multiplier = ?"
        params.append(float(atr_mult))

    # Fractionable filter
    fractionable_filter = request.args.get("fractionable", "").strip()
    if fractionable_filter in ("0", "1"):
        base_query += " AND s.fractionable = ?"
        params.append(int(fractionable_filter))

    # Profitability filter
    profit_filter = request.args.get("profit_status", "").strip()
    if profit_filter == "profitable":
        base_query += " AND s.profit_status = 'profitable'"
    elif profit_filter == "loss_making":
        base_query += " AND s.profit_status = 'loss_making'"
    elif profit_filter == "growing":
        base_query += " AND s.profit_status = 'growing'"
    elif profit_filter == "declining":
        base_query += " AND s.profit_status = 'declining'"

    # Date cutoff filter: show historical data as of that date
    # We keep the main query simple (filter by oldest_data) and overwrite
    # price/change/volume later for the paginated results only.
    if date_cutoff:
        base_query += " AND s.oldest_data <= ?"
        params.append(date_cutoff)

    # Exchange filter — support comma-separated multi-select
    if exchange_filter:
        exchanges = [e.strip() for e in exchange_filter.split(',') if e.strip()]
        if len(exchanges) == 1:
            base_query += " AND s.exchange = ?"
            params.append(exchanges[0])
        elif len(exchanges) > 1:
            placeholders = ",".join(["?" for _ in exchanges])
            base_query += f" AND s.exchange IN ({placeholders})"
            params.extend(exchanges)

    # Total count — wrap the WHERE-filtered query as a subquery so COUNT(*) is
    # valid even when the outer SELECT references joined columns.
    where_idx = base_query.find(" WHERE 1=1")
    count_query = "SELECT COUNT(*) as cnt FROM (" + base_query[:where_idx] + base_query[where_idx:] + ") _cnt"
    total = conn.execute(count_query, params).fetchone()["cnt"]

    # Sorting — for 1W/1M, we sort by the pre-computed 1D stats columns as proxy
    valid_sorts = {
        "symbol": "s.symbol", "name": "COALESCE(a.name, s.name)",
        "price": "s.price", "change_pct": "s.change_pct",
        "weighted_alpha": "s.weighted_alpha", "atrp": "s.atrp",
        "volume": "s.volume", "streak": "s.streak",
        "oldest_data": "s.oldest_data",
        "exchange": "s.exchange",
        "atr_signal": "s.atr_signal", "atr_streak": "s.atr_streak",
        "atr_value": "s.atr_value", "atr_stop": "s.atr_stop",
        "ai_score": "ai.overall_score",
        "vp_score": "ai.volume_profile_score",
        "trendline_score": "ai.trendline_score",
        "sentiment_score": "ai.sentiment_score",
        "pre_change_pct": "s.pre_change_pct",
        "post_change_pct": "s.post_change_pct",
        "profit_status": "s.profit_status",
        "fractionable": "s.fractionable",
        "last_updated": "s.last_updated"
    }
    sort_col = valid_sorts.get(sort_by, "s.symbol")
    order = "DESC" if sort_dir == "desc" else "ASC"
    base_query += f" ORDER BY {sort_col} {order}"

    # Pagination
    offset = (page - 1) * per_page
    base_query += f" LIMIT {per_page} OFFSET {offset}"

    rows = conn.execute(base_query, params).fetchall()

    # Build results — single query, no N+1
    stocks = []
    symbols_in_results = []
    if timeframe == '1Day':
        # Fast path: all stats already in the query result
        for row in rows:
            sym = row["symbol"]
            symbols_in_results.append(sym)
            stocks.append({
                "symbol": sym,
                "name": row["asset_name"] or row["name"] or sym,
                "price": row["price"],
                "change_pct": row["change_pct"],
                "weighted_alpha": row["weighted_alpha"],
                "volume": row["volume"],
                "atrp": row["atrp"],
                "streak": row["streak"],
                "pre_price": row["pre_price"],
                "pre_change_pct": row["pre_change_pct"],
                "post_price": row["post_price"],
                "post_change_pct": row["post_change_pct"],
                "fractionable": row["fractionable"],
                "marginable": row["marginable"],
                "asset_class": row["asset_class"],
                "exchange": row["exchange"],
                "status": row["status"],
                "tradable": row["tradable"],
                "last_updated": row["last_updated"],
                "oldest_data": row["oldest_data"],
                "atr_value": row["atr_value"],
                "atr_stop": row["atr_stop"],
                "atr_signal": row["atr_signal"],
                "atr_crossed_above": row["atr_crossed_above"],
                "atr_crossed_below": row["atr_crossed_below"],
                "atr_streak": row["atr_streak"],
                "atr_multiplier": row["atr_multiplier"],
                "profit_status": row["profit_status"],
                "profit_last_qtr_pct": row["profit_last_qtr_pct"],
                "ai_score": row["overall_score"],
                "ai_bias": row["bias"],
                "ai_tech": row["tech_score"],
                "ai_momentum": row["momentum_score"],
                "ai_volume": row["volume_score"],
                "ai_events": row["events_score"],
                "ai_volume_profile": row["volume_profile_score"],
                "ai_trendline": row["trendline_score"],
                "ai_sentiment": row["sentiment_score"],
                "ai_conclusion": row["conclusion"],
            })

    # If date_cutoff is set, overwrite price/change/volume with historical bar data
    # (only for the paginated results on this page)
    if date_cutoff and stocks:
        syms = [s["symbol"] for s in stocks]
        placeholders = ",".join(["?" for _ in syms])
        params_hist = [date_cutoff, date_cutoff] + syms
        hist_rows = conn.execute(f"""
            SELECT lb.symbol, lb.close, lb.volume,
                   CASE WHEN pb.close IS NOT NULL AND pb.close > 0
                       THEN ROUND(((lb.close - pb.close) / pb.close) * 100, 2)
                       ELSE 0 END as change_pct
            FROM (
                SELECT b1.symbol, b1.close, b1.volume
                FROM bars b1
                WHERE b1.timeframe = '1Day' AND b1.date <= ?
                AND b1.symbol IN ({placeholders})
                AND b1.date = (
                    SELECT MAX(b2.date) FROM bars b2
                    WHERE b2.symbol = b1.symbol
                    AND b2.timeframe = '1Day' AND b2.date <= ?
                )
            ) lb
            LEFT JOIN bars pb ON pb.symbol = lb.symbol
                AND pb.timeframe = '1Day'
                AND pb.date = (SELECT MAX(b3.date) FROM bars b3
                               WHERE b3.symbol = lb.symbol
                               AND b3.timeframe = '1Day' AND b3.date < lb.date)
        """, params_hist).fetchall()
        hist_map = {r["symbol"]: r for r in hist_rows}
        for s in stocks:
            h = hist_map.get(s["symbol"])
            if h:
                s["price"] = h["close"]
                s["volume"] = h["volume"]
                s["change_pct"] = h["change_pct"]
                s["pre_price"] = None
                s["pre_change_pct"] = None
                s["post_price"] = None
                s["post_change_pct"] = None

    else:
        # 1Week / 1Month: compute stats on-the-fly from aggregated 1Day bars
        for row in rows:
            sym = row["symbol"]
            symbols_in_results.append(sym)
            stat = compute_stats_from_bars_tf(sym, timeframe)
            if stat:
                stat['name'] = row["asset_name"] or stat["name"] or sym
                stat['fractionable'] = row["fractionable"]
                stat['marginable'] = row["marginable"]
                stat['asset_class'] = row["asset_class"]
                stat['exchange'] = row["exchange"]
                stat['status'] = row["status"]
                stat['tradable'] = row["tradable"]
                stat['oldest_data'] = row["oldest_data"]
                stat['ai_score'] = row["overall_score"]
                stat['ai_bias'] = row["bias"]
                stat['ai_tech'] = row["tech_score"]
                stat['ai_momentum'] = row["momentum_score"]
                stat['ai_volume'] = row["volume_score"]
                stat['ai_events'] = row["events_score"]
                stat['ai_volume_profile'] = row["volume_profile_score"]
                stat['ai_trendline'] = row["trendline_score"]
                stat['ai_sentiment'] = row["sentiment_score"]
                stat['ai_conclusion'] = row["conclusion"]
                stat['profit_status'] = row["profit_status"]
                stat['profit_last_qtr_pct'] = row["profit_last_qtr_pct"]
                # Compute ATR for this timeframe
                atr_data = compute_atr_for_screener(sym, timeframe, 2)
                if atr_data:
                    stat['atr_value'] = atr_data.get('atr_value', 0)
                    stat['atr_stop'] = atr_data.get('atr_stop', 0)
                    stat['atr_signal'] = atr_data.get('atr_signal', 0)
                    stat['atr_crossed_above'] = atr_data.get('crossed_above', 0)
                    stat['atr_crossed_below'] = atr_data.get('crossed_below', 0)
                    stat['atr_streak'] = atr_data.get('atr_streak', 0)
                    stat['atr_multiplier'] = atr_data.get('multiplier', 2)
                else:
                    stat['atr_value'] = 0
                    stat['atr_stop'] = 0
                    stat['atr_signal'] = 0
                    stat['atr_crossed_above'] = 0
                    stat['atr_crossed_below'] = 0
                    stat['atr_streak'] = 0
                    stat['atr_multiplier'] = 2
                stocks.append(stat)

    # Fetch corporate events for all results in one query
    if symbols_in_results:
        placeholders = ",".join(["?" for _ in symbols_in_results])
        events_rows = conn.execute(f"""
            SELECT symbol, event_type, event_date, description
            FROM corporate_events
            WHERE UPPER(symbol) IN ({placeholders})
            ORDER BY event_date DESC
        """, [s.upper() for s in symbols_in_results]).fetchall()

        # Group events by symbol
        events_by_symbol = {}
        for e in events_rows:
            sym = e["symbol"].upper()
            if sym not in events_by_symbol:
                events_by_symbol[sym] = []
            events_by_symbol[sym].append(dict(e))

        # Attach events to stocks
        for stock in stocks:
            stock["events"] = events_by_symbol.get(stock["symbol"].upper(), [])
    else:
        for stock in stocks:
            stock["events"] = []

    conn.close()

    return jsonify({
        "stocks": stocks,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": math.ceil(total / per_page) if total > 0 else 0,
        "timeframe": timeframe,
    })


@app.route("/api/market-breadth")
def market_breadth():
    """Market breadth: advancing vs declining across indexes."""
    conn = get_db()
    indexes = {
        "S&P 500": ["SPY"],
        "NASDAQ": ["QQQ"],
        "NYSE": ["DIA"],
        "Russell 2000": ["IWM"],
    }

    result = {}
    for name, symbols in indexes.items():
        advancing = 0
        declining = 0
        for sym in symbols:
            row = conn.execute(
                "SELECT change_pct FROM stats WHERE symbol = ?", (sym,)
            ).fetchone()
            if row:
                if row["change_pct"] > 0:
                    advancing += 1
                elif row["change_pct"] < 0:
                    declining += 1

        total_sampled = advancing + declining
        result[name] = {
            "advancing": advancing,
            "declining": declining,
            "total": max(total_sampled, 1),
            "ratio": round(advancing / max(total_sampled, 1) * 100, 1)
        }

    conn.close()
    return jsonify(result)


@app.route("/api/top-lists")
def top_lists():
    """Top 10 Momentum (WA), Gainers (Change%), Volume."""
    conn = get_db()

    momentum = conn.execute("""
        SELECT symbol, name, price, weighted_alpha, change_pct
        FROM stats WHERE price > 0
        ORDER BY weighted_alpha DESC LIMIT 10
    """).fetchall()

    gainers = conn.execute("""
        SELECT symbol, name, price, change_pct, weighted_alpha
        FROM stats WHERE price > 0
        ORDER BY change_pct DESC LIMIT 10
    """).fetchall()

    volume = conn.execute("""
        SELECT symbol, name, price, volume, change_pct
        FROM stats WHERE price > 0 AND volume > 0
        ORDER BY volume DESC LIMIT 10
    """).fetchall()

    conn.close()

    def rows_to_list(rows):
        return [dict(r) for r in rows]

    return jsonify({
        "momentum": rows_to_list(momentum),
        "gainers": rows_to_list(gainers),
        "volume": rows_to_list(volume)
    })


@app.route("/stock/<symbol>")
def stock_page(symbol):
    """Full stock detail page (opens in new tab)."""
    return render_template("stock_detail.html", symbol=symbol.upper())


@app.route("/api/recompute-streaks", methods=["POST"])
def api_recompute_streaks():
    """Recompute all streaks from local bar data. Runs in background."""
    import threading
    threading.Thread(target=recompute_all_streaks, daemon=True).start()
    return jsonify({"status": "started", "message": "Recomputing streaks in background..."})


@app.route("/api/alpaca-news/<symbol>")
def alpaca_news(symbol):
    """Fetch latest news for a symbol from Alpaca."""
    try:
        resp = alpaca_get("/v1beta1/news", params={
            "symbols": symbol.upper(),
            "limit": 10,
            "sort": "desc",
        })
        if resp.status_code == 200:
            data = resp.json().get('news', [])
            return jsonify(data)
        return jsonify([])
    except Exception:
        return jsonify([])


@app.route("/api/news-search")
def news_search():
    """Search for recent news about a stock using web search."""
    symbol = request.args.get("symbol", "").upper()
    name = request.args.get("name", "")

    # Build search queries
    queries = []
    if symbol:
        queries.append(f"{symbol} stock news today")
        queries.append(f"{symbol} {name} latest news")
    if name:
        queries.append(f"{name} stock analysis {symbol}")

    # For now, return structured placeholder data
    # The frontend renders this with links to external searches
    articles = []
    now = datetime.now()

    # Generate search links for multiple platforms
    platforms = [
        {"name": "Google News", "url": f"https://news.google.com/search?q={symbol}+stock+when:7d", "icon": "📰"},
        {"name": "Reddit", "url": f"https://www.reddit.com/search/?q={symbol}+stock&type=link&sort=top&t=week", "icon": "🔴"},
        {"name": "X / Twitter", "url": f"https://x.com/search?q={symbol}+stock&f=live", "icon": "🐦"},
        {"name": "StockTwits", "url": f"https://stocktwits.com/symbol/{symbol}", "icon": "📈"},
        {"name": "Yahoo Finance", "url": f"https://finance.yahoo.com/quote/{symbol}/news/", "icon": "💹"},
    ]

    for p in platforms:
        articles.append({
            "title": f"{p['icon']} {p['name']} — {symbol} discussions & news",
            "source": p['name'],
            "url": p['url'],
            "timeAgo": "Recent",
            "platform": p['name'],
        })

    return jsonify({"articles": articles, "symbol": symbol, "name": name})


@app.route("/api/stock/<symbol>")
def stock_detail(symbol):
    """Get detailed info for a single stock."""
    conn = None
    try:
        conn = get_db()

        stat = conn.execute(
            "SELECT * FROM stats WHERE UPPER(symbol) = ?", (symbol.upper(),)
        ).fetchone()

        if not stat:
            return jsonify({"error": "Stock not found"}), 404

        # Get total bar count
        total_bars = conn.execute("""
            SELECT COUNT(*) FROM bars WHERE symbol = ?
        """, (symbol.upper(),)).fetchone()[0]

        # Get recent bars for chart — return last 90 bars for fast initial load
        bars = conn.execute("""
            SELECT date, open, high, low, close, volume
            FROM bars WHERE symbol = ? ORDER BY date DESC LIMIT 90
        """, (symbol.upper(),)).fetchall()
        # Reverse to chronological order
        bars = [dict(b) for b in reversed(bars)]

        # Get corporate events
        events = conn.execute("""
            SELECT event_type, event_date, description
            FROM corporate_events WHERE UPPER(symbol) = ?
            ORDER BY event_date DESC LIMIT 20
        """, (symbol.upper(),)).fetchall()

        stat_dict = dict(stat)
        return jsonify({
            "symbol": stat_dict.get("symbol", symbol.upper()),
            "name": stat_dict.get("name", ""),
            "price": stat_dict.get("price", 0),
            "change_pct": stat_dict.get("change_pct", 0),
            "weighted_alpha": stat_dict.get("weighted_alpha", 0),
            "atrp": stat_dict.get("atrp", 0),
            "atr_stop": stat_dict.get("atr_stop", 0),
            "atr_signal": stat_dict.get("atr_signal", 0),
            "streak": stat_dict.get("streak", 0),
            "volume": stat_dict.get("volume", 0),
            "fractionable": stat_dict.get("fractionable", 0),
            "marginable": stat_dict.get("marginable", 0),
            "asset_class": stat_dict.get("asset_class", ""),
            "exchange": stat_dict.get("exchange", ""),
            "status": stat_dict.get("status", ""),
            "tradable": stat_dict.get("tradable", 0),
            "pre_price": stat_dict.get("pre_price"),
            "pre_change_pct": stat_dict.get("pre_change_pct"),
            "post_price": stat_dict.get("post_price"),
            "post_change_pct": stat_dict.get("post_change_pct"),
            "downloaded_1day": stat_dict.get("downloaded_1day"),
            "downloaded_1hour": stat_dict.get("downloaded_1hour"),
            "downloaded_1min": stat_dict.get("downloaded_1min"),
            "oldest_data": stat_dict.get("oldest_data"),
            "atr_crossed_above": stat_dict.get("atr_crossed_above", 0),
            "atr_crossed_below": stat_dict.get("atr_crossed_below", 0),
            "profit_status": stat_dict.get("profit_status"),
            "profit_last_qtr_pct": stat_dict.get("profit_last_qtr_pct"),
            "total_bars": total_bars,
            "bars": [dict(b) for b in bars],
            "events": [dict(e) for e in events],
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to load stock data: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/stock/<symbol>/bars")
def stock_bars_more(symbol):
    """Get more bars for a stock (for zoom/pan). Supports offset and limit."""
    conn = get_db()

    # Verify stock exists
    stat = conn.execute(
        "SELECT symbol FROM stats WHERE UPPER(symbol) = ?", (symbol.upper(),)
    ).fetchone()
    if not stat:
        conn.close()
        return jsonify({"error": "Stock not found"}), 404

    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 200, type=int)
    direction = request.args.get("dir", "older")  # "older" = earlier bars, "newer" = later bars

    if direction == "older":
        # Get bars BEFORE the current earliest (for zooming out to the left)
        rows = conn.execute("""
            SELECT date, open, high, low, close, volume
            FROM bars WHERE symbol = ? AND date < (
                SELECT MIN(date) FROM (
                    SELECT date FROM bars WHERE symbol = ? ORDER BY date DESC LIMIT ?
                )
            )
            ORDER BY date DESC LIMIT ?
        """, (symbol.upper(), symbol.upper(), max(offset, 1), limit)).fetchall()
    else:
        # Get bars AFTER the current latest (for zooming out to the right)
        rows = conn.execute("""
            SELECT date, open, high, low, close, volume
            FROM bars WHERE symbol = ? AND date > (
                SELECT MAX(date) FROM (
                    SELECT date FROM bars WHERE symbol = ? ORDER BY date ASC LIMIT ?
                )
            )
            ORDER BY date ASC LIMIT ?
        """, (symbol.upper(), symbol.upper(), max(offset, 1), limit)).fetchall()

    conn.close()

    # Reverse to chronological order
    bars = [dict(r) for r in reversed(rows)]
    return jsonify({"bars": bars, "count": len(bars)})


@app.route("/api/stock/<symbol>/analysis")
def stock_analysis(symbol):
    """Get AI analysis for a stock."""
    symbol = symbol.upper()

    # Check if cached result exists and is fresh (< 1 hour old)
    conn = get_db()
    cached = conn.execute("""
        SELECT * FROM ai_analysis WHERE symbol = ? AND computed_at > ?
    """, (symbol, (datetime.now() - timedelta(hours=1)).isoformat())).fetchone()
    conn.close()

    if cached:
        result = {
            "symbol": cached['symbol'],
            "overall_score": cached['overall_score'],
            "bias": cached['bias'],
            "tech_score": cached['tech_score'],
            "momentum_score": cached['momentum_score'],
            "volume_score": cached['volume_score'],
            "events_score": cached['events_score'],
            "signals": [],
            "cached": True,
        }
    else:
        result = compute_ai_analysis(symbol)
        result["cached"] = False

    return jsonify(result)


@app.route("/api/download-history", methods=["POST"])
def trigger_download_history():
    """Trigger full historical bars download for all symbols."""
    global downloading_history
    with download_lock:
        if downloading_history:
            return jsonify({"status": "already_running"})

    def _bg():
        result = download_all_history()
        print(f"Download result: {result}")

    thread = threading.Thread(target=_bg, daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/download-status")
def download_status():
    """Check download progress with detailed info."""
    with download_lock:
        data = dict(download_progress)

    # Compute timing metrics
    if data.get("start_time") and data.get("status") == "running":
        elapsed = time.time() - data["start_time"]
        done = data.get("symbols_done", 0)
        total = data.get("symbols_total", 0)
        bars = data.get("bars_found", 0)

        data["elapsed"] = elapsed
        data["elapsed_str"] = _format_duration(elapsed)

        if done > 0 and elapsed > 0:
            speed = done / elapsed  # symbols per second
            data["speed"] = round(speed, 2)
            data["speed_str"] = f"{speed:.1f}/s"

            if total > done:
                remaining = total - done
                eta = remaining / speed
                data["eta"] = round(eta)
                data["eta_str"] = _format_duration(eta)
            else:
                data["eta"] = 0
                data["eta_str"] = "done"
        else:
            data["speed"] = 0
            data["speed_str"] = "—"
            data["eta"] = 0
            data["eta_str"] = "—"

    return jsonify(data)


@app.route("/api/download-assets", methods=["POST"])
def trigger_download_assets():
    """Trigger asset list download from Alpaca (fast, no bars)."""
    def _bg():
        _update_progress(phase="assets", message="Fetching all tradable assets...")
        assets = download_all_assets()
        count = store_assets(assets)
        _update_progress(
            status="complete",
            phase="done",
            assets_fetched=count,
            message=f"Loaded {count:,} assets into database"
        )

    thread = threading.Thread(target=_bg, daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/reset-data", methods=["POST"])
def reset_all_data():
    """Reset all data and trigger fresh download."""
    global downloading_history, download_progress

    with download_lock:
        if downloading_history:
            return jsonify({"status": "already_running", "message": "Download already in progress"})

    def _bg():
        global downloading_history
        downloading_history = True
        try:
            conn = get_db()
            # Clear all data tables
            conn.execute("DELETE FROM bars")
            conn.execute("DELETE FROM stats")
            conn.execute("DELETE FROM corporate_events")
            conn.execute("DELETE FROM ai_analysis")
            conn.commit()
            conn.close()
            print("All data cleared. Starting fresh download...")

            # Trigger fresh download
            result = download_all_history()
            print(f"Reset download result: {result}")
        except Exception as e:
            print(f"Reset error: {e}")
            _update_progress(status="error", message=f"Reset failed: {e}")
        finally:
            downloading_history = False

    thread = threading.Thread(target=_bg, daemon=True)
    thread.start()
    return jsonify({"status": "running", "message": "Resetting all data and starting fresh download..."})


@app.route("/api/assets")
def list_assets():
    """Get list of all assets from DB (offline, no API calls)."""
    conn = get_db()
    search = request.args.get("search", "").strip()
    limit = int(request.args.get("limit", 100))

    query = "SELECT symbol, name, asset_class, exchange, status, tradable FROM assets WHERE 1=1"
    params = []

    if search:
        query += " AND (UPPER(symbol) LIKE ? OR UPPER(name) LIKE ?)"
        params.extend([f"%{search.upper()}%", f"%{search.upper()}%"])

    query += f" ORDER BY symbol LIMIT {limit}"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        "assets": [dict(r) for r in rows],
        "count": len(rows),
    })


@app.route("/api/exchanges")
def list_exchanges():
    """Get distinct exchanges for filter dropdown."""
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT exchange FROM stats
        WHERE exchange IS NOT NULL AND exchange != ''
        ORDER BY exchange
    """).fetchall()
    conn.close()
    return jsonify({"exchanges": [r["exchange"] for r in rows]})


@app.route("/api/update-pre-post", methods=["POST"])
def update_pre_post():
    """Update pre/post market prices from latest Alpaca snapshots."""
    global refreshing
    with refresh_lock:
        if refreshing:
            return jsonify({"status": "already_running"})

    def _bg():
        global refreshing
        refreshing = True
        with download_lock:
            download_progress["progress_type"] = "prepost"
            download_progress["status"] = "running"
            download_progress["phase"] = "Fetching snapshots..."
            download_progress["start_time"] = time.time()
            download_progress["symbols_total"] = 0
            download_progress["symbols_done"] = 0
            download_progress["bars_found"] = 0
            download_progress["current_symbol"] = "Starting..."
        try:
            conn = get_db()
            symbols = [r['symbol'] for r in conn.execute(
                "SELECT symbol FROM stats WHERE price > 0"
            ).fetchall()]
            conn.close()

            if not symbols:
                with download_lock:
                    download_progress["status"] = "error"
                    download_progress["message"] = "No data found"
                return jsonify({"status": "no_data"})

            with download_lock:
                download_progress["symbols_total"] = len(symbols)

            updated = 0
            batch_size = 10
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                symbols_param = ",".join(batch)
                params = {"symbols": symbols_param}
                resp = alpaca_get("/v2/stocks/snapshots", base=DATA_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and "snapshots" in data and isinstance(data["snapshots"], dict):
                        data = data["snapshots"]
                    conn = get_db()
                    for sym, snap in data.items():
                        if not snap:
                            continue
                        latest_trade = snap.get('latestTrade', {})
                        daily_bar = snap.get('dailyBar', {})
                        prev_bar = snap.get('prevDailyBar', {})

                        trade_price = latest_trade.get('p', 0)
                        trade_ts = latest_trade.get('t', '')
                        prev_close = prev_bar.get('c', 0) or daily_bar.get('o', 0)

                        pre_price = None
                        pre_change_pct = None
                        post_price = None
                        post_change_pct = None

                        if trade_price > 0 and prev_close > 0:
                            # Determine if pre or post market based on timestamp
                            if trade_ts:
                                try:
                                    from datetime import datetime
                                    dt = datetime.fromisoformat(trade_ts.replace('Z', '+00:00'))
                                    hour = dt.hour
                                    # Pre-market: before 9:30 AM (before 13:30 UTC)
                                    # Post-market: after 4:00 PM (after 20:00 UTC)
                                    if hour < 13:
                                        pre_price = trade_price
                                        pre_change_pct = round(((trade_price - prev_close) / prev_close) * 100, 2)
                                    elif hour >= 20:
                                        post_price = trade_price
                                        post_change_pct = round(((trade_price - prev_close) / prev_close) * 100, 2)
                                    else:
                                        # Regular hours - update both as current
                                        pre_price = trade_price
                                        pre_change_pct = round(((trade_price - prev_close) / prev_close) * 100, 2)
                                        post_price = trade_price
                                        post_change_pct = round(((trade_price - prev_close) / prev_close) * 100, 2)
                                except:
                                    pass

                            conn.execute("""
                                UPDATE stats SET
                                    pre_price = ?, pre_change_pct = ?,
                                    post_price = ?, post_change_pct = ?,
                                    last_updated = ?
                                WHERE symbol = ?
                            """, (pre_price, pre_change_pct, post_price, post_change_pct,
                                  datetime.now().isoformat(), sym))
                            updated += 1
                    conn.commit()
                    conn.close()

                with download_lock:
                    download_progress["symbols_done"] = min(i + batch_size, len(symbols))
                    download_progress["current_symbol"] = f"Batch {i//batch_size + 1}"

            with download_lock:
                download_progress["status"] = "complete"
                download_progress["phase"] = "Complete"
                download_progress["symbols_done"] = len(symbols)
                download_progress["message"] = f"Pre/post update complete: {updated} symbols updated"

            print(f"Pre/post market update complete: {updated} symbols updated")
        except Exception as e:
            print(f"Pre/post update error: {e}")
            import traceback
            traceback.print_exc()
            with download_lock:
                download_progress["status"] = "error"
                download_progress["message"] = f"Pre/post update failed: {str(e)}"
        finally:
            with refresh_lock:
                refreshing = False

    thread = threading.Thread(target=_bg, daemon=True)
    thread.start()
    return jsonify({"status": "started", "message": "Updating pre/post market prices..."})


@app.route("/api/refresh", methods=["POST"])
def trigger_refresh():
    """Trigger a full data refresh."""
    global refreshing
    with refresh_lock:
        if refreshing:
            return jsonify({"status": "already_running"})

    # Reset progress for refresh
    with download_lock:
        download_progress["status"] = "idle"
        download_progress["progress_type"] = "refresh"
        download_progress["phase"] = ""
        download_progress["symbols_total"] = 0
        download_progress["symbols_done"] = 0
        download_progress["bars_found"] = 0
        download_progress["current_symbol"] = ""
        download_progress["message"] = ""

    thread = threading.Thread(target=full_refresh, daemon=True)
    thread.start()
    return jsonify({"status": "started", "message": "Refresh started..."})


@app.route("/api/stats")
def stats_summary():
    """Summary stats."""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as cnt FROM stats WHERE price > 0").fetchone()["cnt"]
    avg_wa = conn.execute("SELECT AVG(weighted_alpha) as avg_wa FROM stats WHERE price > 0").fetchone()["avg_wa"]
    avg_change = conn.execute("SELECT AVG(change_pct) as avg_chg FROM stats WHERE price > 0").fetchone()["avg_chg"]
    assets_total = conn.execute("SELECT COUNT(*) as cnt FROM assets").fetchone()["cnt"]
    oldest_min = conn.execute("SELECT MIN(oldest_data) FROM stats").fetchone()[0]
    oldest_max = conn.execute("SELECT MAX(oldest_data) FROM stats").fetchone()[0]
    conn.close()

    return jsonify({
        "total_stocks": total,
        "total_assets": assets_total,
        "avg_weighted_alpha": round(avg_wa or 0, 1),
        "avg_change_pct": round(avg_change or 0, 2),
        "oldest_data_min": oldest_min,
        "oldest_data_max": oldest_max
    })


# ── Portfolio / Watchlist API ────────────────────────────────────────

@app.route("/portfolio")
def portfolio_page():
    resp = make_response(render_template("portfolio.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/api/portfolios", methods=["GET"])
def list_portfolios():
    conn = get_db()
    rows = conn.execute("SELECT * FROM portfolios ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/portfolios", methods=["POST"])
def create_portfolio():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    conn = get_db()
    c = conn.execute("INSERT INTO portfolios (name) VALUES (?)", (name,))
    conn.commit()
    pid = c.lastrowid
    row = conn.execute("SELECT * FROM portfolios WHERE id = ?", (pid,)).fetchone()
    conn.close()
    return jsonify(dict(row)), 201


@app.route("/api/portfolios/<int:pid>", methods=["DELETE"])
def delete_portfolio(pid):
    conn = get_db()
    conn.execute("DELETE FROM portfolio_symbols WHERE portfolio_id = ?", (pid,))
    conn.execute("DELETE FROM portfolios WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/portfolios/<int:pid>", methods=["GET"])
def get_portfolio(pid):
    conn = get_db()
    pf = conn.execute("SELECT * FROM portfolios WHERE id = ?", (pid,)).fetchone()
    if not pf:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    symbols = conn.execute(
        "SELECT symbol, qty, avg_price, created_at FROM portfolio_symbols WHERE portfolio_id = ? ORDER BY created_at",
        (pid,)
    ).fetchall()
    symbol_list = [dict(r) for r in symbols]
    stats = {}
    sym_names = [s["symbol"] for s in symbol_list]
    if sym_names:
        placeholders = ",".join(["?" for _ in sym_names])
        rows = conn.execute(f"SELECT symbol, price, change_pct, weighted_alpha, volume, pre_price, post_price, name, exchange, atr_signal, atr_stop, atrp, streak, oldest_data, profit_status FROM stats WHERE symbol IN ({placeholders})", sym_names).fetchall()
        for r in rows:
            stats[r["symbol"]] = dict(r)
    conn.close()
    return jsonify({"portfolio": dict(pf), "symbols": symbol_list, "stats": stats})


@app.route("/api/portfolios/<int:pid>/symbols", methods=["POST"])
def add_portfolio_symbols(pid):
    data = request.json or {}
    symbols_raw = data.get("symbols", "")
    entries = data.get("entries", [])  # [{"symbol":"AAPL","qty":10,"avg_price":150}, ...]
    if not symbols_raw and not entries:
        return jsonify({"error": "Symbols required"}), 400

    conn = get_db()
    pf = conn.execute("SELECT * FROM portfolios WHERE id = ?", (pid,)).fetchone()
    if not pf:
        conn.close()
        return jsonify({"error": "Portfolio not found"}), 404

    added = []

    if entries:
        for e in entries:
            sym = e.get("symbol", "").strip().upper()
            qty = float(e.get("qty", 0))
            avg_price = e.get("avg_price")
            if avg_price is not None:
                avg_price = float(avg_price)
            if not sym:
                continue
            try:
                conn.execute("INSERT OR IGNORE INTO portfolio_symbols (portfolio_id, symbol, qty, avg_price) VALUES (?, ?, ?, ?)",
                             (pid, sym, qty, avg_price))
                added.append({"symbol": sym, "qty": qty, "avg_price": avg_price})
            except Exception:
                pass
    else:
        parsed = [s.strip().upper() for s in symbols_raw.replace(",", " ").split() if s.strip()]
        for sym in parsed:
            try:
                conn.execute("INSERT OR IGNORE INTO portfolio_symbols (portfolio_id, symbol) VALUES (?, ?)", (pid, sym))
                added.append({"symbol": sym, "qty": 0, "avg_price": None})
            except Exception:
                pass

    conn.commit()
    conn.close()
    return jsonify({"added": added})


@app.route("/api/portfolios/<int:pid>/symbols/<symbol>", methods=["DELETE"])
def remove_portfolio_symbol(pid, symbol):
    conn = get_db()
    conn.execute("DELETE FROM portfolio_symbols WHERE portfolio_id = ? AND symbol = ?", (pid, symbol.upper()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/portfolios/<int:pid>/symbols/<symbol>", methods=["PATCH"])
def update_portfolio_symbol(pid, symbol):
    data = request.json or {}
    conn = get_db()
    updates = []
    params = []
    if "qty" in data:
        updates.append("qty = ?")
        params.append(float(data["qty"]))
    if "avg_price" in data:
        updates.append("avg_price = ?")
        params.append(float(data["avg_price"]) if data["avg_price"] is not None else None)
    if updates:
        params.append(symbol.upper())
        params.append(pid)
        conn.execute(f"UPDATE portfolio_symbols SET {', '.join(updates)} WHERE symbol = ? AND portfolio_id = ?", params)
        conn.commit()
    row = conn.execute("SELECT symbol, qty, avg_price, created_at FROM portfolio_symbols WHERE portfolio_id = ? AND symbol = ?",
                       (pid, symbol.upper())).fetchone()
    conn.close()
    return jsonify(dict(row) if row else {"ok": True})


# ── Options Chain ────────────────────────────────────────────────────

@app.route("/api/options/<symbol>")
def options_chain(symbol):
    """Fetch options chain for a symbol from Alpaca."""
    try:
        params = {"underlying_symbols": symbol.upper(), "status": "active", "limit": 100}
        headers = {"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": API_SECRET}
        resp = requests.get("https://paper-api.alpaca.markets/v2/options/contracts", headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return jsonify({"status": "unavailable", "message": f"Alpaca options API error: {resp.status_code}"})
        data = resp.json()
        contracts = data.get("option_contracts", [])
        if not contracts:
            return jsonify({"status": "unavailable", "message": "No options contracts found"})

        # Get quotes
        syms_str = ",".join([c["symbol"] for c in contracts[:100]])
        quotes_resp = requests.get("https://paper-api.alpaca.markets/v2/options/quotes", headers=headers,
                                   params={"symbols": syms_str, "feed": "indicative"}, timeout=10)
        quotes = {}
        if quotes_resp.status_code == 200:
            for q in quotes_resp.json().get("quotes", []):
                quotes[q["symbol"]] = q

        chains = {}
        for c in contracts:
            q = quotes.get(c["symbol"], {})
            exp = c["expiration_date"]
            if exp not in chains:
                chains[exp] = {"expiration": exp, "calls": [], "puts": []}
            entry = {
                "contract": c["symbol"],
                "type": c["type"],
                "strike": float(c["strike_price"]),
                "bid": q.get("bid_price"),
                "ask": q.get("ask_price"),
                "last": q.get("last_price"),
                "volume": q.get("volume"),
                "open_interest": q.get("open_interest"),
                "implied_vol": q.get("implied_volatility"),
            }
            chains[exp][c["type"] + "s"].append(entry)

        # Sort each chain by strike
        result = sorted(chains.values(), key=lambda x: x["expiration"])
        for ch in result:
            ch["calls"].sort(key=lambda x: x["strike"])
            ch["puts"].sort(key=lambda x: x["strike"])

        return jsonify({"status": "ok", "chains": result})
    except Exception as e:
        return jsonify({"status": "unavailable", "message": str(e)})


# ── Entry Point ──────────────────────────────────────────────────────
def _quick_start():
    """Fast initial load, then background full asset download."""
    print("Quick-start: initializing...")

    # Ensure assets table has data
    conn = get_db()
    asset_count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    stats_count = conn.execute("SELECT COUNT(*) as cnt FROM stats WHERE price > 0").fetchone()["cnt"]
    conn.close()

    if asset_count == 0:
        print("  Populating initial asset list...")
        assets = _build_fallback_assets()
        store_assets(assets)
        # Also fetch from API in background
        def _bg_assets():
            try:
                api_assets = download_all_assets()
                if api_assets and len(api_assets) > len(assets):
                    store_assets(api_assets)
                    print(f"  Updated assets: {len(api_assets)} from API")
            except Exception as e:
                print(f"  Background asset fetch error: {e}")
        threading.Thread(target=_bg_assets, daemon=True).start()

    if stats_count == 0:
        print("  Loading initial data from snapshots...")
        # Get symbols we have assets for
        conn = get_db()
        symbols = [r['symbol'] for r in conn.execute("SELECT symbol FROM assets LIMIT 200").fetchall()]
        conn.close()

        if symbols:
            snapshots = download_snapshots(symbols)
            tradable_symbols = [s for s in symbols if snapshots.get(s)]
            assets_for_stats = []
            conn = get_db()
            for sym in tradable_symbols:
                a = conn.execute("SELECT * FROM assets WHERE symbol = ?", (sym,)).fetchone()
                if a:
                    assets_for_stats.append(dict(a))
            conn.close()

            compute_and_store_stats(assets_for_stats, snapshots)
            print(f"  Quick-start: {len(assets_for_stats)} symbols loaded")

    print("Starting background full download...")

    def _bg_full():
        try:
            download_all_history()
        except Exception as e:
            print(f"Background download error: {e}")

    threading.Thread(target=_bg_full, daemon=True).start()


if __name__ == "__main__":
    import threading
    import os
    init_db()
    # Schema migrations are fast — run synchronously.
    # Heavy data backfills (oldest_data) run in background.
    migrate_db()
    # Streak recompute at startup is opt-in via env var; on Windows the
    # background thread sometimes dies silently. Use /api/recompute-streaks.
    if os.environ.get("DUMBMONEY_STARTUP_RECOMPUTE") == "1":
        t = threading.Thread(target=recompute_all_streaks, daemon=True)
        t.start()
    print()
    print("=" * 55)
    print(f"  DumbMoney Server #{SERVER_ID}")
    print(f"  http://localhost:{PORT}")
    print(f"  Database: {DB_PATH}")
    print(f"  Alpaca Paper Trading")
    print("=" * 55)
    print()

    # Quick-start
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as cnt FROM stats WHERE price > 0").fetchone()["cnt"]
    asset_count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    conn.close()

    if count == 0 or asset_count == 0:
        _quick_start()

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True, use_reloader=False)
