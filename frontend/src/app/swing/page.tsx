"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ProtectedWorkspace, useAuthSession } from "@/features/auth/session";
import { SwingWorkspace } from "@/features/swing/workspace";
import { safeApiMessage } from "@/features/auth/api-error";

export default function SwingPage() {
  return <ProtectedWorkspace><SwingController /></ProtectedWorkspace>;
}

function SwingController() {
  const session = useAuthSession();
  const [data, setData] = useState<{ items: never[]; chart: never[]; marketSession: string }>({ items: [], chart: [], marketSession: "Unavailable" });
  const [message, setMessage] = useState("");
  useEffect(() => { void (async () => {
    try {
      const response = await session.request("/v1/swing/recommendations?limit=100");
      if (!response.ok) throw new Error(`Swing data unavailable (${response.status}).`);
      const result = await response.json() as { data: { items: never[]; market_session: string } };
      setData({ items: result.data.items, chart: [], marketSession: result.data.market_session }); setMessage("");
    } catch (error) { setMessage(safeApiMessage(error)); }
  })(); }, [session]);
  return <><WorkspaceNav active="swing" />{message && <p role="alert" className="border-b border-warning px-5 py-3 text-sm">{message}</p>}<SwingWorkspace {...data} /></>;
}

function WorkspaceNav({ active }: { active: "swing" | "long-term" | "paper" }) { return <nav aria-label="Investor workspaces" className="flex gap-4 border-b border-line px-5 py-3 text-sm">{([["swing", "/swing/", "Swing"], ["long-term", "/long-term/", "Long-Term"], ["paper", "/paper/", "Paper"]] as const).map(([id, href, label]) => <Link key={id} aria-current={active === id ? "page" : undefined} href={href} className={active === id ? "font-semibold text-accent" : "text-muted"}>{label}</Link>)}</nav>; }
