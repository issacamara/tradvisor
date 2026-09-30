"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { components } from "@/api/generated/schema";
import type { IChartApi, Time } from "lightweight-charts";

type ChartPoint = components["schemas"]["ChartPoint"];
const numeric = (value: { amount: string } | null) => value === null ? null : Number(value.amount);

export function SwingChart({ points }: { points: ChartPoint[] }) {
  const root = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [range, setRange] = useState("1Y");
  const closePoints = useMemo(() => points.flatMap((point) => {
    const value = numeric(point.close);
    return value === null ? [] : [{ date: point.session_date, time: point.session_date as Time, value }];
  }), [points]);
  const visiblePoints = useMemo(() => {
    if (!closePoints.length || range === "1Y") return closePoints;
    const days = { "1D": 1, "1W": 7, "1M": 31, "3M": 92 }[range as "1D" | "1W" | "1M" | "3M"] ?? 92;
    const end = new Date(`${closePoints.at(-1)!.date}T00:00:00Z`).getTime();
    const start = end - days * 24 * 60 * 60 * 1000;
    return closePoints.filter((point) => new Date(`${point.date}T00:00:00Z`).getTime() >= start);
  }, [closePoints, range]);
  const summary = useMemo(() => {
    const values = visiblePoints.map((point) => point.value);
    const latest = values.at(-1) ?? null;
    const previous = values.at(-2) ?? null;
    return {
      latest,
      change: latest !== null && previous !== null ? latest - previous : null,
      changePercent: latest !== null && previous ? ((latest - previous) / previous) * 100 : null,
      high: values.length ? Math.max(...values) : null,
      low: values.length ? Math.min(...values) : null,
    };
  }, [visiblePoints]);
  useEffect(() => {
    let disposed = false;
    let chart: IChartApi | null = null;
    let observer: ResizeObserver | null = null;
    async function mount() {
      if (!root.current || !points.length) return;
      const { LineSeries, createChart } = await import("lightweight-charts");
      if (disposed || !root.current) return;
      chart = createChart(root.current, { width: root.current.clientWidth, height: 260, layout: { background: { color: "#171d1d" }, textColor: "#aab9b5" }, grid: { vertLines: { color: "#303a38" }, horzLines: { color: "#303a38" } }, rightPriceScale: { borderColor: "#303a38" }, timeScale: { borderColor: "#303a38", timeVisible: false } });
      chartRef.current = chart;
      chart.addSeries(LineSeries, { color: "#3d7cff", lineWidth: 2, title: "Close price", crosshairMarkerVisible: true }).setData(visiblePoints.map(({ time, value }) => ({ time, value })));
      chart.timeScale().fitContent();
      observer = new ResizeObserver(() => { if (root.current && chart) chart.applyOptions({ width: root.current.clientWidth }); });
      observer.observe(root.current);
    }
    void mount();
    return () => { disposed = true; observer?.disconnect(); chart?.remove(); chartRef.current = null; };
  }, [visiblePoints]);

  return <section aria-label="Stock closing prices" className="chart-workspace">
    <div className="chart-toolbar"><div><span className="eyebrow">CLOSE PRICE</span><div className="chart-value"><strong>{summary.latest === null ? "—" : summary.latest.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong><span>XOF</span>{summary.changePercent !== null && <span className={`price-change ${summary.changePercent >= 0 ? "positive" : "negative"}`}>{summary.changePercent >= 0 ? "+" : ""}{summary.changePercent.toFixed(2)}%</span>}</div></div>
      <div className="segmented" aria-label="Chart period">{["1W", "1M", "3M", "1Y"].map((option) => <button key={option} type="button" aria-pressed={range === option} onClick={() => setRange(option)}>{option}</button>)}</div>
    </div>
    {visiblePoints.length ? <div className="chart-canvas" ref={root} aria-label="Closing price chart" role="img"><span className="sr-only">Close price by trading session.</span></div> : <div className="chart-empty" role="status">No close-price history is available for this stock and period.</div>}
    <div className="chart-footer"><span>Last session <strong>{visiblePoints.at(-1)?.date ?? "—"}</strong></span><span>High <strong>{summary.high === null ? "—" : summary.high.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></span><span>Low <strong>{summary.low === null ? "—" : summary.low.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></span></div>
  </section>;
}
