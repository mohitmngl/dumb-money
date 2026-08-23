import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "intraday_backtest.db")

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "PKUPBR7N6SS6NQUJ4U24NO7GEO")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "BFGrUckWUymMRYVe9kkrz1V2zVLXeoxBU7Kr5K54Cfsq")
ALPACA_DATA_URL = "https://data.alpaca.markets"

TIMEFRAMES = ["1Min", "5Min", "15Min", "30Min", "1Hour", "1Day"]
TIMEFRAME_LABELS = {
    "1Min": "1 Minute",
    "5Min": "5 Minutes",
    "15Min": "15 Minutes",
    "30Min": "30 Minutes",
    "1Hour": "1 Hour",
    "1Day": "Daily",
}
# Maximum days back per timeframe (Alpaca limits)
MAX_DAYS_BACK = {
    "1Min": 28,
    "5Min": 3650,
    "15Min": 3650,
    "30Min": 3650,
    "1Hour": 3650,
    "1Day": 3650,
}

# Strategy defaults
DEFAULT_N_STOCKS = 200
DEFAULT_N_BATCHES = 1_000_000
DEFAULT_CAPITAL = 10000.0
DEFAULT_TIMEFRAME = "15Min"

# Weighted Alpha parameters (from repo spec, exact values)
WA_SMOOTH_WINDOW = 26
WA_LOOKBACK = 250
WA_L_CAP = -0.002839470936396615
WA_U_CAP = 0.0015636274286274306
WA_TOTAL_CANDLES = WA_SMOOTH_WINDOW + WA_LOOKBACK  # 276

# Accel Peak Signal windows
ACCEL_S4 = 4
ACCEL_S8 = 8
ACCEL_S16 = 16
ACCEL_B3 = 3
ACCEL_B7 = 7
ACCEL_B15 = 15
ACCEL_LATEST_CANDLES = 20

# US market hours (ET)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MIN = 0


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bars (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume INTEGER,
            PRIMARY KEY (symbol, timeframe, timestamp)
        );
        CREATE TABLE IF NOT EXISTS symbols (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            exchange TEXT,
            asset_class TEXT,
            marginable INTEGER DEFAULT 0,
            shortable INTEGER DEFAULT 0,
            fractionable INTEGER DEFAULT 0,
            avg_volume REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            timeframe TEXT,
            n_stocks INTEGER,
            n_batches INTEGER,
            capital REAL,
            margin INTEGER DEFAULT 1,
            charges INTEGER DEFAULT 0,
            days_back INTEGER DEFAULT 60,
            status TEXT DEFAULT 'pending',
            progress REAL DEFAULT 0,
            result_json TEXT,
            equity_json TEXT,
            metrics_json TEXT
        );
        CREATE TABLE IF NOT EXISTS saved_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timeframe TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            n_stocks INTEGER,
            n_batches INTEGER,
            capital REAL,
            margin INTEGER,
            charges INTEGER,
            days_back INTEGER,
            candles_processed INTEGER,
            total_return_pct REAL,
            sharpe_ratio REAL,
            max_drawdown_pct REAL,
            win_rate_pct REAL,
            profit_factor REAL,
            n_signals_avg REAL,
            result_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_bars_tf ON bars(timeframe, symbol);
        CREATE TABLE IF NOT EXISTS download_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT DEFAULT (datetime('now')),
            timeframe TEXT,
            total_symbols INTEGER DEFAULT 0,
            downloaded INTEGER DEFAULT 0,
            total_bars INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            error TEXT
        );
    """)
    conn.close()
