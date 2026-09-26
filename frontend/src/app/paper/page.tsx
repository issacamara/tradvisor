"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { components } from "@/api/generated/schema";
import { ProtectedWorkspace, useAuthSession } from "@/features/auth/session";
import { PaperWorkspace } from "@/features/paper/views/workspace";
import { PaperCommands } from "@/features/paper/commands/paper-commands";

export default function PaperPage() {
  return <ProtectedWorkspace><PaperCommandController /></ProtectedWorkspace>;
}

type MeResponse = { data: { portfolio_setup_state: "setup_required" | "configured" }; meta: { recovery_id: string | null } };
type PortfolioResponse = { data: { summary: components["schemas"]["PortfolioResource"]["summary"] } };
type MutationResult = "confirmed" | "uncertain" | "error";

function PaperCommandController() {
  const session = useAuthSession();
  const [setupRequired, setSetupRequired] = useState(true);
  const [recoveryId, setRecoveryId] = useState<string>();
  const [generation, setGeneration] = useState<string>();
  const [stateVersion, setStateVersion] = useState(0);

  const refresh = useCallback(async () => {
    const me = await session.request("/v1/me");
    if (!me.ok) throw new Error("Current paper state could not be loaded.");
    const profile = await me.json() as MeResponse;
    setSetupRequired(profile.data.portfolio_setup_state === "setup_required");
    setRecoveryId(profile.meta.recovery_id ?? undefined);
    if (profile.data.portfolio_setup_state === "configured") {
      const portfolio = await session.request("/v1/paper/portfolio");
      if (!portfolio.ok) throw new Error("Current paper state could not be loaded.");
      const state = await portfolio.json() as PortfolioResponse;
      setGeneration(state.data.summary?.generation);
      setStateVersion(state.data.summary?.state_version ?? 0);
    } else {
      setGeneration(undefined);
      setStateVersion(0);
    }
  }, [session]);

  useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);

  const mutate = useCallback(async (path: string, body: object, idempotencyKey: string): Promise<MutationResult> => {
    try {
      const response = await session.request(path, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(body),
      });
      if (response.ok) {
        await refresh();
        return "confirmed";
      }
      return response.status === 408 || response.status >= 500 ? "uncertain" : "error";
    } catch {
      return "uncertain";
    }
  }, [refresh, session]);

  return <><WorkspaceNav /><PaperCommands
    setupRequired={setupRequired}
    recoveryId={recoveryId ?? "setup-required"}
    generation={generation}
    stateVersion={stateVersion}
    onSetup={(request, key) => mutate("/v1/paper/portfolio", request, key)}
    onOrder={(request, key) => mutate("/v1/paper/orders", request, key)}
    onReset={(request, key) => mutate("/v1/paper/reset", request, key)}
  /><PaperWorkspace /></>;
}

function WorkspaceNav() { return <nav aria-label="Investor workspaces" className="flex gap-4 border-b border-line px-5 py-3 text-sm"><Link href="/swing/" className="text-muted">Swing</Link><Link href="/long-term/" className="text-muted">Long-Term</Link><Link href="/paper/" aria-current="page" className="font-semibold text-accent">Paper</Link></nav>; }
