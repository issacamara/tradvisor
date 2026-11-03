import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SwingPage from "./page";
import { SwingChart } from "@/features/swing/swing-chart";

const request = vi.fn();
const { applyOptions, createChart, disconnect, remove, setData } = vi.hoisted(() => ({ applyOptions: vi.fn(), createChart: vi.fn(), disconnect: vi.fn(), remove: vi.fn(), setData: vi.fn() }));
vi.mock("lightweight-charts", () => ({
  CandlestickSeries: {},
  LineSeries: {},
  createChart,
}));

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
const secondRecommendation = {
  ...recommendation,
  symbol: "OTHER",
  entry_action: "buy",
  buy_strength: { ...recommendation.buy_strength, value: 70.4 },
  eligibility_guards: [{ code: "ema20_above_ema50", evidence_refs: ["evidence-1"], observed: 10.125, status: "pass", threshold: 9.75 }],
};
const chartPoint = {
  analytical_carried_close: null, close: { amount: "10.25", currency: "XOF" as const }, high: { amount: "11", currency: "XOF" as const },
  last_traded_close: { amount: "10.25", currency: "XOF" as const }, low: { amount: "9", currency: "XOF" as const }, open: { amount: "10", currency: "XOF" as const },
  indicators: {}, session_date: "2026-10-17", source_evidence: [], status: "traded" as const, volume: 5,
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  request.mockReset();
  applyOptions.mockReset();
  setData.mockReset();
  disconnect.mockReset();
  remove.mockReset();
  createChart.mockReset().mockReturnValue({ addSeries: () => ({ setData }), timeScale: () => ({ fitContent: vi.fn() }), applyOptions, remove });
});
afterEach(() => vi.unstubAllGlobals());

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
    expect(await screen.findByRole("status")).toHaveAttribute("data-state", "publication_unavailable");
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

  it("renders chart loading separately from empty and unavailable states", () => {
    render(<SwingChart points={[]} availability="loading" />);

    expect(screen.getByRole("status")).toHaveAttribute("data-state", "loading");
    expect(screen.getByRole("status")).toHaveTextContent("Loading published price history");
  });

  it("initializes the chart from published data in the client effect and cleans it up", async () => {
    const { unmount } = render(<SwingChart points={[chartPoint]} availability="published" />);

    await waitFor(() => expect(createChart).toHaveBeenCalled());
    expect(setData).toHaveBeenCalledWith([{ time: "2026-10-17", open: 10, high: 11, low: 9, close: 10.25 }]);
    unmount();
    expect(remove).toHaveBeenCalledOnce();
  });

  it("resizes the chart with its pane and disconnects the observer", async () => {
    vi.stubGlobal("ResizeObserver", class {
      constructor(private readonly callback: ResizeObserverCallback) {}
      observe(target: Element) {
        Object.defineProperty(target, "clientWidth", { configurable: true, value: 420 });
        this.callback([], this as unknown as ResizeObserver);
      }
      unobserve() {}
      disconnect() { disconnect(); }
    });
    const { unmount } = render(<SwingChart points={[chartPoint]} availability="published" />);

    await waitFor(() => expect(applyOptions).toHaveBeenCalledWith({ width: 420 }));
    unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  });

  it("keeps chart and guard evidence aligned with the selected recommendation", async () => {
    request.mockImplementation((path?: string) => Promise.resolve(path?.startsWith("/v1/swing/")
      ? response({ data: { items: [recommendation, secondRecommendation], batch_id: "batch-1", input_snapshot_id: "snapshot-1", market_session: "2026-10-17", next_cursor: null, published_at: "2026-10-17T18:00:00Z", rule_version: "v1", strategy_id: "swing-v1" } })
      : response({ data: { points: [chartPoint] } })));

    render(<SwingPage />);
    fireEvent.click(await screen.findByRole("button", { name: /OTHER buy/i }));

    expect(screen.getByRole("region", { name: "Selected recommendation summary" })).toHaveTextContent("OTHER");
    expect(screen.getByRole("region", { name: "Selected recommendation evidence" })).toHaveTextContent("EMA 20 above EMA 50");
    expect(screen.getByText("Observed: 10.125 XOF/share")).toBeInTheDocument();
    expect(screen.getByText("Threshold: 9.75 XOF/share")).toBeInTheDocument();
    await waitFor(() => expect(request).toHaveBeenCalledWith(expect.stringContaining("/v1/stocks/OTHER/chart"), expect.anything()));
    fireEvent.click(screen.getByText("View price data as a table"));
    expect(screen.getByRole("table", { name: "Published prices in XOF per share by session" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /2026-10-17/ })).toHaveTextContent("10.25");
    expect(screen.getByRole("link", { name: "TradingView Lightweight Charts" })).toHaveAttribute("href", "https://www.tradingview.com/lightweight-charts/");
  });

  it("allows keyboard resizing between desktop price and evidence panes", async () => {
    request.mockImplementation((path?: string) => Promise.resolve(path?.startsWith("/v1/swing/")
      ? response({ data: { items: [recommendation], batch_id: "batch-1", input_snapshot_id: "snapshot-1", market_session: "2026-10-17", next_cursor: null, published_at: "2026-10-17T18:00:00Z", rule_version: "v1", strategy_id: "swing-v1" } })
      : response({ data: { points: [] } })));

    render(<SwingPage />);
    await screen.findByRole("heading", { name: "Published recommendations" });
    const handle = screen.getByRole("separator", { name: "Resize price and recommendation evidence panes" });
    expect(handle).toHaveAttribute("tabindex", "0");
    expect(screen.getByText("Use the left and right arrow keys to resize these panes.")).toBeInTheDocument();
  });
});
