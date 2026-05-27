# Session 6 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core frontend split-pane dashboard — AgentStream (live WebSocket reasoning), RegimeCard, DirectionCard, SummaryPanel, TopBar with dark/light theme toggle — wired to the existing backend API.

**Architecture:** A single `page.tsx` owns the layout (sticky top bar + split pane). Zustand holds `{ runId, status, result }`. TopBar triggers runs; AgentStream consumes the WebSocket stream and fetches the full result on completion; ResultsPanel renders the three result cards from the store. Theme is handled by `next-themes` with Tailwind v4 class-based dark mode.

**Tech Stack:** Next.js 15 App Router, TypeScript, Tailwind v4, Zustand v5, next-themes, Vitest + @testing-library/react

---

## File map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `frontend/app/providers.tsx` | Client-side ThemeProvider wrapper |
| Modify | `frontend/app/layout.tsx` | Wrap body in Providers |
| Modify | `frontend/app/globals.css` | Add Tailwind v4 dark variant |
| Modify | `frontend/app/page.tsx` | Replace placeholder with split-pane shell |
| Modify | `frontend/lib/api.ts` | Add types + `cancelRun` |
| Create | `frontend/lib/store.ts` | Zustand run store |
| Create | `frontend/vitest.setup.ts` | jest-dom setup |
| Modify | `frontend/vitest.config.ts` | Add setupFiles |
| Create | `frontend/components/TopBar.tsx` | Config bar + Run/Cancel/Theme |
| Create | `frontend/components/AgentStreamView.tsx` | Presentational message list |
| Create | `frontend/components/AgentStream.tsx` | Container: WS + done→fetch |
| Create | `frontend/components/RegimeCard.tsx` | Regime label + confidence |
| Create | `frontend/components/DirectionCard.tsx` | Up/down arrow + confidence |
| Create | `frontend/components/SummaryPanel.tsx` | Summary prose card |
| Create | `frontend/components/ResultsPanel.tsx` | Right pane; reads store |
| Create | `frontend/components/__tests__/AgentStreamView.test.tsx` | Stream view tests |
| Create | `frontend/components/__tests__/RegimeCard.test.tsx` | Regime card tests |
| Create | `frontend/components/__tests__/DirectionCard.test.tsx` | Direction card tests |
| Create | `frontend/components/__tests__/ResultsPanel.test.tsx` | Results panel tests |

---

## Task 1: Install dependencies + configure dark mode

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/app/globals.css`
- Create: `frontend/vitest.setup.ts`
- Modify: `frontend/vitest.config.ts`

- [ ] **Step 1: Install packages**

```bash
cd frontend && npm install next-themes @testing-library/jest-dom
```

Expected: packages added to `node_modules/`, `package.json` updated.

- [ ] **Step 2: Add Tailwind v4 class-based dark mode to globals.css**

Replace the entire `frontend/app/globals.css` with:

```css
@import "tailwindcss";
@variant dark (&:where(.dark, .dark *));

body {
  @apply bg-white text-slate-900 dark:bg-[#0f0f1a] dark:text-slate-100;
  font-family: Arial, Helvetica, sans-serif;
}
```

- [ ] **Step 3: Create vitest setup file**

Create `frontend/vitest.setup.ts`:

```ts
import '@testing-library/jest-dom'
```

- [ ] **Step 4: Register setup file in vitest config**

Replace `frontend/vitest.config.ts` with:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
    },
  },
});
```

- [ ] **Step 5: Verify tests still pass**

```bash
cd frontend && npm run test
```

Expected: existing `lib/__tests__/api.test.ts` and `lib/__tests__/websocket.test.ts` pass.

- [ ] **Step 6: Commit**

```bash
cd frontend && git add package.json package-lock.json app/globals.css vitest.setup.ts vitest.config.ts
git commit -m "chore: install next-themes, configure Tailwind dark mode and jest-dom"
```

---

## Task 2: Extend api.ts — types + cancelRun

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add result types and update existing types**

Replace the contents of `frontend/lib/api.ts` with:

```ts
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 30_000;

export type RunStatus = "pending" | "running" | "completed" | "failed" | "canceled";

export type AnalyzeRequest = {
  date_range_start: string;
  date_range_end: string;
  tasks?: string[];
  analysis_mode?: "quick" | "full";
};

export type RegimeResult = {
  regime: string;
  confidence: number;
  entropy: number;
  distribution: Record<string, number>;
};

export type DirectionResult = {
  direction: string;
  confidence: number;
  entropy: number;
  prediction_date: string;
  distribution: Record<string, number>;
};

export type AnalysisResult = {
  regime: RegimeResult | null;
  direction: DirectionResult | null;
  drift: unknown;
  feature_importance: unknown;
  backtest: unknown;
  summary: string;
  usage: { input_tokens: number; output_tokens: number; estimated_cost_usd: number };
  data_manifest: unknown;
};

export type RunResult = {
  run_id: string;
  status: RunStatus;
  result: AnalysisResult | null;
};

export type HistoryItem = {
  run_id: string;
  created_at: string;
  regime: string | null;
  status: RunStatus;
};

export type DerivativesPriceRequest = {
  regime: string;
  spot: number;
  strike: number;
  tenor_days: number;
  option_type?: "call" | "put";
  style?: "european" | "american";
  n_paths?: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...init,
    });
    if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  analyze: (body: AnalyzeRequest) =>
    request<{ run_id: string }>("/api/analyze", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getRun: (runId: string) =>
    request<RunResult>(`/api/runs/${runId}`),

  cancelRun: (runId: string) =>
    request<{ run_id: string; status: RunStatus }>(`/api/runs/${runId}/cancel`, {
      method: "POST",
    }),

  getHistory: () =>
    request<HistoryItem[]>("/api/history"),

  priceDerivative: (body: DerivativesPriceRequest) =>
    request("/api/derivatives/price", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
```

- [ ] **Step 2: Verify existing tests pass**

```bash
cd frontend && npm run test -- lib/__tests__/api.test.ts
```

Expected: all existing api tests pass (they don't test the new methods).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: extend api types — AnalysisResult, cancelRun, analysis_mode"
```

---

## Task 3: Zustand store

**Files:**
- Create: `frontend/lib/store.ts`

- [ ] **Step 1: Create the store**

Create `frontend/lib/store.ts`:

```ts
import { create } from "zustand";
import type { AnalysisResult } from "./api";

type RunStatus = "idle" | "running" | "completed" | "failed";

type RunStore = {
  runId: string | null;
  status: RunStatus;
  result: AnalysisResult | null;
  error: string | null;
  setRun: (runId: string) => void;
  setResult: (result: AnalysisResult) => void;
  setStatus: (status: RunStatus) => void;
  setError: (error: string) => void;
  clearRun: () => void;
};

export const useRunStore = create<RunStore>((set) => ({
  runId: null,
  status: "idle",
  result: null,
  error: null,
  setRun: (runId) => set({ runId, status: "running", result: null, error: null }),
  setResult: (result) => set({ result, status: "completed" }),
  setStatus: (status) => set({ status }),
  setError: (error) => set({ error, status: "failed" }),
  clearRun: () => set({ runId: null, status: "idle", result: null, error: null }),
}));
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/store.ts
git commit -m "feat: add Zustand run store"
```

---

## Task 4: ThemeProvider — layout wiring

**Files:**
- Create: `frontend/app/providers.tsx`
- Modify: `frontend/app/layout.tsx`

- [ ] **Step 1: Create providers wrapper**

Create `frontend/app/providers.tsx`:

```tsx
"use client";

import { ThemeProvider } from "next-themes";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" disableTransitionOnChange>
      {children}
    </ThemeProvider>
  );
}
```

- [ ] **Step 2: Wrap layout body in Providers**

Replace `frontend/app/layout.tsx` with:

```tsx
import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "TemporalAgent",
  description: "Energy market regime detection powered by TabPFN",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

Note: `suppressHydrationWarning` on `<html>` is required because `next-themes` changes the `class` attribute on the server vs. client and would otherwise produce a hydration warning.

- [ ] **Step 3: Verify type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/providers.tsx frontend/app/layout.tsx
git commit -m "feat: add ThemeProvider for dark/light mode switching"
```

---

## Task 5: AgentStreamView — presentational component (TDD)

**Files:**
- Create: `frontend/components/__tests__/AgentStreamView.test.tsx`
- Create: `frontend/components/AgentStreamView.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/components/__tests__/AgentStreamView.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { AgentStreamView } from "../AgentStreamView";
import type { StreamMessage } from "@/lib/websocket";

describe("AgentStreamView", () => {
  it("shows empty state when no run is active", () => {
    render(<AgentStreamView messages={[]} connected={false} isRunning={false} />);
    expect(screen.getByText(/run an analysis/i)).toBeInTheDocument();
  });

  it("shows connecting indicator when running but not yet connected", () => {
    render(<AgentStreamView messages={[]} connected={false} isRunning={true} />);
    expect(screen.getByText(/connecting/i)).toBeInTheDocument();
  });

  it("renders thought messages", () => {
    const messages: StreamMessage[] = [
      { type: "thought", content: "Fetching EIA data" },
    ];
    render(<AgentStreamView messages={messages} connected={true} isRunning={true} />);
    expect(screen.getByText(/Fetching EIA data/)).toBeInTheDocument();
  });

  it("renders tool_call messages with tool name", () => {
    const messages: StreamMessage[] = [
      { type: "tool_call", tool: "run_tabpfn", input: {} },
    ];
    render(<AgentStreamView messages={messages} connected={true} isRunning={true} />);
    expect(screen.getByText(/run_tabpfn/)).toBeInTheDocument();
  });

  it("renders tool_result messages", () => {
    const messages: StreamMessage[] = [
      { type: "tool_result", tool: "run_tabpfn", output: {} },
    ];
    render(<AgentStreamView messages={messages} connected={true} isRunning={true} />);
    expect(screen.getByText(/run_tabpfn/)).toBeInTheDocument();
  });

  it("renders prediction messages with regime and confidence", () => {
    const messages: StreamMessage[] = [
      { type: "prediction", regime: "range_bound", confidence: 0.95 },
    ];
    render(<AgentStreamView messages={messages} connected={true} isRunning={true} />);
    expect(screen.getByText(/range_bound/)).toBeInTheDocument();
    expect(screen.getByText(/95\.0%/)).toBeInTheDocument();
  });

  it("renders done message", () => {
    const messages: StreamMessage[] = [
      { type: "done", summary: "Analysis complete" },
    ];
    render(<AgentStreamView messages={messages} connected={true} isRunning={true} />);
    expect(screen.getByText(/Complete/i)).toBeInTheDocument();
  });

  it("shows connection lost banner when disconnected with messages", () => {
    const messages: StreamMessage[] = [
      { type: "thought", content: "Working..." },
    ];
    render(<AgentStreamView messages={messages} connected={false} isRunning={true} />);
    expect(screen.getByText(/connection lost/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd frontend && npm run test -- components/__tests__/AgentStreamView.test.tsx
```

Expected: FAIL — `Cannot find module '../AgentStreamView'`

- [ ] **Step 3: Implement AgentStreamView**

Create `frontend/components/AgentStreamView.tsx`:

```tsx
import type { StreamMessage } from "@/lib/websocket";

interface Props {
  messages: StreamMessage[];
  connected: boolean;
  isRunning: boolean;
}

export function AgentStreamView({ messages, connected, isRunning }: Props) {
  if (!isRunning && messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <p className="text-slate-500 dark:text-slate-400 text-sm text-center">
          Run an analysis to see the agent&apos;s reasoning.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto p-4 font-mono text-sm gap-1">
      {isRunning && !connected && messages.length === 0 && (
        <p className="text-slate-400 dark:text-slate-500 text-xs animate-pulse">
          Connecting…
        </p>
      )}
      {!connected && messages.length > 0 && (
        <p className="text-amber-500 text-xs mb-2">Connection lost</p>
      )}
      {messages.map((msg, i) => (
        <MessageRow key={i} message={msg} />
      ))}
    </div>
  );
}

function MessageRow({ message }: { message: StreamMessage }) {
  switch (message.type) {
    case "thought":
      return (
        <div className="text-slate-500 dark:text-slate-400">
          🧠 {message.content}
        </div>
      );
    case "tool_call":
      return (
        <div>
          <span className="text-violet-600 dark:text-violet-400 font-semibold">
            ⚙ tool_call
          </span>{" "}
          <span className="text-slate-700 dark:text-slate-300">{message.tool}</span>
        </div>
      );
    case "tool_result":
      return (
        <div className="pl-4 text-slate-400 dark:text-slate-600 text-xs">
          ✓ tool_result {message.tool}
        </div>
      );
    case "prediction":
      return (
        <div className="text-emerald-600 dark:text-emerald-400">
          📊 {message.regime} · {(message.confidence * 100).toFixed(1)}%
        </div>
      );
    case "done":
      return (
        <div className="text-emerald-600 dark:text-emerald-500 font-semibold">
          ✅ Complete
        </div>
      );
  }
}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd frontend && npm run test -- components/__tests__/AgentStreamView.test.tsx
```

Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/AgentStreamView.tsx frontend/components/__tests__/AgentStreamView.test.tsx
git commit -m "feat: add AgentStreamView presentational component with tests"
```

---

## Task 6: AgentStream — container

**Files:**
- Create: `frontend/components/AgentStream.tsx`

- [ ] **Step 1: Implement the container**

Create `frontend/components/AgentStream.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { useRunStore } from "@/lib/store";
import { useRunStream } from "@/lib/websocket";
import { api } from "@/lib/api";
import { AgentStreamView } from "./AgentStreamView";
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

  return (
    <AgentStreamView
      messages={messages}
      connected={connected}
      isRunning={status === "running"}
    />
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/AgentStream.tsx
git commit -m "feat: add AgentStream container — WS subscription + done→getRun"
```

---

## Task 7: RegimeCard (TDD)

**Files:**
- Create: `frontend/components/__tests__/RegimeCard.test.tsx`
- Create: `frontend/components/RegimeCard.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/components/__tests__/RegimeCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { RegimeCard } from "../RegimeCard";
import type { RegimeResult } from "@/lib/api";

const rangebound: RegimeResult = {
  regime: "range_bound",
  confidence: 0.9503,
  entropy: 0.187,
  distribution: { range_bound: 24 },
};

describe("RegimeCard", () => {
  it("displays the regime label formatted", () => {
    render(<RegimeCard regime={rangebound} />);
    expect(screen.getByText("Range Bound")).toBeInTheDocument();
  });

  it("displays confidence as percentage", () => {
    render(<RegimeCard regime={rangebound} />);
    expect(screen.getByText("95.0%")).toBeInTheDocument();
  });

  it("displays entropy value", () => {
    render(<RegimeCard regime={rangebound} />);
    expect(screen.getByText(/0\.187/)).toBeInTheDocument();
  });

  it("renders bull_supercycle label formatted", () => {
    const bull: RegimeResult = { ...rangebound, regime: "bull_supercycle" };
    render(<RegimeCard regime={bull} />);
    expect(screen.getByText("Bull Supercycle")).toBeInTheDocument();
  });

  it("renders geopolitical_spike label formatted", () => {
    const spike: RegimeResult = { ...rangebound, regime: "geopolitical_spike" };
    render(<RegimeCard regime={spike} />);
    expect(screen.getByText("Geopolitical Spike")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd frontend && npm run test -- components/__tests__/RegimeCard.test.tsx
```

Expected: FAIL — `Cannot find module '../RegimeCard'`

- [ ] **Step 3: Implement RegimeCard**

Create `frontend/components/RegimeCard.tsx`:

```tsx
import type { RegimeResult } from "@/lib/api";

interface Props {
  regime: RegimeResult;
}

const REGIME_COLORS: Record<string, string> = {
  range_bound: "text-violet-600 dark:text-violet-400",
  bull_supercycle: "text-emerald-600 dark:text-emerald-400",
  bust: "text-red-600 dark:text-red-400",
  geopolitical_spike: "text-amber-600 dark:text-amber-400",
};

const REGIME_BAR: Record<string, string> = {
  range_bound: "bg-violet-500",
  bull_supercycle: "bg-emerald-500",
  bust: "bg-red-500",
  geopolitical_spike: "bg-amber-500",
};

function formatRegime(regime: string): string {
  return regime
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function RegimeCard({ regime }: Props) {
  const pct = (regime.confidence * 100).toFixed(1);
  const color = REGIME_COLORS[regime.regime] ?? "text-slate-600 dark:text-slate-400";
  const barColor = REGIME_BAR[regime.regime] ?? "bg-slate-500";

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold tracking-widest text-slate-500 dark:text-slate-400 uppercase">
          Regime
        </span>
        <span className="text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-2 py-0.5 rounded">
          {pct}%
        </span>
      </div>
      <p className={`text-2xl font-bold mb-3 ${color}`}>{formatRegime(regime.regime)}</p>
      <div className="h-1.5 w-full bg-slate-100 dark:bg-slate-800 rounded-full">
        <div
          className={`h-1.5 rounded-full ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-400 dark:text-slate-600 mt-1 text-right">
        entropy {regime.entropy.toFixed(3)}
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd frontend && npm run test -- components/__tests__/RegimeCard.test.tsx
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/RegimeCard.tsx frontend/components/__tests__/RegimeCard.test.tsx
git commit -m "feat: add RegimeCard component with tests"
```

---

## Task 8: DirectionCard (TDD)

**Files:**
- Create: `frontend/components/__tests__/DirectionCard.test.tsx`
- Create: `frontend/components/DirectionCard.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/components/__tests__/DirectionCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { DirectionCard } from "../DirectionCard";
import type { DirectionResult } from "@/lib/api";

const down: DirectionResult = {
  direction: "down",
  confidence: 0.7046,
  entropy: 0.607,
  prediction_date: "2023-06-30",
  distribution: { down: 20 },
};

const up: DirectionResult = {
  ...down,
  direction: "up",
  confidence: 0.82,
};

describe("DirectionCard", () => {
  it("shows Down label for down direction", () => {
    render(<DirectionCard direction={down} />);
    expect(screen.getByText("Down")).toBeInTheDocument();
  });

  it("shows Up label for up direction", () => {
    render(<DirectionCard direction={up} />);
    expect(screen.getByText("Up")).toBeInTheDocument();
  });

  it("displays confidence as percentage", () => {
    render(<DirectionCard direction={down} />);
    expect(screen.getByText("70.5%")).toBeInTheDocument();
  });

  it("displays prediction date", () => {
    render(<DirectionCard direction={down} />);
    expect(screen.getByText(/2023-06-30/)).toBeInTheDocument();
  });

  it("shows down arrow for down direction", () => {
    render(<DirectionCard direction={down} />);
    expect(screen.getByText("↓")).toBeInTheDocument();
  });

  it("shows up arrow for up direction", () => {
    render(<DirectionCard direction={up} />);
    expect(screen.getByText("↑")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd frontend && npm run test -- components/__tests__/DirectionCard.test.tsx
```

Expected: FAIL — `Cannot find module '../DirectionCard'`

- [ ] **Step 3: Implement DirectionCard**

Create `frontend/components/DirectionCard.tsx`:

```tsx
import type { DirectionResult } from "@/lib/api";

interface Props {
  direction: DirectionResult;
}

export function DirectionCard({ direction }: Props) {
  const isUp = direction.direction === "up";
  const pct = (direction.confidence * 100).toFixed(1);

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold tracking-widest text-slate-500 dark:text-slate-400 uppercase">
          WTI Direction
        </span>
        <span className="text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 px-2 py-0.5 rounded">
          {pct}%
        </span>
      </div>
      <div className="flex items-center gap-3 mb-3">
        <span
          className={`text-4xl font-bold leading-none ${
            isUp
              ? "text-emerald-500 dark:text-emerald-400"
              : "text-red-500 dark:text-red-400"
          }`}
        >
          {isUp ? "↑" : "↓"}
        </span>
        <span
          className={`text-2xl font-bold ${
            isUp
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-red-600 dark:text-red-400"
          }`}
        >
          {isUp ? "Up" : "Down"}
        </span>
      </div>
      <div className="h-1.5 w-full bg-slate-100 dark:bg-slate-800 rounded-full">
        <div
          className={`h-1.5 rounded-full ${
            isUp ? "bg-emerald-500" : "bg-red-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-400 dark:text-slate-600 mt-1">
        as of {direction.prediction_date}
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd frontend && npm run test -- components/__tests__/DirectionCard.test.tsx
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/DirectionCard.tsx frontend/components/__tests__/DirectionCard.test.tsx
git commit -m "feat: add DirectionCard component with tests"
```

---

## Task 9: SummaryPanel

**Files:**
- Create: `frontend/components/SummaryPanel.tsx`

- [ ] **Step 1: Implement SummaryPanel**

Create `frontend/components/SummaryPanel.tsx`:

```tsx
interface Props {
  summary: string;
}

export function SummaryPanel({ summary }: Props) {
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 border-l-4 border-l-violet-500 dark:border-l-violet-600">
      <span className="text-xs font-semibold tracking-widest text-slate-500 dark:text-slate-400 uppercase block mb-2">
        Summary
      </span>
      <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
        {summary}
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/SummaryPanel.tsx
git commit -m "feat: add SummaryPanel component"
```

---

## Task 10: ResultsPanel (TDD)

**Files:**
- Create: `frontend/components/__tests__/ResultsPanel.test.tsx`
- Create: `frontend/components/ResultsPanel.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/components/__tests__/ResultsPanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { ResultsPanel } from "../ResultsPanel";
import { useRunStore } from "@/lib/store";
import type { AnalysisResult } from "@/lib/api";

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
  useRunStore.setState({ runId: null, status: "idle", result: null, error: null });
});

describe("ResultsPanel", () => {
  it("shows skeleton when status is running and result is null", () => {
    useRunStore.setState({ status: "running", result: null });
    render(<ResultsPanel />);
    expect(screen.getByTestId("results-skeleton")).toBeInTheDocument();
  });

  it("shows empty state when idle", () => {
    render(<ResultsPanel />);
    expect(screen.getByText(/results will appear/i)).toBeInTheDocument();
  });

  it("renders RegimeCard with regime label when result is set", () => {
    useRunStore.setState({ status: "completed", result: mockResult });
    render(<ResultsPanel />);
    expect(screen.getByText("Range Bound")).toBeInTheDocument();
  });

  it("renders DirectionCard when result is set", () => {
    useRunStore.setState({ status: "completed", result: mockResult });
    render(<ResultsPanel />);
    expect(screen.getByText("Down")).toBeInTheDocument();
  });

  it("renders SummaryPanel text when result is set", () => {
    useRunStore.setState({ status: "completed", result: mockResult });
    render(<ResultsPanel />);
    expect(screen.getByText("Range-bound regime with high confidence.")).toBeInTheDocument();
  });

  it("shows error state when status is failed", () => {
    useRunStore.setState({ status: "failed", error: "Network error" });
    render(<ResultsPanel />);
    expect(screen.getByText(/Network error/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd frontend && npm run test -- components/__tests__/ResultsPanel.test.tsx
```

Expected: FAIL — `Cannot find module '../ResultsPanel'`

- [ ] **Step 3: Implement ResultsPanel**

Create `frontend/components/ResultsPanel.tsx`:

```tsx
"use client";

import { useRunStore } from "@/lib/store";
import { RegimeCard } from "./RegimeCard";
import { DirectionCard } from "./DirectionCard";
import { SummaryPanel } from "./SummaryPanel";

export function ResultsPanel() {
  const { status, result, error } = useRunStore();

  if (status === "idle") {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <p className="text-sm text-slate-500 dark:text-slate-400 text-center">
          Results will appear here after analysis completes.
        </p>
      </div>
    );
  }

  if (status === "running" && !result) {
    return (
      <div
        data-testid="results-skeleton"
        className="flex flex-col gap-3 p-4 animate-pulse"
      >
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-24 rounded-lg bg-slate-100 dark:bg-slate-800"
          />
        ))}
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="text-center">
          <p className="text-sm text-red-500 dark:text-red-400 mb-2">
            {error ?? "Analysis failed"}
          </p>
        </div>
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className="flex flex-col gap-3 p-4 overflow-y-auto">
      {result.regime && <RegimeCard regime={result.regime} />}
      {result.direction && <DirectionCard direction={result.direction} />}
      {result.summary && <SummaryPanel summary={result.summary} />}
    </div>
  );
}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd frontend && npm run test -- components/__tests__/ResultsPanel.test.tsx
```

Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ResultsPanel.tsx frontend/components/__tests__/ResultsPanel.test.tsx
git commit -m "feat: add ResultsPanel with skeleton, error, and result states"
```

---

## Task 11: TopBar

**Files:**
- Create: `frontend/components/TopBar.tsx`

- [ ] **Step 1: Implement TopBar**

Create `frontend/components/TopBar.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useTheme } from "next-themes";
import { useRunStore } from "@/lib/store";
import { api } from "@/lib/api";

export function TopBar() {
  const [start, setStart] = useState("2023-01-01");
  const [end, setEnd] = useState("2023-06-30");
  const [mode, setMode] = useState<"quick" | "full">("quick");
  const [topbarError, setTopbarError] = useState<string | null>(null);
  const { theme, setTheme } = useTheme();
  const { runId, status, setRun, clearRun } = useRunStore();

  const isRunning = status === "running";

  const handleRun = async () => {
    setTopbarError(null);
    try {
      const { run_id } = await api.analyze({
        date_range_start: start,
        date_range_end: end,
        analysis_mode: mode,
      });
      setRun(run_id);
    } catch (e) {
      setTopbarError(e instanceof Error ? e.message : "Failed to start analysis");
    }
  };

  const handleCancel = async () => {
    if (!runId) return;
    try {
      await api.cancelRun(runId);
    } finally {
      clearRun();
    }
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
          {theme === "dark" ? "☀" : "🌙"}
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/TopBar.tsx
git commit -m "feat: add TopBar with date inputs, mode toggle, run/cancel, theme switch"
```

---

## Task 12: Wire up page.tsx

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Replace placeholder with split-pane layout**

Replace `frontend/app/page.tsx` with:

```tsx
import { TopBar } from "@/components/TopBar";
import { AgentStream } from "@/components/AgentStream";
import { ResultsPanel } from "@/components/ResultsPanel";

export default function Home() {
  return (
    <div className="flex flex-col h-screen bg-white dark:bg-[#0f0f1a]">
      <TopBar />
      <main className="flex flex-1 overflow-hidden">
        <section className="flex-1 overflow-hidden border-r border-slate-200 dark:border-slate-800">
          <AgentStream />
        </section>
        <section className="flex-1 overflow-hidden">
          <ResultsPanel />
        </section>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: wire split-pane layout in page.tsx"
```

---

## Task 13: Full test suite + final check

- [ ] **Step 1: Run all frontend tests**

```bash
cd frontend && npm run test
```

Expected: all tests pass — 0 failures. You should see passing suites for:
- `lib/__tests__/api.test.ts`
- `lib/__tests__/websocket.test.ts`
- `components/__tests__/AgentStreamView.test.tsx`
- `components/__tests__/RegimeCard.test.tsx`
- `components/__tests__/DirectionCard.test.tsx`
- `components/__tests__/ResultsPanel.test.tsx`

- [ ] **Step 2: Run type-check and lint**

```bash
cd frontend && npm run type-check && npm run lint
```

Expected: no errors, no warnings.

- [ ] **Step 3: Start dev server and do a visual smoke test**

```bash
# In one terminal — ensure backend is running or skip to just check the frontend renders
cd frontend && npm run dev
```

Open `http://localhost:3000`. Verify:
- Dark mode is applied by default
- TopBar is visible with date inputs, Quick/Full toggle, Run button, theme icon
- Left pane shows "Run an analysis to see the agent's reasoning."
- Right pane shows "Results will appear here after analysis completes."
- Clicking the theme icon toggles to light mode (purple → blue accent)

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: Session 6 frontend — split-pane dashboard with AgentStream and result cards"
```
