"""Debug index and India rebuild failures."""
import sys, os, sqlite3, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# India: get latest string_id to see how far it got
c = sqlite3.connect("india.db", timeout=30)
try:
    latest = c.execute("SELECT MAX(CAST(SUBSTR(string_id,2) AS INTEGER)) FROM historical_string_screener").fetchone()[0]
    cnt = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
    uniq = c.execute("SELECT COUNT(DISTINCT string_id) FROM historical_string_screener").fetchone()[0]
    print(f"India hss: rows={cnt:,}, unique_strings={uniq:,}, max_string_id_num={latest}")
except Exception as e:
    print(f"India hss error: {e}")
c.close()

# US: try creating index and catch error
print()
print("Testing idx_hss_date creation...")
c = sqlite3.connect("screener.db", timeout=600)
try:
    c.execute("CREATE INDEX IF NOT EXISTS idx_hss_date ON historical_string_screener(date)")
    print("Index created successfully!")
except Exception as e:
    print(f"Index creation failed: {e}")
c.close()
