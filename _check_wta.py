import sqlite3
c = sqlite3.connect('screener.db')
c.row_factory = sqlite3.Row

# Check if the extreme WTA baskets are LS (have negative weights)
extreme = c.execute("SELECT string_id, weighted_alpha FROM string_screener_metrics ORDER BY weighted_alpha DESC LIMIT 5").fetchall()
for row in extreme:
    sid = row['string_id']
    members = c.execute("SELECT symbol, weight FROM string_symbols WHERE string_id=?", (sid,)).fetchall()
    has_short = any(m['weight'] < 0 for m in members)
    total_abs_w = sum(abs(m['weight']) for m in members)
    total_w = sum(m['weight'] for m in members)
    print(f"{sid}: WTA={row['weighted_alpha']:.0f}, has_short={has_short}, total_w={total_w:.2f}, total_abs_w={total_abs_w:.2f}")

# Also check normal strings
normal = c.execute("SELECT string_id, weighted_alpha FROM string_screener_metrics WHERE string_id LIKE 'S%' ORDER BY weighted_alpha DESC LIMIT 3").fetchall()
for row in normal:
    sid = row['string_id']
    members = c.execute("SELECT symbol, weight FROM string_symbols WHERE string_id=?", (sid,)).fetchall()
    total_abs_w = sum(abs(m['weight']) for m in members)
    total_w = sum(m['weight'] for m in members)
    print(f"{sid}: WTA={row['weighted_alpha']:.2f}, total_w={total_w:.2f}, total_abs_w={total_abs_w:.2f}")

c.close()
