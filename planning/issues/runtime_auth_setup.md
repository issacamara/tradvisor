# V1-078: Make static authentication and first-user runtime state durable

## Context

This is the Wave 18 foundation for the approved runtime-data availability amendment in `planning/runtime_data_amendment.md` and architecture sections 5.5, 8, 9 and 13.

## Scope

- Persist Firebase browser sessions across static route navigation and refresh.
- Refresh ID tokens before protected API calls and clear state on sign-out or invalid identity.
- Return a typed `setup_required` state for a verified first user with no preference or paper generation.

## Out of scope

No new financial rules, portfolio tracking, real broker integration, production change, data copy, seeding, schedule activation, or default objective/fee/cash selection.

## Contracts

Consume Firebase Authentication and the existing protected API contract. Expose navigation-safe session state and `setup_required` without changing admission or paper ownership semantics.

## Acceptance criteria

- [ ] Reload and static route navigation preserve a signed-in session and protected requests use a current token.
- [ ] A first verified user receives `setup_required` without a seeded preference document.
- [ ] Tests cover token refresh, auth transitions, missing profile, configured profile and unchanged admission failures.
- [ ] Local CI checks pass for the changed backend and frontend modules.

**Estimate:** M
**Wave:** 18
**GitHub issue:** #169
**Blocked by:** #79 / `V1-074`
**Blocks:** `V1-079`
