import sqlite3
import os
import numpy as np

INTRADAY_DB = os.path.join(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt', 'intraday_backtest.db')

def get_db():
    conn = sqlite3.connect(INTRADAY_DB, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-2000000")
    conn.row_factory = sqlite3.Row
    return conn

def get_universe(min_vol=500000):
    conn = get_db()
    rows = conn.execute(
        "SELECT symbol, avg_volume FROM symbols WHERE avg_volume > ? ORDER BY avg_volume DESC",
        (min_vol,)
    ).fetchall()
    conn.close()
    print(f"  Universe: {len(rows)} stocks with vol>{min_vol/1e6:.1f}M")
    return [r[0] for r in rows]

def load_bars(symbols, timeframe, limit=None):
    conn = get_db()
    all_bars = {}
    for sym in symbols:
        if limit:
            rows = conn.execute(
                "SELECT timestamp, open, high, low, close, volume FROM bars WHERE symbol=? AND timeframe=? ORDER BY timestamp DESC LIMIT ?",
                (sym, timeframe, limit)
            ).fetchall()
            rows = rows[::-1]
        else:
            rows = conn.execute(
                "SELECT timestamp, open, high, low, close, volume FROM bars WHERE symbol=? AND timeframe=? ORDER BY timestamp",
                (sym, timeframe)
            ).fetchall()
        if len(rows) >= 20:
            all_bars[sym] = [{'t': r[0], 'o': r[1], 'h': r[2], 'l': r[3], 'c': r[4], 'v': r[5]} for r in rows]
    conn.close()
    return all_bars

def get_bar_count(timeframe):
    conn = get_db()
    r = conn.execute("SELECT COUNT(*), COUNT(DISTINCT symbol) FROM bars WHERE timeframe=?", (timeframe,)).fetchone()
    conn.close()
    return r[0], r[1]

def get_date_range(timeframe):
    conn = get_db()
    r = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM bars WHERE timeframe=?", (timeframe,)).fetchone()
    conn.close()
    return r[0], r[1]
