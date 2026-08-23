# Milestone 1 Handoff Audit

Generated: 2026-08-03T20:03:35

## Event Counts
| Market | Total | Accepted | Rejected |
|--------|-------|----------|----------|
| US | 607531 | 57280 | 550251 |
| INDIA | 311725 | 39512 | 272213 |

## Totals
- Total events: 919256
- Accepted: 96792
- Rejected: 822464

## Accepted State Distribution
- STOPPED_OUT: 69132
- TARGET_COMPLETED: 25106
- EXPIRED: 2110
- POST_ENTRY_ACTIVE: 444

## Rejection State Distribution
- FAILED_BREAKOUT: 557986
- EXPIRED: 86085
- STRUCTURALLY_INVALIDATED: 68481
- ENTRY_TOO_FAR: 51273
- STOPPED_OUT: 29263
- WAITING_FOR_RETURN: 15764
- RECOVERY_FROM_BELOW: 9299
- WAITING_FOR_DEPARTURE: 3191
- BREAKOUT_CONFIRMED: 659
- ACTIVE_RETEST: 359
- TARGET_COMPLETED: 104

## Integrity Assertions
### ALL PASSED
1. Accepted file non-empty: PASS
2. Every accepted row has required fields: PASS
3. Every accepted row confirmed_this_bar=1: PASS
4. No ENTRY_TOO_FAR in accepted: PASS
5. No confirmed events in rejected: PASS
6. No duplicate event_id: PASS
7. No overlapping event_ids between accepted/rejected: PASS