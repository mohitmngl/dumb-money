"""Check historical_screener size for US and India."""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for name, db in [("US", "screener.db"), ("India", "india.db")]:
    c = sqlite3.connect(db, timeout=30)
    n = c.execute("SELECT COUNT(*) FROM historical_screener").fetchone()[0]
    u = c.execute("SELECT COUNT(DISTINCT symbol) FROM historical_screener").fetchone()[0]
    d = c.execute("SELECT COUNT(DISTINCT date) FROM historical_screener").fetchone()[0]
    print(f"{name} historical_screener: rows={n:,}, symbols={u:,}, dates={d}")
    
    # Check prob_up_st_cross range
    stat = c.execute("SELECT MIN(prob_up_st_cross), MAX(prob_up_st_cross), AVG(prob_up_st_cross) FROM historical_screener WHERE prob_up_st_cross IS NOT NULL").fetchone()
    if stat and stat[0] is not None:
        print(f"  prob_up_st_cross: min={stat[0]:.1f}, max={stat[1]:.1f}, avg={stat[2]:.1f}")
    else:
        print(f"  prob_up_st_cross: NULL (not populated yet)")
    c.close()
