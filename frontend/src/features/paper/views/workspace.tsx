"use client";

import { useState } from "react";
import type { components } from "@/api/generated/schema";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Portfolio = components["schemas"]["PortfolioResource"];
type Order = components["schemas"]["PaperOrder"];
type Execution = components["schemas"]["PaperExecution"];
type Movement = components["schemas"]["CashMovement"];
type Props = {
  portfolio?: Portfolio;
  orders?: Order[];
  executions?: Execution[];
  movements?: Movement[];
  orderCursor?: string | null;
  executionCursor?: string | null;
  movementCursor?: string | null;
  freshness?: string;
  cursorError?: "cursor_stale" | "snapshot_expired" | null;
  onNext?(kind: "orders" | "executions" | "movements"): void;
  onRestartPage?(): void;
};
const xof = (amount: string) => `${amount} XOF`;

export function PaperWorkspace({ portfolio, orders = [], executions = [], movements = [], orderCursor = null, executionCursor = null, movementCursor = null, freshness = "Not available", cursorError = null, onNext, onRestartPage }: Props) {
  const [view, setView] = useState<"orders" | "executions" | "ledger">("orders");
  const summary = portfolio?.summary;
  const positions = portfolio?.positions ?? [];
  return <main className="grid gap-5 p-4 sm:p-6">
    <header className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-sm text-muted">Paper / manual simulation</p><h1 className="text-2xl font-bold">Portfolio reporting</h1></div><p className="text-sm text-muted">Valuation freshness: {freshness}</p></header>
    <section aria-label="Paper balances and reservations" className="grid gap-3 border-y border-line py-4 sm:grid-cols-2 xl:grid-cols-4">
      <Metric label="Cash" value={summary ? xof(summary.cash.amount) : "Unavailable"} />
      <Metric label="Reserved cash" value={summary ? xof(summary.reserved_cash.amount) : "Unavailable"} />
      <Metric label="Pending orders" value={summary ? String(summary.pending_order_count) : "Unavailable"} />
      <Metric label="Portfolio valuation" value={portfolio?.valuation_status === "complete" ? "Complete" : portfolio?.valuation_status === "incomplete" ? "Incomplete" : "Unavailable"} />
    </section>
    <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.7fr)]">
      <div className="min-w-0">
        {cursorError && <p role="alert" className="mb-3 border-l-2 border-warning pl-3 text-sm">History changed or expired. Restart pagination to load one consistent current page. <button type="button" className="ml-2 underline" onClick={onRestartPage}>Restart history</button></p>}
        <div className="flex flex-wrap gap-2 border-b border-line" role="tablist" aria-label="Paper history">{(["orders", "executions", "ledger"] as const).map((item) => <button key={item} role="tab" aria-selected={view === item} onClick={() => setView(item)} className={`border-b-2 px-3 py-2 text-sm capitalize ${view === item ? "border-accent" : "border-transparent text-muted"}`}>{item === "ledger" ? "Cash ledger" : item}</button>)}</div>
        {view === "orders" && <HistoryTable title="Order history" headers={["Accepted", "Symbol", "Side", "Quantity", "State", "Reservation"]} rows={orders.map((order) => [order.accepted_at ?? "—", order.symbol, order.side, String(order.quantity), order.status, order.reserved_cash ? xof(order.reserved_cash.amount) : order.reserved_sell_quantity ? `${order.reserved_sell_quantity} shares` : "—"])} empty="No orders in this page." cursor={orderCursor} next={() => onNext?.("orders")} />}
        {view === "executions" && <HistoryTable title="Execution history" headers={["Processed", "Symbol", "Side", "Quantity", "Gross", "Fee", "Net cash"]} rows={executions.map((execution) => [execution.processed_at, execution.execution_price.symbol, execution.signed_cash_effect.amount.startsWith("-") ? "buy" : "sell", String(execution.quantity), xof(execution.gross_amount.amount), xof(execution.fee_amount.amount), xof(execution.signed_cash_effect.amount)])} empty="No confirmed executions in this page." cursor={executionCursor} next={() => onNext?.("executions")} />}
        {view === "ledger" && <HistoryTable title="Cash movement ledger" headers={["Occurred", "Type", "Amount", "Order"]} rows={movements.map((movement) => [movement.occurred_at, movement.movement_type.replaceAll("_", " "), xof(movement.signed_amount.amount), movement.execution_id ?? "Opening cash"])} empty="No cash movements in this page." cursor={movementCursor} next={() => onNext?.("movements")} />}
      </div>
      <aside className="grid content-start gap-4 border-t border-line pt-3">
        <section aria-label="Position valuation"><h2 className="text-lg font-semibold">Positions</h2><table className="mt-2 w-full text-left text-sm"><caption className="sr-only">Paper positions and reserved quantities</caption><thead><tr><th className="py-2" scope="col">Symbol</th><th scope="col">Shares</th><th scope="col">Reserved</th><th scope="col">Cost basis</th></tr></thead><tbody>{positions.map((position) => <tr className="border-t border-line" key={position.symbol}><th className="py-2" scope="row">{position.symbol}</th><td>{position.quantity}</td><td>{position.reserved_sell_quantity}</td><td>{xof(position.remaining_gross_cost.amount)}</td></tr>)}</tbody></table>{!positions.length && <p className="mt-2 text-sm text-muted">No open simulated positions.</p>}<p className="mt-3 text-xs text-muted">{portfolio?.valuation_status === "incomplete" ? "At least one position lacks a current valuation. The total is intentionally withheld." : "Position market value and P&amp;L appear only when provided by the backend valuation contract."}</p></section>
        <section aria-label="Simulated performance"><h2 className="text-lg font-semibold">Simulated performance</h2><div className="mt-3 h-40" role="img" aria-label="No backend P and L series available"><ResponsiveContainer width="100%" height="100%"><AreaChart data={[]}><XAxis dataKey="session" /><YAxis /><Tooltip /><Area dataKey="value" stroke="#65b8d1" fill="#65b8d1" /></AreaChart></ResponsiveContainer></div><p className="text-sm text-muted">Gross and net realized/unrealized P&amp;L are unavailable in the current generated portfolio read contract.</p><dl className="mt-2 grid grid-cols-2 gap-2 text-sm"><Metric label="Gross realized" value="Unavailable" /><Metric label="Net realized" value="Unavailable" /><Metric label="Gross unrealized" value="Unavailable" /><Metric label="Net unrealized" value="Unavailable" /></dl></section>
      </aside>
    </section>
    <p className="text-xs text-muted">Pending orders are reservations, never fills. Execution rows show confirmed simulated fills only.</p>
  </main>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div><dt className="text-xs text-muted">{label}</dt><dd className="mt-1 text-sm font-semibold">{value}</dd></div>; }

function HistoryTable({ title, headers, rows, empty, cursor, next }: { title: string; headers: string[]; rows: string[][]; empty: string; cursor: string | null; next(): void }) {
  return <section aria-label={title} className="overflow-x-auto"><table className="w-full min-w-[34rem] text-left text-sm"><caption className="sr-only">{title}</caption><thead><tr>{headers.map((header) => <th className="px-2 py-3 font-semibold" scope="col" key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={`${row[0]}-${rowIndex}`} className="border-t border-line">{row.map((cell, index) => index === 0 ? <th className="px-2 py-3 font-medium" scope="row" key={index}>{cell}</th> : <td className="px-2 py-3" key={index}>{cell}</td>)}</tr>)}</tbody></table>{!rows.length && <p className="px-2 py-5 text-sm text-muted">{empty}</p>}<button type="button" disabled={!cursor} onClick={next} className="mt-3 rounded border border-line px-3 py-2 text-sm disabled:opacity-50">Load next page</button></section>;
}
