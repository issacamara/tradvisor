import { cleanup, render, screen, within } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkspaceShell } from "./workspace-shell";
import { InvestorNav } from "./investor-nav";
import { Button } from "./ui/button";
import tailwindConfig from "../../tailwind.config";

vi.mock("next/dynamic", () => ({ default: () => () => <div data-testid="chart-boundary">chart boundary</div> }));

afterEach(cleanup);

describe("WorkspaceShell", () => {
  it("provides direct workspace navigation with the current page marked", () => {
    render(<WorkspaceShell workspace="swing" />);
    screen.getAllByRole("link", { name: "Swing" }).forEach((link) => expect(link).toHaveAttribute("aria-current", "page"));
    screen.getAllByRole("link", { name: "Long-Term" }).forEach((link) => expect(link).toHaveAttribute("href", "/long-term"));
  });

  it("keeps a usable stacked navigation structure for narrow screens", () => {
    render(<WorkspaceShell workspace="long-term" />);
    expect(screen.getAllByRole("navigation", { name: "Investor workspaces" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Open workspace navigation" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Long-Term research" })).toHaveLength(2);
  });
});

describe("shared terminal chrome", () => {
  it.each([
    ["swing", "/swing"],
    ["long-term", "/long-term"],
  ] as const)("marks %s active and keeps both research routes directly reachable", (active, activeHref) => {
    render(<InvestorNav active={active} />);
    const nav = screen.getByRole("navigation", { name: "Investor workspaces" });
    const swing = within(nav).getByRole("link", { name: "Swing" });
    const longTerm = within(nav).getByRole("link", { name: "Long-Term" });
    const activeLink = active === "swing" ? swing : longTerm;

    expect(activeLink).toHaveAttribute("href", activeHref);
    expect(activeLink).toHaveAttribute("aria-current", "page");
    expect(nav).toContainElement(swing);
    expect(nav).toContainElement(longTerm);
    expect(swing).toHaveClass("min-h-11", "focus-visible:ring-selection");
    expect(longTerm).toHaveClass("min-h-11", "focus-visible:ring-selection");
  });

  it("maps shared colors to semantic tokens and gives buttons 44px targets", () => {
    const colors = tailwindConfig.theme.extend.colors as unknown as Record<string, string>;
    render(<Button aria-label="Account action">Account</Button>);

    expect(colors.canvas).toContain("--color-canvas");
    expect(colors.positive).toContain("--color-positive");
    expect(colors.selection).toContain("--color-selection");
    expect(screen.getByRole("button", { name: "Account action" })).toHaveClass("min-h-11");
  });
});
