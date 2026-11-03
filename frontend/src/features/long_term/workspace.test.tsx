import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LongTermWorkspace } from "./workspace";
import type { components } from "@/api/generated/schema";

type Company = components["schemas"]["LongTermRankedCompany"];
type Payment = components["schemas"]["NormalizedDividend"];
const metric = (status: components["schemas"]["ScoreMetric"]["status"], value: number | null): components["schemas"]["ScoreMetric"] => ({ basis: "actual", effective_date: null, evidence_refs: [], reason_codes: [], status, unit: "points", value });

const payment = (dividend_id: string, payment_date: string, gross: string | null, net: string | null): Payment => ({
  company_id: "FIX3", dividend_id, installment_id: dividend_id, dividend_type: "ordinary", fiscal_period_end: "2024-12-31",
  gross_amount_per_share: gross === null ? null : { amount: gross, currency: "XOF" }, gross_total_amount: null,
  net_amount_per_share: net === null ? null : { amount: net, currency: "XOF" }, net_total_amount: null,
  payment_date, payment_status: "paid", per_share_semantics: "gross", total_semantics: "unknown", reason_codes: [], revision: {} as unknown as components["schemas"]["Revision"],
});

function company(symbol: string, growthStatus: components["schemas"]["ScoreMetric"]["status"] = "assessable", growthValue: number | null = 74.2): Company {
  return {
    company_id: symbol,
    symbol,
    growth: {
      advisory_state: "candidate",
      annual_dimensions: [
        { fiscal_year: 2025, revenue: 1_240_000_000, earnings: 184_000_000, profitability: 14.8 },
        { fiscal_year: 2024, revenue: null, earnings: -12_000_000, profitability: null },
      ],
      dimension_contributions: { revenue_growth: metric("assessable", 22), profitability: metric("missing_inputs", null) },
      growth_score: metric(growthStatus, growthValue),
      overall_score: metric(growthStatus, growthValue),
      reasons: [],
    },
    dividend_research: {
      coverage: [],
      dividend_score: metric("deferred_scope", null),
      payments: [],
      trailing_ordinary_yield: null,
    },
    result: { company_id: symbol, revision: {} as unknown as Company["result"]["revision"], growth: { objective: "growth", overall_score: metric(growthStatus, growthValue) } as Company["result"]["growth"], dividend: { objective: "dividend", overall_score: metric("deferred_scope", null) } as Company["result"]["dividend"], balanced: { objective: "balanced", overall_score: metric("deferred_scope", null) } as Company["result"]["balanced"] },
  };
}

describe("LongTermWorkspace", () => {
  it("keeps separate tabs, selected company context, and annual evidence", () => {
    const onObjectiveChange = vi.fn();
    const onSymbolChange = vi.fn();
    const items = [company("FIX1"), company("FIX2", "warming_up", null)];
    render(<LongTermWorkspace items={items} publishedAt="2026-10-30" onObjectiveChange={onObjectiveChange} onSymbolChange={onSymbolChange} />);

    expect(screen.getByRole("heading", { name: "FIX1" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Annual revenue and earnings/ })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Published annual revenue, earnings and profitability" })).toHaveTextContent("Revenue · XOF");
    expect(screen.getByRole("table", { name: "Published annual revenue, earnings and profitability" })).toHaveTextContent(/1.240.000.000\sXOF/);
    expect(screen.getByRole("table", { name: "Published annual revenue, earnings and profitability" })).toHaveTextContent("Not reported");
    expect(screen.getByText("revenue growth")).toBeInTheDocument();
    expect(screen.getByText("profitability")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /FIX2/ }));
    expect(onSymbolChange).toHaveBeenCalledWith("FIX2");
    expect(screen.getAllByText("warming up").length).toBeGreaterThan(0);
    fireEvent.keyDown(screen.getByRole("tab", { name: "Growth scores" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Dividend research" })).toHaveAttribute("aria-selected", "true");
    expect(onObjectiveChange).toHaveBeenCalledWith("dividend");
    expect(screen.getByRole("heading", { name: "FIX2" })).toBeInTheDocument();
    expect(screen.getAllByText("deferred scope").length).toBeGreaterThan(0);
    expect(screen.getByText(/Dividend and Balanced composite scores/)).toBeInTheDocument();
    expect(screen.getByText("No dividend payment facts supplied.")).toBeInTheDocument();
    expect(screen.queryByText(/trailing yield/i)).not.toBeInTheDocument();
  });

  it("shows only supplied dividend coverage and payment facts", () => {
    const sample = company("FIX3");
    sample.dividend_research.coverage = [{ company_id: "FIX3", coverage_basis: "fiscal_year", coverage_status: "partial", covered_interval_start: "2024-01-01", covered_interval_end: "2024-12-31", payment_outcome: "payments_recorded", reason_codes: [], revision: {} as unknown as components["schemas"]["Revision"] }];
    sample.dividend_research.payments = [payment("div1", "2025-03-01", "125", "100"), payment("div2", "2025-04-01", "80", null), payment("div3", "2025-05-01", null, null), payment("div4", "2025-06-01", null, "90")];
    render(<LongTermWorkspace items={[sample]} objective="dividend" publishedAt="2026-10-30" />);

    expect(screen.getByRole("table", { name: "Published dividend evidence coverage" })).toHaveTextContent("partial");
    const paymentTable = screen.getByRole("table", { name: "Recorded dividend payment facts" });
    expect(paymentTable).toHaveTextContent("Gross / share · XOF");
    expect(paymentTable).toHaveTextContent("Net / share · XOF");
    const grossAndNet = within(screen.getByRole("row", { name: /Mar 1, 2025/ })).getAllByRole("cell");
    const grossOnly = within(screen.getByRole("row", { name: /Apr 1, 2025/ })).getAllByRole("cell");
    const noAmounts = within(screen.getByRole("row", { name: /May 1, 2025/ })).getAllByRole("cell");
    const netOnly = within(screen.getByRole("row", { name: /Jun 1, 2025/ })).getAllByRole("cell");
    expect(grossAndNet[1]).toHaveTextContent("125 XOF");
    expect(grossAndNet[2]).toHaveTextContent("100 XOF");
    expect(grossOnly[1]).toHaveTextContent("80 XOF");
    expect(grossOnly[2]).toHaveTextContent("Not reported");
    expect(noAmounts[1]).toHaveTextContent("Not reported");
    expect(noAmounts[2]).toHaveTextContent("Not reported");
    expect(netOnly[1]).toHaveTextContent("Not reported");
    expect(netOnly[2]).toHaveTextContent("90 XOF");
    expect(screen.getByText(/Dividend and Balanced composite scores/)).toBeInTheDocument();
  });
});
