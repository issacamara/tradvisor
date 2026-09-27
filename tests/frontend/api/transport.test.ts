import { describe, expect, it, vi } from "vitest";
import { ApiRequestError, createApiTransport } from "@/api/transport";

describe("generated API transport", () => {
  it("encodes repeated chart series parameters", async () => {
    const request = vi.fn(async (path: string) => {
      expect(path).toContain("series=ohlcv");
      expect(path).toContain("series=rsi14");
      return Response.json({ data: {} });
    });

    await createApiTransport(request).request({
      method: "get",
      path: "/v1/stocks/{symbol}/chart",
      parameters: {
        path: { symbol: "ABC" },
        query: { from: "2026-01-01", to: "2026-09-27", series: ["ohlcv", "rsi14"] },
      },
    });
    expect(request).toHaveBeenCalledOnce();
  });

  it("preserves typed API error state", async () => {
    const request = async () => Response.json(
      { error: { code: "analysis_not_ready", message: "No publication", retryable: true } },
      { status: 503 },
    );

    await expect(createApiTransport(request).request({ method: "get", path: "/v1/swing/recommendations" }))
      .rejects.toEqual(expect.objectContaining<ApiRequestError>({ status: 503, code: "analysis_not_ready", retryable: true }));
  });
});
