import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LongTermWorkspace } from "@/features/long_term/workspace";

describe("Long-Term workspace", () => {
  it("keeps V1 objectives separate without offering a deferred composite score", () => {
    render(<LongTermWorkspace />);
    expect(screen.queryByRole("tab", { name: /balanced/i })).not.toBeInTheDocument();
    expect(screen.getByText("No published company research yet.")).toBeInTheDocument();
  });

  it("offers dividend facts as a separate research view", () => {
    render(<LongTermWorkspace />);
    fireEvent.click(screen.getByRole("tab", { name: "Dividend research" }));
    expect(screen.getByRole("tab", { name: "Dividend research" })).toHaveAttribute("aria-selected", "true");
  });
});
