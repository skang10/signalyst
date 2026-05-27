# Run / Resume UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the TopBar's single Run/Cancel toggle with a three-state UX — idle shows Run, running shows Cancel, stopped (canceled/failed/completed) shows Resume + New Run — and preserve run output across cancellations.

**Architecture:** Two-file change. `store.ts` gains a `"canceled"` status, a `lastRunParams` field, and a `setCanceled()` action; `setError()` is updated to keep sessionStorage (matching canceled behavior). `TopBar.tsx` adopts the new store actions and renders the correct buttons per status. No backend changes.

**Tech Stack:** TypeScript, Zustand, React, Vitest, `@testing-library/react`, `fireEvent`

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `frontend/lib/store.ts` | Modify | Add `"canceled"` to `StoreStatus`; add `LastRunParams` type and `lastRunParams` field; add `setCanceled()`; update `setRun()` signature to accept params; update `setError()` to keep sessionStorage; update `clearRun()` to also clear `lastRunParams` |
| `frontend/lib/__tests__/store.test.ts` | Modify | Update `setRun` call sites to pass params; update `setError` assertion (now keeps sessionStorage); add tests for `setCanceled`, `lastRunParams`, `setError` keeping runId |
| `frontend/components/TopBar.tsx` | Modify | Swap `clearRun` for `setCanceled`/`setStatus`; update `handleRun` to pass params; add `handleResume`; add status badge; update button render logic |
| `frontend/components/__tests__/TopBar.test.tsx` | Create | Cover all three button states and all three handlers |

---

## Task 1: Update `store.ts`

**Files:**
- Modify: `frontend/lib/store.ts`
- Test: `frontend/lib/__tests__/store.test.ts`

- [ ] **Step 1.1: Add new tests and update existing ones**

Open `frontend/lib/__tests__/store.test.ts`. Make these changes — the new tests will fail, and the updated assertions will fail once the store changes land:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { useRunStore } from "../store";
import type { StreamMessage } from "../websocket";

const mockMsg: StreamMessage = { type: "thought", content: "thinking..." };

// Add lastRunParams: null to the reset
beforeEach(() => {
  sessionStorage.clear();
  useRunStore.setState({
    runId: null,
    status: "idle",
    result: null,
    error: null,
    messages: [],
    lastRunParams: null,
  });
});

const params = {
  date_range_start: "2023-01-01",
  date_range_end: "2023-06-30",
  analysis_mode: "quick" as const,
};

describe("useRunStore — sessionStorage persistence", () => {
  // Update: setRun now takes a second argument
  it("setRun writes runId to sessionStorage and clears messages", () => {
    useRunStore.getState().setRun("run-123", params);
    expect(sessionStorage.getItem("activeRunId")).toBe("run-123");
    expect(sessionStorage.getItem("activeRunMessages")).toBeNull();
  });

  // Update: setRun now takes a second argument
  it("setRun sets status to running with empty messages", () => {
    useRunStore.getState().setRun("run-123", params);
    const { status, messages } = useRunStore.getState();
    expect(status).toBe("running");
    expect(messages).toHaveLength(0);
  });

  it("setMessages persists messages to sessionStorage", () => {
    useRunStore.getState().setMessages([mockMsg]);
    const raw = sessionStorage.getItem("activeRunMessages");
    expect(JSON.parse(raw!)).toEqual([mockMsg]);
  });

  it("setResult clears sessionStorage and sets status to completed", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setMessages([mockMsg]);
    useRunStore
      .getState()
      .setResult({
        regime: null,
        direction: null,
        drift: null,
        feature_importance: null,
        backtest: null,
        summary: "",
        usage: { input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0 },
        data_manifest: {},
      });
    expect(sessionStorage.getItem("activeRunId")).toBeNull();
    expect(sessionStorage.getItem("activeRunMessages")).toBeNull();
    expect(useRunStore.getState().status).toBe("completed");
  });

  // Updated: setError now KEEPS sessionStorage (runId and messages stay for Resume)
  it("setError keeps sessionStorage and sets status to failed", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setMessages([mockMsg]);
    useRunStore.getState().setError("something went wrong");
    expect(sessionStorage.getItem("activeRunId")).toBe("run-123");
    expect(JSON.parse(sessionStorage.getItem("activeRunMessages")!)).toEqual([mockMsg]);
    expect(useRunStore.getState().status).toBe("failed");
    expect(useRunStore.getState().runId).toBe("run-123");
  });

  it("clearRun removes all sessionStorage entries and resets state", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setMessages([mockMsg]);
    useRunStore.getState().clearRun();
    expect(sessionStorage.getItem("activeRunId")).toBeNull();
    expect(sessionStorage.getItem("activeRunMessages")).toBeNull();
    const { runId, status, result, error, messages, lastRunParams } = useRunStore.getState();
    expect(runId).toBeNull();
    expect(status).toBe("idle");
    expect(result).toBeNull();
    expect(error).toBeNull();
    expect(messages).toHaveLength(0);
    expect(lastRunParams).toBeNull();
  });

  it("sessionStorage retains runId and messages across store state resets", () => {
    useRunStore.getState().setRun("run-456", params);
    useRunStore.getState().setMessages([mockMsg]);
    expect(sessionStorage.getItem("activeRunId")).toBe("run-456");
    expect(JSON.parse(sessionStorage.getItem("activeRunMessages")!)).toEqual([mockMsg]);
  });
});

// NEW tests
describe("useRunStore — canceled status", () => {
  it("setRun saves lastRunParams", () => {
    useRunStore.getState().setRun("run-123", params);
    expect(useRunStore.getState().lastRunParams).toEqual(params);
  });

  it("setCanceled sets status to canceled without clearing sessionStorage", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setMessages([mockMsg]);
    useRunStore.getState().setCanceled();
    expect(useRunStore.getState().status).toBe("canceled");
    expect(useRunStore.getState().runId).toBe("run-123");
    expect(sessionStorage.getItem("activeRunId")).toBe("run-123");
    expect(JSON.parse(sessionStorage.getItem("activeRunMessages")!)).toEqual([mockMsg]);
  });

  it("setCanceled does not clear lastRunParams", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().setCanceled();
    expect(useRunStore.getState().lastRunParams).toEqual(params);
  });

  it("clearRun clears lastRunParams", () => {
    useRunStore.getState().setRun("run-123", params);
    useRunStore.getState().clearRun();
    expect(useRunStore.getState().lastRunParams).toBeNull();
  });
});
```

- [ ] **Step 1.2: Run the tests — verify they fail**

```bash
cd frontend && npm run test -- lib/__tests__/store.test.ts
```

Expected: several failures — `setCanceled is not a function`, type errors on `setRun` arity, `setError` sessionStorage assertions wrong.

- [ ] **Step 1.3: Rewrite `store.ts`**

Replace the full contents of `frontend/lib/store.ts`:

```ts
import { create } from "zustand";
import type { AnalysisResult } from "./api";
import type { StreamMessage } from "./websocket";

type StoreStatus = "idle" | "running" | "completed" | "failed" | "canceled";

type LastRunParams = {
  date_range_start: string;
  date_range_end: string;
  analysis_mode: "quick" | "full";
};

type RunStore = {
  runId: string | null;
  status: StoreStatus;
  result: AnalysisResult | null;
  error: string | null;
  messages: StreamMessage[];
  lastRunParams: LastRunParams | null;
  setRun: (runId: string, params: LastRunParams) => void;
  setResult: (result: AnalysisResult) => void;
  setStatus: (status: StoreStatus) => void;
  setError: (error: string) => void;
  setMessages: (msgs: StreamMessage[]) => void;
  setCanceled: () => void;
  clearRun: () => void;
};

const RUN_ID_KEY = "activeRunId";
const MESSAGES_KEY = "activeRunMessages";

function readPersistedRunId(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(RUN_ID_KEY);
}

function readPersistedMessages(): StreamMessage[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(MESSAGES_KEY);
    return raw ? (JSON.parse(raw) as StreamMessage[]) : [];
  } catch {
    return [];
  }
}

function clearPersisted() {
  sessionStorage.removeItem(RUN_ID_KEY);
  sessionStorage.removeItem(MESSAGES_KEY);
}

export const useRunStore = create<RunStore>((set) => ({
  runId: readPersistedRunId(),
  status: "idle",
  result: null,
  error: null,
  messages: readPersistedMessages(),
  lastRunParams: null,
  setRun: (runId, params) => {
    sessionStorage.setItem(RUN_ID_KEY, runId);
    sessionStorage.removeItem(MESSAGES_KEY);
    set({ runId, status: "running", result: null, error: null, messages: [], lastRunParams: params });
  },
  setResult: (result) => {
    clearPersisted();
    set({ result, status: "completed" });
  },
  setStatus: (status) => set({ status }),
  setError: (error) => {
    set({ error, status: "failed" });
  },
  setMessages: (messages) => {
    try {
      sessionStorage.setItem(MESSAGES_KEY, JSON.stringify(messages));
    } catch {
      // sessionStorage full — continue without persisting
    }
    set({ messages });
  },
  setCanceled: () => set({ status: "canceled" }),
  clearRun: () => {
    clearPersisted();
    set({ runId: null, status: "idle", result: null, error: null, messages: [], lastRunParams: null });
  },
}));
```

- [ ] **Step 1.4: Run the tests — verify they pass**

```bash
cd frontend && npm run test -- lib/__tests__/store.test.ts
```

Expected: all tests pass.

- [ ] **Step 1.5: Commit**

```bash
git add frontend/lib/store.ts frontend/lib/__tests__/store.test.ts
git commit -m "feat: add canceled status, lastRunParams, and setCanceled to run store"
```

---

## Task 2: Update `TopBar.tsx` and add `TopBar.test.tsx`

**Files:**
- Modify: `frontend/components/TopBar.tsx`
- Create: `frontend/components/__tests__/TopBar.test.tsx`

- [ ] **Step 2.1: Write `TopBar.test.tsx`**

Create `frontend/components/__tests__/TopBar.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { TopBar } from "../TopBar";
import { useRunStore } from "@/lib/store";

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "dark", setTheme: vi.fn() }),
}));

const mockAnalyze = vi.fn();
const mockCancelRun = vi.fn();
vi.mock("@/lib/api", () => ({
  api: { analyze: mockAnalyze, cancelRun: mockCancelRun },
}));

const params = {
  date_range_start: "2023-01-01",
  date_range_end: "2023-06-30",
  analysis_mode: "quick" as const,
};

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  useRunStore.setState({
    runId: null,
    status: "idle",
    result: null,
    error: null,
    messages: [],
    lastRunParams: null,
  });
});

describe("TopBar — button states", () => {
  it("shows Run button when idle with no runId", () => {
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /run/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /resume/i })).toBeNull();
  });

  it("shows only Cancel when running", () => {
    useRunStore.setState({ status: "running", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /cancel/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /run/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /resume/i })).toBeNull();
  });

  it("shows Resume and New Run when canceled", () => {
    useRunStore.setState({ status: "canceled", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /resume/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new run/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
  });

  it("shows Resume and New Run when failed", () => {
    useRunStore.setState({ status: "failed", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /resume/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new run/i })).toBeTruthy();
  });

  it("shows Resume and New Run when completed", () => {
    useRunStore.setState({ status: "completed", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /resume/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new run/i })).toBeTruthy();
  });

  it("shows Resume and New Run when idle with a runId (page refresh recovery)", () => {
    useRunStore.setState({ status: "idle", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /resume/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new run/i })).toBeTruthy();
  });
});

describe("TopBar — status badge", () => {
  it("shows Canceled badge when status is canceled", () => {
    useRunStore.setState({ status: "canceled", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByText(/canceled/i)).toBeTruthy();
  });

  it("shows Failed badge when status is failed", () => {
    useRunStore.setState({ status: "failed", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByText(/failed/i)).toBeTruthy();
  });

  it("shows Completed badge when status is completed", () => {
    useRunStore.setState({ status: "completed", runId: "run-1" });
    render(<TopBar />);
    expect(screen.getByText(/completed/i)).toBeTruthy();
  });

  it("shows no badge when status is idle with runId (page refresh)", () => {
    useRunStore.setState({ status: "idle", runId: "run-1" });
    render(<TopBar />);
    expect(screen.queryByText(/canceled|failed|completed/i)).toBeNull();
  });
});

describe("TopBar — handlers", () => {
  it("clicking Cancel calls api.cancelRun and sets status to canceled", async () => {
    mockCancelRun.mockResolvedValueOnce({});
    useRunStore.setState({ status: "running", runId: "run-1" });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() => {
      expect(mockCancelRun).toHaveBeenCalledWith("run-1");
      expect(useRunStore.getState().status).toBe("canceled");
      expect(useRunStore.getState().runId).toBe("run-1");
    });
  });

  it("clicking Resume sets status to running", () => {
    useRunStore.setState({ status: "canceled", runId: "run-1" });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /resume/i }));
    expect(useRunStore.getState().status).toBe("running");
  });

  it("clicking New Run calls api.analyze and sets status to running", async () => {
    mockAnalyze.mockResolvedValueOnce({ run_id: "run-2" });
    useRunStore.setState({ status: "canceled", runId: "run-1" });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /new run/i }));
    await waitFor(() => {
      expect(mockAnalyze).toHaveBeenCalledOnce();
      expect(useRunStore.getState().runId).toBe("run-2");
      expect(useRunStore.getState().status).toBe("running");
    });
  });

  it("clicking Run (idle) calls api.analyze and sets status to running", async () => {
    mockAnalyze.mockResolvedValueOnce({ run_id: "run-3" });
    render(<TopBar />);
    // In idle state the only button with "Run" text is "▶ Run" (not "▶ New Run")
    fireEvent.click(screen.getByRole("button", { name: "▶ Run" }));
    await waitFor(() => {
      expect(mockAnalyze).toHaveBeenCalledOnce();
      expect(useRunStore.getState().status).toBe("running");
    });
  });

  it("Cancel still sets status to canceled when api.cancelRun throws", async () => {
    mockCancelRun.mockRejectedValueOnce(new Error("network error"));
    useRunStore.setState({ status: "running", runId: "run-1" });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() => {
      expect(useRunStore.getState().status).toBe("canceled");
    });
  });
});
```

- [ ] **Step 2.2: Run the tests — verify they fail**

```bash
cd frontend && npm run test -- components/__tests__/TopBar.test.tsx
```

Expected: multiple failures — `Resume` button not found, `New Run` button not found, badge text not found, `setCanceled` not called.

- [ ] **Step 2.3: Rewrite `TopBar.tsx`**

Replace the full contents of `frontend/components/TopBar.tsx`:

```tsx
"use client";

import { useState, useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { useRunStore } from "@/lib/store";
import { api } from "@/lib/api";

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  canceled: { label: "Canceled", color: "#f97316" },
  failed: { label: "Failed", color: "#ef4444" },
  completed: { label: "Completed", color: "#22c55e" },
};

export function TopBar() {
  const [start, setStart] = useState("2023-01-01");
  const [end, setEnd] = useState("2023-06-30");
  const [mode, setMode] = useState<"quick" | "full">("quick");
  const [topbarError, setTopbarError] = useState<string | null>(null);
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const { runId, status, setRun, setCanceled, setStatus } = useRunStore();

  const isRunning = status === "running";
  const hasStoppedRun = status !== "running" && runId !== null;
  const badge = STATUS_BADGE[status] ?? null;

  const handleRun = async () => {
    setTopbarError(null);
    try {
      const { run_id } = await api.analyze({
        date_range_start: start,
        date_range_end: end,
        analysis_mode: mode,
      });
      setRun(run_id, { date_range_start: start, date_range_end: end, analysis_mode: mode });
    } catch (e) {
      setTopbarError(e instanceof Error ? e.message : "Failed to start analysis");
    }
  };

  const handleCancel = async () => {
    if (!runId) return;
    try {
      await api.cancelRun(runId);
    } finally {
      setCanceled();
    }
  };

  const handleResume = () => {
    setStatus("running");
  };

  const inputClass =
    "rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 " +
    "text-slate-900 dark:text-slate-100 text-sm px-2 py-1 focus:outline-none focus:ring-1 " +
    "focus:ring-violet-500";

  const pillBase = "text-sm px-3 py-1 rounded-full border transition-colors";
  const pillActive =
    "border-violet-500 bg-violet-50 dark:bg-violet-950 text-violet-700 dark:text-violet-300 font-semibold";
  const pillInactive =
    "border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-400";

  return (
    <header className="sticky top-0 z-10 flex items-center gap-3 px-4 py-2 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-[#0f0f1a] flex-wrap">
      <span className="font-bold text-slate-900 dark:text-white text-base mr-1">
        TemporalAgent
      </span>

      <input
        type="date"
        value={start}
        onChange={(e) => setStart(e.target.value)}
        className={inputClass}
        disabled={isRunning}
      />
      <span className="text-slate-400 text-sm">→</span>
      <input
        type="date"
        value={end}
        onChange={(e) => setEnd(e.target.value)}
        className={inputClass}
        disabled={isRunning}
      />

      <div className="flex gap-1">
        <button
          onClick={() => setMode("quick")}
          className={`${pillBase} ${mode === "quick" ? pillActive : pillInactive}`}
          disabled={isRunning}
        >
          Quick
        </button>
        <button
          onClick={() => setMode("full")}
          className={`${pillBase} ${mode === "full" ? pillActive : pillInactive}`}
          disabled={isRunning}
        >
          Full
        </button>
      </div>

      <div className="flex gap-2 ml-auto items-center">
        {topbarError && (
          <span className="text-xs text-red-500">{topbarError}</span>
        )}

        {isRunning ? (
          <button
            onClick={handleCancel}
            className="text-sm px-4 py-1.5 rounded bg-red-500 hover:bg-red-600 text-white font-semibold transition-colors"
          >
            ✕ Cancel
          </button>
        ) : hasStoppedRun ? (
          <>
            {badge && (
              <span className="text-xs flex items-center gap-1" style={{ color: badge.color }}>
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ background: badge.color }}
                />
                {badge.label}
              </span>
            )}
            <button
              onClick={handleResume}
              className="text-sm px-4 py-1.5 rounded border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 font-semibold hover:border-slate-500 transition-colors"
            >
              ↩ Resume
            </button>
            <button
              onClick={handleRun}
              className="text-sm px-4 py-1.5 rounded bg-violet-600 hover:bg-violet-700 text-white font-semibold transition-colors"
            >
              ▶ New Run
            </button>
          </>
        ) : (
          <button
            onClick={handleRun}
            className="text-sm px-4 py-1.5 rounded bg-violet-600 hover:bg-violet-700 text-white font-semibold transition-colors"
          >
            ▶ Run
          </button>
        )}

        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="p-1.5 rounded border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
          aria-label="Toggle theme"
        >
          {mounted ? (theme === "dark" ? "☀" : "🌙") : "☀"}
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Step 2.4: Run the tests — verify they pass**

```bash
cd frontend && npm run test -- components/__tests__/TopBar.test.tsx
```

Expected: all tests pass.

- [ ] **Step 2.5: Run full test suite**

```bash
cd frontend && npm run test
```

Expected: all tests pass (store tests, TopBar tests, and all pre-existing tests).

- [ ] **Step 2.6: Run type check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 2.7: Commit**

```bash
git add frontend/components/TopBar.tsx frontend/components/__tests__/TopBar.test.tsx
git commit -m "feat: add Resume and New Run buttons to TopBar for stopped runs"
```
