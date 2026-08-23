# OLD_SWING_RETEST_SCORE — Correction Implementation Plan

**Date**: 2026-08-02
**Status**: PLAN ONLY — no implementation changes
**Repository**: C:\Users\Admin\Desktop\stock test\open code v5 claude prompt
**Current HEAD**: 21b568d

---

## 1. Executive Diagnosis

The current retest engine produces scores that are structurally misaligned with the intended trading pattern. The root causes are:

1. **No departure requirement**: The engine allows a retest to form immediately after breakout, with no requirement that price first move meaningfully away from the level and establish acceptance.
2. **No peak detection**: There is no concept of a post-breakout expansion peak that must form before a pullback can qualify as a retest.
3. **No approach-direction gate**: The engine does not distinguish between a downward return from above (valid retest) and an upward approach from below (momentum/continuation).
4. **Score persistence on completed events**: The visible score is shown for any SIGNAL_GENERATED event, regardless of whether the target/stop has already been resolved, or whether the event is stale.
5. **Model trained on contaminated candidates**: The 271,219 training events include breakouts that never departed, never peaked, and were approached from below — teaching the model to favor momentum patterns.

**Evidence**: Top 5 scores (SONO 66.38, GLBE 57.82, SCI 47.50, LILA 43.30, SOLV 43.00) all show stocks in sustained upward trends at the time of scoring, not pullbacks to support.

**AUC 0.694 is a symptom, not the disease**: The model cannot learn a clean signal because the candidate definition is too loose. Fix the candidate gate first; retrain after.

---

## 2. Current Call Graph with Exact Files/Functions/Lines

### Engine Entry Points
| File | Function | Lines | Purpose |
|------|----------|-------|---------|
| dumbmoney/engine.py | vectorized_stats_pass() | 170-290 | Computes current stats per symbol |
| dumbmoney/engine.py | retest call | 580-595 | Computes historical retest scores |
| dumbmoney/retest_engine.py | compute_retest_score_for_symbol() | 992-1039 | Public API: folds one symbol |
| dumbmoney/retest_engine.py | compute_retest_score_current() | 752-761 | Public API: last bar score |
| dumbmoney/retest_engine.py | fold_symbol() | 626-634 | Creates engine and runs fold |
| dumbmoney/retest_engine.py | RetestEngine.fold() | 319-357 | Main fold loop |
| dumbmoney/retest_engine.py | RetestEngine._advance_cycles() | 411-434 | Per-bar cycle advancement |
| dumbmoney/retest_engine.py | RetestEngine._advance_cycle() | 502-573 | State machine transitions |
| dumbmoney/retest_engine.py | RetestEngine._confirm() | 575-589 | Creates SIGNAL_GENERATED |
| dumbmoney/retest_engine.py | RetestEngine._visible() | 602-610 | Computes visible score |

### Model Integration
| File | Function | Lines | Purpose |
|------|----------|-------|---------|
| dumbmoney/retest_engine.py | load_model() | 787-803 | Loads CatBoost singleton |
| dumbmoney/retest_engine.py | get_model() | 806-808 | Returns loaded model |
| dumbmoney/retest_engine.py | make_score_fn() | 983-989 | Creates score_fn(cycle, zones) |
| dumbmoney/retest_engine.py | _event_to_feature_array() | 934-980 | Extracts 29 features |
| dumbmoney/engine.py | module init | 16-22 | Preloads model at import |

### Training Pipeline
| File | Function | Lines | Purpose |
|------|----------|-------|---------|
| dumbmoney/retest_training_parallel.py | process_single_symbol() | 47-130 | Extracts events |
| dumbmoney/retest_training_parallel.py | run_full_training() | 133-248 | Full training |
| dumbmoney/retest_finetune_full.py | run_full_finetune() | 98-215 | Hyperparameter search |
| dumbmoney/retest_backtest.py | run_backtest() | 55-140 | Backtest evaluator |

### API Endpoints
| File | Route | Lines | Purpose |
|------|-------|-------|---------|
| dumbmoney/app.py | /api/stock/<symbol>/retest-score | 831-860 | Lazy single-symbol |
| dumbmoney/app.py | /api/retest/model-status | 863-875 | Model health |
| dumbmoney/app.py | /api/retest/backtest | 878-899 | Backtest summary |
| dumbmoney/app.py | /api/retest/populate-historical | 902-915 | Bulk historical write |
| dumbmoney/app.py | /api/screener | 620-695 | Current screener |
| dumbmoney/app.py | /api/screener/historical | 400-480 | Historical screener |

### Refresh Integration
| File | Lines | Purpose |
|------|-------|---------|
| dumbmoney/refresh.py | 398-413 | Calls populate_historical_scores() |

### Database Schema
| Table | Column | Lines | Default |
|-------|--------|-------|---------|
| stats | old_swing_retest_score REAL | db.py:31 | 0 |
| historical_screener | old_swing_retest_score REAL | db.py:61 | 0 |

---

## 3. Report Statement Verification

### CHATGPT_DEBUG_REPORT.md
| Statement | Status |
|-----------|--------|
| 1,557 symbols with score > 0 | VERIFIED |
| 9,234 symbols with score = 0 | VERIFIED |
| 0 NULL rows | STALE -- code fixed but DB default is 0 |
| Test AUC 0.694 | VERIFIED |
| Top scores: SONO 66, GLBE 57, SCI 47 | VERIFIED |
| Model not wired | FALSE -- fixed in commit 02c49b6 |
| All 18 tests pass | VERIFIED |

### SESSION_LOG.md
| Statement | Status |
|-----------|--------|
| Model NOT wired | FALSE -- fixed in PHASE 10 |
| Config constants listed | MATCHES current retest_config.py |

---

## 4. Root-Cause Trace for Top 5 Stocks

### Diagnostic Script (PHASE 0 deliverable)
```python
# dumbmoney/retest_audit.py -- READ-ONLY diagnostic
# For each symbol: trace event state machine, report all fields
```

### SONO (Score: 66.38)
Price: 13.95 -> 17.55 (+25.8% in 13 days)
- **Likely cause**: Breakout formed, no departure period, immediate retest on upward move
- **Missing**: departure_established, post_breakout_peak, approach_from_above
- **Probable state**: Should be OVEREXTENDED or FAILED_BREAKOUT

### GLBE (Score: 57.82)
Price: 33.87 -> 40.27 (+18.8% recovery rally)
- **Likely cause**: Recovery from below mistaken for retest from above
- **Missing**: approach_direction gate
- **Probable state**: Should be RECOVERY_FROM_BELOW (rejected)

### SCI (Score: 47.50)
Price: 79.52 -> 85.68 (+7.8% steady uptrend)
- **Likely cause**: Breakout continuation, no pullback
- **Missing**: peak requirement, return-from-above requirement
- **Probable state**: Should be in WAITING_FOR_RETURN or OVEREXTENDED

### LILA (Score: 43.30)
Price: 7.50 -> 8.52 (+13.6% small cap volatile)
- **Likely cause**: Shallow breakout, no meaningful departure
- **Missing**: MIN_DEPARTURE_DISTANCE_ATR check
- **Probable state**: Should be FAILED_BREAKOUT

### SOLV (Score: 43.00)
Price: 80.75 -> 88.53 (+9.6% strong move)
- **Likely cause**: Momentum, not a pullback
- **Missing**: peak detection, pullback requirement
- **Probable state**: Should be OVEREXTENDED

---

## 5. Current vs Required Pattern Definition

### Current Pattern (BROKEN)
```
Breakout (close >= level + 0.25 ATR)
  -> WAITING_FOR_RETEST (delay >= 3 bars)
  -> Touch (low <= level + 0.40 ATR)
  -> WAITING_FOR_CONFIRMATION (3 bars)
  -> SIGNAL_GENERATED (close >= level - 0.10 ATR)
  -> Score = model_prob * freshness_decay
```

### Required Pattern (TARGET)
```
NO_BREAKOUT
  -> valid breakout (age >= 20, quality check)
BREAKOUT_CONFIRMED
  -> WAITING_FOR_DEPARTURE
  -> departure established (max distance >= 1.75 ATR, 3+ closes above level + 0.50 ATR)
DEPARTURE_ESTABLISHED
  -> distinct peak forms, price starts declining
WAITING_FOR_RETURN
  -> price returns downward from above into retest zone
ACTIVE_RETEST
  -> touch but confirmation pending
WAITING_FOR_CONFIRMATION
  -> confirmation close >= level - 0.10 ATR, entry distance <= 0.75 ATR
CONFIRMED_RETEST
  -> score frozen, visible on latest bar only
POST_ENTRY_ACTIVE
  -> target reached / stop hit / expired / overextended
```

---

## 6. Proposed State Machine

```
NO_BREAKOUT -> BREAKOUT_CONFIRMED [valid breakout: age>=20, quality, touch]
BREAKOUT_CONFIRMED -> WAITING_FOR_DEPARTURE [immediately]
WAITING_FOR_DEPARTURE -> DEPARTURE_ESTABLISHED [max_dist>=1.75*ATR, 3+ closes>=level+0.50]
WAITING_FOR_DEPARTURE -> FAILED_BREAKOUT [close<level-0.25 ATR, or delay>60 bars]
DEPARTURE_ESTABLISHED -> WAITING_FOR_RETURN [distinct peak, price declining]
DEPARTURE_ESTABLISHED -> OVEREXTENDED [price > level + 3.0 ATR]
WAITING_FOR_RETURN -> ACTIVE_RETEST [price enters retest zone from ABOVE]
WAITING_FOR_RETURN -> FAILED_BREAKOUT [close<level-0.25 ATR]
ACTIVE_RETEST -> WAITING_FOR_CONFIRMATION [level touched]
ACTIVE_RETEST -> RECOVERY_FROM_BELOW [approach from below]
WAITING_FOR_CONFIRMATION -> CONFIRMED_RETEST [close>=level-0.10 ATR within 3 bars]
CONFIRMED_RETEST -> POST_ENTRY_ACTIVE [score frozen]
POST_ENTRY_ACTIVE -> TARGET_COMPLETED [future high >= entry + 2.0*ATR]
POST_ENTRY_ACTIVE -> STOPPED_OUT [future low <= entry - 0.75*ATR]
POST_ENTRY_ACTIVE -> EXPIRED [20 bars elapsed]
POST_ENTRY_ACTIVE -> STRUCTURALLY_INVALIDATED [close < level - 0.60 ATR]
POST_ENTRY_ACTIVE -> OVEREXTENDED [entry distance > 0.75 ATR]
```

**Key Rules**:
- FAILED_BREAKOUT event cannot revive. Later recovery = new event_id.
- CONFIRMED_RETEST score is frozen at confirmation. No further updates.
- POST_ENTRY_ACTIVE is the ONLY state where score is visible in screener.
- TARGET_COMPLETED / STOPPED_OUT events removed from new-entry view immediately.

---

## 7. Event Data Model (Changes to EventCycle)

### New Fields
```python
# DEPARTURE
departure_established: bool = False
departure_established_date: str = ""
departure_max_distance_atr: float = np.nan
departure_closes_count: int = 0
departure_acceptance_duration: int = 0

# PEAK
post_breakout_peak_date: str = ""
post_breakout_peak_price: float = np.nan
post_breakout_peak_distance_atr: float = np.nan
days_breakout_to_peak: int = 0

# APPROACH DIRECTION
approach_direction: str = ""
approached_from_above: bool = False
pre_retest_distance_atr: float = np.nan
closes_above_level_before_touch: int = 0
bars_since_last_close_below_level: int = 0

# PULLBACK
pullback_from_peak_atr: float = np.nan
pullback_retracement_fraction: float = np.nan
days_peak_to_retest: int = 0
pullback_slope_atr: float = np.nan
pullback_volatility_atr: float = np.nan
pullback_volume_contraction: float = np.nan

# FAILED BREAKOUT
failed_breakout_before_departure: bool = False
failed_breakout_reason: str = ""

# ENTRY QUALITY
entry_distance_atr: float = np.nan
confirmation_rejection_wick: float = np.nan
confirmation_body_atr: float = np.nan

# VISIBILITY
is_new_entry: bool = False
retest_state: str = ""
```

### Fields to Remove/Replace
```python
# REMOVE (constant, adds no information)
# - target_atr (always 2.0)
# - stop_atr (always 0.75)
# - time_to_barrier (always 20)
# - entry (absolute price)

# REPLACE
# - signal_atr -> signal_atr_pct = signal_atr / entry
```

---

## 8. Exact Departure Logic

### Current Code (lines 509-513)
```python
if st == cfg.EventStage.BREAKOUT_CONFIRMED.value:
    if t == c.breakout_idx:
        return False, (np.nan, np.nan, st)
    c.stage = cfg.EventStage.WAITING_FOR_RETEST.value
    return False, (np.nan, np.nan, c.stage)
```
**Problem**: Transitions directly to retest mode with no departure check.

### Proposed Logic
```python
if st == cfg.EventStage.BREAKOUT_CONFIRMED.value:
    if t == c.breakout_idx:
        return False, (np.nan, np.nan, st)
    c.stage = cfg.EventStage.WAITING_FOR_DEPARTURE.value
    return False, (np.nan, np.nan, c.stage)

if st == cfg.EventStage.WAITING_FOR_DEPARTURE.value:
    if close[t] < lvl + 0.25 * a:
        return self._terminate(c, z, t, dates[t], cfg.EventStage.FAILED_BREAKOUT.value, "below_level_pre_departure")
    if delay > 60:
        return self._terminate(c, z, t, dates[t], cfg.EventStage.EXPIRED.value, "no_departure_60")

    dist_atr = (close[t] - lvl) / a
    if dist_atr > c.departure_max_distance_atr:
        c.departure_max_distance_atr = dist_atr
    if close[t] >= lvl + 0.50 * a:
        c.departure_closes_count += 1

    if not c.post_breakout_peak_date:
        if t > c.breakout_idx and high[t] >= high[c.breakout_idx]:
            c.post_breakout_peak_date = dates[t]
            c.post_breakout_peak_price = float(high[t])
            c.post_breakout_peak_distance_atr = (high[t] - lvl) / a

    if c.departure_max_distance_atr >= 1.75 and c.departure_closes_count >= 3:
        c.departure_established = True
        c.departure_established_date = dates[t]
        c.departure_acceptance_duration = c.departure_closes_count
        c.stage = cfg.EventStage.DEPARTURE_ESTABLISHED.value
        return False, (np.nan, np.nan, c.stage)
    return False, (np.nan, np.nan, c.stage)
```

---

## 9. Exact Failed-Breakout Logic

### Before Departure
```python
if close[t] < lvl:
    return FAILED_BREAKOUT, "below_level"
if consecutive_closes_below_level >= 2:
    return FAILED_BREAKOUT, "two_closes_below"
if close[t] < lvl - 0.25 * a:
    return FAILED_BREAKOUT, "structural_invalidation"
```

### After Departure
```python
if close[t] < lvl and c.departure_established:
    return FAILED_BREAKOUT, "departure_failed"
```

**Once FAILED_BREAKOUT: event_id is final, score is NULL, no revival.**

---

## 10. Exact Peak/Pullback Logic

### Peak Detection
```python
if not c.post_breakout_peak_date:
    if t > c.breakout_idx and high[t] > high[t-1] and (t + 1 >= n or high[t] >= high[t+1]):
        c.post_breakout_peak_date = dates[t]
        c.post_breakout_peak_price = float(high[t])
        c.post_breakout_peak_distance_atr = (high[t] - lvl) / a

if c.post_breakout_peak_distance_atr < 1.0:
    pass  # continue waiting for higher peak
```

### Pullback Calculation
```python
c.pullback_from_peak_atr = (c.post_breakout_peak_price - low[t]) / a
c.days_peak_to_retest = t - peak_idx
c.pullback_retracement_fraction = (c.post_breakout_peak_price - low[t]) / (c.post_breakout_peak_price - lvl)
```

### Minimum Pullback
```python
if c.pullback_from_peak_atr < 1.0:
    return False, (np.nan, np.nan, c.stage)  # insufficient retracement
```

---

## 11. Exact Approach-Direction Logic

### Pre-Retest Check
```python
pre_touch_closes_above = 0
for i in range(t - 1, max(t - 5, c.retest_idx - 1), -1):
    if close[i] > lvl + 0.30 * atr[i]:
        pre_touch_closes_above += 1
    else:
        break

if pre_touch_closes_above < 2:
    c.approach_direction = "from_below"
    return self._terminate(c, z, t, dates[t], cfg.EventStage.RECOVERY_FROM_BELOW.value, "approach_from_below")
else:
    c.approach_direction = "from_above"
    c.approached_from_above = True
```

---

## 12. Strict Retest and Confirmation Logic

### Retest Zone (unchanged)
```python
LOWER_RETEST_BOUND = lvl - 0.50 * a
UPPER_RETEST_BOUND = lvl + 0.40 * a
```

### Touch Condition (unchanged)
```python
if delay >= cfg.RETEST_DELAY_MIN and low[t] <= lvl + cfg.RETEST_BOUND_HI_ATR * a:
    # Touch registered
```

### Confirmation (unchanged)
```python
if close[t] >= lvl + cfg.CONFIRM_CLOSE_LEVEL_ATR * a:
    self._confirm(c, z, t, dates[t], a, high, low, close)
```

### Entry Distance Gate (NEW)
```python
c.entry_distance_atr = (c.entry - lvl) / c.signal_atr
if c.entry_distance_atr > cfg.MAX_ENTRY_DISTANCE_ATR:  # 0.75
    return self._terminate(c, z, t, dates[t], cfg.EventStage.OVEREXTENDED.value, "entry_too_far")
```

---

## 13. Close-Entry and Outcome Semantics

### BUG: Target Detection Uses Close Instead of High
```python
# Current (line 543):
hit_target = close[t] >= entry + cfg.BARRIER_UP_ATR * sa  # WRONG

# Fixed:
hit_target = high[t] >= entry + cfg.BARRIER_UP_ATR * sa  # CORRECT
```

### Outcome Scanning Start
```python
# finalize_labels must start from confirm_idx + 1 (already correct)
# But _advance_cycle checks barriers on confirmation candle (BUG)
# Fix: in _confirm, do NOT check barriers on confirmation candle
```

---

## 14. Candidate Eligibility Funnel (Estimated)

| Stage | Count | Notes |
|-------|-------|-------|
| Raw pivot zones | ~50,000+ | Every swing high with prominence >= 1.5 ATR |
| Valid old zones (age >= 20) | ~30,000+ | Most pass |
| Valid breakouts | ~15,000+ | Body + close location filter |
| Departures established | ~2,000 | NEW GATE -- estimated 87% filtered |
| Distinct peaks established | ~1,500 | NEW GATE -- estimated 25% filtered |
| Valid returns from above | ~800 | NEW GATE -- estimated 47% filtered |
| Retest-zone touches | ~600 | |
| Confirmed retests | ~400 | |
| Actionable close entries (distance <= 0.75) | ~300 | |
| WIN | ~80 (26%) | |
| DEEP_DRAWDOWN | ~200 (72%) | |
| TIMEOUT | ~20 (2%) | |

**Total viable events after all gates: ~300 per market. INSUFFICIENT for CatBoost.**

### Options
1. Relax departure threshold (1.75 -> 1.0 ATR)
2. Pool US + India data
3. Use simpler model (logistic regression)
4. Accept lower accuracy, use as ranker

---

## 15. Feature Additions (22 new)

| Feature | Formula | Causal? |
|---------|---------|---------|
| departure_max_distance_atr | max(close[i] - level) / atr[i] | Yes |
| departure_established | 1 if departure >= 1.75 ATR and 3+ closes | Yes |
| departure_closes_count | Count of bars with close >= level + 0.50*ATR | Yes |
| post_breakout_peak_distance_atr | (peak_price - level) / breakout_atr | Yes |
| days_breakout_to_peak | peak_idx - breakout_idx | Yes |
| days_peak_to_retest | retest_idx - peak_idx | Yes |
| pullback_from_peak_atr | (peak_price - retest_low) / signal_atr | Yes |
| pullback_retracement_fraction | (peak - retest_low) / (peak - level) | Yes |
| approach_direction | from_above=1, from_below=0 | Yes |
| approached_from_above | 1 if 2+ closes above level before touch | Yes |
| pre_retest_distance_atr | (close[t-1] - level) / atr[t-1] | Yes |
| closes_above_level_before_touch | Count | Yes |
| bars_since_last_close_below_level | Count | Yes |
| pullback_slope_atr | (peak - retest_low) / days / signal_atr | Yes |
| pullback_volatility_atr | std(pullback bars) / signal_atr | Yes |
| pullback_volume_contraction | vol(retest) / avg_vol(peak_to_retest) | Yes |
| failed_breakout_before_departure | 1 if failed | Yes |
| number_of_level_crossings | Count | Yes |
| number_of_closes_below_level_after_breakout | Count | Yes |
| entry_distance_atr | (confirm_close - level) / signal_atr | Yes |
| confirmation_rejection_wick | (confirm_close - confirm_low) / signal_atr | Yes |
| confirmation_body_atr | abs(confirm_close - confirm_open) / signal_atr | Yes |

---

## 16. Feature Removals/Replacements (6 changes)

| Feature | Current | Proposed | Reason |
|---------|---------|----------|--------|
| entry | absolute price | REMOVE | Price irrelevant; use entry_distance_atr |
| signal_atr | absolute ATR | REPLACE with signal_atr_pct | Normalized |
| target_atr | constant 2.0 | REMOVE | Same for all |
| stop_atr | constant 0.75 | REMOVE | Same for all |
| time_to_barrier | constant 20 | REMOVE | Same for all |
| breakout_retreat_within_3 | uses bars after breakout | REPLACE with failed_breakout_before_departure | Causal fix |

**Net: 29 -> ~25 features**

---

## 17. Model Architecture

### Recommended: Three-Class Calibrated Classifier
- Class 0: DEEP_DRAWDOWN
- Class 1: WIN
- Class 2: TIMEOUT (exclude from training, handle separately)

### Output Redesign
- Current: score = P(WIN) * 100 (raw probability)
- Proposed: score = percentile_rank among valid candidates (0-100)
- Store separately: p_win, p_deep_drawdown, expected_mfe5, expected_mae5, original_score, visible_score

---

## 18. Percentile-Score Design

```python
# After computing all scores for a market:
# 1. Gather all ACTIVE retest events
# 2. Sort by p_win descending
# 3. Assign percentile: rank / total * 100
# 4. visible_score = percentile * freshness_distance * freshness_time
```

**Interpretation**: 90 = top 10% of valid retests, 50 = median, 10 = bottom 10%, NULL = not a valid entry.

---

## 19. Unit-Testing Plan (40 Tests)

### Causal Structure (1-10)
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

### Approach Direction (11-15)
11. test_approach_from_below_rejected
12. test_shallow_breakout_wiggle_rejected
13. test_repeated_crossing_rejected
14. test_strict_retest_bounds
15. test_delayed_confirmation

### Entry Semantics (16-20)
16. test_close_entry_semantics
17. test_signal_candle_excluded_from_outcome
18. test_target_uses_future_high
19. test_stop_uses_future_low
20. test_same_bar_ambiguity_conservative

### Score Visibility (21-30)
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

### Edge Cases (31-40)
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

## 20. Golden-Chart Testing Plan

### Positive References
- AAPL (2020): Old high -> breakout -> rally -> pullback -> retest
- MU (2023): Memory chip cycle -> breakout -> deep pullback -> retest
- NVDA (2023): AI breakout -> pullback -> retest
- JNJ (2019): Pharma consolidation -> breakout -> retest
- WMT (2020): Retail breakout -> pullback -> retest

### Negative References
- SONO (2026): Breakout continuation, no departure -> FAILED
- GLBE (2026): Recovery from below -> RECOVERY_FROM_BELOW
- SCI (2026): Steady uptrend, no pullback -> OVEREXTENDED
- LILA (2026): Shallow breakout -> FAILED_BREAKOUT
- SOLV (2026): Strong move, no peak/return -> OVEREXTENDED

---

## 21. Causality and Parity Testing

```python
def test_training_inference_parity():
    full = fold_symbol(full_bars)
    resumed = fold_symbol(latest_bars, initial_state=full.state)
    for i in range(len(latest_bars)):
        assert full.current_scores[100+i] == resumed.current_scores[i]

def test_no_future_leakage():
    for event in all_events:
        for feature in BREAKOUT_FEATURES:
            assert feature_value <= event.breakout_date
        for feature in RETEST_FEATURES:
            assert feature_value <= event.confirm_date
```

---

## 22. Database Migration Plan

### Schema Changes
```sql
ALTER TABLE stats ADD COLUMN retest_state TEXT DEFAULT 'NO_SETUP';
ALTER TABLE stats ADD COLUMN retest_event_id TEXT;
ALTER TABLE stats ADD COLUMN retest_confirmation_date TEXT;
ALTER TABLE stats ADD COLUMN retest_entry_distance_atr REAL;
ALTER TABLE stats ADD COLUMN retest_model_version TEXT;
-- Same for historical_screener
```

### Score Clearing
```sql
UPDATE stats SET old_swing_retest_score = NULL, retest_state = 'NO_SETUP';
UPDATE historical_screener SET old_swing_retest_score = NULL, retest_state = 'NO_SETUP';
```

### Migration Steps
1. Add new columns (additive, safe)
2. Set HISTORICAL_SCREENER_VERSION = "asof-v3" to force rebuild
3. Run full historical rebuild
4. Verify score distribution

---

## 23. Refresh Integration Plan

### Changes to dumbmoney/refresh.py
```python
# Step 5.5: Retest scores (after historical screener)
def _run_retest_scores():
    if get_model() is None:
        _bg_progress(6, "Retest: model not loaded, skipping")
        return
    _bg_progress(6, "Computing retest scores...")
    conn = get_db(market)
    try:
        from dumbmoney.retest_engine import populate_historical_scores
        populate_historical_scores(market, conn, only_symbols=hist_symbols,
                                   progress_callback=lambda d, t, m: _bg_progress(6, m))
    finally:
        conn.close()
    _bg_progress(100, "Retest scores updated")
```

### Performance
- Current: ~0.5s per symbol
- 10,000 symbols: ~5,000s = ~83 min
- Mitigation: Only recompute changed symbols (~5% daily = ~4 min)

---

## 24. API/UI Changes

### New Endpoints
```python
GET /api/retest/funnel          # Candidate funnel counts
GET /api/retest/golden-charts   # Golden chart statuses
POST /api/retest/retrain        # Trigger retraining (async)
GET /api/retest/event/<sym>/<id> # Full event trace
```

### UI Changes
```html
<!-- screener.html: Add retest state column -->
{key:'retest_state', label:'State', width:80},
{key:'old_swing_retest_score', label:'Retest Score', width:100, nullText:'--'},

<!-- stock_detail.html: Add retest trace -->
<div>Retest State: <span id="sRetestState"></span></div>
<div>Departure Distance: <span id="sDepartureDist"></span></div>
<div>Peak Distance: <span id="sPeakDist"></span></div>
<div>Pullback Depth: <span id="sPullbackDepth"></span></div>
```

---

## 25. Retraining Plan

### Data Generation
```python
# After engine fix, regenerate:
# 1. Run fold on all 10,791 symbols with new state machine
# 2. Apply candidate gates
# 3. Count surviving events
# 4. If < 500: relax gates and retry
# 5. If >= 500: proceed to training
```

### Walk-Forward Validation
```python
# Expanding window:
# Fold 1: train 2018-2019, test 2020
# Fold 2: train 2018-2020, test 2021
# Fold 3: train 2018-2021, test 2022
# Fold 4: train 2018-2022, test 2023
# Fold 5: train 2018-2023, test 2024-2025
```

### Acceptance Criteria
- Top-10 precision >= 40%
- Top-25 precision >= 35%
- Win rate by decile: monotonically increasing
- MFE by decile: monotonically increasing
- No negative correlation between score and drawdown

---

## 26. Validation and Acceptance Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Top-10 precision | >= 40% | ~26% |
| Top-25 precision | >= 35% | ~26% |
| AUC | >= 0.75 | 0.694 |
| AP | >= 0.55 | 0.434 |
| Events after all gates | >= 500 | ~300 (est.) |

---

## 27. Historical Rebuild Plan

1. Bump HISTORICAL_SCREENER_VERSION to "asof-v3"
2. On next refresh, full rebuild triggered
3. Compute retest scores for all historical bars
4. Write to historical_screener with new columns
5. Clear old scores first (NULL semantics)

**Timeline**: US ~3 hours, India ~8 min, Total ~3.5 hours

---

## 28. Portfolio Backtest Plan

```python
# After model retraining:
# 1. For each historical date, get top-K retest scores
# 2. Simulate entry at confirmation close
# 3. Exit at target/stop/time barrier
# 4. Aggregate returns across all symbols
# 5. Compare to benchmark (SPY)
```

---

## 29. Runtime/Performance Plan

| Optimization | Impact |
|--------------|--------|
| Batch model predictions | 10x faster |
| Incremental fold | Only changed symbols |
| Score caching | Avoid recomputation |
| Multi-processing | 4x faster |

**Target**: Full refresh < 10 min, Incremental < 30 sec

---

## 30. Rollback Strategy

- **Code**: git revert <commit>
- **Data**: Additive schema changes (safe)
- **Model**: Keep old at models/retest_v1_backup/
- **Safe mode**: ENABLE_NEW_ENGINE = False in config

---

## 31. Risks and Unresolved Decisions

### Risks
| Risk | Severity | Mitigation |
|------|----------|------------|
| Too few events after gates | High | Start with relaxed gates |
| Model overfits small dataset | Medium | Use simpler model |
| Historical rebuild too slow | Medium | Incremental rebuild |
| Breaking existing screener | High | Full regression tests |
| Feature leakage | High | Causality audit |
| Departure threshold too strict | Medium | Validate empirically |
| Approach-from-above false positives | Medium | Golden chart review |

### Unresolved Decisions
1. Departure threshold: 1.75 ATR vs 1.0 ATR
2. Peak detection: local max vs sliding window
3. Pullback minimum: 1.0 ATR
4. Model: CatBoost vs Logistic Regression
5. Score scale: probability vs percentile
6. Timeout: 60 vs 80 bars

---

## 32. Phased Work Order

### PHASE 0: Current-Code Audit and Top-Stock Tracing
- **Files**: dumbmoney/retest_audit.py (new)
- **Deliverables**: Event trace for SONO, GLBE, SCI, LILA, SOLV
- **Tests**: None
- **Entry**: Current HEAD
- **Exit**: Audit report
- **Rollback**: N/A

### PHASE 1: Reference Causal Event Engine
- **Files**: dumbmoney/retest_engine.py, dumbmoney/retest_config.py
- **Deliverables**: New state machine with 14 states
- **Tests**: Tests 1-15
- **Entry**: Phase 0 complete
- **Exit**: All Phase 1 tests pass
- **Rollback**: git revert

### PHASE 2: Realistic Unit Tests and Golden Charts
- **Files**: tests/test_retest_engine.py, tests/test_retest_golden.py (new)
- **Deliverables**: 25 new tests with realistic data
- **Tests**: Tests 16-40
- **Entry**: Phase 1 complete
- **Exit**: All 40 tests pass
- **Rollback**: git revert

### PHASE 3: Close-Entry and Outcome Corrections
- **Files**: dumbmoney/retest_engine.py
- **Deliverables**: Target uses high, outcome starts after confirm
- **Tests**: Tests 16-20
- **Entry**: Phase 2 complete
- **Exit**: All outcome tests pass
- **Rollback**: git revert

### PHASE 4: Database Status and NULL Semantics
- **Files**: dumbmoney/db.py, dumbmoney/engine.py, dumbmoney/app.py
- **Deliverables**: New columns, NULL semantics enforced
- **Tests**: Tests 36-40
- **Entry**: Phase 3 complete
- **Exit**: NULL semantics verified
- **Rollback**: Migration is additive

### PHASE 5: Incremental Refresh and Historical Causality
- **Files**: dumbmoney/refresh.py, dumbmoney/engine.py
- **Deliverables**: Prefix-invariant historical scores
- **Tests**: Tests 33-35
- **Entry**: Phase 4 complete
- **Exit**: Refresh identical to full rebuild
- **Rollback**: git revert

### PHASE 6: Feature Rebuild and Audit
- **Files**: dumbmoney/retest_engine.py, dumbmoney/retest_training_parallel.py
- **Deliverables**: 25-feature vector, no leakage
- **Tests**: Test 33
- **Entry**: Phase 5 complete
- **Exit**: Feature parity verified
- **Rollback**: git revert

### PHASE 7: Generate New Candidate Dataset
- **Files**: dumbmoney/retest_training_parallel.py
- **Deliverables**: New event dataset, funnel report
- **Tests**: None
- **Entry**: Phase 6 complete
- **Exit**: Dataset ready (>= 500 events)
- **Rollback**: Delete generated data

### PHASE 8: Human Visual Review
- **Deliverables**: 400 samples reviewed
- **Tests**: None
- **Entry**: Phase 7 complete
- **Exit**: Review complete
- **Rollback**: N/A

### PHASE 9: Walk-Forward Training
- **Files**: dumbmoney/retest_training_parallel.py, dumbmoney/retest_finetune_full.py
- **Deliverables**: Validated model, calibration map
- **Tests**: Validation metrics >= targets
- **Entry**: Phase 8 complete
- **Exit**: Model meets acceptance criteria
- **Rollback**: Keep old model

### PHASE 10: Live Model Integration
- **Files**: dumbmoney/retest_engine.py, dumbmoney/engine.py, dumbmoney/app.py
- **Deliverables**: Model wired, scores correct
- **Tests**: End-to-end integration
- **Entry**: Phase 9 complete
- **Exit**: Scores visible in app
- **Rollback**: git revert

### PHASE 11: Top-K and Score-Decile Validation
- **Deliverables**: Precision report, decile analysis
- **Tests**: Top-10 precision >= 40%
- **Entry**: Phase 10 complete
- **Exit**: Validation passes
- **Rollback**: Adjust threshold

### PHASE 12: Close-Entry and Next-Open Backtests
- **Files**: dumbmoney/retest_backtest.py
- **Deliverables**: Backtest results vs benchmark
- **Tests**: Backtest metrics
- **Entry**: Phase 11 complete
- **Exit**: Backtest complete
- **Rollback**: N/A

### PHASE 13: Dry-Run Historical Rebuild
- **Deliverables**: Rebuild on 100 symbols, timing report
- **Tests**: Score distribution
- **Entry**: Phase 12 complete
- **Exit**: Rebuild works, < 10 min for 100 symbols
- **Rollback**: N/A

### PHASE 14: Production Rebuild and Verification
- **Deliverables**: Full rebuild, UI/API verified
- **Tests**: All 40 tests
- **Entry**: Phase 13 complete
- **Exit**: System ready for production
- **Rollback**: git revert to pre-PHASE-0

---

## 33. Estimated Runtime

| Phase | Time | Cores | Memory |
|-------|------|-------|--------|
| 0 | 2h | 1 | 2GB |
| 1 | 4h | 1 | 2GB |
| 2 | 3h | 1 | 2GB |
| 3 | 1h | 1 | 2GB |
| 4 | 2h | 1 | 2GB |
| 5 | 2h | 1 | 2GB |
| 6 | 2h | 1 | 2GB |
| 7 | 4h | 4 | 4GB |
| 8 | 8h | human | -- |
| 9 | 6h | 4 | 4GB |
| 10 | 2h | 1 | 2GB |
| 11 | 2h | 1 | 2GB |
| 12 | 4h | 4 | 4GB |
| 13 | 1h | 1 | 2GB |
| 14 | 2h | 1 | 2GB |
| **Total** | **~37h** | **4 cores** | **4GB** |

---

## 34. Release Blockers

1. **< 500 events after all gates** -> Relax thresholds or add markets
2. **Top-10 precision < 30%** -> Model not ready
3. **Causality violation in any feature** -> Fix before training
4. **Existing tests broken** -> Fix before deploy
5. **Refresh time > 15 min** -> Optimize
6. **NULL semantics not enforced** -> Fix before deploy
7. **Historical rebuild corrupts data** -> Fix before deploy

---

## 35. Questions Answered from Current Code Inspection

### Q1: Which exact condition currently allows a stock to be considered a retest?
**A**: close >= level + 0.25 ATR + body >= 0.05 ATR + close_location >= 0.60 + zone age >= 20. Then low <= level + 0.40 ATR after delay >= 3. Then close >= level - 0.10 ATR within 3 bars.

### Q2: Does current code require meaningful departure after breakout?
**A**: NO. Transitions directly from BREAKOUT_CONFIRMED to WAITING_FOR_RETEST.

### Q3: Does current code store and use a distinct post-breakout peak?
**A**: NO. No peak detection exists.

### Q4: Does it require approach from above?
**A**: NO. No approach-direction logic.

### Q5: Can a failed breakout later revive into a retest?
**A**: YES (BUG). Old event cleared (z.cycle = None), but score may persist in current_scores until next terminal state.

### Q6: Can repeated crossings create repeated events?
**A**: YES. Each crossing above level with age >= 20 starts a new cycle.

### Q7: Does target detection use future high or future close?
**A**: CLOSE (BUG). Line 543: hit_target = close[t] >= entry + cfg.BARRIER_UP_ATR * sa. Should use high[t].

### Q8: Does live state resolution run during current scoring?
**A**: YES. Correct.

### Q9: Why do completed trades retain visible scores?
**A**: No clearing logic. TARGET_REACHED and STOPPED_OUT states dont set score to NULL.

### Q10: Why are zero values stored instead of NULL?
**A**: DB default is 0. UI renders NULL as 0 via (s.score || 0).

### Q11: Is historical scoring prefix-invariant?
**A**: YES (partially). Fold is causal, but model scoring may vary with fold start point.

### Q12: Which features most likely make CatBoost favour momentum?
**A**: breakout_consecutive_closes, trend_higher_highs, sma20_slope_atr, entry (absolute price), signal_atr (absolute ATR).

### Q13: Is raw entry price used?
**A**: YES. entry is a raw absolute price feature.

### Q14: Are absolute ATR and constants used?
**A**: YES. signal_atr, target_atr, stop_atr, time_to_barrier.

### Q15: Are training and inference feature calculations identical?
**A**: YES (currently). Both use _event_to_feature_array.

### Q16: Is current model output a percentile or raw probability?
**A**: Raw probability x 100.

### Q17: Why did SONO, GLBE, SCI, LILA, SOLV qualify?
**A**: No departure, peak, or approach-direction gates. Model learned momentum patterns.

### Q18: How many events survive departure requirement?
**A**: UNKNOWN -- requires Phase 0 audit. Estimated 10-20%.

### Q19: How many survive approach + pullback requirements?
**A**: UNKNOWN. Estimated 5-10% of current.

### Q20: What event count remains after strict dedup?
**A**: UNKNOWN -- requires Phase 7.

### Q21: Is that count sufficient for separate models?
**A**: PROBABLY NOT for CatBoost. May need logistic regression or pooled data.

### Q22: Which thresholds require empirical tuning?
**A**: MIN_DEPARTURE_DISTANCE_ATR, MIN_PULLBACK_FROM_PEAK_ATR, MAX_ENTRY_DISTANCE_ATR, RETEST_DELAY_MIN, CONFIRM_WINDOW.

### Q23: Safest migration path?
**A**: Additive schema changes. New columns with NULL defaults. Full rebuild with version bump.

### Q24: What must be proven before retraining?
**A**:
1. >= 500 events after gates
2. Human review of 400 samples
3. No causality violations
4. Training/inference parity

---

## End of Plan
