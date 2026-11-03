"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ApiRequestError, createApiTransport } from "@/api/transport";
import { InvestorNav } from "@/components/investor-nav";
import { apiState, safeApiMessage, type RuntimeDataState } from "@/features/auth/api-error";
import { ProtectedWorkspace, useAuthSession } from "@/features/auth/session";
import { LongTermWorkspace } from "@/features/long_term/workspace";
import type { components } from "@/api/generated/schema";

type Objective = "growth" | "dividend";
type Company = components["schemas"]["LongTermRankedCompany"];
const paramsFromLocation = () => typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
const initialObjective = (): Objective => paramsFromLocation().get("objective") === "dividend" ? "dividend" : "growth";

export default function LongTermPage() {
  return <ProtectedWorkspace><LongTermController /></ProtectedWorkspace>;
}

function LongTermController() {
  const session = useAuthSession();
  const api = useMemo(() => createApiTransport(session.request), [session.request]);
  const [objective, setObjective] = useState<Objective>(initialObjective);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(() => paramsFromLocation().get("symbol"));
  const [items, setItems] = useState<Company[]>([]);
  const [publishedAt, setPublishedAt] = useState("Unavailable");
  const [state, setState] = useState<RuntimeDataState | "loading">("loading");
  const [message, setMessage] = useState("");
  const [retryable, setRetryable] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      setState("loading");
      setMessage("");
      setRetryable(false);
      try {
        const result = await api.request({ method: "get", path: "/v1/long-term/rankings", parameters: { query: { objective, limit: 100 } } });
        if (!active) return;
        setItems(result.data.items);
        setPublishedAt(result.data.published_at);
        setSelectedSymbol((current) => result.data.items.some((company) => company.symbol === current) ? current : result.data.items[0]?.symbol ?? null);
        setState("ready");
      } catch (error) {
        if (!active) return;
        setItems([]);
        setPublishedAt("Unavailable");
        setState(apiState(error));
        setMessage(safeApiMessage(error));
        setRetryable(error instanceof ApiRequestError && error.retryable === true);
      }
    })();
    return () => { active = false; };
  }, [api, objective, retryKey]);

  const updateLocation = useCallback((next: { objective?: Objective; symbol?: string }) => {
    const params = paramsFromLocation();
    if (next.objective) params.set("objective", next.objective);
    if (next.symbol) params.set("symbol", next.symbol);
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
  }, []);
  const changeObjective = (value: Objective) => { setObjective(value); updateLocation({ objective: value }); };
  const changeSymbol = (symbol: string) => { setSelectedSymbol(symbol); updateLocation({ symbol }); };

  return <>
    <InvestorNav active="long-term" />
    {state === "loading" && <p role="status" className="data-alert">Loading published research…</p>}
    {message && <div role="alert" data-state={state} className="data-alert"><span>{message}</span>{state === "auth_error" && <Link href="/sign-in">Sign in again</Link>}{retryable && <button type="button" onClick={() => setRetryKey((value) => value + 1)}>Try again</button>}</div>}
    {state === "ready" && <LongTermWorkspace items={items} publishedAt={publishedAt} objective={objective} selectedSymbol={selectedSymbol} onObjectiveChange={changeObjective} onSymbolChange={changeSymbol} />}
  </>;
}
