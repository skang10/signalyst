# Agent Drawer Design

## Goal

Remove the left agent-progress panel and integrate a collapsible drawer into the right tab panel. The drawer auto-expands during a run and auto-collapses when the run completes, while remaining user-togglable at any time.

---

## Layout Change

`page.tsx` currently renders two equal-width sections: left = `AgentStream`, right = `ResultsPanel`. After this change it renders a single full-width `ResultsPanel`. `AgentStream` is kept as a headless component (no DOM output) so it continues to own the WebSocket subscription and the `done → fetch result` side-effect without any refactoring of that logic.

## Shared Message State

`useRunStream` must not be called from two components simultaneously (two WebSocket connections). The messages array is added to the Zustand store so `AgentStream` can write it and `AgentDrawer` can read it without a second connection.

**Store additions:**

```ts
messages: StreamMessage[];
setMessages: (msgs: StreamMessage[]) => void;
```

`StreamMessage` is the discriminated union already exported from `lib/websocket.ts`.

`AgentStream` calls `setMessages(messages)` after every render cycle where messages change.

## AgentDrawer Component

Location: `frontend/components/AgentDrawer.tsx`

### Visibility rule

The toggle button and drawer are hidden entirely when `status === "idle"`. They appear the moment a run starts.

### Auto-open / auto-close

| Status transition | Drawer state |
|---|---|
| `idle → running` | opens |
| `running → completed` | closes |
| `running → failed` | closes |
| User click on button | toggles |

Auto-open/close is implemented by a `useEffect` that watches `status`. The local `isOpen` boolean is overridden by the effect; the user's manual toggle has priority once the run is done.

### Toggle button

Rendered in the trailing slot of the `ResultsTabs` tab bar (right side, `ml-auto`):

```
◎ Agent ▾      (closed)
◎ Agent ▴      (open)
```

During a run, the `◎` icon pulses (`animate-pulse text-violet-400`). When idle, button is hidden.

### Drawer body

Two columns separated by a vertical `1px` border:

**Left — phase pipeline (horizontal):**
Renders the same phase list produced by `buildAgentProgress(messages)` as a compact horizontal strip:

```
Preparing ✓ — Features ✓ — Regime ◉ — Direction ○ — Summary ○
```

- Done phases: filled green dot + dimmed label
- Running phase: pulsing violet dot + bold violet label
- Waiting phases: empty dot + muted label
- Dots connected by 1px horizontal lines, coloured to match the earlier phase's completion state

**Right — latest thought:**
The most recent note from the currently running phase (or the last note overall if no phase is actively running). Italic, `text-slate-500`, truncated to one line with `truncate`.

### Drawer height

Fixed at approximately 56 px (compact, not scrollable). It slides in/out using `max-h` transition:
- Open: `max-h-[56px] opacity-100`
- Closed: `max-h-0 opacity-0 overflow-hidden`

Transition duration: 200 ms ease-in-out.

## ResultsTabs Integration

`ResultsTabs.tsx` renders in this order:

1. Icon sidebar (existing, unchanged)
2. Right column:
   a. Tab bar with the Agent toggle button appended at trailing end
   b. `<AgentDrawer />` (zero height when collapsed, 56 px when open)
   c. Tab content (existing)

`AgentDrawer` reads from the store directly — no props needed.

## Files Modified / Created

| File | Action |
|---|---|
| `frontend/lib/store.ts` | Add `messages`, `setMessages` |
| `frontend/lib/websocket.ts` | Export `RunEvent` type (already internal, just export it) |
| `frontend/components/AgentStream.tsx` | Call `setMessages`; return `null` |
| `frontend/app/page.tsx` | Remove left section; keep headless `<AgentStream />` |
| `frontend/components/ResultsTabs.tsx` | Add Agent toggle button + `<AgentDrawer />` |
| `frontend/components/AgentDrawer.tsx` | New component |

## Files Deleted / Retired

`AgentProgressTimeline.tsx` — no longer rendered anywhere after this change. It can be deleted.
`AgentStream.tsx` continues to exist as the headless orchestrator but its visual output is gone.

## Testing

- `AgentDrawer.test.tsx`: unit tests covering idle (button hidden), running (button visible + open), completed (button visible + closed), and manual toggle.
- `ResultsTabs.test.tsx`: verify drawer mounts inside the tab panel.
- `page.test.tsx` (if it exists): verify single-section layout.
- Existing tests for `AgentStream`, `AgentProgressTimeline` (if kept), and `ResultsPanel` must continue to pass.

## Out of Scope

- Redesigning the thought-stream content itself (content stays the same as current `AgentProgressTimeline`)
- Persisting open/closed preference across sessions
- Animated phase-dot transitions beyond simple pulse
