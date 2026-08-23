import numpy as np

def compute_atr(highs, lows, closes, period=14):
    n = len(closes)
    if n < 2:
        return np.full(n, np.nan)
    highs = np.array(highs, dtype=np.float64)
    lows = np.array(lows, dtype=np.float64)
    closes = np.array(closes, dtype=np.float64)
    prev_c = np.concatenate([[closes[0]], closes[:-1]])
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_c), np.abs(lows - prev_c)))
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = tr[:period].mean()
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr

def compute_supertrend(highs, lows, closes, period=14, multiplier=3.0):
    n = len(closes)
    if n < period:
        return None, None, None
    highs = np.array(highs, dtype=np.float64)
    lows = np.array(lows, dtype=np.float64)
    closes = np.array(closes, dtype=np.float64)
    atr = compute_atr(highs, lows, closes, period)
    upper_band = np.full(n, np.nan)
    lower_band = np.full(n, np.nan)
    supertrend = np.full(n, np.nan)
    direction = np.zeros(n, dtype=np.int32)
    hl2 = (highs + lows) / 2.0

    for i in range(period - 1, n):
        if np.isnan(atr[i]):
            continue
        basic_upper = hl2[i] + multiplier * atr[i]
        basic_lower = hl2[i] - multiplier * atr[i]
        if i == period - 1:
            upper_band[i] = basic_upper
            lower_band[i] = basic_lower
        else:
            upper_band[i] = basic_upper if basic_upper < upper_band[i-1] or closes[i-1] > upper_band[i-1] else upper_band[i-1]
            lower_band[i] = basic_lower if basic_lower > lower_band[i-1] or closes[i-1] < lower_band[i-1] else lower_band[i-1]
        if i == period - 1:
            direction[i] = 1
            supertrend[i] = lower_band[i]
        else:
            prev_dir = direction[i-1]
            if prev_dir == 1:
                direction[i] = -1 if closes[i] < lower_band[i-1] else 1
            else:
                direction[i] = 1 if closes[i] > upper_band[i-1] else -1
            supertrend[i] = lower_band[i] if direction[i] == 1 else upper_band[i]

    return supertrend, direction, atr

def find_st_crosses(closes, supertrend, direction):
    crosses = []
    n = len(closes)
    for i in range(1, n):
        if np.isnan(supertrend[i]) or np.isnan(supertrend[i-1]):
            continue
        if direction[i] == 1 and direction[i-1] == -1:
            crosses.append({
                'index': i,
                'type': 'cross_up',
                'price': closes[i],
                'st_value': supertrend[i]
            })
        elif direction[i] == -1 and direction[i-1] == 1:
            crosses.append({
                'index': i,
                'type': 'cross_down',
                'price': closes[i],
                'st_value': supertrend[i]
            })
    return crosses

def measure_continuation(closes, cross_index, max_lookahead=20):
    entry_price = closes[cross_index]
    results = {'up_1': 0, 'up_2': 0, 'up_3': 0, 'up_5': 0, 'up_10': 0}
    n = len(closes)

    max_candles_up = 0
    for j in range(cross_index + 1, min(cross_index + 1 + max_lookahead, n)):
        if closes[j] > entry_price:
            max_candles_up += 1
        else:
            break

    for key, threshold in [('up_1', 1), ('up_2', 2), ('up_3', 3), ('up_5', 5), ('up_10', 10)]:
        if max_candles_up >= threshold:
            results[key] = 1

    results['max_candles_up'] = max_candles_up

    returns = []
    for j in range(cross_index + 1, min(cross_index + 1 + max_lookahead, n)):
        ret = (closes[j] - entry_price) / entry_price * 100
        returns.append(ret)
    results['returns'] = returns

    return results
