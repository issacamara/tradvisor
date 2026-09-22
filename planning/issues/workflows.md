<!-- tradvisor-v1-backlog:V1-023 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 5.3,6,13; BRD-I-01

## Scope
Replace fragile positional pairing with explicit source-stage dependencies while preserving existing addresses; add only required new schedules in paused state.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `terraform/`
- `tests/infrastructure/workflows/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume packaged extractor/loader contracts; expose bounded authenticated orchestration configuration.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Financial/ratings paths reach their intended persistence stage; unchanged completed runs skip repeated work.
- [ ] Adding a source cannot shift existing workflow identities; failures block dependent publication, new schedules stay paused.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 10
Domain: infrastructure
Blocked by: #57
Blocks: #61, #65

Conflict exclusions (not hard dependencies):
- #8: `terraform/`
- #57: `terraform/`
- #14: `terraform/`
- #15: `terraform/`
- #16: `terraform/`
- #20: `terraform/`
- #77: `terraform/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
