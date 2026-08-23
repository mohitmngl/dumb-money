import sys, os, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_project import data
from backtest_project.indicators import compute_supertrend, find_st_crosses
from backtest_project.probability import analyze_probability, print_probability_report
from backtest_project.backtest import BacktestEngine
from backtest_project.stats import compute_stats, print_stats_table

CAPITAL_PER_TRADE = 100
MAX_TRADES = 500

STRATEGY_LABELS = {
    'next_candle': 'Next Candle Exit',
    'stop_only': '1x ST Loss Only',
    'target_only': '2x Profit Only',
    'stop_and_target': '1x ST + 2x Profit',
    'rebalance_1x': 'Rebalance 1x SL/TP',
}

TIMEFRAME_LIMITS = {'1Min': 5000, '5Min': 10000, '15Min': 5000}

def run_for_timeframe(tf_name, symbols):
    limit = TIMEFRAME_LIMITS.get(tf_name, 5000)
    print(f"\n{'#'*80}")
    print(f"  TIMEFRAME: {tf_name} ({len(symbols)} stocks, max {limit} bars each)")
    print(f"{'#'*80}")

    t1 = time.time()
    bars_dict = data.load_bars(symbols, tf_name, limit=limit)
    load_time = time.time() - t1
    print(f"  Loaded {len(bars_dict)} stocks in {load_time:.1f}s")

    if len(bars_dict) < 5:
        print(f"  Not enough data for {tf_name}, skipping")
        return None

    sample_sym = list(bars_dict.keys())[0]
    print(f"  Sample ({sample_sym}): {len(bars_dict[sample_sym])} bars")

    print(f"\n--- PROBABILITY ANALYSIS ---")
    prob_result = analyze_probability(bars_dict, tf_name)
    print_probability_report(prob_result)

    engine = BacktestEngine(bars_dict, max_trades=MAX_TRADES, invest_per_trade=CAPITAL_PER_TRADE)

    print(f"\n--- INDIVIDUAL STOCK BACKTEST ---")
    results = {}
    for strat in ['next_candle', 'stop_only', 'target_only', 'stop_and_target', 'rebalance_1x']:
        t_start = time.time()
        trades = engine.run_individual(strat, bars_dict)
        stats = compute_stats(trades, label=STRATEGY_LABELS[strat])
        elapsed = time.time() - t_start
        results[strat] = {'trades': trades, 'stats': stats}
        print(f"  {STRATEGY_LABELS[strat]:<25}: {stats['trades']} trades, win={stats.get('win_rate',0):.1f}%, PF={stats.get('profit_factor',0):.2f} ({elapsed:.1f}s)")

    all_results = [r['stats'] for r in results.values()]
    print_stats_table(all_results, tf_name)

    elapsed = time.time() - t1
    print(f"\n  {tf_name} completed in {elapsed:.0f}s")

    return {
        'timeframe': tf_name,
        'prob': prob_result,
        'results': results,
        'all_stats': all_results,
        'stock_count': len(bars_dict)
    }

def print_final_summary(all_tf_results):
    print(f"\n{'='*100}")
    print(f"  FINAL SUMMARY: ALL TIMEFRAMES")
    print(f"{'='*100}")

    for tf_name, res in all_tf_results.items():
        if res is None:
            continue
        prob = res['prob']
        if prob:
            print(f"\n  {tf_name}:")
            print(f"    Signals: {prob['total_signals']} across {prob['unique_stocks']} stocks")
            print(f"    P(up 1 candle): {prob['prob_up_1']:.1f}%")
            print(f"    P(up 5 candles): {prob['prob_up_5']:.1f}%")
            print(f"    Avg 1st candle return: {prob['avg_first_candle_return']:+.4f}%")

    print(f"\n  {'STRATEGY':<25}", end='')
    for tf_name in all_tf_results:
        if all_tf_results[tf_name]:
            print(f" | {tf_name:>15}", end='')
    print()
    print('  ' + '-' * 90)

    for strat_key, strat_label in STRATEGY_LABELS.items():
        print(f"  {strat_label:<25}", end='')
        for tf_name, res in all_tf_results.items():
            if res is None or strat_key not in res['results']:
                print(f" | {'N/A':>15}", end='')
                continue
            stats = res['results'][strat_key]['stats']
            if stats['trades'] > 0:
                print(f" | {stats['win_rate']:>5.1f}% PF{stats['profit_factor']:>5.2f}", end='')
            else:
                print(f" | {'NO DATA':>15}", end='')
        print()

    print(f"\n  CAPITAL ANALYSIS ($100 per trade):")
    print(f"  {'STRATEGY':<25}", end='')
    for tf_name in all_tf_results:
        if all_tf_results[tf_name]:
            print(f" | {tf_name:>15}", end='')
    print()
    print('  ' + '-' * 90)

    for strat_key, strat_label in STRATEGY_LABELS.items():
        print(f"  {strat_label:<25}", end='')
        for tf_name, res in all_tf_results.items():
            if res is None or strat_key not in res['results']:
                print(f" | {'N/A':>15}", end='')
                continue
            stats = res['results'][strat_key]['stats']
            trades = res['results'][strat_key]['trades']
            if stats['trades'] > 0:
                total_invested = stats['trades'] * CAPITAL_PER_TRADE
                total_pnl = stats['total_pnl']
                total_return_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
                print(f" | ${total_pnl:>+8.2f} ({total_return_pct:>+.1f}%)", end='')
            else:
                print(f" | {'$0':>15}", end='')
        print()

    print(f"{'='*100}")

def main():
    print("=" * 80)
    print("  SUPER TREND BACKTEST (intraday_backtest.db)")
    print("  SuperTrend(14,3) | No overnight holding")
    print(f"  Capital per trade: ${CAPITAL_PER_TRADE}")
    print("=" * 80)

    t_total = time.time()

    print("\n--- UNIVERSE ---")
    universe = data.get_universe(min_vol=500000)
    print(f"  Universe: {len(universe)} stocks")

    print("\n--- DATA INFO ---")
    for tf in ['1Min', '5Min', '15Min']:
        bars, stocks = data.get_bar_count(tf)
        dr = data.get_date_range(tf)
        print(f"  {tf}: {bars:,} bars, {stocks} stocks, {dr[0]} to {dr[1]}")

    all_tf_results = {}
    for tf_name in ['1Min', '5Min', '15Min']:
        result = run_for_timeframe(tf_name, universe)
        all_tf_results[tf_name] = result

    print_final_summary(all_tf_results)

    elapsed = time.time() - t_total
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f} min)")

if __name__ == '__main__':
    main()
