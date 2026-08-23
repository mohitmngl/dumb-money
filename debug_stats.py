import sys, time, io, contextlib
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
t0 = time.time()

# First, check what vectorized_stats_pass does
from dumbmoney.engine import vectorized_stats_pass
import inspect
src = inspect.getsource(vectorized_stats_pass)
# Look for the skip/early-return logic
for i, line in enumerate(src.split('\n')[:50]):
    print(f'{i}: {line}')
