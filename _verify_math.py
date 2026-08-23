"""P8.2/P8.3: Verify basket and LS calculations independently."""
import sqlite3
import json

def verify_basket_math():
    """Pick one US string, load 10 constituent prices+weights, recalculate basket."""
    conn = sqlite3.connect('screener.db')
    conn.row_factory = sqlite3.Row
    
    # Pick a random string with members
    sids = conn.execute("SELECT id FROM strings LIMIT 5").fetchall()
    if not sids:
        print("No strings found")
        return
    
    for sid_row in sids:
        sid = sid_row[0]
        members = conn.execute(
            "SELECT symbol, weight FROM string_symbols WHERE string_id=?", (sid,)
        ).fetchall()
        if not members:
            continue
        
        print(f"\n=== String {sid} ({len(members)} members) ===")
        symbols = [m['symbol'] for m in members]
        weights = {m['symbol']: m['weight'] for m in members}
        
        # Print weights
        total_w = sum(abs(m['weight']) for m in members)
        print(f"Total |weight|: {total_w:.4f}")
        has_short = any(m['weight'] < 0 for m in members)
        print(f"Has short positions: {has_short}")
        
        # Get latest prices
        for sym in symbols:
            row = conn.execute(
                "SELECT close, volume FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date DESC LIMIT 1",
                (sym,)
            ).fetchone()
            if row:
                price = row['close']
                w = weights[sym]
                contrib = w * price
                print(f"  {sym}: price={price:.2f}, weight={w:.4f}, contribution={contrib:.2f}")
        
        # Get basket metrics from string_screener_metrics
        metrics = conn.execute(
            "SELECT * FROM string_screener_metrics WHERE string_id=?", (sid,)
        ).fetchone()
        if metrics:
            print(f"  Stored price: {metrics['price']:.2f}")
            print(f"  Stored change_pct: {metrics['change_pct']:.2f}%")
            print(f"  Stored weighted_alpha: {metrics['weighted_alpha']:.2f}")
        
        # Verify chart OHLC via the API-like logic
        import pandas as pd
        all_closes = {}
        for sym in symbols:
            rows = conn.execute(
                "SELECT date, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date DESC LIMIT 60",
                (sym,)
            ).fetchall()
            for r in rows:
                if r['date'] not in all_closes:
                    all_closes[r['date']] = {}
                all_closes[r['date']][sym] = r['close']
        
        # Compute basket close for last 5 dates
        sorted_dates = sorted(all_closes.keys())[-5:]
        print(f"\n  Last 5 basket closes (weighted):")
        for dt in sorted_dates:
            bar = all_closes[dt]
            basket_val = sum(weights.get(s, 0) * bar.get(s, 0) for s in symbols if s in bar)
            n_found = sum(1 for s in symbols if s in bar)
            print(f"    {dt}: {basket_val:.2f} ({n_found}/{len(symbols)} constituents)")
        
        break  # Just check one string
    
    conn.close()

def verify_ls_math():
    """Verify LS position math: long UP = gain, short UP = loss."""
    conn = sqlite3.connect('screener.db')
    conn.row_factory = sqlite3.Row
    
    # Find LS strings (negative weights)
    sids = conn.execute(
        "SELECT DISTINCT string_id FROM string_symbols WHERE weight < 0 LIMIT 5"
    ).fetchall()
    if not sids:
        print("\nNo LS strings found")
        return
    
    for sid_row in sids:
        sid = sid_row[0]
        members = conn.execute(
            "SELECT symbol, weight FROM string_symbols WHERE string_id=?", (sid,)
        ).fetchall()
        
        print(f"\n=== LS String {sid} ===")
        longs = [m for m in members if m['weight'] > 0]
        shorts = [m for m in members if m['weight'] < 0]
        print(f"  Longs: {len(longs)}, Shorts: {len(shorts)}")
        
        # Get price changes for each member
        for m in members:
            sym = m['symbol']
            w = m['weight']
            rows = conn.execute(
                "SELECT date, close FROM bars WHERE symbol=? AND timeframe='1Day' ORDER BY date DESC LIMIT 2",
                (sym,)
            ).fetchall()
            if len(rows) >= 2:
                today = rows[0]['close']
                yesterday = rows[1]['close']
                chg_pct = (today / yesterday - 1) * 100
                # PnL contribution: weight * return
                pnl_contrib = w * chg_pct / 100 * 1000  # $1000 allocation
                side = "LONG" if w > 0 else "SHORT"
                expected = "gain" if (w > 0 and chg_pct > 0) or (w < 0 and chg_pct < 0) else "loss"
                print(f"  {sym} ({side}): w={w:.4f}, chg={chg_pct:+.2f}%, PnL contrib=${pnl_contrib:+.2f} ({expected})")
    
    conn.close()

print("=== P8.2: Verify Basket Calculations ===")
verify_basket_math()
print("\n=== P8.3: Verify LS Calculations ===")
verify_ls_math()
