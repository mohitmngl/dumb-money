import sqlite3
conn = sqlite3.connect('screener.db', timeout=30)
conn.execute('PRAGMA busy_timeout=30000')
# Check next_day_return distribution
samples = conn.execute("SELECT symbol, date, next_day_return, prob_up_st_cross FROM historical_screener WHERE atr_crossed_above = 1 AND next_day_return IS NOT NULL ORDER BY RANDOM() LIMIT 20").fetchall()
print("Random samples (atr_crossed_above=1):")
for s in samples:
    print(f"  {s[0]} {s[1]} ndr={s[2]} pst={s[3]}")

# Check percentiles
import numpy as np
ndrs = conn.execute("SELECT next_day_return FROM historical_screener WHERE atr_crossed_above = 1 AND next_day_return IS NOT NULL LIMIT 100000").fetchall()
ndrs = [n[0] for n in ndrs]
arr = np.array(ndrs)
print(f"\nStats: mean={arr.mean():.4f}, median={np.median(arr):.4f}, p5={np.percentile(arr,5):.4f}, p95={np.percentile(arr,95):.4f}, min={arr.min():.4f}, max={arr.max():.4f}")
print(f"Values > 10%: {(arr > 0.1).sum()}, > 50%: {(arr > 0.5).sum()}, > 100%: {(arr > 1.0).sum()}")
print(f"Values < -10%: {(arr < -0.1).sum()}, < -50%: {(arr < -0.5).sum()}")
conn.close()
