# Chat Window PR 2 — Post-Run Continuation Design

**Date:** 2026-05-31
**Branch:** `feat/chat-window-pr2`

---

## Goal

After a run completes, allow the user to send a follow-up message from the chat panel. The agent resumes with the previous result as context, decides whether to explain (no tools, fast) or act (tool calls, data changes), and returns a response that appears as an agent bubble in the chat panel.

---

## Use Cases

| Message | Agent behaviour |
|---|---|
| "Why is drift elevated?" | Reads previous drift scores from context, explains directly — no tool calls |
| "Explain the regime classification" | Reads previous regime result from context, explains — no tool calls |
| "Add Baker Hughes rig count data" | Calls connector authoring tools, re-fetches data, re-analyzes |
| "What are the top features driving this?" | Reads feature importance from context, explains — no tool calls |

---

## Architecture

A new `POST /api/runs/{run_id}/continue` endpoint creates a **new run** (new `run_id`) each time. No status regression — runs only move forward. Context for the new run is reconstructed from the previous `Run.result` already stored in the DB; the full LLM message history does not need to be stored.

The frontend detects the new `run_id`, the store transitions to `running`, and the WebSocket hook reconnects automatically to the new run's channel. When `done` arrives and `chatMessages` is non-empty, the summary is added as an agent bubble.

---

## Backend

### New endpoint: `POST /api/runs/{run_id}/continue`

**File:** `backend/api/routes/analyze.py`

Request:
```json
{ "message": "Why is drift elevated?" }
```

Response:
```json
{ "run_id": "<new_uuid>" }
```

Logic:
1. Load source `Run` from DB. Return `404` if not found, `409` if not `COMPLETED`.
2. Format `Run.result` as a structured context string (see below).
3. Create a new `Run` record (same `date_range_start`, `date_range_end`, `tasks` as source run).
4. Build `messages` list: `[system_prompt, context_message, user_message]`.
5. Commit new run, start `run_agent_continuation` as a background task.
6. Return `{ "run_id": str(new_run.id) }`.

**Context message format** (role: `"user"`):
```
Previous analysis result (2023-01-01 to 2023-06-30):
Regime: range_bound (confidence 0.82)
Direction: up (confidence 0.71)
Drift detected: True, PSI score 0.23, drifted features: CL=F_roc_20d, gpr_level_60d
Top features: CL=F_roc_20d (0.18), CL=F_mom_20d (0.14)
Summary: <previous summary text>
```

Fields present only when available (drift, features may be None for quick runs without backtest).

### New function: `run_agent_continuation`

**File:** `backend/src/agent/loop.py`

```python
async def run_agent_continuation(
    run_id: uuid.UUID,
    messages: list[dict],
    analysis_mode: Literal["quick", "full"] = "quick",
) -> None:
```

- Takes the pre-built `messages` list — does not rebuild from scratch.
- Runs the same ReAct loop (same `MAX_ITERATIONS`, same tool registry, same Redis publishing).
- Publishes to `run:{run_id}` channel.
- On completion: sets `Run.status = COMPLETED`, writes `Run.result`.
- Same cancel and error handling as `run_agent_loop`.

---

## Frontend

### `lib/store.ts`

Add `continueToRun(runId, params)` action — like `setRun` but preserves `chatMessages`:
```typescript
continueToRun: (runId, params) => {
  sessionStorage.setItem(RUN_ID_KEY, runId)
  set({ runId, status: "running", result: null, error: null, messages: [], lastRunParams: params })
  // chatMessages intentionally preserved — user needs to see their message and agent response
}
```

### `lib/api.ts`

Add:
```typescript
continueRun: (runId: string, message: string) =>
  request<{ run_id: string }>(`/api/runs/${runId}/continue`, {
    method: "POST",
    body: JSON.stringify({ message }),
  }),
```

### `components/ChatPanel.tsx`

**Example chips** — shown when `status === "completed"` AND `chatMessages.length === 0`:

```
Why is drift elevated?
Explain the regime classification
Add Baker Hughes rig count data
What are the top features driving this?
```

- Clicking a chip populates the textarea without auto-sending (user can edit first).
- Chips disappear once `chatMessages.length > 0` (first message sent).

**Send while completed:**
```
addChatMessage({ role: "user", content: trimmed, ... })   // 1. show user message first
const { run_id } = await api.continueRun(runId, trimmed)  // 2. start continuation
setRun(run_id, lastRunParams!)                             // 3. transition to running
```

`setRun` must NOT clear `chatMessages` on continuation — the user message added in step 1 must survive so `AgentStream` can detect `chatMessages.length > 0` and so the user can see what they sent. `setRun` already clears `chatMessages` for fresh runs (called from `handleRun`); for continuation we call a new store action `continueToRun(runId, params)` that transitions status and runId but preserves `chatMessages`.

**Input state** — no change from PR 1:
- `completed` → enabled, placeholder "Ask a follow-up question…"
- `running` → disabled

### `components/AgentStream.tsx`

When the `done` event arrives and `chatMessages.length > 0`, add the agent's summary to the chat panel:

```typescript
if (last?.type === "done" && chatMessages.length > 0) {
  addChatMessage({
    id: crypto.randomUUID(),
    role: "agent",
    content: last.summary,
    timestamp: Date.now(),
  })
}
```

This condition fires on continuation runs (where the user sent a follow-up) but not on fresh runs (where `setRun` cleared `chatMessages` before the run started).

---

## Data Flow

```
User sends follow-up in ChatPanel (status=completed)
  → api.continueRun(runId, message)
  → POST /api/runs/{runId}/continue
  → Backend: load Run.result, format context, create new Run, start run_agent_continuation
  → { run_id: newRunId }
  → addChatMessage (user bubble already added before API call)
  → continueToRun(newRunId, lastRunParams) → status=running, chatMessages preserved, WS reconnects
  → run_agent_continuation publishes to run:{newRunId}
  → AgentStream receives thoughts/tool_calls/done
  → on done: addChatMessage({ role: "agent", content: summary })
  → api.getRun(newRunId) → setResult() → ResultsPanel updates
  → status=completed, new example chips hidden (chatMessages.length > 0)
```

---

## Error Handling

- `continueRun` API error → `setTopbarError` (reuse existing pattern) — user sees the error, status stays `completed`
- `run_agent_continuation` failure → `Run.status = FAILED`, WS publishes `phase: failed` → `AgentStream` calls `setError()`
- Source run not found → `404` returned, frontend shows error

---

## Out of Scope

- Streaming agent thoughts into the chat panel (PR 3)
- Dynamic example chips derived from actual run results
- Storing full LLM message history
- Conversation threading across more than one continuation
