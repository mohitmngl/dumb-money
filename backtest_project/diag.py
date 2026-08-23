import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from backtest_project import data

t1 = time.time()
universe = data.get_universe(min_vol=500000)[:50]
bars_dict = data.load_bars(universe, '1Min', limit=5000)
print("Loaded %d stocks in %.1fs" % (len(bars_dict), time.time()-t1), flush=True)

from backtest_project.probability import analyze_probability
t2 = time.time()
prob = analyze_probability(bars_dict, '1Min')
print("Probability done in %.1fs" % (time.time()-t2), flush=True)

from backtest_project.backtest import BacktestEngine
from backtest_project.stats import compute_stats
engine = BacktestEngine(bars_dict, max_trades=500, invest_per_trade=100)

for strat in ['next_candle', 'stop_only', 'target_only', 'stop_and_target', 'rebalance_1x']:
    t3 = time.time()
    trades = engine.run_individual(strat, bars_dict)
    stats = compute_stats(trades, label=strat)
    print("  %s: %d trades, PF=%.2f, sharpe=%.2f (%.1fs)" % (strat, stats['trades'], stats.get('profit_factor', 0), stats.get('sharpe', 0), time.time()-t3), flush=True)

print("TOTAL: %.1fs" % (time.time()-t1), flush=True)
