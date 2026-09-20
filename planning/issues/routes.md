<!-- tradvisor-v1-backlog:V1-054 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 8; BRD-A-04
- Api baseline (publication pending): sections/trace 2,4,5,7

## Scope
Bind approved service handlers to FastAPI with request limits, safe errors, schema checks and distinct workload-authenticated worker entry points.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/app.py`
- `backend/routes/`
- `tests/api/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume generated contracts and domain services; expose full API without browser fill/admin/cancel/top-up routes.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Every protected route verifies admission; workers require workload identity, not user tokens.
- [ ] End-to-end API fixture covers setup, preferences, order, fill/read and reset; OpenAPI matches generated client.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 13
Domain: backend
Blocked by: V1-053 (number pending), V1-051 (number pending), V1-052 (number pending)
Blocks: V1-061 (number pending), V1-065 (number pending), V1-066 (number pending), V1-068 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
