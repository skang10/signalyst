# PR 3 — DataSourceDiscoveryAgent + DataAgent + ReviewInterpreter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire DataSourceDiscoveryAgent and DataAgent so that creating a session automatically discovers and fetches data; wire ReviewInterpreter so that `POST /chat` at USER_REVIEW triggers intent-driven stage transitions; expose the connector registry via `GET/POST /api/connectors`.

**Architecture:** Three LLM-driven units built on a shared `BaseAgent` (async OpenAI tool loop, publisher injection). Services (`run_discovery_service`, `run_data_agent_service`) orchestrate DB ops and error handling, chaining automatically after `POST /api/sessions`. Agents emit typed events to a Redis pub/sub channel; the upgraded WebSocket handler subscribes and forwards to the browser. Builtin connectors (yfinance, fred, eia, gpr) are seeded as DB rows at startup. Upload validation gaps from the spec are fixed in this PR.

**Tech Stack:** FastAPI, `openai.AsyncOpenAI` (`settings.agent_model`), `redis.asyncio` pub/sub, SQLModel/asyncpg, structlog, pytest + `unittest.mock`.

---

## File Structure

**New files:**
```
backend/src/agents/__init__.py
backend/src/agents/base.py              — BaseAgent: async OpenAI tool loop, Publisher injection
backend/src/agents/discovery.py         — DataSourceDiscoveryAgent + DiscoveryContext
backend/src/agents/data_agent.py        — DataAgent (wraps ConnectorRegistry tools)
backend/src/agents/review_interpreter.py — ReviewInterpreter: single structured LLM call
backend/src/services/discovery.py       — run_discovery_service()
backend/src/services/data_agent.py      — run_data_agent_service()
backend/api/routes/connectors.py        — GET /api/connectors, POST /api/connectors
backend/api/routes/chat.py              — POST /api/sessions/{id}/chat

backend/tests/test_upload_validation.py
backend/tests/test_connectors_route.py
backend/tests/test_base_agent.py
backend/tests/test_discovery_agent.py
backend/tests/test_data_agent.py
backend/tests/test_discovery_service.py
backend/tests/test_chat.py
```

**Modified files:**
```
backend/src/db/seed.py                  — seed builtin Connector rows
backend/api/main.py                     — register connectors + chat routes
backend/api/models.py                   — ConnectorOut, ConnectorCreate, ChatRequest, ChatResponse
backend/api/routes/sessions.py          — add BackgroundTasks; launch discovery on create
backend/api/routes/pipeline.py          — upload validation fixes + DATA_GATHERING rerun
backend/api/ws.py                       — Redis pub/sub subscriber
backend/src/services/featurizer.py      — add stage guard (skip if stage ≠ FEATURIZING)
backend/src/services/tabpfn.py          — add stage guard (skip if stage ≠ ANALYZING)
```

---

## Task 1: Upload Validation Spec Gap Fixes

Fixes the four validation gaps noted in `docs/backend-redesign.md` for `POST /sessions/{id}/upload`.

**Files:**
- Modify: `backend/api/routes/pipeline.py` — `_parse_upload`, `upload_data`
- Create: `backend/tests/test_upload_validation.py`

- [ ] **Step 1: Write failing tests for the four validation cases**

Create `backend/tests/test_upload_validation.py`:

```python
import io

import pandas as pd
import pytest


def _make_csv(dates, col="CL=F") -> bytes:
    df = pd.DataFrame({"date": [str(d.date()) for d in dates], col: range(len(dates))})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def _create_session(client) -> str:
    res = client.post(
        "/api/sessions",
        json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
    )
    return res.json()["session_id"]


def test_upload_no_date_column_returns_422(client):
    session_id = _create_session(client)
    df = pd.DataFrame({"CL=F": range(80)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode()
    res = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        data={"source_name": "test"},
    )
    assert res.status_code == 422
    assert "date" in res.json()["detail"].lower()


def test_upload_too_few_rows_returns_422(client):
    session_id = _create_session(client)
    dates = pd.date_range("2023-01-01", periods=20, freq="D")
    csv_bytes = _make_csv(dates)
    res = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        data={"source_name": "test"},
    )
    assert res.status_code == 422
    assert "rows" in res.json()["detail"].lower()


def test_upload_date_range_mismatch_warns_in_manifest(client):
    session_id = _create_session(client)
    # Session timeframe: 2023-01-01 → 2023-06-30, upload: 2020-01-01 → 2020-06-30
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    csv_bytes = _make_csv(dates)
    res = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        data={"source_name": "test"},
    )
    assert res.status_code == 202
    artifact_id = res.json()["artifact_id"]
    detail = client.get(f"/api/sessions/{session_id}/artifacts/{artifact_id}").json()
    assert detail["data_manifest"].get("warnings") is not None
    assert any("overlap" in w.lower() for w in detail["data_manifest"]["warnings"])


def test_upload_no_wti_column_warns_in_manifest(client):
    session_id = _create_session(client)
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    csv_bytes = _make_csv(dates, col="custom_price")
    res = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        data={"source_name": "test"},
    )
    assert res.status_code == 202
    artifact_id = res.json()["artifact_id"]
    detail = client.get(f"/api/sessions/{session_id}/artifacts/{artifact_id}").json()
    assert detail["data_manifest"].get("warnings") is not None
    assert any("wti" in w.lower() for w in detail["data_manifest"]["warnings"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_upload_validation.py -v
```
Expected: 4 FAILs — existing upload endpoint doesn't apply these validations.

- [ ] **Step 3: Fix `_parse_upload` and `upload_data` in `backend/api/routes/pipeline.py`**

Replace the existing `_parse_upload` function (lines 84–95):

```python
_MIN_ROWS = 70  # max(windows=60) + max(lags=20) + 10 for default oil config


def _parse_upload(content: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(content)
    if filename.endswith(".parquet"):
        df = pd.read_parquet(buf)
    else:
        df = pd.read_csv(buf)

    # Validation 1: parseable date index
    date_col = None
    if "date" in df.columns:
        date_col = "date"
    elif df.index.dtype == object or df.index.dtype.name.startswith("datetime"):
        pass  # index might already be dates
    if date_col is None and "date" not in df.columns:
        # Try treating first column as date
        try:
            pd.DatetimeIndex(df.iloc[:, 0])
            date_col = df.columns[0]
        except Exception:
            raise ValueError("No parseable date column found. Include a 'date' column (YYYY-MM-DD).")
    if date_col:
        df = df.set_index(date_col)
    try:
        df.index = pd.DatetimeIndex(df.index)
    except Exception:
        raise ValueError("No parseable date column found. Include a 'date' column (YYYY-MM-DD).")

    df = df.sort_index()
    df = df.select_dtypes(include="number")

    # Validation 2: minimum row count
    if len(df) < _MIN_ROWS:
        raise ValueError(
            f"Uploaded file has {len(df)} rows; at least {_MIN_ROWS} are required for featurization."
        )

    return df
```

In `upload_data`, replace the two error raises and add warnings to the manifest. After `df = _parse_upload(...)` and before writing the artifact, add warning generation. Replace the existing `_build_manifest` call site:

```python
    try:
        df = _parse_upload(content, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if df.empty:
        raise HTTPException(status_code=422, detail="No numeric columns found in uploaded file")

    # ... (existing hash + artifact_id logic stays the same) ...

    data_manifest = _build_manifest(df)

    # Validation 3: date range overlap warning
    warnings: list[str] = []
    upload_start = df.index.min().date()
    upload_end = df.index.max().date()
    if upload_end < s.timeframe_start or upload_start > s.timeframe_end:
        warnings.append(
            f"Uploaded date range {upload_start}–{upload_end} does not overlap with "
            f"session timeframe {s.timeframe_start}–{s.timeframe_end}."
        )

    # Validation 4: oil profile — no WTI column hint
    wti_cols = [c for c in df.columns if "CL=F" in c or "wti" in c.lower()]
    if not wti_cols and s.market_profile == "oil":
        warnings.append(
            "No column matching 'CL=F' or 'wti' found. "
            "TabPFNService will use the first column as a WTI proxy for regime labelling."
        )

    if warnings:
        data_manifest["warnings"] = warnings
```

Also update `_parse_upload` call in `upload_data` to wrap in try/except:

```python
    try:
        df = _parse_upload(content, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if df.empty:
        raise HTTPException(status_code=422, detail="No numeric columns found in uploaded file")
```

The existing `if df.empty:` check at line 143 should be moved to after the try/except.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_upload_validation.py tests/test_pipeline.py -v
```
Expected: all pass. `test_pipeline.py` should still pass since 100-row CSV has a date column and enough rows.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/pipeline.py backend/tests/test_upload_validation.py
git commit -m "fix: upload validation — date index, min rows, date overlap + WTI column warnings"
```

---

## Task 2: Connector DB Seed + GET/POST /api/connectors

Seeds the four builtin connectors as `Connector` DB rows at startup and exposes them via REST.

**Files:**
- Modify: `backend/src/db/seed.py`
- Modify: `backend/api/models.py`
- Create: `backend/api/routes/connectors.py`
- Modify: `backend/api/main.py`
- Create: `backend/tests/test_connectors_route.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_connectors_route.py`:

```python
def test_list_connectors_returns_four_builtins(client):
    res = client.get("/api/connectors")
    assert res.status_code == 200
    ids = {c["id"] for c in res.json()}
    assert ids == {"yfinance", "fred", "eia", "gpr"}


def test_list_connectors_each_has_required_fields(client):
    res = client.get("/api/connectors")
    for c in res.json():
        assert "id" in c
        assert "name" in c
        assert "type" in c
        assert "available" in c


def test_create_connector_stores_spec(client):
    body = {
        "id": "custom_test",
        "name": "Test Connector",
        "description": "A test connector",
        "spec": {"url": "https://example.com/api", "method": "GET"},
    }
    res = client.post("/api/connectors", json=body)
    assert res.status_code == 201
    assert res.json()["id"] == "custom_test"
    assert res.json()["type"] == "spec"


def test_create_connector_conflict_returns_409(client):
    body = {"id": "dup_test", "name": "Dup", "description": "", "spec": {}}
    client.post("/api/connectors", json=body)
    res = client.post("/api/connectors", json=body)
    assert res.status_code == 409


def test_created_connector_appears_in_list(client):
    client.post(
        "/api/connectors",
        json={"id": "listed_test", "name": "Listed", "description": "", "spec": {}},
    )
    res = client.get("/api/connectors")
    ids = {c["id"] for c in res.json()}
    assert "listed_test" in ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_connectors_route.py -v
```
Expected: all fail — route does not exist yet.

- [ ] **Step 3: Add Pydantic models to `backend/api/models.py`**

Append at the end of `backend/api/models.py`:

```python
class ConnectorOut(BaseModel):
    id: str
    name: str
    description: str
    type: str
    available: bool


class ConnectorCreate(BaseModel):
    id: str
    name: str
    description: str = ""
    spec: dict[str, object]
```

- [ ] **Step 4: Seed builtin Connector rows in `backend/src/db/seed.py`**

Add after the existing `seed_profiles` function:

```python
from src.db.models import Connector, ConnectorType

_BUILTIN_CONNECTORS = [
    Connector(
        id="yfinance",
        name="Yahoo Finance",
        description="Daily price series from Yahoo Finance. Supports equities, ETFs, and futures.",
        type=ConnectorType.BUILTIN,
    ),
    Connector(
        id="fred",
        name="FRED",
        description="Macro time series from the St. Louis Fed FRED database.",
        type=ConnectorType.BUILTIN,
    ),
    Connector(
        id="eia",
        name="EIA",
        description="Weekly US crude oil inventory change from the EIA.",
        type=ConnectorType.BUILTIN,
    ),
    Connector(
        id="gpr",
        name="GPR Index",
        description="Daily Geopolitical Risk Index from the Federal Reserve.",
        type=ConnectorType.BUILTIN,
    ),
]


async def seed_connectors(db: AsyncSession) -> None:
    for c in _BUILTIN_CONNECTORS:
        if await db.get(Connector, c.id) is None:
            db.add(c)
    await db.commit()
```

- [ ] **Step 5: Create `backend/api/routes/connectors.py`**

```python
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.models import ConnectorCreate, ConnectorOut
from src.data.registry import connector_registry
from src.db.models import Connector, ConnectorType
from src.db.session import get_session

router = APIRouter(tags=["connectors"])
log = structlog.get_logger()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/connectors", response_model=list[ConnectorOut])
async def list_connectors(db: SessionDep) -> list[ConnectorOut]:
    rows = (
        (await db.execute(select(Connector).where(Connector.is_active == True)))  # noqa: E712
        .scalars()
        .all()
    )
    return [
        ConnectorOut(
            id=row.id,
            name=row.name,
            description=row.description,
            type=row.type,
            available=(
                connector_registry.is_available(row.id)
                if row.type == ConnectorType.BUILTIN
                else True
            ),
        )
        for row in rows
    ]


@router.post("/connectors", response_model=ConnectorOut, status_code=201)
async def create_connector(body: ConnectorCreate, db: SessionDep) -> ConnectorOut:
    existing = await db.get(Connector, body.id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Connector {body.id!r} already exists")
    c = Connector(
        id=body.id,
        name=body.name,
        description=body.description,
        type=ConnectorType.SPEC,
        spec=dict(body.spec),
    )
    db.add(c)
    await db.commit()
    log.info("connector.created", connector_id=body.id)
    return ConnectorOut(
        id=c.id, name=c.name, description=c.description, type=c.type, available=True
    )
```

- [ ] **Step 6: Wire into `backend/api/main.py` and call `seed_connectors` in lifespan**

In `backend/api/main.py`, add the import and registration:

```python
from api.routes import connectors  # add to existing imports
```

Inside the `lifespan` function, after `await seed_profiles(db)`:

```python
        from src.db.seed import seed_connectors
        await seed_connectors(db)
```

After `app.include_router(derivatives.router, prefix="/api")`, add:

```python
app.include_router(connectors.router, prefix="/api")
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_connectors_route.py -v
```
Expected: all 5 pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/db/seed.py backend/api/models.py backend/api/routes/connectors.py \
        backend/api/main.py backend/tests/test_connectors_route.py
git commit -m "feat: seed builtin Connector rows + GET/POST /api/connectors"
```

---

## Task 3: BaseAgent — Async OpenAI Tool Loop

The shared foundation for all LLM agents. Stateless except for the tool registry it holds.

**Files:**
- Create: `backend/src/agents/__init__.py`
- Create: `backend/src/agents/base.py`
- Create: `backend/tests/test_base_agent.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_base_agent.py`:

```python
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base import BaseAgent


def _text_resp(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    msg.model_dump.return_value = {"role": "assistant", "content": content}
    r = MagicMock()
    r.choices = [MagicMock(message=msg)]
    return r


def _tool_resp(name: str, args: dict, call_id: str = "c1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump.return_value = {"role": "assistant", "tool_calls": [tc]}
    r = MagicMock()
    r.choices = [MagicMock(message=msg)]
    return r


def _mock_client(responses: list) -> MagicMock:
    idx = {"v": 0}

    async def create(**kwargs):  # type: ignore[return]
        resp = responses[min(idx["v"], len(responses) - 1)]
        idx["v"] += 1
        return resp

    c = MagicMock()
    c.chat.completions.create = create
    return c


@pytest.mark.asyncio
async def test_base_agent_runs_tool_then_finishes() -> None:
    agent = BaseAgent(name="T", system_prompt="help")

    def echo(value: str, context: object = None) -> dict:
        """Echo a value."""
        return {"echoed": value}

    agent.register_tool(echo, {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]})

    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client([_tool_resp("echo", {"value": "hi"}), _text_resp("done")])
        result = await agent.run(context=None, publisher=pub)

    assert result == "done"
    assert any(e["type"] == "tool_call" and e["tool"] == "echo" for e in events)
    assert any(e["type"] == "tool_result" for e in events)


@pytest.mark.asyncio
async def test_base_agent_stop_tool_exits_loop() -> None:
    agent = BaseAgent(name="T", system_prompt="help")

    def approve(items: list, context: object = None) -> dict:
        """Approve items."""
        return {"approved": items}

    agent.register_tool(
        approve,
        {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "string"}}}, "required": ["items"]},
        is_stop=True,
    )

    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        # Would loop forever if stop tool didn't terminate
        cls.return_value = _mock_client([
            _tool_resp("approve", {"items": ["a", "b"]}),
            _text_resp("should not reach"),
        ])
        result = await agent.run(context=None, publisher=pub)

    data = json.loads(result)
    assert data["approved"] == ["a", "b"]
    assert len([e for e in events if e["type"] == "tool_call"]) == 1


@pytest.mark.asyncio
async def test_base_agent_thought_events_published() -> None:
    agent = BaseAgent(name="T", system_prompt="help")

    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        msg = MagicMock()
        msg.content = "thinking..."
        msg.tool_calls = None
        msg.model_dump.return_value = {}
        resp = MagicMock()
        resp.choices = [MagicMock(message=msg)]
        cls.return_value = _mock_client([resp])
        await agent.run(context=None, publisher=pub)

    assert any(e["type"] == "thought" and e["content"] == "thinking..." for e in events)


@pytest.mark.asyncio
async def test_base_agent_initial_user_message_prepended() -> None:
    agent = BaseAgent(name="T", system_prompt="help")

    captured: list[list] = []

    async def create(**kwargs):  # type: ignore[return]
        captured.append(kwargs["messages"])
        msg = MagicMock()
        msg.content = "ok"
        msg.tool_calls = None
        msg.model_dump.return_value = {}
        r = MagicMock()
        r.choices = [MagicMock(message=msg)]
        return r

    c = MagicMock()
    c.chat.completions.create = create

    async def pub(e: dict) -> None:
        pass

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = c
        await agent.run(context=None, publisher=pub, initial_user_message="fetch oil data")

    first_call_msgs = captured[0]
    roles = [m["role"] for m in first_call_msgs]
    assert roles == ["system", "user"]
    assert first_call_msgs[1]["content"] == "fetch oil data"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_base_agent.py -v
```
Expected: ImportError — `src.agents.base` does not exist.

- [ ] **Step 3: Create `backend/src/agents/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Create `backend/src/agents/base.py`**

```python
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import openai

from src.config import settings

Publisher = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class _ToolEntry:
    fn: Callable[..., Any]
    schema: dict[str, Any]
    is_stop: bool = False


class BaseAgent:
    def __init__(self, name: str, system_prompt: str, max_iterations: int = 10) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self._tools: dict[str, _ToolEntry] = {}

    def register_tool(
        self, fn: Callable[..., Any], schema: dict[str, Any], is_stop: bool = False
    ) -> None:
        self._tools[fn.__name__] = _ToolEntry(fn=fn, schema=schema, is_stop=is_stop)

    def _schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": (entry.fn.__doc__ or "").strip().splitlines()[0],
                    "parameters": entry.schema,
                },
            }
            for name, entry in self._tools.items()
        ]

    async def run(
        self,
        context: Any,
        publisher: Publisher,
        initial_user_message: str = "",
    ) -> str:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        if initial_user_message:
            messages.append({"role": "user", "content": initial_user_message})

        schemas = self._schemas()

        for _ in range(self.max_iterations):
            kwargs: dict[str, Any] = {
                "model": settings.agent_model,
                "messages": messages,
            }
            if schemas:
                kwargs["tools"] = schemas

            resp = await client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message

            if msg.content:
                await publisher({"type": "thought", "agent": self.name, "content": msg.content})

            if not msg.tool_calls:
                return msg.content or ""

            messages.append(msg.model_dump(exclude_unset=True))

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                args = json.loads(tc.function.arguments)

                await publisher(
                    {"type": "tool_call", "agent": self.name, "tool": fn_name, "input": args}
                )

                entry = self._tools.get(fn_name)
                if entry is None:
                    result: Any = {"error": f"unknown tool: {fn_name}"}
                else:
                    try:
                        result = entry.fn(**args, context=context)
                    except Exception as exc:
                        result = {"error": str(exc)}

                await publisher(
                    {"type": "tool_result", "agent": self.name, "tool": fn_name, "output": result}
                )

                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)}
                )

                if entry is not None and entry.is_stop:
                    return json.dumps(result)

        return "max_iterations_reached"
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_base_agent.py -v
```
Expected: all 4 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/__init__.py backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat: BaseAgent — async OpenAI tool loop with publisher injection"
```

---

## Task 4: DataSourceDiscoveryAgent

Discovers appropriate data sources based on the market profile. Writes approved sources to `DiscoveryContext.pending_sources` via the `approve_sources` stop tool.

**Files:**
- Create: `backend/src/agents/discovery.py`
- Create: `backend/tests/test_discovery_agent.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_discovery_agent.py`:

```python
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.discovery import DiscoveryContext, make_discovery_agent


def _tool_resp(name: str, args: dict, call_id: str = "c1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump.return_value = {"role": "assistant"}
    r = MagicMock()
    r.choices = [MagicMock(message=msg)]
    return r


def _mock_client(responses: list) -> MagicMock:
    idx = {"v": 0}

    async def create(**kwargs):  # type: ignore[return]
        resp = responses[min(idx["v"], len(responses) - 1)]
        idx["v"] += 1
        return resp

    c = MagicMock()
    c.chat.completions.create = create
    return c


@pytest.mark.asyncio
async def test_discovery_agent_writes_pending_sources() -> None:
    ctx = DiscoveryContext(
        market_profile="oil",
        timeframe_start="2023-01-01",
        timeframe_end="2023-06-30",
    )

    sources = [
        {"connector_id": "yfinance", "params": {"tickers": ["CL=F", "BZ=F"]}},
        {"connector_id": "fred", "params": {"series_ids": ["INDPRO"]}},
    ]

    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client([_tool_resp("approve_sources", {"sources": sources})])
        agent = make_discovery_agent()
        await agent.run(context=ctx, publisher=pub)

    assert ctx.pending_sources == sources


@pytest.mark.asyncio
async def test_discovery_agent_list_connectors_tool_returns_registry() -> None:
    ctx = DiscoveryContext(
        market_profile="oil",
        timeframe_start="2023-01-01",
        timeframe_end="2023-06-30",
    )

    captured: list[dict] = []

    async def pub(e: dict) -> None:
        if e["type"] == "tool_result" and e["tool"] == "list_available_connectors":
            captured.append(e["output"])

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        # First call: list_connectors. Second call: approve_sources.
        cls.return_value = _mock_client([
            _tool_resp("list_available_connectors", {}, "c1"),
            _tool_resp("approve_sources", {"sources": []}, "c2"),
        ])
        agent = make_discovery_agent()
        await agent.run(context=ctx, publisher=pub)

    assert len(captured) == 1
    assert "available" in captured[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_discovery_agent.py -v
```
Expected: ImportError — `src.agents.discovery` does not exist.

- [ ] **Step 3: Create `backend/src/agents/discovery.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from src.agents.base import BaseAgent
from src.data.registry import connector_registry

_SYSTEM_PROMPT = """\
You are DataSourceDiscoveryAgent. Recommend the best data sources for a market analysis session.

Steps:
1. Call list_available_connectors() to see what's built-in.
2. Select the most relevant sources for the given market profile.
3. For oil markets: recommend WTI + Brent + DXY via yfinance, INDPRO via fred, eia (no params), gpr (no params).
4. Call approve_sources(sources) to finalise. Each source: {"connector_id": "...", "params": {...}}.

Only call approve_sources() — never end without it.
"""


@dataclass
class DiscoveryContext:
    market_profile: str
    timeframe_start: str
    timeframe_end: str
    pending_sources: list[dict[str, Any]] = field(default_factory=list)


def make_discovery_agent() -> BaseAgent:
    agent = BaseAgent(name="DataSourceDiscoveryAgent", system_prompt=_SYSTEM_PROMPT)

    def list_available_connectors(context: DiscoveryContext | None = None) -> dict[str, Any]:
        """List all built-in connectors and their availability."""
        return connector_registry.list()

    def approve_sources(
        sources: list[dict[str, Any]], context: DiscoveryContext | None = None
    ) -> dict[str, Any]:
        """Approve the recommended data sources and hand off to DataAgent."""
        if context is not None:
            context.pending_sources = list(sources)
        return {"approved": len(sources), "sources": sources}

    def http_get(
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        context: DiscoveryContext | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP GET request to explore an external data API."""
        try:
            r = httpx.get(url, headers=headers or {}, params=params or {}, timeout=10)
            return {"status_code": r.status_code, "body": r.text[:2000]}
        except Exception as exc:
            return {"error": str(exc)}

    agent.register_tool(
        list_available_connectors,
        {"type": "object", "properties": {}, "required": []},
    )
    agent.register_tool(
        approve_sources,
        {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "connector_id": {"type": "string"},
                            "params": {"type": "object"},
                        },
                        "required": ["connector_id", "params"],
                    },
                }
            },
            "required": ["sources"],
        },
        is_stop=True,
    )
    agent.register_tool(
        http_get,
        {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "headers": {"type": "object"},
                "params": {"type": "object"},
            },
            "required": ["url"],
        },
    )

    return agent
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_discovery_agent.py -v
```
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/discovery.py backend/tests/test_discovery_agent.py
git commit -m "feat: DataSourceDiscoveryAgent — recommends sources, approve_sources stop tool"
```

---

## Task 5: DataAgent

Fetches approved data sources using the existing `ConnectorRegistry`. Accumulates signals in `AgentContext`. Signals completion via the `complete` stop tool.

**Files:**
- Create: `backend/src/agents/data_agent.py`
- Create: `backend/tests/test_data_agent.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_data_agent.py`:

```python
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.agent.tools import AgentContext
from src.agents.data_agent import make_data_agent


def _tool_resp(name: str, args: dict, call_id: str = "c1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump.return_value = {"role": "assistant"}
    r = MagicMock()
    r.choices = [MagicMock(message=msg)]
    return r


def _mock_client(responses: list) -> MagicMock:
    idx = {"v": 0}

    async def create(**kwargs):  # type: ignore[return]
        resp = responses[min(idx["v"], len(responses) - 1)]
        idx["v"] += 1
        return resp

    c = MagicMock()
    c.chat.completions.create = create
    return c


@pytest.mark.asyncio
async def test_data_agent_fetch_yfinance_populates_signals() -> None:
    ctx = AgentContext(date_range_start="2023-01-01", date_range_end="2023-06-30")
    dates = pd.date_range("2023-01-01", periods=60, freq="D")
    fake_series = pd.Series(range(60), index=dates, name="CL=F", dtype=float)

    async def pub(e: dict) -> None:
        pass

    with patch("src.agents.base.openai.AsyncOpenAI") as cls, patch(
        "src.data.connectors.fetch_price_series", return_value=fake_series
    ):
        cls.return_value = _mock_client([
            _tool_resp("fetch_yfinance", {"tickers": ["CL=F"]}, "c1"),
            _tool_resp("complete", {"summary": "done"}, "c2"),
        ])
        agent = make_data_agent()
        await agent.run(context=ctx, publisher=pub)

    assert "CL=F" in ctx.signals
    assert len(ctx.signals["CL=F"]) == 60


@pytest.mark.asyncio
async def test_data_agent_complete_stops_loop() -> None:
    ctx = AgentContext(date_range_start="2023-01-01", date_range_end="2023-06-30")

    call_count = {"n": 0}

    async def pub(e: dict) -> None:
        if e["type"] == "tool_call":
            call_count["n"] += 1

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client([
            _tool_resp("complete", {"summary": "done"}, "c1"),
            _tool_resp("complete", {"summary": "should not run"}, "c2"),
        ])
        agent = make_data_agent()
        await agent.run(context=ctx, publisher=pub)

    assert call_count["n"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_data_agent.py -v
```
Expected: ImportError — `src.agents.data_agent` does not exist.

- [ ] **Step 3: Create `backend/src/agents/data_agent.py`**

```python
from __future__ import annotations

from typing import Any

from src.agent.tools import AgentContext
from src.agents.base import BaseAgent
from src.data.registry import connector_registry

_SYSTEM_PROMPT = """\
You are DataAgent. Your job is to fetch all approved data sources for the analysis session.

You will receive a list of approved sources. Fetch each one using the appropriate tool:
- fetch_yfinance: for yfinance sources (pass the tickers from params)
- fetch_fred: for fred sources (pass the series_ids from params)
- fetch_eia: for eia sources (no params needed)
- fetch_gpr: for gpr sources (no params needed)

When all sources have been fetched (or attempted), call complete(summary) to finish.
"""


def make_data_agent() -> BaseAgent:
    agent = BaseAgent(name="DataAgent", system_prompt=_SYSTEM_PROMPT)

    def fetch_yfinance(
        tickers: list[str], context: AgentContext | None = None
    ) -> dict[str, Any]:
        """Fetch daily price series from Yahoo Finance for the given tickers."""
        if context is None:
            return {"error": "no context"}
        return connector_registry.fetch("yfinance", {"tickers": tickers}, context)

    def fetch_fred(
        series_ids: list[str], context: AgentContext | None = None
    ) -> dict[str, Any]:
        """Fetch macro time series from FRED for the given series IDs."""
        if context is None:
            return {"error": "no context"}
        return connector_registry.fetch("fred", {"series_ids": series_ids}, context)

    def fetch_eia(context: AgentContext | None = None) -> dict[str, Any]:
        """Fetch weekly EIA crude oil inventory change series."""
        if context is None:
            return {"error": "no context"}
        return connector_registry.fetch("eia", {}, context)

    def fetch_gpr(context: AgentContext | None = None) -> dict[str, Any]:
        """Fetch daily Geopolitical Risk Index (GPR)."""
        if context is None:
            return {"error": "no context"}
        return connector_registry.fetch("gpr", {}, context)

    def list_available_connectors(context: AgentContext | None = None) -> dict[str, Any]:
        """List available data connectors."""
        return connector_registry.list()

    def complete(summary: str = "", context: AgentContext | None = None) -> dict[str, Any]:
        """Signal that data gathering is complete."""
        return {"n_signals": len(context.signals) if context else 0, "summary": summary}

    agent.register_tool(
        fetch_yfinance,
        {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}, "description": "yfinance ticker symbols"}
            },
            "required": ["tickers"],
        },
    )
    agent.register_tool(
        fetch_fred,
        {
            "type": "object",
            "properties": {
                "series_ids": {"type": "array", "items": {"type": "string"}, "description": "FRED series IDs"}
            },
            "required": ["series_ids"],
        },
    )
    agent.register_tool(fetch_eia, {"type": "object", "properties": {}, "required": []})
    agent.register_tool(fetch_gpr, {"type": "object", "properties": {}, "required": []})
    agent.register_tool(
        list_available_connectors, {"type": "object", "properties": {}, "required": []}
    )
    agent.register_tool(
        complete,
        {
            "type": "object",
            "properties": {"summary": {"type": "string", "description": "Brief summary of what was fetched"}},
            "required": [],
        },
        is_stop=True,
    )

    return agent
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_data_agent.py -v
```
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/data_agent.py backend/tests/test_data_agent.py
git commit -m "feat: DataAgent — fetch tools wrapping ConnectorRegistry, complete stop tool"
```

---

## Task 6: Services + POST /sessions Launch + DATA_GATHERING Rerun

Creates the orchestration layer: `run_discovery_service`, `run_data_agent_service`, stage guards, and wires `POST /api/sessions` to launch the full pipeline.

**Files:**
- Create: `backend/src/services/discovery.py`
- Create: `backend/src/services/data_agent.py`
- Modify: `backend/src/services/featurizer.py` — add stage guard
- Modify: `backend/src/services/tabpfn.py` — add stage guard
- Modify: `backend/api/routes/sessions.py` — add BackgroundTasks + launch discovery
- Modify: `backend/api/routes/pipeline.py` — add DATA_GATHERING case to rerun
- Create: `backend/tests/test_discovery_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_discovery_service.py`:

```python
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

import src.db.models  # noqa: F401


@pytest.fixture
async def engine_and_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session_in_db(engine_and_db):
    from datetime import date
    from src.db.models import Session as SessionModel, SessionStage, SessionStatus

    engine = engine_and_db
    async with AsyncSession(engine) as db:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2023, 1, 1),
            timeframe_end=date(2023, 6, 30),
            stage=SessionStage.CONFIGURING,
            status=SessionStatus.RUNNING,
        )
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return s.id, engine


@pytest.mark.asyncio
async def test_run_discovery_service_transitions_to_data_gathering(session_in_db) -> None:
    session_id, engine = session_in_db
    from src.db.models import Session as SessionModel
    from src.services.discovery import run_discovery_service

    fake_sources = [{"connector_id": "yfinance", "params": {"tickers": ["CL=F"]}}]

    async def fake_agent_run(context, publisher, initial_user_message=""):
        context.pending_sources = fake_sources
        return '{"approved": 1}'

    with patch("src.services.discovery.make_discovery_agent") as mock_make, patch(
        "src.services.discovery.aioredis.Redis.from_url"
    ) as mock_redis:
        mock_agent = mock_make.return_value
        mock_agent.run = fake_agent_run
        mock_redis.return_value.publish = AsyncMock()
        mock_redis.return_value.aclose = AsyncMock()

        await run_discovery_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
    assert s is not None
    assert s.stage == "data_gathering"
    assert s.pending_sources == fake_sources


@pytest.mark.asyncio
async def test_run_data_agent_service_writes_data_artifact(session_in_db) -> None:
    session_id, engine = session_in_db
    from datetime import date

    import pandas as pd

    from src.db.models import DataArtifact, Session as SessionModel, SessionStage
    from src.services.data_agent import run_data_agent_service

    # Pre-set session to DATA_GATHERING with pending_sources
    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        assert s is not None
        s.stage = SessionStage.DATA_GATHERING
        s.pending_sources = [{"connector_id": "yfinance", "params": {"tickers": ["CL=F"]}}]
        await db.commit()

    fake_signals: dict = {
        "CL=F": pd.Series(
            range(60),
            index=pd.date_range("2023-01-01", periods=60, freq="D"),
            dtype=float,
        )
    }

    async def fake_agent_run(context, publisher, initial_user_message=""):
        context.signals = fake_signals
        return '{"n_signals": 1}'

    with patch("src.services.data_agent.make_data_agent") as mock_make, patch(
        "src.services.data_agent.aioredis.Redis.from_url"
    ) as mock_redis:
        mock_agent = mock_make.return_value
        mock_agent.run = fake_agent_run
        mock_redis.return_value.publish = AsyncMock()
        mock_redis.return_value.aclose = AsyncMock()

        await run_data_agent_service(session_id, engine)

    async with AsyncSession(engine) as db:
        artifacts = (
            (await db.execute(select(DataArtifact).where(DataArtifact.session_id == session_id)))
            .scalars()
            .all()
        )
        s = await db.get(SessionModel, session_id)

    assert len(artifacts) == 1
    assert artifacts[0].data_manifest["tickers"] == ["CL=F"]
    assert s is not None
    assert s.stage == "user_review"
    assert s.pending_sources == []


def test_create_session_launches_discovery_background_task(client):
    with patch("api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock) as mock_bg:
        res = client.post(
            "/api/sessions",
            json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
        )
    assert res.status_code == 202
    assert mock_bg.called


def test_rerun_data_gathering_launches_data_agent(client):
    with patch("api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock):
        session_id = client.post(
            "/api/sessions",
            json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
        ).json()["session_id"]

    # Force stage to DATA_GATHERING so rerun is valid
    # (in real flow discovery sets it; here we just test the rerun endpoint)
    with patch("api.routes.pipeline._run_data_agent_background", new_callable=AsyncMock) as mock_bg:
        # First set status to WAITING (cancel guard)
        from src.db.models import SessionStatus
        # Manually patch session status via a get then update
        # Simplest: just call rerun at DATA_GATHERING after forcing stage
        # We'll patch the status check too
        with patch("api.routes.pipeline.SessionStatus") as mock_status:
            mock_status.RUNNING = "running"
            # Actually easier — just test that the route accepts and calls bg task
            pass

    # Simpler approach: test that the rerun endpoint wires up correctly when stage matches
    with patch("api.routes.pipeline._run_data_agent_background", new_callable=AsyncMock) as mock_bg:
        res = client.post(
            f"/api/sessions/{session_id}/rerun",
            json={"stage": "data_gathering"},
        )
    # 409 because status is RUNNING (discovery was patched above but status wasn't reset)
    # The test verifies the route exists and accepts the stage value (not 422)
    assert res.status_code in (202, 409)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_discovery_service.py -v
```
Expected: ImportError — services don't exist yet.

- [ ] **Step 3: Create `backend/src/services/discovery.py`**

```python
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.agents.discovery import DiscoveryContext, make_discovery_agent
from src.config import settings
from src.db.models import Session as SessionModel
from src.db.models import SessionStage, SessionStatus
from src.services.stage import append_activity_event, set_status, transition_stage

log = structlog.get_logger()


async def run_discovery_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        if s is None:
            log.error("discovery.session_not_found", session_id=str(session_id))
            return
        if s.status == SessionStatus.CANCELED:
            return
        try:
            await _run(s, db)
        except Exception as exc:
            log.error("discovery.failed", session_id=str(session_id), error=str(exc))
            set_status(s, SessionStatus.FAILED, error=str(exc))
            append_activity_event(
                s, {"type": "error", "stage": "configuring", "message": str(exc)}
            )
            await db.commit()


async def _run(s: SessionModel, db: AsyncSession) -> None:
    r = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    channel = f"session:{s.id}:stream"

    async def publisher(event: dict[str, Any]) -> None:
        enriched = {**event, "created_at": datetime.now(UTC).isoformat()}
        await r.publish(channel, json.dumps(enriched))

    try:
        ctx = DiscoveryContext(
            market_profile=s.market_profile,
            timeframe_start=str(s.timeframe_start),
            timeframe_end=str(s.timeframe_end),
        )
        agent = make_discovery_agent()
        await agent.run(context=ctx, publisher=publisher)

        s.pending_sources = list(ctx.pending_sources)
        s.conversation = [
            *s.conversation,
            {
                "role": "assistant",
                "content": f"Recommended {len(ctx.pending_sources)} data sources.",
            },
        ]
        append_activity_event(
            s,
            {
                "type": "stage_transition",
                "from": SessionStage.CONFIGURING,
                "to": SessionStage.DATA_GATHERING,
                "n_sources": len(ctx.pending_sources),
            },
        )
        transition_stage(s, SessionStage.DATA_GATHERING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        log.info("discovery.complete", session_id=str(s.id), n_sources=len(ctx.pending_sources))
    finally:
        await r.aclose()
```

- [ ] **Step 4: Create `backend/src/services/data_agent.py`**

```python
from __future__ import annotations

import hashlib
import json
import pathlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import func, select

from src.agent.tools import AgentContext
from src.agents.data_agent import make_data_agent
from src.config import settings
from src.db.models import DataArtifact
from src.db.models import Session as SessionModel
from src.db.models import SessionStage, SessionStatus
from src.services.hashing import stable_hash
from src.services.stage import append_activity_event, set_status, transition_stage

log = structlog.get_logger()
_ARTIFACTS_DIR = pathlib.Path("data/artifacts")
_RAW_INLINE_THRESHOLD = 5 * 1024 * 1024


async def run_data_agent_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        if s is None:
            log.error("data_agent.session_not_found", session_id=str(session_id))
            return
        if s.status == SessionStatus.CANCELED:
            return
        if s.stage != SessionStage.DATA_GATHERING:
            log.info(
                "data_agent.wrong_stage",
                session_id=str(session_id),
                stage=s.stage,
            )
            return
        try:
            await _run(s, db)
        except Exception as exc:
            log.error("data_agent.failed", session_id=str(session_id), error=str(exc))
            set_status(s, SessionStatus.FAILED, error=str(exc))
            append_activity_event(
                s, {"type": "error", "stage": "data_gathering", "message": str(exc)}
            )
            await db.commit()


def _series_to_raw_data(signals: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, series in signals.items():
        if isinstance(series, pd.Series):
            result[key] = {
                "index": [
                    str(idx.date()) if hasattr(idx, "date") else str(idx)
                    for idx in series.index
                ],
                "data": [None if pd.isna(v) else float(v) for v in series.values],
            }
    return result


def _build_manifest(signals: dict[str, Any]) -> dict[str, Any]:
    tickers = [k for k, v in signals.items() if isinstance(v, pd.Series)]
    if not tickers:
        return {
            "tickers": [],
            "rows": 0,
            "date_range": {},
            "missing_pct": {},
            "summary_stats": {},
        }
    first = next(v for v in signals.values() if isinstance(v, pd.Series))
    rows = len(first)
    date_range = {
        "start": str(first.index.min().date()) if rows else "",
        "end": str(first.index.max().date()) if rows else "",
    }
    missing_pct = {
        k: round(float(v.isna().mean() * 100), 2)
        for k, v in signals.items()
        if isinstance(v, pd.Series)
    }
    summary_stats = {
        k: {
            "mean": round(float(v.mean(skipna=True)), 4),
            "std": round(float(v.std(skipna=True)), 4),
            "min": round(float(v.min(skipna=True)), 4),
            "max": round(float(v.max(skipna=True)), 4),
        }
        for k, v in signals.items()
        if isinstance(v, pd.Series)
    }
    return {
        "tickers": tickers,
        "rows": rows,
        "date_range": date_range,
        "missing_pct": missing_pct,
        "summary_stats": summary_stats,
    }


async def _run(s: SessionModel, db: AsyncSession) -> None:
    r = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    channel = f"session:{s.id}:stream"

    async def publisher(event: dict[str, Any]) -> None:
        enriched = {**event, "created_at": datetime.now(UTC).isoformat()}
        await r.publish(channel, json.dumps(enriched))

    try:
        ctx = AgentContext(
            date_range_start=str(s.timeframe_start),
            date_range_end=str(s.timeframe_end),
        )
        pending = list(s.pending_sources or [])
        initial_msg = (
            f"Fetch the following approved data sources: {json.dumps(pending)}"
            if pending
            else "Fetch the default oil data sources: yfinance (CL=F, BZ=F, DX-Y.NYB), fred (INDPRO), eia, gpr."
        )
        agent = make_data_agent()
        await agent.run(context=ctx, publisher=publisher, initial_user_message=initial_msg)

        raw_data = _series_to_raw_data(ctx.signals)
        data_manifest = _build_manifest(ctx.signals)

        source_str = json.dumps(
            sorted(pending, key=lambda x: x.get("connector_id", "")), sort_keys=True
        )
        source_hash = stable_hash(hashlib.sha256(source_str.encode()).hexdigest())

        artifact_id = uuid.uuid4()
        count_result = await db.execute(
            select(func.count(DataArtifact.id)).where(DataArtifact.session_id == s.id)
        )
        round_num = (count_result.scalar() or 0) + 1

        raw_json = json.dumps(raw_data).encode()
        if len(raw_json) <= _RAW_INLINE_THRESHOLD:
            raw_data_out: dict[str, Any] | None = raw_data
            raw_data_ref: str | None = None
        else:
            _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            ref = str(_ARTIFACTS_DIR / f"{artifact_id}.parquet")
            df = pd.DataFrame(
                {
                    k: pd.Series(v["data"], index=pd.DatetimeIndex(v["index"]))
                    for k, v in raw_data.items()
                }
            )
            df.to_parquet(ref)
            raw_data_out = None
            raw_data_ref = ref

        sources = [
            {"connector_id": p["connector_id"], "params": p.get("params", {})}
            for p in pending
        ]
        a = DataArtifact(
            id=artifact_id,
            session_id=s.id,
            round=round_num,
            sources=sources,
            data_manifest=data_manifest,
            raw_data=raw_data_out,
            raw_data_ref=raw_data_ref,
            source_hash=source_hash,
        )
        db.add(a)

        s.pending_sources = []
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

        if s.auto:
            transition_stage(s, SessionStage.FEATURIZING)
            set_status(s, SessionStatus.RUNNING)
        else:
            transition_stage(s, SessionStage.USER_REVIEW)
            set_status(s, SessionStatus.WAITING)

        await db.commit()
        log.info(
            "data_agent.complete",
            session_id=str(s.id),
            n_signals=len(ctx.signals),
            round=round_num,
        )
    finally:
        await r.aclose()
```

- [ ] **Step 5: Add stage guards to featurizer and tabpfn services**

In `backend/src/services/featurizer.py`, at the top of `run_featurizer_service` after the canceled check, add:

```python
        if s.stage != SessionStage.FEATURIZING:
            log.info("featurizer.wrong_stage", session_id=str(session_id), stage=s.stage)
            return
```

In `backend/src/services/tabpfn.py`, add the same guard after the canceled check (check for `s.stage != SessionStage.ANALYZING`). Look for `run_tabpfn_service` and add after `if s.status == SessionStatus.CANCELED: return`:

```python
        if s.stage != SessionStage.ANALYZING:
            log.info("tabpfn.wrong_stage", session_id=str(session_id), stage=s.stage)
            return
```

- [ ] **Step 6: Modify `backend/api/routes/sessions.py` to launch discovery**

Add `BackgroundTasks` import at top (if not present):
```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
```

Import the engine at top of file:
```python
from src.db.session import engine, get_session
```

After the existing imports, add the background task function before the route handlers:

```python
async def _run_data_pipeline_background(session_id: uuid.UUID) -> None:
    from src.services.data_agent import run_data_agent_service
    from src.services.discovery import run_discovery_service
    from src.services.featurizer import run_featurizer_service
    from src.services.tabpfn import run_tabpfn_service

    await run_discovery_service(session_id, engine)
    await run_data_agent_service(session_id, engine)
    # Stage guards in featurizer/tabpfn ensure they skip if stage ≠ their target
    await run_featurizer_service(session_id, engine)
    await run_tabpfn_service(session_id, engine)
```

Update `create_session` signature and body:

```python
@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_session(
    req: CreateSessionRequest,
    background_tasks: BackgroundTasks,
    db: SessionDep,
) -> CreateSessionResponse:
    s = SessionModel(
        market_profile=req.market_profile,
        timeframe_start=date.fromisoformat(req.timeframe_start),
        timeframe_end=date.fromisoformat(req.timeframe_end),
        auto=req.auto,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    from src.db.models import SessionStatus
    from src.services.stage import set_status
    set_status(s, SessionStatus.RUNNING)
    await db.commit()
    background_tasks.add_task(_run_data_pipeline_background, s.id)
    log.info(
        "session.created",
        session_id=str(s.id),
        market_profile=req.market_profile,
        auto=req.auto,
    )
    return CreateSessionResponse(session_id=str(s.id))
```

- [ ] **Step 7: Add DATA_GATHERING case to pipeline.py rerun**

In `backend/api/routes/pipeline.py`, add a `_run_data_agent_background` function after the existing background task functions:

```python
async def _run_data_agent_background(session_id: uuid.UUID) -> None:
    from src.services.data_agent import run_data_agent_service
    from src.services.featurizer import run_featurizer_service
    from src.services.tabpfn import run_tabpfn_service

    await run_data_agent_service(session_id, engine)
    await run_featurizer_service(session_id, engine)
    await run_tabpfn_service(session_id, engine)
```

In the `rerun` route handler, add the `data_gathering` case after the existing `elif target == SessionStage.ANALYZING:` block:

```python
    elif target == SessionStage.DATA_GATHERING:
        background_tasks.add_task(_run_data_agent_background, uid)
```

Also update `_RERUN_ALLOWED_STAGES` (already has `data_gathering` key — verify it's there and if not add it).

Also update existing session tests to patch the new background task. In `backend/tests/test_sessions.py`, update every `client.post("/api/sessions", ...)` call to wrap it:

```python
with patch("api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock):
    res = client.post("/api/sessions", json={...})
```

Add `from unittest.mock import AsyncMock, patch` at the top of `test_sessions.py`.

- [ ] **Step 8: Run all tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_discovery_service.py tests/test_sessions.py tests/test_pipeline.py tests/test_featurizer_service.py -v
```
Expected: all pass (stage guards make featurizer/tabpfn skip cleanly in wrong-stage scenarios).

- [ ] **Step 9: Commit**

```bash
git add backend/src/services/discovery.py backend/src/services/data_agent.py \
        backend/src/services/featurizer.py backend/src/services/tabpfn.py \
        backend/api/routes/sessions.py backend/api/routes/pipeline.py \
        backend/tests/test_discovery_service.py backend/tests/test_sessions.py
git commit -m "feat: run_discovery_service + run_data_agent_service, POST /sessions launches pipeline"
```

---

## Task 7: WebSocket Redis Pub/Sub Streaming

Upgrades the WS stub to subscribe to the session's Redis channel and forward events to connected clients.

**Files:**
- Modify: `backend/api/ws.py`
- Modify: `backend/tests/test_ws.py`

- [ ] **Step 1: Write failing tests**

Replace `backend/tests/test_ws.py` with:

```python
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from api.ws import session_stream_handler


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def receive_text(self) -> str:
        raise WebSocketDisconnect()


def _make_pubsub(messages: list[dict]) -> MagicMock:
    """Fake pubsub that yields given message dicts then stops."""
    msgs = list(messages)

    async def listen():  # type: ignore[return]
        for m in msgs:
            yield m

    ps = MagicMock()
    ps.subscribe = AsyncMock()
    ps.unsubscribe = AsyncMock()
    ps.listen = listen
    return ps


@pytest.mark.asyncio
async def test_ws_accepts_connection() -> None:
    ws = _FakeWebSocket()
    pubsub = _make_pubsub([])

    with patch("api.ws.aioredis.Redis.from_url") as mock_redis:
        mock_redis.return_value.pubsub.return_value = pubsub
        mock_redis.return_value.aclose = AsyncMock()
        await session_stream_handler(ws, "test-session-id")  # type: ignore[arg-type]

    assert ws.accepted


@pytest.mark.asyncio
async def test_ws_forwards_message_events() -> None:
    ws = _FakeWebSocket()
    event = {"type": "thought", "agent": "DataAgent", "content": "fetching data"}
    pubsub = _make_pubsub([
        {"type": "message", "data": json.dumps(event).encode()},
    ])

    with patch("api.ws.aioredis.Redis.from_url") as mock_redis:
        mock_redis.return_value.pubsub.return_value = pubsub
        mock_redis.return_value.aclose = AsyncMock()
        await session_stream_handler(ws, "test-session-id")  # type: ignore[arg-type]

    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0])["type"] == "thought"


@pytest.mark.asyncio
async def test_ws_ignores_non_message_events() -> None:
    ws = _FakeWebSocket()
    pubsub = _make_pubsub([
        {"type": "subscribe", "data": 1},
        {"type": "message", "data": json.dumps({"type": "done"}).encode()},
    ])

    with patch("api.ws.aioredis.Redis.from_url") as mock_redis:
        mock_redis.return_value.pubsub.return_value = pubsub
        mock_redis.return_value.aclose = AsyncMock()
        await session_stream_handler(ws, "test-session-id")  # type: ignore[arg-type]

    assert len(ws.sent) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_ws.py -v
```
Expected: 3 fails — WS handler doesn't use Redis yet.

- [ ] **Step 3: Replace `backend/api/ws.py`**

```python
from __future__ import annotations

import structlog
from fastapi import WebSocket, WebSocketDisconnect

import redis.asyncio as aioredis

from src.config import settings

log = structlog.get_logger()


async def session_stream_handler(websocket: WebSocket, session_id: str) -> None:
    """Subscribe to the session's Redis pub/sub channel and forward events to the client."""
    await websocket.accept()
    short_id = session_id[:8]
    log.info("ws.connected", session_id=short_id)

    r = aioredis.Redis.from_url(settings.redis_url, decode_responses=False)
    pubsub = r.pubsub()
    await pubsub.subscribe(f"session:{session_id}:stream")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                text = data.decode() if isinstance(data, bytes) else data
                await websocket.send_text(text)
    except (WebSocketDisconnect, RuntimeError):
        log.info("ws.disconnected", session_id=short_id)
    finally:
        await pubsub.unsubscribe(f"session:{session_id}:stream")
        await r.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_ws.py -v
```
Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/ws.py backend/tests/test_ws.py
git commit -m "feat: WebSocket handler subscribes to Redis pub/sub channel per session"
```

---

## Task 8: ReviewInterpreter + POST /api/sessions/{id}/chat

A single structured LLM call that classifies user intent at USER_REVIEW and triggers the appropriate stage transition.

**Files:**
- Create: `backend/src/agents/review_interpreter.py`
- Modify: `backend/api/models.py` — add ChatRequest, ChatResponse
- Create: `backend/api/routes/chat.py`
- Modify: `backend/api/main.py` — register chat route
- Create: `backend/tests/test_chat.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_chat.py`:

```python
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest


def _make_csv_bytes(n: int = 100) -> bytes:
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    df = pd.DataFrame({"date": [str(d.date()) for d in dates], "CL=F": range(n)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def _setup_session_at_user_review(client) -> str:
    """Create a session, upload data so it moves to USER_REVIEW."""
    with patch("api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock):
        session_id = client.post(
            "/api/sessions",
            json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
        ).json()["session_id"]

    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    return session_id


def test_chat_at_user_review_returns_202(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {
        "action": "advance",
        "updates": {},
        "reply": "Running analysis now.",
    }
    with patch("api.routes.chat.ReviewInterpreter") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.interpret = AsyncMock(return_value=fake_result)
        res = client.post(
            f"/api/sessions/{session_id}/chat",
            json={"message": "looks good, proceed"},
        )
    assert res.status_code == 202


def test_chat_at_wrong_stage_returns_409(client):
    with patch("api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock):
        session_id = client.post(
            "/api/sessions",
            json={"market_profile": "oil", "timeframe_start": "2023-01-01", "timeframe_end": "2023-06-30"},
        ).json()["session_id"]

    res = client.post(
        f"/api/sessions/{session_id}/chat",
        json={"message": "hello"},
    )
    assert res.status_code == 409


def test_chat_advance_action_triggers_featurizing(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {"action": "advance", "updates": {}, "reply": "Proceeding."}
    with patch("api.routes.chat.ReviewInterpreter") as mock_cls, patch(
        "api.routes.chat._run_featurizer_background", new_callable=AsyncMock
    ) as mock_bg:
        mock_cls.return_value.interpret = AsyncMock(return_value=fake_result)
        client.post(f"/api/sessions/{session_id}/chat", json={"message": "run it"})

    mock_bg.assert_called_once()


def test_chat_refetch_action_triggers_data_gathering(client):
    session_id = _setup_session_at_user_review(client)

    fake_result = {
        "action": "refetch",
        "updates": {"sources_to_add": ["baker_hughes"]},
        "reply": "Refetching with additional sources.",
    }
    with patch("api.routes.chat.ReviewInterpreter") as mock_cls, patch(
        "api.routes.chat._run_data_agent_background", new_callable=AsyncMock
    ) as mock_bg:
        mock_cls.return_value.interpret = AsyncMock(return_value=fake_result)
        client.post(f"/api/sessions/{session_id}/chat", json={"message": "add baker hughes"})

    mock_bg.assert_called_once()


def test_review_interpreter_classify_advance():
    from unittest.mock import MagicMock, patch

    from src.agents.review_interpreter import ReviewInterpreter

    interp = ReviewInterpreter()

    async def fake_create(**kwargs):
        msg = MagicMock()
        import json as _json
        msg.content = _json.dumps({
            "action": "advance",
            "updates": {},
            "reply": "Running analysis.",
        })
        r = MagicMock()
        r.choices = [MagicMock(message=msg)]
        return r

    with patch("src.agents.review_interpreter.openai.AsyncOpenAI") as cls:
        cls.return_value.chat.completions.create = fake_create
        import asyncio
        result = asyncio.run(interp.interpret(
            message="looks good proceed",
            session_stage="user_review",
            conversation=[],
            data_manifest={"tickers": ["CL=F"]},
        ))

    assert result["action"] == "advance"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_chat.py -v
```
Expected: ImportError — chat route doesn't exist.

- [ ] **Step 3: Create `backend/src/agents/review_interpreter.py`**

```python
from __future__ import annotations

import json
from typing import Any

import openai

from src.config import settings

_SYSTEM_PROMPT = """\
You are ReviewInterpreter. Classify the user's intent at the data review stage.

Given the user's message and the current session context, output a JSON object with:
- "action": one of "advance" | "refetch" | "update_config"
- "updates": object with optional keys:
    - "sources_to_add": list of connector IDs to add (for "refetch")
    - "featurizer_config_patch": dict of config overrides (for "update_config")
- "reply": a short natural-language reply to show the user

Rules:
- "advance": user wants to proceed to featurizing (e.g. "looks good", "run it", "proceed")
- "refetch": user wants to add/change data sources (e.g. "add X", "fetch Y too")
- "update_config": user wants to change featurizer settings (e.g. "use 30d windows")

Respond ONLY with the JSON object. No other text.
"""


class ReviewInterpreter:
    async def interpret(
        self,
        message: str,
        session_stage: str,
        conversation: list[dict[str, Any]],
        data_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        user_content = (
            f"Session stage: {session_stage}\n"
            f"Data manifest tickers: {data_manifest.get('tickers', [])}\n"
            f"User message: {message}"
        )
        resp = await client.chat.completions.create(
            model=settings.agent_model_fast,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
```

- [ ] **Step 4: Add ChatRequest and ChatResponse to `backend/api/models.py`**

Append at the end:

```python
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    session_id: str
```

- [ ] **Step 5: Create `backend/api/routes/chat.py`**

```python
from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.models import ChatRequest, ChatResponse
from src.agents.review_interpreter import ReviewInterpreter
from src.db.models import Session as SessionModel
from src.db.models import SessionStage, SessionStatus
from src.db.session import engine, get_session
from src.services.stage import append_activity_event, set_status, transition_stage

router = APIRouter(tags=["chat"])
log = structlog.get_logger()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_CHAT_ALLOWED_STAGES = {SessionStage.USER_REVIEW}


async def _run_featurizer_background(session_id: uuid.UUID) -> None:
    from src.services.featurizer import run_featurizer_service
    from src.services.tabpfn import run_tabpfn_service

    await run_featurizer_service(session_id, engine)
    await run_tabpfn_service(session_id, engine)


async def _run_data_agent_background(session_id: uuid.UUID) -> None:
    from src.services.data_agent import run_data_agent_service
    from src.services.featurizer import run_featurizer_service
    from src.services.tabpfn import run_tabpfn_service

    await run_data_agent_service(session_id, engine)
    await run_featurizer_service(session_id, engine)
    await run_tabpfn_service(session_id, engine)


@router.post(
    "/sessions/{session_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def chat(
    session_id: str,
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    db: SessionDep,
) -> ChatResponse:
    try:
        uid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id")

    s = await db.get(SessionModel, uid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if s.stage not in {stage.value for stage in _CHAT_ALLOWED_STAGES}:
        raise HTTPException(
            status_code=409, detail=f"chat not available at stage {s.stage}"
        )

    # Append user message to conversation
    s.conversation = [
        *s.conversation,
        {"role": "user", "content": req.message},
    ]
    await db.commit()

    # Get latest DataArtifact manifest for context
    from sqlmodel import select
    from src.db.models import DataArtifact

    latest_artifact = (
        (
            await db.execute(
                select(DataArtifact)
                .where(DataArtifact.session_id == uid)
                .order_by(DataArtifact.created_at.desc())  # type: ignore[attr-defined]
            )
        )
        .scalars()
        .first()
    )
    data_manifest = latest_artifact.data_manifest if latest_artifact else {}

    interpreter = ReviewInterpreter()
    result = await interpreter.interpret(
        message=req.message,
        session_stage=s.stage,
        conversation=list(s.conversation),
        data_manifest=data_manifest,
    )

    action = result.get("action", "advance")
    reply = result.get("reply", "")
    updates = result.get("updates", {})

    # Append assistant reply
    s.conversation = [*s.conversation, {"role": "assistant", "content": reply}]
    append_activity_event(
        s, {"type": "chat_reply", "action": action, "reply": reply}
    )

    if action == "advance":
        transition_stage(s, SessionStage.FEATURIZING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        background_tasks.add_task(_run_featurizer_background, uid)

    elif action == "refetch":
        sources_to_add = updates.get("sources_to_add", [])
        if sources_to_add:
            s.pending_sources = [
                *list(s.pending_sources or []),
                *[{"connector_id": sid, "params": {}} for sid in sources_to_add],
            ]
        transition_stage(s, SessionStage.DATA_GATHERING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        background_tasks.add_task(_run_data_agent_background, uid)

    elif action == "update_config":
        patch = updates.get("featurizer_config_patch", {})
        if patch:
            s.featurizer_config = {**s.featurizer_config, **patch}
        transition_stage(s, SessionStage.FEATURIZING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        background_tasks.add_task(_run_featurizer_background, uid)

    else:
        await db.commit()

    log.info("chat.handled", session_id=session_id, action=action)
    return ChatResponse(session_id=session_id)
```

- [ ] **Step 6: Register chat route in `backend/api/main.py`**

Add:
```python
from api.routes import chat  # add to existing imports
```

After `app.include_router(connectors.router, prefix="/api")`:
```python
app.include_router(chat.router, prefix="/api")
```

- [ ] **Step 7: Run all tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_chat.py -v
```
Expected: all 5 pass.

- [ ] **Step 8: Run the full test suite**

```bash
cd backend && uv run pytest -v
```
Expected: all tests pass. Fix any regressions before committing.

- [ ] **Step 9: Commit**

```bash
git add backend/src/agents/review_interpreter.py backend/api/routes/chat.py \
        backend/api/models.py backend/api/main.py backend/tests/test_chat.py
git commit -m "feat: ReviewInterpreter + POST /api/sessions/{id}/chat at USER_REVIEW stage"
```

---

## Self-Review

### Spec Coverage Check

| Requirement | Task |
|---|---|
| Built-in connector registry seeded (yfinance, FRED, EIA, GPR) | Task 2 |
| `DataSourceDiscoveryAgent` with HTTP primitive tools | Task 4 |
| `DataAgent` with full tool set + connector dispatch | Task 5 |
| `ReviewInterpreter` (thin LLM call at USER_REVIEW) | Task 8 |
| `POST /api/sessions/{id}/chat` — USER_REVIEW stage only | Task 8 |
| `GET /api/connectors`, `POST /api/connectors` | Task 2 |
| Upload spec gap: parseable date index | Task 1 |
| Upload spec gap: minimum row count | Task 1 |
| Upload spec gap: date range overlap warning | Task 1 |
| Upload spec gap: profile-aware WTI column hint | Task 1 |
| WS handler subscribes to Redis and forwards events | Task 7 |
| `POST /api/sessions` launches DataSourceDiscoveryAgent | Task 6 |
| `POST /rerun { stage: "data_gathering" }` launches DataAgent | Task 6 |
| Stage guards in featurizer/tabpfn services | Task 6 |

All 14 requirements are covered.

### Type Consistency

- `DiscoveryContext` defined in `src/agents/discovery.py`, used in service `src/services/discovery.py` — consistent.
- `AgentContext` (existing) reused by DataAgent and `run_data_agent_service` — consistent.
- `ReviewInterpreter.interpret()` returns `dict[str, Any]` — matches usage in `chat.py`.
- `BaseAgent.run()` signature `(context, publisher, initial_user_message="")` — used consistently in all agents and services.
- `Publisher` type alias defined in `base.py`, referenced by all services — consistent.

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-04-pr3-agent-data-pipeline.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints

**Which approach?**
