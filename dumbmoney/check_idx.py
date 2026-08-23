import sqlite3
conn = sqlite3.connect(r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db")
cur = conn.cursor()
cur.execute("SELECT name, sql FROM sqlite_master WHERE type='index'")
for r in cur.fetchall():
    print(r[0], "|", r[1])
cur.execute("SELECT MIN(date), MAX(date) FROM historical_screener")
print("date range:", cur.fetchone())
cur.execute("SELECT COUNT(*) FROM historical_screener")
print("total rows:", cur.fetchone())
conn.close()
