<!-- tradvisor-v1-backlog:V1-053 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Api part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900607), [Api part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900955): sections/trace 4,7
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 8; NFR-06,NFR-07

## Scope
Implement endpoint readers and signed opaque cursors pinned to analytical batch or owner/generation/state, with exact-money and incomplete valuation handling.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/read_api/`
- `tests/read_api/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume serving/store/holding services; expose generated API read contracts. No BigQuery work on interactive reads.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test 50/100 pagination, 1000-session charts, stale/expired cursors, state changes and missing batches.
- [ ] No cross-user/shared-cache leaks or mixed generations/batches; unpriced holdings cannot appear as zero or complete valuation.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 12
Domain: backend
Blocked by: #36, #56, #50, #60, #63
Blocks: #68

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
