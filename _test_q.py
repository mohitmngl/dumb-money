import sqlite3, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

db_path = 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db'
conn = sqlite3.connect(db_path, timeout=60)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA busy_timeout=120000')
conn.execute('PRAGMA cache_size=-64000')

t0 = time.time()
r = conn.execute("SELECT COUNT(*) FROM historical_string_screener WHERE date >= '2024-01-01' AND next_day_return IS NOT NULL").fetchone()
print(f"2024+ rows with returns: {r[0]} ({time.time()-t0:.0f}s)", flush=True)

t0 = time.time()
dates = [x[0] for x in conn.execute(
    "SELECT DISTINCT date FROM historical_string_screener WHERE date >= '2024-01-01' AND next_day_return IS NOT NULL ORDER BY date"
).fetchall()]
print(f"Dates: {len(dates)} ({time.time()-t0:.0f}s)", flush=True)

# Test one query
t0 = time.time()
rows = conn.execute("""
    SELECT next_day_return FROM historical_string_screener
    WHERE date = ? AND next_day_return IS NOT NULL AND atr_crossed_above = 1
    ORDER BY prob_up_st_cross DESC LIMIT 30
""", (dates[100],)).fetchall()
print(f"Single date query: {len(rows)} rows ({time.time()-t0:.3f}s)", flush=True)

conn.close()
