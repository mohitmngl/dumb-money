import sqlite3
db_path = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\india.db"
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
rows = conn.execute("SELECT date, count(*) FROM historical_screener GROUP BY date ORDER BY date DESC LIMIT 5").fetchall()
print("India latest dates:")
for r in rows:
    print(f"  {r[0]}: {r[1]} rows")
total_score = conn.execute("SELECT count(*) FROM historical_screener WHERE old_swing_retest_score > 0").fetchone()[0]
print(f"\nTotal hist rows with score > 0: {total_score}")
conn.close()
