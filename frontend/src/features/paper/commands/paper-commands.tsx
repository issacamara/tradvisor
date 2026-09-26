"use client";

import { FormEvent, useState } from "react";
import type { components } from "@/api/generated/schema";

type SetupRequest = components["schemas"]["SetupPortfolioRequest"];
type OrderRequest = components["schemas"]["CreatePaperOrderRequest"];
type ResetRequest = components["schemas"]["ResetPortfolioRequest"];
type CommandResult = "idle" | "pending" | "confirmed" | "uncertain" | "error";

type Props = {
  setupRequired: boolean;
  generation?: string;
  stateVersion?: number;
  recoveryId?: string;
  onSetup?(request: SetupRequest): Promise<CommandResult>;
  onOrder?(request: OrderRequest): Promise<CommandResult>;
  onReset?(request: ResetRequest): Promise<CommandResult>;
};

const command = (recoveryId: string, generation?: string, stateVersion = 0) => ({
  issued_at: new Date().toISOString(),
  recovery_id: recoveryId,
  content_length: 0,
  expected_generation: generation ?? null,
  expected_state_version: stateVersion,
});

export function PaperCommands({ setupRequired, generation, stateVersion, recoveryId = "pending-recovery", onSetup, onOrder, onReset }: Props) {
  const [setupCash, setSetupCash] = useState("100000");
  const [feeRate, setFeeRate] = useState("0");
  const [symbol, setSymbol] = useState("");
  const [recommendation, setRecommendation] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [status, setStatus] = useState<CommandResult>("idle");
  const [message, setMessage] = useState("");

  async function submit(action: (() => Promise<CommandResult>) | undefined) {
    if (!action) return;
    setStatus("pending");
    setMessage("");
    try {
      const next = await action();
      setStatus(next);
      setMessage(next === "uncertain" ? "The outcome is uncertain. Refresh the authoritative paper state before retrying." : next === "confirmed" ? "Confirmed by the paper service." : "The command was not confirmed.");
    } catch {
      setStatus("uncertain");
      setMessage("The outcome is uncertain. Refresh the authoritative paper state before retrying.");
    }
  }

  function setup(event: FormEvent) {
    event.preventDefault();
    void submit(onSetup && (() => onSetup({
      fee_rate_pct: feeRate,
      starting_cash: { amount: setupCash, currency: "XOF" },
      command: command(recoveryId),
    })));
  }

  function order(event: FormEvent) {
    event.preventDefault();
    if (!symbol || !recommendation || Number(quantity) < 1 || !generation) return;
    void submit(onOrder && (() => onOrder({
      batch_id: recommendation,
      recommendation_ref: recommendation,
      symbol,
      side,
      quantity: Number(quantity),
      expected_generation: generation,
      expected_state_version: stateVersion ?? 0,
      command: command(recoveryId, generation, stateVersion),
    })));
  }

  function reset(event: FormEvent) {
    event.preventDefault();
    if (!generation) return;
    void submit(onReset && (() => onReset({
      starting_cash: { amount: setupCash, currency: "XOF" },
      expected_generation: generation,
      expected_state_version: stateVersion ?? 0,
      command: command(recoveryId, generation, stateVersion),
    })));
  }

  return <section aria-label="Paper commands" className="grid gap-4 border-y border-line py-4">
    <div className="flex items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Manual paper commands</h2><p className="text-sm text-muted">Commands require current generation and recovery evidence.</p></div>{status !== "idle" && <span role="status" className="text-sm text-muted">{status}</span>}</div>
    {message && <p role="alert" className="border-l-2 border-warning pl-3 text-sm">{message}</p>}
    {setupRequired ? <form onSubmit={setup} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]" aria-label="Set up paper portfolio"><label className="grid gap-1 text-sm">Starting cash<input required min="100000" max="100000000" step="1" inputMode="numeric" value={setupCash} onChange={(event) => setSetupCash(event.target.value)} className="rounded border border-line bg-panel px-3 py-2" /></label><label className="grid gap-1 text-sm">Fee rate %<input required value={feeRate} onChange={(event) => setFeeRate(event.target.value)} className="rounded border border-line bg-panel px-3 py-2" /></label><button type="submit" disabled={status === "pending"} className="self-end rounded border border-accent px-3 py-2 text-sm font-semibold">Set up</button></form> : <div className="grid gap-4 lg:grid-cols-[1fr_auto]"><form onSubmit={order} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" aria-label="Submit paper order"><label className="grid gap-1 text-sm">Symbol<input required value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} className="rounded border border-line bg-panel px-3 py-2" /></label><label className="grid gap-1 text-sm">Recommendation<input required value={recommendation} onChange={(event) => setRecommendation(event.target.value)} className="rounded border border-line bg-panel px-3 py-2" /></label><label className="grid gap-1 text-sm">Side<select value={side} onChange={(event) => setSide(event.target.value as "buy" | "sell")} className="rounded border border-line bg-panel px-3 py-2"><option value="buy">Buy</option><option value="sell">Sell</option></select></label><label className="grid gap-1 text-sm">Quantity<input required min="1" step="1" type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="rounded border border-line bg-panel px-3 py-2" /></label><button type="submit" disabled={status === "pending"} className="self-end rounded border border-accent px-3 py-2 text-sm font-semibold">Submit order</button></form><form onSubmit={reset} aria-label="Reset paper portfolio"><button type="submit" disabled={status === "pending"} className="rounded border border-warning px-3 py-2 text-sm font-semibold">Reset portfolio</button></form></div>}
  </section>;
}
