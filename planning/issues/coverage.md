<!-- tradvisor-v1-backlog:V1-069 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 11,13; ARCH-ASM-07,FR-LT-02

## Scope
Produce an evidence-backed company/category coverage matrix with full/partial/unavailable Growth, current advice, Swing warm-up and blocking semantics.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `docs/validation/coverage.md`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume verified normalized history and results; product owner accepts usefulness, not an invented numeric minimum.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] No private sample uploads, missing-year interpolation, yield-only scores or silent sector removal.
- [ ] Record owner acceptance or explicit scope escalation; source gaps remain visible rather than being waived by unit tests.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 13
Domain: qa
Blocked by: V1-062 (number pending)
Blocks: V1-070 (number pending), V1-074 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
