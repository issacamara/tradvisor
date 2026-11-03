"use client";

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { components } from "@/api/generated/schema";
import { SwingChart } from "./swing-chart";
import type { ChartAvailability } from "./chart-state";
import styles from "./recommendations.module.css";

type Recommendation = components["schemas"]["SwingRecommendation"];
type ChartPoint = components["schemas"]["ChartPoint"];
type ResultsState = "loading" | "published" | "no_publication" | "unavailable" | "request_failure";
type Props = { items?: Recommendation[]; chart?: ChartPoint[]; chartState?: ChartAvailability; marketSession?: string; resultsState?: ResultsState; selectedSymbol?: string | null; onSymbolChange?: (symbol: string) => void };
const label = (value: string) => value.replaceAll("_", " ");
const strength = (item: Recommendation) => item.buy_strength.value === null ? "—" : `${item.buy_strength.value.toFixed(0)} / 100`;

export function SwingWorkspace({ items = [], chart = [], chartState = "empty", marketSession = "Unavailable", resultsState = "no_publication", selectedSymbol = null, onSymbolChange }: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "buy">("all");
  const selected = selectedSymbol ?? items[0]?.symbol ?? null;
  const filtered = useMemo(() => items.filter((item) => item.symbol.toLowerCase().includes(query.trim().toLowerCase()) && (filter === "all" || item.entry_action === "buy")), [items, query, filter]);
  const detail = items.find((item) => item.symbol === selected);
  const buyCount = items.filter((item) => item.entry_action === "buy").length;

  useEffect(() => {
    if (filtered.length && !filtered.some((item) => item.symbol === selected)) onSymbolChange?.(filtered[0].symbol);
  }, [filtered, selected, onSymbolChange]);

  return <main className="workspace-page">
    <header className="page-heading">
      <div><p className="eyebrow">SWING <span aria-hidden="true">/</span> DAILY RESEARCH</p><h1>Published recommendations</h1><p className="page-subtitle">Inspect the action, then review the evidence behind it.</p></div>
      <div className="session-stamp"><span className="session-dot" aria-hidden="true" /> Market session <strong>{marketSession}</strong></div>
    </header>
    <section className="summary-strip" aria-label="Screener summary">
      <div><span>Covered stocks</span><strong>{items.length}</strong></div>
      <div><span>Buy entries</span><strong className="text-accent">{buyCount}</strong></div>
      <div><span>Selected stock</span><strong>{selected ?? "—"}</strong></div>
    </section>
    <div className="research-grid">
      <section className="screener-list" aria-label="Swing recommendations">
        <div className="panel-heading"><div><h2>Market list</h2><p>All returned stocks · counts from this publication</p></div><span className="row-count">{filtered.length} stocks</span></div>
        <div className="list-tools">
          <label className="search-field"><Search size={16} aria-hidden="true" /><span className="sr-only">Search symbol</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search symbol" /></label>
          <div className="segmented" aria-label="Entry filter"><button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All {items.length}</button><button type="button" aria-pressed={filter === "buy"} onClick={() => setFilter("buy")}>Buy {buyCount}</button></div>
        </div>
        <ul className={styles.recommendationList} aria-label="Published recommendation results">
          {filtered.map((item) => <li key={item.symbol}><button type="button" className={styles.recommendation} aria-pressed={item.symbol === selected} onClick={() => onSymbolChange?.(item.symbol)}>
            <span className={styles.recommendationTop}><strong>{item.symbol}</strong><span className={`signal signal-${item.entry_action}`}>{label(item.entry_action)}</span><strong className={styles.score}>{strength(item)}</strong></span>
            <span className={styles.recommendationMeta}><span>{item.buy_strength.value === null ? label(item.buy_strength.status) : "Buy strength · rule score"}</span><span>{item.buy_strength.effective_date ?? "Effective date unavailable"}</span></span>
          </button></li>)}
        </ul>
        {!items.length && resultsState === "loading" && <p className="empty-message">Loading published Swing recommendations…</p>}
        {!items.length && resultsState === "no_publication" && <p className="empty-message">No published Swing recommendations yet.</p>}
        {!items.length && resultsState === "unavailable" && <p className="empty-message">The latest analytical publication is unavailable.</p>}
        {!items.length && resultsState === "request_failure" && <p className="empty-message">Swing recommendations could not be loaded. Try again later.</p>}
        {items.length > 0 && filter === "buy" && !buyCount && !query.trim() && <p className="empty-message">No Buy entries in this publication.</p>}
        {items.length > 0 && !filtered.length && (filter !== "buy" || buyCount > 0 || query.trim()) && <p className="empty-message">No symbols match this filter.</p>}
      </section>
      <div className="research-detail">
        <section className={styles.selectedSummary} aria-label="Selected recommendation summary">
          <div className={styles.selectedHeading}><div><p className="eyebrow">SELECTED RECOMMENDATION</p><h2>{detail?.symbol ?? "No stock selected"}</h2></div>{detail && <span className={`signal signal-${detail.entry_action}`}>{label(detail.entry_action)}</span>}</div>
          {detail ? <dl><div><dt>Buy strength</dt><dd>{strength(detail)}{detail.buy_strength.value === null && <small>{label(detail.buy_strength.status)}</small>}</dd></div><div><dt>Effective date</dt><dd>{detail.buy_strength.effective_date ?? "Unavailable"}</dd></div></dl> : <p className="empty-message">Select a stock to review the recommendation.</p>}
        </section>
        <section className="price-section" aria-label="Price history">
          <div className="detail-heading"><div><p className="eyebrow">PRICE HISTORY</p><h2>{selected ?? "Select a stock"}</h2></div><label className="symbol-select">Symbol<select aria-label="Chart symbol" value={selected ?? ""} onChange={(event) => onSymbolChange?.(event.target.value)} disabled={!items.length}>{!items.length && <option value="">No symbols</option>}{items.map((item) => <option key={item.symbol} value={item.symbol}>{item.symbol}</option>)}</select></label></div>
          <SwingChart points={chart} availability={chartState} />
        </section>
        <section className="evidence-section" aria-label="Selected recommendation detail">
          <div className="detail-heading"><div><p className="eyebrow">RECOMMENDATION EVIDENCE</p><h2>{detail?.symbol ?? "No stock selected"}</h2></div>{detail && <span className={`signal signal-${detail.entry_action}`}>{label(detail.entry_action)}</span>}</div>
          {detail ? <><div className="evidence-summary"><div><span>Entry strength</span><strong>{strength(detail)}</strong></div></div><p className="evidence-note">Strength is a rule score, not a probability. A non-Buy result is not a Sell instruction.</p><h3>Eligibility</h3><ul className="evidence-list">{detail.eligibility_guards.map((guard) => <li key={guard.code}><span>{label(guard.code)}</span><span>{guard.status}{guard.observed !== null ? ` · ${guard.observed}` : ""}</span></li>)}</ul></> : <p className="empty-message">Select a stock to review the evidence.</p>}
        </section>
      </div>
    </div>
    <p className="workspace-footnote">Market recommendations are shared research, not trading instructions.</p>
  </main>;
}
