"""Fast V2 engine batch runner — processes all symbols, stores results.

Usage:
    python scripts/run_v2_batch.py --market US
    python scripts/run_v2_batch.py --market INDIA
"""
import argparse
import os, sys, time, json, sqlite3
import numpy as np

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dumbmoney.retest_engine_v2 import RetestEngineV2, normalize_current_retest_score, V2State
import dumbmoney.retest_config as cfg

US_DB = os.path.join(project_root, "screener.db")
INDIA_DB = os.path.join(project_root, "india.db")
BATCH_SIZE = 200

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="US", choices=["US", "INDIA"])
    args = parser.parse_args()

    db_path = US_DB if args.market == "US" else INDIA_DB
    market = args.market

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Create V2 results table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS retest_v2_scores (
            symbol TEXT PRIMARY KEY,
            market TEXT NOT NULL,
            current_score REAL,
            original_score REAL,
            latest_state TEXT,
            event_count INTEGER,
            confirmed_this_bar INTEGER,
            model_version TEXT,
            bars_processed INTEGER,
            computed_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS retest_v2_events (
            symbol TEXT,
            event_id TEXT,
            state TEXT,
            breakout_date TEXT,
            breakout_level REAL,
            departure_high_distance_atr REAL,
            pullback_from_peak_atr REAL,
            touch_date TEXT,
            confirm_date TEXT,
            entry_price REAL,
            entry_distance_atr REAL,
            outcome TEXT,
            reason TEXT,
            new_entry_score REAL,
            confirmed_this_bar INTEGER,
            PRIMARY KEY (symbol, event_id)
        )
    """)
    conn.commit()

    # Get all symbols, skip already processed
    all_symbols = [r[0] for r in cur.execute("SELECT symbol FROM stats ORDER BY symbol").fetchall()]
    done_symbols = set(r[0] for r in cur.execute("SELECT symbol FROM retest_v2_scores").fetchall())
    symbols = [s for s in all_symbols if s not in done_symbols]
    total = len(symbols)
    print(f"V2 batch runner: {total} remaining symbols (already done: {len(done_symbols)}), batch_size={BATCH_SIZE}")

    start_time = time.time()
    processed = 0
    errors = 0
    total_events = 0
    confirmed_count = 0
    batch_scores = []
    batch_events = []

    for i, symbol in enumerate(symbols):
        try:
            # Load bars
            rows = cur.execute(
                "SELECT date, open, high, low, close, volume FROM bars "
                "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
                (symbol,)
            ).fetchall()

            if len(rows) < 30:
                processed += 1
                continue

            dates = [r[0] for r in rows]
            open_ = np.array([r[1] for r in rows], dtype=np.float64)
            high = np.array([r[2] for r in rows], dtype=np.float64)
            low = np.array([r[3] for r in rows], dtype=np.float64)
            close = np.array([r[4] for r in rows], dtype=np.float64)
            volume = np.array([r[5] for r in rows], dtype=np.float64)

            # Run V2 engine
            engine = RetestEngineV2(market, symbol)
            result = engine.fold(dates, open_, high, low, close, volume)

            # Extract last bar score
            last_score = result.current_scores[-1] if len(result.current_scores) > 0 else None
            if last_score is not None and np.isnan(last_score):
                last_score = None
            last_score = normalize_current_retest_score(last_score)

            # Get last non-null score and state
            non_nan_mask = ~np.isnan(result.current_scores)
            last_non_nan_idx = np.max(np.where(non_nan_mask)) if np.any(non_nan_mask) else -1
            original_score = float(result.original_scores[last_non_nan_idx]) if last_non_nan_idx >= 0 else None
            latest_state = result.states[-1] if result.states else V2State.NO_BREAKOUT

            # Count confirmed_this_bar events
            confirmed = sum(1 for e in result.events if e.confirmed_this_bar)

            batch_scores.append((
                symbol, market, last_score, original_score, latest_state,
                len(result.events), confirmed, cfg.MODEL_VERSION,
                len(dates), time.strftime("%Y-%m-%dT%H:%M:%S")
            ))

            # Store events (only non-terminal for brevity)
            for e in result.events:
                batch_events.append((
                    symbol, e.event_id, e.state, e.breakout_date,
                    e.breakout_level if not np.isnan(e.breakout_level) else None,
                    e.departure_high_distance_atr if not np.isnan(e.departure_high_distance_atr) else None,
                    e.pullback_from_peak_atr if not np.isnan(e.pullback_from_peak_atr) else None,
                    e.touch_date, e.confirm_date,
                    e.entry if not np.isnan(e.entry) else None,
                    e.entry_distance_atr if not np.isnan(e.entry_distance_atr) else None,
                    e.outcome, e.reason,
                    e.new_entry_score, 1 if e.confirmed_this_bar else 0
                ))

            total_events += len(result.events)
            confirmed_count += confirmed

        except Exception as e:
            errors += 1

        processed += 1

        # Flush batch
        if len(batch_scores) >= BATCH_SIZE:
            cur.executemany(
                "INSERT OR REPLACE INTO retest_v2_scores VALUES (?,?,?,?,?,?,?,?,?,?)",
                batch_scores
            )
            if batch_events:
                cur.executemany(
                    "INSERT OR REPLACE INTO retest_v2_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    batch_events
                )
            conn.commit()
            batch_scores = []
            batch_events = []

            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total - processed) / rate if rate > 0 else 0
            print(f"  {processed}/{total} ({100*processed//total}%) "
                  f"- {rate:.0f}/s - ETA {eta:.0f}s - events:{total_events} confirmed:{confirmed_count} errors:{errors}")

    # Flush remaining
    if batch_scores:
        cur.executemany(
            "INSERT OR REPLACE INTO retest_v2_scores VALUES (?,?,?,?,?,?,?,?,?,?)",
            batch_scores
        )
        if batch_events:
            cur.executemany(
                "INSERT OR REPLACE INTO retest_v2_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                batch_events
            )
        conn.commit()

    elapsed = time.time() - start_time
    print(f"\nCOMPLETE: {processed} symbols in {elapsed:.0f}s ({processed/elapsed:.0f}/s)")
    print(f"  Total events: {total_events}")
    print(f"  Confirmed this bar: {confirmed_count}")
    print(f"  Errors: {errors}")

    conn.close()

if __name__ == "__main__":
    main()
