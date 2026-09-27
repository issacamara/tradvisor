# V1-079: Wire the API to the active analytical serving batch

## Context

This is the Wave 19 API composition slice for the approved runtime-data availability amendment in `planning/runtime_data_amendment.md` and architecture sections 5.4, 5.7, 8, 9 and 13.

## Scope

- Compose repositories, publication state and the analytical read service in the FastAPI factory.
- Replace unconditional analysis placeholders with bounded batch-pinned reads for Swing, Long-Term, stock detail and chart responses.
- Preserve typed `analysis_not_ready` when no complete publication is available.

## Out of scope

No BigQuery job execution, data seeding, schedule activation, production mutation, frontend redesign, or financial-rule changes.

## Contracts

Consume immutable analytical batches and active publication state. Expose existing API envelopes and bounded reads without launching BigQuery in request handling.

## Acceptance criteria

- [ ] The packaged API starts with the dependency graph used by tests and production entry points.
- [ ] All four analysis routes read the active batch and return contract-conformant envelopes.
- [ ] Missing publication, stale batch, ownership, pagination and malformed-symbol cases are tested.
- [ ] No route contains an unconditional placeholder 503 handler.

**Estimate:** L
**Wave:** 19
**Blocked by:** `V1-078` and the merged repository/serving contracts
**Blocks:** `V1-080`, `V1-081`
