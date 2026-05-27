import type { StreamMessage } from "./websocket";

export type PhaseStatus = "waiting" | "running" | "done" | "failed" | "canceled";
export type EvidenceTone = "default" | "accent" | "success" | "warning" | "danger";

export interface PhaseEvidence {
  label: string;
  value: string;
  tone?: EvidenceTone;
}

export interface AgentPhase {
  id:
    | "preparing_data"
    | "engineering_features"
    | "checking_drift"
    | "predicting_regime"
    | "predicting_direction"
    | "evaluating_features"
    | "backtesting"
    | "explaining_drivers"
    | "final_summary";
  title: string;
  description: string;
  status: PhaseStatus;
  evidence: PhaseEvidence[];
  notes: string[];
  progress?: {
    completed: number;
    total: number;
    unknownTotal: boolean;
  };
}

export interface AgentProgressState {
  phases: AgentPhase[];
  rawEvents: string[];
  tabpfn: null | {
    completed: number;
    estimated: number;
    unknownBacktest: boolean;
    note?: string;
  };
}

type PhaseId = AgentPhase["id"];
type TabpfnState = NonNullable<AgentProgressState["tabpfn"]>;

const PHASE_DEFINITIONS: Array<Omit<AgentPhase, "status" | "evidence" | "notes" | "progress">> = [
  {
    id: "preparing_data",
    title: "Preparing data",
    description: "Collecting market, macro, and geopolitical inputs.",
  },
  {
    id: "engineering_features",
    title: "Engineering features",
    description: "Building model-ready signals from source data.",
  },
  {
    id: "checking_drift",
    title: "Checking drift",
    description: "Testing whether recent feature behavior shifted.",
  },
  {
    id: "predicting_regime",
    title: "Predicting regime",
    description: "Classifying the current oil market regime.",
  },
  {
    id: "predicting_direction",
    title: "Predicting direction",
    description: "Estimating WTI price direction.",
  },
  {
    id: "evaluating_features",
    title: "Evaluating features",
    description: "Ranking the drivers behind the model output.",
  },
  {
    id: "backtesting",
    title: "Backtesting",
    description: "Validating historical regime and direction performance.",
  },
  {
    id: "explaining_drivers",
    title: "Explaining drivers",
    description: "Synthesizing model evidence into a narrative.",
  },
  {
    id: "final_summary",
    title: "Final summary",
    description: "Capturing the completed analysis.",
  },
];

const BACKEND_PHASES: Record<string, PhaseId | null> = {
  starting: null,
  fetching_market_data: "preparing_data",
  fetching_geopolitical_risk: "preparing_data",
  engineering_features: "engineering_features",
  detecting_drift: "checking_drift",
  predicting_regime: "predicting_regime",
  predicting_direction: "predicting_direction",
  evaluating_features: "evaluating_features",
  backtesting: "backtesting",
  explaining: "explaining_drivers",
  completed: "final_summary",
};

const TOOL_PHASES: Record<string, PhaseId> = {
  fetch_data: "preparing_data",
  fetch_geopolitical_risk: "preparing_data",
  engineer_features: "engineering_features",
  detect_drift: "checking_drift",
  evaluate_features: "evaluating_features",
  backtest: "backtesting",
  explain_prediction: "explaining_drivers",
};

function createPhases(): AgentPhase[] {
  return PHASE_DEFINITIONS.map((phase) => ({
    ...phase,
    status: "waiting",
    evidence: [],
    notes: [],
  }));
}

function getPhase(phases: AgentPhase[], id: PhaseId): AgentPhase {
  return phases.find((phase) => phase.id === id) as AgentPhase;
}

function currentRunningPhase(phases: AgentPhase[]): AgentPhase | undefined {
  return phases.find((phase) => phase.status === "running");
}

function isTerminal(status: PhaseStatus): boolean {
  return status === "failed" || status === "canceled";
}

function markRunning(phases: AgentPhase[], id: PhaseId): void {
  for (const phase of phases) {
    if (phase.status === "running" && phase.id !== id) {
      phase.status = "done";
    }
  }

  const nextPhase = getPhase(phases, id);
  if (!isTerminal(nextPhase.status)) {
    nextPhase.status = "running";
  }
}

function completeRunningPhases(phases: AgentPhase[]): void {
  for (const phase of phases) {
    if (phase.status === "running") {
      phase.status = "done";
    }
  }
}

function failActivePhase(phases: AgentPhase[], status: "failed" | "canceled"): void {
  const active = currentRunningPhase(phases);
  if (active) {
    active.status = status;
    return;
  }

  getPhase(phases, "final_summary").status = status;
}

function phaseForTool(tool: string, output?: unknown): PhaseId | undefined {
  if (tool === "run_tabpfn") {
    if (isRecord(output)) {
      if (output.task === "regime") return "predicting_regime";
      if (output.task === "direction") return "predicting_direction";
    }
    return "predicting_regime";
  }

  return TOOL_PHASES[tool];
}

function rawEvent(message: StreamMessage): string {
  switch (message.type) {
    case "phase":
      return `phase ${message.phase}`;
    case "tool_call":
      return `tool_call ${message.tool} ${compactJson(message.input)}`;
    case "tool_result":
      return `tool_result ${message.tool}`;
    case "tabpfn_progress":
      return `tabpfn_progress ${message.completed_calls}/${message.estimated_calls}`;
    case "tabpfn_estimate":
      return `tabpfn_estimate ${message.known_calls}`;
    case "thought":
      return `thought ${message.content}`;
    case "done":
      return "done";
    case "unknown":
      return message.originalType || message.type;
    case "prediction":
      return message.type;
  }
}

function compactJson(value: unknown): string {
  return JSON.stringify(value) ?? String(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(record: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
  }
  return undefined;
}

function readNumber(record: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return undefined;
}

function readBoolean(record: Record<string, unknown>, keys: string[]): boolean | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "boolean") {
      return value;
    }
  }
  return undefined;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)));
}

function addEvidence(phase: AgentPhase, evidence: PhaseEvidence[]): void {
  if (evidence.length > 0) {
    phase.evidence.push(...evidence);
  } else {
    phase.notes.push("Completed; no compact evidence available");
  }
}

function topFeatureNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => {
      if (typeof item === "string") return item;
      if (isRecord(item)) return readString(item, ["name", "feature"]);
      return undefined;
    })
    .filter((item): item is string => Boolean(item));
}

function evidenceForTool(tool: string, output: unknown): PhaseEvidence[] {
  if (!isRecord(output)) return [];

  switch (tool) {
    case "run_tabpfn": {
      const task = readString(output, ["task"]);
      const prediction = readString(output, [
        "current_prediction",
        "prediction",
        "label",
        "direction",
        "regime",
      ]);
      const confidence = readNumber(output, ["confidence", "mean_confidence"]);
      if (!task || !prediction || confidence === undefined) return [];

      return [
        {
          label: task === "direction" ? "Direction" : "Regime",
          value: `${prediction} · ${formatPercent(confidence)}`,
          tone: "accent",
        },
      ];
    }
    case "detect_drift": {
      const drifted = readBoolean(output, ["drift_detected", "is_drifted"]);
      const psi = readNumber(output, ["psi_total", "psi", "psi_score"]);
      if (drifted === undefined || psi === undefined) return [];

      return [
        {
          label: "Drift",
          value: `${drifted ? "Elevated" : "Stable"} · PSI ${formatNumber(psi)}`,
          tone: drifted ? "warning" : "success",
        },
      ];
    }
    case "fetch_data":
    case "fetch_geopolitical_risk": {
      const summary = readString(output, ["summary"]);
      if (summary) return [{ label: "Data", value: summary, tone: "default" }];

      const fetched = isRecord(output.fetched) ? output.fetched : undefined;
      if (fetched) {
        const tickers = Object.keys(fetched);
        if (tickers.length > 0) {
          return [{ label: "Sources", value: tickers.join(", "), tone: "default" }];
        }
      }

      const tickers = Array.isArray(output.tickers)
        ? output.tickers.filter((ticker): ticker is string => typeof ticker === "string")
        : [];
      return tickers.length > 0
        ? [{ label: "Tickers", value: tickers.join(", "), tone: "default" }]
        : [];
    }
    case "engineer_features": {
      const featureCount =
        readNumber(output, ["feature_count", "n_features"]) ??
        (Array.isArray(output.shape) && typeof output.shape[1] === "number"
          ? output.shape[1]
          : undefined);
      return featureCount === undefined
        ? []
        : [{ label: "Features", value: String(featureCount), tone: "success" }];
    }
    case "evaluate_features":
    case "explain_prediction": {
      const features = topFeatureNames(output.top_features ?? output.key_features);
      return features.length > 0
        ? [{ label: "Top features", value: features.slice(0, 3).join(", "), tone: "accent" }]
        : [];
    }
    case "backtest": {
      const windows = readNumber(output, ["n_windows"]);
      const accuracy = readNumber(output, ["regime_accuracy"]);
      const evidence: PhaseEvidence[] = [];
      if (windows !== undefined) {
        evidence.push({ label: "Windows", value: String(windows), tone: "default" });
      }
      if (accuracy !== undefined) {
        evidence.push({
          label: "Regime accuracy",
          value: formatPercent(accuracy),
          tone: "success",
        });
      }
      return evidence;
    }
    default:
      return [];
  }
}

export function buildAgentProgress(messages: StreamMessage[]): AgentProgressState {
  const phases = createPhases();
  const rawEvents: string[] = [];
  let tabpfn: TabpfnState | null = null;

  for (const message of messages) {
    if (!(message.type === "phase" && message.phase === "starting")) {
      rawEvents.push(rawEvent(message));
    }

    switch (message.type) {
      case "phase": {
        if (message.phase === "failed" || message.phase === "canceled") {
          failActivePhase(phases, message.phase);
          break;
        }

        const phaseId = BACKEND_PHASES[message.phase];
        if (phaseId) {
          if (message.phase === "completed") {
            completeRunningPhases(phases);
            getPhase(phases, phaseId).status = "done";
          } else {
            markRunning(phases, phaseId);
          }
        }
        break;
      }
      case "tabpfn_estimate":
        tabpfn = {
          completed: tabpfn === null ? 0 : tabpfn.completed,
          estimated: message.known_calls,
          unknownBacktest: message.unknown_backtest,
          note: message.note,
        };
        break;
      case "tabpfn_progress": {
        tabpfn = {
          completed: message.completed_calls,
          estimated: message.estimated_calls,
          unknownBacktest: message.unknown_backtest,
          note: tabpfn === null ? undefined : tabpfn.note,
        };

        const active = currentRunningPhase(phases);
        if (active) {
          active.progress = {
            completed: message.completed_calls,
            total: message.estimated_calls,
            unknownTotal: message.unknown_backtest,
          };
        }
        break;
      }
      case "tool_result": {
        const phaseId = phaseForTool(message.tool, message.output);
        if (phaseId) {
          const phase = getPhase(phases, phaseId);
          addEvidence(phase, evidenceForTool(message.tool, message.output));
          if (!isTerminal(phase.status)) {
            phase.status = "done";
          }
        }
        break;
      }
      case "thought": {
        if (message.content.length <= 160) {
          currentRunningPhase(phases)?.notes.push(message.content);
        }
        break;
      }
      case "done": {
        completeRunningPhases(phases);
        const finalSummary = getPhase(phases, "final_summary");
        finalSummary.status = "done";
        finalSummary.notes.push(message.summary);
        break;
      }
      case "tool_call":
      case "prediction":
      case "unknown":
        break;
    }
  }

  return { phases, rawEvents, tabpfn };
}
