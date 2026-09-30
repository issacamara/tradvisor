"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { InvestorNav } from "@/components/investor-nav";
import type { components } from "@/api/generated/schema";
import { ProtectedWorkspace, useAuthSession } from "@/features/auth/session";
import { PaperWorkspace } from "@/features/paper/views/workspace";
import { PaperCommands } from "@/features/paper/commands/paper-commands";
import { apiState, safeApiMessage, type RuntimeDataState } from "@/features/auth/api-error";
import { createApiTransport } from "@/api/transport";

export default function PaperPage() {
  return <ProtectedWorkspace><PaperCommandController /></ProtectedWorkspace>;
}

type MeResponse = { data: { portfolio_setup_state: "setup_required" | "configured" }; meta: { recovery_id: string | null } };
type PortfolioResponse = { data: { summary: components["schemas"]["PortfolioResource"]["summary"] } };
type PortfolioEnvelope = { data: components["schemas"]["PortfolioResource"] };
type PageEnvelope<T> = { data: { items: T[]; next_cursor: string | null } };
type MutationResult = "confirmed" | "uncertain" | "error";

function PaperCommandController() {
  const session = useAuthSession();
  const api = useMemo(() => createApiTransport(session.request), [session.request]);
  const [setupRequired, setSetupRequired] = useState(true);
  const [recoveryId, setRecoveryId] = useState<string>();
  const [generation, setGeneration] = useState<string>();
  const [stateVersion, setStateVersion] = useState(0);
  const [portfolio, setPortfolio] = useState<components["schemas"]["PortfolioResource"]>();
  const [orders, setOrders] = useState<components["schemas"]["PaperOrder"][]>([]);
  const [executions, setExecutions] = useState<components["schemas"]["PaperExecution"][]>([]);
  const [movements, setMovements] = useState<components["schemas"]["CashMovement"][]>([]);
  const [refreshState, setRefreshState] = useState<RuntimeDataState>("ready");
  const [refreshMessage, setRefreshMessage] = useState("");

  const refresh = useCallback(async () => {
    const profile = await api.request({ method: "get", path: "/v1/me" }) as MeResponse;
    setSetupRequired(profile.data.portfolio_setup_state === "setup_required");
    setRecoveryId(profile.meta.recovery_id ?? undefined);
    if (profile.data.portfolio_setup_state === "configured") {
      const state = await api.request({ method: "get", path: "/v1/paper/portfolio" }) as PortfolioEnvelope;
      setGeneration(state.data.summary?.generation);
      setStateVersion(state.data.summary?.state_version ?? 0);
      setPortfolio(state.data);
      const [orderResponse, executionResponse, movementResponse] = await Promise.all([
        api.request({ method: "get", path: "/v1/paper/orders", parameters: { query: { limit: 50 } } }),
        api.request({ method: "get", path: "/v1/paper/executions", parameters: { query: { limit: 50 } } }),
        api.request({ method: "get", path: "/v1/paper/cash-movements", parameters: { query: { limit: 50 } } }),
      ]);
      setOrders((orderResponse as PageEnvelope<components["schemas"]["PaperOrder"]>).data.items);
      setExecutions((executionResponse as PageEnvelope<components["schemas"]["PaperExecution"]>).data.items);
      setMovements((movementResponse as PageEnvelope<components["schemas"]["CashMovement"]>).data.items);
    } else {
      setGeneration(undefined);
      setStateVersion(0);
      setPortfolio(undefined); setOrders([]); setExecutions([]); setMovements([]);
    }
    setRefreshState("ready");
    setRefreshMessage("");
  }, [api]);

  useEffect(() => { void refresh().catch((error) => { setRefreshState(apiState(error)); setRefreshMessage(safeApiMessage(error)); }); }, [refresh]);

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

  return <><InvestorNav active="paper" />{refreshMessage && <p role="alert" data-state={refreshState} className="data-alert">{refreshMessage}</p>}<div className="workspace-page"><header className="page-heading paper-heading"><div><p className="eyebrow">SIMULATED INVESTING <span aria-hidden="true">/</span> BRVM</p><h1>Paper portfolio</h1><p className="page-subtitle">Place manual orders linked to published recommendations.</p></div><span className="session-stamp">Simulated account</span></header><PaperCommands
    setupRequired={setupRequired}
    recoveryId={recoveryId ?? "setup-required"}
    generation={generation}
    stateVersion={stateVersion}
    onSetup={(request, key) => mutate("/v1/paper/portfolio", request, key)}
    onOrder={(request, key) => mutate("/v1/paper/orders", request, key)}
    onReset={(request, key) => mutate("/v1/paper/reset", request, key)}
  /><PaperWorkspace portfolio={portfolio} orders={orders} executions={executions} movements={movements} /></div></>;
}
