# Feature Importance Pipeline Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Features page (`/sessions/<id>/features`) show real SHAP/correlation feature importance instead of always showing "not available", by computing and persisting `AnalysisResult.feature_importance` in the live analyze pipeline.

**Architecture:** Add a small pure helper `_feature_importance(clf, X_test, y_test)` to `backend/src/services/tabpfn.py`, alongside the file's existing pure helpers (`_psi`, `_detect_drift`, `_make_regime_labels`). It reuses the already-implemented `_compute_feature_importance` Spearman-correlation logic from `backend/src/agent/tools.py` (lazily imported, matching this file's existing lazy-import-of-`src.inference` pattern). Call it from `_run`'s existing `if settings.tabpfn_token:` block, right after the regime classifier produces its test-set predictions, and persist the result onto the `AnalysisResult` row the same way `regime`/`direction`/`drift` already are.

**Tech Stack:** Python, pandas/numpy, pytest + pytest-asyncio, SQLModel, in-memory SQLite for tests (existing pattern in `test_tabpfn_service.py`).

## Global Constraints

- Spearman correlation only (`n_repeats=0`) — no permutation importance, no extra TabPFN API calls. (Per approved design spec `docs/superpowers/specs/2026-06-21-feature-importance-pipeline-wiring-design.md`.)
- Feature importance is only computed inside the existing `if settings.tabpfn_token:` branch — same gate as `regime_result`/`direction_result`. When there's no token, it stays `null`, same as today.
- No frontend changes. `frontend/components/tabs/FeaturesTab.tsx` and `frontend/components/tabs/OverviewTab.tsx` already render `feature_importance` correctly once it is non-null.
- Out of scope: `backtest` has the identical gap but is explicitly not addressed in this plan.

---

### Task 1: Add `_feature_importance` helper with unit test

**Files:**
- Modify: `backend/src/services/tabpfn.py` (add function after `_detect_drift`, before `async def run_tabpfn_service`)
- Test: `backend/tests/test_tabpfn_service.py`

**Interfaces:**
- Produces: `_feature_importance(clf: Any, X_test: pd.DataFrame, y_test: pd.Series, max_samples: int = 50, top_n: int = 10) -> dict[str, Any]` — returned dict shape: `{"top_features": [{"name": str, "importance": float}, ...], "n_features_evaluated": int, "n_samples_explained": int}`. Task 2 calls this directly.

- [ ] **Step 1: Write the failing test**

Open `backend/tests/test_tabpfn_service.py`. Add this test anywhere after the existing imports (e.g. right after `test_tabpfn_cache_hit_transitions_to_explaining_and_chains_explanation`):

```python
def test_feature_importance_ranks_by_correlation_and_caps_samples() -> None:
    from src.services.tabpfn import _feature_importance

    n = 20
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    y = pd.Series(["a", "b"] * (n // 2), index=dates, name="regime")
    X = pd.DataFrame(
        {
            "f_corr": [0, 1] * (n // 2),  # perfectly tracks y
            "f_other": np.sin(np.linspace(0, 10, n)),  # unrelated pattern
        },
        index=dates,
    )

    result = _feature_importance(clf=None, X_test=X, y_test=y, max_samples=10, top_n=2)

    assert result["top_features"][0]["name"] == "f_corr"
    assert result["top_features"][0]["importance"] == 1.0
    assert len(result["top_features"]) == 2
    assert result["n_features_evaluated"] == 2
    assert result["n_samples_explained"] == 10
```

This requires `numpy` to be imported as `np` in the test file — check the top of `backend/tests/test_tabpfn_service.py`; it is not currently imported. Add `import numpy as np` to the existing import block (alphabetically, before `import pandas as pd`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_tabpfn_service.py::test_feature_importance_ranks_by_correlation_and_caps_samples -v`
Expected: FAIL with `ImportError: cannot import name '_feature_importance'` (or similar — the function doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

In `backend/src/services/tabpfn.py`, add this function immediately after `_detect_drift` (i.e. right after its closing `}` / `return` block, before the blank lines that precede `async def run_tabpfn_service`):

```python
def _feature_importance(
    clf: Any, X_test: pd.DataFrame, y_test: pd.Series, max_samples: int = 50, top_n: int = 10
) -> dict[str, Any]:
    from src.agent.tools import _compute_feature_importance

    X = X_test.tail(max_samples) if max_samples > 0 else X_test
    y = y_test.loc[X.index]
    importance = _compute_feature_importance(clf, X, y, n_repeats=0)
    ranked = sorted(zip(X.columns, importance.tolist()), key=lambda x: x[1], reverse=True)
    top = [{"name": name, "importance": round(float(imp), 4)} for name, imp in ranked[:top_n]]
    return {
        "top_features": top,
        "n_features_evaluated": len(X.columns),
        "n_samples_explained": len(X),
    }
```

Note: the `from src.agent.tools import _compute_feature_importance` is deliberately a *local* import inside the function, not a top-level import — `src/agent/tools.py` imports `src.inference` (`OilRegimeClassifier`, `DirectionClassifier`) at its own module top level, and `tabpfn.py` already avoids importing `src.inference` eagerly (it does the same `from src.inference import ...` lazily inside `_run`, guarded behind `if settings.tabpfn_token:`). Keep that pattern.

`Any` and `pd` are already imported at the top of `tabpfn.py` — no new top-level imports needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_tabpfn_service.py::test_feature_importance_ranks_by_correlation_and_caps_samples -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd backend && git add src/services/tabpfn.py tests/test_tabpfn_service.py
git commit -m "feat(analysis): add _feature_importance helper to tabpfn pipeline"
```

---

### Task 2: Wire `_feature_importance` into `_run` and persist on `AnalysisResult`

**Files:**
- Modify: `backend/src/services/tabpfn.py` (`_run` function and the `AnalysisResult(...)` construction)
- Test: `backend/tests/test_tabpfn_service.py`

**Interfaces:**
- Consumes: `_feature_importance(clf, X_test, y_test, max_samples=50, top_n=10) -> dict[str, Any]` from Task 1.
- Produces: `AnalysisResult.feature_importance` is non-null after `_run` executes the `settings.tabpfn_token` branch successfully. This is what `frontend/components/tabs/FeaturesTab.tsx` (via `api.getAnalysisArtifact` → `AnalysisResultDetail.feature_importance`) consumes — no further consumers in this plan.

- [ ] **Step 1: Write the failing test**

Add this test to `backend/tests/test_tabpfn_service.py`. It needs `select` from `sqlmodel` (not currently imported) — change the existing line `from sqlmodel import SQLModel` to `from sqlmodel import SQLModel, select`. It also needs `from unittest.mock import AsyncMock, patch` (already imported) and `tmp_path` (a built-in pytest fixture, no import needed).

```python
@pytest.mark.asyncio
async def test_tabpfn_run_persists_feature_importance(tmp_path) -> None:
    engine = await _make_engine()
    session_id = uuid.uuid4()
    da_id = uuid.uuid4()
    fa_id = uuid.uuid4()

    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    features = pd.DataFrame(
        {
            "CL=F_close": np.linspace(70.0, 90.0, n),
            "f1": np.linspace(1.0, 2.0, n),
            "f2": np.sin(np.linspace(0, 10, n)),
        },
        index=dates,
    )
    matrix_path = tmp_path / "features.parquet"
    features.to_parquet(matrix_path)

    fixed_labels = pd.Series(["range_bound", "trend_up"] * (n // 2), index=dates, name="regime")

    async with AsyncSession(engine) as db:
        db.add(
            SessionModel(
                id=session_id,
                market_profile="oil",
                timeframe_start=date(2024, 1, 1),
                timeframe_end=date(2024, 6, 1),
                stage=SessionStage.ANALYZING.value,
                status=SessionStatus.RUNNING.value,
            )
        )
        db.add(
            DataArtifact(
                id=da_id,
                session_id=session_id,
                data_manifest={"tickers": ["CL=F"]},
                source_hash="src-hash",
            )
        )
        db.add(
            FeatureArtifact(
                id=fa_id,
                session_id=session_id,
                data_artifact_id=da_id,
                matrix_hash="matrix-hash-2",
                feature_matrix_ref=str(matrix_path),
            )
        )
        db.add(
            MarketProfile(
                id="oil",
                name="Oil Markets",
                default_connectors=["yfinance", "fred", "eia", "gpr"],
                default_connector_params={
                    "yfinance": {"tickers": ["CL=F", "BZ=F", "DX-Y.NYB"]},
                    "fred": {"series_ids": ["INDPRO"]},
                },
                default_featurizer_config={},
                regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
                regime_thresholds={"trend_up": 0.15, "trend_down": -0.15, "spike": 0.08},
                primary_ticker="CL=F",
            )
        )
        await db.commit()

    fake_redis = _FakeRedis()
    with (
        patch("src.services.tabpfn.aioredis.Redis.from_url", return_value=fake_redis),
        patch("src.services.tabpfn.settings.tabpfn_token", "fake-token"),
        patch("src.services.tabpfn._make_regime_labels", return_value=fixed_labels),
        patch("src.inference.OilRegimeClassifier") as MockRegimeCls,
        patch("src.inference.DirectionClassifier") as MockDirCls,
        patch("src.services.tabpfn.run_explanation_service", new_callable=AsyncMock),
    ):
        # predict()/predict_proba() return fixed values regardless of call args, so the
        # index/length of these mocks doesn't need to match the real train/test split —
        # downstream code only does value_counts().idxmax() and column .mean() on them.
        regime_inst = MockRegimeCls.return_value
        regime_inst.predict.return_value = pd.Series(["range_bound"] * 5, name="regime")
        regime_inst.predict_proba.return_value = pd.DataFrame({"range_bound": [0.8] * 5})

        dir_inst = MockDirCls.return_value
        dir_inst.predict.return_value = pd.Series(["up"] * 5, name="direction")
        dir_inst.predict_proba.return_value = pd.DataFrame({"up": [0.6] * 5})

        await run_tabpfn_service(session_id, engine)

    async with AsyncSession(engine) as db:
        ar = (
            (
                await db.execute(
                    select(AnalysisResult).where(AnalysisResult.session_id == session_id)
                )
            )
            .scalars()
            .first()
        )

    assert ar is not None
    assert ar.feature_importance is not None
    assert set(ar.feature_importance.keys()) == {
        "top_features",
        "n_features_evaluated",
        "n_samples_explained",
    }
    assert ar.feature_importance["n_features_evaluated"] == 3
    assert len(ar.feature_importance["top_features"]) <= 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_tabpfn_service.py::test_tabpfn_run_persists_feature_importance -v`
Expected: FAIL at `assert ar.feature_importance is not None` (it will be `None`, since `_run` doesn't compute or pass it yet).

If instead it fails earlier with an unrelated error (e.g. an `AssertionError`/exception swallowed silently leaving everything `None`, or a DB/setup error), that means one of the mocks doesn't match what `_run` actually does at that line in the current code — re-check against the live `backend/src/services/tabpfn.py` source (regime/direction classifier call shapes can shift) before changing the implementation.

- [ ] **Step 3: Write minimal implementation**

In `backend/src/services/tabpfn.py`, inside `_run`:

1. Find the line:
   ```python
   regime_result: dict[str, Any] | None = None
   direction_result: dict[str, Any] | None = None
   ```
   and add a third line:
   ```python
   regime_result: dict[str, Any] | None = None
   direction_result: dict[str, Any] | None = None
   feature_importance_result: dict[str, Any] | None = None
   ```

2. Find where `regime_result` is assigned:
   ```python
   regime_result = {
       "regime": top_regime,
       "confidence": top_conf,
       "distribution": regime_pred.value_counts().to_dict(),
   }
   ```
   Immediately after this dict literal (still inside the `try` block, before the `dir_clf = DirectionClassifier(...)` line), add:
   ```python
   feature_importance_result = _feature_importance(
       regime_clf, X_test, regime_labels_series.iloc[split:]
   )
   ```

3. Find the `AnalysisResult(...)` construction:
   ```python
   ar = AnalysisResult(
       id=artifact_id,
       session_id=session_id,
       feature_artifact_id=fa.id,
       regime=regime_result,
       direction=direction_result,
       drift=drift,
       feature_hash=feature_hash,
   )
   ```
   Add `feature_importance=feature_importance_result,` (placed next to `regime`/`direction`/`drift` for readability):
   ```python
   ar = AnalysisResult(
       id=artifact_id,
       session_id=session_id,
       feature_artifact_id=fa.id,
       regime=regime_result,
       direction=direction_result,
       feature_importance=feature_importance_result,
       drift=drift,
       feature_hash=feature_hash,
   )
   ```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_tabpfn_service.py::test_tabpfn_run_persists_feature_importance -v`
Expected: PASS

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && uv run python -m pytest`
Expected: all tests pass (no regressions in `test_tabpfn_service.py` or elsewhere — in particular, confirm the pre-existing `test_tabpfn_cache_hit_transitions_to_explaining_and_chains_explanation` test still passes, since it shares fixtures/helpers with the new test).

- [ ] **Step 6: Lint and type-check**

Run: `cd backend && uv run ruff check . && uv run mypy .`
Expected: no errors. (`Any` typed dict return on `_feature_importance` should satisfy mypy given the existing patterns in this file.)

- [ ] **Step 7: Commit**

```bash
cd backend && git add src/services/tabpfn.py tests/test_tabpfn_service.py
git commit -m "feat(analysis): persist feature importance from the live analyze pipeline"
```

---

## Manual verification (after both tasks)

This closes a real gap end-to-end, so after Task 2 is committed, manually confirm against a running backend with `TABPFN_TOKEN` set:

1. `make dev-backend` and `make dev-frontend` (or `make dev`).
2. Run a session through to completion (regime + direction must both compute, i.e. `tabpfn_token` must be set in `.env` — without it, `feature_importance` will still correctly stay `null`, same as before).
3. Open `http://localhost:3000/sessions/<session-id>/features`.
4. Confirm the SHAP Feature Importance panel renders bars instead of the "Feature importance not available" placeholder, and that `OverviewTab`'s "top signal" line also now shows a real feature name instead of `—`.
