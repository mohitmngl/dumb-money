import sqlite3
for db_name, label in [('screener.db', 'US'), ('india.db', 'INDIA')]:
    conn = sqlite3.connect(f'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/{db_name}')
    print(f'=== {label} ===')
    r = conn.execute("SELECT MAX(date) FROM bars WHERE timeframe='1Day'").fetchone()
    print(f'Latest bar: {r[0]}')
    r = conn.execute("SELECT MAX(last_updated) FROM stats").fetchone()
    print(f'Stats last_updated: {r[0]}')
    r = conn.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM historical_screener").fetchone()
    print(f'Historical screener: {r[0]} rows, dates {r[1]} to {r[2]}')
    try:
        rows = conn.execute("SELECT SUBSTR(string_id,1,2) as t, COUNT(*) FROM string_universe GROUP BY t").fetchall()
        print(f'String universe: {dict(rows)}')
    except:
        print('String universe: table missing')
    try:
        r = conn.execute("SELECT COUNT(*) FROM string_screener_metrics").fetchone()
        print(f'String metrics: {r[0]} rows')
    except:
        print('String metrics: table missing')
    try:
        r = conn.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM historical_string_screener").fetchone()
        print(f'String historical: {r[0]} rows, dates {r[1]} to {r[2]}')
    except:
        print('String historical: table missing')
    conn.close()
    print()
