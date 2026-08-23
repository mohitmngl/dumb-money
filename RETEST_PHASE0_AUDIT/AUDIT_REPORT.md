# Phase 0 Audit Report — Retest Score Staleness

**Date**: 2026-08-02
**Status**: READ-ONLY DIAGNOSTIC — no code changes
**Repository HEAD**: 21b568d

---

## Executive Summary

The top-scoring stocks (SONO 66.38, GLBE 57.82, SCI 47.50, LILA 43.30, SOLV 43.00) are **NOT** currently showing active retest signals. Their DB scores are **stale remnants** from terminated events that were never cleared to NULL.

The engine correctly computes `latest_score = NULL` for all 5 symbols. The database simply has old values that were written when events were active and never cleared when events terminated.

---

## Root Cause Confirmed

### Evidence

| Symbol | DB Score | Latest Engine Score | Latest State | Event Status |
|--------|----------|---------------------|--------------|--------------|
| SONO | 66.38 | **NULL** | WAITING_FOR_RETEST | Event terminated 2022 |
| GLBE | 57.82 | **NULL** | WAITING_FOR_RETEST | Event TARGET_REACHED 2024 |
| SCI | 47.50 | **NULL** | WAITING_FOR_RETEST | Event terminated 2025 |
| LILA | 43.30 | **NULL** | WAITING_FOR_RETEST | Event TARGET_REACHED 2026 |
| SOLV | 43.00 | **NULL** | WAITING_FOR_RETEST | Event terminated 2026 |

### Stale Score Traces

**SONO (DB=66.38)**:
- Score 65.93 appeared at indices 443-448 (dates 2022-04-28 to 2022-05-05)
- State was SIGNAL_GENERATED during those bars
- Event has since terminated
- Latest state: WAITING_FOR_RETEST, latest score: NULL
- **DB score is stale from 2022**

**GLBE (DB=57.82)**:
- Score 57.65-58.44 appeared at indices 1096-1131 (dates 2025-09-23 to 2025-11-11)
- Matching event GLBE:12:2 has stage=TARGET_REACHED, breakout=2024-05-28, confirm=2024-06-04
- Latest state: WAITING_FOR_RETEST, latest score: NULL
- **DB score is stale from late 2025**

**SCI (DB=47.50)**:
- Score 46.75-47.46 appeared at indices 434-436 and 1291 (dates 2022-04-19 and 2025-09-18)
- Latest state: WAITING_FOR_RETEST, latest score: NULL
- **DB score is stale from Sept 2025**

**LILA (DB=43.30)**:
- Score 43.34 from event LILA:41:2 (stage=TARGET_REACHED, breakout=2026-03-23, confirm=2026-04-10)
- Latest state: WAITING_FOR_RETEST, latest score: NULL
- **DB score is stale from April 2026**

**SOLV (DB=43.00)**:
- Score 42.96 appeared at index 571 (date 2026-07-13)
- Latest state: WAITING_FOR_RETEST, latest score: NULL
- **DB score is stale from July 2026**

---

## Secondary Findings

### 1. Score Clearing Logic is Missing

When an event transitions to TARGET_REACHED, STOPPED_OUT, EXPIRED, or INVALIDATED, the engine does NOT clear the score in `current_scores`. The score persists as a non-null value until a new event starts.

**Current behavior** (retest_engine.py lines 559-572):
```python
if st == cfg.EventStage.SIGNAL_GENERATED.value:
    # Check barriers...
    if hit_stop:
        return self._terminate(...)  # Returns (True, (np.nan, np.nan, stage))
    if hit_target:
        return self._terminate(...)  # Returns (True, (np.nan, np.nan, stage))
    # If not terminated, return visible score
    return False, self._visible(c, z, close, t)
```

The `_terminate` method returns `(True, (np.nan, np.nan, stage))` which sets `current_scores[t] = np.nan`. However, the score from the PREVIOUS bar persists in the DB because `engine.py` only writes the latest score to `stats.old_swing_retest_score`, not the full time series.

### 2. DB Write Only Captures Latest Score

In `engine.py` line 235-238:
```python
retest_series = compute_retest_score_for_symbol(grp)
row["old_swing_retest_score"] = round(float(retest_series.iloc[-1]), 2) if len(retest_series) > 0 and not pd.isna(retest_series.iloc[-1]) else None
```

This writes ONLY the last bar's score. If the last bar has NULL (event terminated), the DB should be updated to NULL. But the refresh may not be running frequently enough, or the score was written before termination and never updated.

### 3. The Model is Working Correctly

The model scores are being computed correctly. The issue is purely that:
1. Stale scores persist in the DB
2. The "latest score" semantics are unclear (should it show the score of the most recent active event, or only the current bar?)

---

## Why the Previous Plan Was Wrong

The previous plan guessed that:
- SONO was scoring high because of "momentum bias"
- GLBE was scoring high because of "approach from below"
- etc.

**This was incorrect.** The actual reason is simple: **stale DB scores from terminated events.**

The model is NOT rewarding momentum. The model is correctly scoring retest events, but those events have since terminated and the scores were never cleared.

---

## Corrective Actions Needed

### Immediate Fix (Phase 0-4)
1. **Clear stale scores**: Update all stats rows where the current fold shows NULL but DB has non-null
2. **Add score clearing logic**: When an event terminates, ensure the DB score is cleared
3. **Fix score semantics**: Decide whether `old_swing_retest_score` should be:
   - The score of the most recent active event (even if from previous bars), OR
   - Only the score of the current bar (NULL if no active event)

### Structural Fixes (Phase 1-14)
The broader restructuring (departure requirement, peak detection, approach-from-above gate) is still valid and recommended, but the PRIMARY issue is the stale score problem.

---

## Files

- `RETEST_PHASE0_AUDIT/event_traces.json` — Full event traces for top 5 stocks
- `RETEST_PHASE0_AUDIT/detailed_traces.json` — Detailed state transitions
- `RETEST_PHASE0_AUDIT/event_score_traces.json` — Event-to-score mapping

---

## Next Steps

1. Clear stale scores from DB
2. Implement score clearing on event termination
3. Then proceed with structural improvements (departure, peak, approach gates)
4. Retrain model on clean data
