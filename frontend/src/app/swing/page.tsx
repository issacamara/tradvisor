"use client";

import { useEffect, useMemo, useState } from "react";
import { InvestorNav } from "@/components/investor-nav";
import { ProtectedWorkspace, useAuthSession } from "@/features/auth/session";
import { SwingWorkspace } from "@/features/swing/workspace";
import { apiState, safeApiMessage, type RuntimeDataState } from "@/features/auth/api-error";
import { createApiTransport } from "@/api/transport";
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
  const [marketSession, setMarketSession] = useState("Unavailable");
  const [state, setState] = useState<RuntimeDataState>("ready");
  const [message, setMessage] = useState("");
  useEffect(() => { void (async () => {
    try {
      setState("ready");
      const result = await api.request({ method: "get", path: "/v1/swing/recommendations", parameters: { query: { limit: 100 } } });
      setItems(result.data.items);
      setMarketSession(result.data.market_session);
      setSelectedSymbol((current) => result.data.items.some((item) => item.symbol === current) ? current : result.data.items[0]?.symbol ?? null);
      setMessage("");
    } catch (error) { setState(apiState(error)); setMessage(safeApiMessage(error)); }
  })(); }, [api]);
  useEffect(() => { void (async () => {
    if (!selectedSymbol || marketSession === "Unavailable") {
      setChart([]);
      return;
    }
    try {
      const from = new Date(`${marketSession}T00:00:00Z`);
      from.setUTCDate(from.getUTCDate() - 365);
      const chartResult = await api.request({ method: "get", path: "/v1/stocks/{symbol}/chart", parameters: { path: { symbol: selectedSymbol }, query: { from: from.toISOString().slice(0, 10), to: marketSession, series: ["ohlcv"] } } });
      setChart(chartResult.data.points);
    } catch (error) { setChart([]); setState(apiState(error)); setMessage(safeApiMessage(error)); }
  })(); }, [api, marketSession, selectedSymbol]);
  return <><InvestorNav active="swing" />{message && <p role="alert" data-state={state} className="data-alert">{message}</p>}<SwingWorkspace items={items} chart={chart} marketSession={marketSession} selectedSymbol={selectedSymbol} onSymbolChange={setSelectedSymbol} /></>;
}
