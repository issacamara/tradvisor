"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { components } from "@/api/generated/schema";
import type { IChartApi } from "lightweight-charts";
import { chartSeries, type ChartAvailability, type ChartBar, type ChartLinePoint, type ChartWhitespace } from "./chart-state";

type ChartPoint = components["schemas"]["ChartPoint"];
const unavailableMessage: Record<Exclude<ChartAvailability, "published">, string> = {
  loading: "Loading published price history…",
  empty: "No close-price history is available for this stock and period.",
  warming: "Price history is still being prepared for this stock.",
  transport_error: "Price history is temporarily unavailable. Try again shortly.",
  publication_unavailable: "Price history is unavailable because no complete recommendation publication is ready.",
  publication_failure: "Price history could not be requested because recommendations failed to load.",
};

export function SwingChart({ points, availability = "empty" }: { points: ChartPoint[]; availability?: ChartAvailability }) {
  const root = useRef<HTMLDivElement>(null);
  const series = useMemo(() => chartSeries(points), [points]);
  const [range, setRange] = useState("1Y");
  const visiblePoints = useMemo(() => {
    if (!series.data.length || range === "1Y") return series.data;
    const days = { "1W": 7, "1M": 31, "3M": 92 }[range as "1W" | "1M" | "3M"] ?? 92;
    const end = new Date(`${String(series.data.at(-1)!.time)}T00:00:00Z`).getTime();
    const start = end - days * 24 * 60 * 60 * 1000;
    return series.data.filter((point) => new Date(`${String(point.time)}T00:00:00Z`).getTime() >= start);
  }, [series, range]);
  const summary = useMemo(() => {
    const values = visiblePoints.flatMap((point) => "value" in point && typeof point.value === "number" ? [point.value] : "close" in point && typeof point.close === "number" ? [point.close] : []);
    const highs = series.mode === "candlestick" ? visiblePoints.flatMap((point) => "high" in point && typeof point.high === "number" ? [point.high] : []) : values;
    const lows = series.mode === "candlestick" ? visiblePoints.flatMap((point) => "low" in point && typeof point.low === "number" ? [point.low] : []) : values;
    const latest = values.at(-1) ?? null;
    const previous = values.at(-2) ?? null;
    return {
      latest,
      change: latest !== null && previous !== null ? latest - previous : null,
      changePercent: latest !== null && previous ? ((latest - previous) / previous) * 100 : null,
      high: highs.length ? Math.max(...highs) : null,
      low: lows.length ? Math.min(...lows) : null,
    };
  }, [series.mode, visiblePoints]);

  useEffect(() => {
    let disposed = false;
    let chart: IChartApi | null = null;
    let observer: ResizeObserver | null = null;
    async function mount() {
      if (!root.current || !visiblePoints.length) return;
      const { CandlestickSeries, LineSeries, createChart } = await import("lightweight-charts");
      if (disposed || !root.current) return;
      chart = createChart(root.current, { width: Math.max(1, root.current.clientWidth), height: 260, layout: { background: { color: "#171d1d" }, textColor: "#aab9b5", attributionLogo: true }, grid: { vertLines: { color: "#303a38" }, horzLines: { color: "#303a38" } }, rightPriceScale: { borderColor: "#303a38" }, timeScale: { borderColor: "#303a38", timeVisible: false } });
      if (series.mode === "candlestick") {
        chart.addSeries(CandlestickSeries, { upColor: "#39bf91", downColor: "#ef6a6a", borderUpColor: "#39bf91", borderDownColor: "#ef6a6a", wickUpColor: "#39bf91", wickDownColor: "#ef6a6a" }).setData(visiblePoints as (ChartBar | ChartWhitespace)[]);
      } else {
        chart.addSeries(LineSeries, { color: "#3d7cff", lineWidth: 2, title: "Close price", crosshairMarkerVisible: true }).setData(visiblePoints as (ChartLinePoint | ChartWhitespace)[]);
      }
      chart.timeScale().fitContent();
      observer = new ResizeObserver(() => { if (root.current && chart) chart.applyOptions({ width: Math.max(1, root.current.clientWidth) }); });
      observer.observe(root.current);
    }
    void mount();
    return () => { disposed = true; observer?.disconnect(); chart?.remove(); };
  }, [visiblePoints, series.mode]);

  const displayAvailability = availability === "published" && summary.latest === null ? "empty" : availability;
  const ready = displayAvailability === "published" && summary.latest !== null;
  return <section aria-label="Stock price history" className="chart-workspace">
    <div className="chart-toolbar"><div><span className="eyebrow">{series.mode === "candlestick" ? "OPEN · HIGH · LOW · CLOSE" : "CLOSE PRICE"}</span><div className="chart-value"><strong>{summary.latest === null ? "—" : summary.latest.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong><span>XOF</span>{summary.change !== null && <span className={`price-change ${summary.change >= 0 ? "positive" : "negative"}`}>{summary.change >= 0 ? "+" : "−"}{Math.abs(summary.change).toLocaleString(undefined, { maximumFractionDigits: 2 })} XOF</span>}{summary.changePercent !== null && <span className={`price-change ${summary.changePercent >= 0 ? "positive" : "negative"}`}>{summary.changePercent >= 0 ? "+" : ""}{summary.changePercent.toFixed(2)}%</span>}</div></div>
      <div className="segmented" role="group" aria-label="Chart period">{["1W", "1M", "3M", "1Y"].map((option) => <button key={option} type="button" aria-pressed={range === option} onClick={() => setRange(option)}>{option}</button>)}</div>
    </div>
    {ready ? <div className="chart-canvas" ref={root} aria-label={`${series.mode === "candlestick" ? "Open, high, low and close" : "Close price"} chart by trading session`} role="img" aria-describedby="swing-chart-alternative"><span className="sr-only">{series.mode === "candlestick" ? "Candlestick chart" : "Close-price line chart"}. Exact values are available in the price data table below.</span></div> : <div className="chart-empty" role="status" data-state={displayAvailability}>{unavailableMessage[displayAvailability === "published" ? "empty" : displayAvailability]}</div>}
    <div className="chart-footer"><span>Last session <strong>{String(visiblePoints.at(-1)?.time ?? "—")}</strong></span><span>High <strong>{summary.high === null ? "—" : summary.high.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong> XOF</span><span>Low <strong>{summary.low === null ? "—" : summary.low.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong> XOF</span></div>
    <details id="swing-chart-alternative" className="chart-data"><summary>View price data as a table</summary><div className="table-scroll"><table className="data-table"><caption>Published prices in XOF per share by session</caption><thead><tr><th scope="col">Session</th><th scope="col">Open</th><th scope="col">High</th><th scope="col">Low</th><th scope="col">Close</th><th scope="col">Status</th></tr></thead><tbody>{points.map((point) => <tr key={point.session_date}><th scope="row">{point.session_date}</th>{[point.open, point.high, point.low, point.close].map((price, index) => <td key={index}>{price?.amount ?? "—"}</td>)}<td>{point.status.replaceAll("_", " ")}</td></tr>)}</tbody></table></div></details>
    <p className="chart-attribution">Charts by <a href="https://www.tradingview.com/lightweight-charts/" target="_blank" rel="noreferrer">TradingView Lightweight Charts</a></p>
  </section>;
}
