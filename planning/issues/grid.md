<!-- tradvisor-v1-backlog:V1-029 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Financial baseline (publication pending): sections/trace 2,6.1,6.3
- Architecture baseline (publication pending): sections/trace 5.4,7; NFR-02

## Scope
Implement deterministic session-grid/price-basis selection and known-at joins using synthetic normalized fixtures.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/analysis/inputs.py`
- `tests/analysis/inputs/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume normalized calendar/prices/actions/financial revisions; expose versioned input snapshots independent of live adapters.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] No look-ahead, cross-grain row multiplication, skipped unknown sessions or fabricated candles.
- [ ] Confirmed no-trade carry/zero-TR is explicit; unknown close and unknown TR interrupt only dependent chains.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 4
Domain: analysis
Blocked by: V1-002 (number pending)
Blocks: V1-030 (number pending), V1-031 (number pending), V1-032 (number pending), V1-033 (number pending), V1-035 (number pending), V1-036 (number pending), V1-038 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
