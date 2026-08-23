import sqlite3, sys
db = sys.argv[1] if len(sys.argv) > 1 else 'screener.db'
label = sys.argv[2] if len(sys.argv) > 2 else 'US'
path = f'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/{db}'
print(f'Opening {path}...')
conn = sqlite3.connect(path, timeout=15)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=10000')

print(f'=== {label} ===')
try:
    r = conn.execute("SELECT MAX(date) FROM bars WHERE timeframe='1Day'").fetchone()
    print(f'Latest bar: {r[0]}')
except Exception as e:
    print(f'bars error: {e}')

try:
    r = conn.execute("SELECT MAX(last_updated) FROM stats").fetchone()
    print(f'Stats last_updated: {r[0]}')
except Exception as e:
    print(f'stats error: {e}')

try:
    r = conn.execute("SELECT COUNT(*) FROM historical_screener").fetchone()
    print(f'Historical screener rows: {r[0]}')
except Exception as e:
    print(f'hist_screener error: {e}')

try:
    r = conn.execute("SELECT MAX(date) FROM historical_screener").fetchone()
    print(f'Historical screener max date: {r[0]}')
except Exception as e:
    print(f'hist_screener date error: {e}')

try:
    rows = conn.execute("SELECT SUBSTR(string_id,1,2) as t, COUNT(*) FROM string_universe GROUP BY t").fetchall()
    print(f'String universe: {dict(rows)}')
except Exception as e:
    print(f'string_universe error: {e}')

try:
    r = conn.execute("SELECT COUNT(*) FROM string_screener_metrics").fetchone()
    print(f'String metrics: {r[0]} rows')
except Exception as e:
    print(f'string_metrics error: {e}')

try:
    r = conn.execute("SELECT COUNT(*), MAX(date) FROM historical_string_screener").fetchone()
    print(f'String historical: {r[0]} rows, max date: {r[1]}')
except Exception as e:
    print(f'hist_string error: {e}')

conn.close()
print('Done.')
