import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { SwingWorkspace } from "@/features/swing/workspace";
import type { components } from "@/api/generated/schema";

vi.mock("@/features/swing/swing-chart", () => ({ SwingChart: () => null }));

type Recommendation = components["schemas"]["SwingRecommendation"];
const score: components["schemas"]["ScoreMetric"] = { basis: null, effective_date: null, evidence_refs: [], reason_codes: [], status: "assessable", unit: "points", value: 74 };
const item: Recommendation = { symbol: "SAMPLE", entry_action: "no_clear_signal", buy_strength: score, eligibility_guards: [{ code: "current_trade", evidence_refs: [], observed: null, status: "unknown", threshold: null }], indicators: {} };

describe("Swing workspace", () => {
  it("keeps market entry evidence visible and never labels a non-buy as sell", () => {
    render(<SwingWorkspace items={[item]} />);
    fireEvent.click(screen.getByRole("button", { name: /SAMPLE no clear signal/ }));
    expect(screen.getAllByText("no clear signal")).toHaveLength(3);
    expect(screen.getByText(/not a Sell instruction/)).toBeInTheDocument();
  });

  it("filters symbols while keeping the selected recommendation available", () => {
    render(<SwingWorkspace items={[item]} selectedSymbol="SAMPLE" />);
    fireEvent.change(screen.getByPlaceholderText("Search symbol"), { target: { value: "OTHER" } });
    expect(screen.getByText("No symbols match this filter.")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "SAMPLE" })).toHaveLength(3);
  });

  it("does not render the removed dated evidence table", () => {
    render(<SwingWorkspace chart={[{ session_date: "2026-09-01", status: "missing_price", open: null, high: null, low: null, close: null, last_traded_close: null, analytical_carried_close: null, indicators: {}, source_evidence: [], volume: null }]} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("missing price")).not.toBeInTheDocument();
  });

  it("does not render backend source attribution in the removed table", () => {
    render(<SwingWorkspace chart={[{ session_date: "2026-09-01", status: "traded", open: null, high: null, low: null, close: null, last_traded_close: null, analytical_carried_close: null, indicators: {}, source_evidence: [{ source_id: "brvm-market-feed", source_url: "https://example.test/source", collected_at: "2026-09-01T16:00:00Z", published_at: "2026-09-01T17:00:00Z", original_unit: null, basis: "actual" }], volume: null }]} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("brvm-market-feed")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "brvm-market-feed" })).not.toBeInTheDocument();
  });

  it("keeps the selected action, strength and date aligned with the chart symbol", () => {
    const selected: Recommendation = { ...item, entry_action: "buy", buy_strength: { ...score, effective_date: "2026-10-30", value: 82 } };
    render(<SwingWorkspace items={[selected]} selectedSymbol="SAMPLE" marketSession="2026-10-30" />);

    expect(screen.getByRole("region", { name: "Selected recommendation summary" })).toHaveTextContent("buy");
    expect(screen.getByRole("region", { name: "Selected recommendation summary" })).toHaveTextContent("82 / 100");
    expect(screen.getByRole("region", { name: "Selected recommendation summary" })).toHaveTextContent("2026-10-30");
    expect(screen.getByLabelText("Chart symbol")).toHaveValue("SAMPLE");
  });

  it("selects the first visible symbol when filtering hides the current selection", async () => {
    const onSymbolChange = vi.fn();
    render(<SwingWorkspace items={[item, { ...item, symbol: "BUY1", entry_action: "buy" }]} selectedSymbol="SAMPLE" onSymbolChange={onSymbolChange} />);

    fireEvent.click(screen.getByRole("button", { name: /Buy 1/ }));

    await waitFor(() => expect(onSymbolChange).toHaveBeenCalledWith("BUY1"));
  });

  it("keeps selection stable for an empty Buy filter and explains a no-Buy publication", () => {
    render(<SwingWorkspace items={[item]} selectedSymbol="SAMPLE" />);

    fireEvent.click(screen.getByRole("button", { name: /Buy 0/ }));

    expect(screen.getByText("No Buy entries in this publication.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Selected recommendation summary" })).toHaveTextContent("SAMPLE");
    expect(screen.getByLabelText("Chart symbol")).toHaveValue("SAMPLE");
  });

  it("shows the published null-score status separately from a search with no matches", () => {
    const unavailable: Recommendation = { ...item, entry_action: "insufficient_data", buy_strength: { ...score, effective_date: null, status: "missing_inputs", value: null } };
    render(<SwingWorkspace items={[unavailable]} selectedSymbol="SAMPLE" />);

    expect(screen.getAllByText("missing inputs").length).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: "Selected recommendation summary" })).toHaveTextContent("Unavailable");
    fireEvent.change(screen.getByPlaceholderText("Search symbol"), { target: { value: "OTHER" } });
    expect(screen.getByText("No symbols match this filter.")).toBeInTheDocument();
    expect(screen.queryByText("No published Swing recommendations yet.")).not.toBeInTheDocument();
  });

  it("moves a removed selection to the first symbol after results refresh", async () => {
    function Harness() {
      const [items, setItems] = useState([item, { ...item, symbol: "NEXT", entry_action: "buy" as const }]);
      const [selected, setSelected] = useState<string | null>("SAMPLE");
      return <><button type="button" onClick={() => setItems([{ ...item, symbol: "NEXT", entry_action: "buy" }])}>Refresh results</button><SwingWorkspace items={items} selectedSymbol={selected} onSymbolChange={setSelected} /></>;
    }

    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh results" }));

    await waitFor(() => expect(screen.getByRole("region", { name: "Selected recommendation summary" })).toHaveTextContent("NEXT"));
    expect(screen.getByLabelText("Chart symbol")).toHaveValue("NEXT");
  });
});
