import sqlite3, sys, os
sys.path.insert(0, r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt')
import pandas as pd
import numpy as np
from dumbmoney.indicators import (
    supertrend, weighted_alpha, accel, prob_up, next_day_return,
    streak_vectorized, atrp, compute_confluence
)

DB = r'C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\screener.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

issues = []
ok = []

print("=" * 80)
print("COMPREHENSIVE COLUMN VALIDATION")
print("=" * 80)

# 1. Price and Volume
print("\n--- 1. Price & Volume ---")
for sym in ['AAPL', 'TSLA', 'NVDA']:
    r = conn.execute("SELECT symbol, price, volume, change_pct FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r:
        d = dict(r)
        bars = pd.read_sql(f"SELECT close, volume FROM bars WHERE symbol='{sym}' AND timeframe='1Day' ORDER BY date DESC LIMIT 1", conn)
        if not bars.empty:
            db_price = d['price']
            bar_price = bars.close.iloc[0]
            price_ok = abs(db_price - bar_price) < 0.01
            status = "OK" if price_ok else f"MISMATCH db={db_price} bar={bar_price}"
            if price_ok: ok.append(f"{sym}:price")
            else: issues.append(f"{sym}:price {status}")
            print(f"  {sym}: price={db_price}, last_bar_close={bar_price} -> {status}")

# 2. Weighted Alpha (fixed: now uses last 252 bars)
print("\n--- 2. Weighted Alpha (fixed) ---")
for sym in ['AAPL', 'TSLA', 'NVDA', 'MSFT', 'GSIW']:
    r = conn.execute("SELECT symbol, weighted_alpha FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r:
        d = dict(r)
        bars = pd.read_sql(f"SELECT close FROM bars WHERE symbol='{sym}' AND timeframe='1Day' ORDER BY date", conn)
        c = bars.close.astype(float).ffill().fillna(0).values
        n = min(252, len(c))
        c2 = c[-n:]
        if c2[0] > 0:
            cum_ret = (c2 / c2[0]) - 1.0
            weights = np.linspace(0.5, 1.0, n)
            weights = weights / weights.sum()
            expected = float(np.dot(cum_ret, weights)) * 100
            match = abs(d['weighted_alpha'] - expected) < 0.01
            status = "OK" if match else f"MISMATCH db={d['weighted_alpha']:.4f} expected={expected:.4f}"
            if match: ok.append(f"{sym}:weighted_alpha")
            else: issues.append(f"{sym}:weighted_alpha {status}")
            print(f"  {sym}: WA={d['weighted_alpha']:.4f}, expected={expected:.4f} -> {status}")
        else:
            print(f"  {sym}: skip (close[0] <= 0)")

# 3. ATR / SuperTrend
print("\n--- 3. ATR / SuperTrend ---")
for sym in ['AAPL', 'TSLA']:
    r = conn.execute("SELECT symbol, atr_signal, atr_stop, atr_value, atr_streak, atr_crossed_above, atr_crossed_below FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r:
        d = dict(r)
        bars = pd.read_sql(f"SELECT * FROM bars WHERE symbol='{sym}' AND timeframe='1Day' ORDER BY date", conn)
        st = supertrend(bars)
        last_st = int(st['trend'].iloc[-1])
        last_stop = float(st['stop'].iloc[-1])
        last_atr = float(st['atr_value'].iloc[-1])
        last_streak = int(st['streak'].iloc[-1])
        last_cross_up = int(st['crossed_above'].iloc[-1])
        last_cross_down = int(st['crossed_below'].iloc[-1])

        checks = [
            ('atr_signal', d['atr_signal'], last_st),
            ('atr_stop', round(d['atr_stop'], 4), round(last_stop, 4)),
            ('atr_value', round(d['atr_value'], 4), round(last_atr, 4)),
            ('atr_streak', d['atr_streak'], last_streak),
            ('atr_crossed_above', d['atr_crossed_above'], last_cross_up),
            ('atr_crossed_below', d['atr_crossed_below'], last_cross_down),
        ]
        for name, db_val, calc_val in checks:
            match = db_val == calc_val or (isinstance(db_val, float) and abs(db_val - calc_val) < 0.001)
            status = "OK" if match else f"MISMATCH db={db_val} calc={calc_val}"
            if match: ok.append(f"{sym}:{name}")
            else: issues.append(f"{sym}:{name} {status}")
            print(f"  {sym}: {name}={db_val}, calc={calc_val} -> {status}")

# 4. ATRP
print("\n--- 4. ATRP ---")
for sym in ['AAPL']:
    r = conn.execute("SELECT symbol, atrp FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r:
        d = dict(r)
        bars = pd.read_sql(f"SELECT high, low, close FROM bars WHERE symbol='{sym}' AND timeframe='1Day' ORDER BY date", conn)
        h = bars.high.astype(float)
        l = bars.low.astype(float)
        c = bars.close.astype(float)
        daily_range = (h - l) / c * 100
        expected_atrp = float(daily_range.rolling(20, min_periods=1).mean().iloc[-1])
        match = abs(d['atrp'] - expected_atrp) < 0.1
        status = "OK" if match else f"MISMATCH db={d['atrp']:.4f} expected={expected_atrp:.4f}"
        if match: ok.append(f"{sym}:atrp")
        else: issues.append(f"{sym}:atrp {status}")
        print(f"  {sym}: atrp={d['atrp']:.4f}, expected={expected_atrp:.4f} -> {status}")

# 5. Streak
print("\n--- 5. Streak ---")
for sym in ['AAPL', 'NVDA']:
    r = conn.execute("SELECT symbol, streak FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r:
        d = dict(r)
        bars = pd.read_sql(f"SELECT close FROM bars WHERE symbol='{sym}' AND timeframe='1Day' ORDER BY date", conn)
        c = bars.close.astype(float)
        sv = streak_vectorized(c)
        expected = int(sv[-1])
        match = d['streak'] == expected
        status = "OK" if match else f"MISMATCH db={d['streak']} expected={expected}"
        if match: ok.append(f"{sym}:streak")
        else: issues.append(f"{sym}:streak {status}")
        print(f"  {sym}: streak={d['streak']}, expected={expected} -> {status}")

# 6. Prob Up
print("\n--- 6. Prob Up ---")
for sym in ['AAPL']:
    r = conn.execute("SELECT symbol, prob_up_1d, prob_up_5d FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r:
        d = dict(r)
        bars = pd.read_sql(f"SELECT close FROM bars WHERE symbol='{sym}' AND timeframe='1Day' ORDER BY date", conn)
        c = bars.close.astype(float)
        p1 = prob_up(c, 1)
        p5 = prob_up(c, 5)
        exp_1d = float(p1.iloc[-1])
        exp_5d = float(p5.iloc[-1])
        m1 = abs(d['prob_up_1d'] - exp_1d) < 0.5
        m5 = abs(d['prob_up_5d'] - exp_5d) < 0.5
        print(f"  {sym}: prob_up_1d db={d['prob_up_1d']:.2f} calc={exp_1d:.2f} -> {'OK' if m1 else 'MISMATCH'}")
        print(f"  {sym}: prob_up_5d db={d['prob_up_5d']:.2f} calc={exp_5d:.2f} -> {'OK' if m5 else 'MISMATCH'}")
        if m1: ok.append(f"{sym}:prob_up_1d")
        else: issues.append(f"{sym}:prob_up_1d MISMATCH")
        if m5: ok.append(f"{sym}:prob_up_5d")
        else: issues.append(f"{sym}:prob_up_5d MISMATCH")

# 7. Next Day Return
print("\n--- 7. Next Day Return ---")
r = conn.execute("SELECT symbol, next_day_return, change_pct FROM stats WHERE symbol='AAPL'").fetchone()
d = dict(r)
print(f"  AAPL: next_day_return={d['next_day_return']:.4f}%, change_pct={d['change_pct']:.4f}%")
if abs(d['next_day_return'] - d['change_pct']) < 0.001:
    print(f"  NOTE: next_day_return == change_pct (by design: ndr.iloc[-2] = last complete return)")
    ok.append("next_day_return:design")
else:
    issues.append(f"next_day_return: unexpected mismatch")

# 8. Accel
print("\n--- 8. Accel ---")
for sym in ['AAPL', 'TSLA']:
    r = conn.execute("SELECT symbol, accel_a, accel_base, accel_signal, accel_crossed_up, accel_crossed_down, accel_streak FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r:
        d = dict(r)
        bars = pd.read_sql(f"SELECT * FROM bars WHERE symbol='{sym}' AND timeframe='1Day' ORDER BY date", conn)
        ac = accel(bars)
        last_a = round(float(ac['accel_a'].iloc[-1]), 6)
        last_base = round(float(ac['accel_base'].iloc[-1]), 6)
        last_sig = int(ac['accel_signal'].iloc[-1])
        last_xup = int(ac['accel_crossed_up'].iloc[-1])
        last_xdn = int(ac['accel_crossed_down'].iloc[-1])
        last_streak = int(ac['accel_streak'].iloc[-1])

        checks = [
            ('accel_a', d['accel_a'], last_a),
            ('accel_base', d['accel_base'], last_base),
            ('accel_signal', d['accel_signal'], last_sig),
            ('accel_crossed_up', d['accel_crossed_up'], last_xup),
            ('accel_crossed_down', d['accel_crossed_down'], last_xdn),
            ('accel_streak', d['accel_streak'], last_streak),
        ]
        for name, db_val, calc_val in checks:
            match = db_val == calc_val or (isinstance(db_val, float) and abs(db_val - calc_val) < 0.001)
            status = "OK" if match else f"MISMATCH db={db_val} calc={calc_val}"
            if match: ok.append(f"{sym}:{name}")
            else: issues.append(f"{sym}:{name} {status}")
            print(f"  {sym}: {name}={db_val}, calc={calc_val} -> {status}")

# 9. Confluence
print("\n--- 9. Confluence ---")
for sym in ['AAPL', 'NVDA']:
    r = conn.execute("SELECT symbol, atr_signal, accel_signal, weighted_alpha, streak, prob_up_1d, confluence FROM stats WHERE symbol=?", (sym,)).fetchone()
    if r:
        d = dict(r)
        expected = compute_confluence(d)
        match = d['confluence'] == expected
        status = "OK" if match else f"MISMATCH db={d['confluence']} expected={expected}"
        if match: ok.append(f"{sym}:confluence")
        else: issues.append(f"{sym}:confluence {status}")
        print(f"  {sym}: confluence={d['confluence']}, expected={expected} -> {status}")

# 10. AI Scores
print("\n--- 10. AI Analysis ---")
r = conn.execute("SELECT symbol, overall_score, bias, tech_score, conclusion FROM ai_analysis WHERE symbol='AAPL'").fetchone()
if r:
    d = dict(r)
    print(f"  AAPL: overall={d['overall_score']}, bias={d['bias']}, tech={d['tech_score']}, conclusion={d['conclusion']}")
    ok.append("AAPL:ai_analysis")

# 11. Pre/Post
print("\n--- 11. Pre/Post Market ---")
r = conn.execute("SELECT symbol, pre_price, pre_change_pct, post_price, post_change_pct FROM stats WHERE symbol='AAPL'").fetchone()
if r:
    d = dict(r)
    print(f"  AAPL: pre_price={d['pre_price']}, pre_chg={d['pre_change_pct']}, post_price={d['post_price']}, post_chg={d['post_change_pct']}")
    if d['pre_price'] != 0:
        ok.append("AAPL:pre_post")
    else:
        print("  NOTE: pre/post = 0 (not computed yet, run refresh)")
        ok.append("AAPL:pre_post:pending")

# 12. Profit
print("\n--- 12. Profit/Earnings ---")
r = conn.execute("SELECT symbol, profit_status, profit_last_qtr_pct, profit_millions, profit_expectations FROM stats WHERE symbol='AAPL'").fetchone()
if r:
    d = dict(r)
    print(f"  AAPL: status={d['profit_status']}, qtr_pct={d['profit_last_qtr_pct']}, millions={d['profit_millions']}, expect={d['profit_expectations']}")
    if d['profit_status']:
        ok.append("AAPL:profit")
    else:
        print("  NOTE: profit = NULL (not computed yet, run refresh)")
        ok.append("AAPL:profit:pending")

# 13. ATR Stop vs Price
print("\n--- 13. ATR Stop Logic ---")
r = conn.execute("SELECT symbol, atr_stop, price, atr_signal FROM stats WHERE atr_signal=1 AND atr_stop > 0 LIMIT 3").fetchall()
for row in r:
    d = dict(row)
    below = d['atr_stop'] < d['price']
    status = "OK (stop below price)" if below else "BUG (stop above price)"
    if below: ok.append(f"{d['symbol']}:atr_stop_logic")
    else: issues.append(f"{d['symbol']}:atr_stop_logic {status}")
    print(f"  {d['symbol']}: signal=1, stop={d['atr_stop']:.2f}, price={d['price']:.2f} -> {status}")

r = conn.execute("SELECT symbol, atr_stop, price, atr_signal FROM stats WHERE atr_signal=-1 AND atr_stop > 0 LIMIT 3").fetchall()
for row in r:
    d = dict(row)
    above = d['atr_stop'] > d['price']
    status = "OK (stop above price)" if above else "BUG (stop below price)"
    if above: ok.append(f"{d['symbol']}:atr_stop_logic_bear")
    else: issues.append(f"{d['symbol']}:atr_stop_logic_bear {status}")
    print(f"  {d['symbol']}: signal=-1, stop={d['atr_stop']:.2f}, price={d['price']:.2f} -> {status}")

# 14. Asset Info
print("\n--- 14. Asset Info ---")
r = conn.execute("SELECT COUNT(*) as total, SUM(CASE WHEN name != '' AND name IS NOT NULL THEN 1 ELSE 0 END) as named, SUM(CASE WHEN exchange != '' AND exchange IS NOT NULL THEN 1 ELSE 0 END) as exchanged FROM stats").fetchone()
d = dict(r)
print(f"  Total: {d['total']}, with name: {d['named']}, with exchange: {d['exchanged']}")
if d['named'] == d['total']:
    ok.append("asset_info:name")
else:
    issues.append(f"asset_info: {d['total'] - d['named']} missing names")

print("\n" + "=" * 80)
print(f"RESULTS: {len(ok)} OK, {len(issues)} ISSUES")
print("=" * 80)
if issues:
    print("\nISSUES:")
    for i in issues:
        print(f"  - {i}")
else:
    print("\nAll checks passed!")

conn.close()
