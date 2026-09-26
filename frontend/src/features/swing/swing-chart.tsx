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
      const { CandlestickSeries, HistogramSeries, LineSeries, createChart } = await import("lightweight-charts");
      if (disposed || !root.current) return;
      chart = createChart(root.current, { width: root.current.clientWidth, height: 260, layout: { background: { color: "#171d1d" }, textColor: "#aab9b5" }, grid: { vertLines: { color: "#303a38" }, horzLines: { color: "#303a38" } }, rightPriceScale: { borderColor: "#303a38" }, timeScale: { borderColor: "#303a38", timeVisible: false } });
      chartRef.current = chart;
      const usable = points.filter((point) => point.status === "traded" && point.open && point.high && point.low && point.close);
      chart.addSeries(CandlestickSeries).setData(usable.map((point) => ({ time: point.session_date as Time, open: Number(point.open!.amount), high: Number(point.high!.amount), low: Number(point.low!.amount), close: Number(point.close!.amount) })));
      chart.addSeries(HistogramSeries, { priceScaleId: "volume", priceFormat: { type: "volume" }, color: "#59a886" }).setData(usable.filter((point) => point.volume !== null).map((point) => ({ time: point.session_date as Time, value: point.volume!, color: "#59a886" })));
      for (const [key, color] of [["ema20", "#f2c14e"], ["ema50", "#65b8d1"]] as const) {
        const series = usable.flatMap((point) => point.indicators[key]?.value == null ? [] : [{ time: point.session_date as Time, value: point.indicators[key]!.value! }]);
        chart.addSeries(LineSeries, { color, lineWidth: 2, title: key.toUpperCase() }).setData(series);
      }
      chart.timeScale().fitContent();
      observer = new ResizeObserver(() => { if (root.current && chart) chart.applyOptions({ width: root.current.clientWidth }); });
      observer.observe(root.current);
    }
    void mount();
    return () => { disposed = true; observer?.disconnect(); chart?.remove(); chartRef.current = null; };
  }, [points]);

  return <div className="min-h-[16rem] w-full overflow-hidden border border-line bg-panel" ref={root} aria-label="Candlesticks, volume and EMA overlays" role="img"><span className="sr-only">Candlestick chart with volume and backend EMA20 and EMA50 series. A dated data table follows.</span></div>;
}
