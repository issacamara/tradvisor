<!-- tradvisor-v1-backlog:V1-045 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 7; FR-SW-06
- [Financial part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900132): sections/trace 6.4

## Scope
Implement fixed loss, latched trailing, technical and duration checks from historical position state and shared indicators; preserve frozen exit-policy references.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/paper/holding_advice.py`
- `tests/paper/holding_advice/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume position/session/indicator snapshots; expose generation/state-bound Keep/Sell/insufficient advice. No automatic orders.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test 95%,108%,96%, EMA equality, RSI45, session0/29/30/31 and partial availability with independent Sell.
- [ ] Additional buys/partial sells preserve timer/high/activation/policy; no retroactive activation, synthetic new high or reset resurrection.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 7
Domain: paper
Blocked by: #11, #34, #12
Blocks: #58, #64, #63

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
