import type { FixtureTransport } from "./fixture-transport";
import type { components } from "./schema";
const deferredMetric = {
  status: "deferred_scope",
  value: null,
  unit: "score",
  reason_codes: ["dividend_scoring_deferred_v1"],
  evidence_refs: [],
  effective_date: null,
  basis: null,
} satisfies components["schemas"]["SwingRecommendation"]["buy_strength"];

void deferredMetric;

export async function checkAllGeneratedOperations(transport: FixtureTransport) {
  await transport.request({ method: "get", path: "/v1/me" });
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
}
