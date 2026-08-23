import sqlite3, time
t = time.time()
conn = sqlite3.connect(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db', timeout=10)
r = conn.execute('SELECT COUNT(*) FROM historical_string_screener WHERE date >= "2024-01-01" AND next_day_return IS NOT NULL').fetchone()
print(f'2024+ rows: {r[0]} ({time.time()-t:.0f}s)')
conn.close()
