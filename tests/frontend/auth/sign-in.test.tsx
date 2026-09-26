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
    expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/v1/me"))).toBe(false);
  });

  it("checks verified email and current admission before showing workspaces", async () => {
    vi.stubEnv("NEXT_PUBLIC_FIREBASE_API_KEY", "fixture-key");
    vi.stubEnv("NEXT_PUBLIC_TRADVISOR_API_URL", "https://api.example.test");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("signInWithPassword")) return Response.json({ idToken: "private-token" });
      if (url.includes("lookup")) return Response.json({ users: [{ emailVerified: true }] });
      if (url.endsWith("/v1/me")) return Response.json({ data: {} });
      return Response.json({});
    }));
    render(<AuthProvider><AuthScreen /></AuthProvider>);
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "reader@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("heading", { name: "Workspace access verified" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Long-Term" })).toHaveAttribute("href", "/long-term/");
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
