import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useRunStore } from "@/lib/store";

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

import { ResultsTabs } from "../ResultsTabs";
import type { AnalysisResult } from "../../lib/api";

const result: AnalysisResult = {
  regime: {
    regime: "range_bound",
    confidence: 0.95,
    entropy: 0.187,
    distribution: { range_bound: 24 },
  },
  direction: {
    direction: "down",
    confidence: 0.70,
    entropy: 0.607,
    prediction_date: "2023-06-30",
    distribution: { down: 20 },
  },
  drift: null,
  feature_importance: null,
  backtest: null,
  summary: "Test summary.",
  usage: { input_tokens: 100, output_tokens: 10, estimated_cost_usd: 0.001 },
  data_manifest: {},
};

beforeEach(() => {
  useRunStore.setState({ status: "idle", messages: [], result: null, error: null, runId: null });
});

describe("ResultsTabs", () => {
  it("defaults to Overview tab", () => {
    render(<ResultsTabs result={result} />);
    expect(screen.getAllByText(/range.bound/i).length).toBeGreaterThan(0);
  });

  it("switches to Summary tab when tab bar button clicked", () => {
    render(<ResultsTabs result={result} />);
    fireEvent.click(screen.getByRole("button", { name: /^✎ Summary$/ }));
    expect(screen.getByText("Test summary.")).toBeTruthy();
  });

  it("shows Features placeholder when clicked (null data)", () => {
    render(<ResultsTabs result={result} />);
    fireEvent.click(screen.getByRole("button", { name: /^≡ Features$/ }));
    expect(screen.getByText(/feature importance not available/i)).toBeTruthy();
  });

  it("shows Drift placeholder when clicked (null data)", () => {
    render(<ResultsTabs result={result} />);
    fireEvent.click(screen.getByRole("button", { name: /^⊘ Drift$/ }));
    expect(screen.getByText(/drift analysis not available/i)).toBeTruthy();
  });

  it("shows Backtest placeholder when clicked (null data)", () => {
    render(<ResultsTabs result={result} />);
    fireEvent.click(screen.getByRole("button", { name: /^↗ Backtest$/ }));
    expect(screen.getByText(/backtest not available/i)).toBeTruthy();
  });

  it("sidebar icon click also switches tab", () => {
    render(<ResultsTabs result={result} />);
    fireEvent.click(screen.getByRole("button", { name: "Summary sidebar" }));
    expect(screen.getByText("Test summary.")).toBeTruthy();
  });

  it("hides Agent button when status is idle", () => {
    useRunStore.setState({ status: "idle" });
    render(<ResultsTabs result={result} />);
    expect(screen.queryByRole("button", { name: /agent/i })).toBeNull();
  });

  it("shows Agent button when status is running", () => {
    useRunStore.setState({ status: "running", messages: [] });
    render(<ResultsTabs result={result} />);
    expect(screen.getByRole("button", { name: /agent/i })).toBeTruthy();
  });

  it("auto-opens drawer when running, toggles on click", () => {
    useRunStore.setState({ status: "running", messages: [] });
    render(<ResultsTabs result={result} />);
    // drawer auto-opens → button starts as "Collapse"
    const btn = screen.getByRole("button", { name: /collapse agent drawer/i });
    fireEvent.click(btn);
    expect(screen.getByRole("button", { name: /expand agent drawer/i })).toBeTruthy();
  });

  it("shows simple waiting copy for unavailable tabs while running", () => {
    useRunStore.setState({ status: "running", messages: [] });
    render(<ResultsTabs result={null} />);
    fireEvent.click(screen.getByRole("button", { name: /^≡ Features$/ }));
    expect(screen.getByText("Waiting for results")).toBeTruthy();
    expect(
      screen.getByText("This tab will update when the agent finishes the relevant step.")
    ).toBeTruthy();
  });
});
