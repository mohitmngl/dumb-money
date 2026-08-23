import sys, os, time, sqlite3
import numpy as np
import pandas as pd

sys.path.insert(0, r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt")
os.chdir(r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt")

from dumbmoney.retest_engine import compute_retest_score_for_symbol

db_path = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db"
conn = sqlite3.connect(db_path, timeout=60)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")
conn.execute("PRAGMA cache_size=-262144")

test_syms = ["SONO", "GLBE", "AAPL", "MSFT", "NVDA"]
t0 = time.time()
for sym in test_syms:
    bars = pd.read_sql(
        "SELECT date, open, high, low, close, volume FROM bars "
        "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
        conn, params=(sym,), parse_dates=["date"]
    )
    series = compute_retest_score_for_symbol(bars)
    dates = bars["date"].dt.strftime("%Y-%m-%d").values
    pairs = []
    for i in range(len(series)):
        val = series.iloc[i]
        score = 0.0 if val is None or (isinstance(val, float) and np.isnan(val)) else float(val)
        if score != 0.0:
            pairs.append((round(score, 2), sym, dates[i]))
    if pairs:
        conn.executemany(
            "UPDATE historical_screener SET old_swing_retest_score=? "
            "WHERE symbol=? AND date=?",
            pairs
        )
    conn.commit()
    print(f"{sym}: {len(pairs)} non-zero updates")

# Verify
rows = conn.execute(
    "SELECT symbol, date, old_swing_retest_score FROM historical_screener "
    "WHERE symbol IN ('SONO','GLBE','AAPL','MSFT','NVDA') AND old_swing_retest_score > 0 "
    "ORDER BY old_swing_retest_score DESC LIMIT 10"
).fetchall()
print("\nTop historical scores:")
for r in rows:
    print(f"  {r[0]} {r[1]}: {r[2]:.2f}")

conn.close()
print(f"\nDone in {time.time()-t0:.1f}s")
