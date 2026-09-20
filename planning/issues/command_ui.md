<!-- tradvisor-v1-backlog:V1-060 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Api baseline (publication pending): sections/trace 5,6
- Architecture baseline (publication pending): sections/trace 5.5; FR-PT-01,FR-PT-04,FR-PT-07

## Scope
Implement setup/explicit fee, manual recommendation-linked order with Keep acknowledgment, preferences and confirmed reset using one key per intent.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `frontend/src/features/paper/commands/`
- `tests/frontend/paper_commands/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume generated mutation APIs and runtime recovery metadata; refresh authoritative state after success.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Timeout retries reuse key; generation/recovery/stale recommendation requires fresh explicit confirmation, never automatic replacement.
- [ ] Validate cash/quantity/fee fields and reset visibility; keyboard/focus flows work and no optimistic fill appears.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 7
Domain: frontend
Blocked by: V1-056 (number pending), V1-059 (number pending), V1-057 (number pending)
Blocks: V1-061 (number pending)

Conflict exclusions (not hard dependencies):
- V1-055 (number pending): `frontend/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
