import { render, screen } from "@testing-library/react";
import { AgentProgressTimeline } from "../AgentProgressTimeline";
import { buildAgentProgress } from "@/lib/agentProgress";
import type { StreamMessage } from "@/lib/websocket";

function makeState(messages: StreamMessage[]) {
  return buildAgentProgress(messages);
}

describe("AgentProgressTimeline", () => {
  it("shows empty state when not running and all phases are waiting", () => {
    const state = makeState([]);
    render(<AgentProgressTimeline state={state} isRunning={false} connected={false} />);
    expect(screen.getByText(/run an analysis/i)).toBeInTheDocument();
  });

  it("shows connecting indicator when running, not connected, and no progress yet", () => {
    const state = makeState([]);
    render(<AgentProgressTimeline state={state} isRunning={true} connected={false} />);
    expect(screen.getByText(/connecting/i)).toBeInTheDocument();
  });

  it("shows all 9 phase titles once a run starts", () => {
    const state = makeState([{ type: "phase", phase: "fetching_market_data" }]);
    render(<AgentProgressTimeline state={state} isRunning={true} connected={true} />);
    expect(screen.getByText("Preparing data")).toBeInTheDocument();
    expect(screen.getByText("Predicting direction")).toBeInTheDocument();
    expect(screen.getByText("Final summary")).toBeInTheDocument();
  });

  it("shows phase descriptions for timeline context", () => {
    const state = makeState([{ type: "phase", phase: "fetching_market_data" }]);
    render(<AgentProgressTimeline state={state} isRunning={true} connected={true} />);
    expect(
      screen.getByText("Collecting market, macro, and geopolitical inputs.")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Classifying the current oil market regime.")
    ).toBeInTheDocument();
  });

  it("shows only the latest thought in the active phase", () => {
    const state = makeState([
      { type: "phase", phase: "fetching_market_data" },
      { type: "thought", content: "Fetching WTI spot prices" },
      { type: "thought", content: "Now fetching FRED data" },
    ]);
    render(<AgentProgressTimeline state={state} isRunning={true} connected={true} />);
    expect(screen.getByText("Now fetching FRED data")).toBeInTheDocument();
    expect(screen.queryByText("Fetching WTI spot prices")).not.toBeInTheDocument();
  });

  it("shows progress bar with call count when tabpfn_progress arrives", () => {
    const state = makeState([
      { type: "phase", phase: "predicting_regime" },
      {
        type: "tabpfn_progress",
        completed_calls: 15,
        estimated_calls: 24,
        unknown_backtest: false,
      },
    ]);
    render(<AgentProgressTimeline state={state} isRunning={true} connected={true} />);
    expect(screen.getByText("15 / 24")).toBeInTheDocument();
  });

  it("shows indeterminate progress label when backtest total is unknown", () => {
    const state = makeState([
      { type: "phase", phase: "backtesting" },
      {
        type: "tabpfn_progress",
        completed_calls: 3,
        estimated_calls: 3,
        unknown_backtest: true,
      },
    ]);
    render(<AgentProgressTimeline state={state} isRunning={true} connected={true} />);
    expect(screen.getByText("3 calls")).toBeInTheDocument();
  });

  it("shows evidence chips on a completed phase", () => {
    const state = makeState([
      { type: "phase", phase: "engineering_features" },
      {
        type: "tool_result",
        tool: "engineer_features",
        output: { feature_count: 47 },
      },
    ]);
    render(<AgentProgressTimeline state={state} isRunning={true} connected={true} />);
    expect(screen.getByText("Features: 47")).toBeInTheDocument();
  });

  it("shows all phases including remaining waiting ones when a phase fails", () => {
    const state = makeState([
      { type: "phase", phase: "fetching_market_data" },
      { type: "phase", phase: "failed" },
    ]);
    render(<AgentProgressTimeline state={state} isRunning={false} connected={false} />);
    expect(screen.getByText("Preparing data")).toBeInTheDocument();
    expect(screen.getByText("Final summary")).toBeInTheDocument();
  });

  it("shows the done summary note in the final_summary phase on completion", () => {
    const state = makeState([
      { type: "phase", phase: "fetching_market_data" },
      { type: "phase", phase: "completed" },
      { type: "done", summary: "Range-bound regime detected with high confidence." },
    ]);
    render(<AgentProgressTimeline state={state} isRunning={false} connected={false} />);
    expect(screen.getByText("Final summary")).toBeInTheDocument();
    expect(
      screen.getByText("Range-bound regime detected with high confidence.")
    ).toBeInTheDocument();
  });
});
