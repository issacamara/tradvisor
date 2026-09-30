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

  return <section aria-label="Stock market tracker" className="rounded-lg border border-line bg-panel p-4 sm:p-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="flex items-center gap-2 text-base font-semibold"><span aria-hidden="true" className="grid h-7 w-7 place-items-center rounded border border-line text-muted">▥</span>Stock Market Tracker</h3>
      <span className="text-sm text-muted">{visiblePoints.at(-1)?.date ?? "No data"}</span>
    </div>
    <div className="mt-4 grid grid-cols-5 overflow-hidden rounded-lg border border-line text-center text-sm font-medium">
      {["1D", "1W", "1M", "3M", "1Y"].map((option) => <button key={option} type="button" aria-pressed={range === option} onClick={() => setRange(option)} className={`py-2 transition-colors ${range === option ? "bg-white/10 text-foreground" : "text-muted hover:bg-white/5"}`}>{option}</button>)}
    </div>
    <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <strong className="text-2xl tracking-normal">{summary.latest === null ? "—" : summary.latest.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
      {summary.changePercent !== null && <span className={`rounded px-2 py-1 text-xs font-semibold ${summary.changePercent >= 0 ? "bg-emerald-400/15 text-emerald-300" : "bg-red-400/15 text-red-300"}`}>{summary.changePercent >= 0 ? "↗" : "↘"} {Math.abs(summary.changePercent).toFixed(2)}%</span>}
      <span className="basis-full text-xs uppercase tracking-wide text-muted">{visiblePoints.length ? "Close price" : "No close-price observations"}</span>
    </div>
    <div className="mt-4 min-h-[16rem] w-full overflow-hidden border-y border-line py-2" ref={root} aria-label="Closing price chart" role="img"><span className="sr-only">Close price by trading session.</span></div>
    <div className="mt-3 grid grid-cols-2 overflow-hidden rounded-lg border border-line text-center text-sm">
      <div className="border-r border-line py-2"><span className="text-muted">Highest </span><strong>{summary.high === null ? "—" : summary.high.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></div>
      <div className="py-2"><span className="text-muted">Lowest </span><strong>{summary.low === null ? "—" : summary.low.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong></div>
    </div>
  </section>;
}
