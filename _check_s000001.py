"""Check if S000001 still having 50.0 is correct."""
import sqlite3
conn = sqlite3.connect('screener.db', timeout=60)
conn.execute('PRAGMA busy_timeout=60000')

# S000001 constituents
cons = conn.execute("""
    SELECT sc.symbol, sc.weight 
    FROM string_constituents sc 
    JOIN string_universe su ON sc.string_id = su.string_id AND su.market = 'US'
    WHERE sc.string_id = 'S000001'
""").fetchall()
print(f"S000001 constituents ({len(cons)}):")
weighted_sum = 0
weight_total = 0
for sym, wt in cons:
    pst = conn.execute("SELECT prob_up_st_cross FROM historical_screener WHERE symbol = ? AND date = '2020-07-27'", (sym,)).fetchone()
    p = pst[0] if pst else None
    aw = abs(wt)
    if p is not None:
        weighted_sum += aw * p
    weight_total += aw
    print(f"  {sym} wt={wt:.4f} pst={p}")
if weight_total > 0:
    print(f"  Weighted avg = {weighted_sum/weight_total:.4f}")
else:
    print(f"  No weights!")

# Check S000949 constituents for comparison
cons2 = conn.execute("""
    SELECT sc.symbol, sc.weight 
    FROM string_constituents sc 
    JOIN string_universe su ON sc.string_id = su.string_id AND su.market = 'US'
    WHERE sc.string_id = 'S000949'
""").fetchall()
print(f"\nS000949 constituents ({len(cons2)}):")
weighted_sum2 = 0
weight_total2 = 0
for sym, wt in cons2:
    pst = conn.execute("SELECT prob_up_st_cross FROM historical_screener WHERE symbol = ? AND date = '2020-07-27'", (sym,)).fetchone()
    p = pst[0] if pst else None
    aw = abs(wt)
    if p is not None:
        weighted_sum2 += aw * p
    weight_total2 += aw
    if p is not None:
        print(f"  {sym} wt={wt:.4f} pst={p}")
if weight_total2 > 0:
    print(f"  Weighted avg = {weighted_sum2/weight_total2:.4f}")

conn.close()
