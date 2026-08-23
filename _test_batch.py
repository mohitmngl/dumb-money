import sys, time, traceback, sqlite3
print("Testing _compute_symbol_batch directly...", flush=True)

try:
    from dumbmoney.engine import _compute_symbol_batch, _compute_historical_symbol_frame
    import pandas as pd
    print("Import OK", flush=True)

    conn = sqlite3.connect('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', timeout=15)
    conn.execute('PRAGMA busy_timeout=10000')

    # Get AAPL bars
    bars = pd.read_sql("SELECT symbol, date, open, high, low, close, volume FROM bars WHERE timeframe='1Day' AND symbol='AAPL' ORDER BY date", conn)
    print(f"AAPL bars: {len(bars)} rows, date range {bars['date'].iloc[0]} to {bars['date'].iloc[-1]}", flush=True)

    # Test _compute_historical_symbol_frame directly
    t0 = time.time()
    hist = _compute_historical_symbol_frame(bars)
    print(f"_compute_historical_symbol_frame: {len(hist)} rows in {time.time()-t0:.1f}s", flush=True)
    print(f"  date range: {hist['date'].iloc[0]} to {hist['date'].iloc[-1]}", flush=True)
    print(f"  columns: {list(hist.columns)}", flush=True)

    # Test _compute_symbol_batch with requested=None (full rebuild path)
    existing_map = {}
    batch_args = (['AAPL'], 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', existing_map, None, False, False)
    t0 = time.time()
    records = _compute_symbol_batch(batch_args)
    print(f"_compute_symbol_batch(requested=None): {len(records)} records in {time.time()-t0:.1f}s", flush=True)
    if records:
        print(f"  first record date: {records[0][1]}", flush=True)
        print(f"  last record date: {records[-1][1]}", flush=True)

    # Test with requested=['AAPL'] and existing date
    existing_map2 = {'AAPL': '2026-07-21'}
    batch_args2 = (['AAPL'], 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt/screener.db', existing_map2, ['AAPL'], False, False)
    t0 = time.time()
    records2 = _compute_symbol_batch(batch_args2)
    print(f"_compute_symbol_batch(requested=['AAPL'], last=2026-07-21): {len(records2)} records in {time.time()-t0:.1f}s", flush=True)
    if records2:
        print(f"  date range: {records2[0][1]} to {records2[-1][1]}", flush=True)

    conn.close()
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    traceback.print_exc()
