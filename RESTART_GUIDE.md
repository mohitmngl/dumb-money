# Old Swing Retest Score — Complete Project Report

**Project**: `C:\Users\Admin\Desktop\stock test\open code v5 claude prompt`
**Date**: 2026-08-01
**Status**: PHASE 0–6 complete. Model trained but NOT wired into engine.

---

## Executive Summary

A causal event-state engine for scoring "old swing high retest" opportunities on US equities, backed by a trained CatBoost classifier. 10,791 symbols processed, 271,219 events extracted, test AUC 0.694. The model exists but is **not yet connected** to the live engine — the highest-impact remaining task.

---

## Architecture Overview

```
bars (SQLite) → retest_engine.fold_symbol() → EventCycle[] 
                    ↓
             finalize_labels() → MFE/MAE/outcome
                    ↓
             retest_training.py → CatBoost(model.cbm)
                    ↓
             score_fn → compute_retest_score_for_symbol() → old_swing_retest_score
                    ↓
             engine.py → stats table → /api/screener → screener.html
```

---

## Phases Completed

### PHASE 0 — Foundation
- Git initialized at `f9df3f9`
- `.gitignore` created (excludes `.db`, `models/`, `__pycache__/`)
- `RETEST_AUDIT.md` written (40K words, 311K bytes, 25 sections)
- Checkpoint backup: `retest_checkpoint_20260801_145606/` (36 files)
- Legacy archived to `legacy/`
- Model artifacts quarantined to `models/retest_legacy_v1/`
- Call-graph map: `retest_callgraph.md`

### PHASE 1–2 — Engine + Tests
- `dumbmoney/retest_config.py` — single source of truth for all thresholds
- `dumbmoney/retest_engine.py` — causal event-state engine (701 lines)
- `tests/test_retest_engine.py` — 12 tests (structural correctness)
- `tests/test_retest_labels.py` — 6 tests (labeler correctness)
- **All 18 tests pass**

### PHASE 3 — API/UI Wiring
- `dumbmoney/engine.py` L229/L592: calls `compute_retest_score_for_symbol(grp)`
- `dumbmoney/app.py` L64: column registered in `SCREENER_COLUMN_REFERENCE`
- `dumbmoney/app.py` L420/L627: filter by `min_retest_score`
- `dumbmoney/app.py` L831–860: lazy endpoint `api_stock_retest_score(symbol)`
- `screener.html` L176: `num:true` renders 0 for NULL
- `stock_detail.html` L89: `(s.old_swing_retest_score || 0).toFixed(1)`
- `dumbmoney/db.py` L310–324: migrations add column to stats, historical_screener, string_screener_metrics, historical_string_screener

### PHASE 4 — Train/Val/Test Split
- Gap-enforced split: 30-calendar-day gap between train/val and val/test
- 70/15/15 split ratio
- Censored samples (TIMEOUT) excluded from training
- Result: Train=133,868, Val=66,812, Test=70,539 events

### PHASE 5 — Feature Engineering
29 feature columns extracted from engine events:

| Group | Features |
|-------|----------|
| Breakout quality | `breakout_body_atr`, `breakout_close_location`, `breakout_gap_atr`, `breakout_volume_ratio`, `breakout_consecutive_closes`, `breakout_prior_close_rel`, `breakout_retreat_within_3`, `breakout_age_at` |
| Retest quality | `retest_low_atr`, `retest_depth_atr`, `retest_touch_candles`, `retest_closes_below_level`, `retest_volume_ratio` |
| Zone context | `zone_prominence_atr`, `zone_width_atr`, `zone_reactions`, `zone_false_breakouts` |
| Age/trend | `age_band`, `trend_higher_highs`, `context_pivot_low_dist_atr`, `sma20_slope_atr`, `sma20_above_sma60`, `median_traded_value_log` |
| Signal | `entry`, `signal_atr`, `confirm_close_location`, `target_atr`, `stop_atr`, `time_to_barrier` |

### PHASE 6 — Full Model Training
- **Data**: 10,791 US symbols, 271,219 confirmed events
- **Model**: CatBoostClassifier, 580 iterations, max_depth=6
- **Training time**: ~98 minutes (4 workers)
- **Test AUC**: 0.6943
- **Test AP**: 0.4338
- **Model file**: `models/retest_v1/model.cbm` (694KB)
- **Metadata**: `models/retest_v1/metadata.json`

### PHASE 7–9 — Fine-Tuning
- `dumbmoney/retest_finetuning.py` — grid search over feature subsets + depth
- `dumbmoney/retest_finetune_full.py` — randomized hyperparameter search
- Best found: depth=4, lr=0.05, colsample=0.9, AUC=0.666 (300-symbol sample)
- Full-data model (0.694 AUC) remains best

---

## Key Files

| File | Purpose |
|------|---------|
| `dumbmoney/retest_config.py` | All thresholds, enums, freshness tables |
| `dumbmoney/retest_engine.py` | Causal engine, fold, finalize_labels, current_status |
| `dumbmoney/retest_training.py` | Single-process training pipeline |
| `dumbmoney/retest_training_parallel.py` | Multiprocessing full-data training |
| `dumbmoney/retest_backtest.py` | Backtest evaluator |
| `dumbmoney/retest_finetuning.py` | Grid-search fine-tuning |
| `dumbmoney/retest_finetune_full.py` | Randomized search fine-tuning |
| `dumbmoney/engine.py` | Main engine (imports retest_engine, writes to stats) |
| `dumbmoney/app.py` | Flask API (screener, lazy endpoint) |
| `dumbmoney/db.py` | Schema + migrations |
| `tests/test_retest_engine.py` | 12 structural tests |
| `tests/test_retest_labels.py` | 6 labeler tests |
| `tests/common.py` | Synthetic OHLCV builders |
| `models/retest_v1/model.cbm` | Trained CatBoost model |
| `models/retest_v1/metadata.json` | Training metadata |
| `RETEST_AUDIT.md` | Complete spec/audit (40K words) |

---

## What Is NOT Yet Done (CRITICAL)

### 1. Model NOT Wired Into Engine
**This is the #1 priority.** The trained model exists but is never loaded.

Current code in `retest_engine.py` line 708:
```python
def compute_retest_score_for_symbol(grp, model=None):
    ...
    eng = RetestEngine(market, symbol, score_fn)  # score_fn is None!
```

And in `engine.py` line 229:
```python
retest_series = compute_retest_score_for_symbol(grp)  # no model passed
```

**Result**: `original_score` is always None → `current_scores[t]` is NaN → `old_swing_retest_score` in DB is always NULL/0.

**Fix needed**:
```python
# In retest_engine.py, add:
from catboost import CatBoostClassifier

_MODEL = None

def load_model(path):
    global _MODEL
    _MODEL = CatBoostClassifier()
    _MODEL.load_model(path)
    return _MODEL

def make_score_fn(model):
    def fn(cycle):
        # extract features from cycle
        feat = extract_features_for_model(cycle)
        prob = model.predict_proba([feat])[0, 1]
        return float(prob * 100)  # 0-100 scale
    return fn
```

Then in `engine.py`:
```python
from dumbmoney.retest_engine import load_model, compute_retest_score_for_symbol
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "retest_v1", "model.cbm")
load_model(MODEL_PATH)
SCORE_FN = make_score_fn(_MODEL)
```

### 2. Historical Screener Not Populated
`historical_screener.old_swing_retest_score` column exists in DB but is never written. Only `stats.old_swing_retest_score` gets computed.

In `engine.py` line 592, the historical path calls `compute_retest_score_for_symbol(grp)` but the result is never bulk-written to `historical_screener`.

### 3. Model Version Tracking Missing
`retest_config.py` has:
```python
MODEL_VERSION_PLACEHOLDER = "structure-only"
```
This should be updated to `"v1_20260801"` and a version comparison added to `engine.py` to detect when the model needs reloading.

### 4. No Model Caching
`compute_retest_score_for_symbol` is called per-symbol during every refresh. The model is reloaded each time (if wiring is done). Need singleton caching.

### 5. No Error Fallback
If model load fails, the engine has no fallback to structure-only scoring. The `score_fn=None` path leaves scores as NULL, which is documented behavior but should have a warning/log.

### 6. Backtest Results Not Exposed
`models/retest_v1/backtest_results.csv` has 5,688 rows with per-event predictions but no API endpoint or UI display.

### 7. No Scheduled Retraining
Model is static. No pipeline to periodically retrain on fresh data.

### 8. India Data Not Trained
Only US data (10,791 symbols) was trained. India DB has 4.6M bars but no model.

---

## Database Schema

### `stats` table (current)
```sql
old_swing_retest_score REAL DEFAULT 0
```
- Populated by `engine.py` line 229 during stats computation
- Values: NULL (no setup) or float 0–100 (model score)
- Currently: all NULL because model not wired

### `historical_screener` table (historical)
```sql
old_swing_retest_score REAL DEFAULT 0
```
- Should contain per-date scores for date-filter mode
- Currently: all NULL/0 because no historical write path

### `bars` table
- US: 10,644,551 rows (1Day)
- India: 4,645,040 rows (1Day)

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
BARRIER_UP_ATR = 2.00      # target: close >= entry + 2.0 * atr
BARRIER_DOWN_ATR = -0.75   # stop: low <= entry - 0.75 * atr
TIME_BARRIER = 20
ATR_PERIOD = 14
MFE_MAE_WINDOWS = (5, 10, 20)
DAYS_1ATR = 1.0

# Freshness
FRESHNESS_DISTANCE = ((0.5, 1.0), (1.0, 0.9), (1.5, 0.7), (2.0, 0.4))
FRESHNESS_TIME = ((5, 1.0), (10, 0.9), (15, 0.7), (20, 0.5))

# States
class EventStage(str, Enum):
    BREAKOUT_CONFIRMED, WAITING_FOR_RETEST, WAITING_FOR_CONFIRMATION
    SIGNAL_GENERATED, TARGET_REACHED, STOPPED_OUT
    EXPIRED, INVALIDATED, FAILED

class OutcomeClass(str, Enum):
    WIN = "WIN"
    DEEP_DRAWDOWN = "DEEP_DRAWDOWN"
    TIMEOUT = "TIMEOUT"
```

---

## Test Results

All 18 tests pass:
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

## Git Log

```
ada583b PHASE 3-6: Complete retest training pipeline with full data training
f9df3f9 PHASE 0: checkpoint, legacy quarantine, call-graph map, report skeleton
```

---

## How to Wire the Model (Step-by-Step)

### Step 1: Add model loading to retest_engine.py

```python
from catboost import CatBoostClassifier
import os

_MODEL = None
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "retest_v1", "model.cbm")

def load_model(path=None):
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    path = path or _MODEL_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model not found: {path}")
    _MODEL = CatBoostClassifier()
    _MODEL.load_model(path)
    return _MODEL

def get_model():
    return _MODEL
```

### Step 2: Add feature extraction function to retest_engine.py

```python
def event_to_features(cycle):
    """Extract 29-feature vector from EventCycle for model prediction."""
    features = {
        "breakout_body_atr": cycle.breakout_body_atr or 0.0,
        "breakout_close_location": cycle.breakout_close_location or 0.5,
        "breakout_gap_atr": cycle.breakout_gap_atr or 0.0,
        "breakout_volume_ratio": cycle.breakout_volume_ratio or 1.0,
        "breakout_consecutive_closes": cycle.breakout_consecutive_closes,
        "breakout_prior_close_rel": cycle.breakout_prior_close_rel or 0.0,
        "breakout_retreat_within_3": cycle.breakout_retreat_within_3,
        "breakout_age_at": cycle.age_at_breakout,
        "retest_low_atr": cycle.retest_low_atr or 0.0,
        "retest_depth_atr": cycle.retest_depth_atr or 0.0,
        "retest_touch_candles": cycle.retest_touch_candles,
        "retest_closes_below_level": cycle.retest_closes_below_level,
        "retest_volume_ratio": cycle.retest_volume_ratio or 1.0,
        "zone_prominence_atr": 1.5,  # needs zone lookup
        "zone_width_atr": 0.5,
        "zone_reactions": 0,
        "zone_false_breakouts": 0,
        "age_band": cycle.age_band,
        "trend_higher_highs": cycle.trend_higher_highs,
        "context_pivot_low_dist_atr": cycle.context_pivot_low_dist_atr or 0.0,
        "sma20_slope_atr": cycle.sma20_slope_atr or 0.0,
        "sma20_above_sma60": cycle.sma20_above_sma60,
        "median_traded_value_log": float(np.log1p(cycle.median_traded_value)) if not np.isnan(cycle.median_traded_value) else 0.0,
        "entry": cycle.entry,
        "signal_atr": cycle.signal_atr,
        "confirm_close_location": cycle.confirm_close_location or 0.5,
        "target_atr": 2.0,
        "stop_atr": 0.75,
        "time_to_barrier": 20,
    }
    return features
```

### Step 3: Create score_fn and pass to engine

In `retest_engine.py`, add:
```python
def make_score_fn(model):
    def score_fn(cycle):
        feat = event_to_features(cycle)
        import numpy as np
        arr = np.array([[feat[col] for col in FEATURE_COLUMNS]]).astype(float)
        prob = model.predict_proba(arr)[0, 1]
        return float(prob * 100)
    return score_fn
```

### Step 4: Update compute_retest_score_for_symbol

```python
def compute_retest_score_for_symbol(grp, model=None):
    global _MODEL
    if model is None:
        model = _MODEL
    if model is None:
        # No model loaded — return NaN scores (structure-only mode)
        ...
    score_fn = make_score_fn(model)
    ...
    eng = RetestEngine(market, symbol, score_fn)
```

### Step 5: Update engine.py to load model at startup

```python
from dumbmoney.retest_engine import load_model, compute_retest_score_for_symbol

# At module level or in app init:
try:
    load_model()
except FileNotFoundError:
    logger.warning("Retest model not found — scores will be NULL")
```

### Step 6: Update app.py lazy endpoint

```python
from dumbmoney.retest_engine import get_model, compute_retest_score_current
score = compute_retest_score_current(bars)
```

---

## Training Commands

```bash
# Run full training (10,791 symbols, ~98 min)
python dumbmoney/retest_training_parallel.py

# Run fine-tuning (20 iterations, ~10 min per 300 symbols)
python dumbmoney/retest_finetune_full.py --iterations 20 --max-symbols 300

# Run backtest
python dumbmoney/retest_backtest.py

# Run tests
python -m unittest discover -s tests -t . -v
```

---

## Environment

- Python 3.13.13 via miniforge3
- catboost 1.2.10
- scikit-learn 1.9.0
- numpy 2.4.6
- pandas 3.0.3
- numba 0.66.0
- pytest: NOT installed
- shap: NOT installed

---

## Data Stats

| Market | Symbols | Bars | Historical Rows | Events |
|--------|---------|------|-----------------|--------|
| US | 10,791 | 10,644,551 | ~50M+ | 271,219 |
| India | ~500 | 4,645,040 | ~2M+ | N/A (not trained) |

---

## Next Priority Tasks (ranked)

1. **Wire model into engine** — makes scores actually appear in the app
2. **Populate historical_screener** — enables date-filter mode
3. **Add model version to config** — enables drift detection
4. **Cache model in singleton** — avoids reload on every call
5. **Add model fallback logging** — warning when model unavailable
6. **Expose backtest results in API** — `/api/retest/backtest`
7. **Train India model** — retrain with india.db
8. **Add scheduled retraining** — cron or periodic refresh hook
9. **Add SHAP explanation endpoint** — requires shap install
10. **Add model performance dashboard** — AUC over time tracking

---

## Notes for Continuing AI

- The project uses stdlib unittest, NOT pytest
- Tests run: `python -m unittest discover -s tests -t . -v`
- The model is a CatBoost `.cbm` file at `models/retest_v1/model.cbm`
- Feature columns are defined in `retest_training.py` as `FEATURE_COLUMNS`
- The engine's `EventCycle` dataclass has all the fields needed for feature extraction
- Zone info (prominence, width, reactions, false_breakouts) must be looked up from `result.zones` by `zone_id`
- The score is a probability × 100 (0–100 scale), stored as float in DB
- NULL means "no active retest" — do not convert to 0
