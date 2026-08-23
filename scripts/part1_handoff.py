"""Part 1: Fix Milestone 1 handoff — regenerate accepted/rejected event files from V2 batch output."""
import os, sys, json, time, hashlib
import sqlite3
import pandas as pd
import numpy as np

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

OUTPUT_DIR = os.path.join(project_root, "MILESTONE2_DELIVERABLES")
os.makedirs(OUTPUT_DIR, exist_ok=True)

REJECTED_STATES = {
    "FAILED_BREAKOUT", "RECOVERY_FROM_BELOW", "STRUCTURALLY_INVALIDATED",
    "ENTRY_TOO_FAR", "EXPIRED", "NO_BREAKOUT"
}

def load_events(db_path, market):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM retest_v2_events", conn)
    conn.close()
    df["market"] = market
    return df

def classify_events(df):
    """Accepted = confirmed_this_bar=1. Rejected = everything else."""
    accepted = df[df["confirmed_this_bar"] == 1].copy()
    rejected = df[df["confirmed_this_bar"] != 1].copy()
    return accepted, rejected

def validate_accepted(accepted, market):
    errors = []
    # 1. Non-empty
    if len(accepted) == 0:
        errors.append(f"{market}: Accepted events is EMPTY")
    # 2. Required columns
    required = ["symbol", "event_id", "breakout_date", "breakout_level", "state"]
    for col in required:
        if col not in accepted.columns:
            errors.append(f"{market}: Missing column {col}")
    # 3. All confirmed_this_bar=1
    if (accepted["confirmed_this_bar"] != 1).any():
        errors.append(f"{market}: Non-confirmed rows in accepted")
    # 4. No ENTRY_TOO_FAR in accepted
    if (accepted["state"] == "ENTRY_TOO_FAR").any():
        errors.append(f"{market}: ENTRY_TOO_FAR in accepted")
    # 5. No duplicate event_id
    dupes = accepted["event_id"].duplicated().sum()
    if dupes > 0:
        errors.append(f"{market}: {dupes} duplicate event_ids in accepted")
    return errors

def validate_rejected(rejected, accepted, market):
    errors = []
    # 1. No rejected event emitted a new-entry score (confirmed_this_bar=1)
    if (rejected["confirmed_this_bar"] == 1).any():
        errors.append(f"{market}: Confirmed events in rejected")
    # 2. No overlap with accepted
    overlap = set(rejected["event_id"]) & set(accepted["event_id"])
    if len(overlap) > 0:
        errors.append(f"{market}: {len(overlap)} overlapping event_ids")
    return errors

def main():
    all_errors = []
    all_accepted = []
    all_rejected = []

    for db_name, market in [("screener.db", "US"), ("india.db", "INDIA")]:
        db_path = os.path.join(project_root, db_name)
        print(f"Loading {market} events from {db_name}...")
        df = load_events(db_path, market)
        print(f"  Total: {len(df)}")

        accepted, rejected = classify_events(df)
        print(f"  Accepted: {len(accepted)}, Rejected: {len(rejected)}")

        errs = validate_accepted(accepted, market)
        all_errors.extend(errs)
        errs = validate_rejected(rejected, accepted, market)
        all_errors.extend(errs)

        all_accepted.append(accepted)
        all_rejected.append(rejected)

    accepted_all = pd.concat(all_accepted, ignore_index=True)
    rejected_all = pd.concat(all_rejected, ignore_index=True)

    # Cross-market validation
    dupes = accepted_all["event_id"].duplicated().sum()
    if dupes > 0:
        all_errors.append(f"Cross-market: {dupes} duplicate event_ids")

    # Save
    accepted_all.to_parquet(os.path.join(OUTPUT_DIR, "RETEST_V2_ACCEPTED_EVENTS.parquet"), index=False)
    accepted_all.to_csv(os.path.join(OUTPUT_DIR, "RETEST_V2_ACCEPTED_EVENTS.csv"), index=False)
    rejected_all.to_parquet(os.path.join(OUTPUT_DIR, "RETEST_V2_REJECTED_EVENTS.parquet"), index=False)
    rejected_all.to_csv(os.path.join(OUTPUT_DIR, "RETEST_V2_REJECTED_EVENTS.csv"), index=False)

    # Funnel: all events with classification
    accepted_all["classification"] = "ACCEPTED"
    rejected_all["classification"] = "REJECTED"
    funnel = pd.concat([accepted_all, rejected_all], ignore_index=True)
    funnel.to_parquet(os.path.join(OUTPUT_DIR, "RETEST_V2_FUNNEL.parquet"), index=False)
    funnel.to_csv(os.path.join(OUTPUT_DIR, "RETEST_V2_FUNNEL.csv"), index=False)

    # Handoff audit
    audit_lines = [
        "# Milestone 1 Handoff Audit",
        f"\nGenerated: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"\n## Event Counts",
        f"| Market | Total | Accepted | Rejected |",
        f"|--------|-------|----------|----------|",
    ]
    for db_name, market in [("screener.db", "US"), ("india.db", "INDIA")]:
        acc = accepted_all[accepted_all["market"] == market]
        rej = rejected_all[rejected_all["market"] == market]
        total = len(acc) + len(rej)
        audit_lines.append(f"| {market} | {total} | {len(acc)} | {len(rej)} |")

    audit_lines.append(f"\n## Totals")
    audit_lines.append(f"- Total events: {len(funnel)}")
    audit_lines.append(f"- Accepted: {len(accepted_all)}")
    audit_lines.append(f"- Rejected: {len(rejected_all)}")

    # State distribution in accepted
    audit_lines.append(f"\n## Accepted State Distribution")
    for state, cnt in accepted_all["state"].value_counts().items():
        audit_lines.append(f"- {state}: {cnt}")

    # Rejection reasons (state distribution in rejected)
    audit_lines.append(f"\n## Rejection State Distribution")
    for state, cnt in rejected_all["state"].value_counts().items():
        audit_lines.append(f"- {state}: {cnt}")

    # Integrity assertions
    audit_lines.append(f"\n## Integrity Assertions")
    if all_errors:
        audit_lines.append("### FAILED")
        for e in all_errors:
            audit_lines.append(f"- FAIL: {e}")
    else:
        audit_lines.append("### ALL PASSED")
        audit_lines.append("1. Accepted file non-empty: PASS")
        audit_lines.append("2. Every accepted row has required fields: PASS")
        audit_lines.append("3. Every accepted row confirmed_this_bar=1: PASS")
        audit_lines.append("4. No ENTRY_TOO_FAR in accepted: PASS")
        audit_lines.append("5. No confirmed events in rejected: PASS")
        audit_lines.append("6. No duplicate event_id: PASS")
        audit_lines.append("7. No overlapping event_ids between accepted/rejected: PASS")

    audit_text = "\n".join(audit_lines)
    with open(os.path.join(OUTPUT_DIR, "RETEST_V2_HANDOFF_AUDIT.md"), "w") as f:
        f.write(audit_text)

    print(f"\nSaved to {OUTPUT_DIR}")
    print(f"  Accepted: {len(accepted_all)}")
    print(f"  Rejected: {len(rejected_all)}")
    if all_errors:
        print(f"  ERRORS: {len(all_errors)}")
        for e in all_errors:
            print(f"    {e}")
    else:
        print("  All integrity assertions PASSED")

if __name__ == "__main__":
    main()
