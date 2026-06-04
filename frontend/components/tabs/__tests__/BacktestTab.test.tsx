import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("recharts", () => ({
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

import { BacktestTab } from "../BacktestTab";

type BacktestResult = Record<string, unknown>;
const backtest: BacktestResult = {
  regime_accuracy: 0.74,
  strategy_sharpe: 1.42,
  benchmark_sharpe: 0.87,
  n_windows: 12,
};

describe("BacktestTab", () => {
  it("renders regime accuracy as percentage", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByText(/74\.0%/)).toBeTruthy();
  });

  it("renders strategy Sharpe", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByText("1.42")).toBeTruthy();
  });

  it("renders benchmark Sharpe", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByText("0.87")).toBeTruthy();
  });

  it("renders the bar chart", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByTestId("bar-chart")).toBeTruthy();
  });

  it("renders n_windows", () => {
    render(<BacktestTab backtest={backtest} />);
    expect(screen.getByText(/12 windows/)).toBeTruthy();
  });

  it("renders placeholder when backtest is null", () => {
    render(<BacktestTab backtest={null} />);
    expect(screen.getByText(/backtest not available/i)).toBeTruthy();
  });
});
