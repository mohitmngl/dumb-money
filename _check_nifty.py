import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

# Check how Nifty 500 is identified
r = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%nifty%'").fetchall()
print("Nifty tables:", r)
r = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%index%'").fetchall()
print("Index tables:", r)
r = c.execute("PRAGMA table_info(assets)").fetchall()
print("Assets columns:", [(col[1], col[2]) for col in r])
# Check if there's an index or tag for Nifty 500
r = c.execute("SELECT DISTINCT exchange FROM assets LIMIT 10").fetchall()
print("Exchanges:", r)
r = c.execute("SELECT DISTINCT asset_class FROM assets LIMIT 10").fetchall()
print("Asset classes:", r)
c.close()
