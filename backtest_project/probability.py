import numpy as np
from .indicators import compute_supertrend, find_st_crosses, measure_continuation

def analyze_probability(all_bars, timeframe):
    total_signals = 0
    continuation = {k: 0 for k in ['up_1', 'up_2', 'up_3', 'up_5', 'up_10']}
    all_returns = []
    max_candles_dist = {}
    per_stock_signals = {}

    for sym, bars in all_bars.items():
        closes = [b['c'] for b in bars]
        highs = [b['h'] for b in bars]
        lows = [b['l'] for b in bars]

        if len(closes) < 20:
            continue

        supertrend, direction, atr = compute_supertrend(highs, lows, closes, period=14, multiplier=3.0)
        if supertrend is None:
            continue

        crosses = find_st_crosses(closes, supertrend, direction)
        cross_ups = [c for c in crosses if c['type'] == 'cross_up']

        if not cross_ups:
            continue

        per_stock_signals[sym] = len(cross_ups)

        for cross in cross_ups:
            idx = cross['index']
            if idx >= len(closes) - 1:
                continue

            cont = measure_continuation(closes, idx, max_lookahead=20)
            total_signals += 1

            for key in ['up_1', 'up_2', 'up_3', 'up_5', 'up_10']:
                if cont[key]:
                    continuation[key] += 1

            if cont['returns']:
                all_returns.append(cont['returns'][0] if cont['returns'] else 0)

            mcu = cont['max_candles_up']
            max_candles_dist[mcu] = max_candles_dist.get(mcu, 0) + 1

    if total_signals == 0:
        return None

    probs = {}
    for key in ['up_1', 'up_2', 'up_3', 'up_5', 'up_10']:
        probs[key] = continuation[key] / total_signals * 100

    avg_first_return = np.mean(all_returns) if all_returns else 0
    median_first_return = np.median(all_returns) if all_returns else 0

    return {
        'timeframe': timeframe,
        'total_signals': total_signals,
        'unique_stocks': len(per_stock_signals),
        'avg_signals_per_stock': total_signals / max(len(per_stock_signals), 1),
        'prob_up_1': probs['up_1'],
        'prob_up_2': probs['up_2'],
        'prob_up_3': probs['up_3'],
        'prob_up_5': probs['up_5'],
        'prob_up_10': probs['up_10'],
        'avg_first_candle_return': avg_first_return,
        'median_first_candle_return': median_first_return,
        'max_candles_distribution': dict(sorted(max_candles_dist.items())),
        'per_stock_signals': per_stock_signals
    }

def print_probability_report(result):
    if result is None:
        print("  No signals found!")
        return

    print(f"\n{'='*70}")
    print(f"  PROBABILITY ANALYSIS: {result['timeframe']} candles")
    print(f"{'='*70}")
    print(f"  Total ST cross-up signals: {result['total_signals']}")
    print(f"  Unique stocks with signals: {result['unique_stocks']}")
    print(f"  Avg signals per stock: {result['avg_signals_per_stock']:.1f}")
    print(f"\n  PROBABILITY OF CONTINUATION AFTER ST CROSS-UP:")
    print(f"  {'Lookahead':<15} {'Probability':<15} {'Bar'}")
    print(f"  {'-'*45}")
    for key, label in [('up_1', '1 candle'), ('up_2', '2 candles'), ('up_3', '3 candles'), ('up_5', '5 candles'), ('up_10', '10 candles')]:
        prob = result[f'prob_{key}']
        bar = '#' * int(prob / 2)
        print(f"  {label:<15} {prob:>6.1f}%        {bar}")

    print(f"\n  First candle return:")
    print(f"    Avg:   {result['avg_first_candle_return']:+.3f}%")
    print(f"    Median: {result['median_first_candle_return']:+.3f}%")

    print(f"\n  Max consecutive candles up distribution:")
    dist = result['max_candles_distribution']
    for k in sorted(dist.keys()):
        count = dist[k]
        pct = count / result['total_signals'] * 100
        bar = '#' * int(pct / 2)
        print(f"    {k:>2} candles: {count:>5} ({pct:>5.1f}%) {bar}")
    print(f"{'='*70}")
