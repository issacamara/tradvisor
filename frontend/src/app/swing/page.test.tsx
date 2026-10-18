import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SwingPage from "./page";

const request = vi.fn();

vi.mock("@/features/auth/session", () => ({
  ProtectedWorkspace: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuthSession: () => ({ request }),
}));

const recommendation = {
  symbol: "SAMPLE",
  entry_action: "no_clear_signal",
  buy_strength: { basis: null, effective_date: null, evidence_refs: [], reason_codes: [], status: "assessable", unit: "points", value: 74 },
  eligibility_guards: [],
  indicators: {},
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("SwingPage", () => {
  it("keeps recommendations visible when only the chart is unavailable", async () => {
    request.mockImplementation((path: string) => path.startsWith("/v1/swing/")
      ? Promise.resolve(response({ data: { items: [recommendation], market_session: "2026-10-17" } }))
      : Promise.resolve(response({ error: { code: "analysis_not_ready", message: "Chart is warming", retryable: true } }, 503)));

    render(<SwingPage />);

    expect((await screen.findAllByText("SAMPLE")).length).toBeGreaterThan(0);
    const chartStatus = await screen.findByRole("status");
    expect(chartStatus).toHaveAttribute("data-state", "warming");
    expect(chartStatus).toHaveTextContent("still being prepared");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("uses the publication-wide state when recommendations are unavailable", async () => {
    request.mockResolvedValue(response({ error: { code: "analysis_not_ready", message: "No complete publication", retryable: true } }, 503));

    render(<SwingPage />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveAttribute("data-state", "analysis_not_ready");
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("SAMPLE")).not.toBeInTheDocument();
  });
});
