import sqlite3
conn = sqlite3.connect('screener.db', timeout=60)
conn.execute('PRAGMA busy_timeout=60000')
rows = conn.execute(
    "SELECT symbol, date, price, next_day_return FROM historical_screener WHERE symbol = 'AAPL' AND next_day_return IS NOT NULL ORDER BY date DESC LIMIT 5"
).fetchall()
for r in rows:
    print(f"{r[0]} {r[1]}: price={r[2]}, ndr={r[3]:.4f}")
rows2 = conn.execute(
    "SELECT AVG(next_day_return), COUNT(*) FROM historical_screener WHERE price > 5 AND atr_crossed_above = 1 AND next_day_return IS NOT NULL"
).fetchone()
print(f"Stocks>$5 ST cross: avg_ndr={rows2[0]:.4f}, count={rows2[1]}")
conn.close()
