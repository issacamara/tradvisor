"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import type { components } from "@/api/generated/schema";

type SetupRequest = components["schemas"]["SetupPortfolioRequest"];
type OrderRequest = components["schemas"]["CreatePaperOrderRequest"];
type ResetRequest = components["schemas"]["ResetPortfolioRequest"];
type CommandResult = "idle" | "pending" | "confirmed" | "uncertain" | "error";
type MutationHandler<T> = (request: T, idempotencyKey: string) => Promise<CommandResult>;

type Props = {
  setupRequired: boolean;
  generation?: string;
  stateVersion?: number;
  recoveryId?: string;
  onSetup?: MutationHandler<SetupRequest>;
  onOrder?: MutationHandler<OrderRequest>;
  onReset?: MutationHandler<ResetRequest>;
};

const command = (recoveryId: string, generation?: string, stateVersion = 0) => ({
  issued_at: new Date().toISOString(),
  recovery_id: recoveryId,
  content_length: 0,
  expected_generation: generation ?? null,
  expected_state_version: stateVersion,
});

function newIdempotencyKey() {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().replaceAll("-", "")
    : Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
  return `${Date.now().toString().padStart(13, "0")}.${random}`;
}

export function PaperCommands({ setupRequired, generation, stateVersion, recoveryId, onSetup, onOrder, onReset }: Props) {
  const [setupCash, setSetupCash] = useState("100000");
  const [feeRate, setFeeRate] = useState("0");
  const [symbol, setSymbol] = useState("");
  const [recommendation, setRecommendation] = useState("");
  const [batchId, setBatchId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [keepAcknowledged, setKeepAcknowledged] = useState(false);
  const [freshConfirmation, setFreshConfirmation] = useState(false);
  const [status, setStatus] = useState<CommandResult>("idle");
  const [message, setMessage] = useState("");
  const setupKey = useRef<string | undefined>(undefined);
  const orderKey = useRef<string | undefined>(undefined);
  const resetKey = useRef<string | undefined>(undefined);

  useEffect(() => setFreshConfirmation(false), [generation, stateVersion, recoveryId]);

  async function submit(action: (() => Promise<CommandResult>) | undefined, key: MutableRefObject<string | undefined>) {
    if (!action) return;
    setStatus("pending");
    setMessage("");
    try {
      const next = await action();
      setStatus(next);
      if (next === "confirmed") key.current = undefined;
      setMessage(next === "uncertain" ? "The outcome is uncertain. Refresh the authoritative paper state before retrying." : next === "confirmed" ? "Confirmed by the paper service." : "The command was not confirmed.");
    } catch {
      setStatus("uncertain");
      setMessage("The outcome is uncertain. Refresh the authoritative paper state before retrying.");
    }
  }

  function setup(event: FormEvent) {
    event.preventDefault();
    if (!onSetup || !recoveryId) return;
    setupKey.current ??= newIdempotencyKey();
    void submit(() => onSetup({
      fee_rate_pct: feeRate,
      starting_cash: { amount: setupCash, currency: "XOF" },
      command: command(recoveryId),
    }, setupKey.current!), setupKey);
  }

  function order(event: FormEvent) {
    event.preventDefault();
    if (!onOrder || !symbol || !recommendation || !batchId || Number(quantity) < 1 || !generation || !recoveryId) return;
    if (!freshConfirmation) {
      setMessage("Confirm the current recommendation and portfolio state before submitting.");
      return;
    }
    if (side === "sell" && !keepAcknowledged) {
      setMessage("Acknowledge Keep advice before submitting a sell command.");
      return;
    }
    orderKey.current ??= newIdempotencyKey();
    void submit(() => onOrder({
      batch_id: batchId,
      recommendation_ref: recommendation,
      symbol,
      side,
      quantity: Number(quantity),
      expected_generation: generation,
      expected_state_version: stateVersion ?? 0,
      acknowledge_keep_override: keepAcknowledged,
      command: command(recoveryId, generation, stateVersion),
    }, orderKey.current!), orderKey);
  }

  function reset(event: FormEvent) {
    event.preventDefault();
    if (!onReset || !generation || !recoveryId) return;
    resetKey.current ??= newIdempotencyKey();
    void submit(() => onReset({
      starting_cash: { amount: setupCash, currency: "XOF" },
      expected_generation: generation,
      expected_state_version: stateVersion ?? 0,
      command: command(recoveryId, generation, stateVersion),
    }, resetKey.current!), resetKey);
  }

  return <section aria-label="Paper commands" className="grid gap-4 border-y border-line py-4">
    <div className="flex items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Manual paper commands</h2><p className="text-sm text-muted">Commands require current generation and recovery evidence.</p></div>{status !== "idle" && <span role="status" className="text-sm text-muted">{status}</span>}</div>
    {message && <p role="alert" className="border-l-2 border-warning pl-3 text-sm">{message}</p>}
    {setupRequired ? <form onSubmit={setup} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]" aria-label="Set up paper portfolio"><label className="grid gap-1 text-sm">Starting cash<input required min="100000" max="100000000" step="1" inputMode="numeric" value={setupCash} onChange={(event) => setSetupCash(event.target.value)} className="rounded border border-line bg-panel px-3 py-2" /></label><label className="grid gap-1 text-sm">Fee rate %<input required value={feeRate} onChange={(event) => setFeeRate(event.target.value)} className="rounded border border-line bg-panel px-3 py-2" /></label><button type="submit" disabled={status === "pending" || !onSetup || !recoveryId} className="self-end rounded border border-accent px-3 py-2 text-sm font-semibold">Set up</button></form> : <div className="grid gap-4 lg:grid-cols-[1fr_auto]"><form onSubmit={order} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Submit paper order"><label className="grid gap-1 text-sm">Symbol<input required value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} className="rounded border border-line bg-panel px-3 py-2" /></label><label className="grid gap-1 text-sm">Recommendation<input required value={recommendation} onChange={(event) => setRecommendation(event.target.value)} className="rounded border border-line bg-panel px-3 py-2" /></label><label className="grid gap-1 text-sm">Recommendation batch<input required value={batchId} onChange={(event) => setBatchId(event.target.value)} className="rounded border border-line bg-panel px-3 py-2" /></label><label className="grid gap-1 text-sm">Side<select value={side} onChange={(event) => setSide(event.target.value as "buy" | "sell")} className="rounded border border-line bg-panel px-3 py-2"><option value="buy">Buy</option><option value="sell">Sell</option></select></label><label className="grid gap-1 text-sm">Quantity<input required min="1" step="1" type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="rounded border border-line bg-panel px-3 py-2" /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={freshConfirmation} onChange={(event) => setFreshConfirmation(event.target.checked)} />Confirm current recommendation and portfolio state</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={keepAcknowledged} onChange={(event) => setKeepAcknowledged(event.target.checked)} />Acknowledge Keep advice override</label><button type="submit" disabled={status === "pending" || !onOrder || !recoveryId} className="self-end rounded border border-accent px-3 py-2 text-sm font-semibold">Submit order</button></form><form onSubmit={reset} aria-label="Reset paper portfolio"><button type="submit" disabled={status === "pending" || !onReset || !recoveryId} className="rounded border border-warning px-3 py-2 text-sm font-semibold">Reset portfolio</button></form></div>}
  </section>;
}
