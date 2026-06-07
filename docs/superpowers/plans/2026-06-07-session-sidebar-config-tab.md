# Session Sidebar Nav + Config Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the session detail page's horizontal Activity/Data/Results tab row with a vertical `SessionSidebar` (boxed-panel layout), and add a new always-available **Config** tab that lets users view `featurizer_config` at any stage and edit it (with auto-save) during `user_review`.

**Architecture:** A new shared backend helper `apply_config_patch` centralizes the "filter to valid keys, then merge" logic already duplicated inline in `chat.py`; a new `PATCH /api/sessions/{id}/config` endpoint reuses it behind a `stage == user_review` guard. On the frontend, `FeaturizerConfigEditor` gains a `readOnly` mode reused by both the existing review-gate (editable) and the new Config tab (editable in review / read-only otherwise), and a new `SessionSidebar` component replaces the horizontal tab row inside a bordered settings-style panel.

**Tech Stack:** FastAPI + SQLModel + pytest (backend), Next.js 15 + TypeScript + Zustand + Vitest/Testing Library (frontend).

---

## Reference: design spec

Full design at `docs/superpowers/specs/2026-06-07-session-sidebar-config-tab-design.md`. Read it before starting if anything below is ambiguous — this plan implements it section by section (§1 → Task 7, §2 → Task 6, §3 → Tasks 1–3).

## File map

- Create: `backend/src/services/featurizer_config.py` — shared `apply_config_patch` helper
- Create: `backend/tests/test_featurizer_config_service.py`
- Modify: `backend/api/routes/chat.py` — replace inline filter with shared helper
- Modify: `backend/api/models.py` — add `ConfigPatchRequest`/`ConfigPatchResponse`
- Modify: `backend/api/routes/pipeline.py` — add `PATCH /sessions/{id}/config`
- Modify: `backend/tests/test_pipeline.py` — endpoint tests
- Modify: `frontend/lib/api.ts` — add `api.updateConfig`
- Modify: `frontend/lib/__tests__/api.test.ts` — client test
- Modify: `frontend/components/FeaturizerConfigEditor.tsx` — add `readOnly` prop
- Modify: `frontend/components/__tests__/FeaturizerConfigEditor.test.tsx` — readOnly tests
- Create: `frontend/app/sessions/[id]/config/page.tsx` — new Config tab page
- Create: `frontend/components/SessionSidebar.tsx` — vertical nav
- Modify: `frontend/app/sessions/[id]/layout.tsx` — swap horizontal tabs for boxed sidebar panel

---

### Task 1: `apply_config_patch` shared helper

**Files:**
- Create: `backend/src/services/featurizer_config.py`
- Test: `backend/tests/test_featurizer_config_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_featurizer_config_service.py
from src.services.featurizer_config import apply_config_patch


def test_apply_config_patch_merges_valid_keys():
    current = {
        "windows": [5, 20, 60],
        "lags": [1, 5],
        "feature_families": ["rolling_stats"],
        "energy_specific": False,
    }
    result = apply_config_patch(current, {"windows": [7, 30, 90]})
    assert result == {**current, "windows": [7, 30, 90]}


def test_apply_config_patch_drops_unknown_keys():
    current = {"windows": [5, 20, 60]}
    result = apply_config_patch(
        current, {"rolling_windows_days": [7, 30, 90], "lags": [2, 10]}
    )
    assert result == {"windows": [5, 20, 60], "lags": [2, 10]}


def test_apply_config_patch_does_not_mutate_current():
    current = {"windows": [5, 20, 60]}
    apply_config_patch(current, {"windows": [7, 30, 90]})
    assert current == {"windows": [5, 20, 60]}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_featurizer_config_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.featurizer_config'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/src/services/featurizer_config.py
from __future__ import annotations

from typing import Any

_VALID_PATCH_KEYS = {"windows", "lags", "feature_families", "energy_specific"}


def apply_config_patch(current: dict[str, Any], raw_patch: dict[str, Any]) -> dict[str, Any]:
    patch = {k: v for k, v in raw_patch.items() if k in _VALID_PATCH_KEYS}
    return {**current, **patch}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_featurizer_config_service.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/featurizer_config.py backend/tests/test_featurizer_config_service.py
git commit -m "feat: add apply_config_patch helper for filtering+merging featurizer config patches"
```

---

### Task 2: Refactor `chat.py`'s `update_config` branch onto the shared helper

**Files:**
- Modify: `backend/api/routes/chat.py:13-29` (imports + constant), `backend/api/routes/chat.py:182-184` (branch body)

This is a pure refactor — the existing chat tests already cover the behavior (`test_chat_update_config_action_patches_config_and_stays_in_user_review`, `test_chat_update_config_action_drops_unknown_patch_keys`). No new test needed; they must keep passing.

- [ ] **Step 1: Run the existing chat tests to confirm the baseline (they should currently pass)**

Run: `cd backend && uv run pytest tests/test_chat.py -v`
Expected: all tests pass (14 passed)

- [ ] **Step 2: Replace the inline filter with the shared helper**

In `backend/api/routes/chat.py`, add the import alongside the existing `src.*` imports (after line 17, `from src.db.session import engine, get_session`):

```python
from src.services.featurizer_config import apply_config_patch
```

Delete the now-redundant local constant — remove these lines (26-29):

```python
# The only fields a featurizer_config_patch may touch — guards the stored config's
# schema against hallucinated key names (e.g. "rolling_windows_days" instead of "windows")
# regardless of how the LLM phrases the patch.
_VALID_CONFIG_PATCH_KEYS = {"windows", "lags", "feature_families", "energy_specific"}
```

Then replace the branch body (lines 182-184):

```python
        raw_patch = updates.get("featurizer_config_patch", {})
        config_patch = {k: v for k, v in raw_patch.items() if k in _VALID_CONFIG_PATCH_KEYS}
        s.featurizer_config = {**current_featurizer_config, **config_patch}
```

with:

```python
        raw_patch = updates.get("featurizer_config_patch", {})
        s.featurizer_config = apply_config_patch(current_featurizer_config, raw_patch)
```

- [ ] **Step 3: Run the chat tests again to verify the refactor is behavior-preserving**

Run: `cd backend && uv run pytest tests/test_chat.py -v`
Expected: all tests pass (14 passed) — identical to Step 1's baseline

- [ ] **Step 4: Lint check**

Run: `cd backend && uv run ruff check api/routes/chat.py`
Expected: no errors (confirms the removed constant left no dangling references)

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/chat.py
git commit -m "refactor: route chat.py's update_config patch through the shared apply_config_patch helper"
```

---

### Task 3: `PATCH /api/sessions/{session_id}/config` endpoint

**Files:**
- Modify: `backend/api/models.py` (add request/response models near `ProceedRequest`/`ProceedResponse`, after line 114's `RerunResponse`)
- Modify: `backend/api/routes/pipeline.py` (imports + new endpoint, placed after `rerun` and before `cancel`, i.e. after line 427)
- Test: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_pipeline.py` (after `test_proceed_with_featurizer_config_patch_merges_into_session`, i.e. after line 92):

```python
def test_update_config_returns_200_and_merges_patch(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"featurizer_config_patch": {"windows": [7, 30, 90]}},
    )
    assert res.status_code == 200
    assert res.json() == {"session_id": session_id}
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["featurizer_config"]["windows"] == [7, 30, 90]


def test_update_config_outside_user_review_returns_409(client):
    session_id = _create_session(client)
    # Session is at CONFIGURING, not USER_REVIEW
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"featurizer_config_patch": {"windows": [7, 30, 90]}},
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "config can only be edited during user_review"


def test_update_config_drops_unknown_patch_keys(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"featurizer_config_patch": {"rolling_windows_days": [1, 2, 3], "lags": [2, 10]}},
    )
    assert res.status_code == 200
    s = client.get(f"/api/sessions/{session_id}").json()
    assert "rolling_windows_days" not in s["featurizer_config"]
    assert s["featurizer_config"]["lags"] == [2, 10]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_pipeline.py -k update_config -v`
Expected: FAIL with `404 Not Found` / `assert 404 == 200` (route doesn't exist yet)

- [ ] **Step 3: Add the request/response models**

In `backend/api/models.py`, insert after `RerunResponse` (after line 114, before `class CancelResponse`):

```python
class ConfigPatchRequest(BaseModel):
    featurizer_config_patch: dict[str, object]


class ConfigPatchResponse(BaseModel):
    session_id: str
```

- [ ] **Step 4: Wire up imports and add the endpoint**

In `backend/api/routes/pipeline.py`, update the `from api.models import (...)` block (lines 24-33) to include the two new models, keeping the existing alphabetical-ish grouping:

```python
from api.models import (
    CancelResponse,
    ConfigPatchRequest,
    ConfigPatchResponse,
    DataArtifactDetail,
    ProceedRequest,
    ProceedResponse,
    RerunRequest,
    RerunResponse,
    SeriesPoint,
    UploadResponse,
)
```

Add the helper import alongside the existing `src.services.*` imports (after line 37, `from src.services.hashing import stable_hash`):

```python
from src.services.featurizer_config import apply_config_patch
```

Add the endpoint after `rerun` (after line 427, before the `cancel` route at line 430):

```python
@router.patch(
    "/sessions/{session_id}/config",
    response_model=ConfigPatchResponse,
)
async def update_config(
    session_id: str,
    req: ConfigPatchRequest,
    db: SessionDep,
) -> ConfigPatchResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if s.stage != SessionStage.USER_REVIEW:
        raise HTTPException(
            status_code=409, detail="config can only be edited during user_review"
        )

    s.featurizer_config = apply_config_patch(s.featurizer_config, req.featurizer_config_patch)
    await db.commit()

    log.info("session.config_updated", session_id=session_id)
    return ConfigPatchResponse(session_id=session_id)
```

(`uid` is unused here — that's consistent with the existing `cancel` endpoint just above, which also discards it.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_pipeline.py -k update_config -v`
Expected: 3 passed

- [ ] **Step 6: Run the full pipeline + chat suites to check for regressions**

Run: `cd backend && uv run pytest tests/test_pipeline.py tests/test_chat.py -v`
Expected: all pass

- [ ] **Step 7: Lint + type-check**

Run: `cd backend && uv run ruff check api/routes/pipeline.py api/models.py && uv run mypy api/routes/pipeline.py api/models.py`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add backend/api/models.py backend/api/routes/pipeline.py backend/tests/test_pipeline.py
git commit -m "feat: add PATCH /api/sessions/{id}/config endpoint for editing featurizer config during review"
```

---

### Task 4: Frontend `api.updateConfig` client method

**Files:**
- Modify: `frontend/lib/api.ts` (add method after `rerun`, i.e. after line 206)
- Test: `frontend/lib/__tests__/api.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `frontend/lib/__tests__/api.test.ts` (after the `api.proceed` describe block, i.e. after line 100):

```ts
describe("api.updateConfig", () => {
  it("PATCHes /config with the featurizer_config_patch body", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "ses-1" });
    const patch = { windows: [7, 30, 90] };
    await api.updateConfig("ses-1", patch);
    const [, init] = mockFetch.mock.calls[0];
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/sessions/ses-1/config"),
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(JSON.parse(init.body as string)).toEqual({ featurizer_config_patch: patch });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- api.test.ts`
Expected: FAIL with `api.updateConfig is not a function`

- [ ] **Step 3: Add the client method**

In `frontend/lib/api.ts`, add immediately after the `rerun` method (after its closing `}),` on line 206, before `cancelSession`):

```ts
  updateConfig: (sessionId: string, patch: Partial<FeaturizerConfig>) =>
    request<{ session_id: string }>(`/api/sessions/${sessionId}/config`, {
      method: "PATCH",
      body: JSON.stringify({ featurizer_config_patch: patch }),
    }),

```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- api.test.ts`
Expected: all `api.test.ts` tests pass, including the new `api.updateConfig` test

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/__tests__/api.test.ts
git commit -m "feat: add api.updateConfig client method for PATCH /sessions/{id}/config"
```

---

### Task 5: `FeaturizerConfigEditor` `readOnly` prop

**Files:**
- Modify: `frontend/components/FeaturizerConfigEditor.tsx` (full rewrite of `Props`, `NumberRow`, and the main export)
- Test: `frontend/components/__tests__/FeaturizerConfigEditor.test.tsx`

- [ ] **Step 1: Write the failing tests**

Append to `frontend/components/__tests__/FeaturizerConfigEditor.test.tsx` (after the existing `describe("FeaturizerConfigEditor", ...)` block, i.e. after line 55):

```tsx

describe("FeaturizerConfigEditor readOnly mode", () => {
  it("renders pills without remove buttons or an add input", () => {
    render(<FeaturizerConfigEditor value={baseConfig} readOnly />);
    expect(screen.queryByText("20d ×")).toBeNull();
    expect(screen.getByText("20d")).toBeTruthy();
    expect(screen.queryAllByPlaceholderText("+ add")).toHaveLength(0);
  });

  it("does not call onChange when a family pill is clicked", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} readOnly />);
    fireEvent.click(screen.getByText("Lag"));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("disables the energy-specific checkbox", () => {
    render(<FeaturizerConfigEditor value={baseConfig} readOnly />);
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm run test -- FeaturizerConfigEditor.test.tsx`
Expected: FAIL — `readOnly` prop doesn't exist (TypeScript error) and pills still render `×`/`+ add`

- [ ] **Step 3: Rewrite the component with `readOnly` support**

Replace the entire contents of `frontend/components/FeaturizerConfigEditor.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { FeaturizerConfig } from "@/lib/api";

const FAMILY_LABELS: Record<string, string> = {
  rolling_stats: "Rolling Stats",
  momentum: "Momentum",
  lag: "Lag",
  regime: "Regime",
};

type Props = {
  value: FeaturizerConfig;
  onChange?: (next: FeaturizerConfig) => void;
  readOnly?: boolean;
};

const TAG_ACTIVE =
  "px-2 py-0.5 bg-[#1e3a5f] border border-[#1d4ed8] rounded text-xs text-[#93c5fd] hover:bg-[#234876]";
const TAG_INACTIVE =
  "px-2 py-0.5 bg-transparent border border-[#374151] rounded text-xs text-[#4b5563] line-through hover:border-[#4b5563]";
const TAG_READONLY =
  "px-2 py-0.5 bg-transparent border border-[#374151] rounded text-xs text-[#9ca3af]";
const ADD_INPUT =
  "w-14 bg-transparent border border-dashed border-[#374151] rounded px-2 py-0.5 text-xs text-[#6b7280] placeholder:text-[#4b5563] focus:outline-none focus:border-[#3b82f6]";
const ROW_LABEL = "text-[10px] text-[#6b7280] w-16 flex-shrink-0";

function NumberRow({
  label,
  values,
  unit,
  onAdd,
  onRemove,
  readOnly,
}: {
  label: string;
  values: number[];
  unit: string;
  onAdd: (n: number) => void;
  onRemove: (n: number) => void;
  readOnly?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const n = Number(draft);
    if (Number.isInteger(n) && n > 0 && !values.includes(n)) onAdd(n);
    setDraft("");
  };

  if (readOnly) {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <span className={ROW_LABEL}>{label}</span>
        {values.map((v) => (
          <span key={`${label}-${v}`} className={TAG_READONLY}>
            {v}
            {unit}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className={ROW_LABEL}>{label}</span>
      {values.map((v) => (
        <button key={`${label}-${v}`} onClick={() => onRemove(v)} className={TAG_ACTIVE}>
          {v}
          {unit} ×
        </button>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
        }}
        placeholder="+ add"
        className={ADD_INPUT}
      />
    </div>
  );
}

export function FeaturizerConfigEditor({ value, onChange, readOnly = false }: Props) {
  const setWindows = (windows: number[]) => onChange?.({ ...value, windows });
  const setLags = (lags: number[]) => onChange?.({ ...value, lags });

  const toggleFamily = (key: string) => {
    if (readOnly) return;
    onChange?.({
      ...value,
      feature_families: value.feature_families.includes(key)
        ? value.feature_families.filter((f) => f !== key)
        : [...value.feature_families, key],
    });
  };

  return (
    <div className="flex flex-col gap-2.5">
      <NumberRow
        label="WINDOWS"
        values={value.windows}
        unit="d"
        onAdd={(n) => setWindows([...value.windows, n].sort((a, b) => a - b))}
        onRemove={(n) => setWindows(value.windows.filter((w) => w !== n))}
        readOnly={readOnly}
      />
      <NumberRow
        label="LAGS"
        values={value.lags}
        unit="d"
        onAdd={(n) => setLags([...value.lags, n].sort((a, b) => a - b))}
        onRemove={(n) => setLags(value.lags.filter((l) => l !== n))}
        readOnly={readOnly}
      />
      <div className="flex items-center gap-2 flex-wrap">
        <span className={ROW_LABEL}>FAMILIES</span>
        {Object.entries(FAMILY_LABELS).map(([key, label]) => (
          <button
            key={key}
            onClick={() => toggleFamily(key)}
            className={[
              value.feature_families.includes(key) ? TAG_ACTIVE : TAG_INACTIVE,
              readOnly ? "pointer-events-none opacity-60" : "",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-xs text-[#9ca3af]">
        <input
          type="checkbox"
          checked={value.energy_specific}
          onChange={(e) => onChange?.({ ...value, energy_specific: e.target.checked })}
          disabled={readOnly}
          className="accent-[#3b82f6]"
        />
        Energy-specific features
      </label>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run test -- FeaturizerConfigEditor.test.tsx`
Expected: all tests pass (8 total — 5 existing + 3 new)

- [ ] **Step 5: Type-check and lint**

Run: `cd frontend && npm run type-check && npx eslint components/FeaturizerConfigEditor.tsx`
Expected: no errors (confirms `GateMessage.tsx`'s existing `<FeaturizerConfigEditor value={draft} onChange={setDraft} />` call site still type-checks against the now-optional `onChange`)

- [ ] **Step 6: Commit**

```bash
git add frontend/components/FeaturizerConfigEditor.tsx frontend/components/__tests__/FeaturizerConfigEditor.test.tsx
git commit -m "feat: add readOnly mode to FeaturizerConfigEditor for non-review-stage viewing"
```

---

### Task 6: Config tab page

**Files:**
- Create: `frontend/app/sessions/[id]/config/page.tsx`

No test file — this matches the established convention for this directory: `activity/page.tsx`, `data/page.tsx`, and `results/page.tsx` are all untested page components (they're store/route-driven and verified via the running app, not Vitest). This page follows the same shape as `data/page.tsx`: `useParams` for the session id, `useSessionStore` for `featurizerConfig`/`stage`/`setSession`, `api.*` calls guarded by try/catch.

- [ ] **Step 1: Write the page**

```tsx
// frontend/app/sessions/[id]/config/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { FeaturizerConfigEditor } from "@/components/FeaturizerConfigEditor";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import type { FeaturizerConfig } from "@/lib/api";

type SaveStatus = "idle" | "saving" | "saved" | "failed";

export default function ConfigPage() {
  const { id } = useParams<{ id: string }>();
  const { featurizerConfig, stage, setSession } = useSessionStore();
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [pendingConfig, setPendingConfig] = useState<FeaturizerConfig | null>(null);

  useEffect(() => {
    if (status !== "saved") return;
    const timeout = setTimeout(() => setStatus("idle"), 2000);
    return () => clearTimeout(timeout);
  }, [status]);

  if (!featurizerConfig) {
    return (
      <div className="flex items-center justify-center h-full text-[#4b5563] text-sm">
        Loading…
      </div>
    );
  }

  const handleChange = async (next: FeaturizerConfig) => {
    if (!id) return;
    setStatus("saving");
    setPendingConfig(next);
    try {
      await api.updateConfig(id, next);
      const updated = await api.getSession(id);
      setSession(updated);
      setStatus("saved");
      setPendingConfig(null);
    } catch {
      setStatus("failed");
    }
  };

  const handleRetry = () => {
    if (pendingConfig) handleChange(pendingConfig);
  };

  if (stage !== "user_review") {
    return (
      <div className="flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs text-[#9ca3af]">Session config — read only</span>
          <span className="text-xs text-[#6b7280]">🔒 locked at this stage</span>
        </div>
        <FeaturizerConfigEditor value={featurizerConfig} readOnly />
        <p className="text-xs text-[#6b7280]">Editable only during the review step.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[#9ca3af]">Session config — editable while in review</span>
        {status === "saving" && <span className="text-xs text-[#9ca3af]">Saving…</span>}
        {status === "saved" && <span className="text-xs text-[#22c55e]">✓ Saved</span>}
        {status === "failed" && (
          <span className="text-xs text-[#ef4444] flex items-center gap-2">
            Failed to save
            <button onClick={handleRetry} className="underline underline-offset-2">
              retry
            </button>
          </span>
        )}
      </div>
      <FeaturizerConfigEditor value={featurizerConfig} onChange={handleChange} />
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npm run type-check`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/app/sessions/\[id\]/config/page.tsx
git commit -m "feat: add Config tab page with editable auto-save during review and read-only otherwise"
```

---

### Task 7: `SessionSidebar` component + layout integration

**Files:**
- Create: `frontend/components/SessionSidebar.tsx`
- Modify: `frontend/app/sessions/[id]/layout.tsx`

No test file for `SessionSidebar` — this matches the established convention: `StageStrip.tsx` (the other stage-driven, presentational nav component rendered in this same layout) has no test file either; these are verified by running the app. We'll do that manually in Step 4 below.

- [ ] **Step 1: Create the sidebar component**

`TABS` gains the `Config` entry per the design spec (§1); the active/locked/badge logic and styling constants are carried over verbatim from `layout.tsx:11-18` and `:152-161`, just rendered as vertical rows instead of a horizontal underlined row.

```tsx
// frontend/components/SessionSidebar.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { label: "Activity", path: "activity" },
  { label: "Data", path: "data" },
  { label: "Config", path: "config" },
  { label: "Results", path: "results" },
];

const DATA_LOCKED_STAGES = new Set(["configuring", "data_gathering"]);
const RESULTS_UNLOCKED_STAGE = "follow_up";

export function SessionSidebar({
  sessionId,
  stage,
}: {
  sessionId: string;
  stage: string | null;
}) {
  const pathname = usePathname();

  return (
    <nav className="w-[170px] flex-shrink-0 flex flex-col gap-1 p-2.5 border-r border-[#21262d]">
      {TABS.map((tab) => {
        const href = `/sessions/${sessionId}/${tab.path}`;
        const isActive = pathname === href;

        const isLocked =
          (tab.path === "data" && stage !== null && DATA_LOCKED_STAGES.has(stage)) ||
          (tab.path === "results" && stage !== RESULTS_UNLOCKED_STAGE);

        const badge =
          tab.path === "data" && stage !== null && !DATA_LOCKED_STAGES.has(stage)
            ? " ✓"
            : tab.path === "results" && stage === RESULTS_UNLOCKED_STAGE
            ? " ✦"
            : "";

        if (isLocked) {
          return (
            <span
              key={tab.label}
              title="Locked — not available at this stage"
              className="flex items-center justify-between px-3 py-2 rounded text-sm text-[#374151] cursor-not-allowed select-none"
            >
              {tab.label}
              <span aria-hidden>🔒</span>
            </span>
          );
        }

        return (
          <Link
            key={tab.label}
            href={href}
            className={[
              "px-3 py-2 rounded text-sm transition-colors",
              isActive
                ? "bg-[#1f2937] text-[#60a5fa] font-medium"
                : "text-[#9ca3af] hover:text-[#f9fafb]",
            ].join(" ")}
          >
            {tab.label}
            {badge}
          </Link>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 2: Replace the horizontal tab row in `layout.tsx` with the boxed sidebar panel**

In `frontend/app/sessions/[id]/layout.tsx`:

Remove the now-unused constants (lines 11-18):

```ts
const TABS = [
  { label: "Activity", path: "activity" },
  { label: "Data", path: "data" },
  { label: "Results", path: "results" },
];

const DATA_LOCKED_STAGES = new Set(["configuring", "data_gathering"]);
const RESULTS_UNLOCKED_STAGE = "follow_up";
```

Add the import (alongside the existing component imports, after line 6's `import { StageStrip } from "@/components/StageStrip";`):

```ts
import { SessionSidebar } from "@/components/SessionSidebar";
```

Replace everything from the `<StageStrip currentStage={stage} />` line through the end of the component's JSX (lines 145-196 — i.e. `StageStrip`, the horizontal `TABS.map` block, `ReviewBanner`, and `<main>`) with:

```tsx
      <StageStrip currentStage={stage} />

      {stage === "user_review" && id && <ReviewBanner sessionId={id} />}

      <div className="flex-1 min-h-0 m-4 flex border border-[#21262d] rounded-lg overflow-hidden">
        {id && <SessionSidebar sessionId={id} stage={stage} />}
        <main className="flex-1 overflow-auto min-h-0">{children}</main>
      </div>
    </div>
  );
}
```

This keeps `Header`, the session-id bar, `StageStrip`, and `ReviewBanner` full-width above the panel exactly as the spec requires (§1) — `ReviewBanner` simply moves up from its old position between the tab row and `<main>` to sit directly below `StageStrip`, still full-width, still gated on `stage === "user_review"`.

- [ ] **Step 3: Type-check and lint**

Run: `cd frontend && npm run type-check && npx eslint app/sessions/\[id\]/layout.tsx components/SessionSidebar.tsx`
Expected: no errors

- [ ] **Step 4: Manually verify in the browser**

Start both servers (or use `make dev`):

```bash
cd backend && uv run uvicorn api.main:app --reload --port 8000 &
cd frontend && npm run dev &
```

Open `http://localhost:3000`, open an existing session (or create one and upload a CSV to reach `user_review`), and verify:
- The Activity/Data/Config/Results nav now renders as a vertical list inside a bordered panel to the left of the page content
- `Data` shows locked styling (🔒 + tooltip) before data exists, and unlocks with a `✓` badge after upload
- `Results` shows locked styling until `follow_up`, then a `✦` badge
- `Config` is **never** locked, at any stage
- Clicking `Config` while at `user_review` shows the editable, auto-saving editor — adding/removing a window shows `Saving…` then `✓ Saved`, and the change is reflected in the Activity gate's config view too (store refetch)
- Clicking `Config` at any other stage shows the read-only pill view with the "Editable only during the review step." note
- `ReviewBanner` still appears full-width above the panel when at `user_review` and not on the Activity tab

Stop the dev servers when done.

- [ ] **Step 5: Run the full frontend test suite to check for regressions**

Run: `cd frontend && npm run test`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add frontend/components/SessionSidebar.tsx frontend/app/sessions/\[id\]/layout.tsx
git commit -m "feat: replace horizontal session tabs with vertical SessionSidebar in a boxed panel"
```

---

## Final verification

- [ ] Run the full backend suite: `cd backend && uv run python -m pytest` — expect all green
- [ ] Run the full frontend suite: `cd frontend && npm run test` — expect all green
- [ ] Run `make lint` — expect ruff, mypy, eslint, and tsc to all pass clean

Once all tasks are complete and verified, proceed to **superpowers:finishing-a-development-branch**.
