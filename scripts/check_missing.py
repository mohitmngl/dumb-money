import sqlite3
conn = sqlite3.connect("screener.db")
cur = conn.cursor()
all_syms = set(r[0] for r in cur.execute("SELECT symbol FROM stats").fetchall())
done_syms = set(r[0] for r in cur.execute("SELECT symbol FROM retest_v2_scores").fetchall())
missing = all_syms - done_syms
print(f"Missing: {len(missing)}")
short = 0
for s in sorted(missing):
    cnt = cur.execute("SELECT COUNT(*) FROM bars WHERE symbol=? AND timeframe='1Day'", (s,)).fetchone()[0]
    if cnt < 30:
        short += 1
print(f"Of {len(missing)} missing: {short} have <30 bars (DATA_INSUFFICIENT)")
print(f"Remaining {len(missing)-short} have >=30 bars but no V2 score")
conn.close()
