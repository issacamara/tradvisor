"use client";

import Link from "next/link";
import { BarChart3, ChartNoAxesCombined } from "lucide-react";

const views = [
  { id: "swing", label: "Swing", href: "/swing/", icon: ChartNoAxesCombined },
  { id: "long-term", label: "Long-Term", href: "/long-term/", icon: BarChart3 },
] as const;

export function InvestorNav({ active }: { active: (typeof views)[number]["id"] }) {
  return <header className="app-header">
    <Link href="/swing/" className="brand" aria-label="Tradvisor, Swing workspace">
      <span className="brand-mark" aria-hidden="true">T</span>
      <span>TRADVISOR</span>
    </Link>
    <nav aria-label="Investor workspaces" className="workspace-nav">
      {views.map(({ id, label, href, icon: Icon }) => <Link key={id} href={href} aria-current={active === id ? "page" : undefined} className="workspace-link">
        <Icon size={16} aria-hidden="true" /><span>{label}</span>
      </Link>)}
    </nav>
    <span className="app-market">BRVM <span aria-hidden="true">/</span> XOF</span>
  </header>;
}
