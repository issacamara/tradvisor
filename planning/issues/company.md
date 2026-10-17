<!-- tradvisor-v1-backlog:V1-011 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Mapping part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766901667): sections/trace MAP-01,MAP-02
- [Financial part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900132): sections/trace 2
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 11; DR-01

## Scope
Reuse company discovery and mapping; add reference loading with issuer/class validity, market sector, financial category, provenance and manual corrections.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `archive/legacy-ingestion/scripts/company_reference.py`
- `archive/legacy-ingestion/scripts/mapping.csv`
- `tests/ingestion/company/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume catalog/source evidence; expose company records. Unknown classifications stay unsupported.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Fixtures separate banks, insurers, non-financial and unsupported entities without name-based inference.
- [ ] Historical symbol changes and manual corrections retain sources, dates and identity; all catalog companies remain reachable.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 6
Domain: ingestion
Blocked by: #19
Blocks: #42, #43, #44, #45, #46, #47

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
