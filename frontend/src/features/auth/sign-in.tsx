"use client";

import { useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import styles from "./sign-in.module.css";
import { useAuthSession } from "./session";

export function AuthScreen() {
  const session = useAuthSession();
  const [mode, setMode] = useState<"sign_in" | "register" | "reset">("sign_in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const selectedMode = mode === "register" ? "register" : "sign_in";
  const feedback = pending
    ? "Submitting your request…"
    : session.status === "checking"
      ? `${session.message ? `${session.message} ` : ""}Checking your current invitation…`
      : session.status === "unverified"
        ? session.message || "Verify your email to continue. Workspace admission is checked after verification."
        : session.message;

  function handleModeKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const nextMode = selectedMode === "sign_in" ? "register" : "sign_in";
    setMode(nextMode);
    document.getElementById(nextMode === "sign_in" ? "sign-in-tab" : "register-tab")?.focus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    try {
      if (mode === "register") await session.register(email, password);
      else if (mode === "reset") await session.resetPassword(email);
      else await session.signIn(email, password);
    } finally {
      setPending(false);
    }
  }

  if (session.status === "admitted") return <main className={styles.admitted} aria-live="polite">
    <p className={styles.eyebrow}>TRADVISOR / ACCESS VERIFIED</p>
    <div className={styles.admittedHeading}>
      <div>
        <h1>Workspace access verified</h1>
        <p>Your verified account is admitted. Choose a research workspace.</p>
      </div>
      <button className={styles.secondaryButton} type="button" onClick={() => session.signOut()}>Sign out</button>
    </div>
    <nav className={styles.workspaceLinks} aria-label="Investor workspaces">
      <a href="/swing/">Swing</a>
      <a href="/long-term/">Long-Term</a>
    </nav>
  </main>;

  return <main className={styles.authShell}>
    <section className={styles.intro} aria-labelledby="intro-title">
      <p className={styles.eyebrow}>TRADVISOR / BRVM RESEARCH</p>
      <h1 id="intro-title">Research with the evidence in view.</h1>
      <p className={styles.introCopy}>Swing and Long-Term research are separate workspaces, built around published evidence and clear availability.</p>
      <div className={styles.accessNote}>
        <span className={styles.accessMark} aria-hidden="true">01</span>
        <p>A verified email and current invitation are required. Creating an account does not grant workspace access.</p>
      </div>
      <nav className={styles.previewLinks} aria-label="Research workspaces">
        <span>Swing</span><span>Long-Term</span>
      </nav>
    </section>

    <section id="auth-panel" className={styles.authPanel} role="tabpanel" aria-labelledby={selectedMode === "register" ? "register-tab" : "sign-in-tab"}>
      <p className={styles.panelEyebrow}>INVITED ACCESS</p>
      <div className={styles.modeSwitch} role="tablist" aria-label="Account access">
        <button
          id="sign-in-tab"
          type="button"
          role="tab"
          aria-selected={selectedMode === "sign_in"}
          aria-controls="auth-panel"
          tabIndex={selectedMode === "sign_in" ? 0 : -1}
          disabled={pending}
          className={selectedMode === "sign_in" ? styles.modeActive : styles.modeButton}
          onKeyDown={handleModeKeyDown}
          onClick={() => setMode("sign_in")}
        >Sign in</button>
        <button
          id="register-tab"
          type="button"
          role="tab"
          aria-selected={selectedMode === "register"}
          aria-controls="auth-panel"
          tabIndex={selectedMode === "register" ? 0 : -1}
          disabled={pending}
          className={mode === "register" ? styles.modeActive : styles.modeButton}
          onKeyDown={handleModeKeyDown}
          onClick={() => setMode("register")}
        >Create account</button>
      </div>

      <h2 id="auth-title">{mode === "reset" ? "Reset password" : mode === "register" ? "Create account" : "Sign in"}</h2>
      <p className={styles.formIntro}>{mode === "reset"
        ? "Enter the email for your account."
        : mode === "register"
          ? "We will send a verification link before you can request access."
          : "Use your invited account to continue."}</p>

      <form className={styles.form} onSubmit={submit} aria-busy={pending}>
        <label className={styles.field} htmlFor="auth-email">
          <span>Email address</span>
          <input
            id="auth-email"
            name="email"
            autoComplete="email"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            inputMode="email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        {mode !== "reset" && <label className={styles.field} htmlFor="auth-password">
          <span>Password</span>
          <input
            id="auth-password"
            name="password"
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            type="password"
            minLength={8}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>}
        <button className={styles.submitButton} type="submit" disabled={pending}>
          {pending ? "Working…" : mode === "reset" ? "Send reset link" : mode === "register" ? "Create account" : "Continue"}
        </button>
      </form>

      {feedback && <p className={pending ? styles.pendingMessage : styles.sessionMessage} role="status" aria-live="polite">{feedback}</p>}

      <div className={styles.formLinks}>
        {mode === "sign_in" && <button type="button" disabled={pending} onClick={() => setMode("reset")}>Forgot password?</button>}
        {mode === "reset" && <button type="button" disabled={pending} onClick={() => setMode("sign_in")}>Back to sign in</button>}
        {session.status === "unverified" && <button type="button" disabled={pending} onClick={() => void session.resendVerification(email, password)}>Resend verification email</button>}
      </div>
      <p className={styles.privacyNote}>A verified email and current invitation are both required for access.</p>
    </section>
  </main>;
}
