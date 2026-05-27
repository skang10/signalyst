import { describe, expect, it } from "vitest";
import { buildAgentProgress } from "../agentProgress";
import type { StreamMessage } from "../websocket";

function phaseState(messages: StreamMessage[]) {
  return buildAgentProgress(messages).phases.reduce(
    (byId, phase) => ({ ...byId, [phase.id]: phase }),
    {} as Record<string, ReturnType<typeof buildAgentProgress>["phases"][number]>
  );
}

describe("buildAgentProgress", () => {
  it("does not include repeated starting events in raw diagnostics", () => {
    const state = buildAgentProgress([
      { type: "phase", phase: "starting" },
      { type: "phase", phase: "starting" },
      { type: "phase", phase: "fetching_market_data" },
    ]);

    expect(state.rawEvents).toEqual(["phase fetching_market_data"]);
  });

  it("advances phases when a later backend phase starts", () => {
    const phases = phaseState([
      { type: "phase", phase: "fetching_market_data" },
      { type: "phase", phase: "predicting_regime" },
    ]);

    expect(phases.preparing_data.status).toBe("done");
    expect(phases.predicting_regime.status).toBe("running");
  });

  it("tracks TabPFN estimates and attaches progress to the active phase", () => {
    const state = buildAgentProgress([
      {
        type: "tabpfn_estimate",
        known_calls: 3,
        unknown_backtest: true,
        note: "Full backtest call count depends on feature row count",
      },
      { type: "phase", phase: "predicting_regime" },
      {
        type: "tabpfn_progress",
        completed_calls: 1,
        estimated_calls: 3,
        unknown_backtest: true,
        tool: "run_tabpfn",
      },
    ]);

    expect(state.tabpfn).toEqual({
      completed: 1,
      estimated: 3,
      unknownBacktest: true,
      note: "Full backtest call count depends on feature row count",
    });
    expect(state.phases.find((phase) => phase.id === "predicting_regime")?.progress).toEqual({
      completed: 1,
      total: 3,
      unknownTotal: true,
    });
  });

  it("extracts compact run_tabpfn regime and detect_drift evidence", () => {
    const phases = phaseState([
      {
        type: "tool_result",
        tool: "run_tabpfn",
        output: {
          task: "regime",
          current_prediction: "range_bound",
          mean_confidence: 0.95,
        },
      },
      {
        type: "tool_result",
        tool: "detect_drift",
        output: {
          drift_detected: true,
          psi_total: 5.05,
        },
      },
    ]);

    expect(phases.predicting_regime.evidence).toEqual([
      { label: "Regime", value: "range_bound · 95.0%", tone: "accent" },
    ]);
    expect(phases.checking_drift.evidence).toEqual([
      { label: "Drift", value: "Elevated · PSI 5.05", tone: "warning" },
    ]);
  });

  it("marks final summary done and stores the summary note from done events", () => {
    const phases = phaseState([
      { type: "phase", phase: "explaining" },
      { type: "done", summary: "Oil remains range-bound with elevated drift risk." },
    ]);

    expect(phases.explaining_drivers.status).toBe("done");
    expect(phases.final_summary.status).toBe("done");
    expect(phases.final_summary.notes).toEqual([
      "Oil remains range-bound with elevated drift risk.",
    ]);
  });

  it("marks final summary done for completed phase events", () => {
    const phases = phaseState([
      { type: "phase", phase: "explaining" },
      { type: "phase", phase: "completed" },
    ]);

    expect(phases.explaining_drivers.status).toBe("done");
    expect(phases.final_summary.status).toBe("done");
  });

  it("adds fallback notes when known tools have no compact evidence", () => {
    const phases = phaseState([
      { type: "tool_result", tool: "run_tabpfn", output: {} },
      { type: "tool_result", tool: "detect_drift", output: {} },
    ]);

    expect(phases.predicting_regime.status).toBe("done");
    expect(phases.predicting_regime.notes).toContain(
      "Completed; no compact evidence available"
    );
    expect(phases.checking_drift.status).toBe("done");
    expect(phases.checking_drift.notes).toContain(
      "Completed; no compact evidence available"
    );
  });

  it("extracts backtest windows and regime accuracy evidence", () => {
    const phases = phaseState([
      {
        type: "tool_result",
        tool: "backtest",
        output: { n_windows: 5, regime_accuracy: 0.71 },
      },
    ]);

    expect(phases.backtesting.evidence).toContainEqual({
      label: "Windows",
      value: "5",
      tone: "default",
    });
    expect(phases.backtesting.evidence).toContainEqual({
      label: "Regime accuracy",
      value: "71.0%",
      tone: "success",
    });
  });

  it("formats raw events for every stream message type required by Task 2", () => {
    const state = buildAgentProgress([
      { type: "phase", phase: "predicting_regime" },
      { type: "tool_call", tool: "run_tabpfn", input: { task: "regime" } },
      { type: "tool_result", tool: "run_tabpfn", output: {} },
      {
        type: "tabpfn_estimate",
        known_calls: 3,
        unknown_backtest: false,
        note: "Estimate includes configured TabPFN-backed tools",
      },
      {
        type: "tabpfn_progress",
        completed_calls: 1,
        estimated_calls: 2,
        unknown_backtest: false,
      },
      { type: "thought", content: "Checking model output." },
      { type: "done", summary: "Complete." },
      {
        type: "unknown",
        originalType: "backend_debug",
        payload: { type: "backend_debug", message: "extra detail" },
      },
    ]);

    expect(state.rawEvents).toEqual([
      "phase predicting_regime",
      'tool_call run_tabpfn {"task":"regime"}',
      "tool_result run_tabpfn",
      "tabpfn_estimate 3",
      "tabpfn_progress 1/2",
      "thought Checking model output.",
      "done",
      "backend_debug",
    ]);
  });
});
