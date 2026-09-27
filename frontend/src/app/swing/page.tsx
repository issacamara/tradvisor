"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
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
  const [data, setData] = useState<{ items: components["schemas"]["SwingRecommendation"][]; chart: components["schemas"]["ChartPoint"][]; marketSession: string }>({ items: [], chart: [], marketSession: "Unavailable" });
  const [state, setState] = useState<RuntimeDataState>("ready");
  const [message, setMessage] = useState("");
  useEffect(() => { void (async () => {
    try {
      setState("ready");
      const result = await api.request({ method: "get", path: "/v1/swing/recommendations", parameters: { query: { limit: 100 } } });
      let chart: components["schemas"]["ChartPoint"][] = [];
      const first = result.data.items[0]?.symbol;
      if (first) {
        const to = result.data.market_session;
        const from = new Date(`${to}T00:00:00Z`);
        from.setUTCDate(from.getUTCDate() - 365);
        const chartResult = await api.request({ method: "get", path: "/v1/stocks/{symbol}/chart", parameters: { path: { symbol: first }, query: { from: from.toISOString().slice(0, 10), to, series: ["ohlcv", "ema20", "ema50", "rsi14", "atr14", "traded_value20"] } } });
        chart = chartResult.data.points;
      }
      setData({ items: result.data.items, chart, marketSession: result.data.market_session }); setMessage("");
    } catch (error) { setState(apiState(error)); setMessage(safeApiMessage(error)); }
  })(); }, [api]);
  return <><WorkspaceNav active="swing" />{message && <p role="alert" data-state={state} className="border-b border-warning px-5 py-3 text-sm">{message}</p>}<SwingWorkspace {...data} /></>;
}

function WorkspaceNav({ active }: { active: "swing" | "long-term" | "paper" }) { return <nav aria-label="Investor workspaces" className="flex gap-4 border-b border-line px-5 py-3 text-sm">{([["swing", "/swing/", "Swing"], ["long-term", "/long-term/", "Long-Term"], ["paper", "/paper/", "Paper"]] as const).map(([id, href, label]) => <Link key={id} aria-current={active === id ? "page" : undefined} href={href} className={active === id ? "font-semibold text-accent" : "text-muted"}>{label}</Link>)}</nav>; }
