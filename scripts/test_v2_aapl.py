"""Quick smoke test: run V2 engine on AAPL real bars."""
from dumbmoney.retest_engine_v2 import RetestEngineV2 as V2Engine
import numpy as np
import sqlite3

conn = sqlite3.connect("screener.db")
cur = conn.cursor()
cur.execute("SELECT date, open, high, low, close, volume FROM bars WHERE symbol = ? ORDER BY date", ("AAPL",))
rows = cur.fetchall()
conn.close()

if not rows:
    print("No bars for AAPL")
else:
    dates = [r[0] for r in rows]
    open_ = np.array([r[1] for r in rows], dtype=np.float64)
    high = np.array([r[2] for r in rows], dtype=np.float64)
    low = np.array([r[3] for r in rows], dtype=np.float64)
    close = np.array([r[4] for r in rows], dtype=np.float64)
    volume = np.array([r[5] for r in rows], dtype=np.float64)

    engine = V2Engine("US", "AAPL")
    result = engine.fold(dates, open_, high, low, close, volume)

    print(f"Symbol: AAPL")
    print(f"Bars: {len(dates)}")
    print(f"States used: {set(result.states)}")
    print(f"Events: {len(result.events)}")
    print(f"Current scores non-null: {np.count_nonzero(~np.isnan(result.current_scores))}")
    print(f"Model version: {result.model_version}")
    for e in result.events[:5]:
        eid = e.event_id
        state = e.state
        print(f"  Event {eid}: {state}")
