<!-- tradvisor-v1-backlog:V1-057 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 5.5; FR-SW-01,FR-SW-03,FR-SW-04,NFR-10

## Scope
Use typed fixtures to build table, candlestick/volume and EMA/RSI/ATR/traded-value panels with dated evidence, explanations and separate holding advice.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `frontend/src/features/swing/`
- `tests/frontend/swing/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume generated read models; expose selection/detail and order intent handoff, no frontend calculations.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Verify chart lifecycle/resizing/date alignment, missing candles, basis labels and required attribution.
- [ ] Mobile and keyboard/table alternatives work; score is strength not probability and no-clear-Buy never becomes Sell.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 6
Domain: frontend
Blocked by: V1-055 (number pending), V1-004 (number pending)
Blocks: V1-060 (number pending), V1-061 (number pending)

Conflict exclusions (not hard dependencies):
- V1-055 (number pending): `frontend/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
