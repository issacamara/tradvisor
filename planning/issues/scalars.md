<!-- tradvisor-v1-backlog:V1-001 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Api part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900607), [Api part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900955): sections/trace 2,3,6,7
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 8; NFR-03

## Scope
Implement typed scalar bounds, money strings, UTC instants, identifiers, errors and recovery-aware command metadata.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/contracts/scalars.py`
- `backend/contracts/envelopes.py`
- `tests/contracts/scalars/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Expose Pydantic scalar/envelope types; consume API v0.13. No routes or persistence.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test int64 overflow, six-digit precision, whole shares and starting-cash bounds.
- [ ] Reject unknown fields, non-finite values and oversized commands; test safe error/envelope serialization.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 2
Domain: contracts
Blocked by: #6
Blocks: #9, #12, #11

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
