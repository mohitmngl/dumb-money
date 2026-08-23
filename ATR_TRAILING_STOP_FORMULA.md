# ATR Trailing Stop — Exact Implementation Documentation

## Parameters
- **Period**: 14 (Wilder RMA length)
- **Multiplier**: 1.0

---

## Step 1: True Range (TR)

```
TR[0] = High[0] - Low[0]
TR[i] = max(High[i] - Low[i], |High[i] - Close[i-1]|, |Low[i] - Close[i-1]|)   for i >= 1
```

---

## Step 2: ATR (Wilder's RMA)

```
ATR[P-1] = mean(TR[0 : P])           // Simple average of first P True Ranges
ATR[i]   = (ATR[i-1] * (P-1) + TR[i]) / P    for i >= P
```

This is an exponential moving average with alpha = 1/P.

---

## Step 3: Trailing Stop Calculation

For each bar `i` where `ATR[i]` is valid (i.e., `i >= P-1`):

```
Loss[i] = Multiplier * ATR[i]
prev_stop = Stop[i-1]       (NaN for first valid bar)
prev_close = Close[i-1]     (Close[i] for first bar)
```

### Decision logic (evaluated in order):

| # | Condition | Stop | Trend |
|---|-----------|------|-------|
| 1 | `prev_stop is NaN` (first valid bar) | `Close[i] + Loss[i]` | -1 (downtrend) |
| 2 | `Close[i] > prev_stop AND prev_close > prev_stop` | `max(prev_stop, Close[i] - Loss[i])` | +1 (uptrend) |
| 3 | `Close[i] < prev_stop AND prev_close < prev_stop` | `min(prev_stop, Close[i] + Loss[i])` | -1 (downtrend) |
| 4 | `Close[i] > prev_stop AND prev_close <= prev_stop` (cross UP) | `Close[i] - Loss[i]` | +1 (uptrend) |
| 5 | `Close[i] < prev_stop AND prev_close >= prev_stop` (cross DOWN) | `Close[i] + Loss[i]` | -1 (downtrend) |
| 6 | else | `prev_stop` (unchanged) | previous trend |

### Key behaviors:
- **Uptrend (trend=+1)**: Stop is BELOW price. Stop only ratchets UP (never down) via `max()`.
- **Downtrend (trend=-1)**: Stop is ABOVE price. Stop only ratchets DOWN (never up) via `min()`.
- **Cross up**: Price was below stop, now above → new bullish stop placed at `Close - Loss`.
- **Cross down**: Price was above stop, now below → new bearish stop placed at `Close + Loss`.

---

## Step 4: Signal / Crossover Detection

```
Crossed Above[i] = 1  if  trend[i] == +1  AND  trend[i-1] == -1   (bearish → bullish)
Crossed Below[i] = 1  if  trend[i] == -1  AND  trend[i-1] == +1   (bullish → bearish)
```

---

## Step 5: Streak

```
Streak[0] = +1 if trend=+1, -1 if trend=-1, 0 if trend=0
Streak[i] = Streak[i-1] + sign(trend[i])    if trend[i] == trend[i-1]
          = sign(trend[i])                   if trend[i] != trend[i-1]
          = 0                                if trend[i] == 0
```

---

## Step 6: Bars at Side (BAS)

Count of consecutive bars the trend was at the **opposite** side before the current state began.

- When trend=+1 (uptrend): BAS = number of preceding consecutive bars with trend=-1
- When trend=-1 (downtrend): BAS = number of preceding consecutive bars with trend=+1

---

## Rolling Weekly (5-day) ATR Trailing Stop

1. **Resample** daily bars into 5-day rolling candles:
   ```
   Open  = first close in window (NOT the open of first bar)
   High  = max(high) over 5 days
   Low   = min(low) over 5 days
   Close = last close in window
   ```

2. **Compute ATR Trailing Stop** on these 5-day candles using the same parameters (period=14, multiplier=1.0).

3. **Map back**: Each 5-day candle's result is assigned to the LAST daily bar in that window.

> **Note**: The rolling window is OVERLAPPING (sliding window), NOT non-overlapping calendar weeks. Each bar belongs to multiple 5-day windows.

---

## Rolling Monthly (22-day) ATR Trailing Stop

Same as weekly, but with window=22:
```
Open  = first close in 22-day window
High  = max(high) over 22 days
Low   = min(low) over 22 days
Close = last close in 22-day window
```

Then ATR Trailing Stop is computed on these 22-day candles.

---

## Output Columns

| Column | Meaning |
|--------|---------|
| `atr_signal` | Trend direction: +1 (bullish), -1 (bearish), 0 (neutral) |
| `atr_stop` | Trailing stop price level |
| `atr_value` | ATR(14) value |
| `atr_crossed_above` | 1 if trend flipped from -1 to +1 on this bar |
| `atr_crossed_below` | 1 if trend flipped from +1 to -1 on this bar |
| `atr_streak` | Consecutive bars in current trend direction (signed) |
| `atr_multiplier` | Multiplier used (always 1.0) |
| `_w` suffix | Same columns for weekly rolling ATR |
| `_m` suffix | Same columns for monthly rolling ATR |
| `st_bars_below` | Bars at side when in uptrend |
| `st_bars_above` | Bars at side when in downtrend |

---

## Differences from Standard SuperTrend

| Aspect | This Implementation (ATR Trailing Stop) | Standard SuperTrend |
|--------|----------------------------------------|---------------------|
| Bands | No bands — direct recursive stop | Uses HL2 ± M*ATR upper/lower bands |
| Stop update | `max/min(prev_stop, close ± loss)` — ratchets in trend direction | Band ratcheting logic with `prevSuperTrend == prevUpperBand` test |
| Initial bar | `stop = close + loss` (bearish default) | `-1` (bearish) with NaN stop |
| Cross detection | `close > prev_stop` with `prev_close <= prev_stop` | `close > final_upper` or `close < final_lower` |
| Source | Direct close-based | HL2-based (midpoint of high+low) |

---

## Source Code References
- `indicators.py:132-163` — `atr_trailing_stop()` wrapper
- `indicators.py:166-255` — `_atr_trailing_stop_numba()` core logic
- `engine.py:332-387` — Daily, weekly, monthly computation in `_compute_one()`
- `engine.py:829-914` — Historical symbol frame computation
