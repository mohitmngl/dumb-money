import sqlite3
db_path = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\india.db"
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
total = conn.execute("SELECT count(*) FROM stats").fetchone()[0]
with_score = conn.execute("SELECT count(*) FROM stats WHERE old_swing_retest_score > 0").fetchone()[0]
latest = conn.execute("SELECT max(last_updated) FROM stats").fetchone()[0]
top = conn.execute("SELECT symbol, old_swing_retest_score FROM stats WHERE old_swing_retest_score > 0 ORDER BY old_swing_retest_score DESC LIMIT 5").fetchall()
print(f"India stats: {total} total, {with_score} with score, latest={latest}")
for r in top:
    print(f"  {r[0]}: {r[1]:.2f}")
conn.close()
