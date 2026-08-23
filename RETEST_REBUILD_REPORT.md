# RETEST_REBUILD_REPORT.md — skeleton (PHASE 0)

Status: PHASE 0 (checkpoint, quarantine, call-graph map) — complete 2026-08-01.

## 1. Objective
Repair OLD_SWING_RETEST_SCORE per the 27-section specification (RETEST_AUDIT.md).
Close-entry causal event-state engine; genuine walk-forward ML; NULL semantics;
backtests; full test pipeline. Mandatory phases 0–11.

## 2. Phase log (populated as phases complete)

| Phase | Scope | Status |
|---|---|---|
| 0 | Checkpoint, quarantine, call-graph | DONE |
| 1 | Causal engine + unit tests | PENDING |
| 2 | Close-entry labels | PENDING |
| 3 | Event table, NULL semantics, refresh | PENDING |
| 4 | Causal historical + prefix invariance | PENDING |
| 5 | Feature overhaul + audit | PENDING |
| 6 | Event datasets + golden cases | PENDING |
| 7 | Walk-forward training (after review) | PENDING |
| 8 | Model wiring | PENDING |
| 9 | Backtests | PENDING |
| 10 | Dry-run migration + distribution review | PENDING |
| 11 | Production rebuild + verification | PENDING |

## 3. Checkpoint & quarantine
- git repo initialized (no prior repo existed); .gitignore excludes *.db, models/.
- File backup: `retest_checkpoint_20260801_145606/` (36 files incl. templates + RETEST_AUDIT.md).
- Legacy archive: `legacy/` (6 files + LEGACY_README.md with SHA-256s).
- Model quarantine: `models/retest` -> `models/retest_legacy_v1/` (+ MODEL_LEGACY.md).
- Call graph: `retest_callgraph.md`.

## 4. Verification checklist (spec section Y) — filled at PHASE 11
_..._

## 5. Artifacts (spec section Z) — filled as produced
_..._

## 6. Open decisions / deviations
_..._
