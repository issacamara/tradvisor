"use client";

import { useEffect, useRef } from "react";
import type { components } from "@/api/generated/schema";
import type { IChartApi, Time } from "lightweight-charts";

type ChartPoint = components["schemas"]["ChartPoint"];
const numeric = (value: { amount: string } | null) => value === null ? null : Number(value.amount);

export function SwingChart({ points }: { points: ChartPoint[] }) {
  const root = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
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
      const closePrice = points.flatMap((point) => numeric(point.close) === null ? [] : [{ time: point.session_date as Time, value: numeric(point.close)! }]);
      chart.addSeries(LineSeries, { color: "#65b8d1", lineWidth: 2, title: "Close price" }).setData(closePrice);
      chart.timeScale().fitContent();
      observer = new ResizeObserver(() => { if (root.current && chart) chart.applyOptions({ width: root.current.clientWidth }); });
      observer.observe(root.current);
    }
    void mount();
    return () => { disposed = true; observer?.disconnect(); chart?.remove(); chartRef.current = null; };
  }, [points]);

  return <div className="min-h-[16rem] w-full overflow-hidden border border-line bg-panel" ref={root} aria-label="Closing price chart" role="img"><span className="sr-only">Close price by trading session. A dated evidence table follows.</span></div>;
}
