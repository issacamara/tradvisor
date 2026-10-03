"use client";

import { useEffect, useState } from "react";
import type { components } from "@/api/generated/schema";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Company = components["schemas"]["LongTermRankedCompany"];
type Objective = "growth" | "dividend";
const label = (value: string) => value.replaceAll("_", " ");
const metricText = (metric: components["schemas"]["ScoreMetric"]) => metric.value === null ? label(metric.status) : `${metric.value.toFixed(1)} / 100`;
const growthDimensions = [
  ["Revenue", "activity_growth"],
  ["Earnings", "earnings_growth"],
  ["Valuation", "earnings_book_valuation"],
  ["Profitability", "profitability"],
] as const;

export function LongTermWorkspace({ items = [], publishedAt = "Unavailable", objective: controlledObjective, onObjectiveChange }: { items?: Company[]; publishedAt?: string; objective?: Objective; onObjectiveChange?: (objective: Objective) => void }) {
  const [localObjective, setLocalObjective] = useState<Objective>("growth");
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    setSelected((current) => items.some((company) => company.symbol === current) ? current : items[0]?.symbol ?? null);
  }, [items]);
  const objective = controlledObjective ?? localObjective;
  const setObjective = (next: Objective) => { setLocalObjective(next); onObjectiveChange?.(next); };
  const selectedCompany = items.find((company) => company.symbol === selected) ?? items[0];
  const chartData = growthDimensions.map(([name, key]) => {
    const metric = selectedCompany?.growth.dimension_contributions[key];
    return { name, points: metric?.value ?? null, status: metric?.status ?? "unavailable" };
  });
  const annualData = selectedCompany?.growth.annual_dimensions ?? [];
  const shownItems = items;

  return <main className="workspace-page">
    <header className="page-heading"><div><p className="eyebrow">COMPANY RESEARCH <span aria-hidden="true">/</span> BRVM</p><h1>Long-Term research</h1><p className="page-subtitle">Review growth dimensions and recorded dividend facts separately.</p></div><div className="session-stamp">Published <strong>{publishedAt}</strong></div></header>
    <div className="research-tabs" role="tablist" aria-label="Research objective">
      <button type="button" role="tab" aria-selected={objective === "growth"} onClick={() => setObjective("growth")}>Growth scores</button>
      <button type="button" role="tab" aria-selected={objective === "dividend"} onClick={() => setObjective("dividend")}>Dividend research</button>
    </div>
    <div className="long-term-grid">
      <section className="screener-list" aria-label="Company research coverage">
        <div className="panel-heading"><div><h2>{objective === "growth" ? "Growth dimensions" : "Dividend coverage"}</h2><p>{objective === "growth" ? "Revenue, earnings, valuation, and profitability" : "Payment facts are shown without an inferred yield"}</p></div><span className="row-count">{shownItems.length} stocks</span></div>
        <div className="table-scroll"><table className="data-table long-term-table"><caption className="sr-only">Company research coverage</caption><thead><tr><th scope="col">Symbol</th><th scope="col">{objective === "growth" ? "Growth dimensions" : "Dividend research"}</th></tr></thead><tbody>{shownItems.map((company) => <tr key={company.company_id} className={company.symbol === selectedCompany?.symbol ? "selected-row" : undefined} aria-selected={company.symbol === selectedCompany?.symbol}><td><button type="button" className="symbol-button" onClick={() => setSelected(company.symbol)} aria-label={`Inspect ${company.symbol}`}>{company.symbol}</button></td><td>{objective === "growth" ? "Revenue · Earnings · Valuation · Profitability" : `${company.dividend_research.payments.length} recorded payments`}</td></tr>)}</tbody></table></div>
        {!items.length && <p className="empty-message">No published company research yet.</p>}
      </section>
      <aside className="evidence-section" aria-label="Selected company evidence">
        <div className="detail-heading"><div><p className="eyebrow">COMPANY EVIDENCE</p><h2>{selectedCompany?.symbol ?? "Select a company"}</h2></div></div>
        {selectedCompany ? <div className="long-term-detail">
          {objective === "growth" ? <>
            <div className="growth-chart" aria-label="Annual Long-Term research dimensions"><ResponsiveContainer width="100%" height="100%"><LineChart data={annualData} margin={{ left: 12, right: 12 }}><CartesianGrid stroke="#303a38" vertical={false} /><XAxis dataKey="fiscal_year" tick={{ fill: "#aab9b5", fontSize: 11 }} /><YAxis tick={{ fill: "#aab9b5", fontSize: 11 }} /><Tooltip /><Line type="monotone" dataKey="revenue" name="Revenue" stroke="#4b9bc0" connectNulls={false} /><Line type="monotone" dataKey="earnings" name="Earnings" stroke="#45c88a" connectNulls={false} /><Line type="monotone" dataKey="profitability" name="Profitability (%)" stroke="#f2d795" connectNulls={false} /></LineChart></ResponsiveContainer></div>
            <h3>Annual dimensions</h3><ul className="evidence-list">{chartData.filter((row) => row.name !== "Valuation").map((row) => <li key={row.name}><span>{row.name}</span><span>{row.points === null ? "Unavailable" : row.points.toFixed(1)}</span></li>)}<li><span>Valuation</span><span>Unavailable</span></li></ul>
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
