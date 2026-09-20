<!-- tradvisor-v1-backlog:V1-014 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 6,11; BRD-I-02
- Mapping baseline (publication pending): sections/trace MAP-06

## Scope
Reuse and consolidate existing acquisition/extraction/loading stages, repair incremental/initialization signatures, persist accepted artifacts and bound retries.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `archive/legacy-ingestion/scripts/scrape_financials.py`
- `archive/legacy-ingestion/scripts/scrape_financials_init.py`
- `archive/legacy-ingestion/scripts/insert_financials.py`
- `tests/ingestion/financial_pipeline/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Consume stored PDFs and recorded provider responses; expose shared extraction adapter. No paid calls or new extraction service.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Empty-table initialization and incremental fixtures both reach canonical load without import side effects.
- [ ] PDF hash/model/prompt/response evidence enables replay without model calls; duplicate retries do not repeat accepted extraction.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 6
Domain: ingestion
Blocked by: V1-010 (number pending)
Blocks: V1-015 (number pending)

Conflict exclusions (not hard dependencies):
none

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
