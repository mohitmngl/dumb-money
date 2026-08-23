import sqlite3

conn = sqlite3.connect(r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db', timeout=30)
conn.execute('PRAGMA journal_mode=WAL')

rows = conn.execute("""
    SELECT s.symbol, s.price, s.volume, s.atrp, s.weighted_alpha, s.streak,
           s.change_pct, s.atr_signal, s.accel_signal, s.confluence,
           s.prob_up_1d, s.prob_up_5d, s.next_day_return, s.next_5d_return,
           a.name, a.asset_class, a.fractionable
    FROM stats s
    JOIN assets a ON s.symbol = a.symbol
    WHERE a.asset_class = 'stock'
      AND s.volume > 500000
      AND s.price > 5
      AND s.atrp > 5
    ORDER BY s.atrp DESC
    LIMIT 30
""").fetchall()

print("=== TOP 30 MOST VOLATILE + HIGH VOLUME STOCKS ===")
hdr = f"{'Sym':>6} {'Price':>8} {'Vol(M)':>8} {'ATRP%':>7} {'WA':>7} {'Strk':>5} {'Chg%':>7} {'ST':>3} {'Acc':>3} {'Conf':>5} {'P1d':>5} {'ND':>7} {'Frac':>4} Name"
print(hdr)
print("-" * 120)
for r in rows:
    sym, price, vol, atrp, wa, streak, chg, st_sig, acc_sig, conf, p1, p5, nd, nd5, name, ac, frac = r
    f = "Y" if frac else "N"
    n = (name or "")[:22]
    print(f"{sym:>6} {price:>8.2f} {vol/1e6:>8.1f} {atrp:>7.1f} {wa:>7.1f} {streak:>5} {chg:>7.2f} {st_sig:>3} {acc_sig:>3} {conf:>5.1f} {p1:>5.1f} {nd:>7.2f} {f:>4} {n}")

print()
print("=== TOP MOMENTUM PLAYS (high WA + strong direction) ===")
rows2 = conn.execute("""
    SELECT s.symbol, s.price, s.volume, s.atrp, s.weighted_alpha, s.streak,
           s.change_pct, s.atr_signal, s.accel_signal, s.confluence,
           s.prob_up_1d, s.next_day_return, s.next_5d_return,
           a.name, a.fractionable
    FROM stats s
    JOIN assets a ON s.symbol = a.symbol
    WHERE a.asset_class = 'stock'
      AND s.volume > 1000000
      AND s.price > 10
      AND s.atr_signal = 1
      AND s.accel_signal = 1
      AND s.weighted_alpha > 20
      AND s.confluence > 3
    ORDER BY s.confluence DESC, s.weighted_alpha DESC
    LIMIT 20
""").fetchall()
print(f"{'Sym':>6} {'Price':>8} {'Vol(M)':>8} {'ATRP%':>7} {'WA':>7} {'Strk':>5} {'Chg%':>7} {'Conf':>5} {'P1d':>5} {'ND':>7} Name")
print("-" * 100)
for r in rows2:
    sym, price, vol, atrp, wa, streak, chg, st_sig, acc_sig, conf, p1, nd, nd5, name, frac = r
    n = (name or "")[:22]
    print(f"{sym:>6} {price:>8.2f} {vol/1e6:>8.1f} {atrp:>7.1f} {wa:>7.1f} {streak:>5} {chg:>7.2f} {conf:>5.1f} {p1:>5.1f} {nd:>7.2f} {n}")

print()
print("=== TOP SHORT CANDIDATES (bearish signals + high volume) ===")
rows3 = conn.execute("""
    SELECT s.symbol, s.price, s.volume, s.atrp, s.weighted_alpha, s.streak,
           s.change_pct, s.atr_signal, s.accel_signal, s.confluence,
           s.prob_up_1d, s.next_day_return, s.next_5d_return,
           a.name, a.fractionable
    FROM stats s
    JOIN assets a ON s.symbol = a.symbol
    WHERE a.asset_class = 'stock'
      AND s.volume > 1000000
      AND s.price > 10
      AND s.atr_signal = -1
      AND s.accel_signal = -1
      AND s.weighted_alpha < -10
    ORDER BY s.confluence ASC, s.weighted_alpha ASC
    LIMIT 20
""").fetchall()
print(f"{'Sym':>6} {'Price':>8} {'Vol(M)':>8} {'ATRP%':>7} {'WA':>7} {'Strk':>5} {'Chg%':>7} {'Conf':>5} {'P1d':>5} {'ND':>7} Name")
print("-" * 100)
for r in rows3:
    sym, price, vol, atrp, wa, streak, chg, st_sig, acc_sig, conf, p1, nd, nd5, name, frac = r
    n = (name or "")[:22]
    print(f"{sym:>6} {price:>8.2f} {vol/1e6:>8.1f} {atrp:>7.1f} {wa:>7.1f} {streak:>5} {chg:>7.2f} {conf:>5.1f} {p1:>5.1f} {nd:>7.2f} {n}")

conn.close()
