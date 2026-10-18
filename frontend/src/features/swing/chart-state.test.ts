import { describe, expect, it } from "vitest";
import { ApiRequestError } from "@/api/transport";
import { chartAvailability, chartFailureAvailability } from "./chart-state";

describe("chart availability", () => {
  it("distinguishes published and empty chart responses", () => {
    expect(chartAvailability([])).toBe("empty");
    expect(chartAvailability([{}])).toBe("published");
  });

  it("keeps a chart-only unavailable response local to the chart", () => {
    expect(chartFailureAvailability(new ApiRequestError(503, "analysis_not_ready", "Not ready", true))).toBe("warming");
    expect(chartFailureAvailability(new ApiRequestError(503, null, "Unavailable", true))).toBe("transport_error");
  });
});
