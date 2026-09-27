"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
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
  const [objective, setObjective] = useState<"growth" | "dividend" | "balanced">("growth");
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
  return <><WorkspaceNav />{message && <p role="alert" data-state={state} className="border-b border-warning px-5 py-3 text-sm">{message}</p>}<LongTermWorkspace items={items} publishedAt={publishedAt} objective={objective} onObjectiveChange={setObjective} /></>;
}

function WorkspaceNav() { return <nav aria-label="Investor workspaces" className="flex gap-4 border-b border-line px-5 py-3 text-sm"><Link href="/swing/" className="text-muted">Swing</Link><Link href="/long-term/" aria-current="page" className="font-semibold text-accent">Long-Term</Link><Link href="/paper/" className="text-muted">Paper</Link></nav>; }
