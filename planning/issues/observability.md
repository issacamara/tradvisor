<!-- tradvisor-v1-backlog:V1-065 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 9; NFR-05,NFR-08,NFR-09

## Scope
Instrument ingestion/publication/worker failures, backup age, retries and cost drivers with sanitized logs and an operator alert/runbook contract.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/observability/`
- `docs/operations/monitoring.md`
- `tests/observability/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume job/API outcomes; expose minimal actionable telemetry, not a data-quality product.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Logs exclude credentials and unnecessary personal data and respect thirty-day policy.
- [ ] Failed/overdue backups and stale publication are detectable; no keep-alive or automatic five-euro shutdown introduced.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 14
Domain: operations
Blocked by: V1-054 (number pending), V1-062 (number pending), V1-063 (number pending)
Blocks: V1-072 (number pending), V1-077 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
