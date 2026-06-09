# Session Config Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make timeframe and data sources visible and editable on the config page, with stale warnings on results pages when config has drifted from the last run.

**Architecture:** Extend `PATCH /sessions/{id}/config` to accept timeframe/sources patches (relaxing the `user_review`-only gate for those fields). On the frontend, add `ConnectorEditor` and rebuild the config page with three stacked sections (Session, Data Sources, Featurizer). Stale detection is purely frontend — compare session timeframe/sources against the latest `DataArtifact`.

**Tech Stack:** FastAPI + SQLModel (backend), Next.js 15 App Router + Zustand + Tailwind CSS (frontend). No DB migrations — `pending_sources`, `timeframe_start`, `timeframe_end` already exist on the `Session` model. `GET /api/connectors` and `ConnectorOut` are already implemented — no changes needed there.

---

## File Map

| File | Change |
|---|---|
| `backend/api/models.py:117-118` | Extend `ConfigPatchRequest`; add `pending_sources` to `SessionDetail` |
| `backend/api/routes/pipeline.py:433-451` | Relax stage gate in `update_config` |
| `backend/api/routes/sessions.py:103-120` | Add `pending_sources` to `_to_detail` |
| `backend/tests/test_pipeline.py` | Update error message assertion; add 3 new tests |
| `frontend/lib/api.ts` | Add `PendingSource`, `ConnectorOut` types; `pending_sources` on `Session`; extend `updateConfig`; add `getConnectors` |
| `frontend/lib/store.ts` | Add `marketProfile`, `timeframeStart`, `timeframeEnd`, `pendingSources` |
| `frontend/lib/stale.ts` | New — `isSessionStale()` |
| `frontend/components/ConnectorEditor.tsx` | New — inline toggle connector selector |
| `frontend/components/StaleResultsBanner.tsx` | New — amber stale warning banner |
| `frontend/app/sessions/[id]/config/page.tsx` | Rebuild with 3 sections |
| `frontend/app/sessions/[id]/overview/page.tsx` | Add stale banner |
| `frontend/app/sessions/[id]/features/page.tsx` | Add stale banner |
| `frontend/app/sessions/[id]/backtest/page.tsx` | Add stale banner |

---

## Task 1: Backend — extend ConfigPatchRequest and SessionDetail models

**Files:**
- Modify: `backend/api/models.py:43-58, 117-118`

- [ ] **Step 1: Update `ConfigPatchRequest` to accept optional fields**

In `backend/api/models.py`, replace lines 117–118:

```python
class ConfigPatchRequest(BaseModel):
    featurizer_config_patch: dict[str, object] | None = None
    timeframe_start: str | None = None
    timeframe_end: str | None = None
    pending_sources: list[dict[str, object]] | None = None
```

- [ ] **Step 2: Add `pending_sources` to `SessionDetail`**

In `backend/api/models.py`, add one field to `SessionDetail` (after `updated_at` is fine, but for logical grouping add it after `featurizer_config` at line 52):

```python
class SessionDetail(BaseModel):
    session_id: str
    market_profile: str
    timeframe_start: str
    timeframe_end: str
    stage: str
    status: str
    error: str | None
    auto: bool
    featurizer_config: dict[str, object]
    pending_sources: list[object]
    conversation: list[object]
    activity_events: list[object]
    stage_history: list[object]
    artifacts: SessionArtifacts
    created_at: str
    updated_at: str
```

- [ ] **Step 3: Verify Python can import the models**

```bash
cd backend && uv run python -c "from api.models import ConfigPatchRequest, SessionDetail; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/api/models.py
git commit -m "feat: extend ConfigPatchRequest with timeframe and pending_sources fields"
```

---

## Task 2: Backend — relax update_config route and expose pending_sources

**Files:**
- Modify: `backend/api/routes/pipeline.py:433-451`
- Modify: `backend/api/routes/sessions.py:103-120`
- Modify: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

In `backend/tests/test_pipeline.py`, add these three tests after `test_update_config_outside_user_review_returns_409` (line 122):

```python
def test_update_config_timeframe_succeeds_at_configuring(client):
    session_id = _create_session(client)
    # Session is at CONFIGURING — timeframe patch should succeed (no stage gate)
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"timeframe_start": "2024-01-01", "timeframe_end": "2024-12-31"},
    )
    assert res.status_code == 200
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["timeframe_start"] == "2024-01-01"
    assert s["timeframe_end"] == "2024-12-31"


def test_update_config_pending_sources_succeeds(client):
    session_id = _create_session(client)
    sources = [{"connector_id": "yfinance", "params": {"tickers": ["CL=F"]}}]
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"pending_sources": sources},
    )
    assert res.status_code == 200
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["pending_sources"] == sources


def test_update_config_empty_patch_succeeds(client):
    session_id = _create_session(client)
    # All fields optional — empty patch is valid (no-op)
    res = client.patch(f"/api/sessions/{session_id}/config", json={})
    assert res.status_code == 200
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd backend && uv run pytest tests/test_pipeline.py::test_update_config_timeframe_succeeds_at_configuring tests/test_pipeline.py::test_update_config_pending_sources_succeeds tests/test_pipeline.py::test_update_config_empty_patch_succeeds -v
```

Expected: all three FAIL (two with 409, one possibly 422 from required field).

- [ ] **Step 3: Add `from datetime import date` to pipeline.py imports**

In `backend/api/routes/pipeline.py`, find the `from __future__ import annotations` block at the top and add the datetime import after it:

```python
from __future__ import annotations

import hashlib
import io
import pathlib
import uuid
from datetime import date
from typing import Annotated, Any
```

- [ ] **Step 4: Replace `update_config` in pipeline.py**

Replace lines 433–451 in `backend/api/routes/pipeline.py`:

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

    if s.status == SessionStatus.RUNNING:
        raise HTTPException(status_code=409, detail="cannot update config while session is running")

    if req.featurizer_config_patch is not None:
        if s.stage != SessionStage.USER_REVIEW:
            raise HTTPException(
                status_code=409,
                detail="featurizer config can only be edited during user_review",
            )
        s.featurizer_config = apply_config_patch(s.featurizer_config, req.featurizer_config_patch)

    if req.timeframe_start is not None:
        s.timeframe_start = date.fromisoformat(req.timeframe_start)
    if req.timeframe_end is not None:
        s.timeframe_end = date.fromisoformat(req.timeframe_end)
    if req.pending_sources is not None:
        s.pending_sources = req.pending_sources

    await db.commit()
    log.info("session.config_updated", session_id=session_id)
    return ConfigPatchResponse(session_id=session_id)
```

- [ ] **Step 5: Add `pending_sources` to `_to_detail` in sessions.py**

Replace lines 103–120 in `backend/api/routes/sessions.py`:

```python
def _to_detail(s: SessionModel, artifacts: SessionArtifacts) -> SessionDetail:
    return SessionDetail(
        session_id=str(s.id),
        market_profile=s.market_profile,
        timeframe_start=str(s.timeframe_start),
        timeframe_end=str(s.timeframe_end),
        stage=s.stage,
        status=s.status,
        error=s.error,
        auto=s.auto,
        featurizer_config=s.featurizer_config,
        pending_sources=list(s.pending_sources or []),
        conversation=s.conversation,
        activity_events=s.activity_events,
        stage_history=s.stage_history,
        artifacts=artifacts,
        created_at=_iso(s.created_at),
        updated_at=_iso(s.updated_at),
    )
```

- [ ] **Step 6: Update the existing error message test**

In `backend/tests/test_pipeline.py`, update `test_update_config_outside_user_review_returns_409` (line 114) to match the new error message:

```python
def test_update_config_outside_user_review_returns_409(client):
    session_id = _create_session(client)
    # Session is at CONFIGURING, not USER_REVIEW
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"featurizer_config_patch": {"windows": [7, 30, 90]}},
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "featurizer config can only be edited during user_review"
```

- [ ] **Step 7: Run all pipeline tests**

```bash
cd backend && uv run pytest tests/test_pipeline.py -v
```

Expected: all tests pass, including the three new ones.

- [ ] **Step 8: Commit**

```bash
git add backend/api/routes/pipeline.py backend/api/routes/sessions.py backend/tests/test_pipeline.py
git commit -m "feat: relax config patch stage gate for timeframe and pending_sources"
```

---

## Task 3: Frontend — API types, store, and getConnectors

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/store.ts`

- [ ] **Step 1: Add `PendingSource` and `ConnectorOut` types to api.ts**

In `frontend/lib/api.ts`, add these two types after the `FeaturizerConfig` type (after line 20):

```ts
export type PendingSource = {
  connector_id: string;
  params?: Record<string, unknown>;
};

export type ConnectorOut = {
  id: string;
  name: string;
  description: string;
  type: string;
  available: boolean;
};
```

- [ ] **Step 2: Add `pending_sources` to the `Session` type**

In `frontend/lib/api.ts`, add `pending_sources` to the `Session` type (after `featurizer_config` at line 75):

```ts
export type Session = {
  session_id: string;
  market_profile: string;
  timeframe_start: string;
  timeframe_end: string;
  stage: SessionStage;
  status: SessionStatus;
  error: string | null;
  auto: boolean;
  featurizer_config: FeaturizerConfig;
  pending_sources: PendingSource[];
  conversation: ChatMessage[];
  activity_events: ActivityEvent[];
  stage_history: StageHistoryEntry[];
  artifacts: SessionArtifacts;
  created_at: string;
  updated_at: string;
};
```

- [ ] **Step 3: Replace `updateConfig` and add `getConnectors` in api.ts**

Replace the `updateConfig` entry (lines 208–212) in `frontend/lib/api.ts`:

```ts
  updateConfig: (
    sessionId: string,
    patch: {
      featurizer_config_patch?: Partial<FeaturizerConfig>;
      timeframe_start?: string;
      timeframe_end?: string;
      pending_sources?: PendingSource[];
    },
  ) =>
    request<{ session_id: string }>(`/api/sessions/${sessionId}/config`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  getConnectors: () => request<ConnectorOut[]>("/api/connectors"),
```

- [ ] **Step 4: Add fields to the Zustand store**

In `frontend/lib/store.ts`, add four fields to `SessionStore`:

```ts
type SessionStore = {
  sessionId: string | null;
  stage: SessionStage | null;
  status: SessionStatus | null;
  marketProfile: string | null;
  timeframeStart: string | null;
  timeframeEnd: string | null;
  pendingSources: PendingSource[];
  featurizerConfig: FeaturizerConfig | null;
  conversation: ChatMessage[];
  activityEvents: ActivityEvent[];
  wsMessages: WsMessage[];
  artifacts: SessionArtifacts;
  error: string | null;

  setSession: (session: Session) => void;
  appendWsMessage: (msg: WsMessage) => void;
  clearSession: () => void;
};
```

Update the initial state and `setSession`/`clearSession` implementations:

```ts
export const useSessionStore = create<SessionStore>((set) => ({
  sessionId: null,
  stage: null,
  status: null,
  marketProfile: null,
  timeframeStart: null,
  timeframeEnd: null,
  pendingSources: [],
  featurizerConfig: null,
  conversation: [],
  activityEvents: [],
  wsMessages: [],
  artifacts: EMPTY_ARTIFACTS,
  error: null,

  setSession: (session) =>
    set((state) => ({
      sessionId: session.session_id,
      stage: session.stage,
      status: session.status,
      marketProfile: session.market_profile,
      timeframeStart: session.timeframe_start,
      timeframeEnd: session.timeframe_end,
      pendingSources: session.pending_sources ?? [],
      featurizerConfig: session.featurizer_config,
      conversation: session.conversation,
      activityEvents: session.activity_events,
      artifacts: session.artifacts,
      error: session.error,
      wsMessages: state.sessionId !== session.session_id ? [] : state.wsMessages,
    })),

  appendWsMessage: (msg) =>
    set((state) => ({
      wsMessages:
        state.wsMessages.length >= MAX_WS_MESSAGES
          ? [...state.wsMessages.slice(1), msg]
          : [...state.wsMessages, msg],
    })),

  clearSession: () =>
    set({
      sessionId: null,
      stage: null,
      status: null,
      marketProfile: null,
      timeframeStart: null,
      timeframeEnd: null,
      pendingSources: [],
      featurizerConfig: null,
      conversation: [],
      activityEvents: [],
      wsMessages: [],
      artifacts: EMPTY_ARTIFACTS,
      error: null,
    }),
}));
```

Add `PendingSource` and `Session` to the import list at the top of `store.ts`:

```ts
import type {
  ActivityEvent,
  ChatMessage,
  FeaturizerConfig,
  PendingSource,
  Session,
  SessionArtifacts,
  SessionStage,
  SessionStatus,
} from "./api";
```

- [ ] **Step 5: Verify type-check passes**

```bash
cd frontend && npm run type-check
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/store.ts
git commit -m "feat: add PendingSource/ConnectorOut types, extend store with timeframe and sources"
```

---

## Task 4: Frontend — stale detection and banner

**Files:**
- Create: `frontend/lib/stale.ts`
- Create: `frontend/components/StaleResultsBanner.tsx`

- [ ] **Step 1: Create `frontend/lib/stale.ts`**

```ts
import type { PendingSource } from "./api";

export function isSessionStale(
  session: {
    timeframeStart: string | null;
    timeframeEnd: string | null;
    pendingSources: PendingSource[];
  },
  latestArtifact: {
    data_manifest: { date_range: { start: string; end: string } };
    sources: { connector_id: string }[];
  } | null,
): boolean {
  if (!latestArtifact) return false;

  const tfChanged =
    session.timeframeStart !== latestArtifact.data_manifest.date_range.start ||
    session.timeframeEnd !== latestArtifact.data_manifest.date_range.end;

  const sessionIds = session.pendingSources.map((s) => s.connector_id).sort().join(",");
  const artifactIds = latestArtifact.sources.map((s) => s.connector_id).sort().join(",");
  const sourcesChanged = sessionIds !== artifactIds;

  return tfChanged || sourcesChanged;
}
```

- [ ] **Step 2: Create `frontend/components/StaleResultsBanner.tsx`**

```tsx
import Link from "next/link";

type Props = { sessionId: string; isStale: boolean };

export function StaleResultsBanner({ sessionId, isStale }: Props) {
  if (!isStale) return null;
  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs flex-shrink-0">
      <span className="text-amber-600">⚠</span>
      <span className="text-amber-700">Results from prior run — timeframe or sources have changed.</span>
      <Link
        href={`/sessions/${sessionId}/config`}
        className="text-amber-600 underline underline-offset-2 ml-1"
      >
        Go to Config →
      </Link>
    </div>
  );
}
```

- [ ] **Step 3: Verify type-check passes**

```bash
cd frontend && npm run type-check
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/stale.ts frontend/components/StaleResultsBanner.tsx
git commit -m "feat: add isSessionStale helper and StaleResultsBanner component"
```

---

## Task 5: Frontend — ConnectorEditor component

**Files:**
- Create: `frontend/components/ConnectorEditor.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import type { ConnectorOut, PendingSource } from "@/lib/api";

type Props = {
  available: ConnectorOut[];
  value: PendingSource[];
  onChange: (next: PendingSource[]) => void;
  readOnly?: boolean;
};

export function ConnectorEditor({ available, value, onChange, readOnly }: Props) {
  const activeIds = new Set(value.map((s) => s.connector_id));

  function toggle(connector: ConnectorOut) {
    if (readOnly) return;
    if (activeIds.has(connector.id)) {
      onChange(value.filter((s) => s.connector_id !== connector.id));
    } else {
      onChange([...value, { connector_id: connector.id }]);
    }
  }

  function setTickers(connectorId: string, raw: string) {
    const tickers = raw
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    onChange(
      value.map((s) =>
        s.connector_id === connectorId ? { ...s, params: { ...s.params, tickers } } : s,
      ),
    );
  }

  if (available.length === 0) {
    return (
      <div className="border border-gray-200 rounded-lg px-3 py-4 text-xs text-gray-400 text-center">
        No connectors configured.
      </div>
    );
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="text-[10px] text-gray-400 px-3 py-2 border-b border-gray-100 bg-gray-50 font-mono uppercase tracking-widest">
        Click to toggle · active connectors used on next data run
      </div>
      {available.map((connector) => {
        const isActive = activeIds.has(connector.id);
        const source = value.find((s) => s.connector_id === connector.id);
        // Ticker input shown only for yfinance — it's the only connector with user-configurable tickers
        const showTickers = isActive && connector.id === "yfinance";
        const tickers = (source?.params?.tickers as string[] | undefined)?.join(", ") ?? "";

        return (
          <div
            key={connector.id}
            onClick={() => toggle(connector)}
            className={[
              "px-3 py-2.5 border-b border-gray-100 last:border-0 transition-colors",
              readOnly ? "cursor-default" : "cursor-pointer",
              isActive ? "bg-teal-50" : "bg-white",
            ].join(" ")}
          >
            <div className={`flex items-center gap-2 ${isActive ? "" : "opacity-50"}`}>
              <div
                className={`w-2 h-2 rounded-full flex-shrink-0 ${isActive ? "bg-teal-500" : "bg-gray-300"}`}
              />
              <span className={`text-sm font-medium ${isActive ? "text-teal-700" : "text-gray-500"}`}>
                {connector.name}
              </span>
              <span className="text-xs text-gray-400 truncate">{connector.description}</span>
            </div>
            {showTickers && (
              <div
                className="mt-1.5 flex items-center gap-2 ml-4"
                onClick={(e) => e.stopPropagation()}
              >
                <span className="text-[10px] text-gray-400 font-mono">Tickers:</span>
                <input
                  value={tickers}
                  onChange={(e) => setTickers(connector.id, e.target.value)}
                  disabled={readOnly}
                  className="flex-1 text-xs font-mono border border-teal-200 rounded px-2 py-0.5 bg-white outline-none focus:border-teal-400 disabled:opacity-40"
                  placeholder="CL=F, BZ=F, DX-Y.NYB"
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Verify type-check passes**

```bash
cd frontend && npm run type-check
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/ConnectorEditor.tsx
git commit -m "feat: add ConnectorEditor component with inline toggle rows"
```

---

## Task 6: Frontend — rebuild config page

**Files:**
- Modify: `frontend/app/sessions/[id]/config/page.tsx`

- [ ] **Step 1: Replace the full file**

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { FeaturizerConfigEditor } from "@/components/FeaturizerConfigEditor";
import { ConnectorEditor } from "@/components/ConnectorEditor";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { ConnectorOut, DataArtifactDetail, FeaturizerConfig, PendingSource } from "@/lib/api";

type SaveStatus = "idle" | "saving" | "saved" | "failed";

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold tracking-widest text-gray-400 uppercase mb-2">
      {children}
    </div>
  );
}

function SaveIndicator({
  status,
  onRetry,
}: {
  status: SaveStatus;
  onRetry: () => void;
}) {
  if (status === "idle") return null;
  if (status === "saving") return <span className="text-xs text-gray-400">Saving…</span>;
  if (status === "saved") return <span className="text-xs text-green-600">✓ Saved</span>;
  return (
    <span className="text-xs text-red-500 flex items-center gap-2">
      Failed
      <button onClick={onRetry} className="underline underline-offset-2">
        retry
      </button>
    </span>
  );
}

export default function ConfigPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const {
    featurizerConfig,
    stage,
    status,
    marketProfile,
    timeframeStart,
    timeframeEnd,
    pendingSources,
    artifacts,
    setSession,
  } = useSessionStore();

  const [connectors, setConnectors] = useState<ConnectorOut[]>([]);
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);

  const [localStart, setLocalStart] = useState(timeframeStart ?? "");
  const [localEnd, setLocalEnd] = useState(timeframeEnd ?? "");
  const [localSources, setLocalSources] = useState<PendingSource[]>(pendingSources);

  const [tfStatus, setTfStatus] = useState<SaveStatus>("idle");
  const [srcStatus, setSrcStatus] = useState<SaveStatus>("idle");
  const [featStatus, setFeatStatus] = useState<SaveStatus>("idle");
  const [pendingFeatConfig, setPendingFeatConfig] = useState<FeaturizerConfig | null>(null);

  const srcDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync local copies when store updates (e.g. after session refresh in layout)
  useEffect(() => setLocalStart(timeframeStart ?? ""), [timeframeStart]);
  useEffect(() => setLocalEnd(timeframeEnd ?? ""), [timeframeEnd]);
  useEffect(() => setLocalSources(pendingSources), [pendingSources]);

  useEffect(() => {
    api.getConnectors().then(setConnectors).catch(() => {});
  }, []);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  // Auto-clear save indicators
  useEffect(() => {
    if (tfStatus !== "saved") return;
    const t = setTimeout(() => setTfStatus("idle"), 2000);
    return () => clearTimeout(t);
  }, [tfStatus]);
  useEffect(() => {
    if (srcStatus !== "saved") return;
    const t = setTimeout(() => setSrcStatus("idle"), 2000);
    return () => clearTimeout(t);
  }, [srcStatus]);
  useEffect(() => {
    if (featStatus !== "saved") return;
    const t = setTimeout(() => setFeatStatus("idle"), 2000);
    return () => clearTimeout(t);
  }, [featStatus]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as { connector_id: string }[],
        }
      : null,
  );

  const isRunning = status === "running";

  const saveTimeframe = useCallback(async () => {
    if (!id) return;
    setTfStatus("saving");
    try {
      await api.updateConfig(id, { timeframe_start: localStart, timeframe_end: localEnd });
      const updated = await api.getSession(id);
      setSession(updated);
      setTfStatus("saved");
    } catch {
      setTfStatus("failed");
    }
  }, [id, localStart, localEnd, setSession]);

  const handleSourcesChange = (next: PendingSource[]) => {
    setLocalSources(next);
    if (srcDebounce.current) clearTimeout(srcDebounce.current);
    srcDebounce.current = setTimeout(async () => {
      if (!id) return;
      setSrcStatus("saving");
      try {
        await api.updateConfig(id, { pending_sources: next });
        const updated = await api.getSession(id);
        setSession(updated);
        setSrcStatus("saved");
      } catch {
        setSrcStatus("failed");
      }
    }, 600);
  };

  const handleFeatChange = async (next: FeaturizerConfig) => {
    if (!id) return;
    setFeatStatus("saving");
    setPendingFeatConfig(next);
    try {
      await api.updateConfig(id, { featurizer_config_patch: next });
      const updated = await api.getSession(id);
      setSession(updated);
      setFeatStatus("saved");
      setPendingFeatConfig(null);
    } catch {
      setFeatStatus("failed");
    }
  };

  const handleRerun = async () => {
    if (!id) return;
    await api.rerun(id, "data_gathering");
    router.push(`/sessions/${id}/activity`);
  };

  if (!featurizerConfig) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto h-full">
      {stale && (
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg text-xs flex-shrink-0">
          <span className="text-amber-600">⚠</span>
          <span className="text-amber-700">
            Timeframe or sources changed — results shown are from prior run.
          </span>
          <button
            onClick={handleRerun}
            className="ml-auto text-teal-600 underline underline-offset-2 whitespace-nowrap"
          >
            Re-run from data →
          </button>
        </div>
      )}

      {/* SESSION */}
      <div>
        <SectionLabel>Session</SectionLabel>
        <div className="border border-gray-200 rounded-lg p-3 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Market profile</span>
            <span className="bg-gray-100 text-gray-700 text-xs font-semibold px-2 py-0.5 rounded">
              {marketProfile ?? "—"}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-gray-500">Timeframe</span>
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={localStart}
                disabled={isRunning}
                onChange={(e) => setLocalStart(e.target.value)}
                onBlur={saveTimeframe}
                className="border border-gray-200 rounded px-2 py-1 text-xs font-mono outline-none focus:border-teal-400 disabled:opacity-40"
              />
              <span className="text-xs text-gray-400">→</span>
              <input
                type="date"
                value={localEnd}
                disabled={isRunning}
                onChange={(e) => setLocalEnd(e.target.value)}
                onBlur={saveTimeframe}
                className="border border-gray-200 rounded px-2 py-1 text-xs font-mono outline-none focus:border-teal-400 disabled:opacity-40"
              />
              <SaveIndicator status={tfStatus} onRetry={saveTimeframe} />
            </div>
          </div>
        </div>
      </div>

      {/* DATA SOURCES */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <SectionLabel>Data Sources</SectionLabel>
          <SaveIndicator
            status={srcStatus}
            onRetry={() => handleSourcesChange(localSources)}
          />
        </div>
        <ConnectorEditor
          available={connectors}
          value={localSources}
          onChange={handleSourcesChange}
          readOnly={isRunning}
        />
      </div>

      {/* FEATURIZER */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <SectionLabel>Featurizer</SectionLabel>
          <SaveIndicator
            status={featStatus}
            onRetry={() => pendingFeatConfig && handleFeatChange(pendingFeatConfig)}
          />
        </div>
        <FeaturizerConfigEditor
          value={featurizerConfig}
          onChange={stage === "user_review" ? handleFeatChange : undefined}
          readOnly={stage !== "user_review"}
        />
        {stage !== "user_review" && (
          <p className="text-xs text-gray-400 mt-2">Editable only during the review step.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify type-check passes**

```bash
cd frontend && npm run type-check
```

Expected: 0 errors. If `api.getArtifact` is not yet on the api object, add it (see note below).

> **Note:** `api.getArtifact` is used above. Verify it already exists in `api.ts`. If it does not, add it in this step:
>
> ```ts
> getArtifact: (sessionId: string, artifactId: string) =>
>   request<DataArtifactDetail>(`/api/sessions/${sessionId}/artifacts/${artifactId}`),
> ```

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/sessions/[id]/config/page.tsx"
git commit -m "feat: rebuild config page with Session, Data Sources, and Featurizer sections"
```

---

## Task 7: Frontend — stale banners on results pages

**Files:**
- Modify: `frontend/app/sessions/[id]/overview/page.tsx`
- Modify: `frontend/app/sessions/[id]/features/page.tsx`
- Modify: `frontend/app/sessions/[id]/backtest/page.tsx`

All three pages follow the same pattern: become client components, fetch the latest data artifact on mount, compute staleness, render the banner above the tab content.

- [ ] **Step 1: Update overview/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { OverviewTab } from "@/components/tabs/OverviewTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { DataArtifactDetail } from "@/lib/api";

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources } = useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as { connector_id: string }[],
        }
      : null,
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex-1 min-h-0">
        <OverviewTab result={{}} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update features/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { FeaturesTab } from "@/components/tabs/FeaturesTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { DataArtifactDetail } from "@/lib/api";

export default function FeaturesPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources } = useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as { connector_id: string }[],
        }
      : null,
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex-1 min-h-0">
        <FeaturesTab features={null} />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Update backtest/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BacktestTab } from "@/components/tabs/BacktestTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { DataArtifactDetail } from "@/lib/api";

export default function BacktestPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources } = useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as { connector_id: string }[],
        }
      : null,
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex-1 min-h-0">
        <BacktestTab backtest={null} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify type-check passes**

```bash
cd frontend && npm run type-check
```

Expected: 0 errors.

- [ ] **Step 5: Run the full test suite**

```bash
cd backend && uv run pytest && cd ../frontend && npm run test
```

Expected: all backend and frontend tests pass.

- [ ] **Step 6: Commit**

```bash
git add "frontend/app/sessions/[id]/overview/page.tsx" "frontend/app/sessions/[id]/features/page.tsx" "frontend/app/sessions/[id]/backtest/page.tsx"
git commit -m "feat: add stale results banner to overview, features, and backtest pages"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Editable timeframe (Session section, date inputs, onBlur save) — Task 6
- [x] Editable pending_sources (Data Sources section, ConnectorEditor) — Tasks 5, 6
- [x] Featurizer remains user_review-only — Task 2 (stage gate preserved)
- [x] `PATCH /sessions/{id}/config` accepts new fields — Tasks 1, 2
- [x] Stale detection: compare session vs latest artifact — Task 4 (stale.ts)
- [x] Stale warning on config page — Task 6 (inline amber banner + Re-run button)
- [x] Stale warning on results pages (overview, features, backtest) — Task 7
- [x] Save-then-rerun-separately UX — Task 6 (handleRerun navigates to activity page)
- [x] Running session blocks edits — Task 2 (status RUNNING → 409), Task 6 (`isRunning` disables inputs)
- [x] Store exposes marketProfile, timeframeStart, timeframeEnd, pendingSources — Task 3
- [x] `GET /api/connectors` + `ConnectorOut` — already implemented, no changes needed
- [x] `pending_sources` exposed in `SessionDetail` — Tasks 1, 2

**Type consistency:**
- `PendingSource` defined in `api.ts` (Task 3), used in `store.ts` (Task 3), `stale.ts` (Task 4), `ConnectorEditor.tsx` (Task 5), `config/page.tsx` (Task 6)
- `ConnectorOut` defined in `api.ts` (Task 3), used in `ConnectorEditor.tsx` (Task 5), `config/page.tsx` (Task 6)
- `DataArtifactDetail` already in `api.ts`, used in Tasks 6, 7
- `isSessionStale` parameter shape consistent between Tasks 4, 6, 7
- `api.updateConfig` new signature: `{ featurizer_config_patch?, timeframe_start?, timeframe_end?, pending_sources? }` — matches backend `ConfigPatchRequest`
- Config page calls `api.updateConfig(id, { featurizer_config_patch: next })` (not the old `api.updateConfig(id, next)`)
