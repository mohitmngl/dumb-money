import sqlite3
# Check US basket string weights
c = sqlite3.connect('screener.db')
rows = c.execute("SELECT weight FROM string_constituents WHERE string_id='S000001'").fetchall()
print("US S000001 weights:", [r[0] for r in rows])
has_neg = c.execute("SELECT COUNT(*) FROM string_constituents WHERE weight < 0 AND string_id LIKE 'S%'").fetchone()[0]
print("US basket strings with negative weights:", has_neg)

# Check LS string weights
rows = c.execute("SELECT weight FROM string_constituents WHERE string_id='LS000001'").fetchall()
print("LS000001 weights:", [r[0] for r in rows])
ls_neg = c.execute("SELECT COUNT(*) FROM string_constituents WHERE weight < 0 AND string_id LIKE 'LS%'").fetchone()[0]
print("LS strings with negative weights:", ls_neg)
c.close()

# Check India basket
c = sqlite3.connect('india.db')
rows = c.execute("SELECT weight FROM string_constituents WHERE string_id='S000001'").fetchall()
print("INDIA S000001 weights:", [r[0] for r in rows])
has_neg = c.execute("SELECT COUNT(*) FROM string_constituents WHERE weight < 0 AND string_id LIKE 'S%'").fetchone()[0]
print("India basket strings with negative weights:", has_neg)
c.close()
