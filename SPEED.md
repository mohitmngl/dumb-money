# SPEED.md — READ THIS BEFORE ANY WEBSITE CHANGE

Owner's standing order: **the download/refresh flow and every filter must stay super-duper fast.**
Any change that touches data loading, refresh, screener filters, or the DBs must obey this file.
This complements `AGENTS.md` (which owns correctness/invariants); this file owns *speed*.

## The golden rules (in priority order)

1. **SQLite pragmas are already tuned in `dumbmoney/db.py::get_db()` — do not weaken them.**
   - `mmap_size=4GB` (OS caps at 2GB on this Windows box) → measured **6.8× faster** on the date-filter screener query (720ms → 106ms). If you add a new connection factory, copy ALL of: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=30000`, `temp_store=MEMORY`, `cache_size=-262144`, `mmap_size=4294967296`.
   - Never open a raw `sqlite3.connect()` for a read path without these pragmas.

2. **Filter → Count → Order → Limit, all in SQL. Never in Python.**
   - The screener already does this (`app.py` ~line 356/484). Keep it. Never `fetchall()` a big table and slice in pandas/Python.
   - Sort columns must go through the allowlist. Never string-concat user sort input into SQL.

3. **Refresh is incremental. Never full-scan for a normal refresh.**
   - Download bars only for symbols whose latest stored daily bar is stale (market-aware cutoff: skip weekends + US holidays).
   - Group incremental downloads by each symbol's own next-needed start date. One stale symbol must NOT drag a whole batch into years of history.
   - Pass `updated_symbols` through every step (stats, asset info, snapshots, earnings, historical). Empty list = no-op, NOT full recompute.
   - Never trigger `/api/historical/rebuild` or the signal-matrix rebuild from a normal refresh. Those are explicit maintenance only.

4. **Downloads: batch, cache, parallelize.**
   - Reuse the `assets` universe cache (up to 7 days) — do not hit Alpaca/NSE on every click.
   - Use the fast IEX listed-equity path for US; no OTC in the normal path.
   - Alpaca bars: request multiple symbols per HTTP call where the API allows; page with `next_page_token`; never one-symbol-per-request loops for the whole universe.
   - Bulk-insert bars with `executemany` in chunks (5–10k rows) inside ONE transaction. Never row-by-row `INSERT` inside a symbol/date loop.

5. **Progress cadence: emit a progress callback at least every ~1–2 seconds of work** so the UI never looks frozen. Every long network/pandas step needs a progress update and a cancellation checkpoint.

6. **Select only needed columns.** Never `SELECT *` on `bars` or `historical_screener`. Never load unrelated columns for the signal matrix (only the 7 it needs).

7. **Indexes: measure before adding.** The huge historical tables keep ONLY: PK `(symbol,date)`, `idx_hs_sym_date`, `idx_hs_date`, `idx_hs_date_sym`. Run `EXPLAIN QUERY PLAN` before adding any index — extra indexes previously made historical writes much slower and were removed.

## Fast-path checklist before you finish a website change
- [ ] Did I keep all `get_db()` pragmas (esp. `mmap_size`)?
- [ ] Is every filter/sort/paginate in SQL, not Python?
- [ ] Does a no-change refresh finish as a near-instant no-op (no downloads, no rebuild)?
- [ ] Are new downloads incremental + batched + chunked-insert?
- [ ] Does every slow step report progress and honor cancel + market scope?
- [ ] Did I `EXPLAIN QUERY PLAN` any query I changed on the 10M-row tables?

## Known measured numbers (baseline — beat these, never regress)
- Date-filter screener query (filter+order+limit on 10.5M-row US `historical_screener`): **~106 ms** warm with mmap. If yours is slower, you broke something.
- Current-mode screener (stats, ~10k rows): should be single-digit ms.
