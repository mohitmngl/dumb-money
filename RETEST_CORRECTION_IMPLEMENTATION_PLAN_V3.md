# OLD_SWING_RETEST_SCORE — Correction Implementation Plan V3

**Date**: 2026-08-02
**Status**: FINAL PLAN — awaiting approval
**Repository**: C:\Users\Admin\Desktop\stock test\open code v5 claude prompt
**Current HEAD**: c57085f
**Model**: Agnes 2.5 Flash

---

## 1. Verified Current-Score Reconciliation Counts

### Top 50 Reconciliation Results

| Classification | Count | Description |
|----------------|-------|-------------|
| VALUE_MISMATCH | 47 | DB has old score, engine computes different value |
| STALE_DB_SCORE | 2 | DB has score, engine returns NULL |
| MATCH | 1 | DB and engine agree (JHX: 24.21 vs 24.65) |
| MISSING_DB_SCORE | 0 | Engine has score, DB is NULL |
| MODEL_UNAVAILABLE | 0 | Model not loaded |
| DATA_INSUFFICIENT | 0 | Less than 60 bars |
| COMPUTATION_ERROR | 0 | Exception during fold |

### Full Reconciliation (Top 1,557)
**Status**: NOT YET COMPLETED — requires batch processing of all symbols.
**Estimated time**: ~15 minutes for full reconciliation.
**Artifact**: `RETEST_CURRENT_SCORE_RECONCILIATION.csv` (generated in progress)

### Key Finding
**The V2 plan was WRONG** to claim "all 1,557 scores are stale." The actual situation is:
- **47/50 top scores are VALUE_MISMATCH** — engine computes different values due to model retraining
- **2/50 are truly stale** — event terminated, score should be NULL
- **1/50 matches** — consistent scoring

This means the primary issue is **score caching**, not score staleness.

---

## 2. Exact Database Persistence Root Cause

### Bug #1: Lazy Endpoint Cache Shortcut (CRITICAL)
**File**: `dumbmoney/app.py`
**Function**: `api_stock_retest_score()`
**Lines**: 838-840

```python
# CURRENT (BUGGY):
row = conn.execute("SELECT old_swing_retest_score FROM stats WHERE symbol=?", (symbol,)).fetchone()
if row and row[0] and row[0] > 0:
    return jsonify({"symbol": symbol, "old_swing_retest_score": row[0], "cached": True})
```

**Problem**: If DB has any positive score, return it immediately WITHOUT recomputing. The engine's latest computation is ignored forever.

**Reproducible**: SONO has DB=66.38, engine computes 44.43. Lazy endpoint returns 66.38.

### Bug #2: NaN Converted to 0 (HIGH)
**File**: `dumbmoney/app.py`
**Line**: 853

```python
# CURRENT (BUGGY):
score_val = 0.0 if score is None or (isinstance(score, float) and np.isnan(score)) else round(float(score), 2)
```

**Problem**: NaN → 0.0 violates NULL semantics. Should be None.

### Bug #3: Schema Default is 0 (LOW)
**File**: `dumbmoney/db.py`
**Lines**: 312, 316, 320, 324

```sql
old_swing_retest_score REAL DEFAULT 0
```

**Problem**: New symbols get 0 instead of NULL.

### Fix Summary
| File | Line | Current | Proposed |
|------|------|---------|----------|
| app.py | 839 | `if row and row[0] and row[0] > 0:` | Remove cache shortcut |
| app.py | 853 | `score_val = 0.0 if ...` | `score_val = None if ...` |
| db.py | 312 | `DEFAULT 0` | `DEFAULT NULL` |
| db.py | 316 | `DEFAULT 0` | `DEFAULT NULL` |
| db.py | 320 | `DEFAULT 0` | `DEFAULT NULL` |
| db.py | 324 | `DEFAULT 0` | `DEFAULT NULL` |

---

## 3. Errors in V2 Plan and Their Corrections

### ERROR V2-1: Claimed All Scores Are Stale (CORRECTED)
**V2**: "All 1,557 non-null scores are stale"
**V3**: **FALSE** — 47/50 are VALUE_MISMATCH due to model retraining, not staleness. Only 2/50 are truly stale.

### ERROR V2-2: Proposed Setting original_score = None on Termination (FORBIDDEN)
**V2**: "Set c.original_score = None when event terminates"
**V3**: **FORBIDDEN** — ORIGINAL_RETEST_SCORE is immutable after confirmation. Must remain stored.

### ERROR V2-3: Score Semantics Unclear (CORRECTED)
**V2**: "Score is most recent confirmed event"
**V3**: **CORRECTED** — Score is bar-level: numeric ONLY on confirmation bar, NULL elsewhere.

### ERROR V2-4: SQL NULL vs Zero (CORRECTED)
**V2**: "AAPL score 0 is correct"
**V3**: **FALSE** — No setup must be SQL NULL, not 0. Zero is a valid model percentile.

### ERROR V2-5: Pre-Retest OVEREXTENDED (REMOVED)
**V2**: "OVEREXTENDED when price > level + 3 ATR"
**V3**: **REMOVED** — Large departure is positive. Only ENTRY_TOO_FAR at confirmation matters.

### ERROR V2-6: Future-Looking Peak (CORRECTED)
**V2**: "high[t] >= high[t+1]"
**V3**: **CORRECTED** — Use causal running maximum, freeze at touch.

### ERROR V2-7: Inconsistent ATR Usage (CORRECTED)
**V2**: Mixed ATR conventions
**V3**: **CORRECTED** — Strict separation: BREAKOUT_ATR, TOUCH_ATR, SIGNAL_ATR

### ERROR V2-8: Inconsistent State Names (CORRECTED)
**V2**: TARGET_REACHED vs TARGET_COMPLETED, INVALIDATED vs STRUCTURALLY_INVALIDATED
**V3**: **CORRECTED** — Single consistent vocabulary

### ERROR V2-9: Auto Historical Rebuild (FORBIDDEN)
**V2**: "Trigger rebuild on version bump"
**V3**: **FORBIDDEN** — Must be manual, checkpointed, shadow-based

### ERROR V2-10: Arbitrary Performance Estimates (REMOVED)
**V2**: "10x faster", "37 hours total"
**V3**: **REMOVED** — Must measure first, no promises

---

## 4. Correct Score-Field Separation

### Four Separate Fields

| Field | Type | When Numeric | When NULL | Purpose |
|-------|------|--------------|-----------|---------|
| `original_retest_score` | float | Always after confirmation | Before confirmation | Immutable historical score |
| `old_swing_retest_score` | float | Confirmation bar only | All other bars | Main screener column |
| `active_trade_score` | float | During active trade | No active trade | Optional trade monitoring |
| `retest_state` | text | Always | Never | Current event state |

### Bar-Level Score Series

```python
new_entry_score[bar_index] =
    original_score if bar_index == confirmation_index AND gates_passed AND entry_distance <= 0.75
    else NaN
```

**Rules**:
- Confirmation bar: numeric
- Next completed bar: NULL
- Active trade later: NULL in main column
- Completed trade: NULL
- Waiting setup: NULL
- No setup: NULL

**No freshness decay in main column.**

---

## 5. Correct Main Score Semantics

### OLD_SWING_RETEST_SCORE Definition
```
= numeric score on the confirmation bar ONLY
= NULL on all other bars
= NULL if event terminated before confirmation
= NULL if event terminated after confirmation (TARGET, STOP, EXPIRED)
```

### Key Distinction
- **original_retest_score**: Immutable, stored forever
- **old_swing_retest_score**: Bar-level, only numeric on confirmation bar
- **active_trade_score**: Optional, for trade monitoring

---

## 6. Correct State Vocabulary

### Required State Names
```
NO_BREAKOUT
BREAKOUT_CONFIRMED
WAITING_FOR_DEPARTURE
DEPARTURE_ESTABLISHED
WAITING_FOR_RETURN
ACTIVE_RETEST
WAITING_FOR_CONFIRMATION
CONFIRMED_RETEST
POST_ENTRY_ACTIVE
FAILED_BREAKOUT
RECOVERY_FROM_BELOW
STRUCTURALLY_INVALIDATED
TARGET_COMPLETED
STOPPED_OUT
EXPIRED
ENTRY_TOO_FAR
```

### Consistency Rules
- Use TARGET_COMPLETED (not TARGET_REACHED)
- Use STRUCTURALLY_INVALIDATED (not INVALIDATED)
- Use FAILED_BREAKOUT (not FAILED)
- ENTRY_TOO_FAR is a rejection reason, not an engine state

---

## 7. Correct Transition Table

| From State | Condition | To State | Reason Code | Score Effect | Terminal |
|------------|-----------|----------|-------------|--------------|----------|
| NO_BREAKOUT | Valid breakout (age>=20, quality) | BREAKOUT_CONFIRMED | breakout_valid | NULL | No |
| BREAKOUT_CONFIRMED | Immediately | WAITING_FOR_DEPARTURE | departure_start | NULL | No |
| BREAKOUT_CONFIRMED | close < level - 0.25*ATR | FAILED_BREAKOUT | below_level | NULL | Yes |
| BREAKOUT_CONFIRMED | 2 consecutive closes below level | FAILED_BREAKOUT | two_closes_below | NULL | Yes |
| WAITING_FOR_DEPARTURE | max_dist >= 1.75*ATR, 3+ closes >= level+0.50*ATR | DEPARTURE_ESTABLISHED | departure_established | NULL | No |
| WAITING_FOR_DEPARTURE | close < level - 0.25*ATR | FAILED_BREAKOUT | below_level_pre_departure | NULL | Yes |
| WAITING_FOR_DEPARTURE | delay > 60 bars | EXPIRED | no_departure_60 | NULL | Yes |
| DEPARTURE_ESTABLISHED | Price starts declining, running peak exists | WAITING_FOR_RETURN | return_started | NULL | No |
| WAITING_FOR_RETURN | Price enters retest zone from ABOVE | ACTIVE_RETEST | touch_from_above | NULL | No |
| WAITING_FOR_RETURN | Approach from below (<2 closes above) | RECOVERY_FROM_BELOW | approach_from_below | NULL | No |
| ACTIVE_RETEST | Level touched (both bounds) | WAITING_FOR_CONFIRMATION | touch_valid | NULL | No |
| ACTIVE_RETEST | close < level - 0.60*ATR | STRUCTURALLY_INVALIDATED | structural_invalid | NULL | Yes |
| WAITING_FOR_CONFIRMATION | close >= level - 0.10*ATR within 3 bars | CONFIRMED_RETEST | confirm_valid | original_score set | No |
| WAITING_FOR_CONFIRMATION | No confirm within 3 bars | FAILED_BREAKOUT | no_confirmation | NULL | Yes |
| WAITING_FOR_CONFIRMATION | close < level - 0.60*ATR | STRUCTURALLY_INVALIDATED | confirm_invalid | NULL | Yes |
| CONFIRMED_RETEST | entry_distance > 0.75 | ENTRY_TOO_FAR | entry_too_far | NULL | Yes |
| CONFIRMED_RETEST | All gates pass | POST_ENTRY_ACTIVE | entry_valid | original_score frozen | No |
| POST_ENTRY_ACTIVE | future high >= entry + 2.0*SIGNAL_ATR | TARGET_COMPLETED | target_hit | NULL | Yes |
| POST_ENTRY_ACTIVE | future low <= entry - 0.75*SIGNAL_ATR | STOPPED_OUT | stop_hit | NULL | Yes |
| POST_ENTRY_ACTIVE | 20 bars elapsed | EXPIRED | timeout_20 | NULL | Yes |
| POST_ENTRY_ACTIVE | close < level - 0.60*SIGNAL_ATR | STRUCTURALLY_INVALIDATED | post_invalid | NULL | Yes |

---

## 8. Correct ATR Conventions and Formulas

### Three Separate ATR Values
```python
BREAKOUT_ATR  # Frozen at breakout bar
TOUCH_ATR     # Frozen at touch bar
SIGNAL_ATR    # Frozen at confirmation bar
```

### Usage Rules
| Operation | ATR to Use |
|-----------|------------|
| Breakout threshold | BREAKOUT_ATR |
| Departure distance | BREAKOUT_ATR |
| Accepted closes | BREAKOUT_ATR |
| Running peak distance | BREAKOUT_ATR |
| Pullback from peak | BREAKOUT_ATR |
| Pre-departure failed-breakout | BREAKOUT_ATR |
| Retest bounds | TOUCH_ATR |
| Touch penetration | TOUCH_ATR |
| Pre-confirmation invalidation | TOUCH_ATR |
| Entry distance | SIGNAL_ATR |
| Target | SIGNAL_ATR |
| Stop | SIGNAL_ATR |
| Post-entry MFE/MAE | SIGNAL_ATR |

### Correct Feature Formulas
```python
departure_high_distance_atr = (max_high_after_breakout - level) / BREAKOUT_ATR
departure_close_distance_atr = (max_close_after_breakout - level) / BREAKOUT_ATR
pullback_from_peak_atr = (frozen_peak_price - touch_low) / BREAKOUT_ATR
entry_distance_atr = (confirmation_close - level) / SIGNAL_ATR
```

---

## 9. Correct Departure/Peak/Pullback/Approach Gates

### Departure Gate
```python
# Must have:
- max_dist >= 1.75 * BREAKOUT_ATR
- 3+ closes >= level + 0.50 * BREAKOUT_ATR
- At least 8 bars after breakout
```

### Peak Gate (Causal Running Maximum)
```python
# At each bar t after breakout:
running_peak_price = max(high[breakout_idx:t+1])
running_peak_date = date of max

# At retest touch:
frozen_peak_price = running_peak_price
frozen_peak_date = running_peak_date
```

### Pullback Gate
```python
# Must have:
- pullback_from_peak_atr >= 1.0
- retest_date > peak_date
```

### Approach-from-Above Gate
```python
# Must have:
- 3+ of previous 5 closes >= level + 0.30 * BREAKOUT_ATR
- No close below level - 0.10 * BREAKOUT_ATR in previous 3 bars
- Short slope into touch is non-positive
```

---

## 10. Verified Positive Reference

### Status: NOT YET LOCATED
**Requirement**: Find a real local-data event demonstrating:
- Old resistance
- Breakout
- Expansion several ATR above level
- Separation for multiple bars
- Later pullback
- Return from above
- Strict support touch
- Confirmation near level

**Action**: Phase 0 must locate this from local OHLCV data.

**Artifacts to produce**:
- `RETEST_VERIFIED_POSITIVE_REFERENCE.csv`
- `RETEST_VERIFIED_POSITIVE_REFERENCE.png`

---

## 11. Safe Emergency Stale-Score Repair Plan

### DO NOT RUN:
```sql
UPDATE stats SET old_swing_retest_score = NULL WHERE old_swing_retest_score > 0
```

### Required Steps:
```
E0.1: Back up screener.db
E0.2: Recompute current engine score for every non-null DB row
E0.3: Write reconciliation to CSV and shadow column (_v2)
E0.4: Manual review of:
      - MATCH (keep)
      - STALE_DB_SCORE (clear to NULL)
      - VALUE_MISMATCH (clear to NULL, will be recomputed)
      - COMPUTATION_ERROR (investigate)
E0.5: After explicit approval, atomically update:
      SET old_swing_retest_score_v2 = CASE
          WHEN engine_score IS NULL THEN NULL
          ELSE engine_score
      END
E0.6: Never modify original historical event scores
E0.7: Provide rollback SQL and backup path
```

---

## 12. Shadow-First Implementation Order

### PHASE E0: Read-Only Reconciliation
- Complete full reconciliation of all 1,557 scores
- Produce `RETEST_CURRENT_SCORE_RECONCILIATION.csv`
- Produce `RETEST_DB_PERSISTENCE_TRACE.md`
- **No code changes**

### PHASE 1: Fix DB Persistence Bugs
- Remove cache shortcut in lazy endpoint
- Fix NaN → 0 conversion
- Change schema defaults to NULL
- **Tests**: 4 unit tests for NULL semantics

### PHASE 2: Reference Causal Engine (Feature Flag)
- Implement new state machine in isolated module
- Behind feature flag: `ENABLE_RETEST_V2_ENGINE = False`
- **Tests**: 40 structural tests

### PHASE 3: Structural Tests and Golden Charts
- 40 unit tests
- Golden chart validation
- Causality tests
- **Tests**: Prefix invariance, incremental equivalence

### PHASE 4: Entry and Outcome Corrections
- Fix target detection (high vs close)
- Fix outcome scanning start
- Add next-open sensitivity
- **Tests**: Tests 16-20

### PHASE 5: Prefix Invariance and Incremental Equivalence
- Test A = fold full, read at t
- Test B = fold truncated at t
- Assert equality
- **Tests**: Tests 32, 34

### PHASE 6: Shadow Tables
- Add _v2 columns
- Write to shadow, not production
- NULL semantics enforced
- **Tests**: Tests 36-40

### PHASE 7: Measured Candidate Funnel
- Run engine on all symbols
- Count events at each stage
- **No estimates, only measurements**

### PHASE 8: Human Visual Review
- 400 samples reviewed
- Golden charts validated
- **No code changes**

### PHASE 9: Feature Audit and Rebuild
- Update feature extraction
- Remove constants
- Add new features
- Verify training/inference parity
- **Tests**: Test 33

### PHASE 10: Clean Training Dataset
- Run engine with new gates
- Collect events
- Assess count
- **No model training yet**

### PHASE 11: Walk-Forward Model Comparison
- Baseline (structure only)
- Logistic regression
- CatBoost
- Learning-to-rank
- **Tests**: Validation metrics

### PHASE 12: Historical Percentile Mapping
- Build CDF from prior folds
- Map raw scores to percentiles
- Save mapping with model
- **No production changes**

### PHASE 13: Top-K and Score-Decile Validation
- Precision@K metrics
- Decile analysis
- Lift over baseline
- **Tests**: Top-10 precision >= baseline

### PHASE 14: Close-Entry and Next-Open Backtests
- Separate equity curves
- Report both independently
- **No production changes**

### PHASE 15: Limited Shadow Rebuild
- 100 symbols
- Timing measurement
- Validation
- **No production changes**

### PHASE 16: Full Shadow Rebuild
- All symbols
- Checkpointed
- Resumable
- **No production changes**

### PHASE 17: Explicit Production Switch
- Manual approval
- Backup created
- Switch executed
- Verification
- **Final step only**

---

## 13. Tests

### Required Test Suite (40 tests)
1. test_causal_pivot_confirmation
2. test_minimum_level_age
3. test_breakout_identity
4. test_failed_breakout_before_departure
5. test_departure_not_established_below_threshold
6. test_departure_established_after_threshold
7. test_distinct_peak_required
8. test_retest_after_peak
9. test_minimum_pullback_from_peak
10. test_approach_from_above_accepted
11. test_approach_from_below_rejected
12. test_shallow_breakout_wiggle_rejected
13. test_repeated_crossing_rejected
14. test_strict_retest_bounds
15. test_delayed_confirmation
16. test_close_entry_semantics
17. test_signal_candle_excluded_from_outcome
18. test_target_uses_future_high
19. test_stop_uses_future_low
20. test_same_bar_ambiguity_conservative
21. test_entry_distance_hard_gate
22. test_new_entry_visible_only_latest
23. test_score_disappears_after_newer
24. test_target_completed_not_new_entry
25. test_stopped_out_not_new_entry
26. test_invalidated_not_new_entry
27. test_overextended_not_new_entry
28. test_expired_not_new_entry
29. test_failed_cycle_cannot_revive
30. test_new_breakout_new_event_id
31. test_no_duplicate_multibar_retest
32. test_prefix_invariance
33. test_training_inference_feature_equality
34. test_incremental_refresh_equals_full
35. test_refresh_idempotence
36. test_null_vs_zero_semantics
37. test_database_stale_score_clearing
38. test_api_ui_latest_date_behaviour
39. test_model_unavailable_not_zero
40. test_historical_asof_score_correctness

---

## 14. Model and Validation Pipeline

### Model Alternatives to Compare
A. Two-class classifier (WIN vs DEEP_DRAWDOWN, TIMEOUT excluded)
B. Two-stage model (barrier event vs timeout, then win vs drawdown)
C. Competing-risk/survival design
D. Date-grouped learning-to-rank
E. Transparent deterministic structural baseline

### Validation Metrics (No Fixed Thresholds)
- Top-1, top-5, top-10, top-25, top-50 precision
- Lift over unconditional valid-candidate rate
- Score-decile ordering
- MFE and MAE by score band
- Target speed by score decile
- Stability across folds
- Confidence intervals
- Untouched holdout performance

### Historical Percentile Mapping
```python
# For each walk-forward fold:
1. Generate raw utility out of sample
2. Build empirical CDF using only prior out-of-sample utilities
3. Map new candidate's raw utility into prior distribution
4. Save mapping with model artifact
5. Never use future events in mapping
```

---

## 15. Production-Switch Procedure

### Prerequisites
- [ ] All 40 tests pass
- [ ] Shadow data validated
- [ ] Human review complete (400 samples)
- [ ] Performance benchmarks acceptable
- [ ] Backup created
- [ ] Explicit approval received

### Switch Steps
1. Run emergency repair (E0.1-E0.7)
2. Verify shadow columns populated
3. Compare shadow vs production (sample)
4. Execute switch:
   ```sql
   ALTER TABLE stats RENAME COLUMN old_swing_retest_score TO old_swing_retest_score_legacy;
   ALTER TABLE stats RENAME COLUMN old_swing_retest_score_v2 TO old_swing_retest_score;
   ```
5. Verify production scores
6. Run full test suite
7. Monitor for 24 hours

### Rollback
```sql
ALTER TABLE stats RENAME COLUMN old_swing_retest_score TO old_swing_retest_score_v2;
ALTER TABLE stats RENAME COLUMN old_swing_retest_score_legacy TO old_swing_retest_score;
```

---

## 16. Rollback Plan

### Code Rollback
```bash
git revert <commit-hash>
```

### Data Rollback
- Shadow columns preserve old values
- Legacy column preserved during switch
- Backup available

### Model Rollback
- Keep old model at `models/retest_v1_backup/`
- Feature flag can disable new engine

### Emergency Stop
```python
# In retest_config.py:
ENABLE_RETEST_V2_ENGINE = False  # Falls back to old behavior
```

---

## 17. Performance Benchmark Plan

### Required Measurements
```
1. 10 symbols: engine, feature, inference, DB time
2. 100 symbols: same
3. 1,000 symbols: same
4. Full market: same
5. Peak memory
6. Worker count (Windows multiprocessing)
```

### Report Format
| Batch | Engine | Feature | Inference | DB | Memory |
|-------|--------|---------|-----------|-----|--------|
| 10 | ? | ? | ? | ? | ? |
| 100 | ? | ? | ? | ? | ? |
| 1000 | ? | ? | ? | ? | ? |
| Full | ? | ? | ? | ? | ? |

**No promises until measured.**

---

## 18. Phase 0 Artifacts

### Required Artifacts
- [x] `RETEST_PHASE0_AUDIT/AUDIT_REPORT.md`
- [x] `RETEST_PHASE0_AUDIT/event_traces.json`
- [x] `RETEST_PHASE0_AUDIT/detailed_traces.json`
- [x] `RETEST_PHASE0_AUDIT/event_score_traces.json`
- [ ] `RETEST_PHASE0_AUDIT/RETEST_CURRENT_SCORE_RECONCILIATION.csv` (in progress)
- [ ] `RETEST_PHASE0_AUDIT/RETEST_DB_PERSISTENCE_TRACE.md` (created)
- [ ] `RETEST_VERIFIED_POSITIVE_REFERENCE.csv` (pending)
- [ ] `RETEST_VERIFIED_POSITIVE_REFERENCE.png` (pending)

---

## 19. File Change Summary

### Files to Change (Read-Only Diagnostic Phase)
| File | Change | Reason |
|------|--------|--------|
| `dumbmoney/app.py` | Remove cache shortcut, fix NaN→0 | Fix persistence bugs |
| `dumbmoney/db.py` | Change DEFAULT 0 to NULL | Correct NULL semantics |
| `dumbmoney/retest_engine.py` | New state machine (feature flag) | Structural fix |
| `dumbmoney/engine.py` | Use shadow columns | Safe migration |
| `tests/test_retest_engine.py` | Add 28 new tests | Coverage |
| `tests/test_retest_labels.py` | Add 12 new tests | Coverage |

### Files to Create
| File | Purpose |
|------|---------|
| `dumbmoney/retest_engine_v2.py` | New causal engine (feature flag) |
| `tests/test_retest_v2.py` | Structural tests |
| `RETEST_PHASE0_AUDIT/*.csv` | Evidence artifacts |

---

## 20. Final Checklist

### Before Phase 1
- [ ] Full reconciliation complete (all 1,557 symbols)
- [ ] Positive reference located and verified
- [ ] DB persistence trace documented
- [ ] All Phase 0 artifacts complete

### Before Phase 2
- [ ] Feature flag implemented
- [ ] New engine isolated from production
- [ ] 40 tests pass

### Before Phase 17 (Production Switch)
- [ ] Shadow data validated
- [ ] Human review complete
- [ ] Performance benchmarks acceptable
- [ ] Backup created
- [ ] Explicit approval received

---

## End of V3 Plan
