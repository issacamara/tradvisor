import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";
import { ChartAccessibleData } from "./chart-placeholder";

describe("ChartAccessibleData", () => {
  it("provides readable price and score tables for chart data", () => {
    render(<ChartAccessibleData />);

    expect(screen.getByRole("table", { name: "Illustrative closing-price data in XOF" })).toHaveTextContent("2025-01-07");
    expect(screen.getByRole("table", { name: "Illustrative research score data" })).toHaveTextContent("Growth");
    expect(screen.getByRole("cell", { name: "133 XOF" })).toBeInTheDocument();
  });
});
