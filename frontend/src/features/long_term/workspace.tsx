"use client";

import { useState } from "react";
import type { components } from "@/api/generated/schema";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Company = components["schemas"]["LongTermRankedCompany"];
type Objective = "growth" | "dividend";
const label = (value: string) => value.replaceAll("_", " ");
const metricText = (metric: components["schemas"]["ScoreMetric"]) => metric.value === null ? label(metric.status) : `${metric.value.toFixed(1)} / 100`;

export function LongTermWorkspace({ items = [], publishedAt = "Unavailable", objective: controlledObjective, onObjectiveChange }: { items?: Company[]; publishedAt?: string; objective?: Objective; onObjectiveChange?: (objective: Objective) => void }) {
  const [localObjective, setLocalObjective] = useState<Objective>("growth");
  const [selected, setSelected] = useState<string | null>(null);
  const objective = controlledObjective ?? localObjective;
  const setObjective = (next: Objective) => { setLocalObjective(next); onObjectiveChange?.(next); };
  const selectedCompany = items.find((company) => company.symbol === selected) ?? items[0];
  const completeGrowth = items.filter((company) => company.growth.growth_score.status === "assessable");
  const incompleteGrowth = items.filter((company) => company.growth.growth_score.status !== "assessable");
  const chartData = Object.entries(selectedCompany?.growth.dimension_contributions ?? {}).map(([name, metric]) => ({ name: label(name), points: metric.value, status: metric.status }));
  const shownItems = objective === "growth" ? [...completeGrowth, ...incompleteGrowth] : items;

  return <main className="workspace-page">
    <header className="page-heading"><div><p className="eyebrow">COMPANY RESEARCH <span aria-hidden="true">/</span> BRVM</p><h1>Long-Term research</h1><p className="page-subtitle">Review growth scores and recorded dividend facts separately.</p></div><div className="session-stamp">Published <strong>{publishedAt}</strong></div></header>
    <div className="research-tabs" role="tablist" aria-label="Research objective">
      <button type="button" role="tab" aria-selected={objective === "growth"} onClick={() => setObjective("growth")}>Growth scores</button>
      <button type="button" role="tab" aria-selected={objective === "dividend"} onClick={() => setObjective("dividend")}>Dividend research</button>
    </div>
    <div className="long-term-grid">
      <section className="screener-list" aria-label="Company research coverage">
        <div className="panel-heading"><div><h2>{objective === "growth" ? "Growth ranking" : "Dividend coverage"}</h2><p>{objective === "growth" ? "Complete scores appear before incomplete evidence" : "Payment facts are shown without an inferred yield"}</p></div><span className="row-count">{shownItems.length} stocks</span></div>
        <div className="table-scroll"><table className="data-table long-term-table"><caption className="sr-only">Company scores and research coverage</caption><thead><tr><th scope="col">Symbol</th><th scope="col">{objective === "growth" ? "Growth score" : "Dividend score"}</th><th scope="col">{objective === "growth" ? "Advice" : "Payments"}</th><th scope="col">Coverage</th></tr></thead><tbody>{shownItems.map((company) => <tr key={company.company_id} className={company.symbol === selectedCompany?.symbol ? "selected-row" : undefined} aria-selected={company.symbol === selectedCompany?.symbol}><td><button type="button" className="symbol-button" onClick={() => setSelected(company.symbol)} aria-label={`Inspect ${company.symbol}`}>{company.symbol}</button></td><td>{objective === "growth" ? metricText(company.growth.growth_score) : metricText(company.dividend_research.dividend_score)}</td><td>{objective === "growth" ? label(company.growth.advisory_state) : `${company.dividend_research.payments.length} recorded`}</td><td><span className={`coverage ${company.growth.growth_score.status === "assessable" ? "coverage-complete" : ""}`}>{company.growth.growth_score.status === "assessable" ? "Complete" : "Incomplete"}</span></td></tr>)}</tbody></table></div>
        {!items.length && <p className="empty-message">No published company research yet.</p>}
      </section>
      <aside className="evidence-section" aria-label="Selected company evidence">
        <div className="detail-heading"><div><p className="eyebrow">COMPANY EVIDENCE</p><h2>{selectedCompany?.symbol ?? "Select a company"}</h2></div></div>
        {selectedCompany ? <div className="long-term-detail">
          {objective === "growth" ? <>
            <div className="evidence-summary"><div><span>Growth score</span><strong>{metricText(selectedCompany.growth.growth_score)}</strong></div><div><span>Advice</span><strong>{label(selectedCompany.growth.advisory_state)}</strong></div></div>
            {chartData.some((row) => row.points !== null) && <div className="growth-chart" aria-label="Growth dimension contributions"><ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} layout="vertical" margin={{ left: 12, right: 12 }}><CartesianGrid stroke="#303a38" horizontal={false} /><XAxis type="number" domain={[0, "dataMax"]} hide /><YAxis type="category" dataKey="name" width={105} tick={{ fill: "#aab9b5", fontSize: 11 }} /><Tooltip /><Bar dataKey="points" fill="#4b9bc0" /></BarChart></ResponsiveContainer></div>}
            <h3>Score dimensions</h3><ul className="evidence-list">{chartData.map((row) => <li key={row.name}><span>{row.name}</span><span>{row.points === null ? label(row.status) : row.points.toFixed(1)}</span></li>)}</ul>
            {!chartData.length && <p className="empty-message">No dimension evidence was supplied.</p>}
          </> : <>
            <div className="evidence-summary"><div><span>Dividend score</span><strong>{metricText(selectedCompany.dividend_research.dividend_score)}</strong></div><div><span>Recorded payments</span><strong>{selectedCompany.dividend_research.payments.length}</strong></div></div>
            <h3>Payment facts</h3><ul className="evidence-list">{selectedCompany.dividend_research.payments.map((payment) => <li key={payment.dividend_id}><span>{payment.payment_date ?? "Date unavailable"} · {label(payment.dividend_type)} · {label(payment.payment_status)}</span><span>{payment.gross_amount_per_share?.amount ?? "—"} XOF/share</span></li>)}</ul>
            {!selectedCompany.dividend_research.payments.length && <p className="empty-message">No dividend payment facts supplied.</p>}
            <p className="evidence-note">Payment coverage does not establish a trailing yield or a composite investment score.</p>
          </>}
        </div> : <p className="empty-message">Select a company to review its evidence.</p>}
      </aside>
    </div>
  </main>;
}
