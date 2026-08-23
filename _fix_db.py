from trading_bot import db, data

db.init_db()
conn = db.get_db()

alpaca_pos = data.get_positions()
alpaca_syms = set(p['symbol'] for p in alpaca_pos)
print('Alpaca positions: %s' % list(alpaca_syms))

open_rows = conn.execute("SELECT id, symbol FROM positions WHERE status='open'").fetchall()
print('DB open positions: %d' % len(open_rows))

for r in open_rows:
    if r['symbol'] not in alpaca_syms:
        print('  Closing DB position: %s (not on Alpaca)' % r['symbol'])
        conn.execute("UPDATE positions SET status='closed', exit_reason='alpaca_sync' WHERE id=%d" % r['id'])
    else:
        print('  Keeping DB position: %s (still on Alpaca)' % r['symbol'])

conn.commit()

remaining = conn.execute("SELECT COUNT(*) as c FROM positions WHERE status='open'").fetchone()['c']
print('DB open positions after sync: %d' % remaining)
conn.close()
