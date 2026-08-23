import sqlite3
conn = sqlite3.connect('screener.db', timeout=60)
conn.execute('PRAGMA busy_timeout=60000')

# Schema
cur = conn.execute("PRAGMA table_info(historical_string_screener)")
cols = [r[1] for r in cur.fetchall()]
print("HSS columns:", cols)

# Sample HSS rows with real pst
sample = conn.execute("SELECT * FROM historical_string_screener WHERE prob_up_st_cross != 50.0 LIMIT 3").fetchall()
print("HSS non-default sample:", sample)

# Sample HSS rows with 50.0 pst
sample50 = conn.execute("SELECT * FROM historical_string_screener WHERE prob_up_st_cross = 50.0 LIMIT 3").fetchall()
print("HSS 50.0 sample:", sample50)

# HS non-default sample with all columns
cur2 = conn.execute("PRAGMA table_info(historical_screener)")
hs_cols = [r[1] for r in cur2.fetchall()]
print("HS columns:", hs_cols)

hs_sample = conn.execute("SELECT symbol, date, prob_up_st_cross FROM historical_screener WHERE prob_up_st_cross != 50.0 AND date = '2026-07-21' LIMIT 3").fetchall()
print("HS recent non-default:", hs_sample)

# Check: are there strings where the constituent symbols DON'T appear in historical_screener?
missing = conn.execute("""
    SELECT sc.symbol, COUNT(*)
    FROM string_constituents sc
    JOIN string_universe su ON sc.string_id = su.string_id AND su.market = 'US'
    WHERE sc.symbol NOT IN (SELECT DISTINCT symbol FROM historical_screener)
    GROUP BY sc.symbol
    LIMIT 5
""").fetchall()
print("Missing from HS:", missing)

# Check how many string constituents have symbols NOT in HS
missing_count = conn.execute("""
    SELECT COUNT(DISTINCT sc.symbol)
    FROM string_constituents sc
    JOIN string_universe su ON sc.string_id = su.string_id AND su.market = 'US'
    WHERE sc.symbol NOT IN (SELECT DISTINCT symbol FROM historical_screener)
""").fetchone()[0]
total_sc = conn.execute("""
    SELECT COUNT(DISTINCT sc.symbol)
    FROM string_constituents sc
    JOIN string_universe su ON sc.string_id = su.string_id AND su.market = 'US'
""").fetchone()[0]
print(f"Missing symbols: {missing_count}/{total_sc}")

# Check if the fix_hss_pst computed values are all 50.0
# The issue might be that ALL constituent symbols produce 50.0 average
# Let me compute manually for one string
string_id = conn.execute("SELECT string_id FROM string_constituents LIMIT 1").fetchone()[0]
cons = conn.execute("""
    SELECT sc.symbol, sc.weight 
    FROM string_constituents sc 
    JOIN string_universe su ON sc.string_id = su.string_id AND su.market = 'US'
    WHERE sc.string_id = ?
""", (string_id,)).fetchall()
print(f"\nManual check for {string_id}:")
for sym, wt in cons[:3]:
    pst = conn.execute("SELECT prob_up_st_cross FROM historical_screener WHERE symbol = ? AND date = '2026-07-21'", (sym,)).fetchone()
    print(f"  {sym} (wt={wt}): pst={pst}")

conn.close()
