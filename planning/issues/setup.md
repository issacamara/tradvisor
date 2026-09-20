<!-- tradvisor-v1-backlog:V1-043 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Api baseline (publication pending): sections/trace 4,5
- Architecture baseline (publication pending): sections/trace 7; FR-PT-04

## Scope
Create first generation/opening movement and serialize objective/explicit-fee changes; enforce starting-cash boundaries and no top-ups.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/paper/setup.py`
- `backend/paper/preferences.py`
- `tests/paper/setup/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume identity, repository and receipt helpers; expose setup/preferences service handlers.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test minimum/default/maximum/fractional cash and duplicate setup with no partial writes.
- [ ] Fee zero requires explicit selection; concurrent updates serialize and cannot change existing orders or active starting cash.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 7
Domain: paper
Blocked by: V1-041 (number pending), V1-042 (number pending)
Blocks: V1-048 (number pending), V1-051 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
