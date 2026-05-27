# Agent Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the left-panel agent timeline with a collapsible drawer inside the right tab panel, removing the two-column layout.

**Architecture:** `AgentStream` becomes a headless component (renders null, keeps WebSocket + done-effect). Its `messages` array is synced to Zustand so `AgentDrawer` can read them without opening a second socket. `ResultsTabs` gains a toggle button in its tab bar and mounts `AgentDrawer` between the bar and tab content.

**Tech Stack:** React 19, Next.js 15 App Router, Zustand v5, Vitest + @testing-library/react, TypeScript, Tailwind CSS v4.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `frontend/lib/store.ts` | Modify | Add `messages: StreamMessage[]` + `setMessages` |
| `frontend/components/AgentStream.tsx` | Modify | Sync messages to store; return null |
| `frontend/components/AgentDrawer.tsx` | Create | Collapsible drawer body (phases + latest thought) |
| `frontend/components/__tests__/AgentDrawer.test.tsx` | Create | Unit tests for the drawer |
| `frontend/components/ResultsTabs.tsx` | Modify | Add toggle button + mount `AgentDrawer` |
| `frontend/components/__tests__/ResultsTabs.test.tsx` | Modify | Add drawer visibility tests |
| `frontend/app/page.tsx` | Modify | Single-column layout; `AgentStream` headless |
| `frontend/components/AgentProgressTimeline.tsx` | Delete | No longer rendered |
| `frontend/components/__tests__/AgentProgressTimeline.test.tsx` | Delete | References deleted component |

---

### Task 1: Store — add messages state

**Files:**
- Modify: `frontend/lib/store.ts`

- [ ] **Step 1: Add `messages` and `setMessages` to the store**

Replace the full content of `frontend/lib/store.ts` with:

```ts
import { create } from "zustand";
import type { AnalysisResult } from "./api";
import type { StreamMessage } from "./websocket";

type StoreStatus = "idle" | "running" | "completed" | "failed";

type RunStore = {
  runId: string | null;
  status: StoreStatus;
  result: AnalysisResult | null;
  error: string | null;
  messages: StreamMessage[];
  setRun: (runId: string) => void;
  setResult: (result: AnalysisResult) => void;
  setStatus: (status: StoreStatus) => void;
  setError: (error: string) => void;
  setMessages: (msgs: StreamMessage[]) => void;
  clearRun: () => void;
};

export const useRunStore = create<RunStore>((set) => ({
  runId: null,
  status: "idle",
  result: null,
  error: null,
  messages: [],
  setRun: (runId) => set({ runId, status: "running", result: null, error: null }),
  setResult: (result) => set({ result, status: "completed" }),
  setStatus: (status) => set({ status }),
  setError: (error) => set({ error, status: "failed" }),
  setMessages: (messages) => set({ messages }),
  clearRun: () => set({ runId: null, status: "idle", result: null, error: null, messages: [] }),
}));
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Verify existing tests still pass**

```bash
cd frontend && npm run test -- --run
```

Expected: all existing tests pass (`useRunStore.setState` merges, so tests that don't set `messages` keep the default `[]`).

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/store.ts
git commit -m "feat: add messages to run store"
```

---

### Task 2: AgentStream — headless, sync messages to store

**Files:**
- Modify: `frontend/components/AgentStream.tsx`

- [ ] **Step 1: Rewrite `AgentStream` to return null and sync messages**

Replace the full content of `frontend/components/AgentStream.tsx` with:

```tsx
"use client";

import { useEffect } from "react";
import { useRunStore } from "@/lib/store";
import { useRunStream } from "@/lib/websocket";
import { api } from "@/lib/api";
import type { AnalysisResult } from "@/lib/api";

export function AgentStream() {
  const { runId, status, setResult, setStatus, setMessages } = useRunStore();
  const { messages } = useRunStream(runId);

  useEffect(() => {
    setMessages(messages);
  }, [messages, setMessages]);

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

  return null;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Run tests**

```bash
cd frontend && npm run test -- --run
```

Expected: all pass. (Tests that test `AgentProgressTimeline` directly still pass since the component still exists at this point.)

- [ ] **Step 4: Commit**

```bash
git add frontend/components/AgentStream.tsx
git commit -m "refactor: make AgentStream headless, sync messages to store"
```

---

### Task 3: AgentDrawer component

**Files:**
- Create: `frontend/components/AgentDrawer.tsx`
- Create: `frontend/components/__tests__/AgentDrawer.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/components/__tests__/AgentDrawer.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { AgentDrawer } from "../AgentDrawer";
import { useRunStore } from "@/lib/store";
import type { StreamMessage } from "@/lib/websocket";

beforeEach(() => {
  useRunStore.setState({ messages: [], status: "idle", result: null, error: null, runId: null });
});

describe("AgentDrawer", () => {
  it("has max-h-0 class when isOpen is false", () => {
    const { container } = render(<AgentDrawer isOpen={false} />);
    expect(container.firstChild).toHaveClass("max-h-0");
  });

  it("has max-h-14 class when isOpen is true", () => {
    const { container } = render(<AgentDrawer isOpen={true} />);
    expect(container.firstChild).toHaveClass("max-h-14");
  });

  it("renders 9 phase dots (one per phase)", () => {
    const { container } = render(<AgentDrawer isOpen={true} />);
    const phaseDots = container.querySelectorAll("[data-phase-dot]");
    expect(phaseDots.length).toBe(9);
  });

  it("shows latest thought from running phase", () => {
    const messages: StreamMessage[] = [
      { type: "phase", phase: "predicting_regime" },
      { type: "thought", content: "Classifying regime with TabPFN…" },
    ];
    useRunStore.setState({ messages, status: "running" });
    render(<AgentDrawer isOpen={true} />);
    expect(screen.getByText("Classifying regime with TabPFN…")).toBeTruthy();
  });

  it("shows no thought text when messages is empty", () => {
    useRunStore.setState({ messages: [], status: "running" });
    const { container } = render(<AgentDrawer isOpen={true} />);
    expect(container.querySelector("p")).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm run test -- --run AgentDrawer
```

Expected: FAIL with "Cannot find module '../AgentDrawer'".

- [ ] **Step 3: Create `AgentDrawer.tsx`**

Create `frontend/components/AgentDrawer.tsx`:

```tsx
"use client";

import { useRunStore } from "@/lib/store";
import { buildAgentProgress } from "@/lib/agentProgress";
import type { AgentPhase } from "@/lib/agentProgress";

interface Props {
  isOpen: boolean;
}

export function AgentDrawer({ isOpen }: Props) {
  const { messages } = useRunStore();
  const progress = buildAgentProgress(messages);

  const runningPhase = progress.phases.find((p) => p.status === "running");
  const phasesWithNotes = progress.phases.filter((p) => p.notes.length > 0);
  const latestThought =
    runningPhase?.notes[runningPhase.notes.length - 1] ??
    phasesWithNotes[phasesWithNotes.length - 1]?.notes.at(-1);

  return (
    <div
      className={`overflow-hidden transition-all duration-200 border-b border-slate-800 bg-[#0d0d18] ${
        isOpen ? "max-h-14 opacity-100" : "max-h-0 opacity-0"
      }`}
    >
      <div className="flex h-14 items-center gap-3 px-3">
        <div className="flex items-center gap-1 shrink-0">
          {progress.phases.map((phase, i) => (
            <PhaseDot
              key={phase.id}
              phase={phase}
              isLast={i === progress.phases.length - 1}
            />
          ))}
        </div>
        {latestThought && (
          <p className="border-l border-slate-700 pl-3 text-xs italic text-slate-500 truncate min-w-0">
            {latestThought}
          </p>
        )}
      </div>
    </div>
  );
}

function PhaseDot({
  phase,
  isLast,
}: {
  phase: AgentPhase;
  isLast: boolean;
}) {
  const dotClass =
    phase.status === "done"
      ? "bg-emerald-600"
      : phase.status === "running"
      ? "bg-violet-700 animate-pulse ring-1 ring-violet-900"
      : phase.status === "failed" || phase.status === "canceled"
      ? "bg-red-600"
      : "border border-slate-700 bg-transparent";

  const lineClass =
    phase.status === "done"
      ? "bg-emerald-800"
      : phase.status === "running"
      ? "bg-violet-900"
      : "bg-slate-800";

  return (
    <div className="flex items-center gap-1">
      <div
        data-phase-dot
        title={phase.title}
        className={`w-2 h-2 rounded-full shrink-0 ${dotClass}`}
      />
      {!isLast && <div className={`w-3 h-px ${lineClass}`} />}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run AgentDrawer
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/AgentDrawer.tsx frontend/components/__tests__/AgentDrawer.test.tsx
git commit -m "feat: add AgentDrawer component"
```

---

### Task 4: ResultsTabs — integrate drawer and toggle button

**Files:**
- Modify: `frontend/components/ResultsTabs.tsx`
- Modify: `frontend/components/__tests__/ResultsTabs.test.tsx`

- [ ] **Step 1: Add drawer tests to `ResultsTabs.test.tsx`**

Append these tests to the existing `describe("ResultsTabs", ...)` block in `frontend/components/__tests__/ResultsTabs.test.tsx`. Also add the store import at the top.

Add import after the existing imports:

```tsx
import { useRunStore } from "@/lib/store";
```

Add `beforeEach` before the existing tests (or ensure the store is reset):

```tsx
import { beforeEach } from "vitest";

beforeEach(() => {
  useRunStore.setState({ status: "idle", messages: [], result: null, error: null, runId: null });
});
```

Add these tests inside `describe("ResultsTabs", ...)`:

```tsx
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

  it("toggles drawer label on Agent button click", () => {
    useRunStore.setState({ status: "running", messages: [] });
    render(<ResultsTabs result={result} />);
    const btn = screen.getByRole("button", { name: /expand agent drawer/i });
    fireEvent.click(btn);
    expect(screen.getByRole("button", { name: /collapse agent drawer/i })).toBeTruthy();
  });
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
cd frontend && npm run test -- --run ResultsTabs
```

Expected: the 3 new tests fail (Agent button does not exist yet).

- [ ] **Step 3: Update `ResultsTabs.tsx`**

Replace the full content of `frontend/components/ResultsTabs.tsx` with:

```tsx
"use client";

import { useState, useEffect } from "react";
import type { AnalysisResult } from "../lib/api";
import { useRunStore } from "@/lib/store";
import { AgentDrawer } from "./AgentDrawer";
import { OverviewTab } from "./tabs/OverviewTab";
import { FeaturesTab } from "./tabs/FeaturesTab";
import { DriftTab } from "./tabs/DriftTab";
import { BacktestTab } from "./tabs/BacktestTab";
import { SummaryTab } from "./tabs/SummaryTab";

type TabId = "overview" | "features" | "drift" | "backtest" | "summary";

const TABS: Array<{ id: TabId; label: string; icon: string }> = [
  { id: "overview", label: "Overview", icon: "▦" },
  { id: "features", label: "Features", icon: "≡" },
  { id: "drift", label: "Drift", icon: "⊘" },
  { id: "backtest", label: "Backtest", icon: "↗" },
  { id: "summary", label: "Summary", icon: "✎" },
];

type Props = { result: AnalysisResult };

export function ResultsTabs({ result }: Props) {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { status } = useRunStore();

  useEffect(() => {
    if (status === "running") setDrawerOpen(true);
    if (status === "completed" || status === "failed") setDrawerOpen(false);
  }, [status]);

  function renderTab() {
    switch (activeTab) {
      case "overview":
        return <OverviewTab result={result} />;
      case "features":
        return <FeaturesTab features={result.feature_importance} />;
      case "drift":
        return <DriftTab drift={result.drift} />;
      case "backtest":
        return <BacktestTab backtest={result.backtest} />;
      case "summary":
        return <SummaryTab summary={result.summary} />;
    }
  }

  return (
    <div className="flex h-full">
      {/* Icon sidebar */}
      <div className="w-10 flex flex-col items-center py-3 gap-1 border-r border-slate-800 bg-[#07070f] shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            aria-label={`${tab.label} sidebar`}
            title={tab.label}
            onClick={() => setActiveTab(tab.id)}
            className={`w-8 h-8 flex items-center justify-center rounded text-sm transition-colors ${
              activeTab === tab.id
                ? "bg-violet-950 text-violet-400"
                : "text-slate-600 hover:text-slate-400 hover:bg-slate-800"
            }`}
          >
            {tab.icon}
          </button>
        ))}
      </div>

      {/* Main content */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Tab bar */}
        <div className="flex border-b border-slate-800 bg-[#07070f] shrink-0 items-center">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              aria-label={`${tab.icon} ${tab.label}`}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-2 text-xs font-mono transition-colors border-b-2 ${
                activeTab === tab.id
                  ? "border-violet-500 text-violet-400"
                  : "border-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
          {status !== "idle" && (
            <button
              aria-label={drawerOpen ? "Collapse agent drawer" : "Expand agent drawer"}
              onClick={() => setDrawerOpen((v) => !v)}
              className={`ml-auto mr-2 px-2 py-1 text-xs font-mono rounded border ${
                status === "running"
                  ? "border-violet-800 text-violet-400 animate-pulse"
                  : "border-slate-700 text-slate-500"
              }`}
            >
              ◎ Agent {drawerOpen ? "▴" : "▾"}
            </button>
          )}
        </div>

        {/* Agent drawer */}
        <AgentDrawer isOpen={drawerOpen} />

        {/* Tab content */}
        <div className="flex-1 overflow-hidden bg-[#07070f]">{renderTab()}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run all ResultsTabs tests**

```bash
cd frontend && npm run test -- --run ResultsTabs
```

Expected: all 9 tests pass (6 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ResultsTabs.tsx frontend/components/__tests__/ResultsTabs.test.tsx
git commit -m "feat: integrate AgentDrawer into ResultsTabs"
```

---

### Task 5: page.tsx — single-column layout

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Rewrite `page.tsx`**

Replace the full content of `frontend/app/page.tsx` with:

```tsx
import { TopBar } from "@/components/TopBar";
import { AgentStream } from "@/components/AgentStream";
import { ResultsPanel } from "@/components/ResultsPanel";

export default function Home() {
  return (
    <div className="flex flex-col h-screen bg-white dark:bg-[#0f0f1a]">
      <TopBar />
      <AgentStream />
      <main className="flex flex-1 overflow-hidden">
        <section className="flex-1 overflow-hidden">
          <ResultsPanel />
        </section>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Run full test suite**

```bash
cd frontend && npm run test -- --run
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "refactor: remove left panel, single-column layout"
```

---

### Task 6: Cleanup — delete AgentProgressTimeline

**Files:**
- Delete: `frontend/components/AgentProgressTimeline.tsx`
- Delete: `frontend/components/__tests__/AgentProgressTimeline.test.tsx`

- [ ] **Step 1: Delete both files**

```bash
rm frontend/components/AgentProgressTimeline.tsx
rm frontend/components/__tests__/AgentProgressTimeline.test.tsx
```

- [ ] **Step 2: Verify nothing imports `AgentProgressTimeline`**

```bash
grep -r "AgentProgressTimeline" frontend/
```

Expected: no output (zero matches).

- [ ] **Step 3: Run full test suite**

```bash
cd frontend && npm run test -- --run
```

Expected: all tests pass.

- [ ] **Step 4: Lint check**

```bash
cd frontend && npm run lint
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: delete AgentProgressTimeline (replaced by AgentDrawer)"
```

---

## Done

At this point:
- Left panel is gone; `ResultsPanel` fills the full viewport width
- Agent progress is embedded as a collapsible drawer in the tab panel
- Drawer auto-opens on run start, auto-closes on completion
- All tests pass, no dead imports
