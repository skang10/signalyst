# Run / Resume UX — Design Spec

**Date:** 2026-05-25
**Status:** Approved
**Scope:** `frontend/components/TopBar.tsx`, `frontend/lib/store.ts`

---

## Problem

After a run is canceled, the frontend calls `clearRun()`, which wipes `runId`, `messages`, and sessionStorage. The user loses all stream output and cannot inspect what happened or re-run with the same parameters. There is also no way to distinguish "idle with no prior run" from "just canceled" in the UI.

## Goal

Give the user two post-run actions instead of an implicit wipe:

| Action | Description |
|--------|-------------|
| **↩ Resume** | Reconnect the WebSocket to the existing `runId` and replay messages already in the store (no new API call). |
| **▶ New Run** | Clear the previous run and start a fresh analysis with the current form parameters. |

## Status State Machine

```
idle (no runId)
    ↓  click Run
running
    ↓  run completes          → completed
    ↓  WebSocket error/fail   → failed
    ↓  click Cancel           → canceled   ← NEW

canceled / failed / completed
    ↓  click Resume           → running   (WebSocket reconnects to same runId)
    ↓  click New Run          → idle → running  (clearRun + new api.analyze)
```

`"canceled"` is a new terminal status. `canceled`, `failed`, and `completed` are collectively "stopped" — they all show the Resume + New Run buttons.

## TopBar Button Logic

```
isRunning     = status === "running"
hasStoppedRun = status !== "running" && runId !== null

if isRunning      → [✕ Cancel]
if hasStoppedRun  → [↩ Resume] [▶ New Run]
else              → [▶ Run]
```

`hasStoppedRun` covers four cases:
- `status = "canceled"` — user clicked Cancel
- `status = "failed"` — WebSocket/backend error
- `status = "completed"` — run finished
- `status = "idle"` with `runId` set — page refresh during or after a run (sessionStorage recovery)

## Store Changes (`store.ts`)

### New type additions

```ts
type StoreStatus = "idle" | "running" | "completed" | "failed" | "canceled";

type LastRunParams = {
  date_range_start: string;
  date_range_end: string;
  analysis_mode: "quick" | "full";
};
```

### New field: `lastRunParams`

```ts
lastRunParams: LastRunParams | null;
```

Populated by `setRun()`. Used by the TopBar so New Run can re-submit with the same parameters if the user hasn't changed the form. (Note: the TopBar form fields are local state and already hold the values — `lastRunParams` is kept in the store primarily for future use and sessionStorage recovery.)

### New action: `setCanceled()`

```ts
setCanceled: () => void;
```

Sets `status = "canceled"`. Does **not** call `clearPersisted()` — `runId` and `messages` remain in sessionStorage so they survive a page refresh.

### Changed: `setRun(runId, params)`

Signature extends to accept `params: LastRunParams` as a second argument. Saves to `lastRunParams`. Existing behaviour (persist runId, clear messages, set `status = "running"`) is unchanged.

### Changed: `setError(error)`

Keeps `runId` in the store (does not call `clearPersisted()`). Sets `status = "failed"`. Mirrors `setCanceled` so failed runs also show Resume + New Run buttons and messages are preserved for inspection.

### Unchanged: `clearRun()`

Full reset. Clears runId, messages, result, error, lastRunParams, and sessionStorage. Called only by the New Run action.

## TopBar Changes (`TopBar.tsx`)

### `handleCancel`

```ts
const handleCancel = async () => {
  if (!runId) return;
  try {
    await api.cancelRun(runId);
  } finally {
    setCanceled();           // was: clearRun()
  }
};
```

### `handleRun` (New Run)

```ts
const handleRun = async () => {
  setTopbarError(null);
  try {
    const { run_id } = await api.analyze({ date_range_start: start, date_range_end: end, analysis_mode: mode });
    setRun(run_id, { date_range_start: start, date_range_end: end, analysis_mode: mode });
  } catch (e) {
    setTopbarError(e instanceof Error ? e.message : "Failed to start analysis");
  }
};
```

`clearRun()` is not called here. `setRun()` already resets `messages`, `result`, `error`, and `status` to `"running"`, and updates sessionStorage. Calling `clearRun()` before the API call would erase the previous run's output if the API fails, leaving the user with nothing to inspect.

### `handleResume` (new)

```ts
const handleResume = () => {
  setStatus("running");     // causes useRunStream to reconnect WebSocket to existing runId
};
```

The WebSocket hook `useRunStream(runId)` already reconnects when `runId` is present. By setting `status = "running"`, any component that gates on status will re-enter the streaming view. If the backend run is already terminal, the WebSocket receives no new events and the existing store messages remain visible.

### Status badge

A small inline badge appears next to the buttons in State 3 to communicate why two buttons are showing:

```
● Canceled    (orange)
● Failed      (red)
● Completed   (green)
```

Badge is omitted in the `"idle"` + runId case (page refresh) since the status is ambiguous without a backend check.

## What Resume Does NOT Do

- It does not make a new `POST /api/analyze` call.
- It does not fetch or re-fetch run results from the backend.
- It does not clear or replace existing messages.
- It does not attempt to validate that the backend run is still alive.

## Files Affected

| File | Change |
|------|--------|
| `frontend/lib/store.ts` | Add `"canceled"` status, `lastRunParams`, `setCanceled()`. Update `setRun()` signature, `setError()` behaviour. |
| `frontend/components/TopBar.tsx` | Replace `clearRun()` in `handleCancel` with `setCanceled()`. Add `handleResume`. Update button render logic. Add status badge. |

## Out of Scope

- Backend changes — none required.
- Persisting `lastRunParams` to sessionStorage — the form fields already hold the values locally.
- Showing a "resume" prompt automatically on page refresh — the `hasStoppedRun` condition already handles this.
- Fetching live run status from the backend on resume (could be a future enhancement).
