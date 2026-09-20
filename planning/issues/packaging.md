<!-- tradvisor-v1-backlog:V1-022 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 6,13; BRD-I-01

## Scope
Register source-specific function artifacts/runtime/resources; include local initialization modules, mapping resources and managed credential references.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `terraform/`
- `archive/legacy-ingestion/scripts/requirements.txt`
- `tests/packaging/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume tested adapter entry points and preservation evidence; expose buildable function definitions. No provisioning.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Import every packaged entry point in the selected runtime; missing local modules fail the build.
- [ ] Existing resource addresses/settings remain preserved; references target only development and contain no secret values.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 9
Domain: infrastructure
Blocked by: V1-008 (number pending), V1-013 (number pending), V1-015 (number pending), V1-016 (number pending), V1-017 (number pending), V1-020 (number pending), V1-021 (number pending)
Blocks: V1-023 (number pending)

Conflict exclusions (not hard dependencies):
- V1-007 (number pending): `terraform/`
- V1-023 (number pending): `terraform/`
- V1-024 (number pending): `terraform/`
- V1-025 (number pending): `terraform/`
- V1-026 (number pending): `terraform/`
- V1-027 (number pending): `terraform/`
- V1-077 (number pending): `terraform/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
