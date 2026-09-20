<!-- tradvisor-v1-backlog:V1-048 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Api baseline (publication pending): sections/trace 5
- Architecture baseline (publication pending): sections/trace 7; FR-PT-01,FR-PT-03,FR-PT-05

## Scope
Validate current recommendation/advice against latest completed session, state and recovery; reserve cash/shares and create pending order and receipt atomically.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/paper/accept.py`
- `tests/paper/accept/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume current batch/calendar, holding advice and receipt services; expose pending-order creation, never a fill.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test Buy eligibility, fresh Keep override acknowledgment and server-derived immutable evidence; stale advice requires reconfirmation.
- [ ] Concurrent orders cannot reuse funds/shares; intended session is strictly after acceptance date and following-session deadline is frozen.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 9
Domain: paper
Blocked by: V1-043 (number pending), V1-045 (number pending), V1-047 (number pending), V1-046 (number pending)
Blocks: V1-049 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
