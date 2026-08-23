# LEGACY RETEST IMPLEMENTATION — ARCHIVED (NOT TO BE USED)

Archived verbatim on 2026-08-01 as part of the OLD_SWING_RETEST_SCORE rebuild (RETEST_AUDIT.md).
These files are the **buggy legacy implementation** (audit bugs A–J). They are retained for
reference only. Do NOT import, run, load models from, or migrate data using anything in this
directory. New implementations replace the originals in place:

- `dumbmoney/retest_engine.py`  -> new causal event-state engine
- `dumbmoney/retest_models.py`  -> new walk-forward models
- `retest_train.py`             -> new walk-forward trainer

## SHA-256 hashes (verbatim copies)

| File | SHA-256 |
|---|---|
| dumbmoney/retest_engine.py | 801A2728B81CBBA5336F5561E22E8ED46AFE811A66D409AB8449BEABA30E3DC3 |
| dumbmoney/retest_models.py  | 1E5D89ACA7929575AE04D644E11D4DF653795242D9F837990DE40A2733DA6E8F |
| retest_train.py             | 8124020BABC2B871EF6FB00E3CE747F00CA93559F0277A96BD60CB8BA4127606 |
| migrate_retest_score.py     | see checkpoint manifest (retest_checkpoint_20260801_145606) |
| _migrate.py                 | see checkpoint manifest |
| test_migrate_small.py       | see checkpoint manifest |

Checkpoint copy of every archived/related file: `retest_checkpoint_20260801_145606/`.

## Known defects (see RETEST_AUDIT.md sections 1–9)

- BUG A: swing/higher-high detection uses `zscore-1.25` threshold instead of causal pivots
- BUG B: `bk_zone_idx[retest_bar]` passes *bar indices* as *zone indices* (corrupt features/labels)
- BUG C: MFE/MAE/days-to-target counted with Monday's high/low even when entry was Friday's close
- BUG D: same-candle target+stop counted as WIN
- BUG E: "fake resistance" = 1.5x current price instead of real overhead resistance
- BUG F: placeholder feature values (0.0 / 0.5 / 0.01) leak into training
- BUG G: 5d-momentum "speed" utility formula multiplies the percentile
- BUG H: percentile from OOF fit over full dataset (future leakage)
- BUG I: 250-session rolling regression instead of walk-forward with embargo
- BUG J: `models/retest/US` + `INDIA` artifacts trained on corrupt features

## Disabled legacy call sites (all now point to the new engine)

| Location | Legacy call | Replacement |
|---|---|---|
| dumbmoney/engine.py:16,229,592 | compute_retest_score_for_symbol / compute_retest_score_current | fold_symbol per-bar scores |
| dumbmoney/app.py:851-852 | compute_retest_score_current | retest status endpoint (new) |
| migrate_retest_score.py:53 | legacy backfill | retest_rebuild.py (PHASE 10/11) |
| retest_train.py:203 | legacy training | retest_train.py (PHASE 7 rewrite) |
| dumbmoney/retest_models.py:18 | MODEL_DIR=models/retest | models/retest/<market>/v2 (new) |
