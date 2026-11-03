import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LongTermPage from "./page";

const request = vi.fn();
vi.mock("@/features/auth/session", () => ({
  ProtectedWorkspace: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuthSession: () => ({ request }),
}));

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const company = { company_id: "FIX1", symbol: "FIX1", growth: { advisory_state: "candidate", annual_dimensions: [], dimension_contributions: {}, growth_score: { basis: null, effective_date: null, evidence_refs: [], reason_codes: [], status: "warming_up", unit: "points", value: null }, overall_score: { basis: null, effective_date: null, evidence_refs: [], reason_codes: [], status: "warming_up", unit: "points", value: null }, reasons: [] }, dividend_research: { coverage: [], dividend_score: { basis: null, effective_date: null, evidence_refs: [], reason_codes: [], status: "deferred_scope", unit: "points", value: null }, payments: [], trailing_ordinary_yield: null }, result: {} };

describe("LongTermPage", () => {
  beforeEach(() => { request.mockReset(); window.history.replaceState(null, "", "/long-term"); });

  it("keeps objective and company deep-link context on reload and selection", async () => {
    window.history.replaceState(null, "", "/long-term?objective=dividend&symbol=FIX1");
    request.mockImplementation(() => Promise.resolve(response({ data: { items: [company], published_at: "2026-10-30" } })));

    render(<LongTermPage />);

    expect(await screen.findByRole("tab", { name: "Dividend research" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "FIX1" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Growth scores" }));
    await waitFor(() => expect(window.location.search).toContain("objective=growth"));
    expect(window.location.search).toContain("symbol=FIX1");
  });

  it("shows retry only for retryable publication errors and renders no stale data", async () => {
    request.mockResolvedValueOnce(response({ error: { code: "analysis_not_ready", message: "No complete publication", retryable: true } }, 503));
    request.mockResolvedValueOnce(response({ data: { items: [company], published_at: "2026-10-30" } }));

    render(<LongTermPage />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveAttribute("data-state", "analysis_not_ready");
    expect(alert).toHaveTextContent("latest analytical publication is not ready yet");
    expect(screen.queryByText("FIX1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "FIX1" })).toBeInTheDocument();
  });
});
