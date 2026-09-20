<!-- tradvisor-v1-backlog:V1-062 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 5.3,13; ORCH-05,ORCH-07,NFR-07

## Scope
Wire normalized adapters, point-in-time snapshot creation, analysis and independent execution-price publication in a bounded daily job using recorded source fixtures. Wire daily holding projection and eligible pending-order processing after their input readiness, without creating orders.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/jobs/daily.py`
- `tests/integration/daily/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume all source/domain interfaces; expose explicit stage readiness and retry-stable run results.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] End-to-end replay creates a coherent batch with real missing-input states and no paid/source calls.
- [ ] Failures preserve previous publication; unchanged inputs skip redundant work; price availability cannot be backdated by batch completion.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 12
Domain: analysis
Blocked by: V1-023 (number pending), V1-024 (number pending), V1-013 (number pending), V1-016 (number pending), V1-017 (number pending), V1-018 (number pending), V1-019 (number pending), V1-020 (number pending), V1-021 (number pending), V1-047 (number pending), V1-046 (number pending), V1-076 (number pending)
Blocks: V1-065 (number pending), V1-066 (number pending), V1-068 (number pending), V1-069 (number pending), V1-070 (number pending), V1-074 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
