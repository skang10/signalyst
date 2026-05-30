# Chat Window PR 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible right-side chat panel where users can type pre-run context messages before clicking Run, with those messages forwarded to the agent as initial conversation context.

**Architecture:** A new `ChatPanel` component reads `chatOpen` from the Zustand store and renders a fixed-width (280px) aside panel alongside `ResultsPanel`. Pre-run messages typed in the panel are queued in `pendingPreRunMessages` in the store; the TopBar reads and forwards them as `pre_messages` in the `POST /api/analyze` body. The backend inserts them into the agent's message history between the system prompt and the main analysis request.

**Tech Stack:** Next.js 15 App Router, TypeScript, Tailwind CSS, Zustand (`zustand`), FastAPI (Python), Pydantic, pytest (asyncio_mode=auto), Vitest + `@testing-library/react`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `frontend/lib/store.ts` | Add `ChatMessage` type; add `chatOpen`, `chatMessages`, `pendingPreRunMessages` state + 4 new actions |
| Modify | `frontend/lib/api.ts` | Add optional `pre_messages?: string[]` field to `AnalyzeRequest` type |
| Create | `frontend/components/ChatPanel.tsx` | Collapsible chat panel: message list + input bar; reads/writes store directly |
| Modify | `frontend/components/TopBar.tsx` | Add 💬 Chat toggle button; pass `pendingPreRunMessages` to `api.analyze` on Run |
| Modify | `frontend/app/page.tsx` | Render `<ChatPanel />` inside `<main>` alongside `<ResultsPanel />` |
| Modify | `frontend/lib/__tests__/store.test.ts` | Add tests for the 4 new store actions |
| Modify | `frontend/components/__tests__/TopBar.test.tsx` | Add tests for Chat toggle and pre_messages forwarding |
| Create | `frontend/components/__tests__/ChatPanel.test.tsx` | Tests for ChatPanel rendering, input states, send behaviour |
| Modify | `backend/api/routes/analyze.py` | Add `pre_messages: list[str] = []` to `AnalyzeRequest`; forward to `run_agent_loop` as keyword arg |
| Modify | `backend/src/agent/loop.py` | Add `pre_messages` param; insert messages between system prompt and main user message |
| Modify | `backend/tests/test_analyze_route.py` | Add test that `pre_messages` are forwarded to `run_agent_loop` |
| Modify | `backend/tests/test_agent_loop.py` | Add test that pre_messages appear correctly in the LLM message list |

---

## Task 1: Extend the Zustand store with chat state

**Files:**
- Modify: `frontend/lib/store.ts`
- Modify: `frontend/lib/__tests__/store.test.ts`

- [ ] **Step 1: Write failing tests for the new store actions**

Add these tests to the **bottom** of `frontend/lib/__tests__/store.test.ts` (after the existing `describe` blocks):

```typescript
describe("useRunStore — chat state", () => {
  it("chatOpen defaults to false", () => {
    expect(useRunStore.getState().chatOpen).toBe(false);
  });

  it("setChatOpen toggles chatOpen", () => {
    useRunStore.getState().setChatOpen(true);
    expect(useRunStore.getState().chatOpen).toBe(true);
    useRunStore.getState().setChatOpen(false);
    expect(useRunStore.getState().chatOpen).toBe(false);
  });

  it("addChatMessage appends to chatMessages", () => {
    const msg = { id: "1", role: "user" as const, content: "hello", timestamp: 0 };
    useRunStore.getState().addChatMessage(msg);
    expect(useRunStore.getState().chatMessages).toHaveLength(1);
    expect(useRunStore.getState().chatMessages[0]).toEqual(msg);
  });

  it("queuePreRunMessage appends to pendingPreRunMessages", () => {
    useRunStore.getState().queuePreRunMessage("Add EIA data");
    expect(useRunStore.getState().pendingPreRunMessages).toEqual(["Add EIA data"]);
  });

  it("clearPreRunMessages empties pendingPreRunMessages", () => {
    useRunStore.getState().queuePreRunMessage("msg1");
    useRunStore.getState().queuePreRunMessage("msg2");
    useRunStore.getState().clearPreRunMessages();
    expect(useRunStore.getState().pendingPreRunMessages).toHaveLength(0);
  });

  it("clearRun resets chatMessages and pendingPreRunMessages", () => {
    useRunStore.getState().addChatMessage({ id: "1", role: "user", content: "x", timestamp: 0 });
    useRunStore.getState().queuePreRunMessage("x");
    useRunStore.getState().clearRun();
    expect(useRunStore.getState().chatMessages).toHaveLength(0);
    expect(useRunStore.getState().pendingPreRunMessages).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm run test -- --reporter=verbose lib/__tests__/store.test.ts
```

Expected: 6 new tests fail with "chatOpen is not a function" / property undefined errors.

- [ ] **Step 3: Update `frontend/lib/store.ts`**

Replace the entire file with:

```typescript
import { create } from "zustand";
import type { AnalysisResult } from "./api";
import type { StreamMessage } from "./websocket";

type StoreStatus = "idle" | "running" | "completed" | "failed" | "canceled";

type LastRunParams = {
  date_range_start: string;
  date_range_end: string;
  analysis_mode: "quick" | "full";
};

export type ChatMessage = {
  id: string;
  role: "user" | "agent";
  content: string;
  timestamp: number;
  toolPill?: { name: string; status: "running" | "done" | "failed" };
};

type RunStore = {
  runId: string | null;
  status: StoreStatus;
  result: AnalysisResult | null;
  error: string | null;
  messages: StreamMessage[];
  lastRunParams: LastRunParams | null;
  chatOpen: boolean;
  chatMessages: ChatMessage[];
  pendingPreRunMessages: string[];
  setRun: (runId: string, params: LastRunParams) => void;
  setResult: (result: AnalysisResult) => void;
  setStatus: (status: StoreStatus) => void;
  setError: (error: string) => void;
  setMessages: (msgs: StreamMessage[]) => void;
  setCanceled: () => void;
  clearRun: () => void;
  hydrate: () => void;
  setChatOpen: (open: boolean) => void;
  addChatMessage: (msg: ChatMessage) => void;
  queuePreRunMessage: (msg: string) => void;
  clearPreRunMessages: () => void;
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
  runId: null,
  status: "idle",
  result: null,
  error: null,
  messages: [],
  lastRunParams: null,
  chatOpen: false,
  chatMessages: [],
  pendingPreRunMessages: [],
  setRun: (runId, params) => {
    sessionStorage.setItem(RUN_ID_KEY, runId);
    sessionStorage.removeItem(MESSAGES_KEY);
    set({
      runId,
      status: "running",
      result: null,
      error: null,
      messages: [],
      lastRunParams: params,
    });
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
      // sessionStorage full - continue without persisting
    }
    set({ messages });
  },
  setCanceled: () => set({ status: "canceled" }),
  clearRun: () => {
    clearPersisted();
    set({
      runId: null,
      status: "idle",
      result: null,
      error: null,
      messages: [],
      lastRunParams: null,
      chatMessages: [],
      pendingPreRunMessages: [],
    });
  },
  hydrate: () => {
    const runId = readPersistedRunId();
    const messages = readPersistedMessages();
    if (runId) set({ runId, messages });
  },
  setChatOpen: (open) => set({ chatOpen: open }),
  addChatMessage: (msg) =>
    set((state) => ({ chatMessages: [...state.chatMessages, msg] })),
  queuePreRunMessage: (msg) =>
    set((state) => ({ pendingPreRunMessages: [...state.pendingPreRunMessages, msg] })),
  clearPreRunMessages: () => set({ pendingPreRunMessages: [] }),
}));
```

- [ ] **Step 4: Update `beforeEach` in the store test to include new fields**

Find the `beforeEach` block at the top of `frontend/lib/__tests__/store.test.ts` and replace it:

```typescript
beforeEach(() => {
  sessionStorage.clear();
  useRunStore.setState({
    runId: null,
    status: "idle",
    result: null,
    error: null,
    messages: [],
    lastRunParams: null,
    chatOpen: false,
    chatMessages: [],
    pendingPreRunMessages: [],
  });
});
```

- [ ] **Step 5: Run all store tests to verify they pass**

```bash
cd frontend && npm run test -- --reporter=verbose lib/__tests__/store.test.ts
```

Expected: ALL tests pass (existing + 6 new).

- [ ] **Step 6: Run type-check to catch errors**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/store.ts frontend/lib/__tests__/store.test.ts
git commit -m "feat(store): add chat state — chatOpen, chatMessages, pendingPreRunMessages"
```

---

## Task 2: Add `pre_messages` to the frontend API type

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add `pre_messages` to `AnalyzeRequest`**

In `frontend/lib/api.ts`, find the `AnalyzeRequest` type and add the optional field:

```typescript
export type AnalyzeRequest = {
  date_range_start: string;
  date_range_end: string;
  tasks?: string[];
  analysis_mode?: "quick" | "full";
  pre_messages?: string[];
};
```

- [ ] **Step 2: Run type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(api): add pre_messages field to AnalyzeRequest type"
```

---

## Task 3: Build the ChatPanel component

**Files:**
- Create: `frontend/components/ChatPanel.tsx`
- Create: `frontend/components/__tests__/ChatPanel.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/components/__tests__/ChatPanel.test.tsx`:

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { ChatPanel } from "../ChatPanel";
import { useRunStore } from "@/lib/store";

beforeEach(() => {
  useRunStore.setState({
    runId: null,
    status: "idle",
    result: null,
    error: null,
    messages: [],
    lastRunParams: null,
    chatOpen: false,
    chatMessages: [],
    pendingPreRunMessages: [],
  });
});

describe("ChatPanel — visibility", () => {
  it("renders nothing when chatOpen is false", () => {
    useRunStore.setState({ chatOpen: false });
    const { container } = render(<ChatPanel />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the panel when chatOpen is true", () => {
    useRunStore.setState({ chatOpen: true });
    render(<ChatPanel />);
    expect(screen.getByRole("button", { name: /close chat/i })).toBeTruthy();
  });

  it("close button calls setChatOpen(false)", () => {
    useRunStore.setState({ chatOpen: true });
    render(<ChatPanel />);
    fireEvent.click(screen.getByRole("button", { name: /close chat/i }));
    expect(useRunStore.getState().chatOpen).toBe(false);
  });
});

describe("ChatPanel — input states", () => {
  it("input is enabled and shows idle placeholder when status is idle", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask the agent/i);
    expect(textarea).not.toBeDisabled();
  });

  it("input is disabled when status is running", () => {
    useRunStore.setState({ chatOpen: true, status: "running", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/agent is working/i);
    expect(textarea).toBeDisabled();
  });

  it("input is enabled when status is completed", () => {
    useRunStore.setState({ chatOpen: true, status: "completed", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask a follow-up/i);
    expect(textarea).not.toBeDisabled();
  });

  it("input is disabled when status is failed", () => {
    useRunStore.setState({ chatOpen: true, status: "failed", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/run ended/i);
    expect(textarea).toBeDisabled();
  });

  it("input is disabled when status is canceled", () => {
    useRunStore.setState({ chatOpen: true, status: "canceled", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/run ended/i);
    expect(textarea).toBeDisabled();
  });
});

describe("ChatPanel — send behaviour", () => {
  it("send while idle adds to chatMessages and pendingPreRunMessages", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask the agent/i);
    fireEvent.change(textarea, { target: { value: "Add Baker Hughes data" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    const { chatMessages, pendingPreRunMessages } = useRunStore.getState();
    expect(chatMessages).toHaveLength(1);
    expect(chatMessages[0].role).toBe("user");
    expect(chatMessages[0].content).toBe("Add Baker Hughes data");
    expect(pendingPreRunMessages).toEqual(["Add Baker Hughes data"]);
  });

  it("send while completed adds to chatMessages but NOT pendingPreRunMessages", () => {
    useRunStore.setState({ chatOpen: true, status: "completed", runId: "r1" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask a follow-up/i);
    fireEvent.change(textarea, { target: { value: "Why is drift elevated?" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    const { chatMessages, pendingPreRunMessages } = useRunStore.getState();
    expect(chatMessages).toHaveLength(1);
    expect(pendingPreRunMessages).toHaveLength(0);
  });

  it("send clears the textarea", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask the agent/i);
    fireEvent.change(textarea, { target: { value: "test" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("send button is disabled when input is empty", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("pressing Enter sends the message", () => {
    useRunStore.setState({ chatOpen: true, status: "idle" });
    render(<ChatPanel />);
    const textarea = screen.getByPlaceholderText(/ask the agent/i);
    fireEvent.change(textarea, { target: { value: "Enter key test" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(useRunStore.getState().chatMessages).toHaveLength(1);
  });

  it("existing chatMessages are displayed", () => {
    useRunStore.setState({
      chatOpen: true,
      status: "idle",
      chatMessages: [
        { id: "1", role: "user", content: "Hello agent", timestamp: 0 },
        { id: "2", role: "agent", content: "Hello user", timestamp: 1 },
      ],
    });
    render(<ChatPanel />);
    expect(screen.getByText("Hello agent")).toBeTruthy();
    expect(screen.getByText("Hello user")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm run test -- --reporter=verbose components/__tests__/ChatPanel.test.tsx
```

Expected: ALL tests fail — `ChatPanel` does not exist yet.

- [ ] **Step 3: Create `frontend/components/ChatPanel.tsx`**

```typescript
"use client";

import { useRef, useState } from "react";
import { useRunStore } from "@/lib/store";
import type { ChatMessage } from "@/lib/store";

export function ChatPanel() {
  const { chatOpen, chatMessages, status, setChatOpen, addChatMessage, queuePreRunMessage } =
    useRunStore();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  if (!chatOpen) return null;

  const isInputDisabled =
    status === "running" || status === "failed" || status === "canceled";

  const placeholder =
    status === "running"
      ? "Agent is working — message will be queued"
      : status === "completed"
        ? "Ask a follow-up question…"
        : status === "failed" || status === "canceled"
          ? "Run ended"
          : "Ask the agent — add a connector, set context…";

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isInputDisabled) return;

    const msg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: Date.now(),
    };
    addChatMessage(msg);
    if (status === "idle") {
      queuePreRunMessage(trimmed);
    }
    setInput("");
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 0);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <aside className="w-70 border-l border-slate-800 flex flex-col bg-[#0f0f1a] shrink-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800">
        <span className="text-sm font-semibold text-slate-300">Chat</span>
        <button
          onClick={() => setChatOpen(false)}
          className="text-slate-500 hover:text-slate-300 text-sm leading-none"
          aria-label="Close chat"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-0">
        {chatMessages.length === 0 && (
          <p className="text-xs text-slate-500 text-center mt-4">
            Messages appear here.
          </p>
        )}
        {chatMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={
                msg.role === "user"
                  ? "bg-indigo-600 text-white rounded-lg px-3 py-2 max-w-[85%] text-sm"
                  : "bg-slate-800 text-slate-200 rounded-lg px-3 py-2 max-w-[85%] text-sm"
              }
            >
              {msg.content}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-slate-800 p-2 flex gap-2 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isInputDisabled}
          placeholder={placeholder}
          rows={2}
          className={
            "flex-1 resize-none rounded border border-slate-700 bg-slate-900 text-slate-100 " +
            "text-sm px-2 py-1 focus:outline-none focus:ring-1 focus:ring-violet-500 " +
            "disabled:opacity-50 disabled:cursor-not-allowed"
          }
        />
        <button
          onClick={handleSend}
          disabled={isInputDisabled || !input.trim()}
          aria-label="Send message"
          className={
            "px-2 py-1 rounded bg-violet-600 hover:bg-violet-700 text-white text-sm " +
            "font-semibold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          }
        >
          ↑
        </button>
      </div>
    </aside>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --reporter=verbose components/__tests__/ChatPanel.test.tsx
```

Expected: ALL tests pass.

- [ ] **Step 5: Run type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/ChatPanel.tsx frontend/components/__tests__/ChatPanel.test.tsx
git commit -m "feat(chat): add ChatPanel component with pre-run message queuing"
```

---

## Task 4: Wire Chat toggle into TopBar and pass pre_messages on Run

**Files:**
- Modify: `frontend/components/TopBar.tsx`
- Modify: `frontend/components/__tests__/TopBar.test.tsx`

- [ ] **Step 1: Write failing tests**

Add these tests to the **bottom** of `frontend/components/__tests__/TopBar.test.tsx`, updating the `beforeEach` and adding two new `describe` blocks:

First, update the `beforeEach` to include the new chat state fields:

```typescript
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
    chatOpen: false,
    chatMessages: [],
    pendingPreRunMessages: [],
  });
});
```

Then add these new test blocks at the bottom of the file:

```typescript
describe("TopBar — chat toggle", () => {
  it("renders a Chat toggle button", () => {
    render(<TopBar />);
    expect(screen.getByRole("button", { name: /chat/i })).toBeTruthy();
  });

  it("clicking the Chat button sets chatOpen to true when closed", () => {
    useRunStore.setState({ chatOpen: false });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /chat/i }));
    expect(useRunStore.getState().chatOpen).toBe(true);
  });

  it("clicking the Chat button sets chatOpen to false when open", () => {
    useRunStore.setState({ chatOpen: true });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: /chat/i }));
    expect(useRunStore.getState().chatOpen).toBe(false);
  });
});

describe("TopBar — pre_messages forwarding", () => {
  it("passes pendingPreRunMessages as pre_messages when running analysis", async () => {
    mockAnalyze.mockResolvedValueOnce({ run_id: "run-99" });
    useRunStore.setState({
      status: "idle",
      pendingPreRunMessages: ["Add Baker Hughes data", "Focus on 2023 Q1"],
    });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: "▶ Run" }));
    await waitFor(() => {
      expect(mockAnalyze).toHaveBeenCalledWith(
        expect.objectContaining({
          pre_messages: ["Add Baker Hughes data", "Focus on 2023 Q1"],
        })
      );
    });
  });

  it("clears pendingPreRunMessages after a successful run start", async () => {
    mockAnalyze.mockResolvedValueOnce({ run_id: "run-100" });
    useRunStore.setState({
      status: "idle",
      pendingPreRunMessages: ["Some message"],
    });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: "▶ Run" }));
    await waitFor(() => {
      expect(useRunStore.getState().pendingPreRunMessages).toHaveLength(0);
    });
  });

  it("passes empty pre_messages when there are no pending messages", async () => {
    mockAnalyze.mockResolvedValueOnce({ run_id: "run-101" });
    render(<TopBar />);
    fireEvent.click(screen.getByRole("button", { name: "▶ Run" }));
    await waitFor(() => {
      expect(mockAnalyze).toHaveBeenCalledWith(
        expect.objectContaining({ pre_messages: [] })
      );
    });
  });
});
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```bash
cd frontend && npm run test -- --reporter=verbose components/__tests__/TopBar.test.tsx
```

Expected: existing tests pass, the 6 new tests fail.

- [ ] **Step 3: Update `frontend/components/TopBar.tsx`**

Replace the entire file with:

```typescript
"use client";

import { useState, useEffect } from "react";
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

  const {
    runId,
    status,
    chatOpen,
    pendingPreRunMessages,
    setRun,
    setCanceled,
    setStatus,
    hydrate,
    setChatOpen,
    clearPreRunMessages,
  } = useRunStore();

  useEffect(() => { hydrate(); }, [hydrate]);

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
        pre_messages: pendingPreRunMessages,
      });
      clearPreRunMessages();
      setRun(run_id, { date_range_start: start, date_range_end: end, analysis_mode: mode });
    } catch (e) {
      setTopbarError(e instanceof Error ? e.message : "Failed to start analysis");
    }
  };

  const handleCancel = async () => {
    if (!runId) return;
    try {
      await api.cancelRun(runId);
    } catch {
      // swallow API errors — client-side cancellation proceeds regardless
    } finally {
      setCanceled();
    }
  };

  const handleResume = () => {
    setStatus("running");
  };

  const inputClass =
    "rounded border border-slate-700 bg-slate-900 text-slate-100 text-sm px-2 py-1 " +
    "focus:outline-none focus:ring-1 " +
    "focus:ring-violet-500";

  const pillBase = "text-sm px-3 py-1 rounded-full border transition-colors";
  const pillActive =
    "border-violet-500 bg-violet-950 text-violet-300 font-semibold";
  const pillInactive =
    "border-slate-700 text-slate-400 hover:border-slate-400";

  return (
    <header className="sticky top-0 z-10 flex items-center gap-3 px-4 py-2 border-b border-slate-800 bg-[#0f0f1a] flex-wrap">
      <span className="font-bold text-white text-base mr-1">
        Signalyst
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

        <button
          onClick={() => setChatOpen(!chatOpen)}
          className={`${pillBase} ${chatOpen ? pillActive : pillInactive}`}
          aria-label="Toggle chat"
        >
          💬 Chat
        </button>

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
              className="text-sm px-4 py-1.5 rounded border border-slate-600 text-slate-300 font-semibold hover:border-slate-500 transition-colors"
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
      </div>
    </header>
  );
}
```

- [ ] **Step 4: Run all TopBar tests**

```bash
cd frontend && npm run test -- --reporter=verbose components/__tests__/TopBar.test.tsx
```

Expected: ALL tests pass (existing + 6 new).

- [ ] **Step 5: Run type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/TopBar.tsx frontend/components/__tests__/TopBar.test.tsx
git commit -m "feat(topbar): add Chat toggle button and forward pre_messages on run"
```

---

## Task 5: Integrate ChatPanel into the page layout

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Update `frontend/app/page.tsx`**

Replace the entire file with:

```typescript
import { TopBar } from "@/components/TopBar";
import { AgentStream } from "@/components/AgentStream";
import { ResultsPanel } from "@/components/ResultsPanel";
import { ChatPanel } from "@/components/ChatPanel";

export default function Home() {
  return (
    <div className="flex flex-col h-screen bg-[#0f0f1a]">
      <TopBar />
      <AgentStream />
      <main className="flex flex-1 overflow-hidden">
        <section className="flex-1 overflow-hidden">
          <ResultsPanel />
        </section>
        <ChatPanel />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Run type-check**

```bash
cd frontend && npm run type-check
```

Expected: no errors.

- [ ] **Step 3: Run the full frontend test suite**

```bash
cd frontend && npm run test
```

Expected: ALL tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(layout): render ChatPanel alongside ResultsPanel in main"
```

---

## Task 6: Backend — add `pre_messages` to `AnalyzeRequest` and route

**Files:**
- Modify: `backend/api/routes/analyze.py`
- Modify: `backend/tests/test_analyze_route.py`

- [ ] **Step 1: Write a failing test**

Add this test at the **bottom** of `backend/tests/test_analyze_route.py`:

```python
def test_trigger_analysis_forwards_pre_messages_to_loop() -> None:
    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.refresh = AsyncMock(return_value=None)
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("api.routes.analyze.run_agent_loop") as mock_loop:
            client = TestClient(app)
            response = client.post(
                "/api/analyze",
                json={
                    "date_range_start": "2023-01-01",
                    "date_range_end": "2023-06-30",
                    "pre_messages": ["Add Baker Hughes rig count data"],
                },
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert mock_loop.call_args.kwargs["pre_messages"] == ["Add Baker Hughes rig count data"]


def test_trigger_analysis_defaults_pre_messages_to_empty_list() -> None:
    async def override_session():  # type: ignore[return]
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.refresh = AsyncMock(return_value=None)
        yield mock_session

    app.dependency_overrides[get_session] = override_session
    try:
        with patch("api.routes.analyze.run_agent_loop") as mock_loop:
            client = TestClient(app)
            response = client.post(
                "/api/analyze",
                json={
                    "date_range_start": "2023-01-01",
                    "date_range_end": "2023-06-30",
                },
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert mock_loop.call_args.kwargs["pre_messages"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_analyze_route.py::test_trigger_analysis_forwards_pre_messages_to_loop tests/test_analyze_route.py::test_trigger_analysis_defaults_pre_messages_to_empty_list -v
```

Expected: both fail — `pre_messages` field not accepted / not forwarded.

- [ ] **Step 3: Update `backend/api/routes/analyze.py`**

Replace the `AnalyzeRequest` class and the `background_tasks.add_task` call. The full updated file:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import RunResult
from src.agent import run_agent_loop
from src.agent import tabpfn_progress as _tabpfn_progress
from src.db.models import Run, RunStatus
from src.db.session import get_session

router = APIRouter(tags=["analyze"])


class AnalyzeRequest(BaseModel):
    date_range_start: str
    date_range_end: str
    tasks: list[str] = ["regime_classification", "price_direction", "equity_outperformance"]
    analysis_mode: Literal["quick", "full"] = "quick"
    pre_messages: list[str] = []


class AnalyzeResponse(BaseModel):
    run_id: str


class CancelRunResponse(BaseModel):
    run_id: str
    status: RunStatus


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/analyze", response_model=AnalyzeResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> AnalyzeResponse:
    run = Run(
        date_range_start=request.date_range_start,
        date_range_end=request.date_range_end,
        tasks=request.tasks,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    background_tasks.add_task(
        run_agent_loop,
        run.id,
        request.date_range_start,
        request.date_range_end,
        request.tasks,
        request.analysis_mode,
        pre_messages=request.pre_messages,
    )

    return AnalyzeResponse(run_id=str(run.id))


@router.get("/runs/{run_id}", response_model=RunResult)
async def get_run(run_id: str, session: SessionDep) -> RunResult:
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid run_id"
        )

    run = await session.get(Run, uid)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return RunResult(run_id=str(run.id), status=run.status, result=run.result, error=run.error)


@router.post("/runs/{run_id}/cancel", response_model=CancelRunResponse)
async def cancel_run(run_id: str, session: SessionDep) -> CancelRunResponse:
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid run_id"
        )

    run = await session.get(Run, uid)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is already terminal")

    run.status = RunStatus.CANCELED
    run.completed_at = datetime.now(UTC).replace(tzinfo=None)
    run.error = "Canceled by user"
    await session.commit()
    _tabpfn_progress.cancel(run_id)

    return CancelRunResponse(run_id=run_id, status=RunStatus.CANCELED)


@router.get("/history", response_model=list[RunResult])
async def get_history(session: SessionDep) -> list[RunResult]:
    result = await session.execute(
        select(Run).order_by(Run.created_at.desc()).limit(20)  # type: ignore[attr-defined]
    )
    runs = result.scalars().all()
    return [RunResult(run_id=str(r.id), status=r.status, result=r.result) for r in runs]
```

- [ ] **Step 4: Run all route tests**

```bash
cd backend && uv run pytest tests/test_analyze_route.py -v
```

Expected: ALL tests pass (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/analyze.py backend/tests/test_analyze_route.py
git commit -m "feat(api): accept pre_messages in AnalyzeRequest and forward to agent loop"
```

---

## Task 7: Backend — insert pre_messages in `run_agent_loop`

**Files:**
- Modify: `backend/src/agent/loop.py`
- Modify: `backend/tests/test_agent_loop.py`

- [ ] **Step 1: Write a failing test**

Add this test at the **bottom** of `backend/tests/test_agent_loop.py`:

```python
@pytest.mark.asyncio
async def test_run_agent_loop_inserts_pre_messages_before_main_request() -> None:
    """Pre-run messages are inserted between the system prompt and the main analysis request."""
    run = MagicMock()
    run.status = RunStatus.RUNNING
    sessions = _SessionFactory(run)
    redis_client = AsyncMock()
    captured_messages: list[dict] = []

    async def capture_and_cancel(*args: object, **kwargs: object) -> None:
        captured_messages.extend(kwargs["messages"])
        raise RunCanceled

    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(side_effect=capture_and_cancel)

    with (
        patch("src.agent.loop.AsyncSession", sessions),
        patch("src.agent.loop.aioredis.from_url", return_value=redis_client),
        patch("src.agent.loop.openai.AsyncOpenAI", return_value=openai_client),
    ):
        await run_agent_loop(
            uuid.uuid4(),
            "2024-01-01",
            "2024-02-01",
            ["regime"],
            pre_messages=["Add Baker Hughes rig count data"],
        )

    assert captured_messages, "expected the LLM to be called once before cancellation"
    roles = [m["role"] for m in captured_messages]
    contents = [m["content"] for m in captured_messages]
    # system prompt first
    assert roles[0] == "system"
    # pre-run message second
    assert roles[1] == "user"
    assert contents[1] == "Add Baker Hughes rig count data"
    # main analysis request last
    assert roles[-1] == "user"
    assert "Analyze" in contents[-1]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_agent_loop.py::test_run_agent_loop_inserts_pre_messages_before_main_request -v
```

Expected: FAIL — `run_agent_loop` does not accept `pre_messages` yet.

- [ ] **Step 3: Update `backend/src/agent/loop.py`**

Change the `run_agent_loop` signature and the `messages` list construction. Find these two sections and replace them:

**Signature** (line 218–224):
```python
async def run_agent_loop(
    run_id: uuid.UUID,
    date_range_start: str,
    date_range_end: str,
    tasks: list[str],
    analysis_mode: Literal["quick", "full"] = "quick",
    pre_messages: list[str] | None = None,
) -> None:
```

**Messages list** (find the block that starts `messages: list[dict] = [` around line 252 and replace it):
```python
        messages: list[dict] = [  # type: ignore[type-arg]
            {"role": "system", "content": build_system_prompt(analysis_mode, tasks)},
        ]
        for _pre_msg in (pre_messages or []):
            messages.append({"role": "user", "content": _pre_msg})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Analyze {date_range_start} to {date_range_end}. "
                    f"Tasks: {tasks}. Analysis mode: {analysis_mode}."
                ),
            }
        )
```

- [ ] **Step 4: Run the new test to verify it passes**

```bash
cd backend && uv run pytest tests/test_agent_loop.py::test_run_agent_loop_inserts_pre_messages_before_main_request -v
```

Expected: PASS.

- [ ] **Step 5: Run the full agent loop test suite**

```bash
cd backend && uv run pytest tests/test_agent_loop.py -v
```

Expected: ALL tests pass. In particular, verify `test_run_agent_loop_stops_if_run_already_canceled` and `test_run_agent_loop_marks_failed_when_max_iterations_exhausted` still pass — these call `run_agent_loop` without `pre_messages` and must continue to work.

- [ ] **Step 6: Run the full backend test suite**

```bash
cd backend && uv run python -m pytest
```

Expected: ALL tests pass.

- [ ] **Step 7: Run the full frontend test suite**

```bash
cd frontend && npm run test
```

Expected: ALL tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/agent/loop.py backend/tests/test_agent_loop.py
git commit -m "feat(agent): insert pre_messages between system prompt and main analysis request"
```

---

## Task 8: Final verification

- [ ] **Step 1: Run full lint + type-check**

```bash
cd backend && uv run ruff check . && uv run mypy src/ api/
cd frontend && npm run type-check && npm run lint
```

Expected: no errors (mypy may emit existing warnings unrelated to this PR — only new ones are a blocker).

- [ ] **Step 2: Run full test suite**

```bash
cd backend && uv run python -m pytest && cd ../frontend && npm run test
```

Expected: ALL tests pass in both.

- [ ] **Step 3: Confirm git log**

```bash
git log --oneline -8
```

Expected output (your run IDs will differ, order top-to-bottom newest first):
```
<hash>  feat(agent): insert pre_messages between system prompt and main analysis request
<hash>  feat(api): accept pre_messages in AnalyzeRequest and forward to agent loop
<hash>  feat(layout): render ChatPanel alongside ResultsPanel in main
<hash>  feat(topbar): add Chat toggle button and forward pre_messages on run
<hash>  feat(chat): add ChatPanel component with pre-run message queuing
<hash>  feat(api): add pre_messages field to AnalyzeRequest type
<hash>  feat(store): add chat state — chatOpen, chatMessages, pendingPreRunMessages
```
