import sqlite3
c = sqlite3.connect('screener.db')

# Check ALL S-prefix strings for negative weights
neg = c.execute("SELECT string_id, symbol, weight FROM string_constituents WHERE string_id LIKE 'S%' AND weight < 0 LIMIT 20").fetchall()
print("US S-strings with NEGATIVE weights:", len(neg))
for r in neg:
    print(" ", r)

# Check total count of S-strings with negatives
total_neg = c.execute("SELECT COUNT(*) FROM string_constituents WHERE string_id LIKE 'S%' AND weight < 0").fetchone()[0]
print("Total US S-string rows with negative weight:", total_neg)

# Check a few more strings
for sid in ['S000002', 'S000010', 'S000100', 'S010000']:
    rows = c.execute("SELECT symbol, weight FROM string_constituents WHERE string_id=?", (sid,)).fetchall()
    weights = [r[1] for r in rows]
    print(f"{sid}: weights={weights}")

# Also check how many S-prefix strings exist
total = c.execute("SELECT COUNT(DISTINCT string_id) FROM string_constituents WHERE string_id LIKE 'S%'").fetchone()[0]
print(f"Total US S-prefix strings: {total}")

# Check total LS strings
ls_total = c.execute("SELECT COUNT(DISTINCT string_id) FROM string_constituents WHERE string_id LIKE 'LS%'").fetchone()[0]
print(f"Total US LS-prefix strings: {ls_total}")

c.close()
