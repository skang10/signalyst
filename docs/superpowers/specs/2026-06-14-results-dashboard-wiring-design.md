# Results Dashboard Wiring — Design

**Status:** Approved, not yet implemented.

## Context

The Results sub-pages (`app/sessions/[id]/{overview,features,backtest}/page.tsx`) are stub
placeholders left over from PR 4 work: each page passes a hardcoded empty/null value to its tab
component instead of fetching real data —

```tsx
<OverviewTab result={{}} />
<FeaturesTab features={null} />
<BacktestTab backtest={null} />
```

`OverviewTab` requires `regime` and `direction` to render anything; with `result={{}}` it always
hits the `!regime || !direction` branch and shows `TabPlaceholder` ("Analysis incomplete"). This
is the "Overview tab shows nothing" symptom.

There is also no backend endpoint that exposes `AnalysisResult` (the row written by
`src/services/tabpfn.py`'s `_run`, containing `regime`, `direction`, `feature_importance`,
`drift`, `backtest`, `summary`). `GET /api/sessions/{id}/artifacts/{artifact_id}` only looks up
`DataArtifact` rows.

### Scope

Of `AnalysisResult`'s fields, `_run` currently populates `regime`, `direction`, and `drift`.
`feature_importance` (SHAP) and `backtest` (walk-forward eval) are columns on the model but are
**never computed** — `FeaturesTab` and `BacktestTab` already have correct "not available"
placeholder branches for `features === null` / `backtest === null`, which is the true state today.

This spec covers:
- A new backend endpoint exposing the full `AnalysisResult` row (all fields, including the
  currently-always-null `feature_importance`/`backtest`, for forward compatibility).
- Wiring all three Results pages to fetch it and pass real data to their tabs.

Out of scope (separate follow-up): computing `feature_importance` (SHAP via
`tabpfn-extensions`) and `backtest` (wiring `src/eval/backtest.py` into `_run`). Until that
follow-up lands, `FeaturesTab`/`BacktestTab` will continue to show their "not computed"
placeholders — correctly, since `feature_importance`/`backtest` will still be `null`.

## 1. Backend — `GET /api/sessions/{id}/analysis/{artifact_id}`

New Pydantic model in `api/models.py`, sibling to `DataArtifactDetail`:

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

New route in `api/routes/pipeline.py`, mirroring `get_artifact` (`pipeline.py:526`):

```python
@router.get("/sessions/{session_id}/analysis/{artifact_id}", response_model=AnalysisResultDetail)
async def get_analysis_artifact(session_id: str, artifact_id: str, db: SessionDep) -> AnalysisResultDetail:
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

This is a separate endpoint (not folded into `get_artifact`'s `response_model`) to avoid a union
response type, and mirrors the existing `artifacts.analysis[].artifact_id` ref pattern the
frontend already has via `SessionArtifacts.analysis: AnalysisResultRef[]`.

## 2. Frontend — wire the three Results pages

`lib/api.ts`:
- Add `AnalysisResultDetail` type (mirrors the backend model). `regime`/`direction`/`drift`
  reuse the shapes already implicit in `OverviewTab`'s `RegimeResult`/`DirectionResult`/
  `DriftSummary`/`FeatureImportanceSummary`; `feature_importance`/`backtest` reuse
  `FeaturesTab`'s `FeatureImportanceResult` and `BacktestTab`'s `BacktestResult`. These small
  types are currently defined inline in the tab components (not exported) — duplicate minimal
  copies in `api.ts` rather than refactoring the tab components to export/share types (keeps
  this change additive and avoids touching tab component internals).
- Add `getAnalysisArtifact: (sessionId: string, artifactId: string) => request<AnalysisResultDetail>(\`/api/sessions/${sessionId}/analysis/${artifactId}\`)`.

Each of `overview/page.tsx`, `features/page.tsx`, `backtest/page.tsx` (currently near-identical):
- Add `latestAnalysis` state (`AnalysisResultDetail | null`), fetched the same way
  `latestArtifact` is today — `useEffect` on `artifacts.analysis.at(-1)`, calling
  `api.getAnalysisArtifact(id, artifact_id)`.
- Replace the hardcoded stub prop:
  - `overview/page.tsx`: `<OverviewTab result={{}} />` → `<OverviewTab result={latestAnalysis ?? {}} />`
  - `features/page.tsx`: `<FeaturesTab features={null} />` → `<FeaturesTab features={latestAnalysis?.feature_importance ?? null} />`
  - `backtest/page.tsx`: `<BacktestTab backtest={null} />` → `<BacktestTab backtest={latestAnalysis?.backtest ?? null} />`
- If `artifacts.analysis` is empty (analysis not yet run), `latestAnalysis` stays `null` and each
  tab's existing placeholder/`!regime` branches render correctly — no new empty-state UI needed.

## 3. Testing

- Backend: new tests in `tests/test_pipeline.py` mirroring
  `test_get_artifact_returns_data_artifact_detail` / `test_get_artifact_not_found_returns_404`:
  - Create a session, insert an `AnalysisResult` row directly via the test DB session, `GET
    /api/sessions/{id}/analysis/{artifact_id}`, assert `kind == "analysis"` and all fields
    round-trip.
  - 404 for a missing artifact id and for an artifact belonging to a different session.
- Frontend: extend `lib/__tests__/api.test.ts` with a `describe("api.getAnalysisArtifact", ...)`
  block mirroring the existing `api.getArtifact` tests (around `api.test.ts:126`).
- No new page-level tests — there are currently no tests under `app/sessions/[id]/**` for any
  page (component-level tests in `components/tabs/__tests__/` already cover tab rendering given
  props); page wiring changes are thin enough to be covered by the existing tab + api-client
  tests plus manual verification.

## Out of scope

- Computing `feature_importance` (SHAP) and `backtest` (walk-forward eval) in
  `src/services/tabpfn.py::_run` — separate follow-up.
- Any change to `get_artifact` / `DataArtifactDetail`.
- New empty-state UI for "analysis not yet run" — existing tab placeholders cover it.
