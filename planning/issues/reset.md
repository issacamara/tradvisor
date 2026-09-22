<!-- tradvisor-v1-backlog:V1-051 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Integration part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766901291): sections/trace 4
- [Api part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900607), [Api part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900955): sections/trace 5,6,10
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 7; FR-PT-07

## Scope
Persist reset intent, revalidate/fence generation, confirm exclusion, then commit replacement/opening balance/receipt; resume uncertain operations under same ID.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/paper/reset.py`
- `tests/paper/reset/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume register and transactional services; expose reset success only after both stores confirm. No unbounded cleanup in transaction.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Inject failure at every cross-store boundary; cleared generations never become readable or executable.
- [ ] Concurrent resets/fills and retries cannot create multiple generations; cash bounds and preserved fee preferences remain enforced.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 11
Domain: paper
Blocked by: #49, #29, #60
Blocks: #68, #66, #67

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
