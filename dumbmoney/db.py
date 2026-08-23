import sqlite3
import os
from dumbmoney.config import US_DB, INDIA_DB, CRYPTO_DB

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bars (
  symbol TEXT, timeframe TEXT, date TEXT,
  open REAL, high REAL, low REAL, close REAL, volume INTEGER,
  PRIMARY KEY (symbol, timeframe, date));

CREATE TABLE IF NOT EXISTS stats (
  symbol TEXT PRIMARY KEY, name TEXT, price REAL, volume INTEGER, change_pct REAL,
  atrp REAL DEFAULT 0, weighted_alpha REAL DEFAULT 0,
  atr_signal INTEGER DEFAULT 0, atr_stop REAL, atr_value REAL, atr_streak INTEGER DEFAULT 0,
  atr_crossed_above INTEGER DEFAULT 0, atr_crossed_below INTEGER DEFAULT 0, atr_multiplier REAL DEFAULT 1.0,
  streak INTEGER DEFAULT 0,
  next_day_return REAL, prob_up_1d REAL, prob_up_5d REAL, prob_up_st_cross REAL DEFAULT 50,
  pre_price REAL, pre_change_pct REAL, post_price REAL, post_change_pct REAL,
  profit_status TEXT, profit_last_qtr_pct REAL, profit_millions REAL,
  profit_expectations TEXT, profit_post_result_dir TEXT,
  fractionable BOOLEAN DEFAULT 0, marginable BOOLEAN DEFAULT 0,
  asset_class TEXT, exchange TEXT, status TEXT, tradable BOOLEAN DEFAULT 0,
  pattern_name TEXT, pattern_prob REAL,
  last_updated TEXT, oldest_data TEXT,
  downloaded_1day TEXT, downloaded_1hour TEXT, downloaded_1min TEXT,
  accel_a REAL DEFAULT 0, accel_base REAL DEFAULT 0, accel_signal INTEGER DEFAULT 0,
  accel_crossed_up INTEGER DEFAULT 0, accel_crossed_down INTEGER DEFAULT 0, accel_streak INTEGER DEFAULT 0,
  confluence REAL DEFAULT 0,
  st_bars_below INTEGER DEFAULT 0, st_bars_above INTEGER DEFAULT 0,
  accel_bars_below INTEGER DEFAULT 0, accel_bars_above INTEGER DEFAULT 0,
  r_squared REAL DEFAULT 0,
  old_swing_retest_score REAL);

CREATE TABLE IF NOT EXISTS ipos (
  symbol TEXT PRIMARY KEY, first_seen TEXT, first_bar TEXT);

CREATE TABLE IF NOT EXISTS assets (
  symbol TEXT PRIMARY KEY, name TEXT, asset_class TEXT, exchange TEXT,
  status TEXT, tradable BOOLEAN, fractionable BOOLEAN, marginable BOOLEAN,
  shortable INTEGER DEFAULT 0, margin_requirement_long TEXT, margin_requirement_short TEXT,
  last_updated TEXT);

CREATE TABLE IF NOT EXISTS ai_analysis (
  symbol TEXT PRIMARY KEY, overall_score REAL DEFAULT 0,
  bias TEXT DEFAULT 'neutral', tech_score REAL DEFAULT 0, momentum_score REAL DEFAULT 0,
  volume_score REAL DEFAULT 0, events_score REAL DEFAULT 0, volume_profile_score REAL DEFAULT 0,
  trendline_score REAL DEFAULT 0, sentiment_score REAL DEFAULT 0, conclusion TEXT DEFAULT 'HOLD',
  ai_matrix TEXT DEFAULT '', computed_at TEXT);

CREATE TABLE IF NOT EXISTS corporate_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT,
  event_type TEXT, event_date TEXT, description TEXT);

CREATE TABLE IF NOT EXISTS historical_screener (
  symbol TEXT, date TEXT, price REAL, change_pct REAL, volume INTEGER,
  weighted_alpha REAL, atrp REAL, streak INTEGER, atr_value REAL, atr_stop REAL, atr_signal INTEGER,
  atr_crossed_above INTEGER, atr_crossed_below INTEGER, atr_streak INTEGER, atr_multiplier REAL,
  ai_overall_score REAL, ai_bias TEXT, ai_tech_score REAL, ai_momentum_score REAL, ai_volume_score REAL,
  ai_events_score REAL, ai_volume_profile_score REAL, ai_trendline_score REAL, ai_sentiment_score REAL,
  ai_conclusion TEXT, ai_matrix TEXT DEFAULT '', next_day_return REAL, next_5d_return REAL, prob_up_1d REAL, prob_up_5d REAL,
  accel_a REAL, accel_base REAL, accel_signal INTEGER, accel_crossed_up INTEGER, accel_crossed_down INTEGER,
  confluence REAL DEFAULT 0,
  st_bars_below INTEGER DEFAULT 0, st_bars_above INTEGER DEFAULT 0,
  accel_bars_below INTEGER DEFAULT 0, accel_bars_above INTEGER DEFAULT 0,
  r_squared REAL DEFAULT 0,
  old_swing_retest_score REAL,
  PRIMARY KEY (symbol, date));

CREATE TABLE IF NOT EXISTS portfolios (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS portfolio_symbols (
  id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id INTEGER NOT NULL,
  symbol TEXT NOT NULL COLLATE NOCASE, qty REAL DEFAULT 0, avg_price REAL,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
  UNIQUE(portfolio_id, symbol));
CREATE TABLE IF NOT EXISTS portfolio_groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS portfolio_group_members (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id INTEGER NOT NULL REFERENCES portfolio_groups(id) ON DELETE CASCADE,
  portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
  UNIQUE(group_id, portfolio_id));

CREATE TABLE IF NOT EXISTS portfolio_strings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  portfolio_id INTEGER NOT NULL,
  name TEXT,
  entry_date TEXT NOT NULL,
  entry_price REAL,
  exit_date TEXT,
  exit_price REAL,
  status TEXT DEFAULT 'running',
  fractional INTEGER DEFAULT 0,
  realised_pnl REAL,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS portfolio_string_symbols (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  portfolio_string_id INTEGER NOT NULL,
  symbol TEXT NOT NULL COLLATE NOCASE,
  qty REAL DEFAULT 0,
  weight REAL DEFAULT 1.0,
  fractional_allowed INTEGER DEFAULT 0,
  FOREIGN KEY(portfolio_string_id) REFERENCES portfolio_strings(id) ON DELETE CASCADE,
  UNIQUE(portfolio_string_id, symbol)
);

CREATE TABLE IF NOT EXISTS strings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id INTEGER, name TEXT,
  raw_string TEXT, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS string_symbols (
  id INTEGER PRIMARY KEY AUTOINCREMENT, string_id INTEGER, symbol TEXT, weight REAL DEFAULT 1.0);

CREATE TABLE IF NOT EXISTS ss_strategies (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, strategy_type TEXT NOT NULL,
  filter_json TEXT NOT NULL, sort_field TEXT NOT NULL, sort_dir TEXT DEFAULT 'desc', top_n INTEGER DEFAULT 10,
  st_period INTEGER DEFAULT 14, st_multiplier REAL DEFAULT 1.0, total_entries INTEGER DEFAULT 0,
  win_rate REAL, avg_1d_return REAL, median_1d_return REAL, std_1d_return REAL, max_1d_gain REAL, max_1d_loss REAL,
  max_consecutive_wins INTEGER, max_consecutive_losses INTEGER, sharpe_1d REAL,
  prob_up_1d REAL, prob_up_1pct REAL, prob_up_2pct REAL, prob_down_2pct REAL,
  prob_up_after_st_cross REAL, prob_up_after_wa_high REAL,
  current_date TEXT, current_count INTEGER DEFAULT 0, current_symbols TEXT, current_value REAL,
  current_st_signal INTEGER, current_st_crossed INTEGER, current_avg_wa REAL, is_random INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS ss_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER NOT NULL REFERENCES ss_strategies(id) ON DELETE CASCADE,
  date TEXT, symbols TEXT, basket_value REAL, next_day_return REAL, st_signal INTEGER, avg_wa REAL);
CREATE TABLE IF NOT EXISTS ss_backtest_status (
  id INTEGER PRIMARY KEY CHECK (id=1), status TEXT, phase TEXT, progress TEXT, message TEXT, updated_at REAL);

CREATE TABLE IF NOT EXISTS ai_discovered_portfolios (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, rules TEXT NOT NULL,
  score REAL DEFAULT 0, win_rate REAL DEFAULT 0, avg_return REAL DEFAULT 0, total_batches INTEGER DEFAULT 0,
  created_at TEXT, last_updated TEXT);
CREATE TABLE IF NOT EXISTS ai_discovered_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id INTEGER NOT NULL,
  batch_date TEXT NOT NULL, symbols TEXT NOT NULL, avg_return_7d REAL, avg_return_14d REAL, avg_return_30d REAL,
  FOREIGN KEY(portfolio_id) REFERENCES ai_discovered_portfolios(id));

CREATE TABLE IF NOT EXISTS rule_portfolios (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, category TEXT,
  filter_rules TEXT, sort_method TEXT, top_n INTEGER DEFAULT 10, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS rule_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id INTEGER, batch_date TEXT,
  symbols TEXT, basket_value REAL, next_day_return REAL);
CREATE TABLE IF NOT EXISTS rule_portfolio_stats (
  portfolio_id INTEGER PRIMARY KEY, win_rate REAL, avg_return REAL,
  sharpe REAL, total_batches INTEGER, prob_up_1d REAL, updated_at TEXT);

CREATE TABLE IF NOT EXISTS paper_strategies (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, rules TEXT NOT NULL,
  num_stocks INTEGER DEFAULT 10, allocation_type TEXT DEFAULT 'equal', active INTEGER DEFAULT 1,
  rebalance_time TEXT DEFAULT '09:35', created_at TEXT DEFAULT (datetime('now')), last_rebalanced TEXT);
CREATE TABLE IF NOT EXISTS paper_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER REFERENCES paper_strategies(id),
  symbol TEXT NOT NULL, side TEXT NOT NULL, qty REAL NOT NULL, price REAL, filled_at TEXT, alpaca_order_id TEXT);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS signal_prob_matrix (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  st_state TEXT, accel_state TEXT, wa_bucket TEXT,
  prob_up_1d REAL, prob_up_1pct REAL, prob_up_2pct REAL, prob_down_2pct REAL,
  sample_count INTEGER, avg_next_day_return REAL, sharpe REAL,
  UNIQUE(st_state, accel_state, wa_bucket));

CREATE TABLE IF NOT EXISTS string_universe (
  string_id TEXT PRIMARY KEY, market TEXT, num_stocks INTEGER DEFAULT 0,
  expression TEXT, created_at TEXT DEFAULT (datetime('now')), active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS string_constituents (
  string_id TEXT, symbol TEXT, weight REAL DEFAULT 1.0,
  PRIMARY KEY (string_id, symbol));
CREATE TABLE IF NOT EXISTS string_screener_metrics (
  string_id TEXT PRIMARY KEY, market TEXT,
  name TEXT, exchange TEXT, asset_class TEXT,
  price REAL, change_pct REAL, volume REAL, weighted_alpha REAL,
  atrp REAL, streak INTEGER, atr_signal INTEGER, atr_stop REAL, atr_value REAL, atr_streak INTEGER,
  atr_crossed_above INTEGER, atr_crossed_below INTEGER, atr_multiplier REAL,
  next_day_return REAL, next_5d_return REAL, prob_up_1d REAL, prob_up_5d REAL,
  pre_price REAL, pre_change_pct REAL, post_price REAL, post_change_pct REAL,
  profit_status TEXT, fractionable BOOLEAN DEFAULT 0, marginable BOOLEAN DEFAULT 0,
  accel_a REAL, accel_base REAL, accel_signal INTEGER, accel_crossed_up INTEGER, accel_crossed_down INTEGER, accel_streak INTEGER,
  confluence REAL DEFAULT 0, ai_overall_score REAL, ai_bias TEXT, ai_tech_score REAL,
  ai_momentum_score REAL, ai_volume_score REAL, ai_events_score REAL,
  ai_volume_profile_score REAL, ai_trendline_score REAL, ai_sentiment_score REAL,
  ai_conclusion TEXT, ai_matrix TEXT DEFAULT '', updated_at TEXT,
   st_bars_below INTEGER DEFAULT 0, st_bars_above INTEGER DEFAULT 0,
   accel_bars_below INTEGER DEFAULT 0, accel_bars_above INTEGER DEFAULT 0,
   old_swing_retest_score REAL);
CREATE TABLE IF NOT EXISTS historical_string_screener (
  string_id TEXT, date TEXT,
  name TEXT, price REAL, change_pct REAL, volume REAL, weighted_alpha REAL,
  atrp REAL, streak INTEGER, atr_signal INTEGER, atr_stop REAL, atr_value REAL, atr_streak INTEGER,
  atr_crossed_above INTEGER, atr_crossed_below INTEGER, atr_multiplier REAL,
  next_day_return REAL, next_5d_return REAL, prob_up_1d REAL, prob_up_5d REAL,
  pre_price REAL, pre_change_pct REAL, post_price REAL, post_change_pct REAL,
  accel_a REAL, accel_base REAL, accel_signal INTEGER, accel_crossed_up INTEGER, accel_crossed_down INTEGER, accel_streak INTEGER,
  confluence REAL DEFAULT 0, ai_overall_score REAL, ai_bias TEXT,
  ai_tech_score REAL, ai_momentum_score REAL, ai_volume_score REAL, ai_events_score REAL,
  ai_volume_profile_score REAL, ai_trendline_score REAL, ai_sentiment_score REAL,
  ai_conclusion TEXT, ai_matrix TEXT DEFAULT '', PRIMARY KEY (string_id, date),
   st_bars_below INTEGER DEFAULT 0, st_bars_above INTEGER DEFAULT 0,
   accel_bars_below INTEGER DEFAULT 0, accel_bars_above INTEGER DEFAULT 0,
   old_swing_retest_score REAL);

CREATE TABLE IF NOT EXISTS nifty500_constituents (
  symbol TEXT PRIMARY KEY,
  from_date TEXT NOT NULL,
  to_date TEXT DEFAULT '9999-12-31');

CREATE TABLE IF NOT EXISTS nifty50_constituents (
  symbol TEXT PRIMARY KEY,
  from_date TEXT NOT NULL,
  to_date TEXT DEFAULT '9999-12-31');

CREATE TABLE IF NOT EXISTS fo_constituents (
  symbol TEXT PRIMARY KEY,
  from_date TEXT NOT NULL,
  to_date TEXT DEFAULT '9999-12-31');

CREATE TABLE IF NOT EXISTS sp500_constituents (
  symbol TEXT PRIMARY KEY,
  from_date TEXT NOT NULL,
  to_date TEXT DEFAULT '9999-12-31');

CREATE TABLE IF NOT EXISTS nasdaq100_constituents (
  symbol TEXT PRIMARY KEY,
  from_date TEXT NOT NULL,
  to_date TEXT DEFAULT '9999-12-31');

CREATE TABLE IF NOT EXISTS russell2000_constituents (
  symbol TEXT PRIMARY KEY,
  from_date TEXT NOT NULL,
  to_date TEXT DEFAULT '9999-12-31');

CREATE TABLE IF NOT EXISTS dow30_constituents (
  symbol TEXT PRIMARY KEY,
  from_date TEXT NOT NULL,
  to_date TEXT DEFAULT '9999-12-31');

-- CRYPTO tables
CREATE TABLE IF NOT EXISTS crypto_products (
  symbol TEXT PRIMARY KEY, product_id INTEGER NOT NULL,
  contract_type TEXT, tick_size REAL, lot_size INTEGER,
  default_leverage REAL, initial_margin REAL, state TEXT);

CREATE TABLE IF NOT EXISTS crypto_bars (
  symbol TEXT, timeframe TEXT, date TEXT,
  open REAL, high REAL, low REAL, close REAL, volume REAL,
  PRIMARY KEY (symbol, timeframe, date));

CREATE TABLE IF NOT EXISTS crypto_settings (
  key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS crypto_paper_positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL, side TEXT NOT NULL,
  qty REAL NOT NULL, entry_price REAL, current_price REAL,
  unrealized_pnl REAL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')), updated_at TEXT,
  delta_order_id TEXT);

CREATE TABLE IF NOT EXISTS crypto_paper_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL, side TEXT NOT NULL,
  order_type TEXT, qty REAL, price REAL,
  status TEXT DEFAULT 'pending',
  delta_order_id TEXT, filled_qty REAL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')));

CREATE TABLE IF NOT EXISTS crypto_wallet (
  asset TEXT PRIMARY KEY, balance REAL DEFAULT 0, locked REAL DEFAULT 0);

CREATE TABLE IF NOT EXISTS crypto_stats (
  symbol TEXT PRIMARY KEY,
  price REAL, open REAL, high REAL, low REAL, volume REAL,
  oi REAL, oi_value REAL, funding_rate REAL, mark_price REAL,
  change_pct REAL, bid REAL, ask REAL, spread REAL,
  high_24h REAL, low_24h REAL,
  atr_signal INTEGER DEFAULT 0, atr_stop REAL DEFAULT 0, atr_value REAL DEFAULT 0,
  atr_streak INTEGER DEFAULT 0, atr_crossed_above INTEGER DEFAULT 0, atr_crossed_below INTEGER DEFAULT 0,
  atrp REAL DEFAULT 0, streak INTEGER DEFAULT 0, weighted_alpha REAL DEFAULT 0,
  accel_a REAL DEFAULT 0, accel_base REAL DEFAULT 0, accel_signal INTEGER DEFAULT 0,
  accel_crossed_up INTEGER DEFAULT 0, accel_crossed_down INTEGER DEFAULT 0,
  accel_bars_below INTEGER DEFAULT 0, accel_bars_above INTEGER DEFAULT 0,
  prob_up_1d REAL DEFAULT 50, prob_up_5d REAL DEFAULT 50, prob_up_1w REAL DEFAULT 50, prob_up_1m REAL DEFAULT 50,
  prob_up_st_cross REAL DEFAULT 50, confluence REAL DEFAULT 0, next_day_return REAL DEFAULT 0,
  st_bars_below INTEGER DEFAULT 0, st_bars_above INTEGER DEFAULT 0,
  atr_signal_w INTEGER DEFAULT 0, atr_stop_w REAL DEFAULT 0,
  atr_crossed_above_w INTEGER DEFAULT 0, atr_crossed_below_w INTEGER DEFAULT 0, atr_streak_w INTEGER DEFAULT 0,
  atr_signal_m INTEGER DEFAULT 0, atr_stop_m REAL DEFAULT 0,
  atr_crossed_above_m INTEGER DEFAULT 0, atr_crossed_below_m INTEGER DEFAULT 0, atr_streak_m INTEGER DEFAULT 0,
  ai_overall_score REAL DEFAULT 0, ai_bias TEXT DEFAULT 'neutral',
  ai_tech_score REAL DEFAULT 0, ai_momentum_score REAL DEFAULT 0,
  ai_volume_score REAL DEFAULT 0, ai_events_score REAL DEFAULT 0,
  ai_volume_profile_score REAL DEFAULT 0, ai_trendline_score REAL DEFAULT 0,
  ai_sentiment_score REAL DEFAULT 0, ai_conclusion TEXT DEFAULT 'HOLD',
  ai_matrix TEXT DEFAULT '',
  last_updated TEXT
);

CREATE TABLE IF NOT EXISTS crypto_historical_screener (
  symbol TEXT, date TEXT, price REAL, change_pct REAL, volume REAL,
  weighted_alpha REAL, atrp REAL, streak INTEGER, atr_value REAL, atr_stop REAL, atr_signal INTEGER,
  atr_crossed_above INTEGER, atr_crossed_below INTEGER, atr_streak INTEGER,
  next_day_return REAL, prob_up_1d REAL, prob_up_5d REAL, prob_up_1w REAL, prob_up_1m REAL,
  prob_up_st_cross REAL DEFAULT 50,
  accel_a REAL, accel_base REAL, accel_signal INTEGER, accel_crossed_up INTEGER, accel_crossed_down INTEGER,
  confluence REAL DEFAULT 0,
  st_bars_below INTEGER DEFAULT 0, st_bars_above INTEGER DEFAULT 0,
  accel_bars_below INTEGER DEFAULT 0, accel_bars_above INTEGER DEFAULT 0,
  atr_signal_w INTEGER DEFAULT 0, atr_stop_w REAL DEFAULT 0,
  atr_crossed_above_w INTEGER DEFAULT 0, atr_crossed_below_w INTEGER DEFAULT 0, atr_streak_w INTEGER DEFAULT 0,
  atr_signal_m INTEGER DEFAULT 0, atr_stop_m REAL DEFAULT 0,
  atr_crossed_above_m INTEGER DEFAULT 0, atr_crossed_below_m INTEGER DEFAULT 0, atr_streak_m INTEGER DEFAULT 0,
  ai_overall_score REAL DEFAULT 0, ai_bias TEXT DEFAULT 'neutral',
  ai_tech_score REAL DEFAULT 0, ai_momentum_score REAL DEFAULT 0,
  ai_volume_score REAL DEFAULT 0, ai_events_score REAL DEFAULT 0,
  ai_volume_profile_score REAL DEFAULT 0, ai_trendline_score REAL DEFAULT 0,
  ai_sentiment_score REAL DEFAULT 0, ai_conclusion TEXT DEFAULT 'HOLD',
  ai_matrix TEXT DEFAULT '',
  PRIMARY KEY (symbol, date)
);"""

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_stats_wa ON stats(weighted_alpha);
CREATE INDEX IF NOT EXISTS idx_stats_atr_signal ON stats(atr_signal);
CREATE INDEX IF NOT EXISTS idx_stats_streak ON stats(streak);
CREATE INDEX IF NOT EXISTS idx_stats_change ON stats(change_pct);
CREATE INDEX IF NOT EXISTS idx_stats_prob ON stats(prob_up_1d);
CREATE INDEX IF NOT EXISTS idx_stats_exchange ON stats(exchange);
CREATE INDEX IF NOT EXISTS idx_stats_asset ON stats(asset_class);
CREATE INDEX IF NOT EXISTS idx_bars_sym_tf_date ON bars(symbol, timeframe, date);
CREATE INDEX IF NOT EXISTS idx_bars_tf_symbol ON bars(timeframe, symbol);
CREATE INDEX IF NOT EXISTS idx_bars_tf_date ON bars(timeframe, date);
CREATE INDEX IF NOT EXISTS idx_bars_tf_sym_date_cover ON bars(timeframe, symbol, date, open, high, low, close, volume);
CREATE INDEX IF NOT EXISTS idx_hs_sym_date ON historical_screener(symbol, date);
CREATE INDEX IF NOT EXISTS idx_hs_date ON historical_screener(date);
CREATE INDEX IF NOT EXISTS idx_adp_score ON ai_discovered_portfolios(score DESC);
CREATE INDEX IF NOT EXISTS idx_stats_accel ON stats(accel_signal);
CREATE INDEX IF NOT EXISTS idx_stats_confluence ON stats(confluence);
CREATE INDEX IF NOT EXISTS idx_ss_strat_name ON ss_strategies(name);
CREATE INDEX IF NOT EXISTS idx_ss_entries_strat ON ss_entries(strategy_id);
CREATE INDEX IF NOT EXISTS idx_su_market ON string_universe(market);
CREATE INDEX IF NOT EXISTS idx_sc_string ON string_constituents(string_id);
CREATE INDEX IF NOT EXISTS idx_ssm_market ON string_screener_metrics(market);
CREATE INDEX IF NOT EXISTS idx_nifty500_date ON nifty500_constituents(from_date, to_date);
CREATE INDEX IF NOT EXISTS idx_nifty50_date ON nifty50_constituents(from_date, to_date);
CREATE INDEX IF NOT EXISTS idx_fo_date ON fo_constituents(from_date, to_date);
CREATE INDEX IF NOT EXISTS idx_sp500_date ON sp500_constituents(from_date, to_date);
CREATE INDEX IF NOT EXISTS idx_nasdaq100_date ON nasdaq100_constituents(from_date, to_date);
CREATE INDEX IF NOT EXISTS idx_russell2000_date ON russell2000_constituents(from_date, to_date);
CREATE INDEX IF NOT EXISTS idx_dow30_date ON dow30_constituents(from_date, to_date);
-- CRYPTO indexes
CREATE INDEX IF NOT EXISTS idx_crypto_bars_tf_sym_date ON crypto_bars(timeframe, symbol, date);
CREATE INDEX IF NOT EXISTS idx_crypto_bars_sym_date ON crypto_bars(symbol, date);
CREATE INDEX IF NOT EXISTS idx_crypto_bars_tf_sym_date_cover ON crypto_bars(timeframe, symbol, date, open, high, low, close, volume);
CREATE INDEX IF NOT EXISTS idx_cs_wa ON crypto_stats(weighted_alpha);
CREATE INDEX IF NOT EXISTS idx_cs_atr ON crypto_stats(atr_signal);
CREATE INDEX IF NOT EXISTS idx_cs_accel ON crypto_stats(accel_signal);
CREATE INDEX IF NOT EXISTS idx_cs_conf ON crypto_stats(confluence);
CREATE INDEX IF NOT EXISTS idx_cs_prob ON crypto_stats(prob_up_1d);
CREATE INDEX IF NOT EXISTS idx_cs_change ON crypto_stats(change_pct);
CREATE INDEX IF NOT EXISTS idx_cs_volume ON crypto_stats(volume);
CREATE INDEX IF NOT EXISTS idx_chs_sym_date ON crypto_historical_screener(symbol, date);
CREATE INDEX IF NOT EXISTS idx_chs_date ON crypto_historical_screener(date);
CREATE INDEX IF NOT EXISTS idx_chs_wa ON crypto_historical_screener(weighted_alpha);
CREATE INDEX IF NOT EXISTS idx_chs_atr ON crypto_historical_screener(atr_signal);
CREATE INDEX IF NOT EXISTS idx_chs_accel ON crypto_historical_screener(accel_signal);
-- idx_hss_date and idx_hss_string are created by rebuild (too slow at startup with 75M rows)
"""


def _init_db(db_path):
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-262144")
    conn.execute("PRAGMA mmap_size=4294967296")
    for stmt in SCHEMA_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
    for stmt in INDEXES_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
    # Migration: add confluence column if missing
    try:
        conn.execute("ALTER TABLE historical_screener ADD COLUMN confluence REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE ai_analysis ADD COLUMN ai_matrix TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE historical_screener ADD COLUMN ai_matrix TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE assets ADD COLUMN shortable INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE assets ADD COLUMN margin_requirement_long TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE assets ADD COLUMN margin_requirement_short TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE historical_screener ADD COLUMN prob_up_st_cross REAL DEFAULT 50")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE historical_string_screener ADD COLUMN prob_up_st_cross REAL DEFAULT 50")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE stats ADD COLUMN prob_up_st_cross REAL DEFAULT 50")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE string_screener_metrics ADD COLUMN prob_up_st_cross REAL DEFAULT 50")
    except sqlite3.OperationalError:
        pass
    # Migration: add old_swing_retest_score column if missing
    try:
        conn.execute("ALTER TABLE stats ADD COLUMN old_swing_retest_score REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE historical_screener ADD COLUMN old_swing_retest_score REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE string_screener_metrics ADD COLUMN old_swing_retest_score REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE historical_string_screener ADD COLUMN old_swing_retest_score REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # Migration: multi-timeframe SuperTrend columns (rolling weekly / monthly)
    for suffix in ("_w", "_m"):
        for col, typedef in [
            ("atr_signal", "INTEGER DEFAULT 0"),
            ("atr_stop", "REAL DEFAULT 0"),
            ("atr_crossed_above", "INTEGER DEFAULT 0"),
            ("atr_crossed_below", "INTEGER DEFAULT 0"),
            ("atr_streak", "INTEGER DEFAULT 0"),
            ("st_bars_below", "INTEGER DEFAULT 0"),
            ("st_bars_above", "INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE stats ADD COLUMN {col}{suffix} {typedef}")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute(f"ALTER TABLE historical_screener ADD COLUMN {col}{suffix} {typedef}")
            except sqlite3.OperationalError:
                pass
    # Migration: prob_up_1w and prob_up_1m
    for table in ("stats", "historical_screener"):
        for col, typedef in [
            ("prob_up_1w", "REAL DEFAULT 50"),
            ("prob_up_1m", "REAL DEFAULT 50"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass
    # Migration: r_squared straight-trend column (asof-v3)
    for table in ("stats", "historical_screener", "string_screener_metrics", "historical_string_screener"):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN r_squared REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_r2 ON stats(r_squared)")
    except sqlite3.OperationalError:
        pass
    # Migration: portfolio string ordering (present in US/India, missing in crypto/fresh DBs)
    try:
        conn.execute("ALTER TABLE portfolio_strings ADD COLUMN sort_order INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # Migration: add AI score columns to crypto tables
    for table in ("crypto_stats", "crypto_historical_screener"):
        for col, typedef in [
            ("ai_overall_score", "REAL DEFAULT 0"),
            ("ai_bias", "TEXT DEFAULT 'neutral'"),
            ("ai_tech_score", "REAL DEFAULT 0"),
            ("ai_momentum_score", "REAL DEFAULT 0"),
            ("ai_volume_score", "REAL DEFAULT 0"),
            ("ai_events_score", "REAL DEFAULT 0"),
            ("ai_volume_profile_score", "REAL DEFAULT 0"),
            ("ai_trendline_score", "REAL DEFAULT 0"),
            ("ai_sentiment_score", "REAL DEFAULT 0"),
            ("ai_conclusion", "TEXT DEFAULT 'HOLD'"),
            ("ai_matrix", "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass
    conn.commit()
    conn.close()


def init_all_dbs():
    _init_db(US_DB)
    _init_db(INDIA_DB)
    _init_db(CRYPTO_DB)


def get_db(market="US"):
    from dumbmoney.config import DB_PATHS
    db_path = DB_PATHS.get(market, US_DB)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-262144")     # 256MB page cache (was 64MB) — big win on 17-34GB DBs
    conn.execute("PRAGMA mmap_size=4294967296")    # 4GB memory-map: reads skip the read() syscall, major speedup on the hot filter/screener path
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-262144")
    conn.execute("PRAGMA mmap_size=4294967296")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {row[0] for row in cursor.fetchall()}
    for stmt in SCHEMA_SQL.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        table_name = None
        for line in stmt.split("\n"):
            line = line.strip()
            if line.upper().startswith("CREATE TABLE IF NOT EXISTS"):
                parts = line.split()
                for i, p in enumerate(parts):
                    if p.upper() == "TABLE":
                        if i + 2 < len(parts):
                            table_name = parts[i + 2]
                        break
        if table_name and table_name not in existing:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
    for stmt in INDEXES_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
    conn.commit()
    conn.close()


def migrate_nulls(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-262144")
    conn.execute("PRAGMA mmap_size=4294967296")
    c = conn.cursor()
    defaults = {
        "stats": {"atrp": 0, "weighted_alpha": 0, "atr_signal": 0, "atr_streak": 0,
                  "atr_crossed_above": 0, "atr_crossed_below": 0, "atr_multiplier": 1.0,
                  "streak": 0, "fractionable": 0, "marginable": 0, "tradable": 0,
                  "accel_a": 0, "accel_base": 0, "accel_signal": 0,
                  "accel_crossed_up": 0, "accel_crossed_down": 0, "accel_streak": 0, "confluence": 0},
        "ai_analysis": {"overall_score": 0, "bias": "neutral", "tech_score": 0,
                        "momentum_score": 0, "volume_score": 0, "events_score": 0,
                        "volume_profile_score": 0, "trendline_score": 0, "sentiment_score": 0,
                        "conclusion": "HOLD", "ai_matrix": ""},
        "ss_strategies": {"total_entries": 0, "win_rate": 0, "avg_1d_return": 0, "median_1d_return": 0,
                          "std_1d_return": 0, "max_1d_gain": 0, "max_1d_loss": 0,
                          "max_consecutive_wins": 0, "max_consecutive_losses": 0, "sharpe_1d": 0,
                          "prob_up_1d": 0, "prob_up_1pct": 0, "prob_up_2pct": 0, "prob_down_2pct": 0,
                          "prob_up_after_st_cross": 0, "prob_up_after_wa_high": 0,
                          "current_count": 0, "current_value": 0, "current_st_signal": 0,
                          "current_st_crossed": 0, "current_avg_wa": 0, "is_random": 0},
        "portfolio_strings": {"realised_pnl": None},
    }
    for table, cols in defaults.items():
        try:
            c.execute(f"PRAGMA table_info({table})")
            existing_cols = {row[1] for row in c.fetchall()}
            for col, default in cols.items():
                if col not in existing_cols:
                    if isinstance(default, str):
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT DEFAULT '{default}'")
                    else:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} REAL DEFAULT {default}")
        except sqlite3.OperationalError:
            pass
    # CRYPTO: initialize settings table defaults
    try:
        c.execute("INSERT OR IGNORE INTO crypto_settings (key, value) VALUES ('download_progress', '{}')")
        c.execute("INSERT OR IGNORE INTO crypto_settings (key, value) VALUES ('last_download_run', '0')")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    # Add realised_pnl column to portfolio_strings if missing
    try:
        c.execute("PRAGMA table_info(portfolio_strings)")
        ps_cols = {row[1] for row in c.fetchall()}
        if "realised_pnl" not in ps_cols:
            c.execute("ALTER TABLE portfolio_strings ADD COLUMN realised_pnl REAL")
            # Backfill existing closed strings
            c.execute("""
                UPDATE portfolio_strings
                SET realised_pnl = COALESCE(exit_price, 0) - COALESCE(entry_price, 0)
                WHERE status = 'closed' AND exit_price IS NOT NULL AND entry_price IS NOT NULL
            """)
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()
