import sqlite3, pandas as pd, numpy as np

conn = sqlite3.connect(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db')
df = pd.read_sql("SELECT date, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date", conn, params=('AAPL',))

close = df.close.astype(float).ffill().fillna(0).values
lookback = 252
n = min(lookback, len(close))

# Current (buggy): uses FIRST n bars
cum_ret_old = (close[:n] / close[0]) - 1.0
weights = np.linspace(0.5, 1.0, n)
weights = weights / weights.sum()
wa_old = float(np.dot(cum_ret_old, weights)) * 100

# Fixed: uses LAST n bars
close_recent = close[-n:]
cum_ret_new = (close_recent / close_recent[0]) - 1.0
wa_new = float(np.dot(cum_ret_new, weights)) * 100

print(f"AAPL close[-252]={close_recent[0]:.2f} ({df.date.iloc[-252]}), close[-1]={close_recent[-1]:.2f} ({df.date.iloc[-1]})")
print(f"  Annual return: {(close_recent[-1]/close_recent[0]-1)*100:.2f}%")
print(f"  WA OLD (first 252 bars): {wa_old:.4f}")
print(f"  WA NEW (last 252 bars):  {wa_new:.4f}")
print(f"  WA in DB: 0.1623")
print()

for sym in ['TSLA', 'NVDA', 'MSFT']:
    df2 = pd.read_sql("SELECT date, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date", conn, params=(sym,))
    if len(df2) < 10:
        print(f"{sym}: not enough data")
        continue
    c = df2.close.astype(float).ffill().fillna(0).values
    n2 = min(lookback, len(c))
    c2 = c[-n2:]
    cum = (c2 / c2[0]) - 1.0
    w = np.linspace(0.5, 1.0, n2)
    w = w / w.sum()
    wa_fix = float(np.dot(cum, w)) * 100
    
    # Old method
    cum_old = (c[:n2] / c[0]) - 1.0
    wa_ol = float(np.dot(cum_old, w)) * 100
    
    r = conn.execute("SELECT weighted_alpha FROM stats WHERE symbol=?", (sym,)).fetchone()
    db_wa = r[0] if r else None
    yr_ret = (c2[-1]/c2[0]-1)*100
    print(f"{sym}: annual_ret={yr_ret:.2f}%, WA_OLD={wa_ol:.4f}, WA_NEW={wa_fix:.4f}, DB={db_wa}")

# Also check why next_day_return equals change_pct
print("\n=== NEXT_DAY_RETURN VERIFICATION ===")
r = conn.execute("SELECT next_day_return, change_pct FROM stats WHERE symbol='AAPL'").fetchone()
print(f"AAPL: next_day_return={r[0]}, change_pct={r[1]}")
print("BUG: ndr.iloc[-2] gives same value as change_pct")

conn.close()
