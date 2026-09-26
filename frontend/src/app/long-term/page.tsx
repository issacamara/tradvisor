import Link from "next/link";
import { ProtectedWorkspace } from "@/features/auth/session";
import { LongTermWorkspace } from "@/features/long_term/workspace";

export default function LongTermPage() {
  return <ProtectedWorkspace><><WorkspaceNav /><LongTermWorkspace /></></ProtectedWorkspace>;
}

function WorkspaceNav() { return <nav aria-label="Investor workspaces" className="flex gap-4 border-b border-line px-5 py-3 text-sm"><Link href="/swing/" className="text-muted">Swing</Link><Link href="/long-term/" aria-current="page" className="font-semibold text-accent">Long-Term</Link><Link href="/paper/" className="text-muted">Paper</Link></nav>; }
