<!-- tradvisor-v1-backlog:V1-004 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 8; BRD-A-02
- Api baseline (publication pending): sections/trace 11

## Scope
Generate the complete schema and reproducible TypeScript bindings; provide safe fixture transport for frontend work.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/openapi.py`
- `frontend/src/api/generated/`
- `scripts/generate-client/`
- `tests/contracts/openapi/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume frozen typed routes; expose generated client and fixture adapters. No live cloud wiring.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Regeneration is deterministic and drift fails validation.
- [ ] Type-check every endpoint, money string, nullable metric and recovery-aware command; no handwritten duplicate schema.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 5
Domain: contracts
Blocked by: V1-003 (number pending), V1-055 (number pending)
Blocks: V1-005 (number pending), V1-056 (number pending), V1-057 (number pending), V1-058 (number pending), V1-059 (number pending)

Conflict exclusions (not hard dependencies):
- V1-055 (number pending): `frontend/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
