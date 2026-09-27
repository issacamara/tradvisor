# V1-080: Publish daily analytical results from BigQuery to Firestore atomically

## Context

This is the Wave 20 publication slice for the approved runtime-data availability amendment in `planning/runtime_data_amendment.md` and architecture sections 5.2, 5.3, 5.4, 7, 9 and 13.

## Scope

- Implement the concrete daily worker behind the existing job protocol.
- Read one named BigQuery input snapshot, invoke versioned calculators once, and persist immutable analytical evidence.
- Write a complete Firestore serving copy and promote the active pointer only after completion.
- Make retries idempotent by input/session/rule identity.

## Out of scope

No cloud job execution, paid query, schedule activation, data seeding, migration, production mutation, or change to the selected financial rules.

## Contracts

Consume normalized BigQuery snapshots and rule configuration. Expose a batch publication manifest, immutable serving outputs and a complete-or-previous active pointer transition.

## Acceptance criteria

- [ ] Complete publication, no-publication, retry, partial-write recovery and unavailable-company outputs are tested.
- [ ] A partial batch is never visible and a failed publication leaves the previous active pointer unchanged.
- [ ] Repeated input/session/rule identity is idempotent without duplicate serving documents.
- [ ] Local CI checks pass without external cloud credentials or paid queries.

**Estimate:** L
**Wave:** 20
**GitHub issue:** #171
**Blocked by:** #170
**Blocks:** `V1-081`
