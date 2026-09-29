"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

export type SessionStatus = "signed_out" | "checking" | "unverified" | "admitted";
export type SessionActions = {
  status: SessionStatus;
  message: string;
  signIn(email: string, password: string): Promise<void>;
  register(email: string, password: string): Promise<void>;
  resetPassword(email: string): Promise<void>;
  resendVerification(email: string, password: string): Promise<void>;
  signOut(): void;
  refreshAdmission(): Promise<void>;
  request(path: string, init?: RequestInit): Promise<Response>;
};

type FirebaseResponse = {
  idToken?: string;
  refreshToken?: string;
  expiresIn?: string;
  error?: { message?: string };
  users?: Array<{ emailVerified?: boolean }>;
};
type FirebaseRequestBody = {
  email?: string;
  password?: string;
  returnSecureToken?: boolean;
  idToken?: string;
  requestType?: "VERIFY_EMAIL" | "PASSWORD_RESET";
};
const SessionContext = createContext<SessionActions | null>(null);
const authEndpoint = "https://identitytoolkit.googleapis.com/v1/accounts";
const refreshEndpoint = "https://securetoken.googleapis.com/v1/token";
const sessionKey = "tradvisor.firebase.session";
const legacySessionTokenKey = "tradvisor.firebase.id-token";

type StoredSession = { idToken: string; refreshToken: string | null; expiresAt: number };

function readStoredSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(sessionKey);
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<StoredSession>;
      if (typeof parsed.idToken === "string") {
        return {
          idToken: parsed.idToken,
          refreshToken: typeof parsed.refreshToken === "string" ? parsed.refreshToken : null,
          expiresAt: typeof parsed.expiresAt === "number" ? parsed.expiresAt : 0,
        };
      }
    }
    const legacy = window.sessionStorage.getItem(legacySessionTokenKey);
    return legacy ? { idToken: legacy, refreshToken: null, expiresAt: 0 } : null;
  } catch { return null; }
}

function storeSession(session: StoredSession | null): void {
  if (typeof window === "undefined") return;
  try {
    if (session) window.localStorage.setItem(sessionKey, JSON.stringify(session));
    else window.localStorage.removeItem(sessionKey);
    window.sessionStorage.removeItem(legacySessionTokenKey);
  } catch { /* Storage can be unavailable in restricted browser contexts. */ }
}

function sessionFromFirebase(result: FirebaseResponse): StoredSession {
  if (!result.idToken) throw new Error("Authentication could not be completed. Try again.");
  const expiresIn = Number(result.expiresIn ?? "3600");
  return {
    idToken: result.idToken,
    refreshToken: result.refreshToken ?? null,
    expiresAt: Date.now() + (Number.isFinite(expiresIn) ? expiresIn * 1000 : 3600000),
  };
}

function safeAuthMessage(code: string): string {
  if (/EMAIL_NOT_FOUND|INVALID_PASSWORD|INVALID_LOGIN_CREDENTIALS/.test(code)) return "Email or password is incorrect.";
  if (code.includes("EMAIL_EXISTS")) return "An account already exists for this email.";
  if (code.includes("WEAK_PASSWORD")) return "Choose a password with at least eight characters.";
  if (code.includes("TOO_MANY_ATTEMPTS")) return "Too many attempts. Wait before trying again.";
  return "Authentication could not be completed. Check your details and try again.";
}

async function firebaseRequest(action: string, body: FirebaseRequestBody): Promise<FirebaseResponse> {
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

async function verifiedSession(email: string, password: string): Promise<StoredSession> {
  const result = await firebaseRequest("signInWithPassword", { email, password, returnSecureToken: true });
  const session = sessionFromFirebase(result);
  const lookup = await firebaseRequest("lookup", { idToken: session.idToken });
  if (lookup.users?.[0]?.emailVerified !== true) throw new Error("Verify your email before signing in.");
  return session;
}

async function unverifiedVerificationToken(email: string, password: string): Promise<string> {
  const result = await firebaseRequest("signInWithPassword", { email, password, returnSecureToken: true });
  const session = sessionFromFirebase(result);
  const lookup = await firebaseRequest("lookup", { idToken: session.idToken });
  if (lookup.users?.[0]?.emailVerified !== false) {
    throw new Error("This account is already verified or could not be verified.");
  }
  return session.idToken;
}

async function refreshStoredSession(session: StoredSession): Promise<StoredSession> {
  if (!session.refreshToken) return session;
  const apiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  if (!apiKey) throw new Error("Sign-in is not configured for this workspace.");
  const response = await fetch(`${refreshEndpoint}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST", cache: "no-store", credentials: "omit",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: session.refreshToken }).toString(),
  });
  const payload = await response.json() as { id_token?: string; refresh_token?: string; expires_in?: string; error?: { message?: string } };
  if (!response.ok || !payload.id_token) throw new Error(safeAuthMessage(payload.error?.message ?? ""));
  return sessionFromFirebase({ idToken: payload.id_token, refreshToken: payload.refresh_token ?? session.refreshToken, expiresIn: payload.expires_in });
}

function useSessionValue(): SessionActions {
  const [session, setSession] = useState<StoredSession | null>(readStoredSession);
  const [status, setStatus] = useState<SessionStatus>(() => readStoredSession() ? "checking" : "signed_out");
  const [message, setMessage] = useState("");
  const admissionToken = useRef<string | null>(null);

  const currentSession = useCallback(async (force = false): Promise<StoredSession> => {
    if (!session) throw new Error("Protected API access is not available.");
    if (!force && ((session.expiresAt === 0 && !session.refreshToken) || session.expiresAt - Date.now() > 60_000)) return session;
    const refreshed = await refreshStoredSession(session);
    storeSession(refreshed);
    setSession(refreshed);
    return refreshed;
  }, [session]);

  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const apiUrl = process.env.NEXT_PUBLIC_TRADVISOR_API_URL;
    if (!apiUrl) throw new Error("Protected API access is not available.");
    let active = await currentSession();
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const headers = new Headers(init.headers);
      headers.set("Authorization", `Bearer ${active.idToken}`);
      if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
      const response = await fetch(`${apiUrl.replace(/\/$/, "")}${path}`, { ...init, headers, cache: "no-store", credentials: "omit" });
      if (response.status !== 401 || attempt === 1 || !active.refreshToken) {
        if (response.status === 401) {
          storeSession(null);
          setSession(null);
          setStatus("signed_out");
        }
        return response;
      }
      try {
        active = await currentSession(true);
      } catch (error) {
        storeSession(null);
        setSession(null);
        setStatus("signed_out");
        throw error;
      }
    }
    throw new Error("Protected API access is not available.");
  }, [currentSession]);

  const refreshAdmission = useCallback(async () => {
    if (!session) { setStatus("signed_out"); return; }
    if (admissionToken.current === session.idToken) {
      setStatus("admitted");
      return;
    }
    try {
      const active = await currentSession();
      admissionToken.current = active.idToken;
      setStatus("admitted");
    } catch (error) {
      admissionToken.current = null;
      storeSession(null);
      setSession(null);
      setStatus("signed_out");
      setMessage(error instanceof Error ? error.message : "Authentication could not be completed.");
    }
  }, [currentSession, session]);

  useEffect(() => { if (session) void refreshAdmission(); }, [refreshAdmission, session]);
  useEffect(() => {
    if (!session) return;
    const onFocus = () => { void refreshAdmission(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshAdmission, session]);
  return useMemo(() => ({
    status, message, refreshAdmission, request,
    async signIn(email, password) {
      setMessage("");
      try {
        const nextSession = await verifiedSession(email, password);
        storeSession(nextSession);
        setSession(nextSession);
        setStatus("admitted");
      } catch (error) {
        const text = error instanceof Error ? error.message : "Authentication could not be completed.";
        setStatus(text.startsWith("Verify your email") ? "unverified" : "signed_out");
        setMessage(text);
      }
    },
    async register(email, password) {
      setMessage("");
      try {
        const created = await firebaseRequest("signUp", { email, password, returnSecureToken: true });
        if (!created.idToken) throw new Error("Registration could not be completed.");
        await firebaseRequest("sendOobCode", { requestType: "VERIFY_EMAIL", idToken: created.idToken });
        setStatus("unverified");
        setMessage("Account created. Verify your email before signing in.");
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
        const nextToken = await unverifiedVerificationToken(email, password);
        await firebaseRequest("sendOobCode", { requestType: "VERIFY_EMAIL", idToken: nextToken });
        setMessage("Verification email sent.");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Verification email could not be sent.");
      }
    },
    signOut() { admissionToken.current = null; storeSession(null); setSession(null); setStatus("signed_out"); setMessage(""); },
  }), [message, refreshAdmission, request, status]);
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
  if (session.status === "admitted") return <>
    <header className="flex items-center justify-end border-b border-line px-5 py-2">
      <button type="button" className="rounded border border-line px-3 py-1.5 text-sm" onClick={session.signOut}>Sign out</button>
    </header>
    {children}
  </>;
  return <section className="mx-auto max-w-3xl px-5 py-10" aria-live="polite">
    <h1 className="text-2xl font-bold">Sign-in required</h1>
    <p className="mt-2 text-sm text-muted">{session.message || "Sign in with a verified email."}</p>
    {session.status !== "checking" && <a className="mt-4 inline-block underline underline-offset-4" href="/">Sign in</a>}
  </section>;
}
