import sqlite3, time

DB = r"C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("PRAGMA journal_mode=WAL")
cur.execute("PRAGMA cache_size=-200000")
cur.execute("PRAGMA temp_store=MEMORY")

print("="*70)
print("PHASE 1: Create indexed temp table for date >= 2024-07-28")
print("="*70)

t0 = time.time()
cur.execute("""
    CREATE TEMPORARY TABLE IF NOT EXISTS hs AS
    SELECT date, symbol, atr_crossed_above, atr_crossed_below,
           accel_crossed_up, accel_crossed_down,
           atr_signal, accel_signal,
           prob_up_st_cross, prob_up_1d, weighted_alpha, confluence,
           change_pct, next_day_return
    FROM historical_screener
    WHERE date >= '2024-07-28'
""")
print(f"  Created temp table: {cur.rowcount} rows  [{time.time()-t0:.1f}s]")

t0 = time.time()
cur.execute("CREATE INDEX IF NOT EXISTS ix_hs_atr_xa ON hs(atr_crossed_above)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hs_atr_xb ON hs(atr_crossed_below)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hs_ac_xu ON hs(accel_crossed_up)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hs_ac_xd ON hs(accel_crossed_down)")
print(f"  Created indexes on temp table  [{time.time()-t0:.1f}s]")

def run(label, sql, params=()):
    print(f"\n{'='*70}")
    print(label)
    print("-"*70)
    t0 = time.time()
    cur.execute(sql, params)
    rows = cur.fetchall()
    dt = time.time()-t0
    for r in rows:
        print(f"  {list(r)}")
    print(f"  -- {dt:.1f}s")
    return rows

# 1. All column names from the ORIGINAL table
run("1) ALL COLUMNS IN historical_screener:", "PRAGMA table_info(historical_screener)")

# 2. Unique symbols
run("2) Unique symbols (last 2yr):",
    "SELECT COUNT(DISTINCT symbol) as cnt FROM hs")

# 3-6. Cross-event counts
run("3) atr_crossed_above=1 count:",
    "SELECT COUNT(*) as cnt FROM hs WHERE atr_crossed_above=1")

run("4) atr_crossed_below=1 count:",
    "SELECT COUNT(*) as cnt FROM hs WHERE atr_crossed_below=1")

run("5) accel_crossed_up=1 count:",
    "SELECT COUNT(*) as cnt FROM hs WHERE accel_crossed_up=1")

run("6) accel_crossed_down=1 count:",
    "SELECT COUNT(*) as cnt FROM hs WHERE accel_crossed_down=1")

# 7-8. Signal distributions
run("7) atr_signal distribution:",
    "SELECT atr_signal, COUNT(*) as cnt FROM hs GROUP BY atr_signal ORDER BY atr_signal")

run("8) accel_signal distribution:",
    "SELECT accel_signal, COUNT(*) as cnt FROM hs GROUP BY accel_signal ORDER BY accel_signal")

# 9-12. Continuous distributions using histogram buckets (fast, no sort)
def fast_dist(col, label_num):
    print(f"\n{'='*70}")
    print(f"{label_num}) {col} distribution (last 2 years):")
    print("-"*70)
    t0 = time.time()

    cur.execute(f"SELECT COUNT(*), MIN({col}), MAX({col}), AVG({col}) FROM hs WHERE {col} IS NOT NULL")
    r = cur.fetchone()
    n, mn, mx, mean = r[0], r[1], r[2], r[3]

    if n == 0 or mn is None:
        print("  No data")
        return

    # Use 200 buckets for better accuracy
    NB = 200
    step = (mx - mn) / NB if mx != mn else 1.0
    if step == 0:
        step = 1.0

    # Build 200 bucket boundaries and count in each
    boundaries = [mn + i * step for i in range(NB + 1)]

    # Build a CASE expression
    case_parts = []
    params_list = []
    for i in range(NB):
        case_parts.append(f"WHEN {col} >= ? AND {col} < ? THEN ?")
        params_list.extend([boundaries[i], boundaries[i+1], i])
    case_parts.append(f"ELSE ?")
    params_list.append(NB)  # for values exactly == mx

    case_expr = " ".join(case_parts)
    bucket_sql = f"""
        SELECT bucket, COUNT(*) as cnt FROM (
            SELECT CASE {case_expr} END as bucket
            FROM hs WHERE {col} IS NOT NULL
        ) GROUP BY bucket ORDER BY bucket
    """

    cur.execute(bucket_sql, params_list)
    buckets = cur.fetchall()

    cum = 0
    p25_val = p50_val = p75_val = None
    for b in buckets:
        cum += b['cnt']
        bucket_center = mn + (b['bucket'] + 0.5) * step
        if p25_val is None and cum >= n * 0.25:
            p25_val = bucket_center
        if p50_val is None and cum >= n * 0.50:
            p50_val = bucket_center
        if p75_val is None and cum >= n * 0.75:
            p75_val = bucket_center

    dt = time.time()-t0
    print(f"  n={n:,}   min={mn:.4f}   max={mx:.4f}   mean={mean:.4f}")
    print(f"  p25={p25_val:.4f}   p50={p50_val:.4f}   p75={p75_val:.4f}")
    print(f"  -- {dt:.1f}s")

fast_dist("prob_up_st_cross", 9)
fast_dist("prob_up_1d", 10)
fast_dist("weighted_alpha", 11)
fast_dist("confluence", 12)

# 13. Distinct trading days
run("13) Distinct trading days:",
    "SELECT COUNT(DISTINCT date) as cnt FROM hs")

# 14. Avg cross-up events per firing day
run("14a) atr_crossed_above=1 daily stats (avg, min, max, firing_days):",
    """SELECT ROUND(AVG(daily_cnt),2) as avg_per_day, MIN(daily_cnt) as min_day,
              MAX(daily_cnt) as max_day, COUNT(*) as firing_days
       FROM (SELECT date, COUNT(*) as daily_cnt FROM hs WHERE atr_crossed_above=1 GROUP BY date)""")

run("14b) accel_crossed_up=1 daily stats:",
    """SELECT ROUND(AVG(daily_cnt),2) as avg_per_day, MIN(daily_cnt) as min_day,
              MAX(daily_cnt) as max_day, COUNT(*) as firing_days
       FROM (SELECT date, COUNT(*) as daily_cnt FROM hs WHERE accel_crossed_up=1 GROUP BY date)""")

# 15. % days with >= 1 ST cross-up
run("15) % days with >= 1 atr_crossed_above:",
    """SELECT ROUND(SUM(CASE WHEN hc=1 THEN 100.0 ELSE 0 END)/COUNT(*),2) as pct,
              SUM(CASE WHEN hc=1 THEN 1 ELSE 0 END) as days_with,
              COUNT(*) as total_days
       FROM (SELECT date, MAX(CASE WHEN atr_crossed_above=1 THEN 1 ELSE 0 END) as hc
             FROM hs GROUP BY date)""")

# 16. Sample rows
print(f"\n{'='*70}")
print("16) Sample 5 rows for a date with multiple ST cross-ups:")
print("-"*70)
t0 = time.time()
cur.execute("""
    SELECT date, cnt FROM (
        SELECT date, COUNT(*) as cnt FROM hs
        WHERE atr_crossed_above=1 GROUP BY date HAVING cnt>=5
        ORDER BY RANDOM() LIMIT 1
    )""")
sample = cur.fetchone()
dt = time.time()-t0
if sample:
    sd, sc = sample['date'], sample['cnt']
    print(f"  Date: {sd} ({sc} cross-ups)  [found in {dt:.1f}s]")
    cur.execute("""SELECT date, symbol, atr_crossed_above, prob_up_st_cross,
                          change_pct, next_day_return, weighted_alpha, confluence
                   FROM hs WHERE date=? AND atr_crossed_above=1 LIMIT 5""", (sd,))
    rows = cur.fetchall()
    print(f"  {'date':<12} {'symbol':<8} {'ax_up':>5} {'p_st':>8} {'chg%':>8} {'nxt':>8} {'wa':>8} {'conf':>7}")
    for r in rows:
        print(f"  {r['date']:<12} {r['symbol']:<8} {r['atr_crossed_above']:>5} {r['prob_up_st_cross']:>8.4f} {r['change_pct']:>8.4f} {r['next_day_return']:>8.4f} {r['weighted_alpha']:>8.4f} {r['confluence']:>7.4f}")
else:
    print(f"  No qualifying date found [{dt:.1f}s]")

conn.close()
print(f"\n{'='*70}")
print("DONE")
print("="*70)
