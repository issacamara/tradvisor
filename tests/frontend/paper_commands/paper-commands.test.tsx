import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PaperCommands } from "@/features/paper/commands/paper-commands";

describe("PaperCommands", () => {
  it("does not show an optimistic fill and surfaces uncertain outcomes", async () => {
    const onOrder = vi.fn(async () => "uncertain" as const);
    render(<PaperCommands setupRequired={false} generation="g1" stateVersion={3} recoveryId="r1" onOrder={onOrder} />);

    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "ABC" } });
    fireEvent.change(screen.getByLabelText("Recommendation"), { target: { value: "rec-1" } });
    fireEvent.change(screen.getByLabelText("Recommendation batch"), { target: { value: "batch-1" } });
    fireEvent.click(screen.getByLabelText("Confirm current recommendation and portfolio state"));
    fireEvent.click(screen.getByRole("button", { name: "Submit order" }));

    await waitFor(() => expect(onOrder).toHaveBeenCalledOnce());
    expect(await screen.findByRole("alert")).toHaveTextContent("outcome is uncertain");
  });

  it("requires explicit setup fields before dispatch", async () => {
    const onSetup = vi.fn(async () => "confirmed" as const);
    render(<PaperCommands setupRequired recoveryId="r1" onSetup={onSetup} />);
    fireEvent.click(screen.getByRole("button", { name: "Set up" }));
    await waitFor(() => expect(onSetup).toHaveBeenCalledOnce());
    expect(screen.getByLabelText("Starting cash")).toHaveValue("100000");
  });

  it("reuses one idempotency key when a command outcome is uncertain", async () => {
    const onOrder = vi.fn(async () => "uncertain" as const);
    render(<PaperCommands setupRequired={false} generation="g1" stateVersion={3} recoveryId="r1" onOrder={onOrder} />);
    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "ABC" } });
    fireEvent.change(screen.getByLabelText("Recommendation"), { target: { value: "rec-1" } });
    fireEvent.change(screen.getByLabelText("Recommendation batch"), { target: { value: "batch-1" } });
    fireEvent.click(screen.getByLabelText("Confirm current recommendation and portfolio state"));
    fireEvent.click(screen.getByRole("button", { name: "Submit order" }));
    await waitFor(() => expect(onOrder).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Submit order" }));
    await waitFor(() => expect(onOrder).toHaveBeenCalledTimes(2));
    expect(onOrder.mock.calls[0][1]).toMatch(/^\d{13}\.[0-9a-f]{32}$/);
    expect(onOrder.mock.calls[1][1]).toBe(onOrder.mock.calls[0][1]);
  });

  it("requires Keep acknowledgment for sell commands", async () => {
    const onOrder = vi.fn(async () => "confirmed" as const);
    render(<PaperCommands setupRequired={false} generation="g1" stateVersion={3} recoveryId="r1" onOrder={onOrder} />);
    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "ABC" } });
    fireEvent.change(screen.getByLabelText("Recommendation"), { target: { value: "rec-1" } });
    fireEvent.change(screen.getByLabelText("Recommendation batch"), { target: { value: "batch-1" } });
    fireEvent.change(screen.getByLabelText("Side"), { target: { value: "sell" } });
    fireEvent.click(screen.getByLabelText("Confirm current recommendation and portfolio state"));
    fireEvent.click(screen.getByRole("button", { name: "Submit order" }));
    expect(onOrder).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Keep");
  });
});
