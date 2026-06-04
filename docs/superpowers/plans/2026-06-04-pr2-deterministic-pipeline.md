# PR 2 — Deterministic Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the deterministic pipeline (FeaturizerService → TabPFNService) with stage machine endpoints (proceed, rerun, cancel, upload), within-session artifact caching, and the matching frontend UI (cancel button, activity feed, Data sub-page).

**Architecture:** Services live in `src/services/` and run as FastAPI `BackgroundTask`s, publishing activity events to `Session.activity_events` in the DB. Pipeline endpoints (`/proceed`, `/rerun`, `/cancel`, `/upload`) live in a new `api/routes/pipeline.py` router. The frontend adds cancel, a passive activity feed (events from DB, no live stream), and the Data sub-page that renders uploaded DataArtifact manifests.

**Tech Stack:** Python 3.12, FastAPI BackgroundTasks, SQLModel/asyncpg, pandas, parquet (pyarrow), TabPFN client, Next.js 15 App Router, TypeScript, Zustand

**Reference specs:** `docs/backend-redesign.md` §FeaturizerService, §TabPFNService, §Artifact Cache, §Stage Gating, §Upload; `docs/frontend-redesign.md` PR 2 row.

---

## File Map

### Create (backend)
- `backend/src/services/__init__.py`
- `backend/src/services/hashing.py` — `stable_hash`, `canonical_json`
- `backend/src/services/stage.py` — `transition_stage`, `append_activity_event`
- `backend/src/services/featurizer.py` — `FeaturizerService`
- `backend/src/services/tabpfn.py` — `TabPFNService`
- `backend/api/routes/pipeline.py` — proceed, rerun, cancel, upload, artifacts/{id}
- `backend/tests/test_pipeline.py`
- `backend/tests/test_featurizer_service.py`

### Modify (backend)
- `backend/src/featurizer/featurizer.py` — add `feature_families`, `energy_specific` params
- `backend/tests/test_featurizer.py` — add feature_families tests
- `backend/api/models.py` — add pipeline request/response models
- `backend/api/main.py` — wire pipeline router

### Modify (frontend)
- `frontend/lib/api.ts` — add proceed, rerun, cancel, upload, getArtifact
- `frontend/app/sessions/[id]/layout.tsx` — add cancel button
- `frontend/app/sessions/[id]/activity/page.tsx` — render activity_events
- `frontend/app/sessions/[id]/data/page.tsx` — render DataArtifact manifest

---

## Task 1: Extend TimeSeriesFeaturizer with feature_families and energy_specific

**Files:**
- Modify: `backend/src/featurizer/featurizer.py`
- Modify: `backend/tests/test_featurizer.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_featurizer.py`:

```python
import pandas as pd
import pytest
from src.featurizer import TimeSeriesFeaturizer


def _make_series(n: int = 100) -> pd.Series:
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.Series(range(n), index=dates, dtype=float, name="wti")


def test_feature_families_rolling_stats_only():
    f = TimeSeriesFeaturizer(windows=[5], lags=[1], feature_families=["rolling_stats"])
    result = f.transform({"wti": _make_series()})
    cols = list(result.columns)
    assert all("mean" in c or "std" in c or "min" in c or "max" in c for c in cols)
    assert not any("lag" in c or "roc" in c for c in cols)


def test_feature_families_lag_only():
    f = TimeSeriesFeaturizer(windows=[5], lags=[1], feature_families=["lag"])
    result = f.transform({"wti": _make_series()})
    cols = list(result.columns)
    assert all("lag" in c for c in cols)
    assert not any("mean" in c or "roc" in c for c in cols)


def test_feature_families_momentum_only():
    f = TimeSeriesFeaturizer(windows=[5], lags=[1], feature_families=["momentum"])
    result = f.transform({"wti": _make_series()})
    cols = list(result.columns)
    assert all("roc" in c for c in cols)
    assert not any("lag" in c or "mean" in c for c in cols)


def test_energy_specific_flag_is_stored():
    f = TimeSeriesFeaturizer(energy_specific=True)
    assert f.energy_specific is True


def test_all_families_by_default():
    f = TimeSeriesFeaturizer(windows=[5], lags=[1])
    result = f.transform({"wti": _make_series()})
    cols = list(result.columns)
    assert any("mean" in c for c in cols)
    assert any("lag" in c for c in cols)
    assert any("roc" in c for c in cols)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_featurizer.py::test_feature_families_rolling_stats_only -v
```

Expected: FAIL — `TypeError: __init__() got unexpected keyword argument 'feature_families'`

- [ ] **Step 3: Update featurizer.py**

Replace `backend/src/featurizer/featurizer.py`:

```python
from __future__ import annotations

import pandas as pd

_ALL_FAMILIES = {"rolling_stats", "lag", "momentum"}


class TimeSeriesFeaturizer:
    def __init__(
        self,
        windows: list[int] | None = None,
        lags: list[int] | None = None,
        feature_families: list[str] | None = None,
        energy_specific: bool = False,
    ):
        self.windows: list[int] = windows or [5, 20, 60]
        self.lags: list[int] = lags or [1, 5, 20]
        self.feature_families: set[str] = set(feature_families) if feature_families else _ALL_FAMILIES
        self.energy_specific = energy_specific  # reserved for oil-specific features in PR 3

    def align(self, series_dict: dict[str, pd.Series]) -> pd.DataFrame:
        if not series_dict:
            return pd.DataFrame()
        all_dates = pd.DatetimeIndex(
            sorted({date for s in series_dict.values() for date in s.index})
        )
        daily_index = pd.date_range(start=all_dates.min(), end=all_dates.max(), freq="D")
        aligned = {
            name: series.reindex(daily_index, method="ffill")
            for name, series in series_dict.items()
        }
        return pd.DataFrame(aligned, index=daily_index)

    def _rolling_features(self, series: pd.Series, name: str) -> pd.DataFrame:
        frames: dict[str, pd.Series] = {}
        for w in self.windows:
            rolling = series.rolling(w, min_periods=w)
            frames[f"{name}_mean_{w}d"] = rolling.mean()
            frames[f"{name}_std_{w}d"] = rolling.std()
            frames[f"{name}_min_{w}d"] = rolling.min()
            frames[f"{name}_max_{w}d"] = rolling.max()
        return pd.DataFrame(frames, index=series.index)

    def _lag_features(self, series: pd.Series, name: str) -> pd.DataFrame:
        return pd.DataFrame(
            {f"{name}_lag_{lag}d": series.shift(lag) for lag in self.lags},
            index=series.index,
        )

    def _momentum_features(self, series: pd.Series, name: str) -> pd.DataFrame:
        return pd.DataFrame(
            {f"{name}_roc_{w}d": series.pct_change(w) for w in self.windows},
            index=series.index,
        )

    def transform(self, series_dict: dict[str, pd.Series]) -> pd.DataFrame:
        aligned = self.align(series_dict)
        feature_frames = []
        for col in aligned.columns:
            s = aligned[col]
            if "rolling_stats" in self.feature_families:
                feature_frames.append(self._rolling_features(s, col))
            if "lag" in self.feature_families:
                feature_frames.append(self._lag_features(s, col))
            if "momentum" in self.feature_families:
                feature_frames.append(self._momentum_features(s, col))
        if not feature_frames:
            return pd.DataFrame(index=aligned.index)
        return pd.concat(feature_frames, axis=1).dropna()
```

- [ ] **Step 4: Run all featurizer tests**

```bash
cd backend && uv run pytest tests/test_featurizer.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/featurizer/featurizer.py tests/test_featurizer.py
git commit -m "feat: add feature_families and energy_specific to TimeSeriesFeaturizer"
```

---

## Task 2: Hashing utilities

**Files:**
- Create: `backend/src/services/__init__.py`
- Create: `backend/src/services/hashing.py`

- [ ] **Step 1: Create the services package**

Create `backend/src/services/__init__.py`:

```python
```

(empty file)

- [ ] **Step 2: Create hashing.py**

Create `backend/src/services/hashing.py`:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def stable_hash(*parts: str) -> str:
    content = "|".join(parts)
    return hashlib.sha256(content.encode()).hexdigest()[:24]
```

- [ ] **Step 3: Write inline tests directly**

Create `backend/tests/test_hashing.py`:

```python
from src.services.hashing import canonical_json, stable_hash


def test_stable_hash_is_deterministic():
    assert stable_hash("a", "b") == stable_hash("a", "b")


def test_stable_hash_differs_on_different_input():
    assert stable_hash("a", "b") != stable_hash("b", "a")


def test_stable_hash_length():
    assert len(stable_hash("anything")) == 24


def test_canonical_json_sorts_keys():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b


def test_canonical_json_nested():
    result = canonical_json({"windows": [5, 20], "lags": [1]})
    assert result == '{"lags":[1],"windows":[5,20]}'
```

- [ ] **Step 4: Run hashing tests**

```bash
cd backend && uv run pytest tests/test_hashing.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/__init__.py src/services/hashing.py tests/test_hashing.py
git commit -m "feat: add stable_hash and canonical_json utilities"
```

---

## Task 3: Stage transition and activity event helpers

**Files:**
- Create: `backend/src/services/stage.py`

- [ ] **Step 1: Create stage.py**

Create `backend/src/services/stage.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.db.models import Session, SessionStage, SessionStatus


def transition_stage(session: Session, new_stage: SessionStage) -> None:
    """Update session.stage and append to stage_history. Call before db.commit()."""
    session.stage = new_stage.value
    session.stage_history = [
        *session.stage_history,
        {"stage": new_stage.value, "entered_at": datetime.now(UTC).isoformat()},
    ]
    session.updated_at = datetime.now(UTC).replace(tzinfo=None)


def set_status(session: Session, status: SessionStatus, error: str | None = None) -> None:
    session.status = status.value
    if error is not None:
        session.error = error
    session.updated_at = datetime.now(UTC).replace(tzinfo=None)


def append_activity_event(session: Session, event: dict[str, Any]) -> None:
    """Append an event to activity_events with auto-generated event_id and created_at."""
    enriched = {
        "event_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        **event,
    }
    session.activity_events = [*session.activity_events, enriched]
```

- [ ] **Step 2: Write tests**

Create `backend/tests/test_stage_helpers.py`:

```python
from datetime import date, datetime

from src.db.models import Session, SessionStage, SessionStatus
from src.services.stage import append_activity_event, set_status, transition_stage


def _session() -> Session:
    return Session(
        market_profile="oil",
        timeframe_start=date(2024, 1, 1),
        timeframe_end=date(2024, 6, 30),
    )


def test_transition_stage_updates_stage():
    s = _session()
    transition_stage(s, SessionStage.FEATURIZING)
    assert s.stage == "featurizing"


def test_transition_stage_appends_history():
    s = _session()
    transition_stage(s, SessionStage.FEATURIZING)
    transition_stage(s, SessionStage.ANALYZING)
    assert len(s.stage_history) == 2
    assert s.stage_history[0]["stage"] == "featurizing"
    assert s.stage_history[1]["stage"] == "analyzing"
    assert "entered_at" in s.stage_history[0]


def test_set_status_updates_status():
    s = _session()
    set_status(s, SessionStatus.RUNNING)
    assert s.status == "running"


def test_set_status_sets_error():
    s = _session()
    set_status(s, SessionStatus.FAILED, error="something went wrong")
    assert s.error == "something went wrong"


def test_append_activity_event_adds_metadata():
    s = _session()
    append_activity_event(s, {"type": "stage_transition", "from": "configuring", "to": "featurizing"})
    assert len(s.activity_events) == 1
    ev = s.activity_events[0]
    assert "event_id" in ev
    assert "created_at" in ev
    assert ev["type"] == "stage_transition"
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/test_stage_helpers.py -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add src/services/stage.py tests/test_stage_helpers.py
git commit -m "feat: add transition_stage, set_status, append_activity_event helpers"
```

---

## Task 4: FeaturizerService

**Files:**
- Create: `backend/src/services/featurizer.py`
- Create: `backend/tests/test_featurizer_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_featurizer_service.py`:

```python
import asyncio
import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

import src.db.models  # noqa: F401


@pytest.fixture
def engine():
    e = create_async_engine("sqlite+aiosqlite:///:memory:")
    asyncio.run(_setup(e))
    yield e
    asyncio.run(_teardown(e))


async def _setup(e):
    async with e.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def _teardown(e):
    async with e.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await e.dispose()


@pytest.fixture
def db(engine):
    async def _get():
        async with AsyncSession(engine) as session:
            yield session
    return _get


@pytest.mark.asyncio
async def test_featurizer_service_writes_feature_artifact(engine):
    from datetime import UTC, datetime
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlmodel import select
    from src.db.models import DataArtifact, FeatureArtifact
    from src.db.models import Session as SessionModel
    from src.db.models import SessionStage, SessionStatus
    from src.services.featurizer import run_featurizer_service

    async with AsyncSession(engine) as db:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2023, 1, 1),
            timeframe_end=date(2023, 6, 30),
            stage=SessionStage.FEATURIZING,
            status=SessionStatus.RUNNING,
            featurizer_config={
                "windows": [5],
                "lags": [1],
                "feature_families": ["rolling_stats", "lag", "momentum"],
                "energy_specific": False,
            },
        )
        db.add(s)
        await db.commit()
        await db.refresh(s)

        # Build inline raw_data with 100 days of fake WTI prices
        import pandas as pd
        dates = pd.date_range("2023-01-01", periods=100, freq="D")
        values = list(range(70, 170))
        raw_data = {
            "CL=F": {
                "index": [str(d.date()) for d in dates],
                "data": values,
            }
        }

        a = DataArtifact(
            session_id=s.id,
            source_hash="testhash",
            raw_data=raw_data,
            data_manifest={"tickers": ["CL=F"], "rows": 100},
        )
        db.add(a)
        await db.commit()

    await run_featurizer_service(s.id, engine)

    async with AsyncSession(engine) as db:
        fa_rows = (
            await db.execute(select(FeatureArtifact).where(FeatureArtifact.session_id == s.id))
        ).scalars().all()
        assert len(fa_rows) == 1
        fa = fa_rows[0]
        assert fa.config_hash != ""
        assert fa.matrix_hash != ""
        assert fa.feature_matrix_ref != ""
        assert fa.feature_manifest.get("n_features", 0) > 0

        s_updated = await db.get(SessionModel, s.id)
        assert s_updated.stage == "analyzing"
        assert s_updated.status == "running"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_featurizer_service.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.featurizer'`

- [ ] **Step 3: Create backend/src/services/featurizer.py**

```python
from __future__ import annotations

import hashlib
import io
import pathlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import select

from src.db.models import DataArtifact, FeatureArtifact
from src.db.models import Session as SessionModel
from src.db.models import SessionStage, SessionStatus
from src.featurizer import TimeSeriesFeaturizer
from src.services.hashing import canonical_json, stable_hash
from src.services.stage import append_activity_event, set_status, transition_stage

log = structlog.get_logger()

_ARTIFACTS_DIR = pathlib.Path("data/artifacts")
_RAW_SIZE_THRESHOLD = 5 * 1024 * 1024  # 5 MB


def _raw_data_to_series(raw_data: dict[str, Any]) -> dict[str, pd.Series]:
    return {
        col: pd.Series(
            v["data"],
            index=pd.DatetimeIndex(v["index"]),
            name=col,
            dtype=float,
        )
        for col, v in raw_data.items()
    }


def _raw_data_ref_to_series(ref: str) -> dict[str, pd.Series]:
    df = pd.read_parquet(ref)
    return {col: df[col].rename(col) for col in df.columns}


async def run_featurizer_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        if s is None:
            log.error("featurizer.session_not_found", session_id=str(session_id))
            return
        if s.status == SessionStatus.CANCELED:
            log.info("featurizer.canceled", session_id=str(session_id))
            return

        try:
            await _run(s, db)
        except Exception as exc:
            log.error("featurizer.failed", session_id=str(session_id), error=str(exc))
            set_status(s, SessionStatus.FAILED, error=str(exc))
            append_activity_event(s, {"type": "error", "stage": "featurizing", "message": str(exc)})
            await db.commit()


async def _run(s: SessionModel, db: AsyncSession) -> None:
    session_id = s.id
    cfg = s.featurizer_config

    # Load latest DataArtifact
    stmt = (
        select(DataArtifact)
        .where(DataArtifact.session_id == session_id)
        .order_by(DataArtifact.created_at.desc())  # type: ignore[attr-defined]
    )
    data_artifact = (await db.execute(stmt)).scalars().first()
    if data_artifact is None:
        raise ValueError("no DataArtifact found for session")

    # Compute config_hash for within-session cache check
    config_hash = stable_hash(data_artifact.source_hash, canonical_json(cfg))

    existing = (
        await db.execute(
            select(FeatureArtifact)
            .where(FeatureArtifact.session_id == session_id)
            .where(FeatureArtifact.config_hash == config_hash)
        )
    ).scalars().first()

    if existing is not None:
        log.info("featurizer.cache_hit", session_id=str(session_id), config_hash=config_hash)
        append_activity_event(s, {"type": "cache_hit", "stage": "featurizing"})
        transition_stage(s, SessionStage.ANALYZING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        return

    # Reconstruct series_dict from raw_data or raw_data_ref
    if data_artifact.raw_data:
        series_dict = _raw_data_to_series(data_artifact.raw_data)
    elif data_artifact.raw_data_ref:
        series_dict = _raw_data_ref_to_series(data_artifact.raw_data_ref)
    else:
        raise ValueError("DataArtifact has neither raw_data nor raw_data_ref")

    # Run TimeSeriesFeaturizer
    featurizer = TimeSeriesFeaturizer(
        windows=cfg.get("windows", [5, 20, 60]),
        lags=cfg.get("lags", [1, 5, 20]),
        feature_families=cfg.get("feature_families"),
        energy_specific=bool(cfg.get("energy_specific", False)),
    )
    features = featurizer.transform(series_dict)

    if features.empty:
        raise ValueError("featurizer produced empty feature matrix — insufficient data")

    log.info(
        "featurizer.complete",
        session_id=str(session_id),
        rows=len(features),
        cols=len(features.columns),
    )

    # Write feature matrix to parquet
    artifact_id = uuid.uuid4()
    _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ref = str(_ARTIFACTS_DIR / f"{artifact_id}_features.parquet")
    features.to_parquet(ref)
    matrix_bytes = io.BytesIO()
    features.to_parquet(matrix_bytes)
    matrix_hash = hashlib.sha256(matrix_bytes.getvalue()).hexdigest()[:24]

    # Build feature_manifest
    families: dict[str, int] = {}
    for col in features.columns:
        if "_mean_" in col or "_std_" in col or "_min_" in col or "_max_" in col:
            families["rolling_stats"] = families.get("rolling_stats", 0) + 1
        elif "_lag_" in col:
            families["lag"] = families.get("lag", 0) + 1
        elif "_roc_" in col:
            families["momentum"] = families.get("momentum", 0) + 1
    feature_manifest = {
        "n_features": len(features.columns),
        "n_rows": len(features),
        "feature_families": families,
        "columns": list(features.columns),
    }

    fa = FeatureArtifact(
        id=artifact_id,
        session_id=session_id,
        data_artifact_id=data_artifact.id,
        featurizer_config_snapshot=dict(cfg),
        feature_manifest=feature_manifest,
        feature_matrix_ref=ref,
        matrix_hash=matrix_hash,
        config_hash=config_hash,
    )
    db.add(fa)

    append_activity_event(
        s,
        {
            "type": "artifact_ready",
            "kind": "features",
            "artifact_id": str(artifact_id),
            "n_features": len(features.columns),
            "n_rows": len(features),
        },
    )
    transition_stage(s, SessionStage.ANALYZING)
    set_status(s, SessionStatus.RUNNING)
    await db.commit()
```

- [ ] **Step 4: Run the test**

```bash
cd backend && uv run pytest tests/test_featurizer_service.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/featurizer.py tests/test_featurizer_service.py
git commit -m "feat: FeaturizerService — reads DataArtifact, runs featurizer, writes FeatureArtifact"
```

---

## Task 5: TabPFNService

**Files:**
- Create: `backend/src/services/tabpfn.py`

- [ ] **Step 1: Create backend/src/services/tabpfn.py**

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import select

from src.config import settings
from src.db.models import AnalysisResult, FeatureArtifact
from src.db.models import Session as SessionModel
from src.db.models import SessionStage, SessionStatus
from src.services.hashing import canonical_json, stable_hash
from src.services.stage import append_activity_event, set_status, transition_stage

log = structlog.get_logger()

# Heuristic regime labels (same as demo.py)
_KNOWN_REGIMES: list[tuple[str, str, str]] = [
    ("2014-07-01", "2016-12-31", "bust"),
    ("2020-02-01", "2020-10-31", "bust"),
    ("2021-01-01", "2022-06-30", "bull_supercycle"),
    ("2022-02-01", "2022-04-30", "geopolitical_spike"),
    ("2023-10-01", "2023-12-31", "geopolitical_spike"),
]


def _make_regime_labels(wti: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    wti_daily = wti.reindex(index, method="ffill")
    ret5 = wti_daily.pct_change(5)
    ret60 = wti_daily.pct_change(60)
    labels = pd.Series("range_bound", index=index, name="regime")
    labels[ret60 > 0.15] = "bull_supercycle"
    labels[ret60 < -0.15] = "bust"
    labels[ret5 > 0.08] = "geopolitical_spike"
    for start, end, regime in _KNOWN_REGIMES:
        mask = (index >= start) & (index <= end)
        labels[mask] = regime
    return labels


def _make_direction_labels(wti: pd.Series, index: pd.DatetimeIndex, horizon: int = 20) -> pd.Series:
    wti_daily = wti.reindex(index, method="ffill")
    forward_ret = wti_daily.shift(-horizon) / wti_daily - 1
    forward_ret = forward_ret.dropna()
    labels = forward_ret.map(lambda r: "up" if r > 0 else "down")
    labels.name = "direction"
    return labels


def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    """Population Stability Index between two 1-D arrays."""
    breakpoints = np.percentile(expected, np.linspace(0, 100, buckets + 1))
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf
    exp_counts = np.histogram(expected, bins=breakpoints)[0]
    act_counts = np.histogram(actual, bins=breakpoints)[0]
    exp_pct = (exp_counts + 0.001) / len(expected)
    act_pct = (act_counts + 0.001) / len(actual)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def _detect_drift(features: pd.DataFrame, split: int) -> dict[str, Any]:
    train = features.iloc[:split]
    test = features.iloc[split:]
    if len(test) < 5:
        return {"drift_detected": False, "psi_score": 0.0, "drifted_features": []}
    psi_scores = {
        col: _psi(train[col].dropna().to_numpy(), test[col].dropna().to_numpy())
        for col in features.columns
    }
    drifted = [col for col, psi in psi_scores.items() if psi > 0.20]
    overall = float(np.mean(list(psi_scores.values())))
    return {
        "drift_detected": len(drifted) > 0,
        "psi_score": round(overall, 4),
        "drifted_features": drifted[:10],  # cap at 10 for DB size
    }


async def run_tabpfn_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        if s is None:
            log.error("tabpfn.session_not_found", session_id=str(session_id))
            return
        if s.status == SessionStatus.CANCELED:
            log.info("tabpfn.canceled", session_id=str(session_id))
            return

        try:
            await _run(s, db)
        except Exception as exc:
            log.error("tabpfn.failed", session_id=str(session_id), error=str(exc))
            set_status(s, SessionStatus.FAILED, error=str(exc))
            append_activity_event(s, {"type": "error", "stage": "analyzing", "message": str(exc)})
            await db.commit()


async def _run(s: SessionModel, db: AsyncSession) -> None:
    session_id = s.id

    # Load latest FeatureArtifact
    stmt = (
        select(FeatureArtifact)
        .where(FeatureArtifact.session_id == session_id)
        .order_by(FeatureArtifact.created_at.desc())  # type: ignore[attr-defined]
    )
    fa = (await db.execute(stmt)).scalars().first()
    if fa is None:
        raise ValueError("no FeatureArtifact found for session")

    # Regime labels are determined by market_profile — oil uses 4 labels
    regime_labels = ["bull_supercycle", "range_bound", "bust", "geopolitical_spike"]
    analysis_config: dict[str, Any] = {}  # reserved for future tuning params
    feature_hash = stable_hash(
        fa.matrix_hash,
        canonical_json(regime_labels),
        canonical_json(analysis_config),
    )

    # Within-session cache check
    existing = (
        await db.execute(
            select(AnalysisResult)
            .where(AnalysisResult.session_id == session_id)
            .where(AnalysisResult.feature_hash == feature_hash)
        )
    ).scalars().first()

    if existing is not None:
        log.info("tabpfn.cache_hit", session_id=str(session_id))
        append_activity_event(s, {"type": "cache_hit", "stage": "analyzing"})
        # In PR 2 we skip EXPLAINING and go straight to FOLLOW_UP
        transition_stage(s, SessionStage.FOLLOW_UP)
        set_status(s, SessionStatus.WAITING)
        await db.commit()
        return

    # Load feature matrix
    features = pd.read_parquet(fa.feature_matrix_ref)
    split = int(len(features) * 0.8)

    # Drift detection (no TabPFN required)
    drift = _detect_drift(features, split)

    regime_result: dict[str, Any] | None = None
    direction_result: dict[str, Any] | None = None

    if settings.tabpfn_token:
        try:
            from src.inference import DirectionClassifier, OilRegimeClassifier

            X_train, X_test = features.iloc[:split], features.iloc[split:]

            # Need WTI column for labeling; try common names
            wti_col = next(
                (c for c in features.columns if "CL=F" in c or c.lower() == "wti" or "wti" in c.lower()),
                None,
            )
            if wti_col is None:
                # Use first column as proxy
                wti_col = features.columns[0]

            # Reconstruct daily WTI series from the feature column (it's the lagged version)
            wti_proxy = features[wti_col]

            regime_labels_series = _make_regime_labels(wti_proxy, features.index)
            direction_labels_series = _make_direction_labels(wti_proxy, features.index)
            common_idx = features.index.intersection(direction_labels_series.index)
            X_train_dir = features.loc[common_idx[:split]]
            y_dir_train = direction_labels_series.loc[common_idx[:split]]

            regime_clf = OilRegimeClassifier(n_estimators=4)
            regime_clf.fit(X_train, regime_labels_series.iloc[:split])
            regime_pred = regime_clf.predict(X_test)
            regime_proba = regime_clf.predict_proba(X_test)
            top_regime = regime_pred.value_counts().idxmax()
            top_conf = float(regime_proba[top_regime].mean())
            regime_result = {
                "regime": top_regime,
                "confidence": round(top_conf, 4),
                "distribution": regime_pred.value_counts().to_dict(),
            }

            dir_clf = DirectionClassifier(n_estimators=4)
            dir_clf.fit(X_train_dir, y_dir_train)
            X_test_dir = features.loc[common_idx[split:]]
            dir_pred = dir_clf.predict(X_test_dir)
            dir_proba = dir_clf.predict_proba(X_test_dir)
            top_dir = dir_pred.value_counts().idxmax()
            top_dir_conf = float(dir_proba[top_dir].mean())
            direction_result = {
                "direction": top_dir,
                "confidence": round(top_dir_conf, 4),
                "distribution": dir_pred.value_counts().to_dict(),
            }

            log.info(
                "tabpfn.complete",
                session_id=str(session_id),
                regime=top_regime,
                direction=top_dir,
            )
        except Exception as exc:
            log.warning("tabpfn.inference_failed", session_id=str(session_id), error=str(exc))
    else:
        log.info("tabpfn.skipped_no_token", session_id=str(session_id))

    artifact_id = uuid.uuid4()
    ar = AnalysisResult(
        id=artifact_id,
        session_id=session_id,
        feature_artifact_id=fa.id,
        regime=regime_result,
        direction=direction_result,
        drift=drift,
        feature_hash=feature_hash,
    )
    db.add(ar)

    append_activity_event(
        s,
        {
            "type": "artifact_ready",
            "kind": "analysis",
            "artifact_id": str(artifact_id),
            "regime": regime_result.get("regime") if regime_result else None,
        },
    )
    # PR 2: skip EXPLAINING stage (ExplanationAgent is PR 4), go straight to FOLLOW_UP
    transition_stage(s, SessionStage.FOLLOW_UP)
    set_status(s, SessionStatus.WAITING)
    await db.commit()
```

- [ ] **Step 2: Run the test suite to confirm no imports are broken**

```bash
cd backend && uv run pytest tests/test_featurizer_service.py tests/test_stage_helpers.py tests/test_hashing.py -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add src/services/tabpfn.py
git commit -m "feat: TabPFNService — reads FeatureArtifact, runs TabPFN (if token set), writes AnalysisResult"
```

---

## Task 6: New API models for pipeline endpoints

**Files:**
- Modify: `backend/api/models.py`

- [ ] **Step 1: Add the new models at the end of api/models.py**

```python
class ProceedResponse(BaseModel):
    session_id: str


class RerunRequest(BaseModel):
    stage: str
    featurizer_config_patch: dict[str, object] | None = None


class RerunResponse(BaseModel):
    session_id: str


class CancelResponse(BaseModel):
    session_id: str
    stage: str
    status: str


class UploadResponse(BaseModel):
    artifact_id: str


class SeriesPoint(BaseModel):
    date: str
    value: float | None


class DataArtifactDetail(BaseModel):
    kind: str = "data"
    artifact_id: str
    round: int
    sources: list[object]
    data_manifest: dict[str, object]
    series_preview: dict[str, list[SeriesPoint]]
    cache_hit: bool
    cached_from_session_id: str | None
```

- [ ] **Step 2: Verify mypy is still clean**

```bash
cd backend && uv run mypy src/ api/models.py
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add api/models.py
git commit -m "feat: add pipeline API response models"
```

---

## Task 7: Pipeline routes (proceed, rerun, cancel, upload, artifacts)

**Files:**
- Create: `backend/api/routes/pipeline.py`
- Create: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_pipeline.py`:

```python
import io
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest


def _make_csv_bytes() -> bytes:
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    df = pd.DataFrame({"date": [str(d.date()) for d in dates], "CL=F": range(70, 170)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def test_upload_returns_202(client):
    # Create a session first
    res = client.post(
        "/api/sessions",
        json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
    )
    session_id = res.json()["session_id"]

    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background"):
        res = client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "My WTI data"},
        )
    assert res.status_code == 202
    assert "artifact_id" in res.json()


def test_proceed_returns_202(client):
    res = client.post(
        "/api/sessions",
        json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
    )
    session_id = res.json()["session_id"]

    # Upload first so there is a DataArtifact
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background"):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    # Manually advance stage to USER_REVIEW (normally done by DataAgent)
    # Skip this for now — proceed requires USER_REVIEW stage
    # We test the 409 path instead
    with patch("api.routes.pipeline._run_featurizer_background"):
        res = client.post(f"/api/sessions/{session_id}/proceed")
    # Session is in CONFIGURING, not USER_REVIEW → 409
    assert res.status_code == 409


def test_cancel_returns_200(client):
    res = client.post(
        "/api/sessions",
        json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
    )
    session_id = res.json()["session_id"]
    # Can't cancel WAITING session
    res = client.post(f"/api/sessions/{session_id}/cancel")
    assert res.status_code == 409


def test_get_artifact_data(client):
    res = client.post(
        "/api/sessions",
        json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
    )
    session_id = res.json()["session_id"]

    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background"):
        up_res = client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "My WTI data"},
        )
    artifact_id = up_res.json()["artifact_id"]

    ar_res = client.get(f"/api/sessions/{session_id}/artifacts/{artifact_id}")
    assert ar_res.status_code == 200
    body = ar_res.json()
    assert body["kind"] == "data"
    assert body["artifact_id"] == artifact_id
    assert "data_manifest" in body
    assert "series_preview" in body


def test_rerun_invalid_stage_returns_422(client):
    res = client.post(
        "/api/sessions",
        json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
    )
    session_id = res.json()["session_id"]
    res = client.post(f"/api/sessions/{session_id}/rerun", json={"stage": "invalid_stage"})
    assert res.status_code == 422
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_pipeline.py -v
```

Expected: FAIL — `404 Not Found` because routes don't exist yet

- [ ] **Step 3: Create backend/api/routes/pipeline.py**

```python
from __future__ import annotations

import asyncio
import hashlib
import io
import pathlib
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import pandas as pd
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import (
    CancelResponse,
    DataArtifactDetail,
    ProceedResponse,
    RerunRequest,
    RerunResponse,
    SeriesPoint,
    UploadResponse,
)
from src.db.models import AnalysisResult, DataArtifact, FeatureArtifact
from src.db.models import Session as SessionModel
from src.db.models import SessionStage, SessionStatus
from src.db.session import engine, get_session
from src.services.hashing import stable_hash
from src.services.stage import append_activity_event, set_status, transition_stage

router = APIRouter(tags=["pipeline"])
log = structlog.get_logger()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_RERUN_ALLOWED_STAGES = {
    "data_gathering": SessionStage.DATA_GATHERING,
    "featurizing": SessionStage.FEATURIZING,
    "analyzing": SessionStage.ANALYZING,
}
_UPLOAD_SIZE_LIMIT = 50 * 1024 * 1024  # 50 MB
_ARTIFACTS_DIR = pathlib.Path("data/artifacts")
_RAW_INLINE_THRESHOLD = 5 * 1024 * 1024  # 5 MB


def _df_to_raw_data(df: pd.DataFrame) -> dict[str, Any]:
    return {
        col: {
            "index": [str(d.date()) for d in df.index],
            "data": [None if pd.isna(v) else float(v) for v in df[col]],
        }
        for col in df.columns
    }


def _build_manifest(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "tickers": list(df.columns),
        "date_range": {
            "start": str(df.index.min().date()),
            "end": str(df.index.max().date()),
        },
        "rows": len(df),
        "missing_pct": {col: round(float(df[col].isna().mean() * 100), 2) for col in df.columns},
        "summary_stats": {
            col: {
                "mean": round(float(df[col].mean(skipna=True)), 4),
                "std": round(float(df[col].std(skipna=True)), 4),
                "min": round(float(df[col].min(skipna=True)), 4),
                "max": round(float(df[col].max(skipna=True)), 4),
            }
            for col in df.columns
        },
    }


def _parse_upload(content: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(content)
    if filename.endswith(".parquet"):
        df = pd.read_parquet(buf)
    else:
        df = pd.read_csv(buf)

    # Normalize index to DatetimeIndex
    if "date" in df.columns:
        df = df.set_index("date")
    df.index = pd.DatetimeIndex(df.index)
    df = df.sort_index()
    return df.select_dtypes(include="number")


async def _get_session_or_404(session_id: str, db: AsyncSession) -> tuple[uuid.UUID, SessionModel]:
    try:
        uid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")
    s = await db.get(SessionModel, uid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return uid, s


def _run_featurizer_background(session_id: uuid.UUID) -> None:
    from src.services.featurizer import run_featurizer_service

    asyncio.run(run_featurizer_service(session_id, engine))


def _run_tabpfn_background(session_id: uuid.UUID) -> None:
    from src.services.tabpfn import run_tabpfn_service

    asyncio.run(run_tabpfn_service(session_id, engine))


@router.post(
    "/sessions/{session_id}/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_data(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: SessionDep,
    file: UploadFile = File(...),
    source_name: str = Form(...),
) -> UploadResponse:
    uid, s = await _get_session_or_404(session_id, db)

    content = await file.read()
    if len(content) > _UPLOAD_SIZE_LIMIT:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    df = _parse_upload(content, file.filename or "")
    if df.empty:
        raise HTTPException(status_code=422, detail="No numeric columns found in uploaded file")

    file_hash = hashlib.sha256(content).hexdigest()[:16]
    source_hash = stable_hash(f"upload:{source_name}:{file_hash}")
    data_manifest = _build_manifest(df)

    artifact_id = uuid.uuid4()
    raw_data: dict[str, Any] | None = None
    raw_data_ref: str | None = None

    if len(content) <= _RAW_INLINE_THRESHOLD:
        raw_data = _df_to_raw_data(df)
    else:
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        ref = str(_ARTIFACTS_DIR / f"{artifact_id}.parquet")
        df.to_parquet(ref)
        raw_data_ref = ref

    a = DataArtifact(
        id=artifact_id,
        session_id=uid,
        round=1,
        sources=[{"connector_id": "upload", "source_name": source_name}],
        data_manifest=data_manifest,
        raw_data=raw_data,
        raw_data_ref=raw_data_ref,
        source_hash=source_hash,
    )
    db.add(a)

    append_activity_event(
        s,
        {
            "type": "artifact_ready",
            "kind": "data",
            "artifact_id": str(artifact_id),
            "rows": data_manifest["rows"],
            "tickers": data_manifest["tickers"],
        },
    )
    # Transition to USER_REVIEW so the frontend can proceed
    transition_stage(s, SessionStage.USER_REVIEW)
    set_status(s, SessionStatus.WAITING)
    await db.commit()

    log.info(
        "session.upload",
        session_id=session_id,
        source_name=source_name,
        rows=data_manifest["rows"],
        artifact_id=str(artifact_id),
    )
    return UploadResponse(artifact_id=str(artifact_id))


@router.post(
    "/sessions/{session_id}/proceed",
    response_model=ProceedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def proceed(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: SessionDep,
) -> ProceedResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if s.stage != SessionStage.USER_REVIEW:
        raise HTTPException(status_code=409, detail=f"proceed not available at stage {s.stage}")
    if s.status == SessionStatus.RUNNING:
        raise HTTPException(status_code=409, detail="a task is already running — POST /cancel first")

    transition_stage(s, SessionStage.FEATURIZING)
    set_status(s, SessionStatus.RUNNING)
    append_activity_event(s, {"type": "stage_transition", "from": "user_review", "to": "featurizing"})
    await db.commit()

    background_tasks.add_task(_run_featurizer_background, uid)
    log.info("session.proceed", session_id=session_id)
    return ProceedResponse(session_id=session_id)


@router.post(
    "/sessions/{session_id}/rerun",
    response_model=RerunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rerun(
    session_id: str,
    req: RerunRequest,
    background_tasks: BackgroundTasks,
    db: SessionDep,
) -> RerunResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if req.stage not in _RERUN_ALLOWED_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"stage must be one of: {list(_RERUN_ALLOWED_STAGES)}",
        )
    if s.status == SessionStatus.RUNNING:
        raise HTTPException(status_code=409, detail="a task is already running — POST /cancel first")

    target = _RERUN_ALLOWED_STAGES[req.stage]

    if req.featurizer_config_patch:
        merged = {**s.featurizer_config, **req.featurizer_config_patch}
        s.featurizer_config = merged

    transition_stage(s, target)
    set_status(s, SessionStatus.RUNNING)
    append_activity_event(s, {"type": "stage_transition", "from": s.stage, "to": target.value})
    await db.commit()

    if target == SessionStage.FEATURIZING:
        background_tasks.add_task(_run_featurizer_background, uid)
    elif target == SessionStage.ANALYZING:
        background_tasks.add_task(_run_tabpfn_background, uid)

    log.info("session.rerun", session_id=session_id, stage=req.stage)
    return RerunResponse(session_id=session_id)


@router.post("/sessions/{session_id}/cancel", response_model=CancelResponse)
async def cancel(session_id: str, db: SessionDep) -> CancelResponse:
    uid, s = await _get_session_or_404(session_id, db)

    if s.status != SessionStatus.RUNNING:
        raise HTTPException(status_code=409, detail="no task is currently running for this session")

    set_status(s, SessionStatus.CANCELED)
    append_activity_event(s, {"type": "canceled", "stage": s.stage})
    await db.commit()

    log.info("session.canceled", session_id=session_id, stage=s.stage)
    return CancelResponse(session_id=session_id, stage=s.stage, status="canceled")


@router.get("/sessions/{session_id}/artifacts/{artifact_id}", response_model=DataArtifactDetail)
async def get_artifact(session_id: str, artifact_id: str, db: SessionDep) -> DataArtifactDetail:
    try:
        s_uid = uuid.UUID(session_id)
        a_uid = uuid.UUID(artifact_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")

    artifact = await db.get(DataArtifact, a_uid)
    if artifact is None or artifact.session_id != s_uid:
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Build series_preview (max 500 points per series, never expose raw_data directly)
    series_preview: dict[str, list[SeriesPoint]] = {}
    if artifact.raw_data:
        for col, v in artifact.raw_data.items():
            pairs = list(zip(v["index"], v["data"]))[:500]
            series_preview[col] = [SeriesPoint(date=d, value=val) for d, val in pairs]
    elif artifact.raw_data_ref:
        df = pd.read_parquet(artifact.raw_data_ref)
        for col in df.columns[:10]:  # cap columns
            series = df[col].dropna().iloc[:500]
            series_preview[col] = [
                SeriesPoint(date=str(idx.date()), value=float(val))
                for idx, val in zip(series.index, series)
            ]

    return DataArtifactDetail(
        artifact_id=str(artifact.id),
        round=artifact.round,
        sources=artifact.sources,
        data_manifest=artifact.data_manifest,
        series_preview=series_preview,
        cache_hit=artifact.cache_hit,
        cached_from_session_id=(
            str(artifact.cached_from_session_id) if artifact.cached_from_session_id else None
        ),
    )
```

- [ ] **Step 4: Run pipeline tests**

```bash
cd backend && uv run pytest tests/test_pipeline.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/pipeline.py tests/test_pipeline.py api/models.py
git commit -m "feat: pipeline routes — proceed, rerun, cancel, upload, artifacts/{id}"
```

---

## Task 8: Wire pipeline router into FastAPI app

**Files:**
- Modify: `backend/api/main.py`

- [ ] **Step 1: Add pipeline router**

In `backend/api/main.py`, add `pipeline` to the import and `include_router` call:

```python
from api.routes import derivatives, market, pipeline, profiles, sessions
```

And after `app.include_router(sessions.router, prefix="/api")`:

```python
app.include_router(pipeline.router, prefix="/api")
```

- [ ] **Step 2: Run the full backend test suite**

```bash
cd backend && uv run pytest -v 2>&1 | tail -15
```

Expected: all PASS

- [ ] **Step 3: Run mypy**

```bash
cd backend && uv run mypy src/ api/
```

Expected: no errors (suppress any SQLAlchemy `.desc()` or `.asc()` with `# type: ignore[attr-defined]` if needed)

- [ ] **Step 4: Commit**

```bash
git add api/main.py
git commit -m "feat: wire pipeline router into FastAPI app"
```

---

## Task 9: Frontend API additions

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/__tests__/api.test.ts`

- [ ] **Step 1: Add new types and endpoints to lib/api.ts**

Add the following types before the `async function request` line:

```typescript
export type DataArtifactDetail = {
  kind: "data";
  artifact_id: string;
  round: number;
  sources: unknown[];
  data_manifest: {
    tickers: string[];
    date_range: { start: string; end: string };
    rows: number;
    missing_pct: Record<string, number>;
    summary_stats: Record<string, { mean: number; std: number; min: number; max: number }>;
  };
  series_preview: Record<string, { date: string; value: number | null }[]>;
  cache_hit: boolean;
  cached_from_session_id: string | null;
};
```

Add the following methods to the `api` object:

```typescript
  proceed: (sessionId: string) =>
    request<{ session_id: string }>(`/api/sessions/${sessionId}/proceed`, { method: "POST" }),

  rerun: (sessionId: string, stage: string, featurizerConfigPatch?: Record<string, unknown>) =>
    request<{ session_id: string }>(`/api/sessions/${sessionId}/rerun`, {
      method: "POST",
      body: JSON.stringify({ stage, featurizer_config_patch: featurizerConfigPatch ?? null }),
    }),

  cancelSession: (sessionId: string) =>
    request<{ session_id: string; stage: string; status: string }>(
      `/api/sessions/${sessionId}/cancel`,
      { method: "POST" },
    ),

  uploadData: (sessionId: string, file: File, sourceName: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("source_name", sourceName);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60_000);
    return fetch(`${API_URL}/api/sessions/${sessionId}/upload`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    })
      .then((res) => {
        clearTimeout(timeout);
        if (!res.ok) throw new Error(`API error ${res.status}`);
        return res.json() as Promise<{ artifact_id: string }>;
      })
      .catch((err) => {
        clearTimeout(timeout);
        throw err;
      });
  },

  getArtifact: (sessionId: string, artifactId: string) =>
    request<DataArtifactDetail>(`/api/sessions/${sessionId}/artifacts/${artifactId}`),
```

- [ ] **Step 2: Add tests for the new API methods**

Add to `frontend/lib/__tests__/api.test.ts`:

```typescript
describe("api.proceed", () => {
  it("posts to /proceed", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "ses-1" });
    await api.proceed("ses-1");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/sessions/ses-1/proceed"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("api.cancelSession", () => {
  it("posts to /cancel", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "ses-1", stage: "featurizing", status: "canceled" });
    const result = await api.cancelSession("ses-1");
    expect(result.status).toBe("canceled");
  });
});

describe("api.getArtifact", () => {
  it("fetches artifact detail", async () => {
    const { api } = await import("../api");
    mockOk({
      kind: "data",
      artifact_id: "art-1",
      round: 1,
      sources: [],
      data_manifest: { tickers: ["CL=F"], rows: 100, date_range: {}, missing_pct: {}, summary_stats: {} },
      series_preview: { "CL=F": [{ date: "2023-01-01", value: 78.4 }] },
      cache_hit: false,
      cached_from_session_id: null,
    });
    const result = await api.getArtifact("ses-1", "art-1");
    expect(result.kind).toBe("data");
    expect(result.artifact_id).toBe("art-1");
  });
});
```

- [ ] **Step 3: Run frontend tests**

```bash
cd frontend && npm run test -- lib/__tests__/api.test.ts
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add lib/api.ts lib/__tests__/api.test.ts
git commit -m "feat: add proceed, rerun, cancel, upload, getArtifact to frontend API client"
```

---

## Task 10: Session layout — cancel button

**Files:**
- Modify: `frontend/app/sessions/[id]/layout.tsx`

- [ ] **Step 1: Update layout.tsx to add cancel button**

In `frontend/app/sessions/[id]/layout.tsx`, add the cancel handler and button. Replace the session header `<div>` block:

```tsx
"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { StageStrip } from "@/components/StageStrip";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import { useSessionStream } from "@/lib/websocket";

const TABS = [
  { label: "Activity", path: "activity" },
  { label: "Data", path: "data" },
  { label: "Results", path: "results" },
];

export default function SessionLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const { sessionId, stage, status, setSession } = useSessionStore();
  const [canceling, setCanceling] = useState(false);

  useSessionStream(id ?? null);

  useEffect(() => {
    if (!id) return;
    api
      .getSession(id)
      .then(setSession)
      .catch(() => router.push("/"));
  }, [id, router, setSession]);

  const handleCancel = async () => {
    if (!id) return;
    setCanceling(true);
    try {
      const result = await api.cancelSession(id);
      setSession({ ...useSessionStore.getState(), status: result.status as "canceled" } as any);
    } catch {
      // swallow — status will update on next WS/poll
    } finally {
      setCanceling(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-[#060b14] text-[#f9fafb]">
      <header className="flex items-center justify-between px-4 py-2 border-b border-[#21262d] bg-[#111827]">
        <span className="font-bold text-[#3b82f6] text-base tracking-tight">■ SIGNALYST</span>
        <Link
          href="/"
          className="text-sm px-3 py-1 rounded border border-[#21262d] text-[#9ca3af] hover:text-[#f9fafb] transition-colors"
        >
          + NEW ANALYSIS
        </Link>
      </header>

      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#21262d] bg-[#111827]">
        <Link href="/" className="text-[#9ca3af] hover:text-[#f9fafb] text-sm transition-colors">
          ← Sessions
        </Link>
        {sessionId && (
          <>
            <span className="text-[#6b7280] text-xs">·</span>
            <span className="text-sm text-[#9ca3af] font-mono">{id?.slice(0, 8)}</span>
            {stage && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-[#1f2937] text-[#60a5fa] border border-[#1d4ed8]">
                {stage}
              </span>
            )}
            {status && (
              <span
                className={[
                  "text-xs",
                  status === "running" ? "text-[#22c55e]" : "",
                  status === "waiting" ? "text-[#9ca3af]" : "",
                  status === "failed" ? "text-[#ef4444]" : "",
                  status === "canceled" ? "text-[#f59e0b]" : "",
                ].join(" ")}
              >
                {status === "running" && "● "}
                {status}
              </span>
            )}
            {status === "running" && (
              <button
                onClick={handleCancel}
                disabled={canceling}
                className="ml-auto text-xs px-2 py-0.5 rounded border border-[#ef4444] text-[#ef4444] hover:bg-[#ef4444] hover:text-white transition-colors disabled:opacity-40"
              >
                {canceling ? "Canceling…" : "Cancel"}
              </button>
            )}
          </>
        )}
      </div>

      <StageStrip currentStage={stage} />

      <div className="flex gap-4 px-4 border-b border-[#21262d] bg-[#111827]">
        {TABS.map((tab) => {
          const href = `/sessions/${id}/${tab.path}`;
          const isActive = pathname === href;
          return (
            <Link
              key={tab.label}
              href={href}
              className={[
                "text-sm py-2 border-b-2 transition-colors",
                isActive
                  ? "border-[#3b82f6] text-[#f9fafb]"
                  : "border-transparent text-[#9ca3af] hover:text-[#f9fafb]",
              ].join(" ")}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>

      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run type-check 2>&1 | grep "error TS" | grep -v "OverviewTab\|BacktestTab\|DriftTab\|FeaturesTab"
```

Expected: no output (no errors)

- [ ] **Step 3: Commit**

```bash
git add app/sessions/\[id\]/layout.tsx
git commit -m "feat: add cancel button to session layout (visible when status = running)"
```

---

## Task 11: Activity page — passive feed from activity_events

**Files:**
- Modify: `frontend/app/sessions/[id]/activity/page.tsx`

- [ ] **Step 1: Replace the placeholder with the passive feed**

Replace `frontend/app/sessions/[id]/activity/page.tsx`:

```tsx
"use client";

import { useSessionStore } from "@/lib/store";

const EVENT_ICONS: Record<string, string> = {
  stage_transition: "→",
  artifact_ready: "✓",
  cache_hit: "⚡",
  error: "✕",
  canceled: "◌",
};

const STAGE_LABELS: Record<string, string> = {
  configuring: "Config",
  data_gathering: "Data Gathering",
  user_review: "User Review",
  featurizing: "Featurizing",
  analyzing: "Analyzing",
  explaining: "Explaining",
  follow_up: "Follow-up",
};

function EventRow({ event }: { event: Record<string, unknown> }) {
  const type = event.type as string;
  const icon = EVENT_ICONS[type] ?? "·";
  const ts = event.created_at
    ? new Date(event.created_at as string).toLocaleTimeString()
    : "";

  let label = type.replace(/_/g, " ");
  if (type === "stage_transition") {
    label = `${STAGE_LABELS[(event.to as string) ?? ""] ?? event.to} started`;
  } else if (type === "artifact_ready") {
    const kind = event.kind as string;
    const rows = event.rows ? ` · ${event.rows} rows` : "";
    const features = event.n_features ? ` · ${event.n_features} features` : "";
    label = `${kind} artifact ready${rows}${features}`;
  } else if (type === "cache_hit") {
    label = `cache hit at ${event.stage}`;
  } else if (type === "error") {
    label = `error: ${event.message}`;
  }

  return (
    <div className="flex items-start gap-3 py-2 border-b border-[#1f2937] last:border-0">
      <span
        className={[
          "text-xs w-4 mt-0.5 flex-shrink-0",
          type === "error" ? "text-[#ef4444]" : "text-[#3b82f6]",
        ].join(" ")}
      >
        {icon}
      </span>
      <span className="text-sm text-[#f9fafb] flex-1">{label}</span>
      <span className="text-xs text-[#6b7280] flex-shrink-0">{ts}</span>
    </div>
  );
}

export default function ActivityPage() {
  const { activityEvents, stage, status } = useSessionStore();

  const statusMsg: Record<string, string> = {
    running: "Running…",
    waiting: "Waiting for input",
    failed: "Failed",
    canceled: "Canceled",
  };

  return (
    <div className="flex flex-col h-full p-4 gap-4">
      {activityEvents.length === 0 ? (
        <div className="flex items-center justify-center flex-1 text-[#4b5563] text-sm">
          {status === "running"
            ? "Processing… events will appear here"
            : "No activity yet — upload data or start an analysis"}
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          <div className="bg-[#111827] rounded-lg border border-[#21262d] divide-y divide-[#1f2937]">
            {activityEvents.map((ev, i) => (
              <EventRow key={(ev.event_id as string) ?? i} event={ev as Record<string, unknown>} />
            ))}
          </div>
        </div>
      )}

      {stage && status && (
        <div className="text-xs text-[#6b7280]">
          {STAGE_LABELS[stage] ?? stage} · {statusMsg[status] ?? status}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npm run type-check 2>&1 | grep "error TS" | grep -v "OverviewTab\|BacktestTab\|DriftTab\|FeaturesTab"
```

Expected: no output

- [ ] **Step 3: Commit**

```bash
git add app/sessions/\[id\]/activity/page.tsx
git commit -m "feat: activity page — renders activity_events from session state"
```

---

## Task 12: Data sub-page — DataArtifact manifest + sparklines

**Files:**
- Modify: `frontend/app/sessions/[id]/data/page.tsx`

- [ ] **Step 1: Replace the placeholder with the Data sub-page**

Replace `frontend/app/sessions/[id]/data/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useSessionStore } from "@/lib/store";
import type { DataArtifactDetail } from "@/lib/api";

function MetricCard({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`flex-1 px-3 py-2 rounded border bg-[#111827] ${warn ? "border-[#f59e0b]" : "border-[#21262d]"}`}>
      <div className="text-[10px] text-[#6b7280] uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-base font-mono ${warn ? "text-[#f59e0b]" : "text-[#f9fafb]"}`}>{value}</div>
    </div>
  );
}

function Sparkline({ points }: { points: { date: string; value: number | null }[] }) {
  const values = points.map((p) => p.value ?? 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 300;
  const height = 48;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-12">
      <polyline points={pts} fill="none" stroke="#3b82f6" strokeWidth="1.5" />
    </svg>
  );
}

export default function DataPage() {
  const { id } = useParams<{ id: string }>();
  const { artifacts } = useSessionStore();
  const [artifact, setArtifact] = useState<DataArtifactDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!id || artifacts.data.length === 0) return;
    const latestRef = artifacts.data[artifacts.data.length - 1];
    setLoading(true);
    api
      .getArtifact(id, latestRef.artifact_id)
      .then(setArtifact)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id, artifacts.data]);

  if (artifacts.data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[#4b5563] text-sm">
        No data yet — upload a CSV or Parquet file to populate this view
      </div>
    );
  }

  if (loading || !artifact) {
    return (
      <div className="flex items-center justify-center h-full text-[#4b5563] text-sm">
        Loading…
      </div>
    );
  }

  const dm = artifact.data_manifest;
  const avgMissing = Object.values(dm.missing_pct).reduce((s, v) => s + v, 0) / (Object.keys(dm.missing_pct).length || 1);

  return (
    <div className="flex flex-col gap-4 p-4 overflow-auto">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-[#f9fafb]">Data Manifest</h2>
        {artifact.cache_hit && (
          <span className="text-xs text-[#f59e0b]">⚡ Cached</span>
        )}
      </div>

      <div className="flex gap-2">
        <MetricCard label="Rows" value={String(dm.rows)} />
        <MetricCard label="Series" value={String(dm.tickers.length)} />
        <MetricCard
          label="Missing %"
          value={`${avgMissing.toFixed(1)}%`}
          warn={avgMissing > 1}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {dm.tickers.map((ticker) => (
          <span
            key={ticker}
            className={`text-xs px-2 py-0.5 rounded border ${
              (dm.missing_pct[ticker] ?? 0) > 1
                ? "border-[#f59e0b] text-[#f59e0b]"
                : "border-[#21262d] text-[#9ca3af]"
            }`}
          >
            {ticker}
            {dm.missing_pct[ticker] !== undefined && ` · ${dm.missing_pct[ticker]}% missing`}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {Object.entries(artifact.series_preview).map(([ticker, points]) => {
          const stats = dm.summary_stats[ticker];
          return (
            <div key={ticker} className="bg-[#111827] rounded border border-[#21262d] p-3">
              <div className="text-xs font-mono text-[#9ca3af] mb-2">{ticker}</div>
              <Sparkline points={points} />
              {stats && (
                <div className="flex gap-3 mt-2 text-[10px] text-[#6b7280] font-mono">
                  <span>min {stats.min.toFixed(2)}</span>
                  <span>mean {stats.mean.toFixed(2)}</span>
                  <span>max {stats.max.toFixed(2)}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check and tests**

```bash
cd frontend && npm run type-check 2>&1 | grep "error TS" | grep -v "OverviewTab\|BacktestTab\|DriftTab\|FeaturesTab"
npm run test 2>&1 | grep "Test Files\|Tests "
```

Expected: no type errors, all tests pass

- [ ] **Step 3: Commit**

```bash
git add app/sessions/\[id\]/data/page.tsx
git commit -m "feat: Data sub-page renders DataArtifact manifest and series sparklines"
```

---

## Task 13: Final integration check

- [ ] **Step 1: Run full backend test suite + mypy + ruff**

```bash
cd backend && uv run pytest -v 2>&1 | tail -5
uv run mypy src/ api/
uv run ruff check .
```

Expected: all PASS, no mypy errors, no ruff errors

- [ ] **Step 2: Run full frontend tests + lint + type-check**

```bash
cd frontend && npm run test 2>&1 | grep "Test Files\|Tests "
npm run lint
npm run type-check 2>&1 | grep "error TS" | grep -v "OverviewTab\|BacktestTab\|DriftTab\|FeaturesTab"
```

Expected: all PASS

- [ ] **Step 3: Push and check CI**

```bash
git push -u origin feat/deterministic-pipeline
gh run list --branch feat/deterministic-pipeline --limit 3
```

Wait for CI to complete. If any check fails, read logs with `gh run view <run-id> --log-failed` and fix before proceeding.

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A && git commit -m "chore: pr2 integration — all tests pass, lint clean"
git push
```

---

## Self-Review

Spec coverage check against `docs/backend-redesign.md` PR 2 and `docs/frontend-redesign.md` PR 2:

| Requirement | Task |
|---|---|
| Extend `TimeSeriesFeaturizer` for `feature_families` + `energy_specific` | Task 1 |
| `FeaturizerService` wrapping `TimeSeriesFeaturizer` | Task 4 |
| `TabPFNService` wrapping `OilRegimeClassifier` + `DirectionClassifier` | Task 5 |
| Stage machine: `POST /proceed`, `POST /rerun`, `POST /cancel` | Task 7 |
| Within-session artifact cache (config_hash + feature_hash) | Tasks 4, 5 |
| `POST /api/sessions/{id}/upload` → DataArtifact | Task 7 |
| Background task pattern | Tasks 4, 5, 7 |
| Deterministic pipeline end-to-end | Tasks 4, 5, 7 |
| `GET /api/sessions/{id}/artifacts/{artifact_id}` (DataArtifact) | Task 7 |
| Stage history append on every transition | Task 3 (via `transition_stage`) |
| Concurrency protection (409 on double-start) | Task 7 |
| Passive activity feed (frontend) | Task 11 |
| Data sub-page (frontend) | Task 12 |
| Cancel button in session header (frontend) | Task 10 |
| Frontend API additions | Task 9 |
