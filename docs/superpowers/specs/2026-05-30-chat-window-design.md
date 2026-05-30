# Chat Window — Design Spec

**Session:** 9
**Branch:** `feat/agent-connector-authoring`
**Date:** 2026-05-30

---

## Goal

Give users a persistent chat interface to interact with the agent — before a run starts, during a run, and after it completes. This unlocks the connector authoring flow: a non-technical user can type "add Baker Hughes rig count data" and the agent writes the connector, tests it, and continues the analysis without developer involvement.

---

## Layout

A **collapsible right panel** toggled from the TopBar. Closed by default — results stay full-width. When opened, the results panel compresses but remains visible. A close button (✕) or the same toggle dismisses it.

```
┌─────────────────────────────────────────────────────────────┐
│  TopBar          ● Completed          [💬 Chat]             │
├───┬─────────────────────────────────┬─────────────────────  │
│ ← │                                 │  Chat              ✕  │
│   │   Results Panel                 │  ─────────────────    │
│   │   (compressed but visible)      │  User: Add Baker...   │
│   │                                 │  Agent: Written ✓     │
│   │                                 │  ─────────────────    │
│   │                                 │  [Ask the agent…] [↑] │
└───┴─────────────────────────────────┴───────────────────────┘
```

When the panel is closed, the TopBar toggle is the only entry point — no persistent bottom bar. This keeps the default view clean.

---

## Delivery: Three Independent PRs

This feature is too large for a single PR. Each sub-project ships independently and builds on the previous:

| PR | Focus | Backend changes | Frontend changes |
|----|-------|-----------------|------------------|
| 1 | Chat panel UI + pre-run messages | Minor (accept `pre_messages` in analyze request) | New `ChatPanel` component, toggle in TopBar |
| 2 | Post-run continuation | New `POST /api/runs/{run_id}/continue` endpoint | Wire "continue" call after completion |
| 3 | Bidirectional WS + mid-run injection | WS handler receives messages, loop polls Redis | Send messages over open WS connection |

---

## PR 1 — Frontend Chat Panel

### What it does

Adds the collapsible right chat panel. Users can type messages before a run starts; those messages are passed to the agent as part of the initial context. During a run the input is disabled with a note ("message will be sent after this step"). After a run, input is re-enabled but sends no-op until PR 2 lands.

### Components

**`components/ChatPanel.tsx`**
- Collapsible right panel (width ~280px when open)
- Chat history: user messages (right-aligned, indigo bubble) + agent responses (left-aligned, dark bubble with avatar)
- Input bar at the bottom of the panel with Send button
- State: `open: boolean`, `messages: ChatMessage[]`, `pendingInput: string`

**`components/TopBar.tsx`** — add a `💬 Chat` toggle button that sets `chatOpen` in the store

**`lib/store.ts`** — add `chatOpen`, `chatMessages`, `pendingPreRunMessages` to `useRunStore`

### Pre-run message flow

1. User opens chat panel before clicking Run
2. Types a message (e.g. "Also pull Baker Hughes rig count")
3. Message is stored in `pendingPreRunMessages` in the store
4. On `POST /api/analyze`, `pre_messages` field is included in the request body
5. Backend appends pre-run messages to the initial `messages` list before the first LLM call
6. Agent sees them as user context and acts accordingly

### Backend change (minor)

`AnalyzeRequest` gains an optional field:
```python
pre_messages: list[str] = []
```

In `run_agent_loop`, prepend pre-messages to the conversation after the system prompt:
```python
for msg in pre_messages:
    messages.append({"role": "user", "content": msg})
```

### Input states

| Run state | Input state | Placeholder text |
|-----------|-------------|------------------|
| idle | enabled | "Ask the agent — add a connector, set context…" |
| running | disabled | "Agent is working — message will be queued" |
| completed | enabled (no-op until PR 2) | "Ask a follow-up question…" |
| failed / canceled | disabled | "Run ended" |

---

## PR 2 — Post-Run Continuation

### What it does

After a run completes, the user can send a follow-up message. The agent resumes with the full conversation history plus the new message, runs additional tool calls if needed, and produces a new summary. The run transitions COMPLETED → RUNNING → COMPLETED.

### Backend

**New endpoint:** `POST /api/runs/{run_id}/continue`

Request body:
```json
{ "message": "Why is drift elevated?" }
```

Response:
```json
{ "run_id": "..." }
```

The endpoint:
1. Loads the existing `Run` from DB, reads `Run.result` to reconstruct conversation context
2. Appends the user message to the message history
3. Resets `Run.status = RUNNING`
4. Starts a new background task: `run_agent_continuation(run_id, history, new_message)`
5. Returns immediately — client listens on the existing WS stream for new events

**`run_agent_continuation`** is a simplified version of `run_agent_loop` that:
- Starts with the reconstructed message history instead of system prompt + user request
- Runs the same tool loop (up to `MAX_ITERATIONS`)
- Publishes to the same Redis channel `run:{run_id}` — the WS stream re-activates

### Frontend

When run status is `completed` and user sends a chat message:
1. `POST /api/runs/{run_id}/continue` with the message
2. Store status transitions back to `running`
3. Chat panel shows the message as sent; WS stream reactivates and shows agent response
4. On completion: status returns to `completed`, new result appended to chat history

### Persisting conversation history

`Run.result` already stores `summary`. To support continuation, add a `messages` field to `Run.result` that captures the final message history. `run_agent_continuation` reads this to reconstruct the conversation.

---

## PR 3 — Bidirectional WebSocket + Mid-Run Injection

### What it does

The WebSocket connection becomes two-way. While a run is live, the user can send a message that the agent processes at the next natural pause (between tool calls). This enables the primary use case: user says "add Baker Hughes data" mid-analysis and the agent writes the connector, tests it, then continues.

### Backend

**`api/ws.py`** — extend the handler to receive client messages:

```python
# Currently: subscribe to Redis, forward to client
# New: also receive from client, publish to Redis chat channel

async for msg in websocket.iter_json():
    await redis_client.rpush(f"chat:{run_id}", json.dumps(msg))
```

**`src/agent/loop.py`** — poll the chat queue between iterations:

```python
# After processing tool results, before next LLM call:
pending = await redis_client.lpop(f"chat:{run_id}")
if pending:
    user_msg = json.loads(pending)
    messages.append({"role": "user", "content": user_msg["content"]})
    await _publish(redis_client, channel, {
        "type": "user_message", "content": user_msg["content"]
    })
```

### Frontend

When run status is `running` and user sends a message:
1. Instead of HTTP, send over the open WebSocket: `ws.send(JSON.stringify({type: "user_message", content: "..."}))`
2. Chat panel shows the message immediately as optimistic UI
3. Agent picks it up at the next iteration; response arrives via WS stream as `thought` + `tool_call` events

### Mid-run input state

During a run, the input is **enabled** (changed from PR 1's disabled state). Placeholder: "Send a message — agent will act at the next step."

### WebSocket message format (client → server)

```json
{ "type": "user_message", "content": "Add Baker Hughes rig count data" }
```

---

## Chat Message Types

### Display in ChatPanel

| Event type | Who | Display |
|------------|-----|---------|
| User typed message | User | Right-aligned indigo bubble |
| `thought` | Agent | Left-aligned dark bubble, italic |
| `tool_call` + `tool_result` | Agent | Inline pill: `⚙ write_connector ✓` |
| `done` summary | Agent | Left-aligned dark bubble, full summary text |
| `error` | System | Red inline notice |

Tool calls are collapsed by default — just a pill showing the tool name and pass/fail. The full tool input/output remains visible in the AgentDrawer's thought stream.

---

## State Management

`useRunStore` additions:

```typescript
chatOpen: boolean
chatMessages: ChatMessage[]          // displayed in panel
pendingPreRunMessages: string[]      // queued before run starts
setChatOpen: (open: boolean) => void
addChatMessage: (msg: ChatMessage) => void
queuePreRunMessage: (msg: string) => void
clearPreRunMessages: () => void
```

```typescript
type ChatMessage = {
  id: string
  role: "user" | "agent"
  content: string
  timestamp: number
  toolPill?: { name: string; status: "running" | "done" | "failed" }
}
```

---

## Out of Scope

- Message editing or deletion
- Chat history persisted across browser sessions (sessionStorage only, like run state)
- Multi-turn conversation outside of a run (standalone chat without analysis context)
- Agent-initiated messages (agent proactively asking the user a question)
- Rate limiting or abuse prevention on the chat endpoint
