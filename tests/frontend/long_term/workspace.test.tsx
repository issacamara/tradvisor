import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LongTermWorkspace } from "@/features/long_term/workspace";

describe("Long-Term workspace", () => {
  it("keeps the three objective states distinct and marks Balanced deferred", () => {
    render(<LongTermWorkspace />);
    fireEvent.click(screen.getByRole("tab", { name: "balanced" }));
    expect(screen.getByRole("status")).toHaveTextContent("Balanced scoring is deferred in V1");
    expect(screen.getByText("No catalog research results are available.")).toBeInTheDocument();
  });

  it("offers dividend facts as a separate research view", () => {
    render(<LongTermWorkspace />);
    fireEvent.click(screen.getByRole("tab", { name: "Dividend research" }));
    expect(screen.getByRole("tab", { name: "Dividend research" })).toHaveAttribute("aria-selected", "true");
  });
});
