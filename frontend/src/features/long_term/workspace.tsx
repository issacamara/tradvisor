"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { components } from "@/api/generated/schema";
import styles from "./workspace.module.css";

type Company = components["schemas"]["LongTermRankedCompany"];
type Objective = "growth" | "dividend";
type Metric = components["schemas"]["ScoreMetric"];

const label = (value: string) => value.replaceAll("_", " ");
const statusLabel = (status: string) => status === "assessable" ? "Complete" : label(status);
const dateText = (value: string | null) => {
  if (!value) return "Date unavailable";
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" }).format(date);
};
const moneyText = (value: number | string | null, compact = false) => {
  if (value === null) return "Not reported";
  const formatter = new Intl.NumberFormat(undefined, { notation: compact ? "compact" : "standard", maximumFractionDigits: compact ? 1 : 0 });
  const amount = typeof value === "number" ? formatter.format(value) : /^-?\d+$/.test(value) ? formatter.format(BigInt(value)) : value;
  return `${amount} XOF`;
};
const scoreText = (metric: Metric) => metric.value === null || metric.status !== "assessable" ? "—" : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(metric.value)} / 100`;
const metricStatus = (metric: Metric) => statusLabel(metric.status);
const score = (company: Company, objective: Objective) => objective === "growth" ? company.growth.growth_score : company.dividend_research.dividend_score;

function AnnualDimensionChart({ data }: { data: Company["growth"]["annual_dimensions"] }) {
  if (!data.length) return <p className={styles.empty}>No annual financial observations are available.</p>;
  const width = 760;
  const height = 220;
  const padding = { top: 16, right: 18, bottom: 30, left: 18 };
  const series = [{ key: "revenue", label: "Revenue", color: "#4e9bae" }, { key: "earnings", label: "Earnings", color: "#29c98b" }] as const;
  const values = data.flatMap((row) => [row.revenue, row.earnings]).filter((value): value is number => value !== null);
  const min = Math.min(0, ...values);
  const max = Math.max(1, ...values);
  const chartHeight = height - padding.top - padding.bottom;
  const y = (value: number) => padding.top + ((max - value) / (max - min || 1)) * chartHeight;
  const baseline = y(0);
  const groupWidth = (width - padding.left - padding.right) / data.length;
  const barWidth = Math.min(28, groupWidth * 0.32);
  return <div className={styles.chartBlock}>
    <svg className={styles.chart} viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="annual-chart-title annual-chart-description">
      <title id="annual-chart-title">Annual revenue and earnings</title>
      <desc id="annual-chart-description">Published annual values in XOF. A table below provides the exact figures and missing fields.</desc>
      <line x1={padding.left} x2={width - padding.right} y1={baseline} y2={baseline} className={styles.chartBaseline} />
      {data.map((row, index) => <text key={row.fiscal_year} x={padding.left + groupWidth * index + groupWidth / 2} y={height - 7} textAnchor="middle" className={styles.chartYear}>{row.fiscal_year}</text>)}
      {data.flatMap((row, index) => series.map(({ key, color }, seriesIndex) => {
        const value = row[key];
        if (value === null) return null;
        const valueY = y(value);
        const x = padding.left + groupWidth * index + groupWidth / 2 + (seriesIndex === 0 ? -barWidth - 2 : 2);
        const barY = Math.min(valueY, baseline);
        const barHeight = Math.max(1, Math.abs(baseline - valueY));
        return <rect key={`${row.fiscal_year}-${key}`} x={x} y={barY} width={barWidth} height={barHeight} rx="2" fill={color}>
          <title>{`${row.fiscal_year} ${key}: ${moneyText(value)}`}</title>
        </rect>;
      }))}
    </svg>
    <div className={styles.legend} aria-hidden="true"><span><i className={styles.revenueMark} />Revenue</span><span><i className={styles.earningsMark} />Earnings</span><span>Annual values · XOF</span></div>
  </div>;
}

export function LongTermWorkspace({ items = [], publishedAt = "Unavailable", objective: controlledObjective, selectedSymbol, onObjectiveChange, onSymbolChange }: { items?: Company[]; publishedAt?: string; objective?: Objective; selectedSymbol?: string | null; onObjectiveChange?: (objective: Objective) => void; onSymbolChange?: (symbol: string) => void }) {
  const [localObjective, setLocalObjective] = useState<Objective>("growth");
  const [localSelected, setLocalSelected] = useState<string | null>(null);
  const tabRefs = useRef<Record<Objective, HTMLButtonElement | null>>({ growth: null, dividend: null });
  useEffect(() => {
    setLocalSelected((current) => items.some((company) => company.symbol === current) ? current : items[0]?.symbol ?? null);
  }, [items]);
  const objective = controlledObjective ?? localObjective;
  const selected = selectedSymbol ?? localSelected;
  const selectedCompany = items.find((company) => company.symbol === selected) ?? items[0];
  const selectedScore = selectedCompany ? score(selectedCompany, objective) : null;
  const setObjective = (next: Objective) => { setLocalObjective(next); onObjectiveChange?.(next); };
  const setSelected = (symbol: string) => { setLocalSelected(symbol); onSymbolChange?.(symbol); };
  const moveTab = (event: KeyboardEvent, next: Objective) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight" || event.key === "Home" || event.key === "End") {
      event.preventDefault();
      tabRefs.current[next]?.focus();
      setObjective(next);
    }
  };
  const annualData = selectedCompany?.growth.annual_dimensions ?? [];
  const objectiveName = objective === "growth" ? "Growth" : "Dividend research";

  return <main className={styles.page}>
    <header className={styles.heading}>
      <div><p className={styles.eyebrow}>LONG-TERM <span aria-hidden="true">/</span> COMPANY RESEARCH</p><h1>Growth &amp; dividend research</h1><p className={styles.subtitle}>Published company evidence · separate objectives</p></div>
      <p className={styles.published}>Published <strong>{dateText(publishedAt)}</strong></p>
    </header>
    <div className={styles.summary} aria-label="Selected research context">
      <div><span>Companies</span><strong>{items.length}</strong><small>All published companies</small></div>
      <div><span>Selected company</span><strong>{selectedCompany?.symbol ?? "—"}</strong><small>{objectiveName}</small></div>
      <div><span>{objective === "growth" ? "Growth score" : "Dividend score"}</span><strong>{selectedScore ? scoreText(selectedScore) : "—"}</strong><small>{selectedScore ? metricStatus(selectedScore) : "No published score"}</small></div>
    </div>
    <div className={styles.tabs} role="tablist" aria-label="Research objective">
      <button ref={(element) => { tabRefs.current.growth = element; }} id="growth-tab" type="button" role="tab" tabIndex={objective === "growth" ? 0 : -1} aria-controls="research-panel" aria-selected={objective === "growth"} onKeyDown={(event) => moveTab(event, event.key === "Home" ? "growth" : "dividend")} onClick={() => setObjective("growth")}>Growth scores</button>
      <button ref={(element) => { tabRefs.current.dividend = element; }} id="dividend-tab" type="button" role="tab" tabIndex={objective === "dividend" ? 0 : -1} aria-controls="research-panel" aria-selected={objective === "dividend"} onKeyDown={(event) => moveTab(event, event.key === "End" ? "dividend" : "growth")} onClick={() => setObjective("dividend")}>Dividend research</button>
    </div>
    <div className={styles.grid}>
      <section className={styles.coverage} aria-label="Company coverage">
        <div className={styles.panelHeading}><div><h2>Company coverage</h2><p>{objective === "growth" ? "Ranked by published Growth research" : "Payment facts and coverage status"}</p></div><span>{items.length} {items.length === 1 ? "company" : "companies"}</span></div>
        {items.length > 0 && <div className={styles.tableWrap}><table className={styles.coverageTable}><caption className={styles.srOnly}>Company ranking and score status</caption><thead><tr><th scope="col">Company</th><th scope="col">Score</th><th scope="col">Status</th></tr></thead><tbody>
          {items.map((company) => {
            const metric = score(company, objective);
            const isSelected = company.symbol === selectedCompany?.symbol;
            return <tr key={company.company_id} className={`${styles.companyRow} ${isSelected ? styles.selected : ""}`} aria-selected={isSelected}>
              <th scope="row"><button type="button" className={styles.companySelect} aria-current={isSelected ? "true" : undefined} onClick={() => setSelected(company.symbol)}>{company.symbol}</button></th>
              <td className={styles.companyScore}>{scoreText(metric)}</td>
              <td><span className={metric.status === "assessable" ? styles.complete : styles.incomplete}>{metricStatus(metric)}</span></td>
            </tr>;
          })}
        </tbody></table></div>}
        {!items.length && <p className={styles.empty}>No published company research yet.</p>}
      </section>
      <section className={styles.evidence} id="research-panel" role="tabpanel" aria-labelledby={objective === "growth" ? "growth-tab" : "dividend-tab"} aria-label={`${objectiveName} evidence`}>
        {selectedCompany ? <>
          <header className={styles.evidenceHeading}><div><p className={styles.eyebrow}>{objective === "growth" ? "ANNUAL GROWTH EVIDENCE" : "RECORDED DIVIDEND FACTS"}</p><h2>{selectedCompany.symbol}</h2></div><span className={`${styles.status} ${selectedScore?.status === "assessable" ? styles.complete : styles.incomplete}`}>{selectedScore ? metricStatus(selectedScore) : "Unavailable"}</span></header>
          <div className={styles.scoreLine}><span>{objective === "growth" ? "Growth score" : "Dividend research score"}</span><strong>{selectedScore ? scoreText(selectedScore) : "—"}</strong></div>
          {objective === "growth" ? <>
            <p className={styles.statusNote}>{selectedScore?.status === "assessable" ? "Published score with supporting annual evidence." : `Score ${selectedScore ? metricStatus(selectedScore) : "unavailable"}; no value is inferred from partial inputs.`}</p>
            <div className={styles.dimensionGrid} aria-label="Published Growth dimensions">{Object.entries(selectedCompany.growth.dimension_contributions).map(([name, metric]) => <div key={name} className={styles.dimension}><span>{label(name)}</span><strong>{scoreText(metric)}</strong><small className={metric.status === "assessable" ? styles.complete : styles.incomplete}>{metricStatus(metric)}</small></div>)}</div>
            <h3>Annual financial evidence</h3>
            <AnnualDimensionChart data={annualData} />
            <div className={styles.tableWrap}><table className={styles.evidenceTable}><caption className={styles.srOnly}>Published annual revenue, earnings and profitability</caption><thead><tr><th scope="col">Fiscal year</th><th scope="col">Revenue · XOF</th><th scope="col">Earnings · XOF</th><th scope="col">Profitability</th></tr></thead><tbody>{annualData.map((row) => <tr key={row.fiscal_year}><th scope="row">{row.fiscal_year}</th><td>{moneyText(row.revenue)}</td><td>{moneyText(row.earnings)}</td><td>{row.profitability === null ? "Not reported" : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(row.profitability)}%`}</td></tr>)}</tbody></table></div>
            {!annualData.length && <p className={styles.empty}>No annual financial observations are available.</p>}
          </> : <>
            <p className={styles.statusNote}>Dividend and Balanced composite scores and suitability rankings are deferred. This view reports only source-backed payment facts and coverage.</p>
            <h3>Coverage</h3>
            {selectedCompany.dividend_research.coverage.length ? <div className={styles.tableWrap}><table className={styles.evidenceTable}><caption className={styles.srOnly}>Published dividend evidence coverage</caption><thead><tr><th scope="col">Coverage</th><th scope="col">Interval</th><th scope="col">Status</th></tr></thead><tbody>{selectedCompany.dividend_research.coverage.map((coverage) => <tr key={`${coverage.coverage_basis}-${coverage.covered_interval_start}`}><th scope="row">{label(coverage.coverage_basis)}</th><td>{dateText(coverage.covered_interval_start)} – {dateText(coverage.covered_interval_end)}</td><td>{label(coverage.coverage_status)}</td></tr>)}</tbody></table></div> : <p className={styles.empty}>Dividend coverage is not reported.</p>}
            <h3>Payment facts</h3>
            {selectedCompany.dividend_research.payments.length ? <div className={styles.tableWrap}><table className={styles.evidenceTable}><caption className={styles.srOnly}>Recorded dividend payment facts</caption><thead><tr><th scope="col">Payment date</th><th scope="col">Type &amp; status</th><th scope="col">Gross / share · XOF</th><th scope="col">Net / share · XOF</th></tr></thead><tbody>{selectedCompany.dividend_research.payments.map((payment) => <tr key={payment.dividend_id}><th scope="row">{dateText(payment.payment_date)}</th><td>{label(payment.dividend_type)} · {label(payment.payment_status)}</td><td>{payment.gross_amount_per_share ? moneyText(payment.gross_amount_per_share.amount) : "Not reported"}</td><td>{payment.net_amount_per_share ? moneyText(payment.net_amount_per_share.amount) : "Not reported"}</td></tr>)}</tbody></table></div> : <p className={styles.empty}>No dividend payment facts supplied.</p>}
          </>}
        </> : <><h2>No company selected</h2><p className={styles.empty}>Published company evidence will appear here when available.</p></>}
      </section>
    </div>
    <p className={styles.footnote}>Published research is evidence, not a suitability assessment. Revenue and earnings are distinct measures.</p>
  </main>;
}
