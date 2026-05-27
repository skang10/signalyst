# Agent Progress Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `AgentStreamView` with `AgentProgressTimeline` — a vertical timeline that shows all 9 named phases upfront, highlights the active phase with a pulsing icon and live thought, and renders completed phases with evidence chips.

**Architecture:** `AgentStream.tsx` (container) calls `buildAgentProgress(messages)` and passes `AgentProgressState` down as a prop. `AgentProgressTimeline.tsx` is a pure presentational component — no hooks, no message parsing. Tests build state via `buildAgentProgress()` directly, decoupled from raw WebSocket message format.

**Tech Stack:** Next.js 15, TypeScript, Tailwind CSS v4, Vitest + @testing-library/react, Zustand (unchanged)

---

## File map

| Action | File | Role |
|--------|------|------|
| Create | `frontend/components/AgentProgressTimeline.tsx` | New presentational timeline component |
| Create | `frontend/components/__tests__/AgentProgressTimeline.test.tsx` | Tests for the new component |
| Modify | `frontend/components/AgentStream.tsx` | Call `buildAgentProgress`, pass state to timeline |
| Delete | `frontend/components/AgentStreamView.tsx` | Replaced by AgentProgressTimeline |
| Delete | `frontend/components/__tests__/AgentStreamView.test.tsx` | Replaced by AgentProgressTimeline tests |

`lib/agentProgress.ts` and `lib/websocket.ts` are **not changed**.

---

## Task 1: Write failing tests

**Files:**
- Create: `frontend/components/__tests__/AgentProgressTimeline.test.tsx`

- [ ] **Step 1: Create the test file**

Create `frontend/components/__tests__/AgentProgressTimeline.test.tsx`:

```tsx
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd frontend && npm run test -- components/__tests__/AgentProgressTimeline.test.tsx
```

Expected: FAIL — `Cannot find module '../AgentProgressTimeline'`

---

## Task 2: Implement AgentProgressTimeline

**Files:**
- Create: `frontend/components/AgentProgressTimeline.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/components/AgentProgressTimeline.tsx`:

```tsx
import type { AgentProgressState, AgentPhase, EvidenceTone } from "@/lib/agentProgress";

interface Props {
  state: AgentProgressState;
  isRunning: boolean;
  connected: boolean;
}

const TONE_CHIP: Record<EvidenceTone, string> = {
  default: "bg-slate-800 text-slate-300",
  success: "bg-emerald-950 text-emerald-400",
  accent: "bg-violet-950 text-violet-400",
  warning: "bg-amber-950 text-amber-400",
  danger: "bg-red-950 text-red-400",
};

export function AgentProgressTimeline({ state, isRunning, connected }: Props) {
  const allWaiting = state.phases.every((p) => p.status === "waiting");

  if (!isRunning && allWaiting) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <p className="text-slate-500 dark:text-slate-400 text-sm text-center">
          Run an analysis to see the agent&apos;s reasoning.
        </p>
      </div>
    );
  }

  if (isRunning && !connected && allWaiting) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <p className="text-slate-400 dark:text-slate-500 text-xs animate-pulse">
          Connecting…
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto p-4">
      {state.phases.map((phase, i) => (
        <PhaseRow
          key={phase.id}
          phase={phase}
          isLast={i === state.phases.length - 1}
        />
      ))}
    </div>
  );
}

function PhaseRow({ phase, isLast }: { phase: AgentPhase; isLast: boolean }) {
  const isWaiting = phase.status === "waiting";
  const latestNote = phase.notes[phase.notes.length - 1];

  return (
    <div className={`grid grid-cols-[22px_1fr] gap-3 ${isWaiting ? "opacity-[0.35]" : ""}`}>
      <div className="flex flex-col items-center">
        <PhaseIcon status={phase.status} />
        {!isLast && (
          <div
            className={`w-0.5 flex-1 min-h-6 my-1 ${
              phase.status === "done"
                ? "bg-slate-700"
                : phase.status === "running"
                ? "bg-slate-800"
                : "bg-slate-900"
            }`}
          />
        )}
      </div>
      <div className="pb-4 min-w-0">
        <p
          className={`text-sm font-semibold ${
            phase.status === "running"
              ? "text-violet-400"
              : phase.status === "failed" || phase.status === "canceled"
              ? "text-red-400"
              : "text-slate-400"
          }`}
        >
          {phase.title}
        </p>

        {phase.status === "running" && latestNote && (
          <p className="mt-1 text-xs italic text-slate-500">{latestNote}</p>
        )}

        {phase.status === "running" && phase.progress && (
          <ProgressBar progress={phase.progress} />
        )}

        {phase.status === "done" && phase.evidence.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {phase.evidence.map((ev) => (
              <span
                key={`${ev.label}-${ev.value}`}
                className={`text-xs px-2 py-0.5 rounded-full font-medium ${TONE_CHIP[ev.tone ?? "default"]}`}
              >
                {ev.label}: {ev.value}
              </span>
            ))}
          </div>
        )}

        {phase.status === "done" && phase.notes.length > 0 && phase.evidence.length === 0 && (
          <p className="mt-1 text-xs text-slate-500">{phase.notes[phase.notes.length - 1]}</p>
        )}
      </div>
    </div>
  );
}

function PhaseIcon({ status }: { status: AgentPhase["status"] }) {
  if (status === "done") {
    return (
      <div className="h-[22px] w-[22px] rounded-full bg-emerald-600 flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0">
        ✓
      </div>
    );
  }
  if (status === "running") {
    return (
      <div className="h-[22px] w-[22px] rounded-full bg-violet-700 flex items-center justify-center text-white text-[11px] flex-shrink-0 animate-pulse ring-2 ring-violet-900 ring-offset-1 ring-offset-[#0f0f1a]">
        ⋯
      </div>
    );
  }
  if (status === "failed" || status === "canceled") {
    return (
      <div className="h-[22px] w-[22px] rounded-full bg-red-600 flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0">
        ✕
      </div>
    );
  }
  return (
    <div className="h-[22px] w-[22px] rounded-full border-2 border-slate-700 flex-shrink-0" />
  );
}

function ProgressBar({
  progress,
}: {
  progress: NonNullable<AgentPhase["progress"]>;
}) {
  const pct = progress.unknownTotal
    ? null
    : Math.min(100, (progress.completed / Math.max(progress.total, 1)) * 100);

  return (
    <div className="mt-2">
      <div className="h-1 w-full rounded-full bg-slate-800 overflow-hidden">
        {pct !== null ? (
          <div
            className="h-full bg-violet-500 rounded-full transition-[width]"
            style={{ width: `${pct}%` }}
          />
        ) : (
          <div className="h-full w-1/3 bg-violet-500 rounded-full animate-pulse" />
        )}
      </div>
      <p className="mt-1 text-[11px] text-slate-600 text-right">
        {progress.unknownTotal
          ? `${progress.completed} calls`
          : `${progress.completed} / ${progress.total}`}
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Run tests — verify they pass**

```bash
cd frontend && npm run test -- components/__tests__/AgentProgressTimeline.test.tsx
```

Expected: 9 tests pass.

- [ ] **Step 3: Type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/AgentProgressTimeline.tsx frontend/components/__tests__/AgentProgressTimeline.test.tsx
git commit -m "feat: add AgentProgressTimeline component with tests"
```

---

## Task 3: Wire up AgentStream and remove old files

**Files:**
- Modify: `frontend/components/AgentStream.tsx`
- Delete: `frontend/components/AgentStreamView.tsx`
- Delete: `frontend/components/__tests__/AgentStreamView.test.tsx`

- [ ] **Step 1: Update AgentStream.tsx**

Replace the entire contents of `frontend/components/AgentStream.tsx` with:

```tsx
"use client";

import { useEffect } from "react";
import { useRunStore } from "@/lib/store";
import { useRunStream } from "@/lib/websocket";
import { api } from "@/lib/api";
import { buildAgentProgress } from "@/lib/agentProgress";
import { AgentProgressTimeline } from "./AgentProgressTimeline";
import type { AnalysisResult } from "@/lib/api";

export function AgentStream() {
  const { runId, status, setResult, setStatus } = useRunStore();
  const { messages, connected } = useRunStream(runId);

  useEffect(() => {
    const last = messages[messages.length - 1];
    if (last?.type !== "done" || !runId || status === "completed") return;

    api
      .getRun(runId)
      .then((runResult) => {
        if (runResult.result) {
          setResult(runResult.result as AnalysisResult);
        } else {
          setStatus("failed");
        }
      })
      .catch(() => setStatus("failed"));
  }, [messages, runId, status, setResult, setStatus]);

  const progress = buildAgentProgress(messages);

  return (
    <AgentProgressTimeline
      state={progress}
      isRunning={status === "running"}
      connected={connected}
    />
  );
}
```

- [ ] **Step 2: Delete old files**

```bash
rm frontend/components/AgentStreamView.tsx
rm frontend/components/__tests__/AgentStreamView.test.tsx
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/AgentStream.tsx
git add -u frontend/components/AgentStreamView.tsx frontend/components/__tests__/AgentStreamView.test.tsx
git commit -m "feat: wire AgentProgressTimeline into AgentStream, remove AgentStreamView"
```

---

## Task 4: Full suite verification

- [ ] **Step 1: Run the full frontend test suite**

```bash
cd frontend && npm run test
```

Expected: all tests pass. You should see passing suites for:
- `lib/__tests__/api.test.ts`
- `lib/__tests__/websocket.test.ts`
- `lib/__tests__/agentProgress.test.ts` (if it exists)
- `components/__tests__/AgentProgressTimeline.test.tsx`
- `components/__tests__/RegimeCard.test.tsx`
- `components/__tests__/DirectionCard.test.tsx`
- `components/__tests__/ResultsPanel.test.tsx`

No `AgentStreamView` suite should appear.

- [ ] **Step 2: Lint and type-check**

```bash
cd frontend && npm run type-check && npm run lint
```

Expected: no errors, no warnings.

- [ ] **Step 3: Smoke test in browser**

Start the dev server:

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000`. Verify:
- Dark background renders, TopBar visible
- Left pane shows "Run an analysis to see the agent's reasoning."
- If connected to a running backend: click Run, left pane transitions to "Connecting…" then the 9-phase timeline appears with the active phase highlighted in violet

- [ ] **Step 4: Final commit (if any cleanup needed)**

```bash
git add -A
git commit -m "chore: cleanup after AgentProgressTimeline migration"
```
