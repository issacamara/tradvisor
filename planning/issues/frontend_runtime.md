# V1-081: Connect static workspaces to live analysis data and error states

## Context

This is the Wave 21 frontend integration slice for the approved runtime-data availability amendment in `planning/runtime_data_amendment.md` and architecture sections 5.5, 8, 9 and 13.

## Scope

- Use the generated API client for Swing recommendations, chart data, Long-Term rankings and paper reads.
- Render `setup_required`, `analysis_not_ready`, authentication failures and transport failures distinctly.
- Surface paper refresh failures and preserve equal first-class Swing, Long-Term and manual paper workflows.

## Out of scope

No calculation duplication, new indicator family, portfolio tracking, broker integration, production change, data seeding, or schedule activation.

## Contracts

Consume protected API envelopes and the generated TypeScript client. Expose live data and explicit unavailable states without changing backend financial calculations.

## Acceptance criteria

- [ ] Swing renders recommendations and chart series from API responses rather than hard-coded empty arrays.
- [ ] Long-Term and paper workspaces render published data or explicit unavailable states.
- [ ] Auth, setup, analysis-not-ready and transport states remain distinguishable.
- [ ] Frontend unit, type, build and browser-flow checks pass against contract fixtures.

**Estimate:** M
**Wave:** 21
**GitHub issue:** #172
**Blocked by:** #170, #171
**Blocks:** release acceptance update
