<!-- tradvisor-v1-backlog:V1-012 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Integration baseline (publication pending): sections/trace 2
- Mapping baseline (publication pending): sections/trace MAP-03
- Architecture baseline (publication pending): sections/trace 8; NFR-01

## Scope
Parse official dated holiday/schedule evidence and trusted date-specific exception input; publish immutable session grid with verified coverage and officialization-plus-60-second cutoff.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `archive/legacy-ingestion/scripts/calendar.py`
- `tests/ingestion/calendar/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Expose calendar entries/version/index to indicators, admission and workers; consume stored notices, not weekday guesses.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Test explicit years, provisional dates, exception precedence, absent historical coverage and normal/exceptional cutoffs.
- [ ] Boundaries at cutoff +/-1 microsecond are consistent; do not infer all holiday-eve closures or certify unknown history.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 6
Domain: ingestion
Blocked by: V1-010 (number pending)
Blocks: V1-013 (number pending), V1-046 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
