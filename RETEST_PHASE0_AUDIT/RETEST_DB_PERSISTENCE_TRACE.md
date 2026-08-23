# Database Persistence Bug Trace

**Date**: 2026-08-02
**Status**: READ-ONLY DIAGNOSTIC

---

## Executive Summary

The V2 plan incorrectly claimed all 1,557 non-null scores were "stale." The actual reconciliation shows **47 out of 50 top scores are VALUE_MISMATCH** — the engine computes different scores than what's stored in the DB. This is because:
1. The model was retrained (new artifact)
2. The engine code changed (PHASE 10 wiring)
3. But the DB was never updated with new computations

Additionally, there are **three distinct bugs** in the persistence layer that prevent proper score updates.

---

## Bug #1: Lazy Endpoint Cache Shortcut (CRITICAL)

**File**: `dumbmoney/app.py`
**Function**: `api_stock_retest_score()`
**Lines**: 831-860

```python
# Line 838-840: THE BUG
row = conn.execute("SELECT old_swing_retest_score FROM stats WHERE symbol=?", (symbol,)).fetchone()
if row and row[0] and row[0] > 0:  # <-- BUG: truthiness check skips None/0
    return jsonify({"symbol": symbol, "old_swing_retest_score": row[0], "cached": True})
```

**Problem**: If DB has any positive score, return it immediately WITHOUT recomputing. This means:
- Old scores persist forever
- New model predictions are ignored
- NULL scores are never written back

**Reproducible with SONO**:
```python
# DB has 66.38, engine computes 44.43
# Lazy endpoint returns 66.38 (cached) forever
```

---

## Bug #2: NaN Converted to 0 (HIGH)

**File**: `dumbmoney/app.py`
**Function**: `api_stock_retest_score()`
**Line**: 853

```python
score_val = 0.0 if score is None or (isinstance(score, float) and np.isnan(score)) else round(float(score), 2)
```

**Problem**: NaN scores are converted to 0.0, which:
- Violates NULL semantics (0 ≠ NULL)
- Prevents future recomputation (0 passes the `> 0` check on line 839... wait, no it doesn't)
- Actually, 0 would NOT pass `row[0] > 0`, so it would recompute next time

**Correction needed**: Convert NaN to None, not 0.0.

---

## Bug #3: INSERT OR REPLACE May Preserve Old Values (MEDIUM)

**File**: `dumbmoney/engine.py`
**Function**: `vectorized_stats_pass()`
**Lines**: 277-295

```python
conn.executemany(
    """INSERT OR REPLACE INTO stats (
        symbol, name, price, volume, ...
        old_swing_retest_score
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    records
)
```

**Analysis**: INSERT OR REPLACE should overwrite all columns. Let me verify...

Actually, looking at line 274:
```python
r.get("old_swing_retest_score", None),
```

This passes `None` when score is NaN. SQLite should write NULL. So this path is CORRECT.

**The bug is ONLY in the lazy endpoint.**

---

## Bug #4: Historical Path Uses fillna(0) (FIXED IN V1)

**File**: `dumbmoney/engine.py`
**Function**: `compute_historical_retest_scores()` (or similar)
**Lines**: 597-601

```python
# BEFORE (old code):
out["old_swing_retest_score"] = retest_series.fillna(0).round(2)

# AFTER (current code):
out["old_swing_retest_score"] = retest_series.round(2)
```

**Status**: Fixed in PHASE 10. Current code preserves NaN.

---

## Bug #5: Schema Default is 0 (LOW)

**File**: `dumbmoney/db.py`
**Lines**: 312, 316, 320, 324

```sql
old_swing_retest_score REAL DEFAULT 0
```

**Problem**: New symbols get 0 instead of NULL.
**Impact**: Low — 0 is distinguishable from NULL in SQL (`IS NULL` vs `= 0`).
**Correction**: Change to `DEFAULT NULL`.

---

## Root Cause Analysis

### Why 47/50 are VALUE_MISMATCH

1. **Model retrained**: New model produces different probabilities
2. **Engine wired**: PHASE 10 added model loading, but DB wasn't updated
3. **Lazy endpoint caches**: Once a score is written, it's never recomputed
4. **Stats refresh may not run**: If refresh hasn't run since model change, DB has old scores

### Why 2 are STALE_DB_SCORE

- BEZ and MUD have DB scores but engine returns NULL
- These may have genuinely terminated events

### Why 1 is MATCH

- JHX: DB=24.21, Engine=24.65 (within 0.5 threshold)
- This symbol happens to have consistent scores

---

## Reproducible Test Case

```python
# Run this to reproduce the bug:
from dumbmoney.retest_engine import load_model, fold_symbol, make_score_fn
import pandas as pd, sqlite3

load_model()
conn = sqlite3.connect('screener.db')

# Get SONO bars
df = pd.read_sql("SELECT date, open, high, low, close, volume FROM bars WHERE timeframe='1Day' AND symbol='SONO' ORDER BY date", conn)
conn.close()

# Run engine
dates = df['date'].astype(str).tolist()
o, h, l, c, v = df['open'].values, df['high'].values, df['low'].values, df['close'].values, df['volume'].values
score_fn = make_score_fn(get_model())
result = fold_symbol(h, l, c, o, v, dates, "US", "SONO", score_fn=score_fn)

# Check latest score
latest = result.current_scores[-1]
print(f"Engine latest score: {latest}")  # Should be ~44.43

# Check DB
conn = sqlite3.connect('screener.db')
db_score = conn.execute("SELECT old_swing_retest_score FROM stats WHERE symbol='SONO'").fetchone()[0]
conn.close()
print(f"DB score: {db_score}")  # Will be 66.38

# Call lazy endpoint
# This will return 66.38 (cached), NOT 44.43
```

---

## Fix Priority

1. **IMMEDIATE**: Remove cache shortcut in lazy endpoint (app.py line 839)
2. **IMMEDIATE**: Convert NaN to None, not 0.0 (app.py line 853)
3. **SHORT-TERM**: Run full stats refresh to update all scores
4. **LONG-TERM**: Add score versioning to detect model changes

---

## Files to Change

| File | Line | Current | Proposed |
|------|------|---------|----------|
| dumbmoney/app.py | 839 | `if row and row[0] and row[0] > 0:` | Remove cache shortcut, always recompute |
| dumbmoney/app.py | 853 | `score_val = 0.0 if ... else ...` | `score_val = None if ... else round(...)` |
| dumbmoney/db.py | 312 | `DEFAULT 0` | `DEFAULT NULL` |
| dumbmoney/db.py | 316 | `DEFAULT 0` | `DEFAULT NULL` |
| dumbmoney/db.py | 320 | `DEFAULT 0` | `DEFAULT NULL` |
| dumbmoney/db.py | 324 | `DEFAULT 0` | `DEFAULT NULL` |
