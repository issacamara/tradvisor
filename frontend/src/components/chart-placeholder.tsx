"use client";

import React from "react";
import { useEffect, useRef, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip } from "recharts";

const scoreData = [
  { label: "Growth", value: 66 },
  { label: "Quality", value: 74 },
  { label: "Value", value: 58 },
];

export function ChartPlaceholder() {
  const container = useRef<HTMLDivElement>(null);
  const [chartReady, setChartReady] = useState(false);

  useEffect(() => {
    let disposed = false;
    let cleanup: (() => void) | undefined;

    async function initializeChart() {
      if (!container.current) return;
      const { AreaSeries, createChart } = await import("lightweight-charts");
      if (disposed || !container.current) return;
      const chart = createChart(container.current, {
        height: 160,
        layout: { background: { color: "#171d1d" }, textColor: "#9aacaa" },
        grid: { vertLines: { color: "#2d3737" }, horzLines: { color: "#2d3737" } },
      });
      chart.addSeries(AreaSeries, { lineColor: "#45c88a", topColor: "rgba(69, 200, 138, 0.25)", bottomColor: "rgba(69, 200, 138, 0)" }).setData([
        { time: "2025-01-02", value: 120 }, { time: "2025-01-03", value: 128 }, { time: "2025-01-06", value: 125 }, { time: "2025-01-07", value: 133 },
      ]);
      chart.timeScale().fitContent();
      const observer = new ResizeObserver(() => chart.applyOptions({ width: container.current?.clientWidth ?? 0 }));
      observer.observe(container.current);
      cleanup = () => { observer.disconnect(); chart.remove(); };
      setChartReady(true);
    }

    void initializeChart();
    return () => { disposed = true; cleanup?.(); };
  }, []);

  return (
    <section aria-label="Illustrative chart placeholders" className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="rounded-md border border-line bg-panel p-3">
        <div className="mb-2 flex items-center justify-between"><span className="text-sm font-semibold">Price context</span><span className="text-xs text-muted">Local placeholder</span></div>
        <div ref={container} aria-label={chartReady ? "Price chart initialized" : "Preparing price chart"} className="min-h-40 w-full" />
        <p className="mt-2 text-xs text-muted">Charts will display published data and readable alternatives in the integrated workspace.</p>
      </div>
      <div className="rounded-md border border-line bg-panel p-3">
        <p className="mb-2 text-sm font-semibold">Research shape</p>
        <div className="h-36" aria-label="Illustrative score chart">
          <ResponsiveContainer width="100%" height="100%"><AreaChart data={scoreData}><Tooltip /><Area type="monotone" dataKey="value" stroke="#f2c14e" fill="#f2c14e" fillOpacity={0.18} /></AreaChart></ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
