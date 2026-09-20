<!-- tradvisor-v1-backlog:V1-007 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 9,12,13; BRD-A-05

## Scope
Restore compatible declarations and explicit development backend guidance using verified private ownership; retain resource addresses, schedules and existing access.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `terraform/`
- `README.md`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume ownership checklist; expose preservation-only configuration. No backend migration, state removal, apply or key rotation.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Terraform formatting and offline validation pass.
- [ ] Configuration preserves legacy resources and avoids timestamp-driven key churn or authoritative IAM membership loss; document exceptions for review.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 2
Domain: infrastructure
Blocked by: V1-006 (number pending)
Blocks: V1-008 (number pending)

Conflict exclusions (not hard dependencies):
- V1-022 (number pending): `terraform/`
- V1-023 (number pending): `terraform/`
- V1-024 (number pending): `terraform/`
- V1-025 (number pending): `terraform/`
- V1-026 (number pending): `terraform/`
- V1-027 (number pending): `terraform/`
- V1-077 (number pending): `terraform/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
