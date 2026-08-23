# DumbMoney - Project Status & Session History

## What Is This Project?

**DumbMoney** is a stock screening application (Flask + SQLite) for:
- **USA market** (Alpaca API for bars, Yahoo Finance for earnings)
- **India market** (NSE via Yahoo Finance)

Runs on **port 8474**. Green/white glass UI. Features include:
- Technical indicators (SuperTrend, Accel, prob_up, streak, ATRP)
- AI scoring, confluence, combined OHLC
- String screener, rule portfolios, paper trading
- Historical screener, signal probability matrix
- SVG CandleChart with overlays
- Real-time refresh with progress tracking (8 steps)

---

## Current State (as of Jul 5, 2026)

### Databases - BOTH FULL
| | US (screener.db) | India (india.db) |
|---|---|---|
| Size | 2.3 GB | 2.0 GB |
| Bars | 10,447,848 | 4,597,109 |
| Assets | 11,445 | 2,381 |
| Stats | ~10,617 | 2,379 |
| Date range | 2017-08-29 to 2026-07-02 | 1996-01-01 to 2026-07-03 |
| Historical screener | ~10,448,880 rows | 4,572,172 rows |

### What Works
- Both homepages load (US + India)
- Screener API returns full data for both markets
- Stock detail pages work
- Bars download for both markets
- Vectorized stats computation
- Earnings fetch (was stuck, now fixed with parallel workers)

### Where We Are STUCK RIGHT NOW

**`update_signal_prob_matrix` in `engine.py:372`** does:
```python
hs = pd.read_sql("SELECT * FROM historical_screener", conn)
```

This loads **10.4 MILLION rows** into pandas. On US market:
1. It blocks the entire Flask server (unresponsive to HTTP requests)
2. It consumes 7.6GB+ RAM
3. It takes 5-10+ minutes just to load
4. During this time, the status API is unreachable

**The fix needed**: Change `SELECT *` to only select the columns actually needed by `compute_signal_prob_matrix()`:
- `atr_signal`, `atr_streak`, `accel_signal`, `accel_crossed_up`, `accel_crossed_down`
- `weighted_alpha`, `next_day_return`

This would reduce memory from 10.4M rows × ALL columns to 10.4M rows × ~7 columns.

---

## Completed Fixes This Session

1. **`fetch_earnings_yahoo` timeout** — Changed `timeout=8` to `timeout=(3, 8)` (connect=3s, read=8s)
2. **`update_profit_data` parallelized** — Was serial loop over 10,599 symbols (hung on dead Yahoo sessions). Now uses ThreadPoolExecutor with 8 workers, session pool, session refresh on failure
3. **`download_bars` (US)** — Reverted to per-page DB writes instead of accumulate-all + background writer thread
4. **India `_download_one` signature** — Accepts `start_date` param, uses period1/period2 for incremental, range=10y for backfill

---

## Still TODO

1. **Fix `update_signal_prob_matrix`** — Select only needed columns instead of `SELECT *`
2. **Run full US refresh end-to-end** without hangs
3. **Run full India refresh** and verify
4. **Test all pages** (screener, stock detail, historical, string screener, portfolio, paper trading)

---

## Session History (Chronological)

### Session 1: Initial Build
Built the entire DumbMoney application from scratch:
- Full project structure: `dumbmoney/` package
- DB schema with 25+ tables, indexes, WAL mode
- All indicators, screeners, AI scoring, paper trading
- Both HTML templates with green/white glass design
- Alpaca + Yahoo Finance data downloaders
- SVG CandleChart engine

### Session 2: Bug Fixes Round 1
- streak_vectorized fix
- Stats INSERT binding fix
- Screener API LEFT JOINs
- MARKET/OTHER_MARKET constants
- ATR signal uses trend direction
- AI discovery/string_screener None/NaN handling
- Cancel flow
- Incremental download
- signal_prob_matrix UNIQUE constraint
- historical_screener confluence column
- SQLite 999-param limit batching
- Stale status reset
- Refresh polling
- Sidebar stats
- New IPO detection
- Timezone IST

### Session 3: Bug Fixes Round 2
- weighted_alpha (cumulative returns from LAST 252 bars)
- fillna deprecation
- Screener column sorting
- Search filter
- Missing filter UI
- Pre/post market prices
- Profit/earnings data
- Historical_screener hang (first version)
- Date filter
- Earnings fetch crash

### Session 4: Speed & Stability
- India download: raw Yahoo Finance API with parallel sessions
- India download: 5 workers, background writer thread
- India download: parallel session creation (`_init_yf_sessions`)
- US download: background writer thread (later reverted)
- Cancel: `cancel_refresh()` sets status directly
- All times displayed in IST
- India market: NSE only (BSE removed)
- US market: Alpaca only

### Session 5: This Session (Jul 5, 2026)
- Verified both DBs are FULL (not empty as previous summary claimed)
- Started server, tested both markets work
- Found US refresh stuck at earnings step (0/10599, serial loop)
- Fixed `update_profit_data` with parallel workers
- Earnings step now works (2800→7200/10599 in progress)
- Found `update_signal_prob_matrix` blocking server with `SELECT *` on 10.4M rows
- **CURRENTLY STUCK HERE** — need to fix column selection

---

## Key Files

| File | Purpose |
|------|---------|
| `dumbmoney/app.py` | Flask app, all API endpoints |
| `dumbmoney/engine.py` | vectorized_stats_pass, update_historical_screener, update_signal_prob_matrix, compute_portfolio_aggregates |
| `dumbmoney/refresh.py` | _refresh_worker (8 steps), _download_us_bars_incremental, _download_india_bars |
| `dumbmoney/data_us.py` | download_bars (Alpaca), sync_assets, update_profit_data, fetch_earnings_yahoo |
| `dumbmoney/data_india.py` | _init_yf_sessions, _download_one, download_bars_india, sync_india_assets |
| `dumbmoney/indicators.py` | All indicators, compute_signal_prob_matrix |
| `dumbmoney/db.py` | Schema, indexes, WAL mode, get_db, ensure_schema |
| `dumbmoney/config.py` | DB_PATHS, API keys |
| `run.py` | Launcher with sys.path fix |

---

## Key Decisions

- `MARKET` constant in `<head>` block of `base.html`
- `atr_signal` stores SuperTrend `trend` for Above/Below filter
- Stats computation incremental: `vectorized_stats_pass(only_symbols=[...])`
- `signal_prob_matrix` uses DELETE ALL then INSERT OR REPLACE
- Weighted Alpha: LAST 252 bars, cumulative return, linear weights 0.5->1.0, normalized x100
- All times displayed in IST (UTC+5:30)
- India market: NSE only
- India download: raw Yahoo Finance chart API
- US download: Alpaca only
- Cancel: `_cancel_event` checked at every step/batch boundary
- Yahoo auth: fc.yahoo.com -> cookie -> getcrumb -> chart API

---

## Alpaca API Limits
- Free tier (IEX feed): 200 req/min
- Current rate limiter: 190/min
- Historical data since ~2016
- `limit=10000` in bars API limits TOTAL bars across ALL symbols in batch
