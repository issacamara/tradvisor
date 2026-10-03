"use client";

import { useEffect, useState } from "react";
import type { components } from "@/api/generated/schema";

type Company = components["schemas"]["LongTermRankedCompany"];
type Objective = "growth" | "dividend";
const label = (value: string) => value.replaceAll("_", " ");
const metricText = (metric: components["schemas"]["ScoreMetric"]) => metric.value === null ? label(metric.status) : `${metric.value.toFixed(1)} / 100`;
function AnnualDimensionChart({ data }: { data: Company["growth"]["annual_dimensions"] }) {
  if (!data.length) return <p className="chart-empty">No annual financial observations are available.</p>;
  const width = 760;
  const height = 220;
  const padding = { top: 16, right: 20, bottom: 28, left: 20 };
  const series = [
    { key: "revenue", label: "Revenue", color: "#4b9bc0" },
    { key: "earnings", label: "Earnings", color: "#45c88a" },
    { key: "profitability", label: "Profitability (%)", color: "#f2d795" },
  ] as const;
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const baseline = height - padding.bottom;
  const seriesMax = Object.fromEntries(series.map(({ key }) => [key, Math.max(...data.map((row) => row[key] ?? 0), 1)])) as Record<typeof series[number]["key"], number>;
  const groupWidth = chartWidth / data.length;
  const barWidth = Math.min(26, (groupWidth * 0.78) / series.length);
  const x = (index: number, seriesIndex: number) => padding.left + index * groupWidth + (groupWidth - barWidth * series.length) / 2 + seriesIndex * barWidth;
  const barHeight = (key: typeof series[number]["key"], value: number) => (value / seriesMax[key]) * chartHeight;
  return <div className="annual-chart" aria-label="Annual Revenue, Earnings, and Profitability bar chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img">
      <line x1={padding.left} x2={width - padding.right} y1={baseline} y2={baseline} stroke="#303a38" />
      {data.map((row, index) => <text key={row.fiscal_year} x={padding.left + index * groupWidth + groupWidth / 2} y={height - 8} textAnchor="middle" fill="#aab9b5" fontSize="11">{row.fiscal_year}</text>)}
      {data.flatMap((row, index) => series.map(({ key, color }, seriesIndex) => {
        const value = row[key];
        if (value === null) return null;
        const h = barHeight(key, value);
        return <rect key={`${row.fiscal_year}-${key}`} x={x(index, seriesIndex)} y={baseline - h} width={barWidth - 2} height={h} rx="2" fill={color}><title>{`${row.fiscal_year} ${key}: ${value}`}</title></rect>;
      }))}
    </svg>
    <div className="annual-chart-legend">{series.map(({ key, label, color }) => <span key={key}><i style={{ backgroundColor: color }} />{label}</span>)}</div>
  </div>;
}

export function LongTermWorkspace({ items = [], publishedAt = "Unavailable", objective: controlledObjective, onObjectiveChange }: { items?: Company[]; publishedAt?: string; objective?: Objective; onObjectiveChange?: (objective: Objective) => void }) {
  const [localObjective, setLocalObjective] = useState<Objective>("growth");
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    setSelected((current) => items.some((company) => company.symbol === current) ? current : items[0]?.symbol ?? null);
  }, [items]);
  const objective = controlledObjective ?? localObjective;
  const setObjective = (next: Objective) => { setLocalObjective(next); onObjectiveChange?.(next); };
  const selectedCompany = items.find((company) => company.symbol === selected) ?? items[0];
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
            <AnnualDimensionChart data={annualData} />
            <h3>Annual dimensions</h3><ul className="evidence-list">{annualData.map((row) => <li key={row.fiscal_year}><span>{row.fiscal_year}</span><span>Revenue {row.revenue?.toLocaleString() ?? "—"} · Earnings {row.earnings?.toLocaleString() ?? "—"} · Profitability {row.profitability?.toFixed(1) ?? "—"}%</span></li>)}<li><span>Valuation</span><span>Unavailable</span></li></ul>
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
