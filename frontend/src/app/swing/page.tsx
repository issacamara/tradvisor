import Link from "next/link";
import { ProtectedWorkspace } from "@/features/auth/session";
import { SwingWorkspace } from "@/features/swing/workspace";

export default function SwingPage() {
  return <ProtectedWorkspace><><WorkspaceNav active="swing" /><SwingWorkspace /></></ProtectedWorkspace>;
}

function WorkspaceNav({ active }: { active: "swing" | "long-term" | "paper" }) { return <nav aria-label="Investor workspaces" className="flex gap-4 border-b border-line px-5 py-3 text-sm">{([["swing", "/swing/", "Swing"], ["long-term", "/long-term/", "Long-Term"], ["paper", "/paper/", "Paper"]] as const).map(([id, href, label]) => <Link key={id} aria-current={active === id ? "page" : undefined} href={href} className={active === id ? "font-semibold text-accent" : "text-muted"}>{label}</Link>)}</nav>; }
