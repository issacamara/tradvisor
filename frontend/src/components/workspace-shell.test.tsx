import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceShell } from "./workspace-shell";

vi.mock("next/dynamic", () => ({ default: () => () => <div data-testid="chart-boundary">chart boundary</div> }));

describe("WorkspaceShell", () => {
  it("provides direct workspace navigation with the current page marked", () => {
    render(<WorkspaceShell workspace="swing" />);
    screen.getAllByRole("link", { name: "Swing" }).forEach((link) => expect(link).toHaveAttribute("aria-current", "page"));
    screen.getAllByRole("link", { name: "Long-Term" }).forEach((link) => expect(link).toHaveAttribute("href", "/long-term"));
  });

  it("keeps a usable stacked navigation structure for narrow screens", () => {
    render(<WorkspaceShell workspace="paper" />);
    expect(screen.getAllByRole("navigation", { name: "Investor workspaces" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("heading", { name: "Paper trading" })).toHaveLength(2);
  });
});
