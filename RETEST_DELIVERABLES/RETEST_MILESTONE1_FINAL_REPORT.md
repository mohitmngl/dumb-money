# RETEST_MILESTONE1_FINAL_REPORT.md

## Status: IN PROGRESS

## Starting State

- **Branch:** `fix/retest-current-score-persistence`
- **Starting Commit:** `c5e7771` (Milestone 1 partial: fix NULL semantics)
- **Date:** 2026-08-02

## Files Changed

| File | Change |
|------|--------|
| `dumbmoney/retest_engine_v2.py` | New V2 engine with full state machine |
| `dumbmoney/retest_config.py` | Added version constants |
| `dumbmoney/app.py` | Fixed lazy endpoint with NULL semantics |
| `dumbmoney/db.py` | Changed schema defaults to NULL |
| `dumbmoney/templates/stock_detail.html` | Fixed null display |
| `scripts/reconcile_current_scores.py` | Resumable reconciliation with proper precedence |
| `scripts/repair_current_scores.py` | Safe repair consuming reconciliation |
| `scripts/generate_golden_charts.py` | Golden chart generation |
| `tests/test_milestone1.py` | 82 comprehensive tests |

## Test Results

```
Ran 82 tests in 0.839s
OK
```

## Part A: Current-Score Persistence Repair

### Root Cause
1. Lazy endpoint cache shortcut returned stale positive scores
2. NaN → 0 conversion instead of SQL NULL
3. Schema DEFAULT 0 instead of NULL

### Fixes Applied
- Versioned cache validity with engine/model/feature/semantics versions
- NULL semantics: NaN/None → SQL NULL
- Schema defaults changed to NULL for new installations
- UI displays `—` for NULL scores

### Reconciliation Status Precedence
1. MODEL_UNAVAILABLE
2. COMPUTATION_ERROR
3. DATA_INSUFFICIENT
4. LEGACY_UNVERSIONED
5. VERSION_MISMATCH
6. MATCH
7. STALE_DB_SCORE
8. MISSING_DB_SCORE
9. VALUE_MISMATCH

## Part B: Corrected Deterministic Engine V2

### State Vocabulary
All 16 states implemented:
- NO_BREAKOUT, BREAKOUT_CONFIRMED, WAITING_FOR_DEPARTURE
- DEPARTURE_ESTABLISHED, WAITING_FOR_RETURN, ACTIVE_RETEST
- WAITING_FOR_CONFIRMATION, CONFIRMED_RETEST, POST_ENTRY_ACTIVE
- FAILED_BREAKOUT, RECOVERY_FROM_BELOW, STRUCTURALLY_INVALIDATED
- TARGET_COMPLETED, STOPPED_OUT, EXPIRED, ENTRY_TOO_FAR

### Key Features
- Frozen zone snapshots at breakout (causal)
- Departure requirements (8+ bars, 1.75 ATR, 3 accepted closes)
- Pullback minimum (1.0 ATR)
- Return-from-above validation
- Strict retest zone bounds (-0.50 to +0.40 ATR)
- Entry distance gate (0.75 ATR max)
- Confirmed-this-bar score emission
- Outcome: target uses high, stop uses low

## Pending

- [ ] Run full reconciliation for US and India
- [ ] Apply safe repair
- [ ] Generate golden charts
- [ ] Verify 10 manual symbols
- [ ] Main screener verification

## Rollback Command

```sql
-- Restore from rollback table
UPDATE stats SET old_swing_retest_score = (
    SELECT old_score FROM retest_current_score_rollback
    WHERE retest_current_score_rollback.symbol = stats.symbol
    AND repair_id = <REPAIR_ID>
) WHERE symbol IN (
    SELECT symbol FROM retest_current_score_rollback
    WHERE repair_id = <REPAIR_ID>
);
```

## Limitations

1. Full reconciliation not yet run (requires processing ~10,000 symbols)
2. Golden charts not yet generated
3. Historical_screener not modified (as required)
4. Model not retrained (as required)

## Next Steps

1. Run reconciliation: `python scripts/reconcile_current_scores.py --market US`
2. Review results
3. Apply repair: `python scripts/repair_current_scores.py --run-id <ID> --apply --confirm APPLY_CURRENT_RETEST_REPAIR`
4. Generate charts: `python scripts/generate_golden_charts.py`
5. Verify 10 symbols
6. Commit and report
