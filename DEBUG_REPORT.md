# Old Swing Retest Score — Why Scoring Is Bad (Debug Report)

**Date**: 2026-08-02
**Project**: `C:\Users\Admin\Desktop\stock test\open code v5 claude prompt`
**Model**: CatBoost, 580 trees, AUC=0.694, AP=0.434

---

## Current State

| Metric | Value |
|--------|-------|
| Total symbols | 10,791 |
| Stats with score > 0 | **1,557** (14.4%) |
| Stats with score = 0 | 9,234 |
| Stats with score = NULL | **0** |
| Historical rows with score > 0 | 1,311,334 |
| Test AUC (held-out) | 0.694 |
| Test Average Precision | 0.434 |
| Model file | `models/retest_v1/model.cbm` (694KB) |

**Problem**: Only 14.4% of symbols have any score. The other 85.6% show 0.
**Problem**: AUC of 0.694 means the model barely distinguishes WIN from DEEP_DRAWDOWN.
**Problem**: Average Precision of 0.434 means precision at typical thresholds is poor.
**Problem**: Top scores (66, 57, 47) seem arbitrary — no clear relationship to actual price action.

---

## Top 15 Scores with Historical Data

### 1. SONO — Score: 66.38
```
2026-07-16  O=14.02 H=14.36 L=13.93 C=13.95 V=33697
2026-07-17  O=14.38 H=15.50 L=14.38 C=15.10 V=259958
2026-07-18  (no data)
2026-07-20  O=15.32 H=15.84 L=14.95 C=15.21 V=159204
2026-07-21  O=15.42 H=15.44 L=14.95 C=15.05 V=28841
2026-07-22  O=14.88 H=14.88 L=14.34 C=14.67 V=62887
2026-07-23  O=14.34 H=14.64 L=14.32 C=14.53 V=113754
2026-07-24  O=14.59 H=14.77 L=14.40 C=14.71 V=115259
2026-07-27  O=14.94 H=15.85 L=14.92 C=15.66 V=111233
2026-07-28  O=16.12 H=16.83 L=15.78 C=16.83 V=135935
2026-07-29  O=16.75 H=17.60 L=16.65 C=17.55 V=287208
```
Price trend: 13.95 → 17.55 (+25.8% in 13 days). Score 66.38 suggests "high quality retest opportunity" but the stock is already up 26%.

### 2. GLBE — Score: 57.82
```
2026-07-16  O=38.59 H=38.95 L=38.16 C=38.77 V=6357
2026-07-17  O=37.56 H=38.43 L=37.56 C=38.07 V=33119
2026-07-20  O=38.08 H=38.08 L=36.45 C=36.55 V=111951
2026-07-21  O=36.03 H=36.30 L=34.97 C=35.45 V=50521
2026-07-22  O=35.57 H=36.24 L=35.33 C=35.54 V=64171
2026-07-23  O=34.60 H=34.74 L=33.87 C=34.54 V=58525
2026-07-24  O=35.18 H=36.26 L=35.10 C=36.26 V=68622
2026-07-27  O=37.12 H=38.16 L=37.12 C=37.74 V=74695
2026-07-28  O=38.41 H=39.17 L=38.41 C=38.91 V=116801
2026-07-29  O=38.91 H=40.30 L=38.51 C=40.27 V=216368
```
Price trend: 38.77 → 40.27 (+3.9%). Moderate gain. Score 57.82 seems high for a 4% move.

### 3. SCI — Score: 47.50
```
2026-07-16  O=78.85 H=79.67 L=78.85 C=79.52 V=29784
2026-07-17  O=80.28 H=80.97 L=78.59 C=78.70 V=89672
2026-07-20  O=78.25 H=78.25 L=77.47 C=78.00 V=55345
2026-07-21  O=78.04 H=78.04 L=77.02 C=77.46 V=49915
2026-07-22  O=78.11 H=78.11 L=77.11 C=77.27 V=114229
2026-07-23  O=76.82 H=79.75 L=76.82 C=79.36 V=86271
2026-07-24  O=79.78 H=82.73 L=79.28 C=82.33 V=100594
2026-07-27  O=82.89 H=83.92 L=82.73 C=82.77 V=76509
2026-07-28  O=84.32 H=85.92 L=84.12 C=84.98 V=73206
2026-07-29  O=84.83 H=85.77 L=83.84 C=85.68 V=137275
```
Price trend: 79.52 → 85.68 (+7.8%). Score 47.5 seems moderate but this is a steady uptrend, not a retest pattern.

### 4. LILA — Score: 43.30
```
2026-07-16  O=7.59 H=7.61 L=7.49 C=7.50 V=7059
2026-07-17  O=7.42 H=7.49 L=7.29 C=7.33 V=51625
2026-07-20  O=7.43 H=7.43 L=7.23 C=7.34 V=46553
2026-07-21  O=7.32 H=7.38 L=7.20 C=7.28 V=14283
2026-07-22  O=7.28 H=7.47 L=7.13 C=7.41 V=71807
2026-07-23  O=7.23 H=7.42 L=7.21 C=7.42 V=36834
2026-07-24  O=7.54 H=7.59 L=7.45 C=7.51 V=39739
2026-07-27  O=7.62 H=7.85 L=7.61 C=7.79 V=70360
2026-07-28  O=7.77 H=8.51 L=7.77 C=8.31 V=99029
2026-07-29  O=8.38 H=8.52 L=8.22 C=8.52 V=138614
```
Price trend: 7.50 → 8.52 (+13.6%). Small cap, volatile. Score 43.3.

### 5. SOLV — Score: 43.00
```
2026-07-16  O=80.30 H=81.89 L=80.30 C=80.75 V=7624
2026-07-17  O=81.61 H=83.26 L=80.71 C=81.31 V=45417
2026-07-20  O=80.50 H=81.23 L=79.16 C=79.22 V=60430
2026-07-21  O=78.36 H=79.18 L=78.23 C=79.18 V=10653
2026-07-22  O=78.95 H=78.95 L=77.45 C=77.69 V=25377
2026-07-23  O=77.62 H=77.73 L=76.80 C=77.30 V=50698
2026-07-24  O=78.21 H=78.66 L=77.33 C=78.03 V=29635
2026-07-27  O=78.85 H=81.06 L=78.85 C=80.43 V=59642
2026-07-28  O=83.19 H=87.14 L=83.19 C=86.14 V=179132
2026-07-29  O=86.15 H=88.62 L=86.15 C=88.53 V=111127
```
Price trend: 80.75 → 88.53 (+9.6%). Score 43.0.

---

## Architecture

```
bars (SQLite) → retest_engine.fold_symbol() → EventCycle[]
                    ↓
             finalize_labels() → MFE/MAE/outcome (labels)
                    ↓
             retest_training_parallel.py → CatBoost(model.cbm)
                    ↓
             score_fn(cycle, zones) → model.predict_proba() * 100
                    ↓
             engine.py → stats.old_swing_retest_score
                    ↓
             /api/screener → screener.html column
```

---

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `dumbmoney/retest_config.py` | 65 | All thresholds, enums, model version |
| `dumbmoney/retest_engine.py` | 930 | Causal engine + model integration |
| `dumbmoney/engine.py` | 1113 | Main indicator engine (calls retest) |
| `dumbmoney/app.py` | 2915 | Flask API (+ 3 new retest endpoints) |
| `dumbmoney/refresh.py` | 808 | Refresh pipeline (+ retest historical step) |
| `dumbmoney/retest_training_parallel.py` | 285 | Full-data training (multiprocessing) |
| `dumbmoney/retest_backtest.py` | 200 | Backtest evaluator |
| `dumbmoney/retest_finetune_full.py` | 350 | Hyperparameter search |
| `models/retest_v1/model.cbm` | 694KB | Trained CatBoost model |
| `models/retest_v1/metadata.json` | 1.5KB | Training metadata |
| `tests/test_retest_engine.py` | — | 12 structural tests |
| `tests/test_retest_labels.py` | — | 6 labeler tests |

---

## Git History

```
02c49b6 PHASE 10: Wire model into engine, add versioning, backtest API
3720b5c Update .gitignore to exclude all models/
0d84089 PHASE 7-9: Fine-tuning pipeline with hyperparameter search
ada583b PHASE 3-6: Complete retest training pipeline with full data training
f9df3f9 PHASE 0: checkpoint, legacy quarantine, call-graph map, report skeleton
```

---

## Config Constants (retest_config.py)

```python
# Swing / zone
SWING_LOOKBACK = 5
SWING_CONFIRMATION = 5
MIN_PROMINENCE_ATR = 1.5
ZONE_CLUSTER_ATR = 0.4

# Level age
MIN_LEVEL_AGE_AT_BREAKOUT = 20
AGE_BANDS = ((20, 39), (40, 79), (80, 159), (160, 10**9))

# Breakout
BREAKOUT_LEVEL_TOUCH_ATR = 0.25
BREAKOUT_BODY_MIN_ATR = 0.05
BREAKOUT_CLOSE_LOCATION_MIN = 0.60

# Retest
RETEST_DELAY_MIN = 3
RETEST_DELAY_MAX = 80
RETEST_BOUND_LO_ATR = -0.50
RETEST_BOUND_HI_ATR = 0.40
CONFIRM_CLOSE_LEVEL_ATR = -0.10
CONFIRM_WINDOW = 3
INVALIDATE_CLOSE_LEVEL_ATR = -0.60

# Outcome
BARRIER_UP_ATR = 2.00       # target: close >= entry + 2.0 * atr
BARRIER_DOWN_ATR = -0.75    # stop: low <= entry - 0.75 * atr
TIME_BARRIER = 20
ATR_PERIOD = 14
MFE_MAE_WINDOWS = (5, 10, 20)
DAYS_1ATR = 1.0

# Freshness decay
FRESHNESS_DISTANCE = ((0.5, 1.0), (1.0, 0.9), (1.5, 0.7), (2.0, 0.4))
FRESHNESS_TIME = ((5, 1.0), (10, 0.9), (15, 0.7), (20, 0.5))

# Model
MODEL_VERSION = "v1_20260801"
MODEL_PATH = "models/retest_v1/model.cbm"
MODEL_THRESHOLD_DEFAULT = 0.30
MODEL_AUC_TRAINING = 0.694
```

---

## Event State Machine

```
BREAKOUT_CONFIRMED → WAITING_FOR_RETEST → (touch in band)
  → WAITING_FOR_CONFIRMATION → (close >= level - 0.10*ATR)
  → SIGNAL_GENERATED (close-entry, entry = confirm close)
  → [TARGET_REACHED | STOPPED_OUT | EXPIRED | INVALIDATED]
```

**Scoring happens at SIGNAL_GENERATED** — the model predicts WIN probability at confirmation time, then freshness decay is applied per bar:

```
visible_score = original_score * freshness_distance * freshness_time
```

---

## 29 Feature Columns (Input to Model)

```
breakout_body_atr           # body / atr at breakout
breakout_close_location     # (close-low)/(high-low) at breakout
breakout_gap_atr            # gap / atr at breakout
breakout_volume_ratio       # vol / 20day avg at breakout
breakout_consecutive_closes # bars with close above level before breakout
breakout_prior_close_rel    # (prior_close - level) / atr
breakout_retreat_within_3   # did price retreat below breakout level within 3 bars?
breakout_age_at             # age of zone in bars at breakout

retest_low_atr              # depth of retest low in ATR units
retest_depth_atr            # distance from level to retest low / signal_atr
retest_touch_candles        # count of bars touching retest band
retest_closes_below_level   # count of closes below level during retest
retest_volume_ratio         # retest bar volume / 20day avg

zone_prominence_atr         # prominence of zone in ATR
zone_width_atr              # width of zone cluster in ATR
zone_reactions              # number of prior probes
zone_false_breakouts        # false breakout count

age_band                    # 0-3: zone age category
trend_higher_highs          # consecutive higher highs
context_pivot_low_dist_atr  # distance to nearest swing low / atr
sma20_slope_atr             # SMA20 slope in ATR units
sma20_above_sma60           # trend filter (1/0)
median_traded_value_log     # log(median(close*volume)) over lookback

entry                       # confirmation close price
signal_atr                  # ATR at confirmation
confirm_close_location      # (close-low)/(high-low) at confirmation

target_atr                  # constant 2.0 (hardcoded)
stop_atr                    # constant 0.75 (hardcoded)
time_to_barrier             # constant 20 (hardcoded)
```

---

## Training Data Summary

| Metric | Value |
|--------|-------|
| Symbols processed | 10,791 |
| Total events extracted | 271,219 |
| WIN outcomes | 70,501 (26.0%) |
| DEEP_DRAWDOWN outcomes | 195,423 (72.1%) |
| TIMEOUT outcomes | 5,295 (2.0%) |
| Train size (after gap) | 133,868 |
| Val size (after gap) | 66,812 |
| Test size (after gap) | 70,539 |
| Gap enforced | 30 calendar days |

---

## Test Results (ALL PASS)

```
test_01_pivot_only_known_after_confirmation ... ok
test_01b_no_zone_before_p_plus_confirmation ... ok
test_02_age19_no_breakout_age20_breakout ... ok
test_03_one_event_per_breakout_cycle ... ok
test_04_body_min ... ok
test_04b_close_location_min ... ok
test_04c_valid_breakout ... ok
test_05_zone_ids_unique_and_join ... ok
test_06a_touch_above_band_is_no_touch ... ok
test_06b_early_touch_ignored ... ok
test_06c_invalidation_after_retest ... ok
test_06d_confirmation_fails_within_window ... ok
test_06e_confirmation_same_candle ... ok
test_07_mfe_mae_win ... ok
test_08_mfe_mae_stopped_out ... ok
test_09_days_to_1atr_timeout ... ok
test_15_clean_retest_shallower_than_loose ... ok
test_16_far_away_levels_give_null_scores ... ok
```

---

## Known Issues / Questions for ChatGPT

### 1. Why is AUC only 0.694?
The model barely discriminates WIN from DEEP_DRAWDOWN. 0.694 AUC means ~69% of random WIN/LOSS pairs are correctly ordered. For a trading model, you'd want >0.75. Why is the signal-to-noise so low?

### 2. Why do only 1,557 out of 10,791 symbols have scores > 0?
85.6% of symbols show score=0. Is the engine too restrictive in finding breakouts? Are zones not being found? Is the state machine too strict?

### 3. Are the top scores (SONO 66, GLBE 57, SCI 47) meaningful?
These stocks are already trending up when scored. Is the model rewarding "momentum" rather than "quality retest structure"? Should high scores correspond to pullbacks to old highs, not continuing rallies?

### 4. Is the freshness decay too aggressive?
Scores decay by distance from breakout level AND time since confirmation. Could this be suppressing scores for old but still-valid setups?

### 5. Are the features leaking future information?
Features like `breakout_retreat_within_3` use bars after the breakout. Is any feature computed with knowledge that wouldn't be available at signal time?

### 6. Why is Average Precision only 0.434?
With 26% positive class rate, a random model would have AP≈0.26. 0.434 is better than random but still weak. What features drive the most discrimination?

### 7. Is the class imbalance (72% LOSS vs 26% WIN) the root problem?
The model may be learning to predict "most things lose" rather than "this specific setup wins". Should we use focal loss, SMOTE, or change the label definition?

### 8. Should TIMEOUT events (5,295) be included in training?
Currently excluded (censored). But 2% of events are TIMEOUT. If we include them as a third class or as partial labels, would performance improve?

### 9. Are the constant features (target_atr=2.0, stop_atr=0.75, time_to_barrier=20) adding noise?
These are the same for every event. They take up 3 of 29 features. Should they be removed?

### 10. Is the model overfitting to historical patterns that don't generalize?
Training AUC=0.694 on held-out 2025-2026 data. What was the training period? Could the model be memorizing 2020-2021 patterns that don't apply now?

---

## Data Pipeline Flow

```
1. bars table (OHLCV)
   ↓
2. wilders_atr(high, low, close, period=14)
   ↓
3. fold_symbol() → RetestEngine
   - Detect swing pivots (SWING_LOOKBACK=5, SWING_CONFIRMATION=5)
   - Cluster pivots into zones (ZONE_CLUSTER_ATR=0.4)
   - State machine: breakout → retest → confirm → signal → outcome
   ↓
4. EventCycle objects with 29 features
   ↓
5. finalize_labels() → MFE/MAE/days_to_1atr
   ↓
6. compute_retest_score_for_symbol()
   - If model loaded: predict_proba → * 100 → freshness decay
   - If no model: NaN (structure-only)
   ↓
7. stats.old_swing_retest_score (current)
8. historical_screener.old_swing_retest_score (historical)
```

---

## Model Metadata

```json
{
  "market": "US",
  "total_events": 271219,
  "train_size": 133868,
  "val_size": 66812,
  "test_size": 70539,
  "test_results": {
    "auc": 0.6942520623586731,
    "average_precision": 0.4338057059668018,
    "confusion_matrix": [[23170, 27134], [3722, 14529]]
  },
  "outcome_distribution": {
    "DEEP_DRAWDOWN": 195423,
    "WIN": 70501,
    "TIMEOUT": 5295
  },
  "timestamp": "2026-08-01T..."
}
```

---

## What to Ask ChatGPT

Copy this section and paste to ChatGPT:

> I built a machine learning model to score "old swing high retest" opportunities on US stocks. The model trains on 271K historical events from 10,791 symbols and achieves AUC=0.694 on held-out data.
>
> The top-scoring stocks (SONO=66, GLBE=57, SCI=47) don't look like good retest setups — they're already trending up. Only 14.4% of symbols have non-zero scores.
>
> Here's the architecture, features, config, and data. Why is the scoring bad, and how do I fix it?
>
> [paste entire MD file]
