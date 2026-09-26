import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PaperWorkspace } from "@/features/paper/views/workspace";

describe("paper reporting", () => {
  it("keeps an empty or incomplete valuation unavailable instead of zero", () => {
    render(<PaperWorkspace portfolio={{ setup_state: "setup_required", summary: null, positions: [], valuation_batch_id: null, valuation_session: null, valuation_status: "incomplete" }} />);
    expect(screen.getByText("Incomplete", { exact: true })).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText(/total is intentionally withheld/)).toBeInTheDocument();
  });

  it("provides separate paginated order, execution and ledger views", () => {
    const onNext = vi.fn();
    render(<PaperWorkspace orderCursor="next" executionCursor="next" movementCursor="next" onNext={onNext} />);
    fireEvent.click(screen.getByRole("tab", { name: "executions" }));
    fireEvent.click(screen.getByRole("button", { name: "Load next page" }));
    expect(onNext).toHaveBeenCalledWith("executions");
    fireEvent.click(screen.getByRole("tab", { name: "Cash ledger" }));
    expect(screen.getByRole("heading", { name: "Portfolio reporting" })).toBeInTheDocument();
  });

  it("clears a stale page boundary rather than combining history snapshots", () => {
    const restart = vi.fn();
    render(<PaperWorkspace cursorError="cursor_stale" onRestartPage={restart} />);
    expect(screen.getByRole("alert")).toHaveTextContent("History changed or expired");
    fireEvent.click(screen.getByRole("button", { name: "Restart history" }));
    expect(restart).toHaveBeenCalledOnce();
  });

  it("does not report P&L until the backend read contract supplies it", () => {
    render(<PaperWorkspace />);
    expect(screen.getByText(/P&L are unavailable in the current generated portfolio read contract/)).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(5);
  });
});
