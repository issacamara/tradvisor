import { describe, expect, it } from "vitest";
import { ApiRequestError } from "@/api/transport";
import type { components } from "@/api/generated/schema";
import { chartAvailability, chartFailureAvailability, chartPublicationAvailability, chartSeries } from "./chart-state";

type ChartPoint = components["schemas"]["ChartPoint"];
const money = (amount: string) => ({ amount, currency: "XOF" as const });
const point = (session_date: string, values: Partial<Pick<ChartPoint, "open" | "high" | "low" | "close">>): ChartPoint => ({
  analytical_carried_close: null, close: null, high: null, last_traded_close: null, low: null, open: null,
  indicators: {}, session_date, source_evidence: [], status: "traded", volume: null, ...values,
});

describe("chart availability", () => {
  it("distinguishes published and empty chart responses", () => {
    expect(chartAvailability([])).toBe("empty");
    expect(chartAvailability([{}])).toBe("published");
  });

  it("keeps a chart-only unavailable response local to the chart", () => {
    expect(chartFailureAvailability(new ApiRequestError(503, "analysis_not_ready", "Not ready", true))).toBe("warming");
    expect(chartFailureAvailability(new ApiRequestError(503, null, "Unavailable", true))).toBe("transport_error");
  });

  it("keeps recommendation publication failures distinct from chart-only states", () => {
    expect(chartPublicationAvailability("unavailable")).toBe("publication_unavailable");
    expect(chartPublicationAvailability("request_failure")).toBe("publication_failure");
  });

  it("uses only published OHLC values for candles and retains missing sessions as gaps", () => {
    const series = chartSeries([
      point("2026-10-01", { open: money("10"), high: money("12"), low: money("9"), close: money("11") }),
      point("2026-10-02", {}),
      point("2026-10-03", { open: money("11"), high: money("13"), low: money("10"), close: money("12") }),
    ]);

    expect(series).toEqual({ mode: "candlestick", data: [
      { time: "2026-10-01", open: 10, high: 12, low: 9, close: 11 },
      { time: "2026-10-02" },
      { time: "2026-10-03", open: 11, high: 13, low: 10, close: 12 },
    ] });
  });

  it("keeps close-only data as a line and does not fill incomplete OHLC", () => {
    const series = chartSeries([
      point("2026-10-01", { close: money("10") }),
      point("2026-10-02", { open: money("10"), close: money("11") }),
      point("2026-10-03", {}),
    ]);

    expect(series).toEqual({ mode: "line", data: [
      { time: "2026-10-01", value: 10 },
      { time: "2026-10-02", value: 11 },
      { time: "2026-10-03" },
    ] });
  });
});
