import sys, time
sys.path.insert(0, '.')
from dumbmoney.basket_screener import update_historical_string_screener

def prog(pct, detail):
    print(f"  [{time.time()-t0:.0f}s] {pct}% {detail}")

t0 = time.time()
print("Rebuilding US historical with basket-level SuperTrend/Accel...")
rows = update_historical_string_screener("US", force_rebuild=True, progress_callback=prog)
print(f"\nDone in {time.time()-t0:.1f}s, rows={rows}")

import sqlite3
c = sqlite3.connect('screener.db')
r = c.execute("SELECT COUNT(*), COUNT(DISTINCT date), MIN(date), MAX(date) FROM historical_string_screener").fetchone()
print(f"Final: {r[0]:,} rows, {r[1]} dates, {r[2]} to {r[3]}")

# Verify S013969 on 2026-07-01
r = c.execute("SELECT atr_signal, atr_crossed_above, atr_stop, price FROM historical_string_screener WHERE string_id='S013969' AND date='2026-07-01'").fetchone()
if r:
    print(f"\nS013969 on 2026-07-01: atr_signal={r[0]}, crossed_above={r[1]}, atr_stop={r[2]:.2f}, price={r[3]:.2f}")
else:
    print("\nS013969 not found on 2026-07-01")

# Check a few dates around it
rows = c.execute("SELECT date, atr_signal, atr_crossed_above, atr_stop, price FROM historical_string_screener WHERE string_id='S013969' AND date BETWEEN '2026-06-25' AND '2026-07-05' ORDER BY date").fetchall()
print("\nS013969 around 2026-07-01:")
for r in rows:
    print(f"  {r[0]}: ST={r[1]}, cross_up={r[2]}, stop={r[3]:.2f}, price={r[4]:.2f}")

c.close()
