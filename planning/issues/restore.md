<!-- tradvisor-v1-backlog:V1-064 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Integration baseline (publication pending): sections/trace 4,5
- Api baseline (publication pending): sections/trace 10
- Architecture baseline (publication pending): sections/trace 9; NFR-08

## Scope
Implement stopped-writer reconciliation, complete register scan, fresh recovery identifier, exclusions/admission reapplication and once-only rejection of restored pending orders.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/recovery/restore.py`
- `tests/recovery/restore/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume isolated restored state and independent register; expose reopening checks, never infer missing ledger effects.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Old database/worker routing must be isolated before reopen; fresh keys with old recovery IDs fail before replay.
- [ ] Missing inventory blocks globally, inconsistent accounts block locally; terminal orders stay terminal and restored pending reservations release once.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 12
Domain: backend
Blocked by: V1-051 (number pending), V1-052 (number pending), V1-049 (number pending), V1-047 (number pending)
Blocks: V1-066 (number pending), V1-071 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
