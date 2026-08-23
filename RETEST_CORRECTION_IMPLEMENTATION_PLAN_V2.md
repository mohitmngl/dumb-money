# OLD_SWING_RETEST_SCORE — Correction Implementation Plan V2

**Date**: 2026-08-02
**Status**: PLAN ONLY — no implementation changes
**Repository**: C:\Users\Admin\Desktop\stock test\open code v5 claude prompt
**Current HEAD**: 21b568d
**Phase 0 Audit**: Complete — see RETEST_PHASE0_AUDIT/

---

## 1. Executive Diagnosis

### PRIMARY ISSUE: Stale DB Scores (CONFIRMED)

The top-scoring stocks (SONO 66.38, GLBE 57.82, SCI 47.50, LILA 43.30, SOLV 43.00) are **NOT** currently showing active retest signals. Their DB scores are **stale remnants** from terminated events that were never cleared to NULL.

**Evidence** (from Phase 0 audit):

| Symbol | DB Score | Latest Engine Score | Latest State | Event Status |
|--------|----------|---------------------|--------------|--------------|
| SONO | 66.38 | **NULL** | WAITING_FOR_RETEST | Event terminated 2022 |
| GLBE | 57.82 | **NULL** | WAITING_FOR_RETEST | Event TARGET_REACHED 2024 |
| SCI | 47.50 | **NULL** | WAITING_FOR_RETEST | Event terminated 2025 |
| LILA | 43.30 | **NULL** | WAITING_FOR_RETEST | Event TARGET_REACHED 2026 |
| SOLV | 43.00 | **NULL** | WAITING_FOR_RETEST | Event terminated 2026 |

**Root Cause**: When events terminate (TARGET_REACHED, STOPPED_OUT, EXPIRED), the engine correctly sets `current_scores[t] = NaN`, but the DB value `stats.old_swing_retest_score` is never updated to NULL. The score persists indefinitely.

### SECONDARY ISSUES (Structural Improvements Still Needed)

1. **No departure requirement**: Engine allows retest immediately after breakout
2. **No peak detection**: No concept of post-breakout expansion peak
3. **No approach-direction gate**: Cannot distinguish upward approach from downward return
4. **Score semantics unclear**: Should score show current bar or most recent active event?

---

## 2. Errors in Previous Plan and Their Corrections

### ERROR 1 — Root Causes Were Guessed (CORRECTED)
**Previous**: "Likely cause: Breakout formed, no departure period..."
**Corrected**: **CONFIRMED via Phase 0 audit** — DB scores are stale from terminated events. The model is NOT scoring momentum stocks incorrectly; the scores are from 2022-2025 events that terminated.

### ERROR 2 — Premature OVEREXTENDED During Departure (CORRECTED)
**Previous**: Proposed OVEREXTENDED when price > level + 3 ATR during departure
**Corrected**: OVEREXTENDED applies ONLY to confirmation-time entry distance, not departure magnitude. Large post-breakout departure is positive evidence.

### ERROR 3 — Future-Looking Peak Detection (CORRECTED)
**Previous**: Proposed `high[t] >= high[t+1]` for peak detection
**Corrected**: Use causal running maximum: `running_peak = max(high[0:t+1])`. Freeze peak at retest touch.

### ERROR 4 — Contradictory Failed-Breakout Conditions (CORRECTED)
**Previous**: Proposed `close < level + 0.25 ATR` as failure condition (wrong — price can be above level)
**Corrected**: 
- Before departure: FAILED_BREAKOUT when `close < level - 0.25 ATR` OR two consecutive closes below level
- During retest: STRUCTURALLY_INVALIDATED when `close < level - 0.60 ATR`

### ERROR 5 — Only Upper Retest Bound Checked (CORRECTED)
**Previous**: Touch check only `low <= level + 0.40 ATR`
**Corrected**: Valid touch requires BOTH: `level - 0.50 ATR <= low <= level + 0.40 ATR`

### ERROR 6 — Score Visibility Contradictory (CORRECTED)
**Previous**: Said score visible on confirmation date only, but also used freshness decay
**Corrected**: 
- Main column `old_swing_retest_score` = score of most recent CONFIRMED_RETEST event, NULL if no active event
- Separate fields for active trade monitoring
- No freshness decay in main column

### ERROR 7 — Current-Day Percentile Wrong (CORRECTED)
**Previous**: Rank among current active candidates
**Corrected**: Historical out-of-sample percentile mapping. Store separately:
- `ORIGINAL_RETEST_SCORE` = historical percentile
- `DAILY_RANK` = rank among same-date candidates

### ERROR 8 — Model Definition Inconsistent (CORRECTED)
**Previous**: Called it "three-class" but said TIMEOUT excluded
**Corrected**: Compare coherent alternatives:
A. Two-class (WIN vs DEEP_DRAWDOWN, TIMEOUT excluded)
B. Two-stage (barrier event vs timeout, then win vs drawdown)
C. Competing-risk/survival design
D. Learning-to-rank
E. Deterministic structural baseline

### ERROR 9 — Relaxing Gates for Event Count (FORBIDDEN)
**Previous**: "If fewer than 500 events, relax gates"
**Corrected**: **FORBIDDEN**. Event count controls model complexity, not pattern definition. Options:
- Extend historical coverage
- Add more valid symbols
- Pool markets (if validation supports)
- Reduce model complexity (logistic regression)
- Use deterministic ranker
- Report insufficient data

### ERROR 10 — Unsupported Funnel Counts (CORRECTED)
**Previous**: Estimated 50,000 pivots, 2,000 departures, 300 final events
**Corrected**: **REMOVE ALL ESTIMATES**. Phase 6 must produce measured counts from actual data.

### ERROR 11 — Causality Tests Invalid (CORRECTED)
**Previous**: Comparing numeric feature value to date
**Corrected**: 
- Prefix invariance: Fold full history, read state at t. Fold truncated history at t. Compare all states.
- Incremental equivalence: Fold through t, serialize state, resume. Compare to full fold.

### ERROR 12 — Database Clearing Unsafe (CORRECTED)
**Previous**: Clear production score columns before validation
**Corrected**: **FORBIDDEN**. Use shadow columns:
- `old_swing_retest_score_v2`
- `retest_state_v2`
- `retest_events_v2` table
- Only switch to production after full validation

### ERROR 13 — Automatic Historical Rebuild Unsafe (CORRECTED)
**Previous**: Trigger full rebuild on version bump
**Corrected**: **FORBIDDEN**. Must be:
- Manual
- Resumable
- Checkpointed
- Run against shadow storage
- Preceded by backup and dry run
- Activated only via explicit production-switch command

### ERROR 14 — Golden-Chart Dates Invented (CORRECTED)
**Previous**: Hardcoded AAPL 2020, MU 2023, etc.
**Corrected**: **LOCATE FROM LOCAL DATA**. Report exact symbol, dates, zone, data source. If cannot reproduce, state clearly.

### ERROR 15 — Arbitrary Model Targets (CORRECTED)
**Previous**: AUC >= 0.75, AP >= 0.55, >= 500 events
**Corrected**: **REMOVE FIXED THRESHOLDS**. Focus on:
- Top-1, top-5, top-10, top-25, top-50 precision
- Lift over unconditional rate
- Score-decile ordering
- MFE/MAE by score band
- Stability across folds
- Confidence intervals

### ERROR 16 — Unsupported Performance Estimates (CORRECTED)
**Previous**: "10x faster batch", "4x multiprocessing", "37 hours total"
**Corrected**: **MEASURE FIRST**. Required benchmarks:
- 10, 100, 1000, full market symbols
- Event-engine time, feature-extraction time, model-inference time, DB-write time
- Peak memory, worker count, Windows multiprocessing behavior

### ERROR 17 — Close Entry Needs Execution Warning (CORRECTED)
**Previous**: Treated close-entry as executable
**Corrected**: Close-entry is **idealized research assumption**. Must report:
- Close-entry research result
- Next-open executable sensitivity result
Separately, not mixed.

### ERROR 18 — Event Trace Must Precede Implementation (CORRECTED)
**Previous**: Proposed implementation details before full trace
**Corrected**: **Phase 0 MUST complete first**. No engine work until actual top-stock event traces show precisely why wrong stocks qualified.

---

## 3. Current HEAD and Call Graph

### Current State (Verified)
- **HEAD**: 21b568d
- **Model**: Loaded, 580 trees, AUC=0.694
- **DB**: 1,557 symbols with non-null scores (ALL STALE)
- **Latest engine scores**: ALL NULL for top 5 symbols

### Call Graph
| File | Function | Lines | Current Behavior |
|------|----------|-------|------------------|
| dumbmoney/engine.py | vectorized_stats_pass() | 170-290 | Calls compute_retest_score_for_symbol, writes last score to stats |
| dumbmoney/engine.py | retest call | 580-595 | Computes historical scores |
| dumbmoney/retest_engine.py | compute_retest_score_for_symbol() | 992-1039 | Folds symbol, returns score series |
| dumbmoney/retest_engine.py | fold_symbol() | 626-634 | Creates engine, runs fold |
| dumbmoney/retest_engine.py | RetestEngine._advance_cycle() | 502-573 | State machine: BREAKOUT_CONFIRMED->WAITING_FOR_RETEST->...->SIGNAL_GENERATED |
| dumbmoney/retest_engine.py | RetestEngine._confirm() | 575-589 | Creates SIGNAL_GENERATED, computes model score |
| dumbmoney/retest_engine.py | RetestEngine._visible() | 602-610 | Computes score with freshness decay |
| dumbmoney/retest_engine.py | load_model() | 787-803 | Loads CatBoost singleton |
| dumbmoney/retest_engine.py | make_score_fn() | 983-989 | Creates score_fn(cycle, zones) -> float |
| dumbmoney/retest_engine.py | _event_to_feature_array() | 934-980 | Extracts 29 features |
| dumbmoney/app.py | api_stock_retest_score() | 831-860 | Lazy score endpoint |
| dumbmoney/app.py | api_retest_model_status() | 863-875 | Model health |
| dumbmoney/app.py | api_retest_backtest() | 878-899 | Backtest summary |
| dumbmoney/app.py | api_retest_populate_historical() | 902-915 | Bulk historical write |
| dumbmoney/refresh.py | _refresh_worker() | 398-413 | Calls populate_historical_scores after hist screener |

---

## 4. Verified Event Traces for Top Stocks

### SONO (DB=66.38)
- **Cause**: Stale score from event in April-May 2022
- **Score 65.93** appeared at indices 443-448 (dates 2022-04-28 to 2022-05-05)
- **Event stage**: SIGNAL_GENERATED during those bars
- **Current state**: WAITING_FOR_RETEST, latest score: NULL
- **DB not updated**: Event terminated, score never cleared
- **Root cause**: STALE SCORE (not model bias)

### GLBE (DB=57.82)
- **Cause**: Stale score from event that reached TARGET_REACHED
- **Matching event**: GLBE:12:2, stage=TARGET_REACHED, breakout=2024-05-28, confirm=2024-06-04
- **Score 58.04** was frozen at confirmation
- **Recent scores**: 57.65-58.44 in Sept-Nov 2025
- **Current state**: WAITING_FOR_RETEST, latest score: NULL
- **Root cause**: STALE SCORE (event terminated, score never cleared)

### SCI (DB=47.50)
- **Cause**: Stale score from event in Sept 2025
- **Score 47.46** appeared at index 1291 (date 2025-09-18)
- **Current state**: WAITING_FOR_RETEST, latest score: NULL
- **Root cause**: STALE SCORE

### LILA (DB=43.30)
- **Cause**: Stale score from TARGET_REACHED event
- **Matching event**: LILA:41:2, stage=TARGET_REACHED, breakout=2026-03-23, confirm=2026-04-10
- **Score 43.34** frozen at confirmation
- **Current state**: WAITING_FOR_RETEST, latest score: NULL
- **Root cause**: STALE SCORE

### SOLV (DB=43.00)
- **Cause**: Stale score from event in July 2026
- **Score 42.96** appeared at index 571 (date 2026-07-13)
- **Current state**: WAITING_FOR_RETEST, latest score: NULL
- **Root cause**: STALE SCORE

### AAPL (DB=0.00) — Positive Reference
- **Current state**: No active retest signal
- **Latest event**: AAPL:46:1, stage=TARGET_REACHED, breakout=2026-07-15, confirm=2026-07-23
- **DB score correctly 0**: Event terminated, but DB was updated (or never had score)
- **Note**: AAPL shows correct behavior — score cleared after termination

---

## 5. Current Candidate Definition

### Current State Machine (retest_engine.py lines 502-573)
```
BREAKOUT_CONFIRMED -> WAITING_FOR_RETEST (immediately after breakout)
WAITING_FOR_RETEST -> (touch: low <= level + 0.40 ATR, delay >= 3)
WAITING_FOR_RETEST -> WAITING_FOR_CONFIRMATION
WAITING_FOR_CONFIRMATION -> SIGNAL_GENERATED (confirm: close >= level - 0.10 ATR)
SIGNAL_GENERATED -> [TARGET_REACHED | STOPPED_OUT | EXPIRED | INVALIDATED]
```

### Current Problems
1. No departure requirement — retest can form immediately after breakout
2. No peak detection — no concept of post-breakout expansion
3. No approach-direction gate — upward approach treated same as downward return
4. No score clearing on termination — DB retains old scores
5. Target uses close[t] instead of high[t] (line 543)

---

## 6. Required Candidate Definition

### Required Pattern
```
OLD SIGNIFICANT SWING-HIGH RESISTANCE
-> VALID BREAKOUT (age >= 20, quality check)
-> MEANINGFUL DEPARTURE (max distance >= 1.75 ATR, 3+ closes above level + 0.50 ATR)
-> ACCEPTANCE ABOVE RESISTANCE
-> SUBSTANTIAL EXPANSION
-> RUNNING POST-BREAKOUT PEAK
-> LATER PULLBACK FROM THAT PEAK
-> DOWNWARD APPROACH FROM ABOVE
-> RETURN TO ORIGINAL BREAKOUT LEVEL
-> OLD RESISTANCE HOLDS AS SUPPORT
-> CONFIRMATION NEAR SUPPORT
-> LOW-RISK NEW ENTRY
```

### Initial Structural Defaults (Requiring Validation)
```python
SWING_LEFT = 5
SWING_RIGHT = 5
MIN_LEVEL_AGE = 20

# Breakout
BREAKOUT_LEVEL_TOUCH_ATR = 0.25
BREAKOUT_BODY_MIN_ATR = 0.05
BREAKOUT_CLOSE_LOCATION_MIN = 0.60

# Departure
MIN_BARS_BEFORE_RETEST_ELIGIBLE = 8
MIN_DEPARTURE_DISTANCE_ATR = 1.75
MIN_DEPARTURE_CLOSES = 3
DEPARTURE_CLOSE_THRESHOLD_ATR = 0.50

# Peak (causal running maximum)
# running_peak = max(high[breakout_idx:t+1])
# frozen at retest touch

# Pullback
MIN_PULLBACK_FROM_PEAK_ATR = 1.00

# Approach from above
# previous close >= level + 0.30 ATR
# at least 3 of previous 5 closes above threshold
# no close below level - 0.10 ATR in previous 3 bars

# Retest zone
LOWER_RETEST_BOUND = level - 0.50 * TOUCH_ATR
UPPER_RETEST_BOUND = level + 0.40 * TOUCH_ATR
# Valid touch: LOWER <= low <= UPPER

# Confirmation
CONFIRM_CLOSE_LEVEL_ATR = -0.10
CONFIRM_WINDOW = 3

# Entry distance
MAX_ENTRY_DISTANCE_ATR = 0.75

# Time limits
MAX_BREAKOUT_TO_TOUCH_BARS = 120
TIME_BARRIER = 20
```

---

## 7. Correct State Machine

```
NO_BREAKOUT
  -> BREAKOUT_CONFIRMED [valid breakout: age>=20, quality]

BREAKOUT_CONFIRMED
  -> WAITING_FOR_DEPARTURE [immediately]
  -> FAILED_BREAKOUT [close < level - 0.25*ATR, or 2 closes below level]

WAITING_FOR_DEPARTURE
  -> DEPARTURE_ESTABLISHED [max_dist>=1.75*ATR, 3+ closes>=level+0.50*ATR]
  -> FAILED_BREAKOUT [close < level - 0.25*ATR]
  -> EXPIRED [no departure within 60 bars]

DEPARTURE_ESTABLISHED
  -> WAITING_FOR_RETURN [distinct running peak, price declining]
  -> OVEREXTENDED [price > level + 4.0*ATR, no peak after 40 bars]

WAITING_FOR_RETURN
  -> ACTIVE_RETEST [price enters retest zone from ABOVE]
  -> FAILED_BREAKOUT [close < level - 0.25*ATR]

ACTIVE_RETEST
  -> WAITING_FOR_CONFIRMATION [level touched, both bounds checked]
  -> RECOVERY_FROM_BELOW [approach from below, <2 closes above threshold]
  -> FAILED_BREAKOUT [close < level - 0.60*ATR]

WAITING_FOR_CONFIRMATION
  -> CONFIRMED_RETEST [close>=level-0.10*ATR within 3 bars, entry_distance<=0.75]
  -> FAILED [no confirmation within 3 bars]
  -> FAILED_BREAKOUT [close < level - 0.60*ATR]

CONFIRMED_RETEST
  -> POST_ENTRY_ACTIVE [score frozen, visible]
  -> STRUCTURALLY_INVALIDATED [close < level - 0.60*ATR]

POST_ENTRY_ACTIVE
  -> TARGET_COMPLETED [future high >= entry + 2.0*SIGNAL_ATR]
  -> STOPPED_OUT [future low <= entry - 0.75*SIGNAL_ATR]
  -> EXPIRED [20 bars elapsed]
  -> STRUCTURALLY_INVALIDATED [close < level - 0.60*ATR]
  -> OVEREXTENDED [entry_distance > 0.75]
```

**Key Rules**:
- Terminal events never revive
- New cycle gets new event_id
- OVEREXTENDED only for confirmation-time entry distance, not departure magnitude
- Running peak is causal maximum, not future-confirmed local max

---

## 8. Event Schema

### New Fields for EventCycle
```python
# Departure tracking
departure_established: bool = False
departure_established_date: str = ""
departure_max_distance_atr: float = np.nan
departure_closes_count: int = 0
departure_acceptance_duration: int = 0

# Peak tracking (causal running maximum)
post_breakout_peak_date: str = ""
post_breakout_peak_price: float = np.nan
post_breakout_peak_distance_atr: float = np.nan
days_breakout_to_peak: int = 0

# Approach direction
approach_direction: str = ""  # "from_above", "from_below", "neutral"
approached_from_above: bool = False
pre_retest_distance_atr: float = np.nan
closes_above_level_before_touch: int = 0
bars_since_last_close_below_level: int = 0

# Pullback
pullback_from_peak_atr: float = np.nan
pullback_retracement_fraction: float = np.nan
days_peak_to_retest: int = 0

# Failed breakout
failed_breakout_before_departure: bool = False
failed_breakout_reason: str = ""

# Entry quality
entry_distance_atr: float = np.nan

# Visibility
is_new_entry: bool = False
retest_state: str = ""
```

### ATR Conventions
```python
# Store separately:
BREAKOUT_ATR  # Used for: breakout threshold, departure distance, accepted closes, peak distance, pullback, failed-breakout checks
TOUCH_ATR     # Used for: retest bounds, touch penetration, pre-confirmation invalidation
SIGNAL_ATR    # Used for: entry distance, target, stop, post-entry MFE/MAE
```

---

## 9. Score Visibility Semantics

### Main Column: old_swing_retest_score
```
= score of most recent CONFIRMED_RETEST event
= NULL if no active event or event terminated
= NOT cleared until next refresh cycle
```

### Separate Monitoring Fields
```python
RETEST_ORIGINAL_SCORE      # Frozen at confirmation
RETEST_ACTIVE_TRADE_SCORE  # Current visible score with decay
RETEST_TRADE_STATE         # POST_ENTRY_ACTIVE, TARGET_COMPLETED, etc.
RETEST_TARGET_STATUS       # Not reached, reached
RETEST_STOP_STATUS         # Not hit, hit
```

### Key Rule
**Do not use freshness decay in the main new-entry column.** The main column shows the original model score. Decay is for active trade monitoring only.

---

## 10. Feature Audit

### Features to REMOVE (constants, no information)
- target_atr (always 2.0)
- stop_atr (always 0.75)
- time_to_barrier (always 20)
- entry (absolute price — use entry_distance_atr instead)

### Features to REPLACE
- signal_atr -> signal_atr_pct = signal_atr / entry

### Features to ADD (22 new)
| Feature | Formula | Causal? |
|---------|---------|---------|
| departure_max_distance_atr | max(close[i] - level) / atr[i] | Yes |
| departure_established | 1 if departure established | Yes |
| departure_closes_count | Count of accepted closes | Yes |
| post_breakout_peak_distance_atr | (peak - level) / breakout_atr | Yes |
| days_breakout_to_peak | peak_idx - breakout_idx | Yes |
| days_peak_to_retest | retest_idx - peak_idx | Yes |
| pullback_from_peak_atr | (peak - retest_low) / signal_atr | Yes |
| pullback_retracement_fraction | (peak - low) / (peak - level) | Yes |
| approach_direction | from_above=1, from_below=0 | Yes |
| approached_from_above | 1 if 2+ closes above before touch | Yes |
| pre_retest_distance_atr | (close[t-1] - level) / atr[t-1] | Yes |
| closes_above_level_before_touch | Count | Yes |
| bars_since_last_close_below_level | Count | Yes |
| pullback_slope_atr | (peak - low) / days / signal_atr | Yes |
| pullback_volatility_atr | std(pullback bars) / signal_atr | Yes |
| pullback_volume_contraction | vol(retest) / avg_vol | Yes |
| failed_breakout_before_departure | 1 if failed | Yes |
| number_of_level_crossings | Count | Yes |
| number_of_closes_below_level_after_breakout | Count | Yes |
| entry_distance_atr | (confirm_close - level) / signal_atr | Yes |
| confirmation_rejection_wick | (confirm_close - confirm_low) / signal_atr | Yes |
| confirmation_body_atr | abs(confirm_close - confirm_open) / signal_atr | Yes |

**Net: 29 -> ~25 features**

---

## 11. Candidate Funnel Methodology

### Required Measured Funnel (NOT estimated)
```
confirmed_pivots ->
causal_zones ->
old_zones (age>=20) ->
breakouts ->
failed_breakouts_before_departure ->
departures_established ->
peaks_established ->
pullbacks_sufficient ->
returns_from_above ->
recoveries_from_below ->
retest_zone_touches ->
confirmations ->
entries_within_distance_limit ->
independent_deduplicated_signals ->
WIN ->
DEEP_DRAWDOWN ->
TIMEOUT
```

### Phase 6 Deliverable
- Measured counts at each stage
- Distribution analysis
- Event count assessment

---

## 12. Shadow Database Design

### Do NOT modify production schema directly
Use versioned shadow columns:

```sql
-- New columns (additive, safe)
ALTER TABLE stats ADD COLUMN old_swing_retest_score_v2 REAL;
ALTER TABLE stats ADD COLUMN retest_state_v2 TEXT DEFAULT 'NO_SETUP';
ALTER TABLE stats ADD COLUMN retest_event_id_v2 TEXT;
ALTER TABLE stats ADD COLUMN retest_confirmation_date_v2 TEXT;
ALTER TABLE stats ADD COLUMN retest_entry_distance_atr_v2 REAL;
ALTER TABLE stats ADD COLUMN retest_model_version_v2 TEXT;

-- Same for historical_screener
ALTER TABLE historical_screener ADD COLUMN old_swing_retest_score_v2 REAL;
ALTER TABLE historical_screener ADD COLUMN retest_state_v2 TEXT;
-- ... etc
```

### Production Switch Procedure
1. Validate shadow data
2. Backup production columns
3. Run explicit switch command
4. Verify production columns updated
5. Rollback procedure if issues

---

## 13. Historical Rebuild Procedure

### FORBIDDEN: Automatic rebuild on version bump
### REQUIRED: Manual, checkpointed, shadow-based

```
1. Backup production scores
2. Create shadow tables with _v2 suffix
3. Run rebuild against shadow tables
4. Validate shadow results
5. Dry run on subset (100 symbols)
6. Limited-date dry run
7. Full shadow rebuild
8. Explicit production-switch command
9. Verify production
10. Archive shadow tables
```

---

## 14. Phased Implementation Order

### PHASE 0: Read-only Root-Cause Audit ✅ COMPLETE
- Trace top 5 stocks
- Identify stale scores
- Produce audit report

### PHASE 1: Fix Stale Score Clearing (IMMEDIATE)
- Add score clearing on event termination
- Clear existing stale scores
- Verify NULL semantics

### PHASE 2: Reference Causal Engine with Departure/Peak/Approach
- Implement new state machine
- Add departure logic
- Add peak detection (causal running max)
- Add approach-from-above gate
- Add strict touch bounds

### PHASE 3: Structural Tests
- 40 unit tests
- Golden chart validation
- Causality tests

### PHASE 4: Entry and Outcome Corrections
- Fix target detection (high vs close)
- Fix outcome scanning start
- Add next-open sensitivity

### PHASE 5: Shadow Database Integration
- Add _v2 columns
- Implement score clearing
- NULL semantics enforced

### PHASE 6: Measured Candidate Funnel
- Run engine on all symbols
- Count events at each stage
- Assess event count

### PHASE 7: Human Visual Review
- 400 samples reviewed
- Golden charts validated

### PHASE 8: Feature Rebuild
- Update feature extraction
- Remove constants
- Add new features
- Verify training/inference parity

### PHASE 9: Generate Clean Training Dataset
- Run engine with new gates
- Collect events
- Assess count

### PHASE 10: Walk-Forward Model Comparison
- Baseline (structure only)
- Logistic regression
- CatBoost
- Learning-to-rank

### PHASE 11: Historical Percentile Mapping
- Build CDF from prior folds
- Map raw scores to percentiles
- Save mapping with model

### PHASE 12: Top-K and Score-Decile Validation
- Precision@K metrics
- Decile analysis
- Lift over baseline

### PHASE 13: Close-Entry and Next-Open Backtests
- Separate equity curves
- Report both independently

### PHASE 14: Limited Shadow Rebuild
- 100 symbols
- Timing measurement
- Validation

### PHASE 15: Full Shadow Rebuild
- All symbols
- Checkpointed
- Resumable

### PHASE 16: Explicit Production Switch
- Manual approval
- Backup created
- Switch executed
- Verification

---

## 15. Performance Benchmark Plan

### Required Measurements (NOT estimates)
```
1. 10 symbols: event_engine, feature_extraction, model_inference, db_write
2. 100 symbols: same
3. 1,000 symbols: same
4. Full market: same
5. Peak memory usage
6. Worker count behavior (Windows multiprocessing)
```

### Report Format
| Batch Size | Engine Time | Feature Time | Inference Time | DB Time | Memory |
|------------|-------------|--------------|----------------|---------|--------|
| 10 | ? | ? | ? | ? | ? |
| 100 | ? | ? | ? | ? | ? |
| 1,000 | ? | ? | ? | ? | ? |
| Full | ? | ? | ? | ? | ? |

---

## 16. Release Blockers

1. **Stale scores not cleared** -> Must fix before any other work
2. **Event count < 100 after all gates** -> Must address (relax nothing, report insufficiency)
3. **Causality violation in any feature** -> Fix before training
4. **Existing tests broken** -> Fix before deploy
5. **Shadow data not validated** -> Cannot switch to production
6. **Top-5 precision not > baseline** -> Model not ready

---

## 17. Questions Answered from Current Code

### Q1: Why do top stocks have high DB scores?
**A**: Stale scores from terminated events. Confirmed via Phase 0 audit.

### Q2: Does the model score momentum stocks incorrectly?
**A**: **UNANSWERED** — cannot determine until stale scores are cleared and clean events are generated.

### Q3: Is the engine structurally correct?
**A**: **NO** — missing departure, peak, approach gates. But this is secondary to stale scores.

### Q4: What is the actual event count after strict gates?
**A**: **UNKNOWN** — requires Phase 6 measurement.

### Q5: Can we train a model with < 500 events?
**A**: **POSSIBLY** — may need logistic regression or deterministic ranker.

---

## 18. Immediate Actions (Phase 1)

### 1. Clear Stale Scores
```sql
-- Identify stale scores
SELECT symbol, old_swing_retest_score, last_updated
FROM stats
WHERE old_swing_retest_score > 0
AND last_updated < date('now', '-30 days');

-- Clear stale scores (after validation)
UPDATE stats SET old_swing_retest_score = NULL
WHERE old_swing_retest_score > 0;
```

### 2. Add Score Clearing to Engine
In `retest_engine.py`, when event terminates:
```python
def _terminate(self, c, z, t, date, stage, reason):
    c.stage = stage
    c.reason = reason
    c.resolution_idx = t
    c.resolution_date = date
    # Clear score for terminated events
    if stage in (cfg.EventStage.TARGET_REACHED.value, 
                 cfg.EventStage.STOPPED_OUT.value,
                 cfg.EventStage.EXPIRED.value,
                 cfg.EventStage.INVALIDATED.value,
                 cfg.EventStage.FAILED.value):
        c.original_score = None
    # ... rest of terminate logic
```

### 3. Update DB Write Logic
In `engine.py`, ensure NULL is written when score is NULL:
```python
score = retest_series.iloc[-1]
row["old_swing_retest_score"] = None if pd.isna(score) else round(float(score), 2)
```

---

## End of V2 Plan
