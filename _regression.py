"""P10: Full regression - step by step."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
print("Starting P10 regression...")
sys.stdout.flush()

PASS = 0
FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}: {detail}")
    sys.stdout.flush()

# 1. py_compile
print("=== 1. py_compile ===")
import py_compile
files = ["dumbmoney/basket_screener.py","dumbmoney/app.py","dumbmoney/refresh.py",
         "dumbmoney/string_screener.py","dumbmoney/db.py","dumbmoney/engine.py","dumbmoney/indicators.py"]
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        check(f"py_compile {f}", True)
    except py_compile.PyCompileError as e:
        check(f"py_compile {f}", False, str(e))

# 2. DB connectivity
print("=== 2. DB connectivity ===")
import sqlite3
for market in ["US", "INDIA"]:
    try:
        db_file = "screener.db" if market == "US" else "india.db"
        print(f"  Connecting to {db_file}...")
        sys.stdout.flush()
        c = sqlite3.connect(db_file, timeout=5)
        print(f"  Connected, querying counts...")
        sys.stdout.flush()
        n_bars = c.execute("SELECT COUNT(*) FROM bars WHERE timeframe='1Day'").fetchone()[0]
        n_stats = c.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
        n_assets = c.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        check(f"{market}: bars exist", n_bars > 0, f"n_bars={n_bars}")
        check(f"{market}: stats exist", n_stats > 0, f"n_stats={n_stats}")
        check(f"{market}: assets exist", n_assets > 0, f"n_assets={n_assets}")
        c.close()
    except Exception as e:
        check(f"{market}: DB connectivity", False, str(e))

# 3. US bars freshness
print("=== 3. US bars freshness ===")
try:
    c = sqlite3.connect("screener.db", timeout=5)
    latest_bar = c.execute("SELECT MAX(date) FROM bars WHERE timeframe='1Day'").fetchone()[0]
    n_with_latest = c.execute("SELECT COUNT(DISTINCT symbol) FROM bars WHERE timeframe='1Day' AND date=?", (latest_bar,)).fetchone()[0]
    check("US latest bar date is recent", latest_bar >= "2026-07-20", f"latest={latest_bar}")
    check("US symbols with latest bar", n_with_latest >= 5000, f"n={n_with_latest}")
    c.close()
except Exception as e:
    check("US bars freshness", False, str(e))

# 4. historical_string_screener
print("=== 4. historical_string_screener ===")
try:
    c = sqlite3.connect("screener.db", timeout=5)
    n = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
    u = c.execute("SELECT COUNT(DISTINCT string_id) FROM historical_string_screener").fetchone()[0]
    check("hss has data", n > 0, f"rows={n}")
    check("hss has all strings", u >= 50000, f"unique_strings={u}")
    c.close()
except Exception as e:
    check("hss integrity", False, str(e))

# 5. India hss
print("=== 5. India hss ===")
try:
    c = sqlite3.connect("india.db", timeout=5)
    n = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
    u = c.execute("SELECT COUNT(DISTINCT string_id) FROM historical_string_screener").fetchone()[0]
    check("India hss has data", n > 0, f"rows={n}")
    check("India hss strings", u > 0, f"unique_strings={u}")
    c.close()
except Exception as e:
    check("India hss", False, str(e))

# 6. API endpoints
print("=== 6. API endpoints ===")
try:
    import requests
    base = "http://localhost:8474/api"
    for name, url in [("basket-screener", f"{base}/basket-screener?market=US&per_page=1"),
                       ("stock-screener", f"{base}/screener?market=US&per_page=1"),
                       ("basket-columns", f"{base}/basket-screener/columns")]:
        r = requests.get(url, timeout=30)
        check(f"API {name}", r.status_code == 200, f"status={r.status_code}")
except Exception as e:
    check("API endpoints", False, str(e))

# Summary
print(f"\n{'='*40}")
print(f"PASS: {PASS}, FAIL: {FAIL}")
if FAIL == 0:
    print("ALL CHECKS PASSED!")
else:
    print(f"{FAIL} CHECKS FAILED!")
