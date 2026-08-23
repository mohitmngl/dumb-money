import sqlite3, time
try:
    c = sqlite3.connect("screener.db", timeout=2)
    rows = c.execute("SELECT COUNT(*) FROM historical_string_screener").fetchone()[0]
    strings = c.execute("SELECT COUNT(DISTINCT string_id) FROM historical_string_screener").fetchone()[0]
    print(f"{time.strftime('%H:%M:%S')} rows={rows:,} strings={strings}")
    c.close()
except Exception as e:
    print(f"{time.strftime('%H:%M:%S')} DB locked: {e}")
