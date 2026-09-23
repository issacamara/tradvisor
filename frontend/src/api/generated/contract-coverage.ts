import type { FixtureTransport } from "./fixture-transport";
import type { components } from "./schema";

const xofAmount = {
  amount: "1000000.000000",
  currency: "XOF",
} satisfies components["schemas"]["NonNegativeMoney"];

const deferredMetric = {
  status: "deferred_scope",
  value: null,
  unit: "score",
  reason_codes: ["dividend_scoring_deferred_v1"],
  evidence_refs: [],
  effective_date: null,
  basis: null,
} satisfies components["schemas"]["SwingRecommendation"]["buy_strength"];

const recoveryCommand = {
  recovery_id: "restore-1",
  content_length: 120,
  issued_at: "2026-09-23T12:00:00Z",
} satisfies components["schemas"]["CommandMetadataBody"];

void xofAmount;
void deferredMetric;
void recoveryCommand;

export async function checkAllGeneratedOperations(transport: FixtureTransport) {
  await transport.request({ method: "get", path: "/v1/me" });
  await transport.request({
    method: "patch",
    path: "/v1/me/preferences",
    parameters: { header: { "Idempotency-Key": "1726855200000.0123456789abcdef0123456789abcdef" } },
    body: {
      command: {
        recovery_id: "restore-1",
        content_length: 200,
        issued_at: "2026-09-23T12:00:00Z",
      },
      expected_preference_version: 1,
      objective: "growth",
    },
  });
  await transport.request({ method: "get", path: "/v1/swing/recommendations" });
  await transport.request({
    method: "get",
    path: "/v1/long-term/rankings",
    parameters: { query: { objective: "balanced" } },
  });
  await transport.request({
    method: "get",
    path: "/v1/stocks/{symbol}",
    parameters: { path: { symbol: "ABC" } },
  });
  await transport.request({
    method: "get",
    path: "/v1/stocks/{symbol}/chart",
    parameters: {
      path: { symbol: "ABC" },
      query: { from: "2026-01-01", to: "2026-06-30", series: ["ohlcv", "rsi14"] },
    },
  });
  await transport.request({ method: "get", path: "/v1/paper/portfolio" });
  await transport.request({
    method: "post",
    path: "/v1/paper/portfolio",
    parameters: { header: { "Idempotency-Key": "1726855200000.1123456789abcdef0123456789abcdef" } },
    body: {
      command: {
        recovery_id: "restore-1",
        content_length: 180,
        issued_at: "2026-09-23T12:00:00Z",
      },
      starting_cash: { amount: "1000000.000000", currency: "XOF" },
      fee_rate_pct: "1.250000",
    },
  });
  await transport.request({
    method: "post",
    path: "/v1/paper/orders",
    parameters: { header: { "Idempotency-Key": "1726855200000.2123456789abcdef0123456789abcdef" } },
    body: {
      command: {
        recovery_id: "restore-1",
        content_length: 340,
        issued_at: "2026-09-23T12:00:00Z",
        expected_generation: "generation-1",
        expected_state_version: 7,
      },
      expected_generation: "generation-1",
      expected_state_version: 7,
      recommendation_ref: "recommendation-1",
      batch_id: "batch-1",
      symbol: "ABC",
      side: "buy",
      quantity: 10,
      acknowledge_keep_override: false,
    },
  });
  await transport.request({ method: "get", path: "/v1/paper/orders" });
  await transport.request({ method: "get", path: "/v1/paper/executions" });
  await transport.request({ method: "get", path: "/v1/paper/cash-movements" });
  await transport.request({
    method: "post",
    path: "/v1/paper/reset",
    parameters: { header: { "Idempotency-Key": "1726855200000.3123456789abcdef0123456789abcdef" } },
    body: {
      command: {
        recovery_id: "restore-1",
        content_length: 280,
        issued_at: "2026-09-23T12:00:00Z",
        expected_generation: "generation-1",
        expected_state_version: 7,
      },
      expected_generation: "generation-1",
      expected_state_version: 7,
      starting_cash: { amount: "1000000.000000", currency: "XOF" },
    },
  });
}
