"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useAuthSession } from "./session";

export function AuthScreen() {
  const session = useAuthSession();
  const [mode, setMode] = useState<"sign_in" | "register" | "reset">("sign_in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    try {
      if (mode === "register") await session.register(email, password);
      else if (mode === "reset") await session.resetPassword(email);
      else await session.signIn(email, password);
    } finally { setPending(false); }
  }

  if (session.status === "admitted") return <section className="mx-auto max-w-5xl px-5 py-8" aria-live="polite">
    <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">Workspace access verified</h1><button className="rounded border border-line px-3 py-2 text-sm" onClick={() => session.signOut()}>Sign out</button></div>
    <p className="mt-2 text-sm text-muted">Your current invitation is confirmed. Choose a workspace from the navigation.</p>
    <nav aria-label="Investor workspaces" className="mt-5 flex flex-wrap gap-4 text-sm"><a className="underline" href="/swing/">Swing</a><a className="underline" href="/long-term/">Long-Term</a><a className="underline" href="/paper/">Paper portfolio</a></nav>
  </section>;

  return <main className="mx-auto grid min-h-[70vh] max-w-5xl content-center gap-10 px-5 py-10 md:grid-cols-[minmax(0,1fr)_minmax(18rem,26rem)]">
    <section>
      <p className="text-sm font-semibold text-accent">TRADVISOR / INVITED ACCESS</p>
      <h1 className="mt-3 max-w-xl text-3xl font-bold">Research with the evidence in view.</h1>
      <p className="mt-3 max-w-xl text-sm leading-6 text-muted">Swing, Long-Term research, and manual paper trading are separate workspaces. Access is checked against your current invitation after sign-in.</p>
    </section>
    <section aria-labelledby="auth-title" className="border-l border-line pl-0 md:pl-8">
      <div className="mb-5 flex gap-2" role="tablist" aria-label="Account access">
        <button type="button" role="tab" aria-selected={mode === "sign_in"} onClick={() => setMode("sign_in")} className="border-b-2 border-accent px-2 py-2 text-sm">Sign in</button>
        <button type="button" role="tab" aria-selected={mode === "register"} onClick={() => setMode("register")} className="border-b-2 border-transparent px-2 py-2 text-sm text-muted">Create account</button>
      </div>
      <h2 id="auth-title" className="text-xl font-semibold">{mode === "reset" ? "Reset password" : mode === "register" ? "Create account" : "Sign in"}</h2>
      <form onSubmit={submit} className="mt-5 grid gap-4">
        <label className="grid gap-1 text-sm">Email address<input autoComplete="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} className="rounded border border-line bg-panel px-3 py-2 text-ink" /></label>
        {mode !== "reset" && <label className="grid gap-1 text-sm">Password<input autoComplete={mode === "register" ? "new-password" : "current-password"} type="password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} className="rounded border border-line bg-panel px-3 py-2 text-ink" /></label>}
        <button disabled={pending} className="inline-flex min-h-10 items-center justify-center rounded bg-accent px-4 text-sm font-semibold text-canvas disabled:opacity-60">{pending ? "Working…" : mode === "reset" ? "Send reset link" : mode === "register" ? "Create account" : "Continue"}</button>
      </form>
      {session.message && <p role="status" className="mt-4 text-sm text-warning">{session.message}</p>}
      {session.status === "checking" && <p role="status" className="mt-4 text-sm text-muted">Checking your current invitation…</p>}
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm text-muted">
        {mode === "sign_in" && <button type="button" onClick={() => setMode("reset")} className="underline underline-offset-4">Forgot password?</button>}
        {mode === "reset" && <button type="button" onClick={() => setMode("sign_in")} className="underline underline-offset-4">Back to sign in</button>}
        {session.status === "unverified" && <button type="button" onClick={() => void session.resendVerification(email, password)} className="underline underline-offset-4">Resend verification email</button>}
      </div>
      <p className="mt-5 text-xs leading-5 text-muted">Creating an account does not grant an invitation. Protected data remains unavailable until your verified email is admitted.</p>
    </section>
  </main>;
}
