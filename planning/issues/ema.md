<!-- tradvisor-v1-backlog:V1-030 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Financial baseline (publication pending): sections/trace 6.2,6.3
- Architecture baseline (publication pending): sections/trace 5.4; FR-SW-04

## Scope
Implement exact approved SMA seeding, recursion, mature-chain status and versioned checkpoint correction replay.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/analysis/ema.py`
- `tests/analysis/ema/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume dated analytical closes; expose unrounded EMA20/50 series and seed/basis evidence.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test seed points and 249/250-session maturity; do not reseed a moving window.
- [ ] Incremental and full replay agree within contract tolerance; old published versions remain unchanged.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 5
Domain: analysis
Blocked by: V1-029 (number pending)
Blocks: V1-034 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
