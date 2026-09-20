<!-- tradvisor-v1-backlog:V1-013 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Mapping baseline (publication pending): sections/trace MAP-01,MAP-04
- Architecture baseline (publication pending): sections/trace 6; NFR-01, DR-01

## Scope
Verify session and zero-volume meaning against source evidence; preserve decimal parsing, raw OHLC, individual-share volume, revisions and trade-status uncertainty.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `archive/legacy-ingestion/scripts/scrape_shares.py`
- `archive/legacy-ingestion/scripts/insert_shares.py`
- `tests/ingestion/shares/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume issuer/session schemas and load helpers; expose normalized price revisions, not execution availability.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Holiday/retry collection never relabels an old session; localized decimals retain supported precision.
- [ ] Unknown zero-volume OHLC never authorize carry, modeled ATR or fills; missing/duplicate/revised observations retain explicit evidence.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 7
Domain: ingestion
Blocked by: V1-011 (number pending), V1-012 (number pending)
Blocks: V1-022 (number pending), V1-046 (number pending), V1-062 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
