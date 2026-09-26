"use client";

import { useMemo, useState } from "react";
import type { components } from "@/api/generated/schema";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Company = components["schemas"]["LongTermRankedCompany"];
type Objective = "growth" | "dividend" | "balanced";
const metricText = (metric: components["schemas"]["ScoreMetric"]) => metric.value === null ? metric.status.replaceAll("_", " ") : `${metric.value.toFixed(1)} / 100`;

export function LongTermWorkspace({ items = [], publishedAt = "Unavailable" }: { items?: Company[]; publishedAt?: string }) {
  const [objective, setObjective] = useState<Objective>("growth");
  const [selected, setSelected] = useState<string | null>(items[0]?.symbol ?? null);
  const orderedItems = useMemo(() => items, [items]);
  const selectedCompany = items.find((company) => company.symbol === selected);
  const dimensions = selectedCompany?.growth.dimension_contributions ?? {};
  const chartData = Object.entries(dimensions).map(([name, metric]) => ({ name: name.replaceAll("_", " "), points: metric.value, status: metric.status }));
  const completeGrowth = objective === "growth" ? orderedItems.filter((company) => company.growth.growth_score.status === "assessable") : [];
  const incompleteGrowth = objective === "growth" ? orderedItems.filter((company) => company.growth.growth_score.status !== "assessable") : orderedItems;

  return <main className="grid gap-5 p-4 sm:p-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm text-muted">Long-Term / Growth and dividend research</p><h1 className="text-2xl font-bold">Growth rankings</h1></div><p className="text-sm text-muted">Published: {publishedAt}</p></header>
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line">
      <div role="tablist" aria-label="Research view" className="flex gap-2">{(["growth", "dividend", "balanced"] as const).map((value) => <button key={value} type="button" role="tab" aria-selected={objective === value} onClick={() => setObjective(value)} className={`border-b-2 px-3 py-2 text-sm capitalize ${objective === value ? "border-accent font-semibold" : "border-transparent text-muted"}`}>{value === "dividend" ? "Dividend research" : value}</button>)}</div>
      <p className="pb-2 text-xs text-muted">Complete Growth scores rank separately from incomplete coverage.</p>
    </div>
    {objective === "balanced" && <p role="status" className="border-l-2 border-warning pl-3 text-sm">Balanced scoring is deferred in V1. No companies are ranked by a substitute score.</p>}
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.8fr)]">
      <section aria-label="Company research coverage" className="min-w-0 overflow-x-auto border-t border-line">
        <table className="w-full min-w-[42rem] text-left text-sm"><caption className="sr-only">Complete and incomplete company research coverage</caption><thead><tr>{["Company", "Growth", "Advice", "Dividend facts", "Coverage"].map((label) => <th key={label} scope="col" className="px-3 py-3 font-semibold">{label}</th>)}</tr></thead>{objective === "growth" && <tbody aria-label="Complete Growth score group"><tr><th colSpan={5} className="border-t border-line px-3 py-2 text-xs uppercase text-muted" scope="colgroup">Complete Growth scores</th></tr>{completeGrowth.map((company) => renderCompany(company, objective, setSelected))}</tbody>}<tbody aria-label={objective === "growth" ? "Incomplete Growth evidence group" : `${objective} research group`}>{objective === "growth" && <tr><th colSpan={5} className="border-t border-line px-3 py-2 text-xs uppercase text-muted" scope="colgroup">Incomplete and guarded evidence</th></tr>}{incompleteGrowth.map((company) => renderCompany(company, objective, setSelected))}</tbody></table>
        {!items.length && <p className="px-3 py-6 text-sm text-muted">No catalog research results are available.</p>}
      </section>
      <aside aria-label="Selected company evidence" className="border-t border-line pt-3">
        <h2 className="text-lg font-semibold">{selectedCompany?.symbol ?? "Company evidence"}</h2>
        {selectedCompany ? <>
          <p className="mt-1 text-sm text-muted">Growth {metricText(selectedCompany.growth.growth_score)} · {selectedCompany.growth.advisory_state.replaceAll("_", " ")}</p>
          <div className="mt-4 h-48" aria-label="Growth dimension contributions"><ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} layout="vertical" margin={{ left: 12, right: 12 }}><CartesianGrid stroke="#303a38" horizontal={false} /><XAxis type="number" domain={[0, "dataMax"]} hide /><YAxis type="category" dataKey="name" width={100} tick={{ fill: "#aab9b5", fontSize: 11 }} /><Tooltip /><Bar dataKey="points" fill="#65b8d1" /></BarChart></ResponsiveContainer></div>
          <table className="mt-3 w-full text-left text-xs"><caption className="sr-only">Growth dimensions and evidence status</caption><thead><tr><th className="py-2" scope="col">Dimension</th><th scope="col">Points</th><th scope="col">Status</th></tr></thead><tbody>{chartData.map((row) => <tr key={row.name} className="border-t border-line"><th className="py-2 font-medium" scope="row">{row.name}</th><td>{row.points ?? "—"}</td><td>{row.status.replaceAll("_", " ")}</td></tr>)}</tbody></table>
          <h3 className="mt-5 text-sm font-semibold">Dividend evidence</h3>
          <ul className="mt-2 grid gap-2 text-sm">{selectedCompany.dividend_research.payments.map((payment) => <li key={payment.dividend_id} className="flex flex-wrap justify-between gap-2 border-t border-line pt-2"><span>{payment.payment_date ?? "Date unavailable"} · {payment.dividend_type} · {payment.payment_status}</span><span>{payment.gross_amount_per_share?.amount ?? "Amount unavailable"} XOF/share</span></li>)}</ul>
          {!selectedCompany.dividend_research.payments.length && <p className="mt-2 text-sm text-muted">No dividend payment facts supplied.</p>}
          <p className="mt-3 text-xs text-muted">Coverage remains separate from payment rows. Deferred scores and unproven trailing yields are never shown as zero.</p>
        </> : <p className="mt-2 text-sm text-muted">Select a company to inspect supported factors and dividend facts.</p>}
      </aside>
    </div>
  </main>;
}

function renderCompany(company: Company, objective: Objective, select: (symbol: string) => void) {
  const complete = company.growth.growth_score.status === "assessable";
  const score = objective === "growth" ? metricText(company.growth.growth_score) : objective === "balanced" ? "Deferred" : metricText(company.dividend_research.dividend_score);
  return <tr key={company.company_id} className="border-t border-line"><th scope="row" className="px-3 py-3 font-medium"><button onClick={() => select(company.symbol)} className="underline-offset-4 hover:underline">{company.symbol}</button></th><td className="px-3 py-3">{score}</td><td className="px-3 py-3">{company.growth.advisory_state.replaceAll("_", " ")}</td><td className="px-3 py-3">{company.dividend_research.payments.length} recorded facts</td><td className="px-3 py-3">{complete ? "Complete score" : "Incomplete evidence"}</td></tr>;
}
