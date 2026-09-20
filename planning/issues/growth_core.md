<!-- tradvisor-v1-backlog:V1-035 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Financial baseline (publication pending): sections/trace 2,3.1,3.2
- Architecture baseline (publication pending): sections/trace 5.4; FR-LT-03,FR-LT-05

## Scope
Implement approved 30-point activity/earnings growth and 25-point profitability/consistency with required history, six equity dates and loss/small-base policies.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/analysis/growth_core.py`
- `tests/analysis/growth_core/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume normalized annual snapshot; expose unrounded dimensions and evidence.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Verify 12/18 allocation, endpoint recovery/loss rules, strict small-base threshold and no missing-year interpolation.
- [ ] Verify ROE 25/15.5 fixtures and nonpositive equity versus unknown; missing terms are not redistributed.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 5
Domain: analysis
Blocked by: V1-029 (number pending)
Blocks: V1-037 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
