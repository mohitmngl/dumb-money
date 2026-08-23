# RETEST CALL GRAPH (pre-rebuild map — PHASE 0)

Mapped 2026-08-01 from the current codebase (pre-rebuild state).

## Entry points (live code)

- `dumbmoney/engine.py:16` `from dumbmoney.retest_engine import compute_retest_score_for_symbol, compute_retest_score_current`
- `dumbmoney/engine.py:229-232` — stats pass (current score, eager per-symbol, silent except -> 0.0)
- `dumbmoney/engine.py:592-595` — historical screener frame (per-bar series, fillna(0))
- `dumbmoney/app.py:831-858` — `GET /api/stock/<symbol>/retest-score` lazy endpoint (cached-0 "no event" ambiguity; recompute on stale)

## Read/write surfaces (live)

- `dumbmoney/app.py:64` — columns contract meaning text ("ML-scored 0-100 ... NaN/0 means no active retest")
- `dumbmoney/app.py:420-423,627-630` — `min_retest_score` filter (historical + stats)
- `dumbmoney/app.py:460,477,652,685` — sort allowlist + SELECT columns
- `dumbmoney/db.py:31,61,161,176` — schema defaults `old_swing_retest_score REAL DEFAULT 0`
- `dumbmoney/db.py:310-324` — migration adding the column (DEFAULT 0)

## Legacy consumers (now archived to legacy/)

- `legacy/migrate_retest_score.py` — backfill (BUG-laden)
- `legacy/retest_train.py` — trainer (BUG B: bar indices as zone indices)
- `legacy/_migrate.py` — earlier migration attempt
- `legacy/test_migrate_small.py` — ad-hoc migration test (plain script)

## Model artifact consumers (quarantined)

- `models/retest_legacy_v1/US|INDIA/*` — 19 files, trained on corrupt features; `legacy/retest_models.py:18` MODEL_DIR pointed here

## New architecture (replacing all of the above)

- `dumbmoney/retest_config.py` — constants (single source of truth)
- `dumbmoney/retest_engine.py` — causal event-state fold; per-bar CURRENT/ORIGINAL; event records; labels (close-entry)
- `dumbmoney/retest_models.py` — walk-forward training + inference, percentile mapping, manifest
- `retest_train.py` — trainer entry
- `dumbmoney/retest_rebuild.py` — PHASE 10/11 rebuild (replaces migrate_retest_score.py)
- `dumbmoney/retest_backtest.py`, `dumbmoney/retest_golden.py` — PHASE 9/6
- `tests/` — stdlib unittest suite
- `models/retest/<MARKET>/v2/` — new validated artifacts (registered in retest_model_manifest.json)
- DB: `retest_events`, `retest_engine_state`, stats diagnostic columns

## Wiring map (new)

| Context | New path |
|---|---|
| stats pass current score (engine.py:229) | `fold_symbol()` last-bar CURRENT |
| historical frame (engine.py:592) | `fold_symbol()` per-bar CURRENT |
| lazy endpoint (app.py:831) | status enum: VALID/NO_SETUP/MODEL_UNAVAILABLE/DATA_INSUFFICIENT/COMPUTATION_ERROR |
| refresh (refresh.py stats loop) | event fold + `retest_events` upsert + diagnostic columns |
| training (retest_train.py) | event dataset from `retest_events` + fold |
