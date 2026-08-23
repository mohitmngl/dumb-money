import sqlite3
conn = sqlite3.connect('file:screener.db?mode=ro', uri=True, timeout=10)
cur = conn.execute('PRAGMA table_info(historical_screener)')
cols = [r[1] for r in cur.fetchall()]
print('HS columns:', cols)
dr = conn.execute('SELECT MIN(date), MAX(date) FROM historical_screener').fetchone()
print(f'HS date range: {dr[0]} to {dr[1]}')
conn.close()
