import { ApiRequestError } from "@/api/transport";
import type { components } from "@/api/generated/schema";
import type { Time } from "lightweight-charts";

type ChartPoint = components["schemas"]["ChartPoint"];
export type ChartAvailability = "published" | "empty" | "loading" | "warming" | "transport_error" | "publication_unavailable" | "publication_failure";
export type ChartBar = { time: Time; open: number; high: number; low: number; close: number };
export type ChartLinePoint = { time: Time; value: number };
export type ChartWhitespace = { time: Time };
export type ChartSeries = { mode: "candlestick"; data: Array<ChartBar | ChartWhitespace> } | { mode: "line"; data: Array<ChartLinePoint | ChartWhitespace> };

export function chartAvailability(points: readonly unknown[]): ChartAvailability {
  return points.length ? "published" : "empty";
}

export function chartFailureAvailability(error: unknown): ChartAvailability {
  return error instanceof ApiRequestError && error.code === "analysis_not_ready"
    ? "warming"
    : "transport_error";
}

export function chartPublicationAvailability(state: "published" | "loading" | "no_publication" | "unavailable" | "request_failure"): ChartAvailability {
  switch (state) {
    case "loading": return "loading";
    case "no_publication":
    case "published": return "empty";
    case "unavailable": return "publication_unavailable";
    case "request_failure": return "publication_failure";
  }
}

export function chartSeries(points: readonly ChartPoint[]): ChartSeries {
  const closes = points.map((point) => point.close === null ? null : Number(point.close.amount));
  const useCandles = points.some((point) => point.open !== null || point.high !== null || point.low !== null)
    && points.every((point) => point.close === null || (point.open !== null && point.high !== null && point.low !== null));

  if (useCandles) return {
    mode: "candlestick",
    data: points.map((point, index) => {
      const close = closes[index];
      if (close === null) return { time: point.session_date as Time };
      return { time: point.session_date as Time, open: Number(point.open!.amount), high: Number(point.high!.amount), low: Number(point.low!.amount), close };
    }),
  };

  return {
    mode: "line",
    data: points.map((point, index) => closes[index] === null
      ? { time: point.session_date as Time }
      : { time: point.session_date as Time, value: closes[index]! }),
  };
}
