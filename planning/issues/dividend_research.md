<!-- tradvisor-v1-backlog:V1-038 -->
## Context
Tracking epic: https://github.com/issacamara/tradvisor/issues/2
Approved public baseline: https://github.com/issacamara/tradvisor/issues/1
- [Financial part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900132): sections/trace 1,2
- [Api part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900607), [Api part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766900955): sections/trace 3,4
- [Architecture part 1](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766885054), [Architecture part 2](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899249), [Architecture part 3](https://github.com/issacamara/tradvisor/issues/1#issuecomment-5766899584): sections/trace 5.4; FR-LT-01,FR-LT-07

## Scope
Present recorded payments and calculate historical ordinary yield only with verified complete TTM and compatible paid/gross/share basis.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `backend/analysis/dividend_research.py`
- `tests/analysis/dividend_research/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume payment, coverage, adjustment and price fixtures; expose symbol-ordered research facts and deferred score states.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test installments, paid/declared, ordinary/exceptional, exact TTM interval and incomplete coverage.
- [ ] Dividend/Balanced scores always remain null, with no suitability ranking, multiyear inference or automatic activation.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 5
Domain: analysis
Blocked by: #17
Blocks: #48

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
