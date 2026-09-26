"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ProtectedWorkspace, useAuthSession } from "@/features/auth/session";
import { LongTermWorkspace } from "@/features/long_term/workspace";
import { safeApiMessage } from "@/features/auth/api-error";

export default function LongTermPage() {
  return <ProtectedWorkspace><LongTermController /></ProtectedWorkspace>;
}

function LongTermController() {
  const session = useAuthSession();
  const [items, setItems] = useState<never[]>([]);
  const [publishedAt, setPublishedAt] = useState("Unavailable");
  const [message, setMessage] = useState("");
  useEffect(() => { void (async () => {
    try {
      const response = await session.request("/v1/long-term/rankings?objective=growth&limit=100");
      if (!response.ok) throw new Error(`Long-Term data unavailable (${response.status}).`);
      const result = await response.json() as { data: { items: never[]; published_at: string } };
      setItems(result.data.items); setPublishedAt(result.data.published_at); setMessage("");
    } catch (error) { setMessage(safeApiMessage(error)); }
  })(); }, [session]);
  return <><WorkspaceNav />{message && <p role="alert" className="border-b border-warning px-5 py-3 text-sm">{message}</p>}<LongTermWorkspace items={items} publishedAt={publishedAt} /></>;
}

function WorkspaceNav() { return <nav aria-label="Investor workspaces" className="flex gap-4 border-b border-line px-5 py-3 text-sm"><Link href="/swing/" className="text-muted">Swing</Link><Link href="/long-term/" aria-current="page" className="font-semibold text-accent">Long-Term</Link><Link href="/paper/" className="text-muted">Paper</Link></nav>; }
