# Features Tab Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show "model used", a feature-generation summary, and the featurizer config on the Features page, in addition to the existing top-10 SHAP bars.

**Architecture:** Persist model metadata into `AnalysisResult.feature_importance.model_info` (it documents what produced those specific scores, not the whole analysis). Add a new `GET /api/sessions/{session_id}/features/{artifact_id}` endpoint exposing `FeatureArtifact.feature_manifest` + `featurizer_config_snapshot`, mirroring the existing one-endpoint-per-artifact-type convention. Wire both into `FeaturesTab.tsx` as two new optional cards above the existing bars.

**Tech Stack:** Python/FastAPI/SQLModel (backend), Next.js/React/TypeScript/Vitest (frontend).

## Global Constraints

- `model_info` lives nested inside `feature_importance`, not as a new top-level `AnalysisResult` field — it only explains the regime classifier, not the whole analysis. (Per approved spec `docs/superpowers/specs/2026-06-22-features-tab-redesign-design.md`.)
- New endpoint field is named `family_counts`, not `feature_families` — `FeaturizerConfig.feature_families` (a list of enabled family names) already uses that name for a different shape (list, not count dict); reusing it would collide.
- Both new UI cards (model card, feature-generation card) must degrade independently and silently (simply omitted) when their backing data is null/missing — never render an error or a second placeholder. The existing top-10 SHAP section and its "not available" placeholder are unchanged.
- Out of scope: full feature list beyond top 10, direction-classifier model info, Backtest tab.

---

### Task 1: Persist model metadata alongside feature importance

**Files:**
- Modify: `backend/src/inference/classifier.py:35-39` (`OilRegimeClassifier.__init__`)
- Modify: `backend/src/services/tabpfn.py:255-262` (`_run`, right after `feature_importance_result` is computed)
- Test: `backend/tests/test_inference.py`
- Test: `backend/tests/test_tabpfn_service.py`

**Interfaces:**
- Produces: `OilRegimeClassifier.n_estimators: int` (public attribute, readable after construction). `AnalysisResult.feature_importance["model_info"] = {"name": str, "task": str, "n_estimators": int}` when the `tabpfn_token` branch in `_run` succeeds.

- [ ] **Step 1: Write the failing test for the classifier attribute**

Add to `backend/tests/test_inference.py`, after the existing imports/helpers (e.g. right after `test_regime_predict_returns_series_with_correct_index`, around line 55):

```python
def test_regime_classifier_exposes_n_estimators():
    with patch("src.inference.classifier.TabPFNClassifier") as MockCLF:
        MockCLF.return_value = _mock_clf(REGIME_CLASSES, REGIME_PROBA)
        clf = OilRegimeClassifier(n_estimators=4)

    assert clf.n_estimators == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_inference.py::test_regime_classifier_exposes_n_estimators -v`
Expected: FAIL with `AttributeError: 'OilRegimeClassifier' object has no attribute 'n_estimators'`

- [ ] **Step 3: Write minimal implementation**

In `backend/src/inference/classifier.py`, change:

```python
    def __init__(self, n_estimators: int = 8) -> None:
        if settings.tabpfn_token:
            tabpfn_client.set_access_token(settings.tabpfn_token)
        self._clf = TabPFNClassifier(n_estimators=n_estimators)
        self._fitted = False
```

to:

```python
    def __init__(self, n_estimators: int = 8) -> None:
        if settings.tabpfn_token:
            tabpfn_client.set_access_token(settings.tabpfn_token)
        self.n_estimators = n_estimators
        self._clf = TabPFNClassifier(n_estimators=n_estimators)
        self._fitted = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_inference.py::test_regime_classifier_exposes_n_estimators -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for model_info in the live pipeline**

In `backend/tests/test_tabpfn_service.py`, find the existing `test_tabpfn_run_persists_feature_importance` test (added in PR #88) and add these three lines right after the existing `assert len(ar.feature_importance["top_features"]) <= 10` line:

```python
    assert ar.feature_importance["model_info"] == {
        "name": "TabPFN",
        "task": "regime_classification",
        "n_estimators": 4,
    }
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_tabpfn_service.py::test_tabpfn_run_persists_feature_importance -v`
Expected: FAIL with `KeyError: 'model_info'`

- [ ] **Step 7: Write minimal implementation**

In `backend/src/services/tabpfn.py`, change:

```python
            feature_importance_result = _feature_importance(
                regime_clf, X_test, regime_labels_series.iloc[split:]
            )

            dir_clf = DirectionClassifier(n_estimators=4)
```

to:

```python
            feature_importance_result = _feature_importance(
                regime_clf, X_test, regime_labels_series.iloc[split:]
            )
            feature_importance_result["model_info"] = {
                "name": "TabPFN",
                "task": "regime_classification",
                "n_estimators": regime_clf.n_estimators,
            }

            dir_clf = DirectionClassifier(n_estimators=4)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_tabpfn_service.py::test_tabpfn_run_persists_feature_importance -v`
Expected: PASS

Also update that test's existing shape assertion so it doesn't break — find this line in the same test:

```python
    assert set(ar.feature_importance.keys()) == {
        "top_features",
        "n_features_evaluated",
        "n_samples_explained",
    }
```

and change it to:

```python
    assert set(ar.feature_importance.keys()) == {
        "top_features",
        "n_features_evaluated",
        "n_samples_explained",
        "model_info",
    }
```

- [ ] **Step 9: Run the full backend test suite**

Run: `cd backend && uv run python -m pytest`
Expected: all tests pass.

- [ ] **Step 10: Lint and type-check**

Run: `cd backend && uv run ruff check . && uv run mypy .`
Expected: no new errors (pre-existing unrelated mypy errors in other files are fine — confirmed in PR #88 they exist on `main` regardless of this work).

- [ ] **Step 11: Commit**

```bash
cd backend && git add src/inference/classifier.py src/services/tabpfn.py tests/test_inference.py tests/test_tabpfn_service.py
git commit -m "feat(analysis): persist model metadata alongside feature importance"
```

---

### Task 2: Add `GET /api/sessions/{session_id}/features/{artifact_id}` endpoint

**Files:**
- Modify: `backend/api/models.py` (add `FeatureArtifactDetail` after `AnalysisResultDetail`, around line 165)
- Modify: `backend/api/routes/pipeline.py` (add import + new route after `get_analysis_artifact`, around line 593)
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `FeatureArtifact` model fields `feature_manifest: dict[str, Any]` (keys: `n_features`, `n_rows`, `feature_families`, `columns`) and `featurizer_config_snapshot: dict[str, Any]` — both already populated by `backend/src/services/featurizer.py` (no changes needed there).
- Produces: `FeatureArtifactDetail` Pydantic model — `{kind: "features", artifact_id: str, n_features: int, n_rows: int, family_counts: dict[str, int], columns: list[str], featurizer_config: dict[str, object], cache_hit: bool, created_at: str}`. Task 3's frontend type must match this field-for-field.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_pipeline.py`, right after the existing `test_get_analysis_artifact_not_found_returns_404` test:

```python
def test_get_feature_artifact_returns_feature_artifact_detail(client):
    import asyncio
    import uuid

    from src.db.models import FeatureArtifact

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
                FeatureArtifact(
                    id=artifact_id,
                    session_id=uuid.UUID(session_id),
                    data_artifact_id=uuid.uuid4(),
                    featurizer_config_snapshot={
                        "windows": [5, 20, 60],
                        "lags": [1, 5, 20],
                        "feature_families": ["rolling_stats", "lag", "momentum"],
                        "energy_specific": True,
                    },
                    feature_manifest={
                        "n_features": 108,
                        "n_rows": 22,
                        "feature_families": {"rolling_stats": 48, "lag": 30, "momentum": 30},
                        "columns": ["CL=F_mean_5d", "CL=F_lag_1d"],
                    },
                )
            )
            await db.commit()
        finally:
            await agen.aclose()

    asyncio.run(_seed())

    res = client.get(f"/api/sessions/{session_id}/features/{artifact_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "features"
    assert body["artifact_id"] == str(artifact_id)
    assert body["n_features"] == 108
    assert body["n_rows"] == 22
    assert body["family_counts"] == {"rolling_stats": 48, "lag": 30, "momentum": 30}
    assert body["columns"] == ["CL=F_mean_5d", "CL=F_lag_1d"]
    assert body["featurizer_config"]["windows"] == [5, 20, 60]
    assert body["cache_hit"] is False


def test_get_feature_artifact_not_found_returns_404(client):
    session_id = _create_session(client)
    res = client.get(f"/api/sessions/{session_id}/features/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_pipeline.py::test_get_feature_artifact_returns_feature_artifact_detail tests/test_pipeline.py::test_get_feature_artifact_not_found_returns_404 -v`
Expected: both FAIL with `404` for the first (route doesn't exist, FastAPI returns 404 for unknown routes) — confirm the failure is "route not found", not a server error.

- [ ] **Step 3: Write minimal implementation — response model**

In `backend/api/models.py`, add this class immediately after `AnalysisResultDetail` (after its closing `cached_from_session_id: str | None` line, before `class ConnectorOut`):

```python
class FeatureArtifactDetail(BaseModel):
    kind: str = "features"
    artifact_id: str
    n_features: int
    n_rows: int
    family_counts: dict[str, int]
    columns: list[str]
    featurizer_config: dict[str, object]
    cache_hit: bool
    created_at: str
```

- [ ] **Step 4: Write minimal implementation — route**

In `backend/api/routes/pipeline.py`, change the import line:

```python
from src.db.models import AnalysisResult, DataArtifact, SessionStage, SessionStatus, UploadedSource
```

to:

```python
from src.db.models import (
    AnalysisResult,
    DataArtifact,
    FeatureArtifact,
    SessionStage,
    SessionStatus,
    UploadedSource,
)
```

Then add this route immediately after `get_analysis_artifact`'s closing `)` (the end of the existing function, right after the line `cached_from_session_id=(\n            str(artifact.cached_from_session_id) if artifact.cached_from_session_id else None\n        ),\n    )`):

```python
@router.get("/sessions/{session_id}/features/{artifact_id}", response_model=FeatureArtifactDetail)
async def get_feature_artifact(
    session_id: str, artifact_id: str, db: SessionDep
) -> FeatureArtifactDetail:
    try:
        s_uid = uuid.UUID(session_id)
        a_uid = uuid.UUID(artifact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")

    artifact = await db.get(FeatureArtifact, a_uid)
    if artifact is None or artifact.session_id != s_uid:
        raise HTTPException(status_code=404, detail="Artifact not found")

    manifest = artifact.feature_manifest
    return FeatureArtifactDetail(
        artifact_id=str(artifact.id),
        n_features=manifest.get("n_features", 0),
        n_rows=manifest.get("n_rows", 0),
        family_counts=manifest.get("feature_families", {}),
        columns=manifest.get("columns", []),
        featurizer_config=artifact.featurizer_config_snapshot,
        cache_hit=artifact.cache_hit,
        created_at=artifact.created_at.isoformat(),
    )
```

Also change the `from api.models import (...)` block near the top of `backend/api/routes/pipeline.py` from:

```python
from api.models import (
    AnalysisResultDetail,
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

to:

```python
from api.models import (
    AnalysisResultDetail,
    CancelResponse,
    ConfigPatchRequest,
    ConfigPatchResponse,
    DataArtifactDetail,
    FeatureArtifactDetail,
    ProceedRequest,
    ProceedResponse,
    RerunRequest,
    RerunResponse,
    SeriesPoint,
    UploadResponse,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_pipeline.py::test_get_feature_artifact_returns_feature_artifact_detail tests/test_pipeline.py::test_get_feature_artifact_not_found_returns_404 -v`
Expected: both PASS

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && uv run python -m pytest`
Expected: all tests pass.

- [ ] **Step 7: Lint and type-check**

Run: `cd backend && uv run ruff check . && uv run mypy .`
Expected: no new errors.

- [ ] **Step 8: Commit**

```bash
cd backend && git add api/models.py api/routes/pipeline.py tests/test_pipeline.py
git commit -m "feat(api): add GET /sessions/{id}/features/{artifact_id} endpoint"
```

---

### Task 3: Add frontend API client for the new endpoint

**Files:**
- Modify: `frontend/lib/api.ts`
- Test: `frontend/lib/__tests__/api.test.ts`

**Interfaces:**
- Consumes: `GET /api/sessions/{session_id}/features/{artifact_id}` from Task 2, response shape `{kind: "features", artifact_id: string, n_features: number, n_rows: number, family_counts: Record<string, number>, columns: string[], featurizer_config: object, cache_hit: boolean, created_at: string}`.
- Produces: `FeatureArtifactDetail` TypeScript type, `api.getFeatureArtifact(sessionId: string, artifactId: string): Promise<FeatureArtifactDetail>`. Also extends `FeatureImportanceResult` with optional `model_info`. Task 4 consumes both.

- [ ] **Step 1: Write the failing test**

Add to `frontend/lib/__tests__/api.test.ts`, right after the existing `describe("api.getAnalysisArtifact", ...)` block:

```ts
describe("api.getFeatureArtifact", () => {
  it("fetches feature artifact detail", async () => {
    const { api } = await import("../api");
    mockOk({
      kind: "features",
      artifact_id: "fa-1",
      n_features: 108,
      n_rows: 22,
      family_counts: { rolling_stats: 48, lag: 30, momentum: 30 },
      columns: ["CL=F_mean_5d"],
      featurizer_config: {
        windows: [5, 20, 60],
        lags: [1, 5, 20],
        feature_families: ["rolling_stats", "lag", "momentum"],
        energy_specific: true,
      },
      cache_hit: false,
      created_at: "2026-06-22T00:00:00",
    });
    const result = await api.getFeatureArtifact("ses-1", "fa-1");
    expect(result.kind).toBe("features");
    expect(result.n_features).toBe(108);
    expect(result.family_counts.rolling_stats).toBe(48);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- api.test.ts`
Expected: FAIL with a TypeScript/runtime error — `api.getFeatureArtifact is not a function`.

- [ ] **Step 3: Write minimal implementation**

In `frontend/lib/api.ts`, add `model_info` to the existing `FeatureImportanceResult` type — change:

```ts
export type FeatureImportanceResult = {
  top_features: { name: string; importance: number }[];
  n_features_evaluated: number;
  n_samples_explained: number;
};
```

to:

```ts
export type FeatureImportanceResult = {
  top_features: { name: string; importance: number }[];
  n_features_evaluated: number;
  n_samples_explained: number;
  model_info?: { name: string; task: string; n_estimators: number };
};
```

Then add a new type immediately after the existing `AnalysisResultDetail` type definition:

```ts
export type FeatureArtifactDetail = {
  kind: "features";
  artifact_id: string;
  n_features: number;
  n_rows: number;
  family_counts: Record<string, number>;
  columns: string[];
  featurizer_config: FeaturizerConfig;
  cache_hit: boolean;
  created_at: string;
};
```

Finally, add the client function right after the existing `getAnalysisArtifact` entry in the `export const api = {...}` object:

```ts
  getAnalysisArtifact: (sessionId: string, artifactId: string) =>
    request<AnalysisResultDetail>(`/api/sessions/${sessionId}/analysis/${artifactId}`),

  getFeatureArtifact: (sessionId: string, artifactId: string) =>
    request<FeatureArtifactDetail>(`/api/sessions/${sessionId}/features/${artifactId}`),
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- api.test.ts`
Expected: PASS

- [ ] **Step 5: Type-check**

Run: `cd frontend && npm run type-check`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd frontend && git add lib/api.ts lib/__tests__/api.test.ts
git commit -m "feat(api-client): add getFeatureArtifact and model_info type"
```

---

### Task 4: Wire the new data into the Features page UI

**Files:**
- Modify: `frontend/app/sessions/[id]/features/page.tsx`
- Modify: `frontend/components/tabs/FeaturesTab.tsx`
- Test: `frontend/components/tabs/__tests__/FeaturesTab.test.tsx`

**Interfaces:**
- Consumes: `api.getFeatureArtifact` and `FeatureArtifactDetail` from Task 3; `artifacts.features: FeatureArtifactRef[]` already exists on the Zustand session store (`frontend/lib/store.ts`) — no store changes needed.
- Produces: `FeaturesTab` component now takes `{ features: FeatureImportanceResult | null; featureArtifact: FeatureArtifactDetail | null }` (was `{ features }` only). No other component imports `FeaturesTab` besides `frontend/app/sessions/[id]/features/page.tsx` — confirmed by checking the build after this change (Step 8).

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `frontend/components/tabs/__tests__/FeaturesTab.test.tsx` with:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { FeaturesTab } from "../FeaturesTab";

const features = {
  top_features: [
    { name: "rsi_14", importance: 0.42 },
    { name: "macd_signal", importance: 0.27 },
    { name: "eia_storage", importance: 0.15 },
  ],
  n_features_evaluated: 20,
  n_samples_explained: 100,
};

const featuresWithModelInfo = {
  ...features,
  model_info: { name: "TabPFN", task: "regime_classification", n_estimators: 4 },
};

const featureArtifact = {
  kind: "features" as const,
  artifact_id: "fa-1",
  n_features: 108,
  n_rows: 22,
  family_counts: { rolling_stats: 48, lag: 30, momentum: 30 },
  columns: ["CL=F_mean_5d"],
  featurizer_config: {
    windows: [5, 20, 60],
    lags: [1, 5, 20],
    feature_families: ["rolling_stats", "lag", "momentum"],
    energy_specific: true,
  },
  cache_hit: false,
  created_at: "2026-06-22T00:00:00",
};

describe("FeaturesTab", () => {
  it("renders feature names and importance values", () => {
    render(<FeaturesTab features={features} featureArtifact={null} />);
    expect(screen.getByText("rsi_14")).toBeTruthy();
    expect(screen.getByText("0.420")).toBeTruthy();
    expect(screen.getByText("macd_signal")).toBeTruthy();
    expect(screen.getByText("eia_storage")).toBeTruthy();
  });

  it("renders footer with feature count and sample count", () => {
    render(<FeaturesTab features={features} featureArtifact={null} />);
    expect(screen.getByText(/20 features/)).toBeTruthy();
    expect(screen.getByText(/100 samples/)).toBeTruthy();
  });

  it("renders placeholder when features is null", () => {
    render(<FeaturesTab features={null} featureArtifact={null} />);
    expect(screen.getByText(/feature importance not available/i)).toBeTruthy();
  });

  it("renders the model card when model_info is present", () => {
    render(<FeaturesTab features={featuresWithModelInfo} featureArtifact={null} />);
    expect(screen.getByText(/TabPFN/)).toBeTruthy();
    expect(screen.getByText(/Regime Classification/)).toBeTruthy();
    expect(screen.getByText(/4 ensemble members/)).toBeTruthy();
  });

  it("omits the model card when model_info is absent", () => {
    render(<FeaturesTab features={features} featureArtifact={null} />);
    expect(screen.queryByText(/ensemble members/)).toBeNull();
  });

  it("renders the feature generation card when featureArtifact is present", () => {
    render(<FeaturesTab features={features} featureArtifact={featureArtifact} />);
    expect(screen.getByText(/108 features/)).toBeTruthy();
    expect(screen.getByText(/22 rows/)).toBeTruthy();
    expect(screen.getByText("rolling_stats")).toBeTruthy();
  });

  it("omits the feature generation card when featureArtifact is null", () => {
    render(<FeaturesTab features={features} featureArtifact={null} />);
    expect(screen.queryByText(/rolling_stats/)).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd frontend && npm run test -- FeaturesTab.test.tsx`
Expected: the 4 new tests FAIL (component doesn't accept `featureArtifact` prop or render `model_info`/family data yet); the 3 original tests should still PASS since they only check pre-existing behavior with a new no-op prop.

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `frontend/components/tabs/FeaturesTab.tsx` with:

```tsx
import { TabPlaceholder } from "./TabPlaceholder";

type FeatureEntry = { name: string; importance: number };
type ModelInfo = { name: string; task: string; n_estimators: number };
type FeatureImportanceResult = {
  top_features: FeatureEntry[];
  n_features_evaluated: number;
  n_samples_explained: number;
  model_info?: ModelInfo;
};
type FeatureArtifactDetail = {
  n_features: number;
  n_rows: number;
  family_counts: Record<string, number>;
  featurizer_config: {
    windows: number[];
    lags: number[];
    feature_families: string[];
    energy_specific: boolean;
  };
};
type Props = {
  features: FeatureImportanceResult | null;
  featureArtifact: FeatureArtifactDetail | null;
};

function formatTaskLabel(task: string): string {
  return task
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function FamilyBar({ label, count, max }: { label: string; count: number; max: number }) {
  return (
    <div className="flex items-center gap-2 text-xs font-mono">
      <div className="w-24 text-right text-gray-500 truncate">{label}</div>
      <div className="flex-1 bg-gray-100 rounded h-2 overflow-hidden">
        <div
          className="h-full rounded bg-brand"
          style={{ width: `${max > 0 ? (count / max) * 100 : 0}%` }}
        />
      </div>
      <div className="w-8 text-gray-400 text-right">{count}</div>
    </div>
  );
}

export function FeaturesTab({ features, featureArtifact }: Props) {
  if (!features) {
    return (
      <TabPlaceholder
        icon="≡"
        title="Feature importance not available"
        reason="Not computed in this run. Enable in Full mode or add evaluate_features to tasks."
      />
    );
  }

  const max = features.top_features[0]?.importance ?? 1;
  const familyEntries = featureArtifact ? Object.entries(featureArtifact.family_counts) : [];
  const maxFamilyCount =
    familyEntries.length > 0 ? Math.max(...familyEntries.map(([, c]) => c)) : 0;

  return (
    <div className="p-4 flex flex-col gap-3 h-full overflow-y-auto">
      {features.model_info && (
        <div className="bg-white border border-gray-200 rounded p-4 flex flex-col gap-1">
          <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-1">
            Model
          </div>
          <div className="text-xs text-gray-700 font-mono">
            {features.model_info.name} · {formatTaskLabel(features.model_info.task)} ·{" "}
            {features.model_info.n_estimators} ensemble members
          </div>
        </div>
      )}

      {featureArtifact && (
        <div className="bg-white border border-gray-200 rounded p-4 flex flex-col gap-2">
          <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-1">
            Feature Generation
          </div>
          <div className="text-xs text-gray-700 font-mono">
            {featureArtifact.n_features} features · {featureArtifact.n_rows} rows
          </div>
          <div className="flex flex-col gap-1 mt-1">
            {familyEntries.map(([family, count]) => (
              <FamilyBar key={family} label={family} count={count} max={maxFamilyCount} />
            ))}
          </div>
          <div className="text-[10px] text-gray-400 font-mono pt-2 border-t border-gray-200">
            windows {featureArtifact.featurizer_config.windows.join(",")} · lags{" "}
            {featureArtifact.featurizer_config.lags.join(",")}
            {featureArtifact.featurizer_config.energy_specific ? " · energy-specific" : ""}
          </div>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded p-4 flex flex-col gap-2 flex-1">
        <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-2">
          SHAP Feature Importance
        </div>
        <div className="flex flex-col gap-2 flex-1 overflow-y-auto">
          {features.top_features.map((f, i) => (
            <div key={f.name} className="flex items-center gap-2">
              <div className="w-32 text-right text-xs text-gray-500 font-mono truncate">
                {f.name}
              </div>
              <div className="flex-1 bg-gray-100 rounded h-3 overflow-hidden">
                <div
                  className="h-full rounded"
                  style={{
                    width: `${(f.importance / max) * 100}%`,
                    background: "var(--color-brand)",
                    opacity: 1 - i * 0.06,
                  }}
                />
              </div>
              <div className="w-12 text-right text-xs text-gray-400 font-mono">
                {f.importance.toFixed(3)}
              </div>
            </div>
          ))}
        </div>
        <div className="text-[10px] text-gray-400 font-mono pt-2 border-t border-gray-200">
          {features.n_features_evaluated} features · {features.n_samples_explained} samples · SHAP
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test -- FeaturesTab.test.tsx`
Expected: all 9 tests PASS.

- [ ] **Step 5: Wire the page to fetch the feature artifact and pass it down**

In `frontend/app/sessions/[id]/features/page.tsx`, change:

```tsx
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

to:

```tsx
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { FeaturesTab } from "@/components/tabs/FeaturesTab";
import { StaleResultsBanner } from "@/components/StaleResultsBanner";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { isSessionStale } from "@/lib/stale";
import type {
  AnalysisResultDetail,
  DataArtifactDetail,
  FeatureArtifactDetail,
  PendingSource,
} from "@/lib/api";

export default function FeaturesPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts, timeframeStart, timeframeEnd, pendingSources } = useSessionStore();
  const [latestArtifact, setLatestArtifact] = useState<DataArtifactDetail | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResultDetail | null>(null);
  const [latestFeatureArtifact, setLatestFeatureArtifact] = useState<FeatureArtifactDetail | null>(
    null,
  );

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

  useEffect(() => {
    const last = artifacts.features.at(-1);
    if (!id || !last) return;
    api.getFeatureArtifact(id, last.artifact_id).then(setLatestFeatureArtifact).catch(() => {});
  }, [id, artifacts.features]);

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
        <FeaturesTab
          features={latestAnalysis?.feature_importance ?? null}
          featureArtifact={latestFeatureArtifact}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run the full frontend test suite**

Run: `cd frontend && npm run test`
Expected: all tests pass (no regressions in other components that might reference `FeaturesTab`).

- [ ] **Step 7: Type-check and lint**

Run: `cd frontend && npm run type-check && npm run lint`
Expected: no errors.

- [ ] **Step 8: Confirm no other callers of `FeaturesTab` were missed**

Run: `cd frontend && grep -rn "FeaturesTab" --include="*.tsx" --include="*.ts" app components | grep -v __tests__`
Expected: only two matches — the export in `components/tabs/FeaturesTab.tsx` itself and the usage in `app/sessions/[id]/features/page.tsx`. If there are others, update them to pass `featureArtifact` too before continuing.

- [ ] **Step 9: Commit**

```bash
cd frontend && git add app/sessions/\[id\]/features/page.tsx components/tabs/FeaturesTab.tsx components/tabs/__tests__/FeaturesTab.test.tsx
git commit -m "feat(features-tab): show model card and feature generation summary"
```

---

## Manual verification (after all tasks)

This is a real user-facing UI change, so visually confirm it before considering the work done:

1. `make dev-backend` and `make dev-frontend` (or reuse already-running dev servers — they hot-reload).
2. Create a session via `POST /api/sessions` with `{"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30", "auto": true}` (requires `TABPFN_TOKEN` / `ANTHROPIC_API_KEY` in `.env`, and Redis/Postgres running), and poll `GET /api/sessions/{id}` until `stage` reaches `explaining` or later.
3. Open `http://localhost:3000/sessions/<session-id>/features` in a browser (or via Playwright) and confirm: a Model card reading something like "TabPFN · Regime Classification · 4 ensemble members", a Feature Generation card showing total features/rows and a family breakdown, the existing windows/lags/energy-specific line, and the unchanged SHAP bars below.
4. Confirm an *older* session (created before this change, analyzed under PR #88 without `model_info`) still renders its Features page without errors — the model card should simply be absent, everything else unchanged.
