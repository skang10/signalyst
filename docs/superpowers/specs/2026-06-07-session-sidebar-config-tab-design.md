# Session Sidebar Nav + Config Tab — Design

## Goal

Replace the session detail page's horizontal Activity/Data/Results tab row with a vertical
sidebar (Codex-Settings style), and add a new **Config** tab so users can always view —
and, during review, edit — the session's `featurizer_config` without needing to be in the
USER_REVIEW chat gate.

## 1. Sidebar navigation

`app/sessions/[id]/layout.tsx` currently renders `TABS` as a horizontal row of links below
the `StageStrip`. Replace that row with a new `SessionSidebar` component rendered inside a
bordered "boxed panel" (matches the visual direction approved during brainstorming — a
settings-style card, not a full-height edge-to-edge sidebar):

- Header, session-id bar, `StageStrip`, and `ReviewBanner` stay exactly as they are today,
  full width, above the panel.
- Below them, a bordered card (`border border-[#21262d] rounded-lg`) contains a flex row:
  a fixed-width vertical nav on the left (`Activity`, `Data`, `Config`, `Results`) and the
  page content on the right.
- Nav items reuse the existing active/locked/badge logic verbatim — only the rendering
  changes from horizontal `border-b` underline to vertical highlighted rows
  (`bg-[#1f2937] text-[#60a5fa]` for active, `text-[#9ca3af]` inactive,
  `text-[#374151] cursor-not-allowed` + lock icon + tooltip for locked).
- `Config` is **never locked** — `featurizer_config` exists from session creation
  (seeded from `MarketProfile.default_featurizer_config`), so it's always viewable.

`TABS` becomes:

```ts
const TABS = [
  { label: "Activity", path: "activity" },
  { label: "Data", path: "data" },
  { label: "Config", path: "config" },
  { label: "Results", path: "results" },
];
```

`isLocked`/`badge` logic stays the same — `Config` simply never matches a locked condition.

## 2. Config tab (`app/sessions/[id]/config/page.tsx`)

New page, mounted at `/sessions/[id]/config`. Renders `FeaturizerConfigEditor` in one of two
modes depending on `stage`:

**`stage === "user_review"` — editable, auto-saving**
- Renders `FeaturizerConfigEditor` bound directly to `featurizerConfig` from the store.
- Each `onChange` (add/remove a window or lag, toggle a family, flip the energy-specific
  checkbox) immediately calls a new `api.updateConfig(sessionId, patch)`. No separate
  "Save" button or dirty-state banner — this is a settings-page auto-save pattern, distinct
  from the Activity gate's draft-then-"Run Analysis" flow.
- Shows a small inline status next to the editor: `Saving…` while the request is in
  flight, `✓ Saved` on success (auto-clears after a couple seconds), or
  `Failed to save — retry` with a retry affordance on error.
- On success, refetches the session (`api.getSession` → `setSession`) so the store's
  `featurizerConfig` — and therefore the Activity gate's `serverConfig` — reflects the
  saved value. (This relies on the `UserReviewGate` resync fix from PR #36, which already
  re-derives its draft from `serverConfig` when it changes.)
- "Run Analysis" remains exclusively in the Activity gate — this page never starts the
  pipeline, by construction (it only ever calls `updateConfig`, never `proceed`).

**Any other stage — read-only**
- Renders `FeaturizerConfigEditor` in a new `readOnly` mode (see below) bound to
  `featurizerConfig`.
- Shows a small note explaining why it's locked, e.g. "Editable only during the review
  step."

### `FeaturizerConfigEditor` `readOnly` prop

Add an optional `readOnly?: boolean` prop (default `false`). When `true`:
- `NumberRow` hides the `×` remove buttons and the `+ add` input; pills render with the
  inactive/dimmed style (`border-[#374151] text-[#9ca3af]`, no hover, no `onClick`).
- The family toggle buttons and the energy-specific checkbox become inert
  (`pointer-events-none`, dimmed, `disabled` on the checkbox).
- `onChange` is never called in this mode — the prop can be omitted by read-only callers.

This reuses the existing pill-based visual language (approved during brainstorming) instead
of building a separate read-only summary view, keeping the two presentations visually
consistent.

## 3. Backend: `PATCH /api/sessions/{session_id}/config`

New endpoint in `backend/api/routes/pipeline.py` (alongside `proceed`/`rerun`, which already
own `featurizer_config_patch` handling):

- Request body: `{"featurizer_config_patch": {...}}`
- Returns `{"session_id": "..."}`  with `200 OK` (no stage/status change, so `202 Accepted`
  — which signals "background work started" elsewhere in this API — would be misleading)
- **Guard:** only allowed when `s.stage == SessionStage.USER_REVIEW`; otherwise `409` with
  `detail="config can only be edited during user_review"` — matches "read-only outside
  review" and gives the frontend a clear signal if the stage changes mid-edit (e.g. via a
  concurrent chat "advance").
- Filters the patch to the four valid keys and merges into `s.featurizer_config`, then
  commits. **No** stage/status change, **no** `background_tasks.add_task` — by construction
  this can never start the pipeline, mirroring the deterministic guard already established
  for `update_config` in `chat.py`.

### Shared patch-filter helper

`chat.py` (the `update_config` chat action) and this new endpoint both need to "filter to
valid keys, then merge." Extract the existing inline filter from `chat.py` into a small
shared helper, e.g.:

```python
# backend/src/services/featurizer_config.py
_VALID_PATCH_KEYS = {"windows", "lags", "feature_families", "energy_specific"}

def apply_config_patch(current: dict[str, Any], raw_patch: dict[str, Any]) -> dict[str, Any]:
    patch = {k: v for k, v in raw_patch.items() if k in _VALID_PATCH_KEYS}
    return {**current, **patch}
```

Both `chat.py`'s `update_config` branch and the new `PATCH /config` endpoint call this
helper instead of duplicating the filter set and merge expression.

### Frontend API client

`frontend/lib/api.ts` gains:

```ts
updateConfig: (sessionId: string, patch: Partial<FeaturizerConfig>) =>
  request<{ session_id: string }>(`/api/sessions/${sessionId}/config`, {
    method: "PATCH",
    body: JSON.stringify({ featurizer_config_patch: patch }),
  }),
```

(Mirrors the existing `proceed`/`rerun` request helpers in shape and error handling.)

## Out of scope

- No changes to the Activity gate's existing draft/dirty/"Run Analysis" flow.
- No changes to `StageStrip`, `ReviewBanner`, header, or session-id bar.
- No debounce on auto-save — edits are discrete user actions (button clicks / Enter to
  commit a number), not continuous typing, so each edit firing its own request is simple
  and sufficient (YAGNI).
- No "undo" for auto-saved edits — the existing chat-driven `update_config` path already
  lets users restate a setting in natural language if they change their mind, and the
  config remains editable for the whole USER_REVIEW stage.
