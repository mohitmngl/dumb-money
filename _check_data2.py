import sqlite3

# US HS
conn = sqlite3.connect('screener.db', timeout=30)
conn.execute('PRAGMA busy_timeout=30000')
conn.execute('PRAGMA journal_mode=WAL')
dr = conn.execute('SELECT MIN(date), MAX(date) FROM historical_screener').fetchone()
print(f'US HS: {dr[0]} to {dr[1]}')
sample = conn.execute("SELECT symbol, date, atr_crossed_above, prob_up_st_cross, next_day_return FROM historical_screener WHERE atr_crossed_above = 1 AND prob_up_st_cross > 60 AND next_day_return IS NOT NULL ORDER BY date DESC LIMIT 5").fetchall()
print(f'Sample US ST crossed up:')
for s in sample:
    print(f'  {s[0]} {s[1]} crossed={s[2]} pst={s[3]:.1f} next_day={s[4]:.4f}')
conn.close()

# US HSS
conn2 = sqlite3.connect('screener.db', timeout=30)
conn2.execute('PRAGMA busy_timeout=30000')
dr2 = conn2.execute('SELECT MIN(date), MAX(date) FROM historical_string_screener').fetchone()
print(f'\nUS HSS: {dr2[0]} to {dr2[1]}')
sample2 = conn2.execute("SELECT string_id, date, accel_crossed_up, prob_up_st_cross, next_day_return FROM historical_string_screener WHERE accel_crossed_up = 1 AND prob_up_st_cross > 60 AND next_day_return IS NOT NULL ORDER BY date DESC LIMIT 5").fetchall()
print(f'Sample US HSS ST crossed up:')
for s in sample2:
    print(f'  {s[0]} {s[1]} crossed={s[2]} pst={s[3]:.1f} next_day={s[4]:.4f}')
conn2.close()
