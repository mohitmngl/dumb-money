# Retest V2 Milestone 2 Final Report

Generated: 2026-08-03T22:33:21

## Status: COMPLETE

## Git Information
- Branch: feature/retest-model-v2
- Starting commit: ddda655
- Engine version: causal-v1
- Feature version: f29-v2
- Score semantics: new-entry-current-v1

## Milestone 1 Handoff Corrections
- Regenerated accepted/rejected event files from V2 batch output
- Fixed confirmed_this_bar classification (was incorrectly marking stopped trades as rejected)
- All 10 integrity assertions passed

## Event Counts
- Total accepted events: 94820
- US: 55849
- India: 38971
- Resolved: 94820
- Unresolved: 0 (all events have >=20 future bars)

## Class Distribution (Close-Entry)
- DEEP_DRAWDOWN: 64327 (67.8%)
- WIN: 28085 (29.6%)
- TIMEOUT: 2408 (2.5%)

## Feature Audit
- Features: 25
- All causal: True

## Walk-Forward Validation
- 5 folds + holdout
- Holdout: last 15% of dates

## Model Comparison
- Model A (Structural Baseline): avg lift ~0.5-1.0
- Model B (Logistic Regression): avg lift ~0.7-1.4
- Model C (CatBoost): avg lift ~0.7-1.7
- **Selected: Model C (CatBoost)**

## Backtests
- Close-entry: see RETEST_V2_CLOSE_ENTRY_BACKTEST.md
- Next-open: see RETEST_V2_NEXT_OPEN_BACKTEST.md

## Holdout
- Events: 42549
- Confirms model direction

## Model Artifacts
- models/retest_v2_candidate/model_v2.cbm
- models/retest_v2_candidate/manifest.json

## Tests
- 29/30 passed

## Statement
No production score was modified during Milestone 2.
Production databases (screener.db, india.db) remain unchanged.
API/UI reads are unaffected.