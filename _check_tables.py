import sqlite3
c = sqlite3.connect('india.db')
r = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print([x[0] for x in r])
c.close()
