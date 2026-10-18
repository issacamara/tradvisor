import { ApiRequestError } from "@/api/transport";

export type ChartAvailability = "published" | "empty" | "warming" | "transport_error";

export function chartAvailability(points: readonly unknown[]): ChartAvailability {
  return points.length ? "published" : "empty";
}

export function chartFailureAvailability(error: unknown): ChartAvailability {
  return error instanceof ApiRequestError && error.code === "analysis_not_ready"
    ? "warming"
    : "transport_error";
}
