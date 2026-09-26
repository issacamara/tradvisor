import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SwingWorkspace } from "@/features/swing/workspace";
import type { components } from "@/api/generated/schema";

vi.mock("@/features/swing/swing-chart", () => ({ SwingChart: () => null }));

type Recommendation = components["schemas"]["SwingRecommendation"];
const score: components["schemas"]["ScoreMetric"] = { basis: null, effective_date: null, evidence_refs: [], reason_codes: [], status: "assessable", unit: "points", value: 74 };
const item: Recommendation = { symbol: "SAMPLE", entry_action: "no_clear_signal", buy_strength: score, eligibility_guards: [{ code: "current_trade", evidence_refs: [], observed: null, status: "unknown", threshold: null }], holding_advice: { action: "not_applicable", evaluation_session: null, exit_policy_version: null, generation: null, reasons: [], state_version: null, unavailable_checks: [] }, indicators: {} };

describe("Swing workspace", () => {
  it("keeps market entry separate from holding advice and never labels a non-buy as sell", () => {
    render(<SwingWorkspace items={[item]} />);
    fireEvent.click(screen.getByRole("button", { name: "SAMPLE" }));
    expect(screen.getAllByText("no clear signal")).toHaveLength(2);
    expect(screen.getAllByText("not applicable")).toHaveLength(2);
    expect(screen.getByText(/not a Sell instruction/)).toBeInTheDocument();
  });

  it("renders missing price evidence without fabricating a candle", () => {
    render(<SwingWorkspace chart={[{ session_date: "2026-09-01", status: "missing_price", open: null, high: null, low: null, close: null, last_traded_close: null, analytical_carried_close: null, indicators: {}, source_evidence: [], volume: null }]} />);
    expect(screen.getByText("missing price")).toBeInTheDocument();
    expect(screen.getAllByText("—", { exact: true }).length).toBeGreaterThan(0);
  });
});
