# PR 1 — Session Data Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old `Run`-based backend with the new `Session`-based data model, add basic CRUD endpoints, seed the oil `MarketProfile`, expose `GET /api/market/snapshot`, stub the session WebSocket, and rebuild the frontend routing/home page against the new API.

**Architecture:** Backend — six new SQLModel tables (`Session`, `DataArtifact`, `FeatureArtifact`, `AnalysisResult`, `Connector`, `MarketProfile`) replace the single `Run` table; three new route files handle sessions, profiles, and market snapshot; `api/ws.py` is updated for session-scoped streams. Frontend — `lib/api.ts`, `lib/store.ts`, `lib/websocket.ts` are full rewrites; the home page, shared session layout, and new component shells replace the old single-page design.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, asyncpg, Alembic, yfinance, Next.js 15 App Router, TypeScript, Tailwind CSS, Zustand, Vitest

**Reference specs:** `docs/backend-redesign.md`, `docs/frontend-redesign.md`

---

## File Map

### Delete
- `backend/api/routes/analyze.py`
- `backend/src/agent/loop.py`
- `backend/src/agent/tabpfn_progress.py`
- `backend/tests/test_agent_loop.py`
- `backend/tests/test_analyze_route.py`
- `frontend/components/AgentDrawer.tsx` + `components/__tests__/AgentDrawer.test.tsx`
- `frontend/components/AgentProgressTimeline.tsx` + `components/__tests__/AgentProgressTimeline.test.tsx`
- `frontend/components/AgentStream.tsx`
- `frontend/components/ChatPanel.tsx` + `components/__tests__/ChatPanel.test.tsx`
- `frontend/components/ResultsPanel.tsx` + `components/__tests__/ResultsPanel.test.tsx`
- `frontend/components/ResultsTabs.tsx` + `components/__tests__/ResultsTabs.test.tsx`
- `frontend/components/ThoughtStream.tsx`
- `frontend/lib/agentProgress.ts` + `lib/__tests__/agentProgress.test.ts`

### Modify
- `backend/src/db/models.py` — replace `Run` with 6 new models
- `backend/api/models.py` — replace `RunResult` with session response models
- `backend/api/main.py` — remove old routes, add new routes + profile seeding in lifespan
- `backend/api/ws.py` — session-scoped stub
- `backend/src/agent/__init__.py` — remove `run_agent_loop` export
- `backend/alembic/env.py` — update model import
- `backend/tests/test_db_models.py` — replace with new model tests
- `backend/tests/test_routes.py` — remove old run tests, keep derivatives tests
- `backend/tests/test_ws.py` — update for session WS stub
- `frontend/app/page.tsx` — home page
- `frontend/app/layout.tsx` — root layout (minimal change)
- `frontend/lib/api.ts` — full rewrite
- `frontend/lib/store.ts` — full rewrite (`useSessionStore`)
- `frontend/lib/websocket.ts` — full rewrite (`useSessionStream`)
- `frontend/lib/__tests__/api.test.ts` — full rewrite
- `frontend/lib/__tests__/store.test.ts` — full rewrite
- `frontend/lib/__tests__/websocket.test.ts` — full rewrite
- `frontend/components/TopBar.tsx` — adapt as nav-only (remove run controls)

### Create
- `backend/api/routes/sessions.py`
- `backend/api/routes/profiles.py`
- `backend/api/routes/market.py`
- `backend/alembic/versions/0002_session_schema.py`
- `backend/tests/test_sessions.py`
- `backend/tests/test_profiles.py`
- `backend/tests/test_market_snapshot.py`
- `frontend/app/sessions/[id]/layout.tsx`
- `frontend/app/sessions/[id]/activity/page.tsx`
- `frontend/components/SessionIndicators.tsx`
- `frontend/components/SessionsTable.tsx`
- `frontend/components/NewAnalysisModal.tsx`
- `frontend/components/StageStrip.tsx`

---

## Task 1: Delete old backend code and clean up imports

**Files:**
- Delete: `backend/api/routes/analyze.py`
- Delete: `backend/src/agent/loop.py`
- Delete: `backend/src/agent/tabpfn_progress.py`
- Delete: `backend/tests/test_agent_loop.py`
- Delete: `backend/tests/test_analyze_route.py`
- Modify: `backend/src/agent/__init__.py`

- [ ] **Step 1: Delete the old route and agent files**

```bash
cd backend
rm api/routes/analyze.py
rm src/agent/loop.py
rm src/agent/tabpfn_progress.py
rm tests/test_agent_loop.py
rm tests/test_analyze_route.py
```

- [ ] **Step 2: Clear the agent __init__.py**

Replace `backend/src/agent/__init__.py` with:

```python
# Agents will be added in PR 3
```

- [ ] **Step 3: Verify existing tests still pass after deletions**

Run: `cd backend && uv run pytest tests/test_health.py tests/test_featurizer.py tests/test_inference.py -v`

Expected: all PASS (these don't touch the deleted code)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove old Run-based agent loop and analyze routes"
```

---

## Task 2: Replace DB models

**Files:**
- Modify: `backend/src/db/models.py`
- Modify: `backend/tests/test_db_models.py`

- [ ] **Step 1: Write the failing tests for new models**

Replace `backend/tests/test_db_models.py` with:

```python
from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine

from src.db.models import (
    AnalysisResult,
    Connector,
    ConnectorType,
    DataArtifact,
    FeatureArtifact,
    MarketProfile,
    SessionStage,
    SessionStatus,
)
from src.db.models import Session as SessionModel


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


def test_session_default_stage_and_status(engine):
    with Session(engine) as session:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2024, 1, 1),
            timeframe_end=date(2024, 6, 30),
        )
        session.add(s)
        session.commit()
        session.refresh(s)
    assert s.stage == SessionStage.CONFIGURING
    assert s.status == SessionStatus.WAITING
    assert s.auto is False
    assert s.featurizer_config == {}
    assert s.conversation == []
    assert s.activity_events == []
    assert s.stage_history == []


def test_session_id_is_uuid(engine):
    with Session(engine) as session:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2024, 1, 1),
            timeframe_end=date(2024, 6, 30),
        )
        session.add(s)
        session.commit()
        session.refresh(s)
    assert isinstance(s.id, uuid.UUID)


def test_session_stage_values():
    assert SessionStage.CONFIGURING == "configuring"
    assert SessionStage.DATA_GATHERING == "data_gathering"
    assert SessionStage.USER_REVIEW == "user_review"
    assert SessionStage.FEATURIZING == "featurizing"
    assert SessionStage.ANALYZING == "analyzing"
    assert SessionStage.EXPLAINING == "explaining"
    assert SessionStage.FOLLOW_UP == "follow_up"


def test_session_status_values():
    assert SessionStatus.RUNNING == "running"
    assert SessionStatus.WAITING == "waiting"
    assert SessionStatus.FAILED == "failed"
    assert SessionStatus.CANCELED == "canceled"


def test_data_artifact_defaults(engine):
    with Session(engine) as session:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2024, 1, 1),
            timeframe_end=date(2024, 6, 30),
        )
        session.add(s)
        session.commit()
        session.refresh(s)
        a = DataArtifact(session_id=s.id, source_hash="abc123")
        session.add(a)
        session.commit()
        session.refresh(a)
    assert a.round == 1
    assert a.cache_hit is False
    assert a.raw_data is None
    assert isinstance(a.id, uuid.UUID)


def test_market_profile_stores_regime_labels(engine):
    with Session(engine) as session:
        p = MarketProfile(
            id="oil",
            name="Oil Markets",
            regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
        )
        session.add(p)
        session.commit()
        session.refresh(p)
    assert p.regime_labels == ["bull_supercycle", "range_bound", "bust", "geopolitical_spike"]


def test_connector_type_values():
    assert ConnectorType.BUILTIN == "builtin"
    assert ConnectorType.SPEC == "spec"
    assert ConnectorType.GENERATED == "generated"


def test_connector_defaults(engine):
    with Session(engine) as session:
        c = Connector(id="yfinance", name="yfinance")
        session.add(c)
        session.commit()
        session.refresh(c)
    assert c.type == ConnectorType.BUILTIN
    assert c.is_active is True
    assert c.code is None
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_db_models.py -v
```

Expected: FAIL — `ImportError: cannot import name 'SessionStage'`

- [ ] **Step 3: Replace src/db/models.py with new models**

```python
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON as SAJson
from sqlalchemy import Column
from sqlalchemy import String as SAString
from sqlmodel import Field, SQLModel


class SessionStage(StrEnum):
    CONFIGURING    = "configuring"
    DATA_GATHERING = "data_gathering"
    USER_REVIEW    = "user_review"
    FEATURIZING    = "featurizing"
    ANALYZING      = "analyzing"
    EXPLAINING     = "explaining"
    FOLLOW_UP      = "follow_up"


class SessionStatus(StrEnum):
    RUNNING  = "running"
    WAITING  = "waiting"
    FAILED   = "failed"
    CANCELED = "canceled"


class Session(SQLModel, table=True):
    id:                uuid.UUID      = Field(default_factory=uuid.uuid4, primary_key=True)
    market_profile:    str
    timeframe_start:   date
    timeframe_end:     date
    stage:             str            = Field(
        default=SessionStage.CONFIGURING,
        sa_column=Column(SAString, nullable=False),
    )
    status:            str            = Field(
        default=SessionStatus.WAITING,
        sa_column=Column(SAString, nullable=False),
    )
    error:             str | None     = Field(default=None)
    auto:              bool           = Field(default=False)
    featurizer_config: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    pending_sources:   list[Any]      = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    conversation:      list[Any]      = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    activity_events:   list[Any]      = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    stage_history:     list[Any]      = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    created_at:        datetime       = Field(default_factory=lambda: datetime.now(UTC))
    updated_at:        datetime       = Field(default_factory=lambda: datetime.now(UTC))


class DataArtifact(SQLModel, table=True):
    id:                      uuid.UUID      = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id:              uuid.UUID      = Field(foreign_key="session.id")
    round:                   int            = Field(default=1)
    sources:                 list[Any]      = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    data_manifest:           dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    raw_data:                dict[str, Any] | None = Field(
        default=None, sa_column=Column(SAJson, nullable=True)
    )
    raw_data_ref:            str | None     = Field(default=None)
    source_hash:             str            = Field(default="")
    cached_from_session_id:  uuid.UUID | None = Field(default=None)
    cached_from_artifact_id: uuid.UUID | None = Field(default=None)
    cache_hit:               bool           = Field(default=False)
    created_at:              datetime       = Field(default_factory=lambda: datetime.now(UTC))


class FeatureArtifact(SQLModel, table=True):
    id:                          uuid.UUID      = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id:                  uuid.UUID      = Field(foreign_key="session.id")
    data_artifact_id:            uuid.UUID      = Field(foreign_key="dataartifact.id")
    featurizer_config_snapshot:  dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    feature_manifest:            dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    feature_matrix_ref:          str            = Field(default="")
    matrix_hash:                 str            = Field(default="")
    config_hash:                 str            = Field(default="")
    cached_from_session_id:      uuid.UUID | None = Field(default=None)
    cached_from_artifact_id:     uuid.UUID | None = Field(default=None)
    cache_hit:                   bool           = Field(default=False)
    created_at:                  datetime       = Field(default_factory=lambda: datetime.now(UTC))


class AnalysisResult(SQLModel, table=True):
    id:                      uuid.UUID      = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id:              uuid.UUID      = Field(foreign_key="session.id")
    feature_artifact_id:     uuid.UUID      = Field(foreign_key="featureartifact.id")
    regime:                  dict[str, Any] | None = Field(
        default=None, sa_column=Column(SAJson, nullable=True)
    )
    direction:               dict[str, Any] | None = Field(
        default=None, sa_column=Column(SAJson, nullable=True)
    )
    feature_importance:      dict[str, Any] | None = Field(
        default=None, sa_column=Column(SAJson, nullable=True)
    )
    drift:                   dict[str, Any] | None = Field(
        default=None, sa_column=Column(SAJson, nullable=True)
    )
    backtest:                dict[str, Any] | None = Field(
        default=None, sa_column=Column(SAJson, nullable=True)
    )
    summary:                 str | None     = Field(default=None)
    feature_hash:            str            = Field(default="")
    cached_from_session_id:  uuid.UUID | None = Field(default=None)
    cached_from_artifact_id: uuid.UUID | None = Field(default=None)
    cache_hit:               bool           = Field(default=False)
    created_at:              datetime       = Field(default_factory=lambda: datetime.now(UTC))


class ConnectorType(StrEnum):
    BUILTIN   = "builtin"
    SPEC      = "spec"
    GENERATED = "generated"


class Connector(SQLModel, table=True):
    id:          str            = Field(primary_key=True)
    name:        str
    description: str            = Field(default="")
    type:        str            = Field(
        default=ConnectorType.BUILTIN,
        sa_column=Column(SAString, nullable=False),
    )
    spec:        dict[str, Any] | None = Field(
        default=None, sa_column=Column(SAJson, nullable=True)
    )
    code:        str | None     = Field(default=None)
    tests:       str | None     = Field(default=None)
    is_active:   bool           = Field(default=True)
    created_at:  datetime       = Field(default_factory=lambda: datetime.now(UTC))


class MarketProfile(SQLModel, table=True):
    id:                        str            = Field(primary_key=True)
    name:                      str
    description:               str            = Field(default="")
    default_connectors:        list[str]      = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    default_featurizer_config: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(SAJson, nullable=False)
    )
    regime_labels:             list[str]      = Field(
        default_factory=list, sa_column=Column(SAJson, nullable=False)
    )
    created_at:                datetime       = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_db_models.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/db/models.py tests/test_db_models.py
git commit -m "feat: replace Run model with Session, DataArtifact, FeatureArtifact, AnalysisResult, Connector, MarketProfile"
```

---

## Task 3: Update Alembic and generate migration

**Files:**
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0002_session_schema.py`

- [ ] **Step 1: Update alembic/env.py to import new models**

Replace the `import src.db.models` line in `backend/alembic/env.py`:

```python
import src.db.models  # noqa: F401 — registers all tables with SQLModel.metadata
```

(The line is the same string but now it registers the new models. Verify it already says `import src.db.models` — if so, no change needed.)

- [ ] **Step 2: Create the migration**

With Docker Postgres running (`make dev` or `docker-compose up -d db`):

```bash
cd backend && uv run alembic revision --autogenerate -m "session schema"
```

Expected: creates `alembic/versions/0002_session_schema.py`

- [ ] **Step 3: Review the generated migration**

Open the generated file and verify it:
- Drops `run` table
- Creates `session`, `dataartifact`, `featureartifact`, `analysisresult`, `connector`, `marketprofile` tables
- Adds indexes: `idx_data_artifact_source_hash`, `idx_session_created_at`, `idx_data_artifact_session_id`, etc.

If the auto-generated migration is missing indexes, add them manually to the `upgrade()` function:

```python
op.create_index("idx_session_created_at", "session", ["created_at"])
op.create_index("idx_data_artifact_session_id", "dataartifact", ["session_id"])
op.create_index("idx_data_artifact_source_hash", "dataartifact", ["source_hash"])
op.create_index("idx_feature_artifact_session_id", "featureartifact", ["session_id"])
op.create_index("idx_feature_artifact_config_hash", "featureartifact", ["config_hash"])
op.create_index("idx_analysis_result_session_id", "analysisresult", ["session_id"])
op.create_index("idx_analysis_result_feature_hash", "analysisresult", ["feature_hash"])
op.create_index("idx_connector_is_active", "connector", ["is_active"])
```

And in `downgrade()`:
```python
op.drop_index("idx_connector_is_active", table_name="connector")
op.drop_index("idx_analysis_result_feature_hash", table_name="analysisresult")
op.drop_index("idx_analysis_result_session_id", table_name="analysisresult")
op.drop_index("idx_feature_artifact_config_hash", table_name="featureartifact")
op.drop_index("idx_feature_artifact_session_id", table_name="featureartifact")
op.drop_index("idx_data_artifact_source_hash", table_name="dataartifact")
op.drop_index("idx_data_artifact_session_id", table_name="dataartifact")
op.drop_index("idx_session_created_at", table_name="session")
```

- [ ] **Step 4: Verify Alembic migration test still passes**

```bash
cd backend && uv run pytest tests/test_alembic_config.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alembic/env.py alembic/versions/
git commit -m "feat: add Alembic migration for session schema (drop run, create 6 new tables)"
```

---

## Task 4: New API response models

**Files:**
- Modify: `backend/api/models.py`

- [ ] **Step 1: Replace api/models.py**

```python
from __future__ import annotations

from pydantic import BaseModel


class DataArtifactRef(BaseModel):
    artifact_id: str
    round: int
    cache_hit: bool
    created_at: str


class FeatureArtifactRef(BaseModel):
    artifact_id: str
    cache_hit: bool
    created_at: str


class AnalysisResultRef(BaseModel):
    artifact_id: str
    cache_hit: bool
    has_summary: bool
    created_at: str


class SessionArtifacts(BaseModel):
    data: list[DataArtifactRef]
    features: list[FeatureArtifactRef]
    analysis: list[AnalysisResultRef]


class SessionListItem(BaseModel):
    session_id: str
    market_profile: str
    timeframe_start: str
    timeframe_end: str
    stage: str
    status: str
    created_at: str
    updated_at: str


class SessionDetail(BaseModel):
    session_id: str
    market_profile: str
    timeframe_start: str
    timeframe_end: str
    stage: str
    status: str
    error: str | None
    auto: bool
    featurizer_config: dict
    conversation: list
    activity_events: list
    stage_history: list
    artifacts: SessionArtifacts
    created_at: str
    updated_at: str


class CreateSessionRequest(BaseModel):
    market_profile: str
    timeframe_start: str
    timeframe_end: str
    auto: bool = False


class CreateSessionResponse(BaseModel):
    session_id: str


class ProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    default_connectors: list[str]
    default_featurizer_config: dict
    regime_labels: list[str]


class IndicatorValue(BaseModel):
    price: float
    change_pct: float


class MarketSnapshotResponse(BaseModel):
    wti: IndicatorValue | None = None
    brent: IndicatorValue | None = None
    dxy: IndicatorValue | None = None
    gpr: IndicatorValue | None = None
    eia_inventory_change_mmbbl: float | None = None
    fetched_at: str
```

- [ ] **Step 2: Run the full test suite to confirm nothing is broken**

```bash
cd backend && uv run pytest tests/test_health.py tests/test_db_models.py -v
```

Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add api/models.py
git commit -m "feat: add session API response models"
```

---

## Task 5: Session CRUD routes

**Files:**
- Create: `backend/api/routes/sessions.py`
- Create: `backend/tests/test_sessions.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_sessions.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_create_session_returns_202(client):
    res = client.post(
        "/api/sessions",
        json={
            "market_profile": "oil",
            "timeframe_start": "2024-01-01",
            "timeframe_end": "2024-06-30",
        },
    )
    assert res.status_code == 202
    assert "session_id" in res.json()


def test_create_session_missing_fields_returns_422(client):
    res = client.post("/api/sessions", json={})
    assert res.status_code == 422


def test_list_sessions_returns_list(client):
    res = client.get("/api/sessions")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_session_not_found_returns_404(client):
    res = client.get("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_get_session_invalid_uuid_returns_422(client):
    res = client.get("/api/sessions/not-a-uuid")
    assert res.status_code == 422


def test_get_session_roundtrip(client):
    create_res = client.post(
        "/api/sessions",
        json={
            "market_profile": "oil",
            "timeframe_start": "2024-01-01",
            "timeframe_end": "2024-06-30",
            "auto": True,
        },
    )
    session_id = create_res.json()["session_id"]

    get_res = client.get(f"/api/sessions/{session_id}")
    assert get_res.status_code == 200
    body = get_res.json()
    assert body["session_id"] == session_id
    assert body["market_profile"] == "oil"
    assert body["stage"] == "configuring"
    assert body["status"] == "waiting"
    assert body["auto"] is True
    assert body["artifacts"] == {"data": [], "features": [], "analysis": []}


def test_delete_session(client):
    create_res = client.post(
        "/api/sessions",
        json={
            "market_profile": "oil",
            "timeframe_start": "2024-01-01",
            "timeframe_end": "2024-06-30",
        },
    )
    session_id = create_res.json()["session_id"]
    del_res = client.delete(f"/api/sessions/{session_id}")
    assert del_res.status_code == 200
    get_res = client.get(f"/api/sessions/{session_id}")
    assert get_res.status_code == 404


def test_delete_session_not_found_returns_404(client):
    res = client.delete("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_sessions.py -v
```

Expected: FAIL — `404` or `422` because `/api/sessions` routes don't exist yet

- [ ] **Step 3: Create backend/api/routes/sessions.py**

```python
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import (
    AnalysisResultRef,
    CreateSessionRequest,
    CreateSessionResponse,
    DataArtifactRef,
    FeatureArtifactRef,
    SessionArtifacts,
    SessionDetail,
    SessionListItem,
)
from src.db.models import AnalysisResult, DataArtifact, FeatureArtifact
from src.db.models import Session as SessionModel
from src.db.session import get_session

router = APIRouter(tags=["sessions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _isoformat(dt) -> str:
    return dt.isoformat() if dt else ""


async def _build_artifacts(db: AsyncSession, session_id: uuid.UUID) -> SessionArtifacts:
    data_rows = (
        await db.execute(select(DataArtifact).where(DataArtifact.session_id == session_id))
    ).scalars().all()
    feature_rows = (
        await db.execute(select(FeatureArtifact).where(FeatureArtifact.session_id == session_id))
    ).scalars().all()
    analysis_rows = (
        await db.execute(select(AnalysisResult).where(AnalysisResult.session_id == session_id))
    ).scalars().all()

    return SessionArtifacts(
        data=[
            DataArtifactRef(
                artifact_id=str(r.id),
                round=r.round,
                cache_hit=r.cache_hit,
                created_at=_isoformat(r.created_at),
            )
            for r in data_rows
        ],
        features=[
            FeatureArtifactRef(
                artifact_id=str(r.id),
                cache_hit=r.cache_hit,
                created_at=_isoformat(r.created_at),
            )
            for r in feature_rows
        ],
        analysis=[
            AnalysisResultRef(
                artifact_id=str(r.id),
                cache_hit=r.cache_hit,
                has_summary=r.summary is not None,
                created_at=_isoformat(r.created_at),
            )
            for r in analysis_rows
        ],
    )


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
        conversation=s.conversation,
        activity_events=s.activity_events,
        stage_history=s.stage_history,
        artifacts=artifacts,
        created_at=_isoformat(s.created_at),
        updated_at=_isoformat(s.updated_at),
    )


@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_session(
    req: CreateSessionRequest, db: SessionDep
) -> CreateSessionResponse:
    from datetime import date
    s = SessionModel(
        market_profile=req.market_profile,
        timeframe_start=date.fromisoformat(req.timeframe_start),
        timeframe_end=date.fromisoformat(req.timeframe_end),
        auto=req.auto,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return CreateSessionResponse(session_id=str(s.id))


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(db: SessionDep) -> list[SessionListItem]:
    rows = (
        await db.execute(
            select(SessionModel).order_by(SessionModel.created_at.desc()).limit(100)
        )
    ).scalars().all()
    return [
        SessionListItem(
            session_id=str(s.id),
            market_profile=s.market_profile,
            timeframe_start=str(s.timeframe_start),
            timeframe_end=str(s.timeframe_end),
            stage=s.stage,
            status=s.status,
            created_at=_isoformat(s.created_at),
            updated_at=_isoformat(s.updated_at),
        )
        for s in rows
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, db: SessionDep) -> SessionDetail:
    try:
        uid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")
    s = await db.get(SessionModel, uid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    artifacts = await _build_artifacts(db, uid)
    return _to_detail(s, artifacts)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: SessionDep) -> dict:
    try:
        uid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")
    s = await db.get(SessionModel, uid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(s)
    await db.commit()
    return {"session_id": session_id}
```

- [ ] **Step 4: Run the session tests**

```bash
cd backend && uv run pytest tests/test_sessions.py -v
```

Expected: all PASS (TestClient uses SQLite in-memory via the app's database setup — if DB is not mocked, this will require a real DB; see note below)

> **Note:** The existing `conftest.py` uses the real app with `TestClient`. Session tests hit the real database. Either run `make dev` first to start Postgres, or update `conftest.py` to override the DB URL with SQLite for tests. Check the existing `test_health.py` — if it passes without a DB, the app handles missing DB gracefully and you may need to mock the DB for session tests. If DB is required, ensure `docker-compose up -d db` is running.

- [ ] **Step 5: Commit**

```bash
git add api/routes/sessions.py tests/test_sessions.py
git commit -m "feat: add session CRUD routes (POST/GET/DELETE /api/sessions)"
```

---

## Task 6: Market profiles routes + oil profile seed

**Files:**
- Create: `backend/api/routes/profiles.py`
- Create: `backend/tests/test_profiles.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_profiles.py`:

```python
def test_list_profiles_returns_list(client):
    res = client.get("/api/profiles")
    assert res.status_code == 200
    profiles = res.json()
    assert isinstance(profiles, list)


def test_list_profiles_includes_oil(client):
    res = client.get("/api/profiles")
    ids = [p["id"] for p in res.json()]
    assert "oil" in ids


def test_get_oil_profile(client):
    res = client.get("/api/profiles/oil")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "oil"
    assert body["name"] == "Oil Markets"
    assert "bull_supercycle" in body["regime_labels"]
    assert "windows" in body["default_featurizer_config"]


def test_get_profile_not_found(client):
    res = client.get("/api/profiles/nonexistent")
    assert res.status_code == 404


import pytest
from fastapi.testclient import TestClient
from api.main import app

@pytest.fixture
def client():
    return TestClient(app)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_profiles.py -v
```

Expected: FAIL — 404 because `/api/profiles` routes don't exist yet

- [ ] **Step 3: Create backend/api/routes/profiles.py**

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import ProfileResponse
from src.db.models import MarketProfile
from src.db.session import get_session

router = APIRouter(tags=["profiles"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/profiles", response_model=list[ProfileResponse])
async def list_profiles(db: SessionDep) -> list[ProfileResponse]:
    rows = (await db.execute(select(MarketProfile))).scalars().all()
    return [
        ProfileResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            default_connectors=p.default_connectors,
            default_featurizer_config=p.default_featurizer_config,
            regime_labels=p.regime_labels,
        )
        for p in rows
    ]


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str, db: SessionDep) -> ProfileResponse:
    p = await db.get(MarketProfile, profile_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        default_connectors=p.default_connectors,
        default_featurizer_config=p.default_featurizer_config,
        regime_labels=p.regime_labels,
    )
```

- [ ] **Step 4: Create the oil profile seed data**

Create `backend/src/db/seed.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.db.models import MarketProfile

OIL_PROFILE = MarketProfile(
    id="oil",
    name="Oil Markets",
    description="WTI/Brent crude oil regime analysis using macro, geopolitical, and energy signals.",
    default_connectors=["yfinance", "fred", "eia", "gpr"],
    default_featurizer_config={
        "windows": [5, 20, 60],
        "lags": [1, 5, 20],
        "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
        "energy_specific": True,
    },
    regime_labels=["bull_supercycle", "range_bound", "bust", "geopolitical_spike"],
    created_at=datetime.now(UTC),
)


async def seed_profiles(db: AsyncSession) -> None:
    existing = await db.get(MarketProfile, "oil")
    if existing is None:
        db.add(OIL_PROFILE)
        await db.commit()
```

- [ ] **Step 5: Wire seed into lifespan (done in Task 8 — come back to run tests then)**

- [ ] **Step 6: Commit the route and seed files**

```bash
git add api/routes/profiles.py src/db/seed.py tests/test_profiles.py
git commit -m "feat: add profiles routes and oil profile seed data"
```

---

## Task 7: Market snapshot route

**Files:**
- Create: `backend/api/routes/market.py`
- Create: `backend/tests/test_market_snapshot.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_market_snapshot.py`:

```python
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_market_snapshot_returns_200(client):
    with patch("api.routes.market._fetch_price_change", return_value={"price": 83.0, "change_pct": 1.2}):
        res = client.get("/api/market/snapshot")
    assert res.status_code == 200
    body = res.json()
    assert "fetched_at" in body
    assert "wti" in body
    assert "brent" in body
    assert "dxy" in body


def test_market_snapshot_returns_null_on_failure(client):
    with patch("api.routes.market._fetch_price_change", side_effect=Exception("network error")):
        res = client.get("/api/market/snapshot")
    assert res.status_code == 200
    body = res.json()
    assert body["wti"] is None
    assert body["brent"] is None
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && uv run pytest tests/test_market_snapshot.py -v
```

Expected: FAIL — 404 because route doesn't exist

- [ ] **Step 3: Create backend/api/routes/market.py**

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
import yfinance as yf
from fastapi import APIRouter

from api.models import IndicatorValue, MarketSnapshotResponse

router = APIRouter(tags=["market"])
log = structlog.get_logger()


def _fetch_price_change(ticker: str) -> dict:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=7)
    data = yf.download(ticker, start=start.isoformat(), end=end.isoformat(), progress=False, auto_adjust=True)
    if len(data) < 2:
        raise ValueError(f"insufficient data for {ticker}")
    latest = float(data["Close"].iloc[-1])
    prev = float(data["Close"].iloc[-2])
    change_pct = round((latest - prev) / prev * 100, 2)
    return {"price": round(latest, 2), "change_pct": change_pct}


def _safe_fetch(ticker: str) -> IndicatorValue | None:
    try:
        result = _fetch_price_change(ticker)
        return IndicatorValue(**result)
    except Exception as exc:
        log.warning("market_snapshot.fetch_failed", ticker=ticker, error=str(exc))
        return None


@router.get("/market/snapshot", response_model=MarketSnapshotResponse)
async def get_market_snapshot() -> MarketSnapshotResponse:
    return MarketSnapshotResponse(
        wti=_safe_fetch("CL=F"),
        brent=_safe_fetch("BZ=F"),
        dxy=_safe_fetch("DX-Y.NYB"),
        fetched_at=datetime.now(UTC).isoformat(),
    )
```

> **Note:** `gpr` and `eia_inventory_change_mmbbl` are omitted for now — GPR requires a FRED API key and EIA requires a separate API key. Both fields default to `None` in the response model. Add them in a follow-up once keys are confirmed available in the environment.

- [ ] **Step 4: Run the market snapshot tests**

```bash
cd backend && uv run pytest tests/test_market_snapshot.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/market.py tests/test_market_snapshot.py
git commit -m "feat: add GET /api/market/snapshot (yfinance WTI, Brent, DXY)"
```

---

## Task 8: Update WebSocket handler and wire up FastAPI app

**Files:**
- Modify: `backend/api/ws.py`
- Modify: `backend/api/main.py`
- Modify: `backend/tests/test_ws.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Replace api/ws.py with session-scoped stub**

```python
import structlog
from fastapi import WebSocket, WebSocketDisconnect

log = structlog.get_logger()


async def session_stream_handler(websocket: WebSocket, session_id: str) -> None:
    """WebSocket stub for PR 1. Accepts connections; agent events arrive in PR 3."""
    await websocket.accept()
    log.info("ws.connected", session_id=session_id)
    try:
        while True:
            # Keep connection alive. Agents will publish via Redis in PR 3.
            await websocket.receive_text()
    except WebSocketDisconnect:
        log.info("ws.disconnected", session_id=session_id)
```

- [ ] **Step 2: Update api/main.py**

Replace the full content of `backend/api/main.py`:

```python
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from api.logging import configure_logging, request_log_level, should_log_request
from api.routes import derivatives, profiles, sessions, market
from api.ws import session_stream_handler
from src.config import settings
from src.db.seed import seed_profiles
from src.db.session import engine

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
    async with AsyncSession(engine) as db:
        await seed_profiles(db)
    log.info("startup", environment=settings.environment)
    yield
    log.info("shutdown")


app = FastAPI(title="Signalyst API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api")
app.include_router(profiles.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(derivatives.router, prefix="/api")
app.add_api_websocket_route("/ws/sessions/{session_id}/stream", session_stream_handler)


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = perf_counter()
    response = await call_next(request)
    include_noisy = logging.getLogger().isEnabledFor(logging.DEBUG)
    if should_log_request(request.method, request.url.path, include_noisy=include_noisy):
        duration_ms = round((perf_counter() - start) * 1000, 2)
        log_method = getattr(log, request_log_level(request.method, request.url.path))
        log_method(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

> **Note:** Add `from api.routes import derivatives, profiles, sessions, market` — you'll need to create `backend/api/routes/__init__.py` if it doesn't expose these, or adjust to direct imports.

- [ ] **Step 3: Update tests/test_ws.py for the session stub**

```python
from __future__ import annotations

import pytest
from fastapi import WebSocketDisconnect

from api.ws import session_stream_handler


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self._messages = iter(["ping", WebSocketDisconnect()])

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        msg = next(self._messages)
        if isinstance(msg, WebSocketDisconnect):
            raise msg
        return msg


@pytest.mark.asyncio
async def test_session_stream_handler_accepts_and_disconnects() -> None:
    ws = _FakeWebSocket()
    await session_stream_handler(ws, "test-session-id")  # type: ignore[arg-type]
    assert ws.accepted
```

- [ ] **Step 4: Update tests/test_routes.py — remove old run/analyze tests**

Keep only the derivatives tests and the health test. Remove all `test_analyze_*` and `test_get_run_*` tests. Final file:

```python
import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200


def test_derivatives_missing_required_fields(client):
    res = client.post("/api/derivatives/price", json={})
    assert res.status_code == 422


def test_derivatives_invalid_option_type(client):
    res = client.post(
        "/api/derivatives/price",
        json={
            "regime": "geopolitical_spike",
            "spot": 87.5,
            "strike": 90.0,
            "tenor_days": 30,
            "option_type": "swap",
        },
    )
    assert res.status_code == 422


def test_derivatives_invalid_style(client):
    res = client.post(
        "/api/derivatives/price",
        json={
            "regime": "geopolitical_spike",
            "spot": 87.5,
            "strike": 90.0,
            "tenor_days": 30,
            "style": "asian",
        },
    )
    assert res.status_code == 422
```

- [ ] **Step 5: Run the full backend test suite**

```bash
cd backend && uv run pytest -v --ignore=tests/test_agent_tools.py --ignore=tests/test_data_tools.py --ignore=tests/test_deferred_tools.py
```

Expected: all PASS (agent/data tools tests may still reference old imports — fix those in a follow-up if needed, or delete `test_agent_tools.py` and `test_deferred_tools.py` since they test the old loop)

- [ ] **Step 6: Commit**

```bash
git add api/ws.py api/main.py tests/test_ws.py tests/test_routes.py
git commit -m "feat: wire new routes into FastAPI app, update WS handler for session streams"
```

---

## Task 9: Delete old frontend files

**Files:** All deletions listed in the File Map above.

- [ ] **Step 1: Delete old components and their tests**

```bash
cd frontend
rm components/AgentDrawer.tsx components/__tests__/AgentDrawer.test.tsx
rm components/AgentProgressTimeline.tsx components/__tests__/AgentProgressTimeline.test.tsx
rm components/AgentStream.tsx
rm components/ChatPanel.tsx components/__tests__/ChatPanel.test.tsx
rm components/ResultsPanel.tsx components/__tests__/ResultsPanel.test.tsx
rm components/ResultsTabs.tsx components/__tests__/ResultsTabs.test.tsx
rm components/ThoughtStream.tsx
rm lib/agentProgress.ts lib/__tests__/agentProgress.test.ts
```

- [ ] **Step 2: Run the frontend test suite to confirm remaining tests still pass**

```bash
cd frontend && npm run test
```

Expected: tests for `lib/__tests__/api.test.ts`, `lib/__tests__/store.test.ts`, `lib/__tests__/websocket.test.ts`, and tab components still run. Some may fail because they import from the old API — that's expected and will be fixed in Tasks 10-12.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove old run-based frontend components and tests"
```

---

## Task 10: Rewrite lib/api.ts

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/__tests__/api.test.ts`

- [ ] **Step 1: Write the failing tests**

Replace `frontend/lib/__tests__/api.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

beforeEach(() => {
  vi.clearAllMocks();
});

function mockOk(data: unknown) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(""),
  });
}

function mockError(status: number, text = "error") {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    text: () => Promise.resolve(text),
  });
}

describe("api.createSession", () => {
  it("posts to /api/sessions and returns session_id", async () => {
    const { api } = await import("../api");
    mockOk({ session_id: "abc-123" });
    const result = await api.createSession({
      market_profile: "oil",
      timeframe_start: "2024-01-01",
      timeframe_end: "2024-06-30",
    });
    expect(result.session_id).toBe("abc-123");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/sessions"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws on API error", async () => {
    const { api } = await import("../api");
    mockError(422, "validation error");
    await expect(
      api.createSession({
        market_profile: "oil",
        timeframe_start: "2024-01-01",
        timeframe_end: "2024-06-30",
      })
    ).rejects.toThrow("API error 422");
  });
});

describe("api.getSessions", () => {
  it("fetches /api/sessions", async () => {
    const { api } = await import("../api");
    mockOk([]);
    const result = await api.getSessions();
    expect(Array.isArray(result)).toBe(true);
  });
});

describe("api.getProfiles", () => {
  it("fetches /api/profiles", async () => {
    const { api } = await import("../api");
    mockOk([{ id: "oil", name: "Oil Markets" }]);
    const result = await api.getProfiles();
    expect(result[0].id).toBe("oil");
  });
});

describe("api.getMarketSnapshot", () => {
  it("fetches /api/market/snapshot", async () => {
    const { api } = await import("../api");
    mockOk({ wti: { price: 83.0, change_pct: 1.2 }, fetched_at: "2024-01-01T00:00:00Z" });
    const result = await api.getMarketSnapshot();
    expect(result.wti?.price).toBe(83.0);
  });
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd frontend && npm run test -- lib/__tests__/api.test.ts
```

Expected: FAIL — imports from `../api` fail because the file still has old types

- [ ] **Step 3: Replace frontend/lib/api.ts**

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 30_000;

export type SessionStage =
  | "configuring"
  | "data_gathering"
  | "user_review"
  | "featurizing"
  | "analyzing"
  | "explaining"
  | "follow_up";

export type SessionStatus = "running" | "waiting" | "failed" | "canceled";

export type FeaturizerConfig = {
  windows: number[];
  lags: number[];
  feature_families: string[];
  energy_specific: boolean;
};

export type DataArtifactRef = {
  artifact_id: string;
  round: number;
  cache_hit: boolean;
  created_at: string;
};

export type FeatureArtifactRef = {
  artifact_id: string;
  cache_hit: boolean;
  created_at: string;
};

export type AnalysisResultRef = {
  artifact_id: string;
  cache_hit: boolean;
  has_summary: boolean;
  created_at: string;
};

export type SessionArtifacts = {
  data: DataArtifactRef[];
  features: FeatureArtifactRef[];
  analysis: AnalysisResultRef[];
};

export type ChatMessage = {
  role: "user" | "agent";
  content: string;
  created_at: string;
};

export type ActivityEvent = {
  event_id: string;
  type: string;
  created_at: string;
  [key: string]: unknown;
};

export type StageHistoryEntry = {
  stage: SessionStage;
  entered_at: string;
};

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
  conversation: ChatMessage[];
  activity_events: ActivityEvent[];
  stage_history: StageHistoryEntry[];
  artifacts: SessionArtifacts;
  created_at: string;
  updated_at: string;
};

export type SessionListItem = {
  session_id: string;
  market_profile: string;
  timeframe_start: string;
  timeframe_end: string;
  stage: SessionStage;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
};

export type MarketProfile = {
  id: string;
  name: string;
  description: string;
  default_connectors: string[];
  default_featurizer_config: FeaturizerConfig;
  regime_labels: string[];
};

export type MarketSnapshot = {
  wti: { price: number; change_pct: number } | null;
  brent: { price: number; change_pct: number } | null;
  dxy: { price: number; change_pct: number } | null;
  gpr: { value: number; change_pct: number } | null;
  eia_inventory_change_mmbbl: number | null;
  fetched_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...init,
    });
    if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  getMarketSnapshot: () =>
    request<MarketSnapshot>("/api/market/snapshot"),

  createSession: (body: {
    market_profile: string;
    timeframe_start: string;
    timeframe_end: string;
    auto?: boolean;
  }) =>
    request<{ session_id: string }>("/api/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getSessions: () => request<SessionListItem[]>("/api/sessions"),

  getSession: (id: string) => request<Session>(`/api/sessions/${id}`),

  deleteSession: (id: string) =>
    request<void>(`/api/sessions/${id}`, { method: "DELETE" }),

  getProfiles: () => request<MarketProfile[]>("/api/profiles"),
};
```

- [ ] **Step 4: Run the API tests**

```bash
cd frontend && npm run test -- lib/__tests__/api.test.ts
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add lib/api.ts lib/__tests__/api.test.ts
git commit -m "feat: rewrite lib/api.ts with session-based types and endpoints"
```

---

## Task 11: Rewrite lib/store.ts

**Files:**
- Modify: `frontend/lib/store.ts`
- Modify: `frontend/lib/__tests__/store.test.ts`

- [ ] **Step 1: Write the failing tests**

Replace `frontend/lib/__tests__/store.test.ts`:

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { useSessionStore } from "../store";
import type { Session } from "../api";

function mockSession(overrides: Partial<Session> = {}): Session {
  return {
    session_id: "ses-1",
    market_profile: "oil",
    timeframe_start: "2024-01-01",
    timeframe_end: "2024-06-30",
    stage: "configuring",
    status: "waiting",
    error: null,
    auto: false,
    featurizer_config: { windows: [5, 20, 60], lags: [1, 5, 20], feature_families: [], energy_specific: true },
    conversation: [],
    activity_events: [],
    stage_history: [],
    artifacts: { data: [], features: [], analysis: [] },
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  useSessionStore.getState().clearSession();
});

describe("useSessionStore", () => {
  it("starts with null sessionId", () => {
    expect(useSessionStore.getState().sessionId).toBeNull();
  });

  it("setSession populates store from session object", () => {
    useSessionStore.getState().setSession(mockSession());
    const state = useSessionStore.getState();
    expect(state.sessionId).toBe("ses-1");
    expect(state.stage).toBe("configuring");
    expect(state.status).toBe("waiting");
    expect(state.error).toBeNull();
  });

  it("clearSession resets all fields", () => {
    useSessionStore.getState().setSession(mockSession());
    useSessionStore.getState().clearSession();
    const state = useSessionStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.stage).toBeNull();
    expect(state.wsMessages).toEqual([]);
  });

  it("appendWsMessage adds to wsMessages", () => {
    useSessionStore.getState().appendWsMessage({ type: "thought", content: "thinking" });
    expect(useSessionStore.getState().wsMessages).toHaveLength(1);
    expect(useSessionStore.getState().wsMessages[0].type).toBe("thought");
  });

  it("appendWsMessage caps at 500 messages", () => {
    for (let i = 0; i < 510; i++) {
      useSessionStore.getState().appendWsMessage({ type: "thought", content: `msg ${i}` });
    }
    expect(useSessionStore.getState().wsMessages).toHaveLength(500);
  });
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd frontend && npm run test -- lib/__tests__/store.test.ts
```

Expected: FAIL — `useSessionStore` not found (old store has `useRunStore`)

- [ ] **Step 3: Replace frontend/lib/store.ts**

```typescript
import { create } from "zustand";
import type {
  ActivityEvent,
  ChatMessage,
  FeaturizerConfig,
  Session,
  SessionArtifacts,
  SessionStage,
  SessionStatus,
} from "./api";

type WsMessage = Record<string, unknown> & { type: string };

const EMPTY_ARTIFACTS: SessionArtifacts = { data: [], features: [], analysis: [] };
const MAX_WS_MESSAGES = 500;

type SessionStore = {
  sessionId: string | null;
  stage: SessionStage | null;
  status: SessionStatus | null;
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

export const useSessionStore = create<SessionStore>((set) => ({
  sessionId: null,
  stage: null,
  status: null,
  featurizerConfig: null,
  conversation: [],
  activityEvents: [],
  wsMessages: [],
  artifacts: EMPTY_ARTIFACTS,
  error: null,

  setSession: (session) =>
    set({
      sessionId: session.session_id,
      stage: session.stage,
      status: session.status,
      featurizerConfig: session.featurizer_config,
      conversation: session.conversation,
      activityEvents: session.activity_events,
      artifacts: session.artifacts,
      error: session.error,
    }),

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
      featurizerConfig: null,
      conversation: [],
      activityEvents: [],
      wsMessages: [],
      artifacts: EMPTY_ARTIFACTS,
      error: null,
    }),
}));
```

- [ ] **Step 4: Run the store tests**

```bash
cd frontend && npm run test -- lib/__tests__/store.test.ts
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add lib/store.ts lib/__tests__/store.test.ts
git commit -m "feat: rewrite lib/store.ts as useSessionStore (replaces useRunStore)"
```

---

## Task 12: Rewrite lib/websocket.ts

**Files:**
- Modify: `frontend/lib/websocket.ts`
- Modify: `frontend/lib/__tests__/websocket.test.ts`

- [ ] **Step 1: Write the failing tests**

Replace `frontend/lib/__tests__/websocket.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  readyState = 0;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  close() { this.readyState = 3; }
}

vi.stubGlobal("WebSocket", MockWebSocket);
vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }));

beforeEach(() => { MockWebSocket.instances = []; });

describe("useSessionStream", () => {
  it("connects to the correct session WS URL", async () => {
    const { useSessionStream } = await import("../websocket");
    renderHook(() => useSessionStream("ses-abc"));
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain("/ws/sessions/ses-abc/stream");
  });

  it("does not connect when sessionId is null", async () => {
    const { useSessionStream } = await import("../websocket");
    renderHook(() => useSessionStream(null));
    expect(MockWebSocket.instances).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run to verify failure**

```bash
cd frontend && npm run test -- lib/__tests__/websocket.test.ts
```

Expected: FAIL — `useSessionStream` not exported from `../websocket`

- [ ] **Step 3: Replace frontend/lib/websocket.ts**

```typescript
"use client";

import { useEffect, useRef } from "react";
import { useSessionStore } from "./store";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

export function useSessionStream(sessionId: string | null) {
  const { appendWsMessage, setSession } = useSessionStore();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);

  useEffect(() => {
    if (!sessionId) return;

    function connect() {
      const socket = new WebSocket(`${WS_URL}/ws/sessions/${sessionId}/stream`);
      wsRef.current = socket;

      socket.onopen = () => {
        attemptRef.current = 0;
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as Record<string, unknown> & { type: string };
          if (msg.type === "stage_transition" || msg.type === "artifact_ready") {
            fetch(`${API_URL}/api/sessions/${sessionId}`)
              .then((r) => r.json())
              .then(setSession)
              .catch(() => {});
          }
          appendWsMessage(msg);
        } catch {}
      };

      socket.onclose = () => {
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attemptRef.current, RECONNECT_MAX_MS);
        attemptRef.current += 1;
        reconnectRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      wsRef.current?.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, [sessionId, appendWsMessage, setSession]);
}
```

- [ ] **Step 4: Run the websocket tests**

```bash
cd frontend && npm run test -- lib/__tests__/websocket.test.ts
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add lib/websocket.ts lib/__tests__/websocket.test.ts
git commit -m "feat: rewrite lib/websocket.ts as useSessionStream with exponential backoff reconnect"
```

---

## Task 13: Frontend routing skeleton and shared session layout

**Files:**
- Create: `frontend/app/sessions/[id]/layout.tsx`
- Create: `frontend/app/sessions/[id]/activity/page.tsx`
- Create: `frontend/components/StageStrip.tsx`

- [ ] **Step 1: Create the stage strip component**

Create `frontend/components/StageStrip.tsx`:

```tsx
"use client";

import type { SessionStage } from "@/lib/api";

const STAGES: { key: SessionStage; label: string }[] = [
  { key: "configuring",    label: "CONFIG" },
  { key: "data_gathering", label: "DATA" },
  { key: "user_review",    label: "REVIEW" },
  { key: "featurizing",    label: "FEATURES" },
  { key: "analyzing",      label: "ANALYZE" },
  { key: "explaining",     label: "EXPLAIN" },
  { key: "follow_up",      label: "FOLLOW-UP" },
];

const STAGE_ORDER = STAGES.map((s) => s.key);

type Props = { currentStage: SessionStage | null };

export function StageStrip({ currentStage }: Props) {
  const currentIdx = currentStage ? STAGE_ORDER.indexOf(currentStage) : -1;

  return (
    <div className="flex items-center px-4 py-2 border-b border-[#21262d] bg-[#111827] gap-1">
      {STAGES.map((stage, idx) => {
        const isDone    = idx < currentIdx;
        const isActive  = idx === currentIdx;
        const isPending = idx > currentIdx;

        return (
          <div key={stage.key} className="flex items-center gap-1 flex-1">
            <div className="flex flex-col items-center flex-1">
              <div
                className={[
                  "h-1 w-full rounded-full",
                  isDone   ? "bg-[#22c55e]" : "",
                  isActive ? "bg-[#3b82f6] animate-pulse" : "",
                  isPending ? "bg-[#374151]" : "",
                ].join(" ")}
              />
              <span
                className={[
                  "text-[10px] mt-1 font-mono tracking-wider",
                  isDone   ? "text-[#22c55e]" : "",
                  isActive ? "text-[#60a5fa]" : "",
                  isPending ? "text-[#4b5563]" : "",
                ].join(" ")}
              >
                {stage.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Create the shared session layout**

Create `frontend/app/sessions/[id]/layout.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { useParams, useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useSessionStore } from "@/lib/store";
import { useSessionStream } from "@/lib/websocket";
import { api } from "@/lib/api";
import { StageStrip } from "@/components/StageStrip";

const TABS = [
  { label: "Activity", href: (id: string) => `/sessions/${id}/activity` },
  { label: "Data",     href: (id: string) => `/sessions/${id}/data` },
  { label: "Results",  href: (id: string) => `/sessions/${id}/results` },
];

export default function SessionLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const { sessionId, stage, status, setSession } = useSessionStore();

  useSessionStream(id ?? null);

  useEffect(() => {
    if (!id) return;
    api.getSession(id).then(setSession).catch(() => router.push("/"));
  }, [id]);

  return (
    <div className="flex flex-col h-screen bg-[#060b14] text-[#f9fafb]">
      {/* Top nav */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-[#21262d] bg-[#111827]">
        <span className="font-bold text-[#3b82f6] text-base tracking-tight">
          ■ SIGNALYST
        </span>
        <Link
          href="/"
          className="text-sm px-3 py-1 rounded border border-[#21262d] text-[#9ca3af] hover:text-[#f9fafb] transition-colors"
        >
          + NEW ANALYSIS
        </Link>
      </header>

      {/* Session header */}
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
              <span className={[
                "text-xs",
                status === "running" ? "text-[#22c55e]" : "",
                status === "waiting" ? "text-[#9ca3af]" : "",
                status === "failed"  ? "text-[#ef4444]" : "",
                status === "canceled" ? "text-[#f59e0b]" : "",
              ].join(" ")}>
                {status === "running" && "● "}
                {status}
              </span>
            )}
          </>
        )}
      </div>

      {/* Stage progress strip */}
      <StageStrip currentStage={stage} />

      {/* Tab bar */}
      <div className="flex gap-4 px-4 border-b border-[#21262d] bg-[#111827]">
        {TABS.map((tab) => {
          const href = tab.href(id ?? "");
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

      {/* Page content */}
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
```

- [ ] **Step 3: Create the activity placeholder page**

Create `frontend/app/sessions/[id]/activity/page.tsx`:

```tsx
export default function ActivityPage() {
  return (
    <div className="flex items-center justify-center h-full text-[#4b5563] text-sm">
      Activity feed — live agent stream available in PR 3
    </div>
  );
}
```

- [ ] **Step 4: Verify the frontend type-checks**

```bash
cd frontend && npm run type-check
```

Expected: PASS (no TypeScript errors)

- [ ] **Step 5: Commit**

```bash
git add app/sessions/ components/StageStrip.tsx
git commit -m "feat: add session routing skeleton with shared layout, stage strip, and activity placeholder"
```

---

## Task 14: Home page with sessions table, new analysis modal, and indicators strip

**Files:**
- Modify: `frontend/app/page.tsx`
- Create: `frontend/components/SessionIndicators.tsx`
- Create: `frontend/components/SessionsTable.tsx`
- Create: `frontend/components/NewAnalysisModal.tsx`
- Modify: `frontend/components/TopBar.tsx`

- [ ] **Step 1: Create SessionIndicators component**

Create `frontend/components/SessionIndicators.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { MarketSnapshot } from "@/lib/api";

function IndicatorCard({
  label,
  value,
  changePct,
  warn,
}: {
  label: string;
  value: string;
  changePct: number | null;
  warn?: boolean;
}) {
  const changeColor =
    changePct === null
      ? "text-[#6b7280]"
      : changePct >= 0
      ? "text-[#22c55e]"
      : "text-[#ef4444]";

  return (
    <div
      className={[
        "flex-1 px-3 py-2 rounded border bg-[#111827]",
        warn ? "border-[#f59e0b]" : "border-[#21262d]",
      ].join(" ")}
    >
      <div className="text-[10px] text-[#6b7280] uppercase tracking-wider mb-1">{label}</div>
      <div className="text-base font-mono text-[#f9fafb]">{value}</div>
      {changePct !== null && (
        <div className={`text-xs ${changeColor}`}>
          {changePct >= 0 ? "+" : ""}
          {changePct.toFixed(2)}%
        </div>
      )}
    </div>
  );
}

export function SessionIndicators() {
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);

  useEffect(() => {
    api.getMarketSnapshot().then(setSnapshot).catch(() => {});
  }, []);

  return (
    <div className="flex gap-2 px-4 py-3 border-b border-[#21262d]">
      <IndicatorCard
        label="WTI Crude"
        value={snapshot?.wti ? `$${snapshot.wti.price.toFixed(2)}` : "—"}
        changePct={snapshot?.wti?.change_pct ?? null}
      />
      <IndicatorCard
        label="Brent"
        value={snapshot?.brent ? `$${snapshot.brent.price.toFixed(2)}` : "—"}
        changePct={snapshot?.brent?.change_pct ?? null}
      />
      <IndicatorCard
        label="DXY"
        value={snapshot?.dxy ? snapshot.dxy.price.toFixed(1) : "—"}
        changePct={snapshot?.dxy?.change_pct ?? null}
      />
      <IndicatorCard
        label="GPR Index"
        value={snapshot?.gpr ? String(snapshot.gpr.value) : "—"}
        changePct={snapshot?.gpr?.change_pct ?? null}
        warn={(snapshot?.gpr?.value ?? 0) > 200}
      />
    </div>
  );
}
```

- [ ] **Step 2: Create SessionsTable component**

Create `frontend/components/SessionsTable.tsx`:

```tsx
"use client";

import Link from "next/link";
import type { SessionListItem, SessionStage, SessionStatus } from "@/lib/api";

const STAGE_LABELS: Record<SessionStage, string> = {
  configuring:    "Config",
  data_gathering: "Data",
  user_review:    "Review",
  featurizing:    "Features",
  analyzing:      "Analyze",
  explaining:     "Explain",
  follow_up:      "Follow-up",
};

const STATUS_DOT: Record<SessionStatus, string> = {
  running:  "bg-[#22c55e] animate-pulse",
  waiting:  "bg-[#9ca3af]",
  failed:   "bg-[#ef4444]",
  canceled: "bg-[#f59e0b]",
};

type Props = { sessions: SessionListItem[] };

export function SessionsTable({ sessions }: Props) {
  if (sessions.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-[#6b7280] text-sm">
        No sessions yet — create your first analysis above
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-[#21262d] text-[#6b7280] text-xs uppercase tracking-wider">
          <th className="text-left px-4 py-2">Profile</th>
          <th className="text-left px-4 py-2">Timeframe</th>
          <th className="text-left px-4 py-2">Stage</th>
          <th className="text-left px-4 py-2">Status</th>
          <th className="text-left px-4 py-2">Last Updated</th>
          <th className="px-4 py-2" />
        </tr>
      </thead>
      <tbody>
        {sessions.map((s) => (
          <tr
            key={s.session_id}
            className="border-b border-[#1f2937] hover:bg-[#111827] transition-colors"
          >
            <td className="px-4 py-3 text-[#f9fafb] font-medium capitalize">{s.market_profile}</td>
            <td className="px-4 py-3 text-[#9ca3af] font-mono text-xs">
              {s.timeframe_start} → {s.timeframe_end}
            </td>
            <td className="px-4 py-3">
              <span className="text-xs px-2 py-0.5 rounded-full bg-[#1f2937] text-[#60a5fa] border border-[#1d4ed8]">
                {STAGE_LABELS[s.stage] ?? s.stage}
              </span>
            </td>
            <td className="px-4 py-3">
              <div className="flex items-center gap-1.5">
                <div className={`w-2 h-2 rounded-full ${STATUS_DOT[s.status]}`} />
                <span className="text-[#9ca3af] capitalize">{s.status}</span>
              </div>
            </td>
            <td className="px-4 py-3 text-[#6b7280] text-xs">
              {new Date(s.updated_at).toLocaleString()}
            </td>
            <td className="px-4 py-3 text-right">
              <Link
                href={`/sessions/${s.session_id}/activity`}
                className="text-[#3b82f6] hover:text-[#60a5fa] text-xs transition-colors"
              >
                Open →
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 3: Create NewAnalysisModal component**

Create `frontend/components/NewAnalysisModal.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { MarketProfile } from "@/lib/api";

type Props = { onClose: () => void };

export function NewAnalysisModal({ onClose }: Props) {
  const router = useRouter();
  const [profiles, setProfiles] = useState<MarketProfile[]>([]);
  const [profileId, setProfileId] = useState("oil");
  const [start, setStart] = useState("2023-01-01");
  const [end, setEnd] = useState("2023-06-30");
  const [autoMode, setAutoMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getProfiles().then(setProfiles).catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { session_id } = await api.createSession({
        market_profile: profileId,
        timeframe_start: start,
        timeframe_end: end,
        auto: autoMode,
      });
      router.push(`/sessions/${session_id}/activity`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#111827] border border-[#21262d] rounded-lg p-6 w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-[#f9fafb]">New Analysis</h2>
          <button
            onClick={onClose}
            className="text-[#6b7280] hover:text-[#f9fafb] transition-colors text-lg"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-[#9ca3af] uppercase tracking-wider">Market Profile</span>
            <select
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              className="bg-[#1f2937] border border-[#374151] rounded px-3 py-2 text-sm text-[#f9fafb] focus:outline-none focus:border-[#3b82f6]"
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
              {profiles.length === 0 && <option value="oil">Oil Markets</option>}
            </select>
          </label>

          <div className="flex gap-3">
            <label className="flex flex-col gap-1 flex-1">
              <span className="text-xs text-[#9ca3af] uppercase tracking-wider">Start</span>
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="bg-[#1f2937] border border-[#374151] rounded px-3 py-2 text-sm text-[#f9fafb] focus:outline-none focus:border-[#3b82f6]"
              />
            </label>
            <label className="flex flex-col gap-1 flex-1">
              <span className="text-xs text-[#9ca3af] uppercase tracking-wider">End</span>
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="bg-[#1f2937] border border-[#374151] rounded px-3 py-2 text-sm text-[#f9fafb] focus:outline-none focus:border-[#3b82f6]"
              />
            </label>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autoMode}
              onChange={(e) => setAutoMode(e.target.checked)}
              className="w-4 h-4 accent-[#3b82f6]"
            />
            <span className="text-sm text-[#9ca3af]">Auto mode (skip user review gate)</span>
          </label>

          {error && <p className="text-xs text-[#ef4444]">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 py-2 rounded bg-[#1d4ed8] hover:bg-[#2563eb] disabled:opacity-50 text-sm font-semibold text-white transition-colors"
          >
            {loading ? "Starting…" : "Start Analysis"}
          </button>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Rewrite app/page.tsx as home page**

```tsx
"use client";

import { useEffect, useState } from "react";
import { SessionIndicators } from "@/components/SessionIndicators";
import { SessionsTable } from "@/components/SessionsTable";
import { NewAnalysisModal } from "@/components/NewAnalysisModal";
import { api } from "@/lib/api";
import type { SessionListItem } from "@/lib/api";

export default function Home() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [showModal, setShowModal] = useState(false);

  const refresh = () => {
    api.getSessions().then(setSessions).catch(() => {});
  };

  useEffect(() => { refresh(); }, []);

  return (
    <div className="flex flex-col min-h-screen bg-[#060b14] text-[#f9fafb]">
      {/* Top nav */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-[#21262d] bg-[#111827]">
        <span className="font-bold text-[#3b82f6] text-base tracking-tight">■ SIGNALYST</span>
        <button
          onClick={() => setShowModal(true)}
          className="text-sm px-3 py-1 rounded bg-[#1d4ed8] hover:bg-[#2563eb] text-white font-semibold transition-colors"
        >
          + NEW ANALYSIS
        </button>
      </header>

      {/* Live indicators strip */}
      <SessionIndicators />

      {/* Sessions table */}
      <main className="flex-1 px-4 py-4">
        <h1 className="text-xs text-[#6b7280] uppercase tracking-wider mb-3">Sessions</h1>
        <div className="rounded-lg border border-[#21262d] overflow-hidden">
          <SessionsTable sessions={sessions} />
        </div>
      </main>

      {showModal && (
        <NewAnalysisModal
          onClose={() => { setShowModal(false); refresh(); }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 5: Simplify TopBar.tsx to nav-only**

Replace `frontend/components/TopBar.tsx` content — the top nav is now embedded in each page directly. TopBar is no longer used as a shared component. Delete the file and its references rather than adapting it.

```bash
rm frontend/components/TopBar.tsx frontend/components/__tests__/TopBar.test.tsx 2>/dev/null || true
```

- [ ] **Step 6: Type-check and run all frontend tests**

```bash
cd frontend && npm run type-check && npm run test
```

Expected: all PASS (tab component tests may have stale imports — fix any import errors pointing to deleted files)

- [ ] **Step 7: Commit**

```bash
git add app/page.tsx components/SessionIndicators.tsx components/SessionsTable.tsx components/NewAnalysisModal.tsx
git commit -m "feat: home page with sessions table, new analysis modal, and live indicators strip"
```

---

## Task 15: Final integration check

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend && uv run pytest -v
```

Expected: all PASS. If `test_agent_tools.py` or `test_deferred_tools.py` fail due to importing deleted modules, delete those test files too (they test the old loop — PR 3 will add new agent tests).

- [ ] **Step 2: Run the full frontend test suite and type check**

```bash
cd frontend && npm run type-check && npm run test
```

Expected: all PASS

- [ ] **Step 3: Run lint on both**

```bash
cd backend && uv run ruff check .
cd frontend && npm run lint
```

Expected: no errors

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: pr1 integration — all tests pass, lint clean"
```

---

## Self-Review

Spec coverage check against `docs/backend-redesign.md` PR 1 and `docs/frontend-redesign.md` PR 1:

| Requirement | Task |
|---|---|
| Remove old `Run` model | Task 2 |
| Remove old `run_agent_loop` | Task 1 |
| Remove old `/api/analyze` and `/api/runs` routes | Task 1, 8 |
| New `Session`, `DataArtifact`, `FeatureArtifact`, `AnalysisResult`, `Connector`, `MarketProfile` models | Task 2 |
| Alembic migration | Task 3 |
| `POST`, `GET`, `DELETE /api/sessions` | Task 5 |
| `GET /api/profiles`, `GET /api/profiles/{id}` (seeded oil) | Task 6 |
| `GET /api/market/snapshot` | Task 7 |
| WebSocket stub at `/ws/sessions/{id}/stream` | Task 8 |
| Routing skeleton (`/`, `/sessions/[id]/activity`) | Task 13 |
| Shared layout shell | Task 13 |
| Home page (sessions table + new analysis modal + indicators strip) | Task 14 |
| `lib/api.ts` rewrite | Task 10 |
| `lib/store.ts` rewrite (`useSessionStore`) | Task 11 |
| `lib/websocket.ts` rewrite (`useSessionStream`) | Task 12 |
| Profile dropdown wired to `GET /api/profiles` | Task 14 (NewAnalysisModal) |
| Live indicators strip from `GET /api/market/snapshot` | Task 14 (SessionIndicators) |
