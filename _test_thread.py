import sys, time, traceback, sqlite3, os
sys.path.insert(0, 'C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')
os.chdir('C:/Users/Admin/Desktop/stock test/open code v5 claude prompt')

print("Testing update_historical_screener with debug...", flush=True)

try:
    from dumbmoney.engine import _compute_symbol_batch, _compute_historical_symbol_frame, HISTORICAL_SCREENER_COLUMNS
    from dumbmoney.db import get_db
    import pandas as pd
    import numpy as np
    print("Imports OK", flush=True)

    # Manually replicate what update_historical_screener does
    market = "US"
    conn = get_db(market)
    
    # Get all symbols with bars
    max_rows = conn.execute(
        "SELECT symbol, MAX(date) FROM bars WHERE timeframe='1Day' GROUP BY symbol"
    ).fetchall()
    
    # Get existing historical_screener dates
    existing = conn.execute(
        "SELECT symbol, MAX(date) as max_date FROM historical_screener GROUP BY symbol"
    ).fetchall()
    existing_map = {row[0]: row[1] for row in existing}
    
    # Find symbols that need updating
    all_symbols = [row[0] for row in max_rows if existing_map.get(row[0]) != row[1]]
    print(f"Symbols needing update: {len(all_symbols)}", flush=True)
    
    if not all_symbols:
        print("No symbols need updating", flush=True)
        conn.close()
        sys.exit(0)
    
    # Test with just 1 symbol
    test_sym = all_symbols[0]
    print(f"Testing with symbol: {test_sym}", flush=True)
    
    from dumbmoney.config import DB_PATHS
    db_path = DB_PATHS.get(market, DB_PATHS["US"])
    
    # Test _compute_symbol_batch directly with requested=None (our fix)
    batch_args = ([test_sym], db_path, existing_map, None, False, False)
    t0 = time.time()
    records = _compute_symbol_batch(batch_args)
    print(f"  _compute_symbol_batch returned {len(records)} records in {time.time()-t0:.1f}s", flush=True)
    if records:
        print(f"  first: {records[0][:3]}", flush=True)
        print(f"  last: {records[-1][:3]}", flush=True)
    
    # Now test with a small batch through ThreadPoolExecutor
    from concurrent.futures import ThreadPoolExecutor, as_completed
    batch_args_list = [([test_sym], db_path, existing_map, None, False, False)]
    
    print("Testing through ThreadPoolExecutor...", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_compute_symbol_batch, a): a for a in batch_args_list}
        for future in as_completed(futures):
            try:
                result = future.result(timeout=60)
                print(f"  ThreadPool returned {len(result)} records in {time.time()-t0:.1f}s", flush=True)
                if result:
                    print(f"  first: {result[0][:3]}", flush=True)
            except Exception as e:
                print(f"  ThreadPool ERROR: {e}", flush=True)
                traceback.print_exc()
    
    conn.close()
    print("Done", flush=True)

except Exception as e:
    print(f"ERROR: {e}", flush=True)
    traceback.print_exc()
