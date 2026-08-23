import sqlite3, time
DB = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()
t0 = time.time()
cur.execute("SELECT COUNT(*) FROM historical_screener WHERE date >= '2024-07-28' AND atr_crossed_above=1")
print(f"Query 1: {cur.fetchone()[0]} rows  [{time.time()-t0:.1f}s]")
t0 = time.time()
cur.execute("SELECT COUNT(*) FROM historical_screener WHERE date >= '2024-07-28'")
print(f"Query 2: {cur.fetchone()[0]} rows  [{time.time()-t0:.1f}s]")
conn.close()
