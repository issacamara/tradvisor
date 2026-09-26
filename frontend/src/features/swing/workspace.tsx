"use client";

import { useMemo, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { components } from "@/api/generated/schema";
import { SwingChart } from "./swing-chart";

type Recommendation = components["schemas"]["SwingRecommendation"];
type ChartPoint = components["schemas"]["ChartPoint"];
type Props = { items?: Recommendation[]; chart?: ChartPoint[]; marketSession?: string };

export function SwingWorkspace({ items = [], chart = [], marketSession = "Unavailable" }: Props) {
  const [selected, setSelected] = useState<string | null>(items[0]?.symbol ?? null);
  const columns = useMemo<ColumnDef<Recommendation>[]>(() => [
    { accessorKey: "symbol", header: "Symbol", cell: ({ row }) => <button className="font-semibold underline-offset-4 hover:underline" onClick={() => setSelected(row.original.symbol)}>{row.original.symbol}</button> },
    { accessorKey: "entry_action", header: "Entry state", cell: ({ getValue }) => String(getValue()).replaceAll("_", " ") },
    { id: "strength", header: "Strength", cell: ({ row }) => row.original.buy_strength.value === null ? "Unavailable" : `${row.original.buy_strength.value.toFixed(1)} / 100` },
    { id: "holding", header: "Holding advice", cell: ({ row }) => row.original.holding_advice?.action.replaceAll("_", " ") ?? "Not held" },
  ], []);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });
  const detail = items.find((item) => item.symbol === selected);

  return <main className="grid gap-5 p-4 sm:p-6">
    <header className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-sm text-muted">Swing / shared market state</p><h1 className="text-2xl font-bold">Swing screener</h1></div><p className="text-sm text-muted">Market session: {marketSession}</p></header>
    <div className="grid gap-5 xl:grid-cols-[minmax(18rem,0.8fr)_minmax(0,1.4fr)_minmax(16rem,0.7fr)]">
      <section aria-label="Swing recommendations" className="min-w-0 overflow-x-auto border-t border-line">
        <table className="w-full min-w-[34rem] text-left text-sm"><caption className="sr-only">Swing recommendations with separate holding advice</caption><thead><tr>{table.getHeaderGroups()[0]?.headers.map((header) => <th key={header.id} scope="col" className="border-b border-line px-3 py-3 font-semibold">{flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr></thead><tbody>{table.getRowModel().rows.map((row) => <tr key={row.id} className="border-b border-line">{row.getVisibleCells().map((cell) => <td key={cell.id} className="px-3 py-3">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table>
        {!items.length && <p className="px-3 py-6 text-sm text-muted">No published Swing results.</p>}
      </section>
      <section className="min-w-0">
        <h2 className="mb-2 text-sm font-semibold">{selected ?? "Price and indicators"} / dated evidence</h2>
        <SwingChart points={chart} />
        <div className="mt-3 overflow-x-auto border-t border-line">
          <table className="w-full min-w-[42rem] text-left text-xs"><caption className="sr-only">Dated OHLCV, backend indicator values, and source evidence</caption><thead><tr>{["Session", "Status", "Open", "High", "Low", "Close", "Volume", "EMA20", "EMA50", "RSI14", "ATR14", "Traded value", "Source evidence"].map((label) => <th className="px-2 py-2 font-semibold" key={label} scope="col">{label}</th>)}</tr></thead><tbody>{chart.map((point) => <tr key={point.session_date} className="border-t border-line"><th scope="row" className="px-2 py-2">{point.session_date}</th><td className="px-2 py-2">{point.status.replaceAll("_", " ")}</td>{[point.open, point.high, point.low, point.close].map((value, index) => <td className="px-2 py-2" key={index}>{value?.amount ?? "—"}</td>)}<td className="px-2 py-2">{point.volume ?? "—"}</td>{["ema20", "ema50", "rsi14", "atr14", "traded_value20"].map((key) => { const metric = point.indicators[key]; return <td className="px-2 py-2" key={key}>{metric?.value ?? "—"}{metric?.basis === "estimated" ? " est." : ""}</td>; })}<td className="px-2 py-2">{point.source_evidence.length ? <ul className="grid gap-1">{point.source_evidence.map((evidence, index) => <li key={`${evidence.source_id}-${index}`}>{evidence.source_url?.startsWith("https://") ? <a className="underline" href={evidence.source_url} target="_blank" rel="noreferrer">{evidence.source_id}</a> : evidence.source_id} ({evidence.basis}){evidence.collected_at ? ` · collected ${evidence.collected_at}` : ""}{evidence.published_at ? ` · published ${evidence.published_at}` : ""}</li>)}</ul> : "Unavailable"}</td></tr>)}</tbody></table>
          {!chart.length && <p className="px-2 py-4 text-xs text-muted">Chart evidence is unavailable until a typed session series is supplied.</p>}
        </div>
      </section>
      <aside aria-label="Selected recommendation detail" className="border-t border-line pt-3">
        <h2 className="text-lg font-semibold">{detail?.symbol ?? "Recommendation detail"}</h2>
        {detail ? <><p className="mt-2 text-sm">Entry: <strong>{detail.entry_action.replaceAll("_", " ")}</strong></p><p className="mt-1 text-sm text-muted">Strength is a rule score, not a probability. A result that does not qualify for Buy is not a Sell instruction.</p><h3 className="mt-5 text-sm font-semibold">Eligibility evidence</h3><ul className="mt-2 grid gap-2 text-sm">{detail.eligibility_guards.map((guard) => <li key={guard.code} className="flex justify-between gap-3"><span>{guard.code.replaceAll("_", " ")}</span><span className="text-muted">{guard.status}{guard.observed !== null ? ` · ${guard.observed}` : ""}</span></li>)}</ul><h3 className="mt-5 text-sm font-semibold">Holding advice</h3><p className="mt-2 text-sm">{detail.holding_advice?.action.replaceAll("_", " ") ?? "Not applicable"}</p><ul className="mt-2 grid gap-2 text-sm text-muted">{detail.holding_advice?.reasons.map((reason) => <li key={reason.code}>{reason.message}</li>)}</ul></> : <p className="mt-2 text-sm text-muted">Select a row to inspect rule and holding evidence.</p>}
      </aside>
    </div>
    <p className="text-xs text-muted">Market recommendations are shared. Personalized holding advice is separate and never submits an order.</p>
  </main>;
}
