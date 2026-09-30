"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { components } from "@/api/generated/schema";
import { SwingChart } from "./swing-chart";

type Recommendation = components["schemas"]["SwingRecommendation"];
type ChartPoint = components["schemas"]["ChartPoint"];
type Props = { items?: Recommendation[]; chart?: ChartPoint[]; marketSession?: string; selectedSymbol?: string | null; onSymbolChange?: (symbol: string) => void };
const label = (value: string) => value.replaceAll("_", " ");
const strength = (item: Recommendation) => item.buy_strength.value === null ? "—" : `${item.buy_strength.value.toFixed(0)} / 100`;

export function SwingWorkspace({ items = [], chart = [], marketSession = "Unavailable", selectedSymbol = null, onSymbolChange }: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "buy">("all");
  const selected = selectedSymbol ?? items[0]?.symbol ?? null;
  const filtered = useMemo(() => items.filter((item) => item.symbol.toLowerCase().includes(query.trim().toLowerCase()) && (filter === "all" || item.entry_action === "buy")), [items, query, filter]);
  const columns = useMemo<ColumnDef<Recommendation>[]>(() => [
    { accessorKey: "symbol", header: "Symbol", cell: ({ row }) => <button type="button" className="symbol-button" onClick={() => onSymbolChange?.(row.original.symbol)} aria-label={`Inspect ${row.original.symbol}`}>{row.original.symbol}</button> },
    { accessorKey: "entry_action", header: "Entry", cell: ({ row }) => <span className={`signal signal-${row.original.entry_action}`}>{label(row.original.entry_action)}</span> },
    { id: "strength", header: "Strength", cell: ({ row }) => <span className="tabular-nums">{strength(row.original)}</span> },
    { id: "holding", header: "Holding", cell: ({ row }) => row.original.holding_advice ? label(row.original.holding_advice.action) : "Not held" },
  ], [onSymbolChange]);
  const table = useReactTable({ data: filtered, columns, getCoreRowModel: getCoreRowModel() });
  const detail = items.find((item) => item.symbol === selected);
  const buyCount = items.filter((item) => item.entry_action === "buy").length;

  return <main className="workspace-page">
    <header className="page-heading">
      <div><p className="eyebrow">DAILY RESEARCH <span aria-hidden="true">/</span> BRVM</p><h1>Swing screener</h1><p className="page-subtitle">Technical signals and their supporting evidence.</p></div>
      <div className="session-stamp"><span className="session-dot" aria-hidden="true" /> Market session <strong>{marketSession}</strong></div>
    </header>
    <section className="summary-strip" aria-label="Screener summary">
      <div><span>Covered stocks</span><strong>{items.length}</strong></div>
      <div><span>Buy entries</span><strong className="text-accent">{buyCount}</strong></div>
      <div><span>Selected stock</span><strong>{selected ?? "—"}</strong></div>
    </section>
    <div className="research-grid">
      <section className="screener-list" aria-label="Swing recommendations">
        <div className="panel-heading"><div><h2>Market list</h2><p>Choose a symbol to inspect its signal</p></div><span className="row-count">{filtered.length} stocks</span></div>
        <div className="list-tools">
          <label className="search-field"><Search size={16} aria-hidden="true" /><span className="sr-only">Search symbol</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search symbol" /></label>
          <div className="segmented" aria-label="Entry filter"><button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All</button><button type="button" aria-pressed={filter === "buy"} onClick={() => setFilter("buy")}>Buy</button></div>
        </div>
        <div className="table-scroll"><table className="data-table"><caption className="sr-only">Swing recommendations with separate holding advice</caption><thead><tr>{table.getHeaderGroups()[0]?.headers.map((header) => <th key={header.id} scope="col">{flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr></thead><tbody>{table.getRowModel().rows.map((row) => <tr key={row.id} className={row.original.symbol === selected ? "selected-row" : undefined} aria-selected={row.original.symbol === selected}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table></div>
        {!items.length && <p className="empty-message">No published Swing recommendations yet.</p>}
        {items.length > 0 && !filtered.length && <p className="empty-message">No symbols match this filter.</p>}
      </section>
      <div className="research-detail">
        <section className="price-section" aria-label="Price history">
          <div className="detail-heading"><div><p className="eyebrow">PRICE HISTORY</p><h2>{selected ?? "Select a stock"}</h2></div><label className="symbol-select">Symbol<select aria-label="Chart symbol" value={selected ?? ""} onChange={(event) => onSymbolChange?.(event.target.value)} disabled={!items.length}>{!items.length && <option value="">No symbols</option>}{items.map((item) => <option key={item.symbol} value={item.symbol}>{item.symbol}</option>)}</select></label></div>
          <SwingChart points={chart} />
        </section>
        <section className="evidence-section" aria-label="Selected recommendation detail">
          <div className="detail-heading"><div><p className="eyebrow">RECOMMENDATION EVIDENCE</p><h2>{detail?.symbol ?? "No stock selected"}</h2></div>{detail && <span className={`signal signal-${detail.entry_action}`}>{label(detail.entry_action)}</span>}</div>
          {detail ? <><div className="evidence-summary"><div><span>Entry strength</span><strong>{strength(detail)}</strong></div><div><span>Holding advice</span><strong>{detail.holding_advice ? label(detail.holding_advice.action) : "Not held"}</strong></div></div><p className="evidence-note">Strength is a rule score, not a probability. A non-Buy result is not a Sell instruction.</p><h3>Eligibility</h3><ul className="evidence-list">{detail.eligibility_guards.map((guard) => <li key={guard.code}><span>{label(guard.code)}</span><span>{guard.status}{guard.observed !== null ? ` · ${guard.observed}` : ""}</span></li>)}</ul>{detail.holding_advice?.reasons.length ? <><h3>Holding rationale</h3><ul className="reason-list">{detail.holding_advice.reasons.map((reason) => <li key={reason.code}>{reason.message}</li>)}</ul></> : null}</> : <p className="empty-message">Select a stock to review the evidence.</p>}
        </section>
      </div>
    </div>
    <p className="workspace-footnote">Market recommendations are shared. Holding advice applies only to simulated positions; no order is submitted from this screen.</p>
  </main>;
}
