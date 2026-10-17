<!-- tradvisor-v1-backlog:V1-026 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 4,9; BRD-A-03,NFR-05

## Scope
Define request-billed Cloud Run API with min zero, finite jobs/retries and narrowly scoped new identities and secret references.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `terraform/`
- `backend/Dockerfile`
- `tests/infrastructure/runtime/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Expose runtime deployment contract and private parameter inputs; no keep-alives or production trust copying.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Validate zero minimum instances, bounded timeouts/results/retries and explicit development-only targets.
- [ ] No Cloud SQL/VM/permanent capacity; existing IAM membership and resources are not silently removed.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 6
Domain: infrastructure
Blocked by: #10
Blocks: #61, #77

Conflict exclusions (not hard dependencies):
- #8: `terraform/`
- #57: `terraform/`
- #59: `terraform/`
- #14: `terraform/`
- #15: `terraform/`
- #20: `terraform/`
- #77: `terraform/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
