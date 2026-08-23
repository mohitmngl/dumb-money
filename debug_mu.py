import sys, traceback
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
import pandas as pd
from dumbmoney.db import get_db
from dumbmoney.engine import weighted_alpha, supertrend, accel, atrp, prob_up, prob_up_after_st_cross_up, next_day_return, streak_vectorized, ai_score_latest, compute_confluence
from dumbmoney.indicators import prob_up_after_st_cross_up

conn = get_db('US')
df = pd.read_sql("SELECT symbol, date, open, high, low, close, volume FROM bars WHERE symbol='MU' AND timeframe='1Day' ORDER BY date", conn, parse_dates=["date"])
conn.close()

print(f"MU bars loaded: {len(df)} rows")
grp = df.sort_values("date").reset_index(drop=True)

try:
    c = grp["close"].astype(float)
    h = grp["high"].astype(float)
    l = grp["low"].astype(float)
    v = grp["volume"].astype(float)
    
    last_close = c.iloc[-1]
    print(f"Last close: {last_close}")
    
    wa = weighted_alpha(grp)
    print(f"Weighted alpha: {wa.iloc[-1]}")
    
    st_result = supertrend(grp, period=14, multiplier=1.0)
    print(f"SuperTrend OK: {len(st_result)} rows")
    
    ac = accel(grp)
    print(f"Accel OK: {len(ac)} rows")
    
    atrp_val = atrp(h, l, c)
    print(f"ATRP OK: {atrp_val.iloc[-1]}")
    
    p1d = prob_up(c, 1)
    print(f"Prob up 1d: {p1d.iloc[-1]}")
    
    ndr = next_day_return(c)
    print(f"Next day return: {ndr.iloc[-1]}")
    
    streak_val = streak_vectorized(c)
    print(f"Streak: {streak_val.iloc[-1]}")
    
    ai = ai_score_latest(grp)
    print(f"AI: {ai['overall_score']}")
    
    print("\nALL INDICATORS OK - MU should have been computed!")
except Exception as e:
    print(f"\nERROR: {e}")
    traceback.print_exc()
