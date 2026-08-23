import sqlite3, numpy as np
conn = sqlite3.connect('screener.db', timeout=30)
conn.execute('PRAGMA busy_timeout=30000')
rows = conn.execute(
    "SELECT symbol, date, price, next_day_return FROM historical_screener WHERE symbol = 'AAPL' AND next_day_return IS NOT NULL ORDER BY date DESC LIMIT 5"
).fetchall()
for r in rows:
    print(f"{r[0]} {r[1]}: price={r[2]}, ndr={r[3]:.4f} -> implied_next={r[2]*(1+r[3]):.2f}")
# What % of non-penny stocks have ndr > 0.1?
rows2 = conn.execute(
    "SELECT AVG(next_day_return), COUNT(*) FROM historical_screener WHERE price > 5 AND atr_crossed_above = 1 AND next_day_return IS NOT NULL"
).fetchone()
print(f"\nStocks >$5 with ST cross up: avg_ndr={rows2[0]:.4f}, count={rows2[1]}")
rows3 = conn.execute(
    "SELECT AVG(next_day_return), COUNT(*) FROM historical_screener WHERE price > 10 AND atr_crossed_above = 1 AND next_day_return IS NOT NULL"
).fetchone()
print(f"Stocks >$10 with ST cross up: avg_ndr={rows3[0]:.4f}, count={rows3[1]}")
conn.close()
