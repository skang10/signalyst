# Features Tab Redesign — Model Card, Feature Generation Summary, Featurizer Config

## Problem

The Features page (`/sessions/<id>/features`) only shows a flat list of the top-10
SHAP/correlation feature-importance bars (`FeaturesTab.tsx`, fed by
`AnalysisResult.feature_importance`, wired up in PR #88). It gives no sense of:

- **What model produced these scores.** Today this is not persisted anywhere — it's
  hardcoded in `backend/src/services/tabpfn.py::_run` (`OilRegimeClassifier`, backed by
  `tabpfn_client.TabPFNClassifier`, `n_estimators=4`). Notably, feature importance is
  computed only against the *regime* classifier, not the direction classifier, which
  isn't obvious from the UI.
- **How many features were generated overall, and from what.** The featurizer
  produces ~100+ candidate features across families (`rolling_stats`, `lag`,
  `momentum`), but only the top 10 by importance are visible. The family breakdown
  and total count live in `FeatureArtifact.feature_manifest`, which has no API
  endpoint today.
- **What configuration produced this run's features** (windows, lags, enabled
  families, energy-specific flag) — available client-side already via the session
  store (`featurizerConfig`), but not currently shown on this page.

## Approach

Add three pieces of information to the Features tab, each independently optional so
the existing top-10 list keeps working unchanged if any piece is missing (e.g. on
older cached `AnalysisResult` rows from before this change):

1. **Model card** — nested inside `feature_importance.model_info`, not a new
   top-level `AnalysisResult` field, because it specifically documents what produced
   *these* importance scores (the regime classifier), not the whole analysis run.
2. **Feature generation summary** — total feature count, row count, and a
   family-count breakdown, sourced from the existing `FeatureArtifact.feature_manifest`
   via a new dedicated endpoint, following the established one-endpoint-per-artifact-type
   convention (`/artifacts/{id}` for data, `/analysis/{id}` for analysis — now
   `/features/{id}` for the feature artifact).
3. **Featurizer config used** — windows/lags/families/energy-specific flag, returned
   by the same new endpoint (`FeatureArtifact.featurizer_config_snapshot`).

## Backend changes

### 1. Persist model metadata alongside feature importance

`backend/src/inference/classifier.py` — `OilRegimeClassifier.__init__` currently
takes `n_estimators` but doesn't expose it. Add:

```python
def __init__(self, n_estimators: int = 8) -> None:
    if settings.tabpfn_token:
        tabpfn_client.set_access_token(settings.tabpfn_token)
    self.n_estimators = n_estimators
    self._clf = TabPFNClassifier(n_estimators=n_estimators)
    self._fitted = False
```

`backend/src/services/tabpfn.py::_run` — immediately after the existing
`feature_importance_result = _feature_importance(regime_clf, X_test, regime_labels_series.iloc[split:])`
call, add:

```python
feature_importance_result["model_info"] = {
    "name": "TabPFN",
    "task": "regime_classification",
    "n_estimators": regime_clf.n_estimators,
}
```

This reads the actual value used to construct `regime_clf` rather than duplicating
the literal `4` a second time, so the two can't drift out of sync.

### 2. New endpoint: `GET /api/sessions/{session_id}/features/{artifact_id}`

`backend/api/models.py` — new response model:

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

`family_counts` (not `feature_families`) deliberately avoids colliding with the
existing `FeaturizerConfig.feature_families`, which is a list of *enabled* family
names, not a count breakdown — these are different shapes and need different names
in the same response.

`backend/api/routes/pipeline.py` — new route, mirroring `get_analysis_artifact`
exactly in structure:

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

## Frontend changes

### `frontend/lib/api.ts`

- Add `model_info?: { name: string; task: string; n_estimators: number }` to the
  existing `FeatureImportanceResult` type.
- Add `FeatureArtifactDetail` type, matching the backend model field-for-field.
- Add `getFeatureArtifact: (sessionId: string, artifactId: string) => request<FeatureArtifactDetail>(\`/api/sessions/${sessionId}/features/${artifactId}\`)`,
  next to `getArtifact` / `getAnalysisArtifact`.

### `frontend/app/sessions/[id]/features/page.tsx`

Add a third independent fetch, parallel to the existing `latestArtifact` /
`latestAnalysis` ones:

```ts
const [latestFeatureArtifact, setLatestFeatureArtifact] = useState<FeatureArtifactDetail | null>(null);

useEffect(() => {
  const last = artifacts.features.at(-1);
  if (!id || !last) return;
  api.getFeatureArtifact(id, last.artifact_id).then(setLatestFeatureArtifact).catch(() => {});
}, [id, artifacts.features]);
```

Pass `featureArtifact={latestFeatureArtifact}` into `<FeaturesTab>` alongside the
existing `features={latestAnalysis?.feature_importance ?? null}` prop.

### `frontend/components/tabs/FeaturesTab.tsx`

`Props` becomes `{ features: FeatureImportanceResult | null; featureArtifact: FeatureArtifactDetail | null }`.

The existing top-10 SHAP bars section is unchanged. Two new cards are added above
it, styled consistently with the house pattern already established in
`OverviewTab.tsx` / `DriftTab.tsx` (white card, `border-gray-200`, `text-[10px]
uppercase tracking-widest font-mono` section header):

- **Model card** — rendered only if `features?.model_info` is present (older cached
  results won't have it — omitted, not a placeholder). One line:
  `TabPFN · Regime Classifier · 4 ensemble members`.
- **Feature generation card** — rendered only if `featureArtifact` is present
  (independent of whether `features` loaded — the two fetches are unrelated).
  Shows `n_features` / `n_rows`, a small bar-per-family breakdown of `family_counts`
  (reusing the `DistBar`-style horizontal bar), and the featurizer config that
  produced them (windows, lags, energy-specific flag) from `featureArtifact.featurizer_config`.

Both new cards degrade independently and silently (simply omitted, no error state)
if their data isn't available — the tab still works exactly as it does today if
only `feature_importance` loads.

## Testing

- `backend/tests/test_inference.py` — assert `OilRegimeClassifier(n_estimators=4).n_estimators == 4`.
- `backend/tests/test_tabpfn_service.py` — extend the existing
  `test_tabpfn_run_persists_feature_importance` (added in PR #88) to also assert
  `ar.feature_importance["model_info"] == {"name": "TabPFN", "task": "regime_classification", "n_estimators": 4}`.
- `backend/tests/test_pipeline.py` — add `test_get_feature_artifact_returns_feature_artifact_detail`
  and `test_get_feature_artifact_not_found_returns_404`, mirroring
  `test_get_analysis_artifact_returns_analysis_result_detail` / `test_get_analysis_artifact_not_found_returns_404` exactly.
- `frontend/components/tabs/__tests__/FeaturesTab.test.tsx` — add cases for: model
  card renders when `model_info` present; model card omitted when absent; feature
  generation card renders family counts and featurizer config when `featureArtifact`
  present; feature generation card omitted when `featureArtifact` is null. Existing
  tests (placeholder, top-features list, footer counts) stay unchanged.

## Out of scope

- Full feature list beyond the top 10 (not requested).
- Showing `direction` model metadata (the importance scores only ever explain the
  regime classifier, so there's nothing direction-specific to show here).
- Backtest tab (separate, pre-existing gap, not part of this work).
