import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PaperCommands } from "@/features/paper/commands/paper-commands";

describe("PaperCommands", () => {
  it("does not show an optimistic fill and surfaces uncertain outcomes", async () => {
    const onOrder = vi.fn(async () => "uncertain" as const);
    render(<PaperCommands setupRequired={false} generation="g1" stateVersion={3} onOrder={onOrder} />);

    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "ABC" } });
    fireEvent.change(screen.getByLabelText("Recommendation"), { target: { value: "rec-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit order" }));

    await waitFor(() => expect(onOrder).toHaveBeenCalledOnce());
    expect(await screen.findByRole("alert")).toHaveTextContent("outcome is uncertain");
  });

  it("requires explicit setup fields before dispatch", async () => {
    const onSetup = vi.fn(async () => "confirmed" as const);
    render(<PaperCommands setupRequired onSetup={onSetup} />);
    fireEvent.click(screen.getByRole("button", { name: "Set up" }));
    await waitFor(() => expect(onSetup).toHaveBeenCalledOnce());
    expect(screen.getByLabelText("Starting cash")).toHaveValue("100000");
  });
});
