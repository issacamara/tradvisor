<!-- tradvisor-v1-backlog:V1-041 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 9; BRD-A-01
- Api baseline (publication pending): sections/trace 2

## Scope
Implement token verification, verified-email checks and fail-closed current admin-controlled membership on every protected request and receipt replay.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/auth/`
- `tests/auth/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume Firebase identity and live admission repository; expose verified UID context, not caller-supplied ownership.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test valid-token removal, unverified/nonadmitted identity, email changes and cross-user requests.
- [ ] Registration does not admit; unavailable membership denies access; safe errors and private no-store responses leak no identity records.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 6
Domain: backend
Blocked by: V1-040 (number pending)
Blocks: V1-043 (number pending), V1-052 (number pending), V1-053 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
