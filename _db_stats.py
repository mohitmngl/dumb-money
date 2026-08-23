"""Quick DB stats using fast indexed queries."""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for name, db in [("US", "screener.db"), ("INDIA", "india.db")]:
    if not os.path.exists(db):
        print(f"{name}: DB not found")
        continue
    c = sqlite3.connect(db, timeout=5)
    c.execute("PRAGMA locking_mode=NORMAL")
    try:
        # Fast stats
        pgs = c.execute("PRAGMA page_count").fetchone()[0]
        print(f"{name}: page_count={pgs:,}")
        n_assets = c.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        print(f"{name}: assets={n_assets}")
        n_stats = c.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
        print(f"{name}: stats={n_stats}")
        # bars with MAX(date)
        latest = c.execute("SELECT MAX(date) FROM bars WHERE timeframe='1Day'").fetchone()[0]
        # bars timeframe counts
        tfs = c.execute("SELECT timeframe, COUNT(*) FROM bars GROUP BY timeframe ORDER BY COUNT(*) DESC").fetchall()
        for tf, cnt in tfs:
            print(f"{name}: bars({tf})={cnt:,}")
        # historical_string_screener
        hss = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
        print(f"{name}: hist_string_screener={hss:,}")
        c.close()
    except Exception as e:
        print(f"{name}: Error: {e}")
