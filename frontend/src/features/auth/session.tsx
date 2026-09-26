"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

export type SessionStatus = "signed_out" | "checking" | "unverified" | "not_admitted" | "admitted" | "removed";
export type SessionActions = {
  status: SessionStatus;
  message: string;
  signIn(email: string, password: string): Promise<void>;
  register(email: string, password: string): Promise<void>;
  resetPassword(email: string): Promise<void>;
  resendVerification(email: string, password: string): Promise<void>;
  signOut(): void;
  refreshAdmission(): Promise<void>;
};

type FirebaseResponse = { idToken?: string; error?: { message?: string }; users?: Array<{ emailVerified?: boolean }> };
const SessionContext = createContext<SessionActions | null>(null);
const authEndpoint = "https://identitytoolkit.googleapis.com/v1/accounts";

function safeAuthMessage(code: string): string {
  if (/EMAIL_NOT_FOUND|INVALID_PASSWORD|INVALID_LOGIN_CREDENTIALS/.test(code)) return "Email or password is incorrect.";
  if (code.includes("EMAIL_EXISTS")) return "An account already exists for this email.";
  if (code.includes("WEAK_PASSWORD")) return "Choose a password with at least eight characters.";
  if (code.includes("TOO_MANY_ATTEMPTS")) return "Too many attempts. Wait before trying again.";
  return "Authentication could not be completed. Check your details and try again.";
}

async function firebaseRequest(action: string, body: Record<string, string>): Promise<FirebaseResponse> {
  const apiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  if (!apiKey) throw new Error("Sign-in is not configured for this workspace.");
  const response = await fetch(`${authEndpoint}:${action}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST", cache: "no-store", credentials: "omit",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const payload = await response.json() as FirebaseResponse;
  if (!response.ok) throw new Error(safeAuthMessage(payload.error?.message ?? ""));
  return payload;
}

async function verifiedSession(email: string, password: string): Promise<string> {
  const result = await firebaseRequest("signInWithPassword", { email, password, returnSecureToken: "true" });
  if (!result.idToken) throw new Error("Authentication could not be completed. Try again.");
  const lookup = await firebaseRequest("lookup", { idToken: result.idToken });
  if (lookup.users?.[0]?.emailVerified !== true) throw new Error("Verify your email before signing in.");
  return result.idToken;
}

function useSessionValue(): SessionActions {
  const [status, setStatus] = useState<SessionStatus>("signed_out");
  const [token, setToken] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const wasAdmitted = useRef(false);

  const refreshAdmission = useCallback(async () => {
    if (!token) return;
    const apiUrl = process.env.NEXT_PUBLIC_TRADVISOR_API_URL;
    if (!apiUrl) {
      wasAdmitted.current = false;
      setStatus("not_admitted");
      setMessage("Protected workspace access is not configured.");
      setToken(null);
      return;
    }
    setStatus("checking");
    try {
      const response = await fetch(`${apiUrl.replace(/\/$/, "")}/v1/me`, {
        headers: { Authorization: `Bearer ${token}` }, cache: "no-store", credentials: "omit",
      });
      if (response.ok) {
        wasAdmitted.current = true;
        setStatus("admitted");
        setMessage("");
        return;
      }
      const body = await response.json().catch(() => null) as { error?: { code?: string } } | null;
      const removed = response.status === 403 && wasAdmitted.current;
      wasAdmitted.current = false;
      setStatus(removed ? "removed" : "not_admitted");
      setMessage(body?.error?.code === "admission_unavailable"
        ? "Access could not be verified. Protected information has been cleared."
        : removed
          ? "Your invitation is no longer active. Protected information has been cleared."
          : "This verified email does not have an active invitation.");
      setToken(null);
    } catch {
      wasAdmitted.current = false;
      setStatus("not_admitted");
      setMessage("Access could not be verified. Protected information has been cleared.");
      setToken(null);
    }
  }, [token]);

  useEffect(() => { if (token) void refreshAdmission(); }, [refreshAdmission, token]);
  useEffect(() => {
    if (!token) return;
    const onFocus = () => { void refreshAdmission(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshAdmission, token]);

  return useMemo(() => ({
    status, message, refreshAdmission,
    async signIn(email, password) {
      setMessage("");
      try {
        const nextToken = await verifiedSession(email, password);
        wasAdmitted.current = false;
        setToken(nextToken);
        setStatus("checking");
      } catch (error) {
        const text = error instanceof Error ? error.message : "Authentication could not be completed.";
        setStatus(text.startsWith("Verify your email") ? "unverified" : "signed_out");
        setMessage(text);
      }
    },
    async register(email, password) {
      setMessage("");
      try {
        const created = await firebaseRequest("signUp", { email, password, returnSecureToken: "true" });
        if (!created.idToken) throw new Error("Registration could not be completed.");
        await firebaseRequest("sendOobCode", { requestType: "VERIFY_EMAIL", idToken: created.idToken });
        setStatus("unverified");
        setMessage("Account created. Verify your email before requesting workspace access.");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Registration could not be completed.");
      }
    },
    async resetPassword(email) {
      setMessage("");
      try { await firebaseRequest("sendOobCode", { requestType: "PASSWORD_RESET", email }); }
      catch { /* Keep the response identical for known and unknown addresses. */ }
      setMessage("If an account exists for that email, a reset message has been sent.");
    },
    async resendVerification(email, password) {
      try {
        const nextToken = await verifiedSession(email, password);
        await firebaseRequest("sendOobCode", { requestType: "VERIFY_EMAIL", idToken: nextToken });
        setMessage("Verification email sent.");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Verification email could not be sent.");
      }
    },
    signOut() { wasAdmitted.current = false; setToken(null); setStatus("signed_out"); setMessage(""); },
  }), [message, refreshAdmission, status]);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const value = useSessionValue();
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useAuthSession(): SessionActions {
  const context = useContext(SessionContext);
  if (!context) throw new Error("AuthProvider is missing");
  return context;
}

export function ProtectedWorkspace({ children }: { children: ReactNode }) {
  const session = useAuthSession();
  if (session.status === "admitted") return <>{children}</>;
  return <section className="mx-auto max-w-3xl px-5 py-10" aria-live="polite">
    <h1 className="text-2xl font-bold">{session.status === "checking" ? "Checking invitation" : "Workspace access required"}</h1>
    <p className="mt-2 text-sm text-muted">{session.message || "Sign in with a verified email and current invitation."}</p>
    {session.status !== "checking" && <a className="mt-4 inline-block underline underline-offset-4" href="/">Sign in</a>}
  </section>;
}
