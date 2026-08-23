import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from backtest_project import data

t1 = time.time()
universe = data.get_universe(min_vol=500000)
print("Universe: %d stocks" % len(universe), flush=True)

for tf, limit in [('1Min', 5000), ('5Min', 10000), ('15Min', 5000)]:
    t2 = time.time()
    bars_dict = data.load_bars(universe, tf, limit=limit)
    total_bars = sum(len(b) for b in bars_dict.values())
    print("%s: loaded %d stocks, %d total bars in %.1fs" % (tf, len(bars_dict), total_bars, time.time()-t2), flush=True)
print("TOTAL: %.1fs" % (time.time()-t1), flush=True)
