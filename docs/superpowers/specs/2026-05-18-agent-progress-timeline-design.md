# Agent Progress Timeline — Design Spec

**Date:** 2026-05-18
**Scope:** Replace `AgentStreamView` with a vertical timeline component that renders the agent's 9 phases in human-readable form, replacing raw tool names with named steps, evidence chips, and live thought sub-text.

---

## Problem

The current `AgentStreamView` renders raw WebSocket events as a log: tool names like `run_tabpfn` and `fetch_data` appear directly, which is ambiguous and doesn't convey meaningful progress to the user.

---

## Goal

Replace the agent process panel (left pane) with a vertical timeline that shows:
- All 9 named phases upfront, greyed out until reached
- The active phase highlighted with the agent's current thought and an optional progress bar
- Completed phases collapsed to a checkmark + evidence chips (brief, human-readable summary of what was found)

---

## Architecture

### Files changed

| Action | File | Reason |
|--------|------|---------|
| Delete | `frontend/components/AgentStreamView.tsx` | Replaced entirely |
| Delete | `frontend/components/__tests__/AgentStreamView.test.tsx` | Tests replaced |
| Create | `frontend/components/AgentProgressTimeline.tsx` | New presentational component |
| Create | `frontend/components/__tests__/AgentProgressTimeline.test.tsx` | New tests |
| Modify | `frontend/components/AgentStream.tsx` | Call `buildAgentProgress(messages)`, pass result to timeline |

No other files change. `buildAgentProgress()` in `lib/agentProgress.ts` already derives all phase state from the message stream — the new component is purely a rendering layer on top of it.

### Data flow

```
useRunStream(runId)          → messages: StreamMessage[]
buildAgentProgress(messages) → AgentProgressState { phases, tabpfn }
AgentProgressTimeline        → renders phases as vertical timeline
```

`AgentProgressState` already contains everything needed:
- `phases[].status` — `"waiting" | "running" | "done" | "failed" | "canceled"`
- `phases[].title` — human-readable name (e.g. "Predicting regime")
- `phases[].notes` — agent thoughts (strings ≤ 160 chars), most recent shown when running
- `phases[].evidence` — `{ label, value, tone }` chips shown when done
- `phases[].progress` — `{ completed, total, unknownTotal }` for progress bar when running

---

## Component: `AgentProgressTimeline`

### Props

```ts
interface Props {
  state: AgentProgressState;
  isRunning: boolean;
  connected: boolean;
}
```

### States

| Condition | Renders |
|-----------|---------|
| `!isRunning && phases all waiting` | Empty state: "Run an analysis to see the agent's reasoning." |
| `isRunning && !connected && all phases still "waiting"` | Pulsing "Connecting…" indicator |
| Running or completed | Full 9-phase vertical timeline |

### Phase rendering (per status)

| Status | Icon | Title style | Body |
|--------|------|-------------|------|
| `waiting` | Empty circle, 35% opacity | Muted grey | — |
| `running` | Pulsing violet circle + outer glow ring | Violet bold | Latest `notes[]` entry as italic grey sub-text; progress bar if `progress` is set |
| `done` | Green checkmark circle | Muted grey | Evidence chips from `evidence[]` |
| `failed` | Red ✕ circle | Red | Phase title only |
| `canceled` | Red ✕ circle | Red | Phase title only |

### Progress bar

Shown inside a running phase when `phase.progress` is set:

```
[████████████░░░░░░░░] 15 / 24
```

- Width: `(completed / total) * 100%`, capped at 100%
- If `unknownTotal` is true: show completed count only, no fraction; animate as indeterminate

### Evidence chips

Shown on a completed phase below the title:

```
[ Sources: WTI, FRED, EIA ]  [ Features: 47 ]
```

Colors by `tone`:
- `default` → slate badge (`bg-slate-800 text-slate-400`)
- `success` → green (`bg-green-950 text-green-400`)
- `accent` → violet (`bg-violet-950 text-violet-400`)
- `warning` → amber (`bg-amber-950 text-amber-400`)
- `danger` → red (`bg-red-950 text-red-400`)

### Connector line

A 2px vertical line connects each phase icon to the next. Color:
- Done→next: `bg-slate-700`
- Running→next: `bg-slate-800`
- Waiting→next: `bg-slate-900` (nearly invisible)

---

## AgentStream container changes

```tsx
// AgentStream.tsx — only change: derive progress state and pass to timeline
const progress = buildAgentProgress(messages);

return (
  <AgentProgressTimeline
    state={progress}
    isRunning={status === "running"}
    connected={connected}
  />
);
```

The `useEffect` for fetching the result on `done` stays unchanged.

---

## Error handling

| Scenario | Behaviour |
|----------|-----------|
| WS drops mid-run | `connected` prop becomes false; if phases have started, timeline stays visible — no "Connection lost" banner needed since the timeline itself shows partial progress |
| Phase `failed` / `canceled` message | Active phase icon turns red ✕; remaining waiting phases stay greyed |
| `tool_result` arrives with no parseable evidence | Phase still marks done; no chips shown (already handled by `addEvidence` in `agentProgress.ts`) |

---

## Testing

Replace `AgentStreamView.test.tsx` with `AgentProgressTimeline.test.tsx`. Tests use `buildAgentProgress()` directly to construct state, keeping tests decoupled from raw WebSocket message formats.

| Test | Asserts |
|------|---------|
| All phases waiting, not running | Empty state text shown |
| Connecting (running, not connected, no progress) | "Connecting" text shown |
| One phase running | Phase title in violet; thought sub-text visible |
| Running phase with progress | Progress bar rendered with correct count |
| Phase done with evidence | Evidence chips visible with correct labels |
| Phase failed | Red icon; remaining phases still visible |
| All phases done | All green checkmarks |

---

## Out of scope

- Redesign of the results panel (right pane)
- Redesign of TopBar
- Raw event log / debug toggle (can be added later if needed)
- Auto-scroll behaviour (phases are few and fixed in height; no scroll needed)
