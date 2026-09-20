<!-- tradvisor-v1-backlog:V1-015 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Mapping baseline (publication pending): sections/trace MAP-01,MAP-06
- Financial baseline (publication pending): sections/trace 2,3
- Architecture baseline (publication pending): sections/trace 13; FR-LT-05

## Scope
Extend the existing extraction schema for period/publication/units/scope, matched ordinary-owner earnings/equity, opening balance and non-financial debt/cash/current assets/liabilities where evidenced.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `archive/legacy-ingestion/scripts/financial_normalization.py`
- `tests/ingestion/financial_common/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Expose canonical annual records with supported partial fields; consume recorded source reports.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Five consecutive years and six equity dates are verifiable; missing years/opening balances stay unavailable.
- [ ] Distinguish debt from total liabilities, restricted cash and mismatched owner/consolidation scope; unknown publication time cannot imply point-in-time availability.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 7
Domain: ingestion
Blocked by: V1-014 (number pending), V1-011 (number pending)
Blocks: V1-016 (number pending), V1-017 (number pending), V1-022 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
