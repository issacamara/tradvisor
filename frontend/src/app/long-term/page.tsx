"use client";

import { useEffect, useMemo, useState } from "react";
import { InvestorNav } from "@/components/investor-nav";
import { ProtectedWorkspace, useAuthSession } from "@/features/auth/session";
import { LongTermWorkspace } from "@/features/long_term/workspace";
import { apiState, safeApiMessage, type RuntimeDataState } from "@/features/auth/api-error";
import { createApiTransport } from "@/api/transport";
import type { components } from "@/api/generated/schema";

export default function LongTermPage() {
  return <ProtectedWorkspace><LongTermController /></ProtectedWorkspace>;
}

function LongTermController() {
  const session = useAuthSession();
  const api = useMemo(() => createApiTransport(session.request), [session.request]);
  const [objective, setObjective] = useState<"growth" | "dividend">("growth");
  const [items, setItems] = useState<components["schemas"]["LongTermRankedCompany"][]>([]);
  const [publishedAt, setPublishedAt] = useState("Unavailable");
  const [state, setState] = useState<RuntimeDataState>("ready");
  const [message, setMessage] = useState("");
  useEffect(() => { void (async () => {
    try {
      setState("ready");
      const result = await api.request({ method: "get", path: "/v1/long-term/rankings", parameters: { query: { objective, limit: 100 } } });
      setItems(result.data.items); setPublishedAt(result.data.published_at); setMessage("");
    } catch (error) { setState(apiState(error)); setMessage(safeApiMessage(error)); }
  })(); }, [api, objective]);
  return <><InvestorNav active="long-term" />{message && <p role="alert" data-state={state} className="data-alert">{message}</p>}<LongTermWorkspace items={items} publishedAt={publishedAt} objective={objective} onObjectiveChange={setObjective} /></>;
}
