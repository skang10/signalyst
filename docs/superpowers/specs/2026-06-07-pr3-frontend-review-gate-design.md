# PR 3-Frontend: FeaturizerConfigEditor & UserReviewGate Design

**Date:** 2026-06-07
**Branch:** main

## Problem

Per `frontend-redesign.md`, PR 3-frontend's scope was "live activity feed with WebSocket streaming, USER_REVIEW gate message, FeaturizerConfigEditor, chat input wired to `POST /chat`." The feed, streaming, layout, and chat input already landed as part of the unified-activity-chat work (`activity/page.tsx`, `lib/websocket.ts`, `lib/activity-groups.ts`). What's left is the gate itself: today `RunAnalysisChip` (`activity/page.tsx:328`) is a bare pill button. Users can inspect the data summary (via `DataCompletionChip`) but have no way to see or adjust `featurizer_config` before `POST /proceed` kicks off `FEATURIZING` — their only options are "accept the agent's defaults" or "describe the change in free text and hope `ReviewInterpreter` parses it correctly."

## Goal

Replace `RunAnalysisChip` with a `UserReviewGate` card containing an inline `FeaturizerConfigEditor` (editable tags for `windows`, `lags`, `feature_families`, `energy_specific`). Submitting a config change should be deterministic — no LLM round-trip — while the existing free-text path (`POST /chat` → `ReviewInterpreter`) remains available for ambiguous requests ("add a data source", "what's PSI?").

---

## Design

### 1. Submission path: extend `POST /proceed`, not a two-step flow

Two options were considered for getting edited config to the backend:

- **(a)** Route structured edits through `POST /chat`, letting `ReviewInterpreter` (an LLM call) translate "the user changed windows to [5, 30, 90]" into a `featurizer_config` patch.
- **(b)** Extend `POST /proceed` to accept an optional `featurizer_config_patch`, applied directly — no LLM in the loop for structured edits.

**(b) is the right choice and mirrors an existing pattern.** `POST /rerun` (`backend/api/routes/pipeline.py:386`) already accepts `featurizer_config_patch: dict[str, object] | None` and merges it with `s.featurizer_config = {**s.featurizer_config, **req.featurizer_config_patch}` before transitioning (`pipeline.py:405-406`). `POST /proceed` gets the identical treatment — same `RerunRequest`-shaped optional field, same merge, applied just before `transition_stage(s, SessionStage.FEATURIZING)` at `pipeline.py:371`. `ReviewInterpreter` stays exactly as-is for natural-language chat; it is never asked to parse structured tag edits.

### 2. FeaturizerConfigEditor — local draft state

A new component, `components/FeaturizerConfigEditor.tsx`, renders the four editable rows described in `frontend-redesign.md:122-126` (windows tags, lags tags, feature-family toggle tags, `energy_specific` toggle). It is a controlled component:

```ts
type Props = {
  value: FeaturizerConfig;          // current draft
  onChange: (next: FeaturizerConfig) => void;
};
```

`UserReviewGate` owns the draft state, seeded once from `useSessionStore().featurizerConfig` (already present at `lib/store.ts:21`) when the gate first mounts for a given `sessionId`. The draft is **plain local React state** — it never writes back to the store. Tag add/remove/toggle interactions mutate the draft via `onChange`; no network calls happen until the user explicitly acts.

`isDirty` is computed as a shallow comparison: `!arraysEqual(draft.windows, server.windows) || !arraysEqual(draft.lags, server.lags) || !arraysEqual(draft.feature_families, server.feature_families) || draft.energy_specific !== server.energy_specific`.

### 3. UserReviewGate — replacing RunAnalysisChip

`components/GateMessage.tsx` (per `frontend-redesign.md:272`) houses `UserReviewGate` (the FOLLOW_UP variant is a separate concern, out of scope here — see below). It renders in the same slot `RunAnalysisChip` occupies today, inside the scrollable feed (`activity/page.tsx:452-454`), gated by the same `showRunAnalysis` condition. Layout, top to bottom:

- `FeaturizerConfigEditor` (draft state as above)
- A dirty banner — shown only when `isDirty` — reading "Config changed — Run Analysis to apply, or Discard" with a "Discard" action that resets the draft to `server`
- Action row: chat input enable/disable state (see §4) is reflected by the surrounding `activity/page.tsx` input bar, not duplicated here; the gate itself contributes the **"Run Analysis →"** button

The existing `proceeding` / `proceedError` state and `handleProceed` callback in `activity/page.tsx` are reused, with `handleProceed` extended to pass the patch (or `undefined` when clean):

```ts
const handleProceed = async () => {
  ...
  await api.proceed(sessionId, isDirty ? draft : undefined);
  ...
};
```

The backend merge is a shallow spread (`{**s.featurizer_config, **patch}`), so sending the full draft as the patch is equivalent to sending only the changed fields — no diffing helper needed. When the draft is clean, no body is sent at all, which is the existing no-arg `POST /proceed` behavior.

### 4. The chat/editor boundary — preventing silent loss of edits

This is the crux of the dual-path design: the editor's draft is **local** React state while the chat path drives **server** state through `ReviewInterpreter`. Two paths writing to the same logical value (`featurizer_config`) from different layers creates exactly one dangerous interleaving:

> User edits `windows` to `[5, 30, 90]` in the editor (draft now dirty), then types "looks good, run it" in chat. `ReviewInterpreter` returns `advance` → `FEATURIZING` starts from the **server's** `featurizer_config` (still `[5, 20, 60]`). The user's edits vanish without any error.

**Resolution: the chat send button is disabled whenever `isDirty` is true.** This makes the two paths mutually exclusive by construction — at any instant either (a) the draft matches the server and both "Run Analysis →" and chat-send are live, or (b) the draft is dirty and only "Run Analysis →" / "Discard" are live. `activity/page.tsx`'s existing `inputDisabled` expression gains one term:

```ts
const inputDisabled = sending || status !== "waiting" || (stage === "user_review" && isDirty);
```

The placeholder text switches to "Config changes pending — Run Analysis or Discard to continue chatting" when this is the active reason for disabling. `isDirty` needs to be lifted from `UserReviewGate` to the page (or read from a small shared hook) so both the input bar and the gate card can react to it — this is the one piece of state that crosses the component boundary, and it's a single boolean.

A second interleaving — `ReviewInterpreter` returns `update_config` and the server-side `featurizer_config` changes while the draft is dirty — cannot occur once the above holds: chat is only reachable when the draft is clean, so `update_config` always rehydrates into a draft that has nothing to lose.

### 5. Backend change

`backend/api/routes/pipeline.py::proceed` (line 330) gains a request body, mirroring `rerun`:

```python
class ProceedRequest(BaseModel):
    featurizer_config_patch: dict[str, object] | None = None
```

(FastAPI route bodies are optional by default when the model has no required fields, so existing callers sending no body keep working.) Inside the handler, immediately before `transition_stage(s, SessionStage.FEATURIZING)` (`pipeline.py:371`):

```python
if req.featurizer_config_patch:
    s.featurizer_config = {**s.featurizer_config, **req.featurizer_config_patch}
```

`api.proceed` in `lib/api.ts:170-171` gains an optional second argument and sends a JSON body when present — same shape as `api.rerun` (`lib/api.ts:190-201`).

---

## Component Map

| File | Change |
|---|---|
| `frontend/components/FeaturizerConfigEditor.tsx` | New — controlled editable-tags editor for `windows` / `lags` / `feature_families` / `energy_specific` |
| `frontend/components/GateMessage.tsx` | New — houses `UserReviewGate` (USER_REVIEW variant; FOLLOW_UP variant out of scope) |
| `frontend/app/sessions/[id]/activity/page.tsx` | Replace `RunAnalysisChip` with `UserReviewGate`; lift `isDirty` so the input bar can disable chat-send; extend `handleProceed` to pass an optional patch |
| `frontend/lib/api.ts` | `proceed(sessionId, featurizerConfigPatch?)` sends optional JSON body |
| `backend/api/models.py` | New `ProceedRequest` (mirrors `RerunRequest`) |
| `backend/api/routes/pipeline.py` | `proceed` handler accepts `req: ProceedRequest`, merges patch before transition (mirrors `rerun` lines 404-406) |

`RunAnalysisChip` (`activity/page.tsx:328-346`) is deleted once `UserReviewGate` replaces its render site.

---

## Out of Scope

- FOLLOW_UP gate card variant (separate `frontend-redesign.md:134-141` concern; `GateMessage.tsx` will need it eventually but it has no config editor and no dirty-state question)
- Any backend validation of patch *values* (e.g. rejecting `windows: []`) — `TimeSeriesFeaturizer` already validates at run time and surfaces errors through the existing `error` event path
- Persisting/restoring an in-progress draft across page reloads — the draft is ephemeral; reloading re-seeds from server state
- Feature-count estimate (`≈ 187 features planned`, `frontend-redesign.md:126`) — deferred; requires a feature-count formula that doesn't yet exist in `TimeSeriesFeaturizer`
