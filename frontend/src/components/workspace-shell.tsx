"use client";

import React from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Menu, PanelLeft, Search } from "lucide-react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const ChartPlaceholder = dynamic(() => import("@/components/chart-placeholder").then((module) => module.ChartPlaceholder), { ssr: false, loading: () => <div className="min-h-40 animate-pulse rounded-md bg-white/5" aria-label="Loading charts" /> });

const views = [
  { id: "overview", label: "Overview", href: "/" },
  { id: "swing", label: "Swing", href: "/swing/" },
  { id: "long-term", label: "Long-Term", href: "/long-term/" },
  { id: "paper", label: "Paper", href: "/paper/" },
] as const;

type Workspace = (typeof views)[number]["id"];

const copy: Record<Workspace, { title: string; description: string; status: string }> = {
  overview: { title: "Investor workspace", description: "A static, local-data shell for daily research and manual paper trading.", status: "Local placeholders" },
  swing: { title: "Swing research", description: "Market recommendations, indicator evidence, and readable chart context will appear here.", status: "No market data loaded" },
  "long-term": { title: "Long-Term research", description: "Growth ranking and dividend research will remain distinct, with coverage states shown directly.", status: "No research data loaded" },
  paper: { title: "Paper trading", description: "Manual recommendation-linked orders and simulated positions will be available after protected API integration.", status: "No paper account loaded" },
};

function Sidebar({ workspace }: { workspace: Workspace }) {
  return <nav aria-label="Investor workspaces" className="flex h-full flex-col gap-1 p-3">
    <span className="mb-4 px-2 text-sm font-bold tracking-wide text-accent">TRADVISOR</span>
    {views.map((view) => <Link key={view.id} href={view.href} aria-current={view.id === workspace ? "page" : undefined} className={`rounded-md px-3 py-2 text-sm ${view.id === workspace ? "bg-accent/15 font-semibold text-accent" : "text-muted hover:bg-white/5 hover:text-ink"}`}>{view.label}</Link>)}
  </nav>
}

export function WorkspaceShell({ workspace }: { workspace: Workspace }) {
  const current = copy[workspace];
  return (
    <main className="min-h-screen bg-canvas">
      <header className="flex min-h-16 items-center justify-between border-b border-line px-4 lg:px-6">
        <div className="flex items-center gap-3"><Button className="lg:hidden" aria-label="Open workspace navigation"><Menu size={18} /></Button><span className="font-bold text-accent lg:hidden">TRADVISOR</span><span className="hidden text-sm text-muted sm:inline">BRVM investor research</span></div>
        <div className="flex items-center gap-2"><Badge tone="warning">Static preview</Badge><Button aria-label="Search stocks"><Search size={18} /></Button></div>
      </header>
      <div className="hidden min-h-[calc(100vh-4rem)] lg:block">
        <PanelGroup direction="horizontal" aria-label="Resizable investor workspace">
          <Panel defaultSize={18} minSize={14} maxSize={28} className="border-r border-line bg-panel"><Sidebar workspace={workspace} /></Panel>
          <PanelResizeHandle className="w-1 bg-line focus-visible:bg-warning" aria-label="Resize navigation panel" />
          <Panel defaultSize={82} minSize={45}><WorkspaceContent current={current} /></Panel>
        </PanelGroup>
      </div>
      <div className="lg:hidden"><nav aria-label="Investor workspaces" className="flex overflow-x-auto border-b border-line px-2 py-2">{views.map((view) => <Link key={view.id} href={view.href} aria-current={view.id === workspace ? "page" : undefined} className={`shrink-0 rounded-md px-3 py-2 text-sm ${view.id === workspace ? "bg-accent/15 text-accent" : "text-muted"}`}>{view.label}</Link>)}</nav><WorkspaceContent current={current} /></div>
    </main>
  );
}

function WorkspaceContent({ current }: { current: { title: string; description: string; status: string } }) {
  return <section className="mx-auto grid max-w-7xl gap-5 p-4 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="mb-1 text-sm text-muted">Research workspace</p><h1 className="text-2xl font-bold">{current.title}</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-muted">{current.description}</p></div><Badge>{current.status}</Badge></div><ChartPlaceholder /><section aria-label="Workspace status" className="grid gap-3 sm:grid-cols-3">{[["Market state", "Awaiting published analysis"], ["Long-Term", "Awaiting ranked research"], ["Paper portfolio", "Awaiting protected account"]].map(([label, value]) => <div key={label} className="rounded-md border border-line bg-panel p-4"><p className="text-sm font-semibold">{label}</p><p className="mt-2 text-sm text-muted">{value}</p></div>)}</section><div className="flex items-center gap-2 text-sm text-muted"><PanelLeft size={16} aria-hidden="true" />Drag the desktop divider to resize the navigation pane.</div></section>;
}
