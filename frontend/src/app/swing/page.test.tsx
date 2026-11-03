import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

beforeEach(() => request.mockReset());

describe("SwingPage", () => {
  it("keeps recommendations visible when only the chart is unavailable", async () => {
    request.mockImplementation((path?: string) => {
      return path?.startsWith("/v1/swing/")
      ? Promise.resolve(response({ data: { items: [recommendation], batch_id: "batch-1", input_snapshot_id: "snapshot-1", market_session: "2026-10-17", next_cursor: null, published_at: "2026-10-17T18:00:00Z", rule_version: "v1", strategy_id: "swing-v1" } }))
      : Promise.resolve(response({ error: { code: "analysis_not_ready", message: "Chart is warming", retryable: true } }, 503));
    });

    render(<SwingPage />);

    expect((await screen.findAllByText("SAMPLE")).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByRole("status")).toHaveAttribute("data-state", "warming"));
    expect(screen.getByRole("status")).toHaveTextContent("still being prepared");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("uses the publication-wide state when recommendations are unavailable", async () => {
    request.mockResolvedValue(response({ error: { code: "analysis_not_ready", message: "No complete publication", retryable: true } }, 503));

    render(<SwingPage />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveAttribute("data-state", "analysis_not_ready");
    expect(screen.getByText("The latest analytical publication is unavailable.")).toBeInTheDocument();
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("SAMPLE")).not.toBeInTheDocument();
    expect(screen.queryByText("No published Swing recommendations yet.")).not.toBeInTheDocument();
  });

  it("distinguishes a successful empty publication from an unavailable publication", async () => {
    request.mockResolvedValue(response({ data: { items: [], batch_id: "batch-1", input_snapshot_id: "snapshot-1", market_session: "2026-10-17", next_cursor: null, published_at: "2026-10-17T18:00:00Z", rule_version: "v1", strategy_id: "swing-v1" } }));

    render(<SwingPage />);

    expect(await screen.findByText("No published Swing recommendations yet.")).toBeInTheDocument();
    expect(screen.queryByText("The latest analytical publication is unavailable.")).not.toBeInTheDocument();
  });

  it("shows a request failure separately from an empty publication", async () => {
    request.mockResolvedValue(response({ error: { code: "upstream_unavailable", message: "Private upstream detail", retryable: false } }, 503));

    render(<SwingPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Swing recommendations could not be loaded. Try again later.");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.queryByText("No published Swing recommendations yet.")).not.toBeInTheDocument();
  });

  it("retries an explicitly retryable recommendation failure and clears the failure on success", async () => {
    request.mockResolvedValueOnce(response({ error: { code: "analysis_not_ready", message: "No complete publication", retryable: true } }, 503));
    request.mockImplementation((path?: string) => Promise.resolve(path?.startsWith("/v1/swing/")
      ? response({ data: { items: [recommendation], batch_id: "batch-1", input_snapshot_id: "snapshot-1", market_session: "2026-10-17", next_cursor: null, published_at: "2026-10-17T18:00:00Z", rule_version: "v1", strategy_id: "swing-v1" } })
      : response({ data: { points: [] } })));

    render(<SwingPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "Published recommendations" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Selected recommendation summary" })).toHaveTextContent("SAMPLE");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("does not offer retry for a non-retryable recommendation failure", async () => {
    request.mockResolvedValue(response({ error: { code: "analysis_not_ready", message: "No complete publication", retryable: false } }, 503));

    render(<SwingPage />);

    expect(await screen.findByRole("alert")).toHaveAttribute("data-state", "analysis_not_ready");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});
