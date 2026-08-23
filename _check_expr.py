import sqlite3
c = sqlite3.connect('screener.db')

# Check string_universe for S000001
r = c.execute("SELECT * FROM string_universe WHERE string_id='S000001'").fetchone()
print("S000001:", r)

# Check string_universe for LS000001
r = c.execute("SELECT * FROM string_universe WHERE string_id='LS000001'").fetchone()
print("LS000001:", r)

# Check the expression field - does it contain SHORT()?
for sid in ['S000001', 'S000002', 'LS000001']:
    r = c.execute("SELECT expression FROM string_universe WHERE string_id=?", (sid,)).fetchone()
    print(f"{sid} expression: {r[0][:200] if r and r[0] else 'None'}")

# Check if any S-prefix strings have SHORT in their expression
r = c.execute("SELECT COUNT(*) FROM string_universe WHERE string_id LIKE 'S%' AND expression LIKE '%SHORT%'").fetchone()
print(f"S-prefix strings with SHORT in expression: {r[0]}")

r = c.execute("SELECT COUNT(*) FROM string_universe WHERE string_id LIKE 'S%' AND expression LIKE '%short%'").fetchone()
print(f"S-prefix strings with 'short' in expression: {r[0]}")

c.close()
