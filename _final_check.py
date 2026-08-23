import sqlite3
for db, label in [('screener.db', 'US'), ('india.db', 'INDIA')]:
    path = f'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/{db}'
    c = sqlite3.connect(path, timeout=30)
    c.execute('PRAGMA busy_timeout=30000')
    print(f"\n=== {label} ===")
    r = c.execute("SELECT COUNT(*), MAX(date) FROM bars WHERE timeframe='1Day'").fetchone()
    print(f"  Bars: {r[0]:,} rows, max date: {r[1]}")
    r = c.execute("SELECT MAX(last_updated) FROM stats").fetchone()
    print(f"  Stats updated: {r[0]}")
    r = c.execute("SELECT COUNT(*), MAX(date) FROM historical_screener").fetchone()
    print(f"  Hist screener: {r[0]:,} rows, max date: {r[1]}")
    try:
        rows = c.execute("SELECT SUBSTR(string_id,1,2) as t, COUNT(*) FROM string_universe GROUP BY t").fetchall()
        print(f"  String universe: {dict(rows)}")
    except: pass
    try:
        r = c.execute("SELECT COUNT(*) FROM string_screener_metrics").fetchone()
        print(f"  String metrics: {r[0]:,} rows")
    except: pass
    try:
        r = c.execute("SELECT COUNT(*), MAX(date) FROM historical_string_screener").fetchone()
        print(f"  String historical: {r[0]:,} rows, max date: {r[1]}")
    except: pass
    c.close()
