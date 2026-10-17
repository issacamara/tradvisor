<!-- tradvisor-v1-backlog:V1-025 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 5.5,9; BRD-A-01,BRD-A-02

## Scope
Define development static hosting and email/password identity configuration, route refresh behavior and verified redirect/origin settings.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `terraform/`
- `firebase.json`
- `tests/infrastructure/hosting/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Expose static-host/auth configuration; consume private verified environment parameters. No users or live activation.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] No SSR/Server Actions, embedded private data or production redirect targets.
- [ ] Exported workspace deep links resolve; identity registration does not itself grant application admission.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 5
Domain: infrastructure
Blocked by: #10
Blocks: #61

Conflict exclusions (not hard dependencies):
- #8: `terraform/`
- #57: `terraform/`
- #59: `terraform/`
- #14: `terraform/`
- #16: `terraform/`
- #20: `terraform/`
- #77: `terraform/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
