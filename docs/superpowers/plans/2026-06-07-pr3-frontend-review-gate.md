# PR 3-Frontend Review Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bare `RunAnalysisChip` in the USER_REVIEW gate with a `UserReviewGate` card that lets users inspect and edit `featurizer_config` (windows/lags/feature_families/energy_specific) before kicking off `FEATURIZING`, submitted deterministically through an extended `POST /proceed`.

**Architecture:** `POST /proceed` gains an optional `featurizer_config_patch` body field, merged into `session.featurizer_config` exactly like the existing `POST /rerun` does. On the frontend, a new `FeaturizerConfigEditor` (controlled, local draft state) is wrapped by `UserReviewGate`, which tracks dirtiness against the server's config and reports it upward so the chat input can be disabled whenever the draft and server diverge — making the structured-edit and free-text-chat paths mutually exclusive.

**Tech Stack:** FastAPI + Pydantic (backend), Next.js 15 / React / TypeScript / Tailwind + Vitest + Testing Library (frontend)

---

## Spec Reference

This plan implements `docs/superpowers/specs/2026-06-07-pr3-frontend-review-gate-design.md`.

---

### Task 1: Backend — extend `POST /proceed` with an optional `featurizer_config_patch`

**Files:**
- Modify: `backend/api/models.py:100-101` (add `ProceedRequest` before `ProceedResponse`)
- Modify: `backend/api/routes/pipeline.py:24-32` (import), `backend/api/routes/pipeline.py:330-378` (handler)
- Test: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_pipeline.py` (after `test_proceed_from_wrong_stage_returns_409`, currently ending at line 73):

```python
def test_proceed_with_featurizer_config_patch_merges_into_session(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        res = client.post(
            f"/api/sessions/{session_id}/proceed",
            json={"featurizer_config_patch": {"windows": [5, 30, 90]}},
        )
    assert res.status_code == 202
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["featurizer_config"]["windows"] == [5, 30, 90]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_pipeline.py::test_proceed_with_featurizer_config_patch_merges_into_session -v`
Expected: FAIL — `assert s["featurizer_config"]["windows"] == [5, 30, 90]` fails because the current handler ignores the request body and `windows` stays at its default value (e.g. `[5, 20, 60]`).

- [ ] **Step 3: Add `ProceedRequest` to `backend/api/models.py`**

Insert directly before `class ProceedResponse(BaseModel):` (currently at `backend/api/models.py:100`):

```python
class ProceedRequest(BaseModel):
    featurizer_config_patch: dict[str, object] | None = None


class ProceedResponse(BaseModel):
    session_id: str
```

- [ ] **Step 4: Wire the request model into the `proceed` handler**

In `backend/api/routes/pipeline.py`, add `ProceedRequest` to the import block (currently `pipeline.py:24-32`):

```python
from api.models import (
    CancelResponse,
    DataArtifactDetail,
    ProceedRequest,
    ProceedResponse,
    RerunRequest,
    RerunResponse,
    SeriesPoint,
    UploadResponse,
)
```

Change the handler signature (currently `pipeline.py:330-334`) from:

```python
async def proceed(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: SessionDep,
) -> ProceedResponse:
```

to:

```python
async def proceed(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: SessionDep,
    req: ProceedRequest | None = None,
) -> ProceedResponse:
```

(`req: ProceedRequest | None = None` makes the JSON body optional — calls with no body, an empty body, or `{}` all resolve `req` to a value whose `featurizer_config_patch` is `None`, so the existing no-body callers keep working unchanged.)

Then, immediately before `from_stage = s.stage` (currently `pipeline.py:370`, right after the missing-data guard block), add the merge — mirroring `rerun` at `pipeline.py:405-406`:

```python
    if req and req.featurizer_config_patch:
        s.featurizer_config = {**s.featurizer_config, **req.featurizer_config_patch}

    from_stage = s.stage
    transition_stage(s, SessionStage.FEATURIZING)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_pipeline.py -k proceed -v`
Expected: PASS — both `test_proceed_with_featurizer_config_patch_merges_into_session` and the pre-existing `test_proceed_from_user_review_returns_202` / `test_proceed_from_wrong_stage_returns_409` (the latter two double as regression guards that no-body and wrong-stage calls still behave as before).

- [ ] **Step 6: Commit**

```bash
cd backend && git add api/models.py api/routes/pipeline.py tests/test_pipeline.py
git commit -m "feat: accept optional featurizer_config_patch in POST /proceed"
```

---

### Task 2: Frontend — `api.proceed` sends an optional `featurizer_config_patch`

**Files:**
- Modify: `frontend/lib/api.ts:170-171`
- Test: `frontend/lib/__tests__/api.test.ts:74-84`

- [ ] **Step 1: Write the failing test**

Replace the existing `describe("api.proceed", ...)` block (`frontend/lib/__tests__/api.test.ts:74-84`) with:

```ts
describe("api.proceed", () => {
  it("posts to /proceed with no body when no patch is given", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "ses-1" });
    await api.proceed("ses-1");
    const [, init] = mockFetch.mock.calls[0];
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/sessions/ses-1/proceed"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(init.body).toBeUndefined();
  });

  it("posts featurizer_config_patch in the body when a patch is given", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "ses-1" });
    const patch = {
      windows: [5, 30, 90],
      lags: [1, 5],
      feature_families: ["rolling_stats"],
      energy_specific: true,
    };
    await api.proceed("ses-1", patch);
    const [, init] = mockFetch.mock.calls[0];
    expect(JSON.parse(init.body as string)).toEqual({ featurizer_config_patch: patch });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- api.test.ts`
Expected: FAIL on the second test — `api.proceed` currently takes no second argument and never sets a body, so `init.body` is `undefined` and `JSON.parse(undefined as string)` throws.

- [ ] **Step 3: Update `api.proceed`**

Replace `frontend/lib/api.ts:170-171`:

```ts
  proceed: (sessionId: string) =>
    request<{ session_id: string }>(`/api/sessions/${sessionId}/proceed`, { method: "POST" }),
```

with:

```ts
  proceed: (sessionId: string, featurizerConfigPatch?: FeaturizerConfig) =>
    request<{ session_id: string }>(`/api/sessions/${sessionId}/proceed`, {
      method: "POST",
      body: featurizerConfigPatch
        ? JSON.stringify({ featurizer_config_patch: featurizerConfigPatch })
        : undefined,
    }),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- api.test.ts`
Expected: PASS — both `api.proceed` tests green.

- [ ] **Step 5: Commit**

```bash
cd frontend && git add lib/api.ts lib/__tests__/api.test.ts
git commit -m "feat: send optional featurizer_config_patch from api.proceed"
```

---

### Task 3: `FeaturizerConfigEditor` component

**Files:**
- Create: `frontend/components/FeaturizerConfigEditor.tsx`
- Test: `frontend/components/__tests__/FeaturizerConfigEditor.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/components/__tests__/FeaturizerConfigEditor.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FeaturizerConfigEditor } from "../FeaturizerConfigEditor";
import type { FeaturizerConfig } from "@/lib/api";

const baseConfig: FeaturizerConfig = {
  windows: [5, 20, 60],
  lags: [1, 5],
  feature_families: ["rolling_stats", "momentum"],
  energy_specific: true,
};

describe("FeaturizerConfigEditor", () => {
  it("renders tags for windows, lags, and families", () => {
    render(<FeaturizerConfigEditor value={baseConfig} onChange={() => {}} />);
    expect(screen.getByText("5d ×")).toBeTruthy();
    expect(screen.getByText("20d ×")).toBeTruthy();
    expect(screen.getByText("60d ×")).toBeTruthy();
    expect(screen.getByText("1d ×")).toBeTruthy();
    expect(screen.getByText("Rolling Stats")).toBeTruthy();
  });

  it("calls onChange with the window removed when its tag is clicked", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} />);
    fireEvent.click(screen.getByText("20d ×"));
    expect(onChange).toHaveBeenCalledWith({ ...baseConfig, windows: [5, 60] });
  });

  it("adds a new window on Enter, keeping the list sorted and de-duplicated", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} />);
    const [windowsInput] = screen.getAllByPlaceholderText("+ add");
    fireEvent.change(windowsInput, { target: { value: "10" } });
    fireEvent.keyDown(windowsInput, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith({ ...baseConfig, windows: [5, 10, 20, 60] });
  });

  it("toggles a feature family on click", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} />);
    fireEvent.click(screen.getByText("Lag"));
    expect(onChange).toHaveBeenCalledWith({
      ...baseConfig,
      feature_families: ["rolling_stats", "momentum", "lag"],
    });
  });

  it("toggles energy_specific via the checkbox", () => {
    const onChange = vi.fn();
    render(<FeaturizerConfigEditor value={baseConfig} onChange={onChange} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledWith({ ...baseConfig, energy_specific: false });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- FeaturizerConfigEditor.test.tsx`
Expected: FAIL — `Cannot find module '../FeaturizerConfigEditor'` (file doesn't exist yet).

- [ ] **Step 3: Implement `FeaturizerConfigEditor`**

Create `frontend/components/FeaturizerConfigEditor.tsx`:

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
  onChange: (next: FeaturizerConfig) => void;
};

const TAG_ACTIVE =
  "px-2 py-0.5 bg-[#1e3a5f] border border-[#1d4ed8] rounded text-xs text-[#93c5fd] hover:bg-[#234876]";
const TAG_INACTIVE =
  "px-2 py-0.5 bg-transparent border border-[#374151] rounded text-xs text-[#4b5563] line-through hover:border-[#4b5563]";
const ADD_INPUT =
  "w-14 bg-transparent border border-dashed border-[#374151] rounded px-2 py-0.5 text-xs text-[#6b7280] placeholder:text-[#4b5563] focus:outline-none focus:border-[#3b82f6]";
const ROW_LABEL = "text-[10px] text-[#6b7280] w-16 flex-shrink-0";

function NumberRow({
  label,
  values,
  unit,
  onAdd,
  onRemove,
}: {
  label: string;
  values: number[];
  unit: string;
  onAdd: (n: number) => void;
  onRemove: (n: number) => void;
}) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const n = Number(draft);
    if (Number.isInteger(n) && n > 0 && !values.includes(n)) onAdd(n);
    setDraft("");
  };
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

export function FeaturizerConfigEditor({ value, onChange }: Props) {
  const setWindows = (windows: number[]) => onChange({ ...value, windows });
  const setLags = (lags: number[]) => onChange({ ...value, lags });

  const toggleFamily = (key: string) => {
    onChange({
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
      />
      <NumberRow
        label="LAGS"
        values={value.lags}
        unit="d"
        onAdd={(n) => setLags([...value.lags, n].sort((a, b) => a - b))}
        onRemove={(n) => setLags(value.lags.filter((l) => l !== n))}
      />
      <div className="flex items-center gap-2 flex-wrap">
        <span className={ROW_LABEL}>FAMILIES</span>
        {Object.entries(FAMILY_LABELS).map(([key, label]) => (
          <button
            key={key}
            onClick={() => toggleFamily(key)}
            className={value.feature_families.includes(key) ? TAG_ACTIVE : TAG_INACTIVE}
          >
            {label}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-xs text-[#9ca3af]">
        <input
          type="checkbox"
          checked={value.energy_specific}
          onChange={(e) => onChange({ ...value, energy_specific: e.target.checked })}
          className="accent-[#3b82f6]"
        />
        Energy-specific features
      </label>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- FeaturizerConfigEditor.test.tsx`
Expected: PASS — all 5 tests green.

- [ ] **Step 5: Commit**

```bash
cd frontend && git add components/FeaturizerConfigEditor.tsx components/__tests__/FeaturizerConfigEditor.test.tsx
git commit -m "feat: add FeaturizerConfigEditor for inline windows/lags/families editing"
```

---

### Task 4: `UserReviewGate` (in `GateMessage.tsx`)

**Files:**
- Create: `frontend/components/GateMessage.tsx`
- Test: `frontend/components/__tests__/GateMessage.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/components/__tests__/GateMessage.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { UserReviewGate } from "../GateMessage";
import type { FeaturizerConfig } from "@/lib/api";

const serverConfig: FeaturizerConfig = {
  windows: [5, 20, 60],
  lags: [1, 5],
  feature_families: ["rolling_stats", "momentum"],
  energy_specific: true,
};

describe("UserReviewGate", () => {
  it("calls onProceed with no patch when the draft matches the server config", () => {
    const onProceed = vi.fn();
    render(
      <UserReviewGate
        serverConfig={serverConfig}
        onProceed={onProceed}
        proceeding={false}
        onDirtyChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("→ Run Analysis"));
    expect(onProceed).toHaveBeenCalledWith(undefined);
  });

  it("shows the dirty banner and notifies the parent after an edit", () => {
    const onDirtyChange = vi.fn();
    render(
      <UserReviewGate
        serverConfig={serverConfig}
        onProceed={() => {}}
        proceeding={false}
        onDirtyChange={onDirtyChange}
      />,
    );
    fireEvent.click(screen.getByText("20d ×"));
    expect(screen.getByText(/Config changed/)).toBeTruthy();
    expect(onDirtyChange).toHaveBeenLastCalledWith(true);
  });

  it("sends the edited draft as the patch when running analysis while dirty", () => {
    const onProceed = vi.fn();
    render(
      <UserReviewGate
        serverConfig={serverConfig}
        onProceed={onProceed}
        proceeding={false}
        onDirtyChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("20d ×"));
    fireEvent.click(screen.getByText("→ Run Analysis"));
    expect(onProceed).toHaveBeenCalledWith({ ...serverConfig, windows: [5, 60] });
  });

  it("discard resets the draft to the server config and clears dirty state", () => {
    const onDirtyChange = vi.fn();
    render(
      <UserReviewGate
        serverConfig={serverConfig}
        onProceed={() => {}}
        proceeding={false}
        onDirtyChange={onDirtyChange}
      />,
    );
    fireEvent.click(screen.getByText("20d ×"));
    fireEvent.click(screen.getByText("Discard"));
    expect(screen.queryByText(/Config changed/)).toBeNull();
    expect(onDirtyChange).toHaveBeenLastCalledWith(false);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm run test -- GateMessage.test.tsx`
Expected: FAIL — `Cannot find module '../GateMessage'` (file doesn't exist yet).

- [ ] **Step 3: Implement `UserReviewGate`**

Create `frontend/components/GateMessage.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { FeaturizerConfigEditor } from "./FeaturizerConfigEditor";
import type { FeaturizerConfig } from "@/lib/api";

function arraysEqual<T>(a: T[], b: T[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

function configsEqual(a: FeaturizerConfig, b: FeaturizerConfig): boolean {
  return (
    arraysEqual(a.windows, b.windows) &&
    arraysEqual(a.lags, b.lags) &&
    arraysEqual(a.feature_families, b.feature_families) &&
    a.energy_specific === b.energy_specific
  );
}

type UserReviewGateProps = {
  serverConfig: FeaturizerConfig;
  onProceed: (patch?: FeaturizerConfig) => void;
  proceeding: boolean;
  onDirtyChange: (dirty: boolean) => void;
};

export function UserReviewGate({
  serverConfig,
  onProceed,
  proceeding,
  onDirtyChange,
}: UserReviewGateProps) {
  const [draft, setDraft] = useState(serverConfig);
  const isDirty = !configsEqual(draft, serverConfig);

  // Notify the parent so the chat input can be disabled while edits are unsaved —
  // this is what keeps the structured-edit and free-text-chat paths from racing
  // (see "The chat/editor boundary" in the design doc).
  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  return (
    <div className="self-end max-w-[85%] flex flex-col gap-3 bg-[#0d1117] border border-[#21262d] rounded-lg p-3">
      <FeaturizerConfigEditor value={draft} onChange={setDraft} />

      {isDirty && (
        <div className="flex items-center gap-2 px-2.5 py-1.5 bg-[#1c1009] border border-[#92400e] rounded text-xs text-[#fbbf24]">
          <span className="flex-1">Config changed — Run Analysis to apply, or discard your edits</span>
          <button onClick={() => setDraft(serverConfig)} className="text-[#f97316] hover:underline">
            Discard
          </button>
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={() => onProceed(isDirty ? draft : undefined)}
          disabled={proceeding}
          className="px-4 py-2 bg-[#052e16] border border-[#15803d] rounded-full text-[#22c55e] text-sm font-semibold hover:bg-[#14532d] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {proceeding ? "Starting…" : "→ Run Analysis"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm run test -- GateMessage.test.tsx`
Expected: PASS — all 4 tests green.

- [ ] **Step 5: Commit**

```bash
cd frontend && git add components/GateMessage.tsx components/__tests__/GateMessage.test.tsx
git commit -m "feat: add UserReviewGate with dirty-state tracking for config edits"
```

---

### Task 5: Wire `UserReviewGate` into the activity feed, replacing `RunAnalysisChip`

**Files:**
- Modify: `frontend/app/sessions/[id]/activity/page.tsx`

This task has no new tests of its own — `RunAnalysisChip` (the thing being replaced) had none, and the wiring is exercised end-to-end by the existing activity-page rendering plus the component tests from Tasks 3–4. Each step below is a self-contained edit; verify with `npm run type-check` after Step 5 and a manual smoke check (Step 6).

- [ ] **Step 1: Swap the import and delete `RunAnalysisChip`**

In `frontend/app/sessions/[id]/activity/page.tsx`, add the import alongside the existing `useSessionStore` import (currently line 8):

```tsx
import { useSessionStore } from "@/lib/store";
import { UserReviewGate } from "@/components/GateMessage";
```

Delete the entire `RunAnalysisChip` function, currently `activity/page.tsx:328-346`:

```tsx
// --- Run Analysis quick-action chip ---

function RunAnalysisChip({
  onProceed,
  proceeding,
}: {
  onProceed: () => void;
  proceeding: boolean;
}) {
  return (
    <div className="flex justify-end">
      <button
        onClick={onProceed}
        disabled={proceeding}
        className="px-4 py-2 bg-[#052e16] border border-[#15803d] rounded-full text-[#22c55e] text-sm font-semibold hover:bg-[#14532d] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {proceeding ? "Starting…" : "→ Run Analysis"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Pull `featurizerConfig` from the store and add `reviewConfigDirty` state**

Change the store destructure (currently `activity/page.tsx:366-367`):

```tsx
  const { activityEvents, wsMessages, conversation, stage, status, sessionId, setSession } =
    useSessionStore();
```

to:

```tsx
  const {
    activityEvents,
    wsMessages,
    conversation,
    stage,
    status,
    sessionId,
    featurizerConfig,
    setSession,
  } = useSessionStore();
```

Add a new piece of state alongside `proceedError` (currently `activity/page.tsx:373`):

```tsx
  const [proceedError, setProceedError] = useState<string | null>(null);
  const [reviewConfigDirty, setReviewConfigDirty] = useState(false);
```

- [ ] **Step 3: Let `handleProceed` forward an optional patch**

Change `handleProceed` (currently `activity/page.tsx:407-420`) from:

```tsx
  const handleProceed = async () => {
    if (!sessionId || proceeding) return;
    setProceeding(true);
    setProceedError(null);
    try {
      await api.proceed(sessionId);
      const updated = await api.getSession(sessionId);
      setSession(updated);
    } catch (e) {
      setProceedError(e instanceof Error ? e.message : "Failed to start analysis");
    } finally {
      setProceeding(false);
    }
  };
```

to:

```tsx
  const handleProceed = async (featurizerConfigPatch?: FeaturizerConfig) => {
    if (!sessionId || proceeding) return;
    setProceeding(true);
    setProceedError(null);
    try {
      await api.proceed(sessionId, featurizerConfigPatch);
      const updated = await api.getSession(sessionId);
      setSession(updated);
    } catch (e) {
      setProceedError(e instanceof Error ? e.message : "Failed to start analysis");
    } finally {
      setProceeding(false);
    }
  };
```

Add `FeaturizerConfig` to the type-only import at the top of the file (currently `activity/page.tsx:5`):

```tsx
import type { ChatMessage, FeaturizerConfig } from "@/lib/api";
```

- [ ] **Step 4: Disable chat while the review config is dirty**

Change `inputDisabled` (currently `activity/page.tsx:424`) from:

```tsx
  const inputDisabled = sending || status !== "waiting";
```

to:

```tsx
  const inputDisabled =
    sending || status !== "waiting" || (stage === "user_review" && reviewConfigDirty);
```

Update the input placeholder (currently `activity/page.tsx:478-484`) to surface *why* it's disabled in the dirty case — change:

```tsx
              placeholder={
                stage === "data_gathering" && status === "running"
                  ? "Fetching data..."
                  : status === "running"
                  ? "Agent is thinking..."
                  : "Ask to adjust data, or say “run analysis”"
              }
```

to:

```tsx
              placeholder={
                stage === "data_gathering" && status === "running"
                  ? "Fetching data..."
                  : status === "running"
                  ? "Agent is thinking..."
                  : stage === "user_review" && reviewConfigDirty
                  ? "Config changes pending — Run Analysis or Discard to continue chatting"
                  : "Ask to adjust data, or say “run analysis”"
              }
```

- [ ] **Step 5: Replace the `RunAnalysisChip` render with `UserReviewGate`**

Change (currently `activity/page.tsx:452-454`):

```tsx
            {showRunAnalysis && (
              <RunAnalysisChip onProceed={handleProceed} proceeding={proceeding} />
            )}
```

to:

```tsx
            {showRunAnalysis && featurizerConfig && (
              <UserReviewGate
                key={JSON.stringify(featurizerConfig)}
                serverConfig={featurizerConfig}
                onProceed={handleProceed}
                proceeding={proceeding}
                onDirtyChange={setReviewConfigDirty}
              />
            )}
```

The `key={JSON.stringify(featurizerConfig)}` remounts the gate (re-seeding its local draft) whenever the *server's* config changes. This is safe specifically because of the invariant established in Task 4 / the design doc: chat (the only path that can change `featurizer_config` server-side via `update_config`) is disabled whenever the draft is dirty, so the server's config can only change out from under the gate while the draft is clean — at which point a fresh draft equal to the new server config is exactly correct.

- [ ] **Step 6: Verify with the dev server**

Run: `cd frontend && npm run type-check`
Expected: no errors.

Then start the stack (`make dev-backend` in one terminal, `make dev-frontend` in another — or `make dev` for docker-compose), open a session that has reached `USER_REVIEW` (create one and upload a CSV, or use an existing session at that stage), and confirm in the browser:
- The gate card shows editable tags seeded from the session's `featurizer_config`
- Removing/adding a window or lag tag, toggling a family, or flipping the energy-specific checkbox shows the amber "Config changed" banner and disables the chat input (with the new placeholder)
- "Discard" restores the original tags, hides the banner, and re-enables chat
- "Run Analysis →" with no edits calls `/proceed` with no patch (check Network tab: empty body) and transitions the session to `FEATURIZING`
- "Run Analysis →" with edits calls `/proceed` with `{"featurizer_config_patch": {...}}` in the body and the new config is reflected in `GET /api/sessions/{id}`

- [ ] **Step 7: Commit**

```bash
cd frontend && git add app/sessions/\[id\]/activity/page.tsx
git commit -m "feat: replace RunAnalysisChip with UserReviewGate in the review feed"
```

---

### Task 6: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && uv run python -m pytest`
Expected: all tests pass, including the two new/changed `proceed` tests from Task 1.

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npm run test`
Expected: all tests pass, including `api.test.ts`, `FeaturizerConfigEditor.test.tsx`, and `GateMessage.test.tsx`.

- [ ] **Step 3: Run lint and type-check**

Run: `make lint`
Expected: ruff, mypy, eslint, and tsc all pass with no new warnings/errors.

- [ ] **Step 4: Final commit (only if any of the above required fixes)**

```bash
git add -A
git commit -m "test: fix lint/type issues from review gate work"
```

(Skip this step if Steps 1–3 were clean — don't create an empty commit.)
