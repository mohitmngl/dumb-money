# AGENTS.md - Read Before Any Code Change

Every agent must read this file before editing this project. Do not skip it. Most breakage in this app has come from mixing current values with historical values, or from treating the US and India refresh flows as one shared flow.

> **Also read [`SPEED.md`](SPEED.md) before touching any data-loading, refresh, download, filter, or DB code.** Owner's standing order: the download/refresh flow and every filter must stay super-duper fast. AGENTS.md owns correctness; SPEED.md owns speed. The `get_db()` pragmas (esp. `mmap_size`) gave a measured 6.8× on the date-filter query — never weaken them.

## Project Map

- `run.py`: starts the Flask app on port `8474`.
- `dumbmoney/app.py`: Flask routes and `/api/*` endpoints. The main table endpoint is `/api/screener`.
- `dumbmoney/refresh.py`: the only full-site data update path. Refresh downloads data, recomputes stats, fills history, and updates derived tables.
- `dumbmoney/engine.py`: indicator computation, current `stats`, `historical_screener`, signal matrix, and aggregates.
- `dumbmoney/indicators.py`: SuperTrend, Accel, weighted alpha, probabilities, streaks, ATRP, confluence helpers.
- `dumbmoney/db.py`: SQLite schema, indexes, WAL mode, DB connections.
- `dumbmoney/templates/base.html`: market switcher and refresh polling UI.
- `dumbmoney/templates/screener.html`: screener filters, sorting, columns, table rendering.
- `/api/screener/columns`: machine-readable source/meaning contract for visible screener columns. Update it whenever columns are added, renamed, or re-sourced.
- `screukener.db` is not a valid table or DB name. The real US DB must be `screener.db`.
- Real DBs:
  - US: `screener.db`
  - India: `india.db`

## Non-Negotiable Refresh Invariants

- Refresh is market-scoped. US and India must never share thread state, cancel events, or persisted status.
- US refresh status is stored in US `screener.db`, key `settings.refresh_status`.
- India refresh status is stored in India `india.db`, key `settings.refresh_status`.
- `/api/refresh/status?market=US` must return US status only.
- `/api/refresh/status?market=INDIA` must return India status only.
- `/api/refresh/cancel` must receive and honor the market.
- The frontend must poll status with `MARKET`: `/api/refresh/status?market=${MARKET}`.
- The frontend must cancel with `{market: MARKET}`.
- A normal refresh should recompute current `stats` for updated symbols and historical rows for updated symbols only.
- A full historical rebuild is allowed only when the historical logic/schema version changes or the user explicitly asks.
- A no-change fast refresh must not start a full historical rebuild just because the stored historical version is missing. Use the explicit `/api/historical/rebuild` maintenance path for full rebuilds.
- Treat `only_symbols=[]` as a deliberate no-op. Never convert an empty updated-symbol list to `None`; `None` means full-market recompute.
- Normal refresh must not perform deep 1970/2016 backfill for symbols that are otherwise current. Backfill is a separate explicit maintenance/full-rebuild job.

## Refresh Step Rules

Current refresh order:

1. Sync universe.
2. Download daily bars.
3. Vectorized stats.
4. Fundamentals / asset info.
5. Pre/post market, US only.
6. AI scores.
7. Aggregates.
8. Background history and signal probability matrix.

Fast normal refresh contract:

- Universe sync may reuse a recent populated `assets` cache, currently up to 7 days old; do not hit Alpaca/NSE on every refresh click unless forced.
- Download daily bars only for symbols whose latest stored daily bar is stale or missing.
- Stale-date cutoff is market-aware: weekends are skipped for both markets, and US observed federal holidays are skipped for US so holiday closures do not trigger full downloads.
- Normal refresh seeds brand-new/no-bar symbols from a recent indicator warm-up window, currently 450 calendar days. It must not deep-download from 1970/2016 for every newly listed or newly discovered symbol.
- Group incremental downloads by each symbol's own next needed start date. Do not let one very stale symbol force a whole mixed batch to download years of extra bars.
- US normal bar refresh uses the fast listed-equity IEX path. Do not include OTC assets in that normal path unless the data feed is changed to one that reliably supports them.
- For full default market refresh planning, compute latest/oldest bar dates with indexed per-asset lookups against `(symbol,timeframe,date)`. Use `symbol IN (...)` only for genuinely scoped symbol lists; avoid full historical `GROUP BY symbol` scans.
- Pass the exact `updated_symbols` list through stats, asset info, pre/post snapshots, earnings, historical screener, and any new derived feature.
- If `updated_symbols` is empty, stats, asset info, snapshots, earnings, and incremental history should finish as no-ops.
- Normal refresh must not rebuild the full signal probability matrix. The matrix is full-history maintenance and is recomputed by explicit `/api/historical/rebuild`.
- If a historical version mismatch exists, one explicit full historical rebuild is expected; do not hide that cost inside unrelated current-only feature work.
- `/api/historical/rebuild` is the explicit maintenance endpoint for rebuilding `historical_screener` and `signal_prob_matrix`; it can be slow and should not be called by normal fast refresh UI clicks.

When adding a website feature, decide if it needs refresh:

- If the feature displays data derived from downloaded bars, assets, earnings, snapshots, portfolios, strings, or historical rows, it must be added to refresh.
- If the feature changes any screener, stock detail, portfolio, string screener, paper trading, or AI strategy value, define the refresh step that computes it.
- BTST Dashboard is read-only over current `stats` and generated `ss_strategies`; it must not invent/mock candidates. Empty string picks mean String Screener backtest has not generated strategies yet.
- String Screener generation should produce 10k+ real strategy variants from current `stats` plus `historical_screener` backtests; keep filters/sorts SQL-backed in `get_strategies`.
- If the feature is visible in date-filter mode, compute and store the value as of each historical date. Do not copy current `stats` into old dates.
- If the feature is current-only, return `NULL` or clearly current-only values in historical mode and document that here.
- Any new refresh step needs a progress callback, cancellation boundary, market argument, and DB write strategy.
- Never add a long network or pandas operation without progress updates.

## Download & Refresh Speed Contract

These are the things that keep a normal refresh fast. Do not regress any of them.

- Universe sync reuses a populated `assets` cache up to 7 days old. Never hit Alpaca/NSE per refresh click; `force=True` is the explicit universe re-sync.
- Plan downloads with one indexed per-asset `MAX(bars.date)` correlated subquery. Skip the `MIN(date)` oldest-date subquery unless `allow_backfill=True`; it doubles planning time on the huge bars table for data the normal path never reads.
- Download only stale symbols: latest stored bar older than the market-aware last-weekday cutoff. Weekends skip for both markets; US federal holidays skip for US.
- Group incremental downloads by each symbol's own next start date (latest bar + 1 day). New/no-bar symbols seed from the 450-day warm-up window, never 1970/2016.
- US normal path is the Alpaca multi-symbol IEX feed (`feed=iex`, 200-symbol batches, paged) with OTC excluded. India is pooled pre-authenticated Yahoo sessions with a background writer thread so downloads never block on DB writes.
- Keep the symbol list and its per-asset date lookup on the same asset filter (`status='active'`, and for US `tradable=1`, non-OTC). A symbol in the list but missing from the date map is treated as brand new and re-downloads 450 days on every refresh.
- Bulk insert bars with `executemany` per API page/batch. No row-by-row commits inside download loops.
- Downloader helpers return `[]` when nothing was downloaded — never a bare `return`. `None` downstream means full-market recompute; `[]` means no-op.
- Pass the returned `updated_symbols` list unchanged into stats, asset info, snapshots, earnings, and historical screener.
- Persist progress at least once per download batch and every ~50 symbols during stats. `_persist_status` already throttles to one DB write per second, so callbacks may be frequent; the UI must never sit on a stale phase for minutes.
- Normal refresh appends only the latest basket-history date. If the string universe changed size, say so in the status phase and stop; the full basket history rebuild belongs to the explicit Basket Screener generate/historical endpoints, never to normal refresh.

## Date Filter Atomic Semantics

`/api/screener?date_cutoff=YYYY-MM-DD` means: show values as they were on that selected trading date.

Authoritative source for date-filter mode:

- Use `historical_screener h` for all historical indicator/table values.
- Join `assets a` only for metadata: `name`, `exchange`, `asset_class`, `fractionable`, `marginable`.
- Join `stats s` only for explicitly current-only fields such as `profit_status` until a historical fundamentals table exists.

Column meanings in date-filter mode:

- `symbol`: `historical_screener.symbol`
- `date`: selected date
- `price`: `bars.close` for that exact date, stored as `historical_screener.price`
- `volume`: `bars.volume` for that exact date
- `change_pct`: close(selected date) vs previous available trading close for the same symbol
- `next_day_return`: next available trading close vs selected date close
- `next_5d_return`: close five trading rows later vs selected date close
- `weighted_alpha`: computed using only bars up to and including the selected date
- `atrp`: computed using only bars up to and including the selected date
- `streak`: computed using only closes up to and including the selected date
- `atr_signal`, `atr_stop`, `atr_value`, `atr_streak`, `atr_crossed_above`, `atr_crossed_below`: SuperTrend state as of the selected date
- `accel_a`, `accel_base`, `accel_signal`, `accel_crossed_up`, `accel_crossed_down`: Accel state as of the selected date
- `prob_up_1d`, `prob_up_5d`: trailing completed-period probabilities using bars available as of the selected date
- `confluence`: computed from the as-of-date row
- `ai_*`: local vectorized AI score computed as of the selected date
- `pre_price`, `post_price`, `pre_change_pct`, `post_change_pct`: current-session only; return `NULL` in historical mode unless historical extended-hours data is added
- `last_updated`: the selected historical date, not today's stats timestamp

Never do this in date-filter mode:

- Do not query old `bars` and join current `stats` for indicators.
- Do not sort/filter a page in Python after SQL pagination.
- Do not sort historical `change_pct` by `bars.close`.
- Do not copy today's `weighted_alpha`, `streak`, ATR, Accel, probability, or next-day-return into old dates.

## Sorting And Filtering Rules

- Current mode uses `stats`.
- Historical mode uses `historical_screener`.
- Keep current and historical screener responses field-compatible. If a visible current-only field has no historical source, return it as `NULL` in historical mode and document it in `/api/screener/columns`.
- Keep `/api/screener/columns` synchronized with `templates/screener.html` and the SQL SELECT lists.
- The visible table columns, `/api/screener/columns`, current SELECT list, and historical SELECT list must move together in one atomic patch. If one changes and the others do not, stop and fix the contract before testing UI.
- Apply filters in SQL before `COUNT`, `ORDER BY`, `LIMIT`, and `OFFSET`.
- Apply sorting in SQL before pagination.
- Python may format returned rows, but must not change which rows belong on a page.
- Use allowlists for sort columns. Never concatenate raw user sort input into SQL.
- Order with `<col> <dir> NULLS LAST`, never `CASE WHEN <col> IS NULL THEN 1 ELSE 0 END, <col> <dir>`. Both produce identical rows, but the CASE wrapper forces a temp B-tree sort while NULLS LAST lets current mode use the stats indexes (measured 74ms to 4ms on US).
- Historical `change_pct` sort must use `h.change_pct`.
- Historical `weighted_alpha` sort must use `h.weighted_alpha`.
- Historical `next_day_return` sort must use `h.next_day_return`.

## Historical Rebuild Rules

- Historical logic version is stored in `settings.historical_screener_version`.
- Current version: `asof-v2`.
- If the code changes historical meanings, bump `HISTORICAL_SCREENER_VERSION` in `engine.py`.
- A version mismatch should delete and rebuild `historical_screener` and `signal_prob_matrix` once.
- After a successful rebuild, write the new version to settings.
- Incremental refresh should recompute symbols passed through `only_symbols`.
- If no symbols changed and the version is current, historical recompute should no-op.
- `only_symbols=[...]` must remain scoped even when the stored historical version is missing; do not delete/rebuild the whole table from a scoped validation or incremental refresh.
- `only_symbols=[...]` must compare `MAX(bars.date)` to `MAX(historical_screener.date)` for those symbols before computing. If the historical rows are already current and the version is current, return immediately.
- When appending historical rows for changed scoped symbols, compute indicators with the full symbol history but insert only dates after that symbol's latest existing historical date unless the version changed or a forced rebuild is running.
- Only a full rebuild (`only_symbols is None`) may write `settings.historical_screener_version`.

## Performance Rules

- SQLite is the bottleneck more often than math. Check query plans before adding Python work.
- Keep WAL mode and `busy_timeout`.
- Use compound indexes for date-filter paths.
- Benchmark and inspect `EXPLAIN QUERY PLAN` before adding heavyweight compound indexes to huge historical tables; do not create many startup indexes blindly.
- Existing DBs should keep only lean historical indexes by default: primary key `(symbol,date)`, `idx_hs_sym_date`, and `idx_hs_date`. Extra date+sort indexes made historical writes much slower and were removed from the current DBs.
- Select only needed columns from huge tables.
- COUNT queries must drop joins that cannot change the row count (a LEFT JOIN on a unique key that no filter references).
- Never `SELECT DISTINCT` or `COUNT(DISTINCT)` straight over the multi-million-row bars table on a request path. Use a recursive loose index scan (one indexed MAX/MIN seek per distinct value) as in `/api/hs-dates` and `/api/market-stats` (measured 3.6s to 26ms on India dates, 18s to 0.2s on India symbol count).
- `/api/market-stats` runs on every page load; its distinct-symbol counts stay behind a 60s cache keyed by latest bar date. Keep cheap queries live, keep heavy ones cached.
- Never `SELECT * FROM historical_screener` for signal probability matrix.
- Bulk insert historical rows in chunks.
- Avoid row-by-row DB writes inside symbol/date loops.
- Use pandas/NumPy vectorization before considering JAX.
- Do not add JAX to the app runtime unless a benchmark proves it beats pandas/NumPy for the exact workload including startup/JIT cost.

## Future Anti-Break Checks

- Before changing refresh, write down the exact market, table, source rows, recompute step, and visible columns affected.
- Before changing date filters, test at least one older non-latest date where `next_day_return` is not zero and compare it to the next trading close.
- Before changing sorting, test both `sort_dir=asc` and `sort_dir=desc` for current and historical mode with `per_page` small enough to inspect.
- Before adding a column, add it to `SCREENER_COLUMN_REFERENCE`, both SQL SELECT lists, the UI `COLUMNS` array, and this file if the meaning is new.
- Keep ordinary refresh fast by passing `updated_symbols`; use `/api/historical/rebuild` only for explicit full historical maintenance.
- Do not put full-table signal matrix rebuild back into normal refresh. It scans millions of historical rows and makes small daily refreshes slow.

## Signal Probability Matrix

Only these columns are needed from `historical_screener`:

- `atr_signal`
- `atr_streak`
- `accel_signal`
- `accel_crossed_up`
- `accel_crossed_down`
- `weighted_alpha`
- `next_day_return`

Do not load unrelated historical columns for this job.
Compute the matrix SQL-first with grouped aggregates. Do not load millions of historical rows into pandas just to group a small state/bucket matrix.
Even SQL-first, it is full-history maintenance; call it from `/api/historical/rebuild`, not normal refresh.

## Validation Checklist Before Finishing

- Run `python -m py_compile` on changed Python files.
- Check `/api/screener?market=US` and `/api/screener?market=INDIA`.
- Check date-filter mode for both markets.
- Verify date-filter sorting by `change_pct`, `weighted_alpha`, `next_day_return`, `price`, and `volume`.
- Verify filters apply before pagination.
- Compare one symbol across three dates and confirm historical indicators are not repeated current values.
- Confirm latest historical row matches current bar price and volume.
- Confirm `next_day_return` equals next trading close vs selected close for old rows.
- Confirm `/api/refresh/status?market=US` and `/api/refresh/status?market=INDIA` are independent.
- Confirm cancel sends and honors the selected market.
- Use `EXPLAIN QUERY PLAN` for slow screener queries.

## Sources For Performance Guidance

- SQLite WAL: https://sqlite.org/wal.html
- SQLite query planner: https://sqlite.org/queryplanner.html
- SQLite `EXPLAIN QUERY PLAN`: https://www.sqlite.org/eqp.html
- pandas performance: https://pandas.pydata.org/docs/user_guide/enhancingperf.html
- JAX JIT: https://docs.jax.dev/en/latest/jit-compilation.html
