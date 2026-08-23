import sqlite3
c = sqlite3.connect('screener.db')

# Check the basket-screener API response for a few strings
# Look for how the string detail is rendered - does it show shorts?
r = c.execute("SELECT name, raw_string FROM strings WHERE string_id LIKE 'S000001'").fetchall()
print("String S000001:", r)

# Check if there's any string_universe metadata about long/short
r = c.execute("SELECT * FROM string_universe WHERE string_id='S000001'").fetchall()
print("String universe S000001:", r)

# Check if there are any strings with 'short' in the name or metadata
r = c.execute("SELECT DISTINCT string_id FROM string_universe WHERE string_id LIKE 'S%' LIMIT 3").fetchall()
for row in r:
    sid = row[0]
    s = c.execute("SELECT * FROM strings WHERE string_id=?", (sid,)).fetchone()
    print(f"  {sid}: {s}")

# Check the app.py basket-screener detail endpoint to see how it renders long/short
c.close()
