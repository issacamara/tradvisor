<!-- tradvisor-v1-backlog:V1-055 -->
## Context
Tracking epic: EPIC_PENDING
Approved public baseline: BASELINE_PENDING
- Architecture baseline (publication pending): sections/trace 5.5; NFR-04,BRD-A-02

## Scope
Initialize pinned Next.js static export, Tailwind/shadcn, TanStack v8, selected chart libraries and resizable desktop/stacked mobile workspace primitives.

Owned files/modules (new paths are proposed boundaries, not claims that code exists):
- `frontend/`

## Out Of Scope
No changes to approved scoring, scope or contracts; no real portfolio/broker execution, automatic orders, extra indicator families, Dividend/Balanced scoring, or five-year dividend acquisition. No production mutation, secret/user/state cloning, unapproved live queries/provider calls, cloud provisioning, data seeding or schedule activation. Planning/implementation does not grant those permissions.
Private operator evidence must not be committed or pasted into this public issue. Publish only sanitized conclusions.

## Contracts
Expose static routes and reusable accessible shell using local placeholders; no request-time frontend server.
Architecture v1.0; financial v1.1; API v0.13; integration v1.0. Coverage amendments override retained future-version formulas. Escalate conflicting requirements instead of silently changing them.

## Acceptance Criteria
- [ ] Desktop/mobile direct navigation and refresh work; browser-only charts never break prerender.
- [ ] Stable layout/focus/contrast and component version compatibility verified; no private build-time data.
- [ ] Add focused automated tests and report commands/results, or record evidence and owner decisions for review-only work. Missing release evidence is not a passing test.
- [ ] Preserve unrelated work; link delivering PR/evidence against V1 and keep required CI gates. Split before implementation if this exceeds half a day.

## Estimate And Scheduling
Estimate: M (2-4 hours of focused work; not elapsed wait for approvals/evidence).
Wave: 1
Domain: frontend
Blocked by: none
Blocks: V1-004 (number pending), V1-056 (number pending), V1-057 (number pending), V1-058 (number pending), V1-059 (number pending)

Conflict exclusions (not hard dependencies):
- V1-004 (number pending): `frontend/`
- V1-005 (number pending): `frontend/`
- V1-056 (number pending): `frontend/`
- V1-057 (number pending): `frontend/`
- V1-058 (number pending): `frontend/`
- V1-059 (number pending): `frontend/`
- V1-060 (number pending): `frontend/`
- V1-061 (number pending): `frontend/`

Assignment: none. Dispatch is disabled at the stakeholder's request. Before future assignment, verify merged prerequisite artifacts on V1, current state, actual roster and file reservations in the epic. Closure or a wave label alone is not eligibility. Infrastructure plans, provisioning, paid runs, seeding and activation retain separate approval gates.
