# Agent Progress Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw left-panel tool stream with a grouped agent progress timeline that shows phase status, compact evidence, TabPFN progress, and collapsed raw events.

**Architecture:** Keep the backend protocol unchanged. Extend the frontend WebSocket message union, add a pure stream-to-progress-state mapper, then render that state from `AgentStreamView`. Keep raw events available through a collapsed disclosure at the bottom.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest, Testing Library, Tailwind CSS.

---

## File Structure

- Create `frontend/lib/agentProgress.ts`
  - Owns phase definitions, stream-event mapping, evidence extraction, raw-event formatting, and derived progress state.
  - Pure TypeScript; no React dependency.
- Create `frontend/lib/__tests__/agentProgress.test.ts`
  - Tests phase advancement, TabPFN progress, evidence extraction, raw-event formatting, and terminal states.
- Modify `frontend/lib/websocket.ts`
  - Add currently emitted backend event types: `phase`, `tabpfn_estimate`, `tabpfn_progress`, and optional `usage` on `done`.
- Modify `frontend/components/AgentStreamView.tsx`
  - Replace raw chronological primary rendering with the Agent Progress timeline.
  - Keep empty, connecting, and connection-lost states.
  - Add collapsed raw-events disclosure.
- Modify `frontend/components/__tests__/AgentStreamView.test.tsx`
  - Replace raw tool-row assertions with timeline/evidence/raw-disclosure assertions.

---

### Task 1: Extend Stream Message Types

**Files:**
- Modify: `frontend/lib/websocket.ts`
- Test: `frontend/lib/__tests__/websocket.test.ts`

- [ ] **Step 1: Update the stream message union**

In `frontend/lib/websocket.ts`, replace the `StreamMessage` type with:

```ts
export type StreamMessage =
  | { type: "thought"; content: string }
  | { type: "phase"; phase: string; tool?: string | null }
  | { type: "tabpfn_estimate"; known_calls: number; unknown_backtest: boolean; note: string }
  | {
      type: "tabpfn_progress";
      completed_calls: number;
      estimated_calls: number;
      unknown_backtest: boolean;
      tool?: string | null;
    }
  | { type: "tool_call"; tool: string; input: unknown }
  | { type: "tool_result"; tool: string; output: unknown }
  | { type: "prediction"; regime: string; confidence: number }
  | {
      type: "done";
      summary: string;
      usage?: {
        input_tokens: number;
        output_tokens: number;
        estimated_cost_usd: number;
      };
    }
  | { type: string; [key: string]: unknown };
```

Reason for the final fallback member: unknown backend events should remain stored in raw history and ignored by primary UI.

- [ ] **Step 2: Add a websocket hook test for new event types**

Append this test to `frontend/lib/__tests__/websocket.test.ts`:

```ts
  it("preserves structured progress messages from the backend", () => {
    const { result } = renderHook(() => useRunStream("run-1"));

    act(() =>
      MockWebSocket.instances[0].emit({
        type: "tabpfn_progress",
        completed_calls: 1,
        estimated_calls: 2,
        unknown_backtest: false,
        tool: "run_tabpfn",
      })
    );

    expect(result.current.messages[0]).toEqual({
      type: "tabpfn_progress",
      completed_calls: 1,
      estimated_calls: 2,
      unknown_backtest: false,
      tool: "run_tabpfn",
    });
  });
```

- [ ] **Step 3: Run the websocket tests**

Run:

```bash
cd frontend
npm run test -- lib/__tests__/websocket.test.ts
```

Expected: all websocket tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/websocket.ts frontend/lib/__tests__/websocket.test.ts
git commit -m "feat: type structured stream events"
```

---

### Task 2: Build the Agent Progress State Mapper

**Files:**
- Create: `frontend/lib/agentProgress.ts`
- Create: `frontend/lib/__tests__/agentProgress.test.ts`

- [ ] **Step 1: Create failing tests for timeline derivation**

Create `frontend/lib/__tests__/agentProgress.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { StreamMessage } from "../websocket";
import { buildAgentProgress } from "../agentProgress";

describe("buildAgentProgress", () => {
  it("advances phases from phase events", () => {
    const messages: StreamMessage[] = [
      { type: "phase", phase: "starting", tool: null },
      { type: "phase", phase: "fetching_market_data", tool: "fetch_data" },
      { type: "phase", phase: "predicting_regime", tool: "run_tabpfn" },
    ];

    const progress = buildAgentProgress(messages);

    expect(progress.phases.find((phase) => phase.id === "preparing_data")?.status).toBe("done");
    expect(progress.phases.find((phase) => phase.id === "predicting_regime")?.status).toBe("running");
  });

  it("tracks TabPFN estimate and progress", () => {
    const progress = buildAgentProgress([
      {
        type: "tabpfn_estimate",
        known_calls: 2,
        unknown_backtest: false,
        note: "Estimate includes configured TabPFN-backed tools",
      },
      {
        type: "tabpfn_progress",
        completed_calls: 1,
        estimated_calls: 2,
        unknown_backtest: false,
        tool: "run_tabpfn",
      },
    ]);

    expect(progress.tabpfn).toEqual({
      completed: 1,
      estimated: 2,
      unknownBacktest: false,
      note: "Estimate includes configured TabPFN-backed tools",
    });
  });

  it("extracts compact evidence from tool results", () => {
    const progress = buildAgentProgress([
      {
        type: "tool_result",
        tool: "run_tabpfn",
        output: { task: "regime", prediction: "range_bound", confidence: 0.9496 },
      },
      {
        type: "tool_result",
        tool: "detect_drift",
        output: { drift_detected: true, psi_total: 5.05 },
      },
    ]);

    expect(progress.phases.find((phase) => phase.id === "predicting_regime")?.evidence).toContainEqual({
      label: "Regime",
      value: "range_bound · 95.0%",
      tone: "accent",
    });
    expect(progress.phases.find((phase) => phase.id === "checking_drift")?.evidence).toContainEqual({
      label: "Drift",
      value: "Elevated · PSI 5.05",
      tone: "warning",
    });
  });

  it("marks final summary complete from done events", () => {
    const progress = buildAgentProgress([{ type: "done", summary: "Analysis complete" }]);
    const finalSummary = progress.phases.find((phase) => phase.id === "final_summary");

    expect(finalSummary?.status).toBe("done");
    expect(finalSummary?.notes).toContain("Analysis complete");
  });

  it("formats raw events for debug disclosure", () => {
    const progress = buildAgentProgress([
      { type: "phase", phase: "predicting_regime", tool: "run_tabpfn" },
      { type: "tool_call", tool: "run_tabpfn", input: { task: "regime" } },
      {
        type: "tabpfn_progress",
        completed_calls: 1,
        estimated_calls: 2,
        unknown_backtest: false,
        tool: "run_tabpfn",
      },
    ]);

    expect(progress.rawEvents).toEqual([
      "phase predicting_regime",
      'tool_call run_tabpfn {"task":"regime"}',
      "tabpfn_progress 1/2",
    ]);
  });
});
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
cd frontend
npm run test -- lib/__tests__/agentProgress.test.ts
```

Expected: fail because `frontend/lib/agentProgress.ts` does not exist.

- [ ] **Step 3: Implement the mapper**

Create `frontend/lib/agentProgress.ts` with these exports and helpers:

```ts
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
  progress?: { completed: number; total: number; unknownTotal: boolean };
}

export interface AgentProgressState {
  phases: AgentPhase[];
  rawEvents: string[];
  tabpfn: {
    completed: number;
    estimated: number;
    unknownBacktest: boolean;
    note?: string;
  } | null;
}

const PHASES: Omit<AgentPhase, "status" | "evidence" | "notes" | "progress">[] = [
  { id: "preparing_data", title: "Preparing data", description: "Loading market, macro, and geopolitical inputs." },
  { id: "engineering_features", title: "Engineering features", description: "Building model-ready features from source signals." },
  { id: "checking_drift", title: "Checking drift", description: "Checking whether feature behavior has shifted." },
  { id: "predicting_regime", title: "Predicting regime", description: "Classifying the current oil market regime." },
  { id: "predicting_direction", title: "Predicting direction", description: "Predicting the next WTI direction signal." },
  { id: "evaluating_features", title: "Evaluating features", description: "Estimating which features drove the model output." },
  { id: "backtesting", title: "Backtesting", description: "Validating signals on historical windows." },
  { id: "explaining_drivers", title: "Explaining drivers", description: "Synthesizing model outputs into a concise narrative." },
  { id: "final_summary", title: "Final summary", description: "Final analysis result." },
];

const PHASE_EVENT_TO_ID: Record<string, AgentPhase["id"] | "none"> = {
  starting: "none",
  fetching_market_data: "preparing_data",
  engineering_features: "engineering_features",
  detecting_drift: "checking_drift",
  predicting_regime: "predicting_regime",
  predicting_direction: "predicting_direction",
  evaluating_features: "evaluating_features",
  backtesting: "backtesting",
  explaining: "explaining_drivers",
  completed: "final_summary",
  failed: "none",
  canceled: "none",
};

export function buildAgentProgress(messages: StreamMessage[]): AgentProgressState {
  const phases = PHASES.map((phase) => ({
    ...phase,
    status: "waiting" as PhaseStatus,
    evidence: [],
    notes: [],
  }));
  const rawEvents: string[] = [];
  let activePhaseId: AgentPhase["id"] | null = null;
  let tabpfn: AgentProgressState["tabpfn"] = null;

  const phaseById = (id: AgentPhase["id"]) => phases.find((phase) => phase.id === id);
  const markRunning = (id: AgentPhase["id"]) => {
    if (activePhaseId && activePhaseId !== id) {
      const active = phaseById(activePhaseId);
      if (active?.status === "running") active.status = "done";
    }
    const phase = phaseById(id);
    if (phase && phase.status === "waiting") phase.status = "running";
    activePhaseId = id;
  };
  const markDone = (id: AgentPhase["id"]) => {
    const phase = phaseById(id);
    if (phase && phase.status !== "failed" && phase.status !== "canceled") phase.status = "done";
  };

  for (const message of messages) {
    rawEvents.push(formatRawEvent(message));

    if (message.type === "phase") {
      if (message.phase === "failed" && activePhaseId) {
        const active = phaseById(activePhaseId);
        if (active) active.status = "failed";
        continue;
      }
      if (message.phase === "canceled" && activePhaseId) {
        const active = phaseById(activePhaseId);
        if (active) active.status = "canceled";
        continue;
      }
      const phaseId = PHASE_EVENT_TO_ID[message.phase];
      if (phaseId && phaseId !== "none") {
        markRunning(phaseId);
        if (message.phase === "completed") markDone(phaseId);
      }
      continue;
    }

    if (message.type === "tabpfn_estimate") {
      tabpfn = {
        completed: 0,
        estimated: message.known_calls,
        unknownBacktest: message.unknown_backtest,
        note: message.note,
      };
      continue;
    }

    if (message.type === "tabpfn_progress") {
      tabpfn = {
        completed: message.completed_calls,
        estimated: message.estimated_calls,
        unknownBacktest: message.unknown_backtest,
        note: tabpfn?.note,
      };
      if (activePhaseId) {
        const active = phaseById(activePhaseId);
        if (active) {
          active.progress = {
            completed: message.completed_calls,
            total: message.estimated_calls,
            unknownTotal: message.unknown_backtest,
          };
        }
      }
      continue;
    }

    if (message.type === "tool_result") {
      const { phaseId, evidence } = evidenceFromToolResult(message.tool, message.output);
      if (phaseId) {
        const phase = phaseById(phaseId);
        if (phase) {
          phase.status = phase.status === "waiting" ? "done" : phase.status;
          phase.evidence.push(...evidence);
          if (evidence.length === 0) {
            phase.notes.push("Completed; no compact evidence available");
          }
        }
      }
      continue;
    }

    if (message.type === "thought" && activePhaseId && message.content.length <= 220) {
      phaseById(activePhaseId)?.notes.push(message.content);
      continue;
    }

    if (message.type === "done") {
      if (activePhaseId) markDone(activePhaseId);
      const finalSummary = phaseById("final_summary");
      if (finalSummary) {
        finalSummary.status = "done";
        finalSummary.notes = [message.summary];
      }
    }
  }

  return { phases, rawEvents, tabpfn };
}

function evidenceFromToolResult(
  tool: string,
  output: unknown,
): { phaseId: AgentPhase["id"] | null; evidence: PhaseEvidence[] } {
  const value = isRecord(output) ? output : {};

  if (tool === "run_tabpfn") {
    const task = stringValue(value.task);
    const prediction = stringValue(value.prediction ?? value.label ?? value.direction);
    const confidence = numberValue(value.confidence);
    const evidence = prediction
      ? [{ label: task === "direction" ? "Direction" : "Regime", value: formatPrediction(prediction, confidence), tone: task === "direction" ? "danger" as const : "accent" as const }]
      : [];
    return { phaseId: task === "direction" ? "predicting_direction" : "predicting_regime", evidence };
  }

  if (tool === "detect_drift") {
    const psi = numberValue(value.psi_total ?? value.psi);
    const drift = Boolean(value.drift_detected ?? value.is_drifted);
    return {
      phaseId: "checking_drift",
      evidence: [{ label: "Drift", value: `${drift ? "Elevated" : "Stable"}${psi == null ? "" : ` · PSI ${psi.toFixed(2)}`}`, tone: drift ? "warning" : "success" }],
    };
  }

  if (tool === "fetch_data" || tool === "fetch_geopolitical_risk") {
    const tickers = Array.isArray(value.tickers) ? value.tickers.join(", ") : stringValue(value.summary);
    return { phaseId: "preparing_data", evidence: tickers ? [{ label: "Loaded", value: tickers }] : [] };
  }

  if (tool === "engineer_features") {
    const count = numberValue(value.feature_count ?? value.n_features);
    return { phaseId: "engineering_features", evidence: count == null ? [] : [{ label: "Features", value: String(count) }] };
  }

  if (tool === "evaluate_features" || tool === "explain_prediction") {
    const features = Array.isArray(value.top_features) ? value.top_features.slice(0, 3).map(String).join(", ") : null;
    return { phaseId: tool === "evaluate_features" ? "evaluating_features" : "explaining_drivers", evidence: features ? [{ label: "Top drivers", value: features }] : [] };
  }

  if (tool === "backtest") {
    const windows = numberValue(value.n_windows);
    const accuracy = numberValue(value.direction_accuracy ?? value.accuracy);
    return {
      phaseId: "backtesting",
      evidence: [
        ...(windows == null ? [] : [{ label: "Windows", value: String(windows) }]),
        ...(accuracy == null ? [] : [{ label: "Accuracy", value: `${(accuracy * 100).toFixed(1)}%` }]),
      ],
    };
  }

  return { phaseId: null, evidence: [] };
}

function formatRawEvent(message: StreamMessage): string {
  if (message.type === "phase") return `phase ${message.phase}`;
  if (message.type === "tool_call") return `tool_call ${message.tool} ${compactJson(message.input)}`;
  if (message.type === "tool_result") return `tool_result ${message.tool}`;
  if (message.type === "tabpfn_progress") return `tabpfn_progress ${message.completed_calls}/${message.estimated_calls}`;
  if (message.type === "tabpfn_estimate") return `tabpfn_estimate ${message.known_calls}`;
  if (message.type === "thought") return `thought ${message.content}`;
  if (message.type === "done") return "done";
  return message.type;
}

function compactJson(value: unknown): string {
  if (value == null) return "";
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

function formatPrediction(prediction: string, confidence: number | null): string {
  return confidence == null ? prediction : `${prediction} · ${(confidence * 100).toFixed(1)}%`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
```

- [ ] **Step 4: Run mapper tests**

Run:

```bash
cd frontend
npm run test -- lib/__tests__/agentProgress.test.ts
```

Expected: all mapper tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/agentProgress.ts frontend/lib/__tests__/agentProgress.test.ts
git commit -m "feat: derive agent progress state"
```

---

### Task 3: Render the Timeline UI

**Files:**
- Modify: `frontend/components/AgentStreamView.tsx`
- Modify: `frontend/components/__tests__/AgentStreamView.test.tsx`

- [ ] **Step 1: Replace component tests with progress UI expectations**

In `frontend/components/__tests__/AgentStreamView.test.tsx`, keep the empty/connecting/connection-lost tests and replace raw `tool_call`, `tool_result`, `prediction`, and `done` tests with:

```ts
  it("renders phase timeline and evidence instead of raw tool rows", () => {
    const messages: StreamMessage[] = [
      { type: "phase", phase: "predicting_regime", tool: "run_tabpfn" },
      {
        type: "tool_result",
        tool: "run_tabpfn",
        output: { task: "regime", prediction: "range_bound", confidence: 0.9496 },
      },
    ];

    render(<AgentStreamView messages={messages} connected={true} isRunning={true} />);

    expect(screen.getByText("Agent Progress")).toBeInTheDocument();
    expect(screen.getByText("Predicting regime")).toBeInTheDocument();
    expect(screen.getByText("range_bound · 95.0%")).toBeInTheDocument();
    expect(screen.queryByText(/tool_call run_tabpfn/)).not.toBeInTheDocument();
  });

  it("renders TabPFN progress in the header", () => {
    const messages: StreamMessage[] = [
      { type: "tabpfn_estimate", known_calls: 2, unknown_backtest: false, note: "Estimate includes configured TabPFN-backed tools" },
      { type: "tabpfn_progress", completed_calls: 1, estimated_calls: 2, unknown_backtest: false, tool: "run_tabpfn" },
    ];

    render(<AgentStreamView messages={messages} connected={true} isRunning={true} />);

    expect(screen.getByText("TabPFN 1 / 2")).toBeInTheDocument();
  });

  it("keeps raw events collapsed by default", () => {
    const messages: StreamMessage[] = [
      { type: "tool_call", tool: "run_tabpfn", input: { task: "regime" } },
    ];

    render(<AgentStreamView messages={messages} connected={true} isRunning={true} />);

    expect(screen.getByText("Raw events · 1 message")).toBeInTheDocument();
    expect(screen.queryByText(/tool_call run_tabpfn/)).not.toBeInTheDocument();
  });

  it("shows final summary when done", () => {
    const messages: StreamMessage[] = [{ type: "done", summary: "Analysis complete" }];

    render(<AgentStreamView messages={messages} connected={true} isRunning={true} />);

    expect(screen.getByText("Final summary")).toBeInTheDocument();
    expect(screen.getByText("Analysis complete")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run component tests and verify they fail**

Run:

```bash
cd frontend
npm run test -- components/__tests__/AgentStreamView.test.tsx
```

Expected: fail because the component still renders the old raw rows.

- [ ] **Step 3: Replace `AgentStreamView` rendering**

In `frontend/components/AgentStreamView.tsx`, import the mapper and render derived state:

```tsx
import { buildAgentProgress, type AgentPhase, type EvidenceTone } from "@/lib/agentProgress";
import type { StreamMessage } from "@/lib/websocket";
```

Inside `AgentStreamView`, after the empty-state guard:

```tsx
  const progress = buildAgentProgress(messages);
```

Replace the old `messages.map` block with:

```tsx
      <div className="flex items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">Agent Progress</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Timeline and evidence from the current analysis
          </p>
        </div>
        {progress.tabpfn && (
          <span className="shrink-0 rounded-full border border-violet-500/40 bg-violet-500/10 px-2 py-1 text-xs font-semibold text-violet-300">
            TabPFN {progress.tabpfn.completed} / {progress.tabpfn.estimated}
            {progress.tabpfn.unknownBacktest ? "+" : ""}
          </span>
        )}
      </div>

      <div className="space-y-0">
        {progress.phases.map((phase, index) => (
          <PhaseRow
            key={phase.id}
            phase={phase}
            isLast={index === progress.phases.length - 1}
          />
        ))}
      </div>

      {progress.rawEvents.length > 0 && (
        <details className="mt-4 border-t border-slate-800 pt-3 text-xs text-slate-500">
          <summary className="cursor-pointer select-none text-slate-400 hover:text-slate-200">
            Raw events · {progress.rawEvents.length} {progress.rawEvents.length === 1 ? "message" : "messages"}
          </summary>
          <div className="mt-2 space-y-1 font-mono text-[11px] leading-5 text-slate-500">
            {progress.rawEvents.map((event, index) => (
              <div key={`${event}-${index}`}>{event}</div>
            ))}
          </div>
        </details>
      )}
```

Add helper components below `AgentStreamView`:

```tsx
function PhaseRow({ phase, isLast }: { phase: AgentPhase; isLast: boolean }) {
  const visible =
    phase.status !== "waiting" ||
    phase.evidence.length > 0 ||
    phase.notes.length > 0 ||
    phase.id === "final_summary";

  if (!visible) return null;

  return (
    <section className="grid grid-cols-[18px_1fr] gap-3">
      <div className="flex flex-col items-center">
        <span className={`mt-1 h-3 w-3 rounded-full ${statusDotClass(phase.status)}`} />
        {!isLast && <span className="mt-2 h-full min-h-8 w-px bg-slate-800" />}
      </div>
      <div className="pb-5">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-200">{phase.title}</h3>
          <span className="text-[11px] uppercase tracking-wide text-slate-500">{phase.status}</span>
        </div>
        <p className="mt-1 text-xs leading-5 text-slate-500">{phase.description}</p>
        {phase.progress && (
          <div className="mt-3">
            <div className="h-1.5 rounded-full bg-slate-800">
              <div
                className="h-1.5 rounded-full bg-violet-500"
                style={{ width: `${Math.min(100, (phase.progress.completed / Math.max(phase.progress.total, 1)) * 100)}%` }}
              />
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              Model calls {phase.progress.completed} / {phase.progress.total}
              {phase.progress.unknownTotal ? "+" : ""}
            </p>
          </div>
        )}
        {phase.evidence.length > 0 && (
          <div className="mt-3 grid gap-2">
            {phase.evidence.map((item) => (
              <div key={`${item.label}-${item.value}`} className="flex items-center justify-between gap-3 rounded border border-slate-800 bg-slate-950/50 px-2 py-1.5">
                <span className="text-xs text-slate-400">{item.label}</span>
                <span className={`text-right text-xs font-semibold ${evidenceTextClass(item.tone)}`}>{item.value}</span>
              </div>
            ))}
          </div>
        )}
        {phase.notes.map((note) => (
          <p key={note} className="mt-2 text-xs leading-5 text-slate-300">{note}</p>
        ))}
      </div>
    </section>
  );
}

function statusDotClass(status: AgentPhase["status"]) {
  if (status === "done") return "bg-emerald-500";
  if (status === "running") return "bg-violet-500 shadow-[0_0_0_4px_rgba(139,92,246,0.16)]";
  if (status === "failed") return "bg-red-500";
  if (status === "canceled") return "bg-amber-500";
  return "bg-slate-700";
}

function evidenceTextClass(tone: EvidenceTone = "default") {
  if (tone === "accent") return "text-violet-300";
  if (tone === "success") return "text-emerald-300";
  if (tone === "warning") return "text-amber-300";
  if (tone === "danger") return "text-red-300";
  return "text-slate-200";
}
```

Remove the old `MessageRow` function.

- [ ] **Step 4: Run component tests**

Run:

```bash
cd frontend
npm run test -- components/__tests__/AgentStreamView.test.tsx
```

Expected: all `AgentStreamView` tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/AgentStreamView.tsx frontend/components/__tests__/AgentStreamView.test.tsx
git commit -m "feat: render agent progress timeline"
```

---

### Task 4: Polish Integration and Edge Cases

**Files:**
- Modify: `frontend/lib/agentProgress.ts`
- Modify: `frontend/lib/__tests__/agentProgress.test.ts`
- Modify: `frontend/components/AgentStreamView.tsx`

- [ ] **Step 1: Add tests for failed, canceled, and disconnected behavior**

Append to `frontend/lib/__tests__/agentProgress.test.ts`:

```ts
  it("marks the active phase failed from failed phase events", () => {
    const progress = buildAgentProgress([
      { type: "phase", phase: "predicting_direction", tool: "run_tabpfn" },
      { type: "phase", phase: "failed", tool: null },
    ]);

    expect(progress.phases.find((phase) => phase.id === "predicting_direction")?.status).toBe("failed");
  });

  it("marks the active phase canceled from canceled phase events", () => {
    const progress = buildAgentProgress([
      { type: "phase", phase: "evaluating_features", tool: "evaluate_features" },
      { type: "phase", phase: "canceled", tool: null },
    ]);

    expect(progress.phases.find((phase) => phase.id === "evaluating_features")?.status).toBe("canceled");
  });
```

Update `frontend/components/__tests__/AgentStreamView.test.tsx` connection-lost test so it uses a structured message:

```ts
  it("shows connection lost banner when disconnected with messages", () => {
    const messages: StreamMessage[] = [
      { type: "phase", phase: "fetching_market_data", tool: "fetch_data" },
    ];
    render(<AgentStreamView messages={messages} connected={false} isRunning={true} />);
    expect(screen.getByText(/connection lost/i)).toBeInTheDocument();
    expect(screen.getByText("Preparing data")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
cd frontend
npm run test -- lib/__tests__/agentProgress.test.ts components/__tests__/AgentStreamView.test.tsx
```

Expected: pass.

- [ ] **Step 3: Manually inspect the rendered layout**

Start the frontend:

```bash
cd frontend
npm run dev
```

Open the app and run a quick analysis. Verify:

- the left panel title reads `Agent Progress`
- phases advance as the run proceeds
- TabPFN progress appears when estimate/progress events arrive
- raw events are collapsed by default
- expanding raw events shows compact monospace event lines

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/agentProgress.ts frontend/lib/__tests__/agentProgress.test.ts frontend/components/AgentStreamView.tsx frontend/components/__tests__/AgentStreamView.test.tsx
git commit -m "fix: handle agent progress edge states"
```

---

### Task 5: Final Verification

**Files:**
- Verify all frontend changes.

- [ ] **Step 1: Run frontend lint**

```bash
cd frontend
npm run lint
```

Expected: `eslint . --max-warnings=0` exits 0.

- [ ] **Step 2: Run frontend type-check**

```bash
cd frontend
npm run type-check
```

Expected: `tsc --noEmit` exits 0.

- [ ] **Step 3: Run frontend tests**

```bash
cd frontend
npm run test
```

Expected: all tests pass.

- [ ] **Step 4: Run frontend build**

```bash
cd frontend
npm run build
```

Expected: build exits 0. If Turbopack fails locally with `Operation not permitted` when binding to a port, rerun outside the sandbox; do not change code for that local sandbox failure.

- [ ] **Step 5: Push branch**

```bash
git push
```

Expected: branch pushes successfully and PR checks start.

- [ ] **Step 6: Watch PR checks**

```bash
gh pr checks --watch
```

Expected: frontend lint/test/build and docker checks pass.
