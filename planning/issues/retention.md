<!-- tradvisor-v1-backlog:V1-063 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 9; NFR-09
- Api baseline (publication pending): sections/trace 10

## Scope
Implement bounded retryable old-generation deletion, receipt expiry and analytical evidence lifecycle while preserving active references and register exclusions.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/jobs/retention.py`
- `tests/retention/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume manifests, active generations and recovery inventory; expose cleanup results and blocked deletion reasons.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Reset operational data deleted within seven days; receipts/log policy thirty days and recommendation policy twelve months.
- [ ] Active calculation/position evidence and any exclusion protecting restorable copies survive generic expiry; unknown cleanup eligibility retains protection.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 12
Domain: backend
Blocked by: V1-051 (number pending), V1-047 (number pending), V1-050 (number pending)
Blocks: V1-065 (number pending), V1-066 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
