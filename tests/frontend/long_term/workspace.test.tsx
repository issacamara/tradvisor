import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LongTermWorkspace } from "@/features/long_term/workspace";
import type { components } from "@/api/generated/schema";

type Company = components["schemas"]["LongTermRankedCompany"];
const score: components["schemas"]["ScoreMetric"] = { basis: null, effective_date: null, evidence_refs: [], reason_codes: [], status: "assessable", unit: "points", value: 80 };
const company = {
  company_id: "sample", symbol: "SAMPLE",
  growth: { growth_score: score, overall_score: score, advisory_state: "candidate", dimension_contributions: {}, reasons: [] },
  dividend_research: { dividend_score: { ...score, status: "deferred_scope", value: null }, payments: [], coverage: [], trailing_ordinary_yield: null },
} as unknown as Company;

describe("Long-Term workspace", () => {
  it("keeps V1 objectives separate without offering a deferred composite score", () => {
    render(<LongTermWorkspace />);
    expect(screen.queryByRole("tab", { name: /balanced/i })).not.toBeInTheDocument();
    expect(screen.getByText("No published company research yet.")).toBeInTheDocument();
  });

  it("offers dividend facts as a separate research view", () => {
    render(<LongTermWorkspace />);
    fireEvent.click(screen.getByRole("tab", { name: "Dividend research" }));
    expect(screen.getByRole("tab", { name: "Dividend research" })).toHaveAttribute("aria-selected", "true");
  });

  it("uses the selected objective's score status rather than Growth coverage", () => {
    render(<LongTermWorkspace items={[company]} />);
    const row = screen.getByRole("row", { name: /SAMPLE/ });
    expect(within(row).getAllByRole("cell").at(-1)).toHaveTextContent("Complete");
    fireEvent.click(screen.getByRole("tab", { name: "Dividend research" }));
    expect(within(row).getAllByRole("cell").at(-1)).toHaveTextContent("deferred scope");
  });
});
