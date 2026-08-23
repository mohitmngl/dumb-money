import sqlite3
c = sqlite3.connect('screener.db')
r = c.execute("SELECT COUNT(*) FROM string_symbols WHERE weight < 0").fetchone()
print("LS members:", r[0])
r2 = c.execute("SELECT DISTINCT string_id FROM string_symbols WHERE weight < 0 LIMIT 10").fetchall()
print("LS string IDs:", [x[0] for x in r2])
r3 = c.execute("SELECT COUNT(DISTINCT string_id) FROM strings").fetchone()
print("Total strings:", r3[0])
tables = [x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
ls_tables = [t for t in tables if 'ls' in t.lower() or 'long_short' in t.lower() or 'longshort' in t.lower()]
print("LS tables:", ls_tables)
# Check string_screener_metrics for LS strings
r4 = c.execute("SELECT COUNT(*) FROM string_screener_metrics").fetchone()
print("String metrics rows:", r4[0])
c.close()
