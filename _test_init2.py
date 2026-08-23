import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dumbmoney.db import _init_db
t0 = time.time()
_init_db("screener.db")
print(f"US init: {time.time()-t0:.1f}s")
t0 = time.time()
_init_db("india.db")
print(f"India init: {time.time()-t0:.1f}s")
