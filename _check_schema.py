import sqlite3
c = sqlite3.connect('screener.db')
c.row_factory = sqlite3.Row

# Check string_symbols table schema
schema = c.execute("PRAGMA table_info(string_symbols)").fetchall()
print("string_symbols columns:", [s['name'] for s in schema])

# Check string_symbols content
total = c.execute("SELECT COUNT(*) FROM string_symbols").fetchone()[0]
print(f"Total string_symbols rows: {total}")

# Sample
rows = c.execute("SELECT * FROM string_symbols LIMIT 3").fetchall()
for r in rows:
    print(dict(r))

# Check string_universe
schema2 = c.execute("PRAGMA table_info(string_universe)").fetchall()
print("\nstring_universe columns:", [s['name'] for s in schema2])
total2 = c.execute("SELECT COUNT(*) FROM string_universe").fetchone()[0]
print(f"Total string_universe rows: {total2}")
rows2 = c.execute("SELECT * FROM string_universe LIMIT 3").fetchall()
for r in rows2:
    print(dict(r))

# Check strings table
schema3 = c.execute("PRAGMA table_info(strings)").fetchall()
print("\nstrings columns:", [s['name'] for s in schema3])
total3 = c.execute("SELECT COUNT(*) FROM strings").fetchone()[0]
print(f"Total strings rows: {total3}")
rows3 = c.execute("SELECT * FROM strings LIMIT 3").fetchall()
for r in rows3:
    print(dict(r))

c.close()
