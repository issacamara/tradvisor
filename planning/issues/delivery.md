<!-- tradvisor-v1-backlog:V1-028 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 13; BRD-A-05

## Scope
Define V1-to-development build and reviewed-plan delivery with immutable artifacts and verified identity trust; no automatic PR apply.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `.github/workflows/deploy.yml`
- `scripts/deployment/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume approved infrastructure definitions and CI artifacts; expose separately gated plan/deploy/activation procedures.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Reject wrong branch/environment/backend; never print plan secrets or use production credentials.
- [ ] Apply, data seed and schedule activation require separate explicit approval; rollback preserves existing resources.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 11
Domain: ci
Blocked by: V1-005 (number pending), V1-023 (number pending), V1-024 (number pending), V1-025 (number pending), V1-026 (number pending), V1-027 (number pending)
Blocks: V1-071 (number pending), V1-074 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
