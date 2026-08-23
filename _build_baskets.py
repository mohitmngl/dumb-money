import time, sys, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
sys.path.insert(0, r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt")
from dumbmoney.basket_screener import generate_string_universe, compute_current_metrics

for mkt in ["US", "INDIA"]:
    t0 = time.time()
    print(f"=== {mkt}: generating universe ===", flush=True)
    n = generate_string_universe(mkt, n=25000)
    print(f"=== {mkt}: generated {n} in {time.time()-t0:.1f}s ===", flush=True)
    t1 = time.time()
    print(f"=== {mkt}: computing current metrics ===", flush=True)
    c = compute_current_metrics(mkt)
    print(f"=== {mkt}: computed {c} metrics in {time.time()-t1:.1f}s ===", flush=True)
print("ALL DONE", flush=True)
