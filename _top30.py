import sqlite3
c = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/india.db', timeout=30)
c.execute('PRAGMA busy_timeout=30000')

rows = c.execute("""
    SELECT h.symbol, a.name, h.price, h.change_pct, h.volume, h.weighted_alpha, h.streak
    FROM historical_screener h
    LEFT JOIN assets a ON h.symbol = a.symbol
    WHERE h.date = '2024-03-12'
    ORDER BY h.change_pct DESC
    LIMIT 30
""").fetchall()

print(f"{'#':<4} {'Symbol':<15} {'Name':<35} {'Price':>10} {'Chg%':>8} {'Volume':>12} {'WA':>8} {'Streak':>7}")
print("-" * 105)
for i, (sym, name, price, chg, vol, wa, streak) in enumerate(rows, 1):
    name_short = (name or '')[:33]
    print(f"{i:<4} {sym:<15} {name_short:<35} {price or 0:>10.2f} {chg or 0:>7.2f}% {vol or 0:>12,.0f} {wa or 0:>8.2f} {streak or 0:>7}")

c.close()
