"""Safe repair script that consumes reconciliation results.

Usage:
    python scripts/repair_current_scores.py --run-id <ID> --dry-run
    python scripts/repair_current_scores.py --run-id <ID> --apply --confirm APPLY_CURRENT_RETEST_REPAIR
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
from dumbmoney.retest_engine import get_model_version

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


def validate_repair_prerequisites(conn, run_id, market):
    """Validate all safety checks before repair."""
    # Check run exists and is COMPLETE
    run = conn.execute(
        "SELECT * FROM retest_reconciliation_runs WHERE run_id=?", (run_id,)
    ).fetchone()
    if not run:
        print(f"ERROR: Run {run_id} not found")
        return False
    if run["status"] != "COMPLETE":
        print(f"ERROR: Run {run_id} status is {run['status']}, need COMPLETE")
        return False
    if run["market"] != market:
        print(f"ERROR: Run {run_id} market is {run['market']}, need {market}")
        return False

    # Check versions still match
    current_model = get_model_version()
    current_engine = RETEST_ENGINE_VERSION
    current_feature = RETEST_FEATURE_VERSION
    current_semantics = RETEST_SCORE_SEMANTICS_VERSION

    if run["model_version"] != current_model:
        print(f"ERROR: Model version changed: {run['model_version']} -> {current_model}")
        return False
    if run["engine_version"] != current_engine:
        print(f"ERROR: Engine version changed: {run['engine_version']} -> {current_engine}")
        return False
    if run["feature_version"] != current_feature:
        print(f"ERROR: Feature version changed: {run['feature_version']} -> {current_feature}")
        return False
    if run["semantics_version"] != current_semantics:
        print(f"ERROR: Semantics version changed: {run['semantics_version']} -> {current_semantics}")
        return False

    # Check no MODEL_UNAVAILABLE rows
    model_unavail = conn.execute(
        "SELECT COUNT(*) FROM retest_reconciliation_rows WHERE run_id=? AND market=? AND classification='MODEL_UNAVAILABLE'",
        (run_id, market)
    ).fetchone()[0]
    if model_unavail > 0:
        print(f"ERROR: {model_unavail} MODEL_UNAVAILABLE rows exist")
        return False

    # Check no COMPUTATION_ERROR rows
    comp_errors = conn.execute(
        "SELECT COUNT(*) FROM retest_reconciliation_rows WHERE run_id=? AND market=? AND classification='COMPUTATION_ERROR'",
        (run_id, market)
    ).fetchone()[0]
    if comp_errors > 0:
        print(f"ERROR: {comp_errors} COMPUTATION_ERROR rows exist")
        return False

    print("All prerequisites validated")
    return True


def get_repair_candidates(conn, run_id, market):
    """Get symbols that need updating."""
    rows = conn.execute("""
        SELECT symbol, database_score, engine_latest_score, latest_bar_date
        FROM retest_reconciliation_rows
        WHERE run_id=? AND market=?
        AND classification IN ('STALE_DB_SCORE', 'MISSING_DB_SCORE', 'VALUE_MISMATCH', 'LEGACY_UNVERSIONED')
        AND computation_status = 'COMPUTED'
    """, (run_id, market)).fetchall()

    candidates = []
    for row in rows:
        candidates.append({
            "symbol": row["symbol"],
            "old_score": row["database_score"],
            "new_score": row["engine_latest_score"],
            "latest_bar_date": row["latest_bar_date"],
        })
    return candidates


def create_rollback_records(conn, repair_id, run_id, market, candidates):
    """Create rollback records before production update."""
    for c in candidates:
        conn.execute("""
            INSERT INTO retest_current_score_rollback
            (repair_id, run_id, market, symbol, old_score, new_score, backed_up_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (repair_id, run_id, market, c["symbol"], c["old_score"], c["new_score"],
              datetime.utcnow().isoformat()))
    conn.commit()

    # Verify count
    count = conn.execute(
        "SELECT COUNT(*) FROM retest_current_score_rollback WHERE repair_id=? AND run_id=? AND market=?",
        (repair_id, run_id, market)
    ).fetchone()[0]
    return count


def apply_repair(conn, run_id, market, candidates):
    """Apply the repair to production stats."""
    success_count = 0
    error_count = 0

    for c in candidates:
        try:
            conn.execute(
                "UPDATE stats SET old_swing_retest_score=? WHERE symbol=?",
                (c["new_score"], c["symbol"])
            )
            success_count += 1
        except Exception as e:
            print(f"  Error updating {c['symbol']}: {e}")
            error_count += 1

    conn.commit()
    return success_count, error_count


def export_rollback_csv(conn, repair_id, run_id, market, output_dir):
    """Export rollback data to CSV."""
    rows = conn.execute(
        "SELECT * FROM retest_current_score_rollback WHERE repair_id=? AND run_id=? AND market=?",
        (repair_id, run_id, market)
    ).fetchall()

    csv_path = os.path.join(output_dir, "RETEST_CURRENT_SCORE_ROLLBACK.csv")
    if rows:
        cols = [desc[0] for desc in conn.execute(
            "SELECT * FROM retest_current_score_rollback LIMIT 1"
        ).description]
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            for row in rows:
                writer.writerow(row)

    return csv_path, len(rows)


def run_repair(run_id, market, dry_run=True, apply=False, confirm=None, output_dir="RETEST_DELIVERABLES"):
    """Run the repair process."""
    print(f"\n{'='*60}")
    print(f"REPAIR: {market} (Run {run_id})")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
    print(f"{'='*60}")

    os.makedirs(output_dir, exist_ok=True)
    conn = get_db(market)

    # Validate prerequisites
    if not validate_repair_prerequisites(conn, run_id, market):
        conn.close()
        return False

    # Get candidates
    candidates = get_repair_candidates(conn, run_id, market)
    print(f"\nRepair candidates: {len(candidates)}")
    if not candidates:
        print("No candidates to repair")
        conn.close()
        return True

    # Show summary
    stale = sum(1 for c in candidates if c["old_score"] is not None and c["new_score"] is None)
    missing = sum(1 for c in candidates if c["old_score"] is None and c["new_score"] is not None)
    mismatch = sum(1 for c in candidates if c["old_score"] is not None and c["new_score"] is not None)
    print(f"  STALE_DB_SCORE: {stale}")
    print(f"  MISSING_DB_SCORE: {missing}")
    print(f"  VALUE_MISMATCH: {mismatch}")

    if dry_run:
        print("\nDRY RUN - No changes made")
        # Show first 10 candidates
        for c in candidates[:10]:
            print(f"  {c['symbol']}: {c['old_score']} -> {c['new_score']}")
        if len(candidates) > 10:
            print(f"  ... and {len(candidates) - 10} more")
        conn.close()
        return True

    # Verify confirmation
    if not apply or confirm != "APPLY_CURRENT_RETEST_REPAIR":
        print("\nERROR: Must pass --apply and --confirm APPLY_CURRENT_RETEST_REPAIR")
        conn.close()
        return False

    # Create rollback records
    repair_id = int(time.time())
    rollback_count = create_rollback_records(conn, repair_id, run_id, market, candidates)
    print(f"\nRollback records created: {rollback_count}")
    if rollback_count != len(candidates):
        print("ERROR: Rollback count mismatch")
        conn.close()
        return False

    # Export rollback CSV
    csv_path, csv_count = export_rollback_csv(conn, repair_id, run_id, market, output_dir)
    print(f"Rollback CSV: {csv_path} ({csv_count} rows)")

    # Apply repair
    print("\nApplying repair...")
    success, errors = apply_repair(conn, run_id, market, candidates)
    print(f"Applied: {success}, Errors: {errors}")

    if errors > 0:
        print("WARNING: Some updates failed")
        # Could rollback here if needed

    conn.close()
    return errors == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Safe repair from reconciliation")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--market", default="US", choices=["US", "INDIA"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default=None)
    parser.add_argument("--output-dir", default="RETEST_DELIVERABLES")
    args = parser.parse_args()

    success = run_repair(
        args.run_id, args.market, args.dry_run, args.apply,
        args.confirm, args.output_dir
    )
    sys.exit(0 if success else 1)
