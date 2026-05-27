import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ResultsPanel } from "../ResultsPanel";
import { useRunStore } from "@/lib/store";
import type { AnalysisResult } from "@/lib/api";

vi.mock("recharts", () => ({
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mockResult: AnalysisResult = {
  regime: {
    regime: "range_bound",
    confidence: 0.9503,
    entropy: 0.187,
    distribution: { range_bound: 24 },
  },
  direction: {
    direction: "down",
    confidence: 0.7046,
    entropy: 0.607,
    prediction_date: "2023-06-30",
    distribution: { down: 20 },
  },
  drift: null,
  feature_importance: null,
  backtest: null,
  summary: "Range-bound regime with high confidence.",
  usage: { input_tokens: 1000, output_tokens: 100, estimated_cost_usd: 0.01 },
  data_manifest: {},
};

beforeEach(() => {
  useRunStore.setState({ runId: null, status: "idle", result: null, error: null, messages: [] });
});

describe("ResultsPanel", () => {
  it("shows waiting state when status is running and result is null", () => {
    useRunStore.setState({ status: "running", result: null, messages: [] });
    render(<ResultsPanel />);
    expect(screen.getByText(/waiting for results/i)).toBeInTheDocument();
  });

  it("shows empty state when idle", () => {
    render(<ResultsPanel />);
    expect(screen.getByText(/results will appear/i)).toBeInTheDocument();
  });

  it("renders Overview tab with regime data when result is set", () => {
    useRunStore.setState({ status: "completed", result: mockResult });
    render(<ResultsPanel />);
    expect(screen.getAllByText(/range.bound/i).length).toBeGreaterThan(0);
  });

  it("renders direction data in Overview tab", () => {
    useRunStore.setState({ status: "completed", result: mockResult });
    render(<ResultsPanel />);
    expect(screen.getAllByText(/down/i).length).toBeGreaterThan(0);
  });

  it("shows tab bar navigation", () => {
    useRunStore.setState({ status: "completed", result: mockResult });
    render(<ResultsPanel />);
    expect(screen.getByRole("button", { name: /^✎ Summary$/ })).toBeTruthy();
  });

  it("shows error state when status is failed", () => {
    useRunStore.setState({ status: "failed", error: "Network error" });
    render(<ResultsPanel />);
    expect(screen.getByText(/Network error/i)).toBeInTheDocument();
  });
});
