<!-- tradvisor-v1-backlog:V1-056 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 5.5,9; BRD-A-01,NFR-10

## Scope
Implement email/password verification/reset screens and runtime token handling with explicit unverified/nonadmitted/removed states.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `frontend/src/features/auth/`
- `tests/frontend/auth/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume identity provider and typed /me API via fixture transport; backend remains authorization boundary.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Keyboard/focus and error states work; registration does not imply admission.
- [ ] Email change, stale token and admission removal clear protected views; no tokens in logs or shared caches.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 6
Domain: frontend
Blocked by: V1-055 (number pending), V1-004 (number pending)
Blocks: V1-060 (number pending)

Conflict exclusions (not hard dependencies):
- V1-055 (number pending): `frontend/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
