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

def main():
    print("TEST: Loading 10 stocks x 1Min...")
    t0 = time.time()

    universe = data.get_universe(min_vol=500000)
    symbols = universe[:10]
    print(f"  Symbols: {symbols}")

    bars_dict = data.load_bars(symbols, '1Min', limit=2000)
    print(f"  Loaded {len(bars_dict)} stocks in {time.time()-t0:.1f}s")
    for sym, bars in bars_dict.items():
        print(f"    {sym}: {len(bars)} bars")

    if not bars_dict:
        print("No data!")
        return

    t1 = time.time()
    print(f"\n--- PROBABILITY ---")
    prob = analyze_probability(bars_dict, '1Min')
    print_probability_report(prob)
    print(f"  Probability done in {time.time()-t1:.1f}s")

    engine = BacktestEngine(bars_dict, max_trades=MAX_TRADES, invest_per_trade=CAPITAL_PER_TRADE)

    t2 = time.time()
    print(f"\n--- BACKTEST ---")
    for strat in ['stop_only', 'target_only', 'stop_and_target', 'rebalance_1x', 'next_candle']:
        trades = engine.run_individual(strat, bars_dict)
        stats = compute_stats(trades, label=STRATEGY_LABELS[strat])
        print(f"  {STRATEGY_LABELS[strat]:<25}: {stats['trades']} trades, win={stats.get('win_rate',0):.1f}%, PF={stats.get('profit_factor',0):.2f}")
    print(f"  Backtest done in {time.time()-t2:.1f}s")
    print(f"  Total: {time.time()-t0:.1f}s")

if __name__ == '__main__':
    main()
