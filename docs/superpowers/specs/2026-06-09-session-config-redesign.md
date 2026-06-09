# Session Config Redesign Implementation Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple timeframe and data sources from session identity — make them visible and editable on the config page, with stale warnings on results pages when config has changed since the last run.

**Architecture:** Extend `PATCH /sessions/{id}/config` to accept timeframe and pending_sources patches (relaxing the `user_review`-only gate for those fields). Add `GET /api/connectors`. On the frontend, add a `ConnectorEditor` component and rebuild the config page with three stacked sections (Session, Data Sources, Featurizer). Stale detection is purely frontend — compare session's current timeframe/sources against the latest `DataArtifact`.

**Tech Stack:** FastAPI + SQLModel (backend), Next.js 15 App Router + Zustand + Tailwind CSS (frontend). No DB migrations required — all fields already exist on the `Session` model.

---

## Background

Sessions are currently anchored to a fixed `timeframe_start` / `timeframe_end` set at creation. Changing the timeframe requires creating a new session, which is poor UX for iterative analysis. The config page only shows featurizer settings; timeframe and data sources are invisible after session creation.

The `DataArtifact` model already has a `round` field anticipating re-runs within a session. The `/rerun` endpoint already supports `stage: "data_gathering"`. This spec wires up the missing pieces: editable timeframe/sources + stale signalling.

---

## Section 1 — Backend

### 1a. Extend `ConfigPatchRequest` and `PATCH /sessions/{id}/config`

**File:** `backend/api/models.py`

Add three optional fields to `ConfigPatchRequest`:

```python
class ConfigPatchRequest(BaseModel):
    featurizer_config_patch: dict[str, Any] | None = None
    timeframe_start: str | None = None          # ISO date string
    timeframe_end: str | None = None            # ISO date string
    pending_sources: list[dict[str, Any]] | None = None
```

**File:** `backend/api/routes/pipeline.py`

Relax the stage gate: `featurizer_config_patch` remains `user_review`-only. `timeframe_start`, `timeframe_end`, and `pending_sources` are editable whenever `status != RUNNING`.

```python
@router.patch("/sessions/{session_id}/config", response_model=ConfigPatchResponse)
async def update_config(session_id: str, req: ConfigPatchRequest, db: SessionDep) -> ConfigPatchResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if s.status == SessionStatus.RUNNING:
        raise HTTPException(status_code=409, detail="cannot update config while session is running")

    # featurizer config: user_review only
    if req.featurizer_config_patch is not None:
        if s.stage != SessionStage.USER_REVIEW:
            raise HTTPException(status_code=409, detail="featurizer config can only be edited during user_review")
        s.featurizer_config = apply_config_patch(s.featurizer_config, req.featurizer_config_patch)

    # timeframe + sources: any non-running state
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

### 1b. Add `GET /api/connectors`

**File:** `backend/api/routes/connectors.py` (new file)

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from src.db.models import Connector
from src.db.session import get_session
from typing import Annotated

router = APIRouter(tags=["connectors"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

@router.get("/connectors", response_model=list[ConnectorOut])
async def list_connectors(db: SessionDep) -> list[ConnectorOut]:
    rows = (await db.execute(select(Connector).where(Connector.is_active == True))).scalars().all()
    return [ConnectorOut(id=r.id, name=r.name, description=r.description, type=r.type) for r in rows]
```

**`ConnectorOut` model** added to `api/models.py`:

```python
class ConnectorOut(BaseModel):
    id: str
    name: str
    description: str
    type: str
```

Register the new router in `api/main.py`:

```python
from api.routes import connectors
app.include_router(connectors.router, prefix="/api")
```

---

## Section 2 — Frontend: Store + API types

### 2a. Session store (`frontend/lib/store.ts`)

Add four fields to `SessionStore`:

```ts
marketProfile: string | null;
timeframeStart: string | null;
timeframeEnd: string | null;
pendingSources: unknown[];
```

Update `setSession`:
```ts
marketProfile: session.market_profile,
timeframeStart: session.timeframe_start,
timeframeEnd: session.timeframe_end,
pendingSources: session.pending_sources ?? [],
```

Update `clearSession`:
```ts
marketProfile: null,
timeframeStart: null,
timeframeEnd: null,
pendingSources: [],
```

### 2b. API types and calls (`frontend/lib/api.ts`)

Add types:

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
};
```

Add `pending_sources` to the `Session` type:
```ts
pending_sources: PendingSource[];
```

Extend `updateConfig`:
```ts
updateConfig: (id: string, patch: {
  featurizer_config_patch?: FeaturizerConfig;
  timeframe_start?: string;
  timeframe_end?: string;
  pending_sources?: PendingSource[];
}) =>
  request<{ session_id: string }>(`/api/sessions/${id}/config`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  }),

getConnectors: () => request<ConnectorOut[]>("/api/connectors"),
```

---

## Section 3 — Frontend: ConnectorEditor component

**File:** `frontend/components/ConnectorEditor.tsx` (new file)

Props:
```ts
type Props = {
  available: ConnectorOut[];           // from GET /api/connectors
  value: PendingSource[];              // current session pending_sources
  onChange: (next: PendingSource[]) => void;
  readOnly?: boolean;
};
```

Behaviour:
- Each connector renders as a row: colored dot (teal = active, gray = inactive) + name + description + inline ticker input (visible only when active).
- Clicking a row toggles it active/inactive. When activated, it's added to `value` with empty `params`. When deactivated, it's removed from `value`.
- The ticker input (shown only for active connectors that have a `tickers` concept — currently only `yfinance`) edits `params.tickers` as a comma-separated string.
- When `readOnly`, rows are not clickable and the ticker input is disabled.

```tsx
"use client";
import type { ConnectorOut, PendingSource } from "@/lib/api";

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
    const tickers = raw.split(",").map((t) => t.trim()).filter(Boolean);
    onChange(value.map((s) =>
      s.connector_id === connectorId ? { ...s, params: { ...s.params, tickers } } : s
    ));
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="text-[10px] text-gray-400 px-3 py-2 border-b border-gray-100 bg-gray-50 font-mono uppercase tracking-widest">
        Click to toggle · active connectors used on next data run
      </div>
      {available.map((connector) => {
        const isActive = activeIds.has(connector.id);
        const source = value.find((s) => s.connector_id === connector.id);
        const tickers = (source?.params?.tickers as string[] | undefined)?.join(", ") ?? "";
        const showTickers = isActive && connector.id === "yfinance";

        return (
          <div
            key={connector.id}
            onClick={() => toggle(connector)}
            className={[
              "px-3 py-2.5 border-b border-gray-100 last:border-0 cursor-pointer transition-colors",
              isActive ? "bg-teal-50" : "bg-white opacity-60",
              readOnly ? "cursor-default" : "",
            ].join(" ")}
          >
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isActive ? "bg-teal-500" : "bg-gray-300"}`} />
              <span className={`text-sm font-medium ${isActive ? "text-teal-700" : "text-gray-400"}`}>
                {connector.name}
              </span>
              <span className="text-xs text-gray-400 truncate">{connector.description}</span>
            </div>
            {showTickers && (
              <div className="mt-1.5 flex items-center gap-2 ml-4" onClick={(e) => e.stopPropagation()}>
                <span className="text-[10px] text-gray-400 font-mono">Tickers:</span>
                <input
                  value={tickers}
                  onChange={(e) => setTickers(connector.id, e.target.value)}
                  disabled={readOnly}
                  className="flex-1 text-xs font-mono border border-teal-200 rounded px-2 py-0.5 bg-white outline-none focus:border-teal-400"
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

---

## Section 4 — Frontend: Config page rebuild

**File:** `frontend/app/sessions/[id]/config/page.tsx`

The page fetches connectors on mount (`api.getConnectors()`). It reads `marketProfile`, `timeframeStart`, `timeframeEnd`, `pendingSources` from the store alongside the existing `featurizerConfig`.

Three sections, each with its own save status:

**Session section** (editable when `status !== "running"`):
- Market profile: read-only gray chip
- Timeframe: two date `<input type="date">` fields; on blur, call `api.updateConfig(id, { timeframe_start, timeframe_end })`

**Data Sources section** (editable when `status !== "running"`):
- Renders `<ConnectorEditor>` with `available={connectors}` and `value={pendingSources}`
- On change, debounce 600 ms then call `api.updateConfig(id, { pending_sources })`

**Featurizer section** (existing, editable only during `user_review`):
- Renders `<FeaturizerConfigEditor>` unchanged
- The existing `api.updateConfig(id, next)` call becomes `api.updateConfig(id, { featurizer_config_patch: next })` to match the extended signature

**Stale banner** at top of page when stale (see Section 5 for stale logic). The "Re-run from data →" link in the banner calls `api.rerun(id, "data_gathering")` and navigates to the Activity page.

The lock/read-only copy (`Session config — read only`) is removed; instead each section independently shows its editability state.

---

## Section 5 — Frontend: Stale detection + results banners

### Stale detection hook (`frontend/lib/stale.ts` — new file)

`DataArtifactDetail` exposes `data_manifest.date_range` (for timeframe) and `sources` as a top-level field (for connector comparison) — both returned by `GET /sessions/{id}/artifacts/{artifact_id}`.

```ts
import type { PendingSource } from "./api";

export function isSessionStale(
  session: {
    timeframeStart: string | null;
    timeframeEnd: string | null;
    pendingSources: unknown[];
  },
  latestArtifact: {
    data_manifest: { date_range: { start: string; end: string } };
    sources: unknown[];
  } | null
): boolean {
  if (!latestArtifact) return false;
  const tfChanged =
    session.timeframeStart !== latestArtifact.data_manifest.date_range.start ||
    session.timeframeEnd !== latestArtifact.data_manifest.date_range.end;
  const sessionIds = (session.pendingSources as PendingSource[]).map((s) => s.connector_id).sort().join(",");
  const artifactIds = (latestArtifact.sources as { connector_id: string }[]).map((s) => s.connector_id).sort().join(",");
  const sourcesChanged = sessionIds !== artifactIds;
  return tfChanged || sourcesChanged;
}
```

The config page and results pages each fetch the latest data artifact via `api.getArtifact(sessionId, artifactId)` using the last entry in `artifacts.data` from the store.

### Stale banner component (`frontend/components/StaleResultsBanner.tsx` — new file)

```tsx
import Link from "next/link";
type Props = { sessionId: string; isStale: boolean };

export function StaleResultsBanner({ sessionId, isStale }: Props) {
  if (!isStale) return null;
  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs flex-shrink-0">
      <span className="text-amber-600">⚠</span>
      <span className="text-amber-700">Results from prior run — timeframe or sources have changed.</span>
      <Link href={`/sessions/${sessionId}/config`} className="text-amber-600 underline underline-offset-2 ml-1">
        Go to Config →
      </Link>
    </div>
  );
}
```

**Overview, Features, Backtest pages** each:
1. Read `artifacts.data` from the store to get the latest data artifact ID
2. Fetch the artifact manifest on mount
3. Compute `isStale` using `isSessionStale()`
4. Render `<StaleResultsBanner>` at the top of the page

---

## Files Changed

| File | Change |
|---|---|
| `backend/api/models.py` | Add `ConnectorOut`, extend `ConfigPatchRequest` |
| `backend/api/routes/pipeline.py` | Relax config patch stage gate |
| `backend/api/routes/connectors.py` | New — `GET /api/connectors` |
| `backend/api/main.py` | Register connectors router |
| `frontend/lib/store.ts` | Add marketProfile, timeframeStart, timeframeEnd, pendingSources |
| `frontend/lib/api.ts` | Add ConnectorOut, PendingSource, getConnectors, extend updateConfig |
| `frontend/lib/stale.ts` | New — isSessionStale() |
| `frontend/components/ConnectorEditor.tsx` | New — inline toggle connector selector |
| `frontend/components/StaleResultsBanner.tsx` | New — amber stale warning banner |
| `frontend/app/sessions/[id]/config/page.tsx` | Rebuild with 3 sections |
| `frontend/app/sessions/[id]/overview/page.tsx` | Add stale banner |
| `frontend/app/sessions/[id]/features/page.tsx` | Add stale banner |
| `frontend/app/sessions/[id]/backtest/page.tsx` | Add stale banner |

No DB migrations required.
