# Results Dashboard Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `AnalysisResult` (regime, direction, drift, feature_importance, backtest, summary) via a new backend endpoint and wire the Overview/Features/Backtest results pages to fetch and render it, replacing their hardcoded empty stubs.

**Architecture:** Add `GET /api/sessions/{id}/analysis/{artifact_id}` returning a new `AnalysisResultDetail` model (mirrors `DataArtifactDetail`'s pattern). On the frontend, add `AnalysisResultDetail`/`getAnalysisArtifact` to `lib/api.ts`, then update each of the three Results pages to fetch the latest analysis artifact (via `artifacts.analysis.at(-1)`, same pattern already used for `artifacts.data.at(-1)`) and pass real data into `OverviewTab`/`FeaturesTab`/`BacktestTab`.

**Tech Stack:** FastAPI, SQLModel, pytest (`asyncio_mode = "auto"`, sqlite in-memory), Next.js App Router, Vitest.

All backend commands assume `cd backend` first. All frontend commands assume `cd frontend` first.

---

## Reference: full spec

See `docs/superpowers/specs/2026-06-14-results-dashboard-wiring-design.md` for the approved design.

---

### Task 1: Backend — `AnalysisResultDetail` model + `GET /api/sessions/{id}/analysis/{artifact_id}`

**Files:**
- Modify: `backend/api/models.py` (add `AnalysisResultDetail` after `DataArtifactDetail`, line 152)
- Modify: `backend/api/routes/pipeline.py` (imports + new route after `get_artifact`, ~line 564)
- Test: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests for the new endpoint**

Append to `backend/tests/test_pipeline.py`:

```python
def test_get_analysis_artifact_returns_analysis_result_detail(client):
    import asyncio
    import uuid

    from src.db.models import AnalysisResult

    session_id = _create_session(client)
    artifact_id = uuid.uuid4()

    async def _seed() -> None:
        from api.main import app
        from src.db.session import get_session

        override = app.dependency_overrides[get_session]
        agen = override()
        db = await agen.__anext__()
        try:
            db.add(
                AnalysisResult(
                    id=artifact_id,
                    session_id=uuid.UUID(session_id),
                    feature_artifact_id=uuid.uuid4(),
                    regime={"regime": "bull_supercycle", "confidence": 0.8, "distribution": {"bull_supercycle": 10}},
                    direction={"direction": "up", "confidence": 0.7, "distribution": {"up": 8, "down": 2}},
                    feature_importance={
                        "top_features": [{"name": "CL=F_ret_5", "importance": 0.42}],
                        "n_features_evaluated": 12,
                        "n_samples_explained": 20,
                    },
                    drift={"psi_score": 0.05, "drift_detected": False},
                    backtest={
                        "strategy_sharpe": 1.2,
                        "benchmark_sharpe": 0.8,
                        "regime_accuracy": 0.65,
                        "n_windows": 5,
                    },
                    summary="Markets are in a bull supercycle.",
                )
            )
            await db.commit()
        finally:
            await agen.aclose()

    asyncio.run(_seed())

    res = client.get(f"/api/sessions/{session_id}/analysis/{artifact_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "analysis"
    assert body["artifact_id"] == str(artifact_id)
    assert body["regime"]["regime"] == "bull_supercycle"
    assert body["direction"]["direction"] == "up"
    assert body["feature_importance"]["top_features"][0]["name"] == "CL=F_ret_5"
    assert body["drift"]["psi_score"] == 0.05
    assert body["backtest"]["strategy_sharpe"] == 1.2
    assert body["summary"] == "Markets are in a bull supercycle."
    assert body["cache_hit"] is False
    assert body["cached_from_session_id"] is None


def test_get_analysis_artifact_not_found_returns_404(client):
    session_id = _create_session(client)
    res = client.get(
        f"/api/sessions/{session_id}/analysis/00000000-0000-0000-0000-000000000000"
    )
    assert res.status_code == 404


def test_get_analysis_artifact_wrong_session_returns_404(client):
    import asyncio
    import uuid
    from datetime import date

    from src.db.models import AnalysisResult, SessionStage, SessionStatus
    from src.db.models import Session as SessionModel

    session_id = _create_session(client)
    other_session_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    async def _seed() -> None:
        from api.main import app
        from src.db.session import get_session

        override = app.dependency_overrides[get_session]
        agen = override()
        db = await agen.__anext__()
        try:
            db.add(
                SessionModel(
                    id=other_session_id,
                    market_profile="oil",
                    timeframe_start=date(2023, 1, 1),
                    timeframe_end=date(2023, 6, 30),
                    stage=SessionStage.FOLLOW_UP.value,
                    status=SessionStatus.WAITING.value,
                    conversation=[],
                )
            )
            db.add(
                AnalysisResult(
                    id=artifact_id,
                    session_id=other_session_id,
                    feature_artifact_id=uuid.uuid4(),
                )
            )
            await db.commit()
        finally:
            await agen.aclose()

    asyncio.run(_seed())

    res = client.get(f"/api/sessions/{session_id}/analysis/{artifact_id}")
    assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline.py -v -k get_analysis_artifact`
Expected: all three FAIL — `404 Not Found` (route doesn't exist yet).

- [ ] **Step 3: Add `AnalysisResultDetail` to `api/models.py`**

In `backend/api/models.py`, after the `DataArtifactDetail` class (after line 152, before `class ConnectorOut`):

```python
class AnalysisResultDetail(BaseModel):
    kind: str = "analysis"
    artifact_id: str
    regime: dict[str, object] | None
    direction: dict[str, object] | None
    feature_importance: dict[str, object] | None
    drift: dict[str, object] | None
    backtest: dict[str, object] | None
    summary: str | None
    cache_hit: bool
    cached_from_session_id: str | None
```

- [ ] **Step 4: Add the route in `api/routes/pipeline.py`**

Update the `api.models` import block (currently lines 25-32) to add `AnalysisResultDetail`:

```python
from api.models import (
    AnalysisResultDetail,
    CancelResponse,
    ConfigPatchRequest,
    ConfigPatchResponse,
    DataArtifactDetail,
    ProceedRequest,
```

Update the `src.db.models` import (line 37) to add `AnalysisResult`:

```python
from src.db.models import AnalysisResult, DataArtifact, SessionStage, SessionStatus, UploadedSource
```

After the existing `get_artifact` function (ends around line 564), add:

```python
@router.get(
    "/sessions/{session_id}/analysis/{artifact_id}", response_model=AnalysisResultDetail
)
async def get_analysis_artifact(
    session_id: str, artifact_id: str, db: SessionDep
) -> AnalysisResultDetail:
    try:
        s_uid = uuid.UUID(session_id)
        a_uid = uuid.UUID(artifact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")

    artifact = await db.get(AnalysisResult, a_uid)
    if artifact is None or artifact.session_id != s_uid:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return AnalysisResultDetail(
        artifact_id=str(artifact.id),
        regime=artifact.regime,
        direction=artifact.direction,
        feature_importance=artifact.feature_importance,
        drift=artifact.drift,
        backtest=artifact.backtest,
        summary=artifact.summary,
        cache_hit=artifact.cache_hit,
        cached_from_session_id=(
            str(artifact.cached_from_session_id) if artifact.cached_from_session_id else None
        ),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_pipeline.py -v -k get_analysis_artifact`
Expected: all three PASS.

- [ ] **Step 6: Run the full backend test suite**

Run: `uv run python -m pytest -q`
Expected: all tests PASS (235 + 3 new = 238).

- [ ] **Step 7: Lint**

Run: `uv run ruff check .`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add api/models.py api/routes/pipeline.py tests/test_pipeline.py
git commit -m "feat(backend): add GET /api/sessions/{id}/analysis/{artifact_id} endpoint"
```

---

### Task 2: Frontend — `AnalysisResultDetail` type + `getAnalysisArtifact` API client

**Files:**
- Modify: `frontend/lib/api.ts` (add types after `DataArtifactDetail`, ~line 163; add method to `api` object, ~line 276)
- Test: `frontend/lib/__tests__/api.test.ts`

- [ ] **Step 1: Write failing test for `api.getAnalysisArtifact`**

Append to `frontend/lib/__tests__/api.test.ts`, after the `describe("api.getArtifact", ...)` block:

```typescript
describe("api.getAnalysisArtifact", () => {
  it("fetches analysis result detail", async () => {
    const { api } = await import("../api");
    mockOk({
      kind: "analysis",
      artifact_id: "ar-1",
      regime: { regime: "bull_supercycle", confidence: 0.8, distribution: { bull_supercycle: 10 } },
      direction: { direction: "up", confidence: 0.7, distribution: { up: 8, down: 2 } },
      feature_importance: {
        top_features: [{ name: "CL=F_ret_5", importance: 0.42 }],
        n_features_evaluated: 12,
        n_samples_explained: 20,
      },
      drift: { psi_score: 0.05, drift_detected: false },
      backtest: { strategy_sharpe: 1.2, benchmark_sharpe: 0.8, regime_accuracy: 0.65, n_windows: 5 },
      summary: "Markets are in a bull supercycle.",
      cache_hit: false,
      cached_from_session_id: null,
    });
    const result = await api.getAnalysisArtifact("ses-1", "ar-1");
    expect(result.kind).toBe("analysis");
    expect(result.regime?.regime).toBe("bull_supercycle");
    expect(result.feature_importance?.top_features[0].name).toBe("CL=F_ret_5");
    expect(result.backtest?.strategy_sharpe).toBe(1.2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- lib/__tests__/api.test.ts`
Expected: FAIL — `api.getAnalysisArtifact is not a function`.

- [ ] **Step 3: Add types and method to `lib/api.ts`**

In `frontend/lib/api.ts`, after the `DataArtifactDetail` type (after line 163, before `export const api = {`):

```typescript
export type RegimeResult = {
  regime: string;
  confidence: number;
  distribution: Record<string, number>;
};

export type DirectionResult = {
  direction: string;
  confidence: number;
  distribution: Record<string, number>;
};

export type DriftSummary = {
  psi_score: number;
  drift_detected: boolean;
};

export type FeatureImportanceResult = {
  top_features: { name: string; importance: number }[];
  n_features_evaluated: number;
  n_samples_explained: number;
};

export type BacktestResult = {
  strategy_sharpe: number;
  benchmark_sharpe: number;
  regime_accuracy: number;
  n_windows: number;
};

export type AnalysisResultDetail = {
  kind: "analysis";
  artifact_id: string;
  regime: RegimeResult | null;
  direction: DirectionResult | null;
  feature_importance: FeatureImportanceResult | null;
  drift: DriftSummary | null;
  backtest: BacktestResult | null;
  summary: string | null;
  cache_hit: boolean;
  cached_from_session_id: string | null;
};
```

Then add to the `api` object, after `getArtifact`:

```typescript
  getAnalysisArtifact: (sessionId: string, artifactId: string) =>
    request<AnalysisResultDetail>(`/api/sessions/${sessionId}/analysis/${artifactId}`),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- lib/__tests__/api.test.ts`
Expected: PASS.

- [ ] **Step 5: Type-check**

Run: `npm run type-check`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add lib/api.ts lib/__tests__/api.test.ts
git commit -m "feat(frontend): add AnalysisResultDetail type and getAnalysisArtifact API client"
```

---

### Task 3: Wire `overview/page.tsx` to real `AnalysisResult` data

**Files:**
- Modify: `frontend/app/sessions/[id]/overview/page.tsx`

- [ ] **Step 1: Add `latestAnalysis` state and fetch effect, and pass it to `OverviewTab`**

Replace the full contents of `frontend/app/sessions/[id]/overview/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { OverviewTab } from "@/components/tabs/OverviewTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { AnalysisResultDetail, DataArtifactDetail, PendingSource } from "@/lib/api";

export default function OverviewPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources } = useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResultDetail | null>(null);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  useEffect(() => {
    const last = artifacts.analysis.at(-1);
    if (!id || !last) return;
    api.getAnalysisArtifact(id, last.artifact_id).then(setLatestAnalysis).catch(() => {});
  }, [id, artifacts.analysis]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as PendingSource[],
        }
      : null,
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex-1 min-h-0">
        <OverviewTab result={latestAnalysis ?? {}} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `npm run type-check`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add app/sessions/\[id\]/overview/page.tsx
git commit -m "feat(frontend): fetch and render real AnalysisResult on overview page"
```

---

### Task 4: Wire `features/page.tsx` to real `feature_importance` data

**Files:**
- Modify: `frontend/app/sessions/[id]/features/page.tsx`

- [ ] **Step 1: Add `latestAnalysis` state and fetch effect, and pass it to `FeaturesTab`**

Replace the full contents of `frontend/app/sessions/[id]/features/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { FeaturesTab } from "@/components/tabs/FeaturesTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { AnalysisResultDetail, DataArtifactDetail, PendingSource } from "@/lib/api";

export default function FeaturesPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources } = useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResultDetail | null>(null);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  useEffect(() => {
    const last = artifacts.analysis.at(-1);
    if (!id || !last) return;
    api.getAnalysisArtifact(id, last.artifact_id).then(setLatestAnalysis).catch(() => {});
  }, [id, artifacts.analysis]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as PendingSource[],
        }
      : null,
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex-1 min-h-0">
        <FeaturesTab features={latestAnalysis?.feature_importance ?? null} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `npm run type-check`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add app/sessions/\[id\]/features/page.tsx
git commit -m "feat(frontend): fetch and render real feature importance on features page"
```

---

### Task 5: Wire `backtest/page.tsx` to real `backtest` data

**Files:**
- Modify: `frontend/app/sessions/[id]/backtest/page.tsx`

- [ ] **Step 1: Add `latestAnalysis` state and fetch effect, and pass it to `BacktestTab`**

Replace the full contents of `frontend/app/sessions/[id]/backtest/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { BacktestTab } from "@/components/tabs/BacktestTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type { AnalysisResultDetail, DataArtifactDetail, PendingSource } from "@/lib/api";

export default function BacktestPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources } = useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResultDetail | null>(null);

  useEffect(() => {
    const last = artifacts.data.at(-1);
    if (!id || !last) return;
    api.getArtifact(id, last.artifact_id).then(setLatestArtifact).catch(() => {});
  }, [id, artifacts.data]);

  useEffect(() => {
    const last = artifacts.analysis.at(-1);
    if (!id || !last) return;
    api.getAnalysisArtifact(id, last.artifact_id).then(setLatestAnalysis).catch(() => {});
  }, [id, artifacts.analysis]);

  const stale = isSessionStale(
    { timeframeStart, timeframeEnd, pendingSources },
    latestArtifact
      ? {
          data_manifest: { date_range: latestArtifact.data_manifest.date_range },
          sources: latestArtifact.sources as PendingSource[],
        }
      : null,
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {id && <StaleResultsBanner sessionId={id} isStale={stale} />}
      <div className="flex-1 min-h-0">
        <BacktestTab backtest={latestAnalysis?.backtest ?? null} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `npm run type-check`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add app/sessions/\[id\]/backtest/page.tsx
git commit -m "feat(frontend): fetch and render real backtest results on backtest page"
```

---

### Task 6: Full verification

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && uv run python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 2: Run backend lint**

Run: `cd backend && uv run ruff check .`
Expected: no errors.

- [ ] **Step 3: Run the full frontend test suite**

Run: `cd frontend && npm run test`
Expected: all tests PASS.

- [ ] **Step 4: Run frontend lint and type-check**

Run: `cd frontend && npm run lint && npm run type-check`
Expected: no errors.

- [ ] **Step 5: Confirm no remaining hardcoded stub props**

Run: `grep -rn "result={{}}\|features={null}\|backtest={null}" frontend/app/sessions/`
Expected: no matches.

---

## Out of scope (do not touch)

- Computing `feature_importance` (SHAP) and `backtest` in `src/services/tabpfn.py::_run` — these remain `null` until a separate follow-up wires SHAP/walk-forward eval into the pipeline. `FeaturesTab`/`BacktestTab` will correctly show their "not available" placeholders until then.
- `get_artifact` / `DataArtifactDetail` — unchanged.
- Any new empty-state UI — existing tab placeholders (`TabPlaceholder`) cover the "analysis not yet run" case.
