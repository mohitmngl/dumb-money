"""Quick verify - check specific strings on old dates."""
import sqlite3

for market, db_file in [("US", "screener.db"), ("INDIA", "india.db")]:
    conn = sqlite3.connect(db_file, timeout=60)
    conn.execute('PRAGMA busy_timeout=60000')
    
    # Pick a specific string and check old vs recent
    sids = conn.execute("SELECT string_id FROM historical_string_screener WHERE prob_up_st_cross != 50.0 AND prob_up_st_cross IS NOT NULL LIMIT 1").fetchall()
    if sids:
        sid = sids[0][0]
        old_val = conn.execute(f"SELECT prob_up_st_cross FROM historical_string_screener WHERE string_id = ? AND date = '2021-01-04'", (sid,)).fetchone()
        recent_val = conn.execute(f"SELECT prob_up_st_cross FROM historical_string_screener WHERE string_id = ? AND date = '2026-07-21'", (sid,)).fetchone()
        print(f"{market} string {sid}:")
        print(f"  2021-01-04 pst={old_val}")
        print(f"  2026-07-21 pst={recent_val}")
    else:
        print(f"{market}: no non-default rows found")
    
    # Check old date - do we still see 50.0?
    check50 = conn.execute("SELECT string_id, prob_up_st_cross FROM historical_string_screener WHERE date = '2020-07-27' AND prob_up_st_cross = 50.0 LIMIT 3").fetchall()
    check_real = conn.execute("SELECT string_id, prob_up_st_cross FROM historical_string_screener WHERE date = '2020-07-27' AND prob_up_st_cross != 50.0 LIMIT 3").fetchall()
    print(f"  2020-07-27: still-50.0={check50}, non-default={check_real}")
    
    conn.close()
