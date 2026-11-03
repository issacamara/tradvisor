import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthScreen } from "./sign-in";

const auth = vi.hoisted(() => ({
  status: "signed_out",
  message: "",
  signIn: vi.fn(),
  register: vi.fn(),
  resetPassword: vi.fn(),
  resendVerification: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("./session", () => ({ useAuthSession: () => auth }));

describe("AuthScreen", () => {
  beforeEach(() => {
    auth.status = "signed_out";
    auth.message = "";
    vi.clearAllMocks();
  });

  it("keeps sign-in credentials labeled and supports native password managers", () => {
    render(<AuthScreen />);

    expect(screen.getByLabelText("Email address")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });

  it("registers without treating account creation as workspace admission", async () => {
    auth.register.mockResolvedValue(undefined);
    render(<AuthScreen />);

    fireEvent.click(screen.getByRole("tab", { name: "Create account" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByText(/does not grant workspace access/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "investor@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(auth.register).toHaveBeenCalledWith("investor@example.com", "correct-horse"));
    expect(auth.signIn).not.toHaveBeenCalled();
    expect(screen.queryByRole("navigation", { name: "Investor workspaces" })).not.toBeInTheDocument();
  });

  it("supports password reset navigation without asking for a password", async () => {
    auth.resetPassword.mockResolvedValue(undefined);
    render(<AuthScreen />);

    fireEvent.click(screen.getByRole("button", { name: "Forgot password?" }));
    expect(screen.getByRole("heading", { name: "Reset password" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "investor@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    await waitFor(() => expect(auth.resetPassword).toHaveBeenCalledWith("investor@example.com"));

    fireEvent.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("moves between account tabs with the arrow keys", () => {
    render(<AuthScreen />);
    const signInTab = screen.getByRole("tab", { name: "Sign in" });
    const registerTab = screen.getByRole("tab", { name: "Create account" });

    fireEvent.keyDown(signInTab, { key: "ArrowRight" });
    expect(registerTab).toHaveAttribute("aria-selected", "true");
    expect(registerTab).toHaveFocus();
    fireEvent.keyDown(registerTab, { key: "ArrowLeft" });
    expect(signInTab).toHaveAttribute("aria-selected", "true");
    expect(signInTab).toHaveFocus();
  });

  it("shows checking and denied feedback without changing access state", () => {
    auth.status = "checking";
    auth.message = "This account is not on the invitation list.";
    render(<AuthScreen />);

    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Checking your current invitation");
    expect(screen.getByRole("status")).toHaveTextContent("This account is not on the invitation list.");
    expect(screen.queryByRole("navigation", { name: "Investor workspaces" })).not.toBeInTheDocument();
  });

  it.each([
    ["denied", "This account is not on the invitation list."],
    ["expired", "Your session expired. Sign in again to continue."],
  ])("announces %s access feedback and keeps protected workspaces hidden", (_state, message) => {
    auth.status = "signed_out";
    auth.message = message;
    render(<AuthScreen />);

    expect(screen.getByRole("status")).toHaveTextContent(message);
    expect(screen.queryByRole("navigation", { name: "Investor workspaces" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });

  it("offers verification resend and preserves sign-out cleanup for admitted users", () => {
    auth.status = "unverified";
    auth.message = "Verify your email before signing in.";
    const { rerender } = render(<AuthScreen />);
    fireEvent.click(screen.getByRole("button", { name: "Resend verification email" }));
    expect(auth.resendVerification).toHaveBeenCalledWith("", "");

    auth.status = "admitted";
    rerender(<AuthScreen />);
    expect(screen.getByRole("link", { name: "Swing" })).toHaveAttribute("href", "/swing/");
    expect(screen.getByRole("link", { name: "Long-Term" })).toHaveAttribute("href", "/long-term/");
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(auth.signOut).toHaveBeenCalledOnce();
  });

  it("announces pending work and prevents duplicate submissions", async () => {
    let finish!: () => void;
    auth.signIn.mockImplementation(() => new Promise<void>((resolve) => { finish = resolve; }));
    render(<AuthScreen />);
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "investor@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(screen.getByRole("status")).toHaveTextContent("Submitting your request");
    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
    expect(screen.getByRole("tablist", { name: "Account access" }).querySelectorAll("button:disabled")).toHaveLength(2);
    finish();
    await waitFor(() => expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled());
  });
});
