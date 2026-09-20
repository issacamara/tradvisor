<!-- tradvisor-v1-backlog:V1-034 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 5.4; FR-SW-01,FR-SW-02,FR-SW-03,FR-SW-05,FR-SW-07

## Scope
Compose approved 20+20+30+30 contributions, unrounded threshold and independent liquidity/current-trade/structural guards behind one stable strategy interface.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/analysis/swing.py`
- `backend/analysis/rules/swing_v1.json`
- `tests/analysis/swing/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume mature indicator snapshot; expose shared entry results and immutable rule/evidence references.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test curve endpoints/interiors and score 70 equality; rounding cannot promote eligibility.
- [ ] Reject flat/falling EMA despite score 80 and extension >=3 despite score 70; failure to Buy never implies Sell.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 6
Domain: analysis
Blocked by: V1-030 (number pending), V1-031 (number pending), V1-032 (number pending), V1-033 (number pending)
Blocks: V1-039 (number pending), V1-045 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
