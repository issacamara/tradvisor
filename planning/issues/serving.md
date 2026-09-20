<!-- tradvisor-v1-backlog:V1-047 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 5.4,8; NFR-02

## Scope
Copy validated canonical results to bounded immutable serving records and promote one active pointer only after manifest completeness checks.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/publication/analysis.py`
- `tests/publication/analysis/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume canonical batch; expose rebuildable batch-pinned reads. No execution-price timestamp mutation.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Mid-copy failure leaves old batch active; retries complete without mixed versions.
- [ ] Per-stock unavailable states are valid coverage; rebuilding matches canonical evidence and retention dependencies.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 8
Domain: backend
Blocked by: V1-040 (number pending), V1-039 (number pending)
Blocks: V1-048 (number pending), V1-053 (number pending), V1-062 (number pending), V1-063 (number pending), V1-064 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
