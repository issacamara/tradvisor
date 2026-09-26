import Link from "next/link";
import { ProtectedWorkspace } from "@/features/auth/session";
import { PaperWorkspace } from "@/features/paper/views/workspace";
import { PaperCommands } from "@/features/paper/commands/paper-commands";

export default function PaperPage() {
  return <ProtectedWorkspace><><WorkspaceNav /><PaperCommands setupRequired /><PaperWorkspace /></></ProtectedWorkspace>;
}

function WorkspaceNav() { return <nav aria-label="Investor workspaces" className="flex gap-4 border-b border-line px-5 py-3 text-sm"><Link href="/swing/" className="text-muted">Swing</Link><Link href="/long-term/" className="text-muted">Long-Term</Link><Link href="/paper/" aria-current="page" className="font-semibold text-accent">Paper</Link></nav>; }
