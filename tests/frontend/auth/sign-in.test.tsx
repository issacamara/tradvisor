import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/features/auth/session";
import { AuthScreen } from "@/features/auth/sign-in";

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("email and password access", () => {
  it("does not grant workspace admission after registration", async () => {
    vi.stubEnv("NEXT_PUBLIC_FIREBASE_API_KEY", "fixture-key");
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("signUp")) return Response.json({ idToken: "fixture-token" });
      if (url.includes("sendOobCode")) return Response.json({});
      return Response.json({}, { status: 403 });
    });
    vi.stubGlobal("fetch", fetch);
    render(<AuthProvider><AuthScreen /></AuthProvider>);
    fireEvent.click(screen.getByRole("tab", { name: "Create account" }));
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "reader@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Verify your email before requesting workspace access");
    expect(fetch).toHaveBeenCalledTimes(2);
    const signUpBody = JSON.parse(String(fetch.mock.calls[0]?.[1]?.body));
    expect(signUpBody).toMatchObject({ email: "reader@example.com", password: "correct-horse", returnSecureToken: true });
    expect(typeof signUpBody.returnSecureToken).toBe("boolean");
    expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/v1/me"))).toBe(false);
  });

  it("checks verified email and current admission before showing workspaces", async () => {
    vi.stubEnv("NEXT_PUBLIC_FIREBASE_API_KEY", "fixture-key");
    vi.stubEnv("NEXT_PUBLIC_TRADVISOR_API_URL", "https://api.example.test");
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("signInWithPassword")) return Response.json({ idToken: "private-token" });
      if (url.includes("lookup")) return Response.json({ users: [{ emailVerified: true }] });
      if (url.endsWith("/v1/me")) return Response.json({ data: {} });
      return Response.json({});
    });
    vi.stubGlobal("fetch", fetch);
    render(<AuthProvider><AuthScreen /></AuthProvider>);
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "reader@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Workspace access verified" })).toBeInTheDocument();
    const signInBody = JSON.parse(String(fetch.mock.calls[0]?.[1]?.body));
    expect(signInBody).toMatchObject({ email: "reader@example.com", password: "correct-horse", returnSecureToken: true });
    expect(typeof signInBody.returnSecureToken).toBe("boolean");
    expect(screen.getByRole("link", { name: "Long-Term" })).toHaveAttribute("href", "/long-term/");
  });

  it("resends verification using an unverified token without admitting a workspace session", async () => {
    vi.stubEnv("NEXT_PUBLIC_FIREBASE_API_KEY", "fixture-key");
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("signInWithPassword")) return Response.json({ idToken: "verification-only-token" });
      if (url.includes("lookup")) return Response.json({ users: [{ emailVerified: false }] });
      if (url.includes("sendOobCode")) return Response.json({});
      return Response.json({}, { status: 403 });
    });
    vi.stubGlobal("fetch", fetch);
    render(<AuthProvider><AuthScreen /></AuthProvider>);
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "reader@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("button", { name: "Resend verification email" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resend verification email" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Verification email sent");
    const requests = fetch.mock.calls;
    const signInBody = JSON.parse(String(requests[0]?.[1]?.body));
    expect(signInBody.returnSecureToken).toBe(true);
    const verificationRequest = requests.find(([input]) => String(input).includes("sendOobCode"));
    expect(JSON.parse(String(verificationRequest?.[1]?.body))).toEqual({ requestType: "VERIFY_EMAIL", idToken: "verification-only-token" });
    expect(requests.some(([input]) => String(input).endsWith("/v1/me"))).toBe(false);
  });

  it("returns one reset confirmation for an unknown address", async () => {
    vi.stubEnv("NEXT_PUBLIC_FIREBASE_API_KEY", "fixture-key");
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({}, { status: 400 })));
    render(<AuthProvider><AuthScreen /></AuthProvider>);
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "unknown@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Forgot password?" }));
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("If an account exists"));
  });
});
