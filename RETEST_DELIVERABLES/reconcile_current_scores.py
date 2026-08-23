"""Resumable reconciliation script with proper status precedence.

Status precedence (highest to lowest):
1. MODEL_UNAVAILABLE
2. COMPUTATION_ERROR
3. DATA_INSUFFICIENT
4. LEGACY_UNVERSIONED
5. VERSION_MISMATCH
6. MATCH
7. STALE_DB_SCORE
8. MISSING_DB_SCORE
9. VALUE_MISMATCH

Usage:
    python scripts/reconcile_current_scores.py --market US --batch-size 100
    python scripts/reconcile_current_scores.py --market INDIA --resume-run-id <ID>
    python scripts/reconcile_current_scores.py --market US --only-symbols AAPL,MSFT
"""
import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dumbmoney.config import US_DB, INDIA_DB
from dumbmoney.db import get_db
from dumbmoney.retest_config import (
    RETEST_ENGINE_VERSION, RETEST_FEATURE_VERSION, RETEST_SCORE_SEMANTICS_VERSION
)
from dumbmoney.retest_engine import (
    compute_retest_score_current, load_model, get_model, get_model_version
)
from dumbmoney.retest_engine_v2 import normalize_current_retest_score

# ---------------------------------------------------------------------------
# Shadow tables DDL
# ---------------------------------------------------------------------------
RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retest_reconciliation_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    latest_bar_date TEXT,
    model_version TEXT,
    engine_version TEXT,
    feature_version TEXT,
    semantics_version TEXT,
    total_symbols INTEGER DEFAULT 0,
    processed_symbols INTEGER DEFAULT 0,
    model_unavailable_count INTEGER DEFAULT 0,
    computation_error_count INTEGER DEFAULT 0,
    insufficient_data_count INTEGER DEFAULT 0,
    match_count INTEGER DEFAULT 0,
    stale_db_count INTEGER DEFAULT 0,
    missing_db_count INTEGER DEFAULT 0,
    value_mismatch_count INTEGER DEFAULT 0,
    legacy_unversioned_count INTEGER DEFAULT 0,
    version_mismatch_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'RUNNING'
)
"""

ROWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retest_reconciliation_rows (
    run_id INTEGER NOT NULL,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    database_score REAL,
    engine_latest_score REAL,
    latest_non_null_score REAL,
    latest_non_null_index INTEGER,
    latest_non_null_date TEXT,
    latest_bar_date TEXT,
    database_model_version TEXT,
    current_model_version TEXT,
    database_engine_version TEXT,
    current_engine_version TEXT,
    database_feature_version TEXT,
    current_feature_version TEXT,
    database_semantics_version TEXT,
    current_semantics_version TEXT,
    classification TEXT,
    computation_status TEXT,
    error_type TEXT,
    error_message TEXT,
    reconciled_at TEXT,
    PRIMARY KEY (run_id, market, symbol)
)
"""

ROLLBACK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retest_current_score_rollback (
    repair_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    old_score REAL,
    new_score REAL,
    old_score_date TEXT,
    new_score_date TEXT,
    old_model_version TEXT,
    new_model_version TEXT,
    old_engine_version TEXT,
    new_engine_version TEXT,
    backed_up_at TEXT,
    restored_at TEXT,
    PRIMARY KEY (repair_id, run_id, market, symbol)
)
"""


def create_shadow_tables(conn):
    """Create all shadow tables."""
    conn.execute(RUNS_TABLE_SQL)
    conn.execute(ROWS_TABLE_SQL)
    conn.execute(ROLLBACK_TABLE_SQL)
    conn.commit()


def get_latest_bar_date(conn, symbol):
    """Get latest completed bar date for a symbol."""
    row = conn.execute(
        "SELECT MAX(date) FROM bars WHERE timeframe='1Day' AND symbol=?", (symbol,)
    ).fetchone()
    return row[0] if row and row[0] else None


def get_latest_non_null_score(conn, symbol):
    """Get the latest non-null historical score for diagnostics."""
    row = conn.execute(
        "SELECT old_swing_retest_score FROM stats WHERE symbol=? AND old_swing_retest_score IS NOT NULL",
        (symbol,)
    ).fetchone()
    if row and row[0] is not None:
        return row[0], None, None
    return None, None, None


def classify_row(database_score, engine_score, db_model, cur_model,
                 db_engine, cur_engine, db_feature, cur_feature,
                 db_semantics, cur_semantics, latest_bar_date, computation_status):
    """Classify reconciliation status with proper precedence."""
    # 1. MODEL_UNAVAILABLE
    if computation_status == "MODEL_UNAVAILABLE":
        return "MODEL_UNAVAILABLE"

    # 2. COMPUTATION_ERROR
    if computation_status == "COMPUTATION_ERROR":
        return "COMPUTATION_ERROR"

    # 3. DATA_INSUFFICIENT
    if computation_status == "DATA_INSUFFICIENT":
        return "DATA_INSUFFICIENT"

    # 4. LEGACY_UNVERSIONED (no version metadata in DB)
    if db_model is None and db_engine is None and database_score is not None:
        return "LEGACY_UNVERSIONED"

    # 5. VERSION_MISMATCH
    versions_differ = False
    if db_model and db_model != cur_model:
        versions_differ = True
    if db_engine and db_engine != cur_engine:
        versions_differ = True
    if db_feature and db_feature != cur_feature:
        versions_differ = True
    if db_semantics and db_semantics != cur_semantics:
        versions_differ = True
    if versions_differ:
        return "VERSION_MISMATCH"

    # Normalize scores
    db_is_null = database_score is None
    eng_is_null = engine_score is None

    # 6. MATCH
    if db_is_null and eng_is_null:
        return "MATCH"
    if not db_is_null and not eng_is_null:
        if abs(float(database_score) - float(engine_score)) < 0.005:
            return "MATCH"

    # 7. STALE_DB_SCORE
    if not db_is_null and eng_is_null:
        return "STALE_DB_SCORE"

    # 8. MISSING_DB_SCORE
    if db_is_null and not eng_is_null:
        return "MISSING_DB_SCORE"

    # 9. VALUE_MISMATCH
    if not db_is_null and not eng_is_null:
        return "VALUE_MISMATCH"

    return "UNKNOWN"


def reconcile_symbol(conn, market, symbol, current_model_version, current_engine_version,
                     current_feature_version, current_semantics_version):
    """Reconcile a single symbol."""
    try:
        # Get database score
        row = conn.execute(
            "SELECT old_swing_retest_score FROM stats WHERE symbol=?", (symbol,)
        ).fetchone()
        db_score = row[0] if row else None

        # Get latest bar date
        latest_bar_date = get_latest_bar_date(conn, symbol)

        # Get latest non-null for diagnostics
        latest_nn_score, _, _ = get_latest_non_null_score(conn, symbol)

        # Check model availability
        model = get_model()
        if model is None:
            try:
                load_model()
                model = get_model()
            except:
                pass

        if model is None:
            return {
                "symbol": symbol,
                "database_score": db_score,
                "engine_latest_score": None,
                "latest_non_null_score": latest_nn_score,
                "latest_non_null_index": None,
                "latest_non_null_date": None,
                "latest_bar_date": latest_bar_date,
                "database_model_version": None,
                "current_model_version": current_model_version,
                "database_engine_version": None,
                "current_engine_version": current_engine_version,
                "database_feature_version": None,
                "current_feature_version": current_feature_version,
                "database_semantics_version": None,
                "current_semantics_version": current_semantics_version,
                "classification": "MODEL_UNAVAILABLE",
                "computation_status": "MODEL_UNAVAILABLE",
                "error_type": "MODEL_UNAVAILABLE",
                "error_message": "Model artifact not found",
            }

        # Compute engine score
        import pandas as pd
        bars = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM bars "
            "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
            conn, params=(symbol,), parse_dates=["date"]
        )

        if len(bars) < 30:
            return {
                "symbol": symbol,
                "database_score": db_score,
                "engine_latest_score": None,
                "latest_non_null_score": latest_nn_score,
                "latest_non_null_index": None,
                "latest_non_null_date": None,
                "latest_bar_date": latest_bar_date,
                "database_model_version": None,
                "current_model_version": current_model_version,
                "database_engine_version": None,
                "current_engine_version": current_engine_version,
                "database_feature_version": None,
                "current_feature_version": current_feature_version,
                "database_semantics_version": None,
                "current_semantics_version": current_semantics_version,
                "classification": "DATA_INSUFFICIENT",
                "computation_status": "DATA_INSUFFICIENT",
                "error_type": None,
                "error_message": f"Only {len(bars)} bars, need 30",
            }

        try:
            raw_score = compute_retest_score_current(bars)
            engine_score = normalize_current_retest_score(raw_score)
        except Exception as e:
            return {
                "symbol": symbol,
                "database_score": db_score,
                "engine_latest_score": None,
                "latest_non_null_score": latest_nn_score,
                "latest_non_null_index": None,
                "latest_non_null_date": None,
                "latest_bar_date": latest_bar_date,
                "database_model_version": None,
                "current_model_version": current_model_version,
                "database_engine_version": None,
                "current_engine_version": current_engine_version,
                "database_feature_version": None,
                "current_feature_version": current_feature_version,
                "database_semantics_version": None,
                "current_semantics_version": current_semantics_version,
                "classification": "COMPUTATION_ERROR",
                "computation_status": "COMPUTATION_ERROR",
                "error_type": type(e).__name__,
                "error_message": str(e)[:500],
            }

        # Classify
        classification = classify_row(
            db_score, engine_score, None, current_model_version,
            None, current_engine_version, None, current_feature_version,
            None, current_semantics_version, latest_bar_date, "COMPUTED"
        )

        return {
            "symbol": symbol,
            "database_score": db_score,
            "engine_latest_score": engine_score,
            "latest_non_null_score": latest_nn_score,
            "latest_non_null_index": None,
            "latest_non_null_date": None,
            "latest_bar_date": latest_bar_date,
            "database_model_version": None,
            "current_model_version": current_model_version,
            "database_engine_version": None,
            "current_engine_version": current_engine_version,
            "database_feature_version": None,
            "current_feature_version": current_feature_version,
            "database_semantics_version": None,
            "current_semantics_version": current_semantics_version,
            "classification": classification,
            "computation_status": "COMPUTED",
            "error_type": None,
            "error_message": None,
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "database_score": None,
            "engine_latest_score": None,
            "latest_non_null_score": None,
            "latest_non_null_index": None,
            "latest_non_null_date": None,
            "latest_bar_date": None,
            "database_model_version": None,
            "current_model_version": current_model_version,
            "database_engine_version": None,
            "current_engine_version": current_engine_version,
            "database_feature_version": None,
            "current_feature_version": current_feature_version,
            "database_semantics_version": None,
            "current_semantics_version": current_semantics_version,
            "classification": "COMPUTATION_ERROR",
            "computation_status": "COMPUTATION_ERROR",
            "error_type": type(e).__name__,
            "error_message": str(e)[:500],
        }


def run_reconciliation(market, batch_size=100, resume_run_id=None, only_symbols=None, output_dir=None):
    """Run resumable reconciliation for a market."""
    print(f"\n{'='*60}")
    print(f"RECONCILIATION: {market}")
    print(f"{'='*60}")

    conn = get_db(market)
    create_shadow_tables(conn)

    # Get current versions
    try:
        load_model()
        current_model_version = get_model_version()
    except:
        current_model_version = "unknown"

    current_engine_version = RETEST_ENGINE_VERSION
    current_feature_version = RETEST_FEATURE_VERSION
    current_semantics_version = RETEST_SCORE_SEMANTICS_VERSION

    # Get symbols to process
    if only_symbols:
        symbols = [s.strip() for s in only_symbols.split(",")]
    else:
        symbols = [row[0] for row in conn.execute("SELECT symbol FROM stats").fetchall()]

    total = len(symbols)
    print(f"Total symbols: {total}")

    # Create or resume run
    if resume_run_id:
        run_id = resume_run_id
        # Get already processed symbols
        processed = set(row[0] for row in conn.execute(
            "SELECT symbol FROM retest_reconciliation_rows WHERE run_id=? AND market=?",
            (run_id, market)
        ).fetchall())
        print(f"Resuming run {run_id}, already processed: {len(processed)}")
    else:
        cursor = conn.execute(
            """INSERT INTO retest_reconciliation_runs
               (market, started_at, model_version, engine_version, feature_version, semantics_version, total_symbols)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (market, datetime.utcnow().isoformat(), current_model_version, current_engine_version,
             current_feature_version, current_semantics_version, total)
        )
        run_id = cursor.lastrowid
        conn.commit()
        processed = set()
        print(f"Started run {run_id}")

    # Process in batches
    start_time = time.time()
    counts = {
        "MODEL_UNAVAILABLE": 0, "COMPUTATION_ERROR": 0, "DATA_INSUFFICIENT": 0,
        "LEGACY_UNVERSIONED": 0, "VERSION_MISMATCH": 0, "MATCH": 0,
        "STALE_DB_SCORE": 0, "MISSING_DB_SCORE": 0, "VALUE_MISMATCH": 0,
    }

    batch = []
    processed_count = len(processed)

    for i, symbol in enumerate(symbols):
        if symbol in processed:
            continue

        result = reconcile_symbol(
            conn, market, symbol, current_model_version, current_engine_version,
            current_feature_version, current_semantics_version
        )
        result["run_id"] = run_id
        result["market"] = market
        result["reconciled_at"] = datetime.utcnow().isoformat()
        batch.append(result)
        counts[result["classification"]] = counts.get(result["classification"], 0) + 1
        processed_count += 1

        if len(batch) >= batch_size:
            _flush_batch(conn, batch, run_id, market)
            batch = []
            # Update progress
            conn.execute(
                "UPDATE retest_reconciliation_runs SET processed_symbols=? WHERE run_id=?",
                (processed_count, run_id)
            )
            conn.commit()
            elapsed = time.time() - start_time
            rate = processed_count / elapsed if elapsed > 0 else 0
            eta = (total - processed_count) / rate if rate > 0 else 0
            print(f"  {processed_count}/{total} ({processed_count*100//total}%) "
                  f"- {rate:.0f}/s - ETA {eta:.0f}s")

    # Flush remaining
    if batch:
        _flush_batch(conn, batch, run_id, market)

    # Update run stats
    conn.execute("""
        UPDATE retest_reconciliation_runs SET
            completed_at=?, status='COMPLETE',
            processed_symbols=?,
            model_unavailable_count=?, computation_error_count=?, insufficient_data_count=?,
            match_count=?, stale_db_count=?, missing_db_count=?, value_mismatch_count=?,
            legacy_unversioned_count=?, version_mismatch_count=?
        WHERE run_id=?
    """, (
        datetime.utcnow().isoformat(), processed_count,
        counts["MODEL_UNAVAILABLE"], counts["COMPUTATION_ERROR"], counts["DATA_INSUFFICIENT"],
        counts["MATCH"], counts["STALE_DB_SCORE"], counts["MISSING_DB_SCORE"],
        counts["VALUE_MISMATCH"], counts["LEGACY_UNVERSIONED"], counts["VERSION_MISMATCH"],
        run_id
    ))
    conn.commit()

    # Export CSV
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, f"RETEST_CURRENT_SCORE_RECONCILIATION_{market}.csv")
        _export_csv(conn, run_id, market, csv_path)
        print(f"CSV exported: {csv_path}")

    conn.close()

    print(f"\nRun {run_id} COMPLETE")
    print(f"Classifications:")
    for cls, count in sorted(counts.items()):
        if count > 0:
            print(f"  {cls}: {count}")

    return run_id, counts


def _flush_batch(conn, batch, run_id, market):
    """Write a batch of results to the database."""
    for result in batch:
        conn.execute("""
            INSERT OR REPLACE INTO retest_reconciliation_rows
            (run_id, market, symbol, database_score, engine_latest_score,
             latest_non_null_score, latest_non_null_index, latest_non_null_date,
             latest_bar_date, database_model_version, current_model_version,
             database_engine_version, current_engine_version,
             database_feature_version, current_feature_version,
             database_semantics_version, current_semantics_version,
             classification, computation_status, error_type, error_message, reconciled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, market, result["symbol"], result["database_score"],
            result["engine_latest_score"], result["latest_non_null_score"],
            result["latest_non_null_index"], result["latest_non_null_date"],
            result["latest_bar_date"], result["database_model_version"],
            result["current_model_version"], result["database_engine_version"],
            result["current_engine_version"], result["database_feature_version"],
            result["current_feature_version"], result["database_semantics_version"],
            result["current_semantics_version"], result["classification"],
            result["computation_status"], result["error_type"],
            result["error_message"], result["reconciled_at"],
        ))


def _export_csv(conn, run_id, market, csv_path):
    """Export reconciliation results to CSV."""
    rows = conn.execute(
        "SELECT * FROM retest_reconciliation_rows WHERE run_id=? AND market=?",
        (run_id, market)
    ).fetchall()
    if rows:
        cols = [desc[0] for desc in conn.execute(
            "SELECT * FROM retest_reconciliation_rows LIMIT 1"
        ).description]
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            for row in rows:
                writer.writerow(row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resumable reconciliation")
    parser.add_argument("--market", default="US", choices=["US", "INDIA"])
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--resume-run-id", type=int, default=None)
    parser.add_argument("--only-symbols", default=None)
    parser.add_argument("--output-dir", default="RETEST_DELIVERABLES")
    args = parser.parse_args()

    run_id, counts = run_reconciliation(
        args.market, args.batch_size, args.resume_run_id,
        args.only_symbols, args.output_dir
    )
    print(f"\nRun ID: {run_id}")
