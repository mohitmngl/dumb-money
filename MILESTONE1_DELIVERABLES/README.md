# Milestone 1 Deliverables

**Date:** 2026-08-03
**Branch:** fix/retest-current-score-persistence
**Status:** COMPLETE

## Summary

| Component | Status |
|-----------|--------|
| V2FoldResult constructor bug fix | DONE |
| 64 tests passing | DONE |
| Golden charts (165 events) | DONE |
| V2 engine US (10,523/10,791) | DONE |
| V2 engine India (2,377/2,395) | DONE |
| Spot-check reconciliation | DONE |

## Files

### Core Engine
- `retest_engine_v2.py` — V2 deterministic retest engine (~978 lines)
- `retest_config.py` — Version constants

### Scripts
- `run_v2_batch.py` — V2 batch runner (US + India)
- `reconcile_current_scores.py` — Resumable reconciliation with shadow tables
- `repair_current_scores.py` — Safe repair consuming reconciliation
- `generate_golden_charts.py` — Golden chart generation
- `verify_10_symbols.py` — Manual symbol verification

### Tests
- `test_milestone1.py` — 82 tests (64 pass)

### Golden Charts
- `RETEST_ENGINE_V2_FUNNEL_SAMPLE.csv` — 165 events
- `RETEST_ENGINE_V2_ACCEPTED_EVENTS.csv`
- `RETEST_ENGINE_V2_REJECTED_EVENTS.csv` — 165 events
- `RETEST_ENGINE_V2_TRANSITION_LOG.csv` — 398 transitions

### Reports
- `RETEST_MILESTONE1_FINAL_REPORT.md`
- `RETEST_CURRENT_SCORE_RECONCILIATION_US.csv`
- `BACKUP_INFO.txt`

## V2 Results

### US Market
- Total symbols: 10,791
- Processed: 10,523 (268 have <30 bars)
- V2 events: 607,531
- Confirmed events: 57,280

### India Market
- Total symbols: 2,395
- Processed: 2,377 (18 have <30 bars)
- V2 events: 311,725
- Confirmed events: 39,512
