# Feature Importance Pipeline Wiring

## Problem

The Features page (`/sessions/<id>/features`) always shows "Feature importance not
available" — `AnalysisResult.feature_importance` is never set anywhere in the live
pipeline. The frontend (`FeaturesTab`, `OverviewTab`, `lib/api.ts`) is fully wired to
consume it; the gap is entirely on the backend.

The computation already exists — `_compute_feature_importance(clf, X, y, n_repeats)`
in `backend/src/agent/tools.py` — but it's only reachable through the `evaluate_features`
tool, built for an LLM ReAct agent loop that the live analyze pipeline
(`backend/src/services/tabpfn.py::_run`) never invokes. `_run` computes `regime`,
`direction`, and `drift` and persists them to `AnalysisResult`; it never touches
feature importance.

`backtest` has the identical gap (same pattern: orphaned agent-tool logic, never
wired into `_run`). Out of scope for this spec — tracked as a known follow-up, not
addressed here.

## Approach

Reuse `_compute_feature_importance` (a pure function, not coupled to `AgentContext`)
from inside `_run`'s existing `if settings.tabpfn_token:` block, right after the
regime classifier is fit and has produced test-set predictions. This is the same
gate already used for `regime_result`/`direction_result` — feature importance is
only meaningful paired with an actual fitted classifier, so when there's no token
(and therefore no regime/direction either), it stays `null`, consistent with
today's behavior.

Default to the Spearman-correlation path (`n_repeats=0`) — zero extra TabPFN API
calls, and the existing tool's own docstring calls this the "quick mode default".
Permutation importance (`n_repeats>0`) is not used here; it would add
`n_repeats × n_features + 1` TabPFN calls to every analysis run.

## Implementation

In `backend/src/services/tabpfn.py`:

1. Import `_compute_feature_importance` from `src.agent.tools` (no circular import —
   `tools.py` does not import from `services.tabpfn`).
2. Inside the `if settings.tabpfn_token:` block, after `regime_pred = regime_clf.predict(X_test)`:
   ```python
   importance_X = X_test.tail(50)
   importance_y = regime_labels_series.iloc[split:].tail(50)
   importance = _compute_feature_importance(regime_clf, importance_X, importance_y, n_repeats=0)
   ranked = sorted(zip(importance_X.columns, importance.tolist()), key=lambda x: x[1], reverse=True)
   feature_importance_result = {
       "top_features": [{"name": n, "importance": round(float(i), 4)} for n, i in ranked[:10]],
       "n_features_evaluated": len(importance_X.columns),
       "n_samples_explained": len(importance_X),
   }
   ```
   `tail(50)` and top-10 mirror the existing tool's `max_samples=50` / `top_n=10` defaults.
3. This sits inside the existing `try/except` around the regime/direction block, so a
   failure here logs `tabpfn.inference_failed` and leaves `feature_importance` as
   `null` — it does not fail the whole analysis run.
4. Pass `feature_importance=feature_importance_result` into the `AnalysisResult(...)`
   constructor alongside `regime`, `direction`, `drift`.

No frontend changes — `FeaturesTab.tsx` and `OverviewTab.tsx` already render this
correctly once the field is non-null.

## Testing

`test_tabpfn_service.py` currently has no test exercising the
`settings.tabpfn_token` branch at all (only the cache-hit path and the
`_make_regime_labels` helper are tested). Add one new test:

- Mock `settings.tabpfn_token` to a truthy value.
- Mock `src.inference.OilRegimeClassifier` / `DirectionClassifier` (same pattern
  already used in `test_deferred_tools.py`).
- Provide a small real feature-matrix parquet via a seeded `FeatureArtifact`.
- Run `_run` (or `run_tabpfn_service`) and assert the persisted
  `AnalysisResult.feature_importance` has the expected shape and top feature name.
