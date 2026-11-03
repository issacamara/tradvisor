"use client";

import { useEffect, useMemo, useState } from "react";
import { InvestorNav } from "@/components/investor-nav";
import { Button } from "@/components/ui/button";
import { ProtectedWorkspace, useAuthSession } from "@/features/auth/session";
import { SwingWorkspace } from "@/features/swing/workspace";
import { chartAvailability, chartFailureAvailability, chartPublicationAvailability, type ChartAvailability } from "@/features/swing/chart-state";
import { apiState, safeApiMessage, type RuntimeDataState } from "@/features/auth/api-error";
import { ApiRequestError, createApiTransport } from "@/api/transport";
import type { components } from "@/api/generated/schema";

export default function SwingPage() {
  return <ProtectedWorkspace><SwingController /></ProtectedWorkspace>;
}

function SwingController() {
  const session = useAuthSession();
  const api = useMemo(() => createApiTransport(session.request), [session.request]);
  const [items, setItems] = useState<components["schemas"]["SwingRecommendation"][]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [chart, setChart] = useState<components["schemas"]["ChartPoint"][]>([]);
  const [chartState, setChartState] = useState<ChartAvailability>("empty");
  const [marketSession, setMarketSession] = useState("Unavailable");
  const [resultsState, setResultsState] = useState<"loading" | "published" | "no_publication" | "unavailable" | "request_failure">("loading");
  const [state, setState] = useState<RuntimeDataState>("ready");
  const [message, setMessage] = useState("");
  const [retryable, setRetryable] = useState(false);
  const [requestAttempt, setRequestAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setState("ready");
    setMessage("");
    setRetryable(false);
    setResultsState("loading");
    setItems([]);
    setSelectedSymbol(null);
    setMarketSession("Unavailable");
    void (async () => {
    try {
      const result = await api.request({ method: "get", path: "/v1/swing/recommendations", parameters: { query: { limit: 100 } } });
      if (!active) return;
      setItems(result.data.items);
      setResultsState(result.data.items.length ? "published" : "no_publication");
      setMarketSession(result.data.market_session);
      setSelectedSymbol((current) => result.data.items.some((item) => item.symbol === current) ? current : result.data.items[0]?.symbol ?? null);
      setMessage("");
    } catch (error) {
      if (!active) return;
      const errorState = apiState(error);
      setState(errorState);
      setResultsState(errorState === "analysis_not_ready" ? "unavailable" : "request_failure");
      setSelectedSymbol(null);
      setMarketSession("Unavailable");
      setMessage(errorState === "transport_error" ? "Swing recommendations could not be loaded. Try again later." : safeApiMessage(error));
      setRetryable(error instanceof ApiRequestError && error.retryable === true);
    }
    })();
    return () => { active = false; };
  }, [api, requestAttempt]);
  useEffect(() => {
    let active = true;
    if (!selectedSymbol || marketSession === "Unavailable") {
      setChart([]);
      setChartState(chartPublicationAvailability(resultsState));
      return () => { active = false; };
    }
    setChart([]);
    setChartState("loading");
    void (async () => {
    try {
      const from = new Date(`${marketSession}T00:00:00Z`);
      from.setUTCDate(from.getUTCDate() - 365);
      const chartResult = await api.request({ method: "get", path: "/v1/stocks/{symbol}/chart", parameters: { path: { symbol: selectedSymbol }, query: { from: from.toISOString().slice(0, 10), to: marketSession, series: ["ohlcv"] } } });
      if (!active) return;
      setChart(chartResult.data.points);
      setChartState(chartAvailability(chartResult.data.points));
    } catch (error) { if (!active) return; setChart([]); setChartState(chartFailureAvailability(error)); }
    })();
    return () => { active = false; };
  }, [api, marketSession, selectedSymbol, resultsState]);
  return <><InvestorNav active="swing" />{message && <div role="alert" data-state={state} className="data-alert"><span>{message}</span>{retryable && <Button type="button" onClick={() => setRequestAttempt((current) => current + 1)}>Try again</Button>}</div>}<SwingWorkspace items={items} chart={chart} chartState={chartState} marketSession={marketSession} resultsState={resultsState} selectedSymbol={selectedSymbol} onSymbolChange={setSelectedSymbol} /></>;
}
