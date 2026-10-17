<!-- tradvisor-v1-backlog:V1-066 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Integration part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766901291): sections/trace 5
- [Api part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900607), [Api part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900955): sections/trace 10
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 7; NFR-02,NFR-03

## Scope
Exercise the complete protocol fault matrix across emulator/storage fakes with deterministic scheduling and every reset/access boundary.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `tests/integration/races/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume delivered services; expose regression evidence without changing policies.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Race publication/invalidation/calendar changes against fills and expiry; confirm one terminal effect.
- [ ] Crash reset/removal/re-admission, partial scans and cleanup with surviving restored copies; no resurrection or false success.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 14
Domain: qa
Blocked by: #68, #67, #66, #65
Blocks: #76, #79

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
