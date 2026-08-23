import sys, os, time, json
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

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--tf', required=True, choices=['1Min', '5Min', '15Min', '1Day'])
    args = p.parse_args()

    limits = {'1Min': 5000, '5Min': 5000, '15Min': 5000, '1Day': 2500}
    tf = args.tf
    limit = limits[tf]

    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), f'backtest_{tf}.json')
    if os.path.exists(out_path):
        print(f"Already done: {out_path}")
        sys.exit(0)

    t1 = time.time()
    universe = data.get_universe(min_vol=500000)
    bars_dict = data.load_bars(universe, tf, limit=limit)
    print(f"Loaded {len(bars_dict)} stocks in {time.time()-t1:.1f}s", flush=True)

    print("Computing probability...", flush=True)
    prob = analyze_probability(bars_dict, tf)
    print_probability_report(prob)

    print(f"Running backtest...", flush=True)
    engine = BacktestEngine(bars_dict, max_trades=MAX_TRADES, invest_per_trade=CAPITAL_PER_TRADE)

    all_stats = []
    for strat in ['next_candle', 'stop_only', 'target_only', 'stop_and_target', 'rebalance_1x']:
        t0 = time.time()
        trades = engine.run_individual(strat, bars_dict)
        stats = compute_stats(trades, label=STRATEGY_LABELS[strat])
        all_stats.append(stats)
        print(f"  {STRATEGY_LABELS[strat]:<25}: {stats['trades']} trades, win={stats.get('win_rate',0):.1f}%, PF={stats.get('profit_factor',0):.2f} ({time.time()-t0:.1f}s)", flush=True)

    print_stats_table(all_stats, tf)

    result = {'timeframe': tf, 'prob': prob, 'stats': {s['label']: s for s in all_stats}, 'elapsed': time.time()-t1}
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"DONE in {time.time()-t1:.0f}s -> {out_path}", flush=True)
