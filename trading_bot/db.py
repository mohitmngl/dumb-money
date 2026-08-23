import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'trading_bot.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL DEFAULT 'long',
            entry_price REAL NOT NULL,
            stop_price REAL NOT NULL,
            target_price REAL NOT NULL,
            qty REAL NOT NULL,
            notional REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            order_id TEXT,
            entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            exit_price REAL,
            exit_time TIMESTAMP,
            exit_reason TEXT,
            pnl REAL
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            qty REAL NOT NULL,
            notional REAL NOT NULL,
            stop_price REAL NOT NULL,
            target_price REAL NOT NULL,
            entry_time TIMESTAMP NOT NULL,
            exit_time TIMESTAMP,
            exit_reason TEXT,
            pnl REAL,
            duration_sec REAL
        );

        CREATE TABLE IF NOT EXISTS stock_universe (
            symbol TEXT PRIMARY KEY,
            avg_daily_volume REAL,
            last_refreshed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_pos_status ON positions(status);
        CREATE INDEX IF NOT EXISTS idx_pos_symbol ON positions(symbol);
        CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
    """)
    conn.commit()
    conn.close()

def open_position(symbol, entry_price, stop_price, target_price, qty, notional, order_id=None):
    conn = get_db()
    conn.execute("""
        INSERT INTO positions (symbol, side, entry_price, stop_price, target_price, qty, notional, order_id)
        VALUES (?, 'long', ?, ?, ?, ?, ?, ?)
    """, (symbol, entry_price, stop_price, target_price, qty, notional, order_id))
    conn.commit()
    conn.close()

def close_position(position_id, exit_price, exit_reason, pnl):
    conn = get_db()
    row = conn.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
    if not row:
        conn.close()
        return
    conn.execute("""
        UPDATE positions SET status='closed', exit_price=?, exit_time=CURRENT_TIMESTAMP,
        exit_reason=?, pnl=? WHERE id=?
    """, (exit_price, exit_reason, pnl, position_id))
    duration = 0
    if row['entry_time']:
        from datetime import datetime
        try:
            et = datetime.fromisoformat(row['entry_time'])
            duration = (datetime.now() - et).total_seconds()
        except:
            pass
    conn.execute("""
        INSERT INTO trades (symbol, side, entry_price, exit_price, qty, notional,
        stop_price, target_price, entry_time, exit_time, exit_reason, pnl, duration_sec)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
    """, (row['symbol'], row['side'], row['entry_price'], exit_price, row['qty'],
          row['notional'], row['stop_price'], row['target_price'], row['entry_time'],
          exit_reason, pnl, duration))
    conn.commit()
    conn.close()

def get_open_positions():
    conn = get_db()
    rows = conn.execute("SELECT * FROM positions WHERE status='open'").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_open_count():
    conn = get_db()
    r = conn.execute("SELECT COUNT(*) as c FROM positions WHERE status='open'").fetchone()
    conn.close()
    return r['c']

def get_trades(limit=50):
    conn = get_db()
    rows = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_universe(symbols_with_volume):
    conn = get_db()
    conn.execute("DELETE FROM stock_universe")
    conn.executemany(
        "INSERT OR REPLACE INTO stock_universe (symbol, avg_daily_volume) VALUES (?, ?)",
        symbols_with_volume
    )
    conn.commit()
    conn.close()

def get_universe():
    conn = get_db()
    rows = conn.execute("SELECT symbol, avg_daily_volume FROM stock_universe ORDER BY avg_daily_volume DESC").fetchall()
    conn.close()
    return [(r['symbol'], r['avg_daily_volume']) for r in rows]

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, str(value)))
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = get_db()
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return r['value'] if r else default
