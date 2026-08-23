"""Verify prob_up_st_cross columns exist."""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for name, db in [("US", "screener.db"), ("India", "india.db")]:
    c = sqlite3.connect(db, timeout=5)
    cols = [r[1] for r in c.execute("PRAGMA table_info(historical_screener)").fetchall()]
    print(f"{name} historical_screener: prob_up_st_cross = {'prob_up_st_cross' in cols}")
    cols = [r[1] for r in c.execute("PRAGMA table_info(historical_string_screener)").fetchall()]
    print(f"{name} historical_string_screener: prob_up_st_cross = {'prob_up_st_cross' in cols}")
    cols = [r[1] for r in c.execute("PRAGMA table_info(stats)").fetchall()]
    print(f"{name} stats: prob_up_st_cross = {'prob_up_st_cross' in cols}")
    c.close()
