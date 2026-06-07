# ExplanationAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `ExplanationAgent` — a no-tools LLM agent that writes a natural-language
summary of a completed analysis into `AnalysisResult.summary` — and wire the `EXPLAINING` stage
back into the pipeline (it is currently skipped, with `ANALYZING` transitioning straight to
`FOLLOW_UP`).

**Architecture:** A new `make_explanation_agent()` factory builds a tool-less `BaseAgent`
(mirrors `make_data_agent`/`make_discovery_agent`). A new `run_explanation_service` background
service (mirrors `run_tabpfn_service`/`run_data_agent_service`) loads the session's
`AnalysisResult` + `DataArtifact`, runs the agent, writes the summary, and transitions
`EXPLAINING → FOLLOW_UP`. `tabpfn.py::_run` is changed at its two `FOLLOW_UP`-transition points
(cache-hit and fresh-analysis) to transition to `EXPLAINING` and chain into the new service —
this is the single edit point that guarantees `EXPLAINING` always runs after `ANALYZING`.

**Tech Stack:** FastAPI, SQLModel/asyncpg, OpenAI Python SDK (`openai.AsyncOpenAI`,
`gpt-5` via `settings.agent_model`), Redis pub/sub for activity streaming, pytest +
pytest-asyncio with an in-memory SQLite engine for service tests.

---

## Reference spec

`docs/superpowers/specs/2026-06-07-explanation-agent-design.md` — read this first if anything
below is unclear; it documents the brainstorming decisions (agent shape, chaining location,
how to handle the never-populated SHAP/backtest fields, the cancellation-guard requirement).

## Context the engineer needs

- **`BaseAgent`** (`backend/src/agents/base.py`): a tool-calling LLM loop. With zero tools
  registered, `run()` makes exactly one `chat.completions.create` call; since the response has
  no `tool_calls`, it streams the text as a `{"type": "thought", "agent": ..., "content": ...}`
  event via the `publisher` and returns the text immediately. That returned string is what we
  write to `AnalysisResult.summary`.
- **Background-service pattern** (`backend/src/services/discovery.py`,
  `backend/src/services/tabpfn.py`): build a Redis publisher closure
  (`channel = f"session:{session_id}:stream"`, `await r.publish(channel, json.dumps({**event,
  "created_at": ...}))`), snapshot every session field you'll need *before* any `await` (asyncpg
  expires ORM objects across the connection-pool boundary — re-fetch fresh after an `await`),
  use `transition_stage`/`set_status`/`append_activity_event` from `src/services/stage.py`,
  wrap the run in try/except that sets `status = FAILED`, `error = str(exc)` on crash.
- **`AnalysisResult.feature_importance` (SHAP) and `.backtest`** are real columns on the model
  but are **never populated anywhere in the codebase today** — they are always `None`. The
  agent's prompt must instruct it to omit those sections rather than inventing commentary.
- **`settings.agent_model`** (`gpt-5`) is the model `DataAgent`/`DiscoveryAgent` use for
  substantive generation; `settings.agent_model_fast` (`gpt-5-mini`) is what `ReviewInterpreter`
  uses for cheap classification. Use `settings.agent_model` here — summarization is substantive.
- **Stage/status convention**: while a stage's background work is actively running, `status`
  stays `RUNNING` (see `featurizer.py:122-123`, `transition_stage(s, ANALYZING);
  set_status(s, RUNNING)`); `status = WAITING` is reserved for stages that are waiting on user
  input (`FOLLOW_UP`, `USER_REVIEW`). So the `ANALYZING → EXPLAINING` transition sets
  `status = RUNNING` (not `WAITING`); only the final `EXPLAINING → FOLLOW_UP` transition (done
  inside the new service once the summary is written) sets `status = WAITING`.

---

## Task 1: ExplanationAgent definition

**Files:**
- Create: `backend/src/agents/explanation_agent.py`
- Test: `backend/tests/test_explanation_agent.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_explanation_agent.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.agents.explanation_agent import make_explanation_agent


def _text_resp(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    msg.model_dump.return_value = {"role": "assistant", "content": content}
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


def test_make_explanation_agent_has_no_tools() -> None:
    agent = make_explanation_agent()
    assert agent.name == "ExplanationAgent"
    assert agent._tools == {}


@pytest.mark.asyncio
async def test_explanation_agent_returns_text_and_streams_thought() -> None:
    agent = make_explanation_agent()
    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client(
            [_text_resp("The model calls a bull_supercycle regime with 80% confidence.")]
        )
        result = await agent.run(
            context=None, publisher=pub, initial_user_message="Summarize this analysis."
        )

    assert result == "The model calls a bull_supercycle regime with 80% confidence."
    assert any(e["type"] == "thought" and e["agent"] == "ExplanationAgent" for e in events)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_explanation_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.explanation_agent'`

- [ ] **Step 3: Write the implementation**

Create `backend/src/agents/explanation_agent.py`:

```python
from __future__ import annotations

from src.agents.base import BaseAgent

_SYSTEM_PROMPT = """\
You are ExplanationAgent. Write a clear, analyst-style natural-language summary of a \
completed market regime analysis for the user to read in the session's activity feed.

You will be given, in the user message:
- The regime classification result (regime label + confidence)
- The price-direction prediction (direction + confidence)
- Drift-detection findings (whether drift was detected, drifted features, PSI score)
- Feature-importance (SHAP) and backtest results — these may be present or may be null/missing
- The data sources fetched (data manifest) and the featurizer settings used for this run
- Recent conversation turns from the user-review step

Write 2-4 short paragraphs that:
1. State the regime call and the price-direction call, including their confidence levels.
2. Explain what the drift findings mean for how much to trust this result.
3. Briefly describe what data and featurizer settings the analysis was built on.
4. Reference relevant conversation context where it adds insight (e.g. if the user changed \
settings or asked about specific tickers/sources during review, connect that to the result).

IMPORTANT: Only discuss feature-importance or backtest results if they are explicitly present \
and non-null in the input. If they are missing, simply omit those sections — never invent or \
speculate about SHAP rankings or backtest performance you were not given.

Respond with the summary text only — no preamble, no JSON, no markdown headers.
"""


def make_explanation_agent() -> BaseAgent:
    return BaseAgent(name="ExplanationAgent", system_prompt=_SYSTEM_PROMPT)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_explanation_agent.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
cd backend
git add src/agents/explanation_agent.py tests/test_explanation_agent.py
git commit -m "feat: add ExplanationAgent (no-tools LLM agent for analysis summaries)"
```

---

## Task 2: `run_explanation_service`

**Files:**
- Create: `backend/src/services/explanation.py`
- Test: `backend/tests/test_explanation_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_explanation_service.py`:

```python
from __future__ import annotations

import json
import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

import src.db.models  # noqa: F401 — registers all tables
from src.db.models import AnalysisResult, DataArtifact, FeatureArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.services.explanation import run_explanation_service


def _text_resp(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    msg.model_dump.return_value = {"role": "assistant", "content": content}
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


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append(json.loads(message))

    async def aclose(self) -> None:
        pass


async def _make_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _seed_session(engine, *, stage: str, status: str) -> tuple[uuid.UUID, uuid.UUID]:
    session_id = uuid.uuid4()
    da_id = uuid.uuid4()
    fa_id = uuid.uuid4()
    ar_id = uuid.uuid4()

    async with AsyncSession(engine) as db:
        db.add(
            SessionModel(
                id=session_id,
                market_profile="oil",
                timeframe_start=date(2023, 1, 1),
                timeframe_end=date(2023, 6, 30),
                stage=stage,
                status=status,
                featurizer_config={
                    "windows": [5, 20],
                    "lags": [1],
                    "feature_families": ["momentum"],
                    "energy_specific": True,
                },
                conversation=[
                    {
                        "role": "user",
                        "content": "looks good, run it",
                        "created_at": "2023-01-01T00:00:00",
                    }
                ],
            )
        )
        db.add(
            DataArtifact(
                id=da_id,
                session_id=session_id,
                data_manifest={"tickers": ["CL=F"], "rows": 120},
                source_hash="src-hash",
            )
        )
        db.add(
            FeatureArtifact(
                id=fa_id,
                session_id=session_id,
                data_artifact_id=da_id,
                matrix_hash="matrix-hash",
            )
        )
        db.add(
            AnalysisResult(
                id=ar_id,
                session_id=session_id,
                feature_artifact_id=fa_id,
                regime={"regime": "bull_supercycle", "confidence": 0.8},
                direction={"direction": "up", "confidence": 0.7},
                drift={"drift_detected": False, "psi_score": 0.01, "drifted_features": []},
                feature_hash="feature-hash",
            )
        )
        await db.commit()

    return session_id, ar_id


@pytest.mark.asyncio
async def test_run_explanation_service_writes_summary_and_advances_to_follow_up() -> None:
    engine = await _make_engine()
    session_id, ar_id = await _seed_session(
        engine, stage=SessionStage.EXPLAINING.value, status=SessionStatus.RUNNING.value
    )
    fake_redis = _FakeRedis()

    with (
        patch("src.agents.base.openai.AsyncOpenAI") as cls,
        patch("src.services.explanation.aioredis.Redis.from_url", return_value=fake_redis),
    ):
        cls.return_value = _mock_client(
            [_text_resp("WTI is in a bull_supercycle regime with an upward bias; drift is low.")]
        )
        await run_explanation_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        ar = await db.get(AnalysisResult, ar_id)

    assert s is not None and ar is not None
    assert s.stage == SessionStage.FOLLOW_UP.value
    assert s.status == SessionStatus.WAITING.value
    assert ar.summary == "WTI is in a bull_supercycle regime with an upward bias; drift is low."
    assert any(
        e["type"] == "artifact_ready" and e.get("kind") == "analysis_summary"
        for e in s.activity_events
    )
    assert any(e["stage"] == SessionStage.FOLLOW_UP.value for e in s.stage_history)
    assert any(
        m["type"] == "stage_transition" and m["to"] == "follow_up" for m in fake_redis.published
    )


@pytest.mark.asyncio
async def test_run_explanation_service_noop_when_stage_is_not_explaining() -> None:
    engine = await _make_engine()
    session_id, ar_id = await _seed_session(
        engine, stage=SessionStage.ANALYZING.value, status=SessionStatus.RUNNING.value
    )
    fake_redis = _FakeRedis()

    with patch("src.services.explanation.aioredis.Redis.from_url", return_value=fake_redis):
        await run_explanation_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        ar = await db.get(AnalysisResult, ar_id)

    assert s is not None and ar is not None
    assert s.stage == SessionStage.ANALYZING.value
    assert ar.summary is None


@pytest.mark.asyncio
async def test_run_explanation_service_skips_write_when_canceled_midrun() -> None:
    engine = await _make_engine()
    session_id, ar_id = await _seed_session(
        engine, stage=SessionStage.EXPLAINING.value, status=SessionStatus.RUNNING.value
    )
    fake_redis = _FakeRedis()

    async def create(**kwargs):  # type: ignore[return]
        # Simulate a cancellation arriving while the LLM call is in flight.
        async with AsyncSession(engine) as cancel_db:
            fresh = await cancel_db.get(SessionModel, session_id)
            assert fresh is not None
            fresh.status = SessionStatus.CANCELED.value
            await cancel_db.commit()
        return _text_resp("a summary that should never be written")

    mock_client = MagicMock()
    mock_client.chat.completions.create = create

    with (
        patch("src.agents.base.openai.AsyncOpenAI") as cls,
        patch("src.services.explanation.aioredis.Redis.from_url", return_value=fake_redis),
    ):
        cls.return_value = mock_client
        await run_explanation_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        ar = await db.get(AnalysisResult, ar_id)

    assert s is not None and ar is not None
    assert ar.summary is None
    assert s.stage == SessionStage.EXPLAINING.value
    assert s.status == SessionStatus.CANCELED.value


@pytest.mark.asyncio
async def test_run_explanation_service_marks_failed_on_exception() -> None:
    engine = await _make_engine()
    session_id, ar_id = await _seed_session(
        engine, stage=SessionStage.EXPLAINING.value, status=SessionStatus.RUNNING.value
    )
    fake_redis = _FakeRedis()

    with (
        patch("src.agents.base.openai.AsyncOpenAI", side_effect=RuntimeError("llm down")),
        patch("src.services.explanation.aioredis.Redis.from_url", return_value=fake_redis),
    ):
        await run_explanation_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        ar = await db.get(AnalysisResult, ar_id)

    assert s is not None and ar is not None
    assert ar.summary is None
    assert s.status == SessionStatus.FAILED.value
    assert s.error == "llm down"
    assert any(
        e["type"] == "error" and e.get("stage") == "explaining" for e in s.activity_events
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_explanation_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.explanation'`

- [ ] **Step 3: Write the implementation**

Create `backend/src/services/explanation.py`:

```python
from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import select

from src.agents.explanation_agent import make_explanation_agent
from src.config import settings
from src.db.models import AnalysisResult, DataArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.services.stage import append_activity_event, set_status, transition_stage

log = structlog.get_logger()

Publisher = Callable[[dict[str, Any]], Awaitable[None]]


async def run_explanation_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    session_id_str = str(session_id)
    r = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    channel = f"session:{session_id_str}:stream"

    async def publisher(event: dict[str, Any]) -> None:
        enriched = {**event, "created_at": datetime.now(UTC).isoformat()}
        await r.publish(channel, json.dumps(enriched))

    try:
        async with AsyncSession(engine) as db:
            s = await db.get(SessionModel, session_id)
            if s is None:
                log.error("explanation.session_not_found", session_id=session_id_str)
                return
            if s.status == SessionStatus.CANCELED:
                log.info("explanation.canceled", session_id=session_id_str)
                return
            if s.stage != SessionStage.EXPLAINING:
                log.info("explanation.wrong_stage", session_id=session_id_str, stage=s.stage)
                return

            try:
                await _run(s, db, engine, publisher)
            except Exception as exc:
                log.error("explanation.failed", session_id=session_id_str, error=str(exc))
                set_status(s, SessionStatus.FAILED, error=str(exc))
                err_event: dict[str, Any] = {
                    "type": "error",
                    "stage": "explaining",
                    "message": str(exc),
                }
                append_activity_event(s, err_event)
                await db.commit()
                await publisher(err_event)
    finally:
        await r.aclose()  # type: ignore[attr-defined]


def _build_context_block(
    regime: dict[str, Any] | None,
    direction: dict[str, Any] | None,
    drift: dict[str, Any] | None,
    feature_importance: dict[str, Any] | None,
    backtest: dict[str, Any] | None,
    data_manifest: dict[str, Any],
    featurizer_config: dict[str, Any],
    conversation: list[dict[str, Any]],
) -> str:
    prior_turns = conversation[-6:]
    history = "\n".join(f"{t.get('role', 'user')}: {t.get('content', '')}" for t in prior_turns)
    return (
        f"Regime result: {json.dumps(regime)}\n"
        f"Direction result: {json.dumps(direction)}\n"
        f"Drift result: {json.dumps(drift)}\n"
        f"Feature importance (SHAP): {json.dumps(feature_importance)}\n"
        f"Backtest result: {json.dumps(backtest)}\n"
        f"Data manifest: {json.dumps(data_manifest)}\n"
        f"Featurizer config: {json.dumps(featurizer_config)}\n"
        f"Recent conversation:\n{history}\n"
        "Write the summary now."
    )


async def _run(
    s: SessionModel, db: AsyncSession, engine: AsyncEngine, publisher: Publisher
) -> None:
    session_id = s.id
    session_id_str = str(session_id)

    # Snapshot everything before the first await — asyncpg expires the object
    # when the connection returns to the pool between async calls.
    current_conversation = list(s.conversation or [])
    current_featurizer_config = dict(s.featurizer_config or {})

    analysis_result = (
        (
            await db.execute(
                select(AnalysisResult)
                .where(AnalysisResult.session_id == session_id)
                .order_by(AnalysisResult.created_at.desc())  # type: ignore[attr-defined]
            )
        )
        .scalars()
        .first()
    )
    if analysis_result is None:
        raise ValueError("no AnalysisResult found for session")

    analysis_result_id = analysis_result.id
    regime = analysis_result.regime
    direction = analysis_result.direction
    drift = analysis_result.drift
    feature_importance = analysis_result.feature_importance
    backtest = analysis_result.backtest

    latest_artifact = (
        (
            await db.execute(
                select(DataArtifact)
                .where(DataArtifact.session_id == session_id)
                .order_by(DataArtifact.created_at.desc())  # type: ignore[attr-defined]
            )
        )
        .scalars()
        .first()
    )
    data_manifest = latest_artifact.data_manifest if latest_artifact else {}

    context_block = _build_context_block(
        regime,
        direction,
        drift,
        feature_importance,
        backtest,
        data_manifest,
        current_featurizer_config,
        current_conversation,
    )

    agent = make_explanation_agent()
    summary = await agent.run(
        context=None,
        publisher=publisher,
        initial_user_message=context_block,
    )

    # `s` is expired after the agent's await — re-fetch everything fresh.
    async with AsyncSession(engine) as fresh_db:
        fresh_s = await fresh_db.get(SessionModel, session_id)
        if fresh_s is None or fresh_s.status == SessionStatus.CANCELED:
            log.info("explanation.canceled_midrun", session_id=session_id_str)
            return

        fresh_ar = await fresh_db.get(AnalysisResult, analysis_result_id)
        assert fresh_ar is not None
        fresh_ar.summary = summary

        summary_event: dict[str, Any] = {
            "type": "artifact_ready",
            "kind": "analysis_summary",
            "artifact_id": str(fresh_ar.id),
        }
        append_activity_event(fresh_s, summary_event)
        transition_stage(fresh_s, SessionStage.FOLLOW_UP)
        set_status(fresh_s, SessionStatus.WAITING)

        await fresh_db.commit()
        log.info("explanation.complete", session_id=session_id_str)

    await publisher(summary_event)
    await publisher({"type": "stage_transition", "from": "explaining", "to": "follow_up"})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_explanation_service.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd backend
git add src/services/explanation.py tests/test_explanation_service.py
git commit -m "feat: add run_explanation_service to write AnalysisResult summaries"
```

---

## Task 3: Wire EXPLAINING into the pipeline

**Files:**
- Modify: `backend/src/services/tabpfn.py:17-20` (imports), `:163-170` (cache-hit branch),
  `:253-263` (fresh-analysis completion branch)
- Test: `backend/tests/test_tabpfn_service.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tabpfn_service.py`:

```python
from __future__ import annotations

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

import src.db.models  # noqa: F401 — registers all tables
from src.db.models import AnalysisResult, DataArtifact, FeatureArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.services.hashing import canonical_json, stable_hash
from src.services.tabpfn import run_tabpfn_service


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append(json.loads(message))

    async def aclose(self) -> None:
        pass


async def _make_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_tabpfn_cache_hit_transitions_to_explaining_and_chains_explanation() -> None:
    """`_run`'s within-session cache-hit branch must stop at EXPLAINING (not FOLLOW_UP)
    and hand off to run_explanation_service — this is the fix for the stale
    'PR 2: skip EXPLAINING' shortcut."""
    engine = await _make_engine()
    session_id = uuid.uuid4()
    da_id = uuid.uuid4()
    fa_id = uuid.uuid4()
    ar_id = uuid.uuid4()

    # _run computes feature_hash as stable_hash(matrix_hash, canonical_json(regime_labels),
    # canonical_json(analysis_config)) with these exact constants — replicate it so our
    # pre-seeded AnalysisResult is recognized as a within-session cache hit.
    feature_hash = stable_hash(
        "matrix-hash",
        canonical_json(["bull_supercycle", "range_bound", "bust", "geopolitical_spike"]),
        canonical_json({}),
    )

    async with AsyncSession(engine) as db:
        db.add(
            SessionModel(
                id=session_id,
                market_profile="oil",
                timeframe_start=date(2023, 1, 1),
                timeframe_end=date(2023, 6, 30),
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
                matrix_hash="matrix-hash",
            )
        )
        db.add(
            AnalysisResult(
                id=ar_id,
                session_id=session_id,
                feature_artifact_id=fa_id,
                regime={"regime": "bull_supercycle"},
                feature_hash=feature_hash,
            )
        )
        await db.commit()

    fake_redis = _FakeRedis()
    with (
        patch("src.services.tabpfn.aioredis.Redis.from_url", return_value=fake_redis),
        patch(
            "src.services.tabpfn.run_explanation_service", new_callable=AsyncMock
        ) as mock_explain,
    ):
        await run_tabpfn_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)

    assert s is not None
    assert s.stage == SessionStage.EXPLAINING.value
    assert s.status == SessionStatus.RUNNING.value
    mock_explain.assert_awaited_once_with(session_id, engine)
    assert any(
        m["type"] == "stage_transition" and m["to"] == "explaining" for m in fake_redis.published
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_tabpfn_service.py -v`
Expected: FAIL — `s.stage == "follow_up"` (not `"explaining"`), and/or
`AttributeError`/`ImportError` on `src.services.tabpfn.run_explanation_service` (it doesn't
exist there yet, so `patch(...)` raises `AttributeError: <module> does not have the attribute
'run_explanation_service'`)

- [ ] **Step 3: Make the change**

In `backend/src/services/tabpfn.py`, add the import alongside the existing `src.services.stage`
import (around line 20):

```python
from src.services.explanation import run_explanation_service
from src.services.stage import append_activity_event, set_status, transition_stage
```

Replace the cache-hit branch (currently lines 163-170):

```python
    if existing is not None:
        log.info("tabpfn.cache_hit", session_id=str(session_id))
        append_activity_event(s, {"type": "cache_hit", "stage": "analyzing"})
        transition_stage(s, SessionStage.FOLLOW_UP)
        set_status(s, SessionStatus.WAITING)
        await db.commit()
        await publisher({"type": "stage_transition", "from": "analyzing", "to": "follow_up"})
        return
```

with:

```python
    if existing is not None:
        log.info("tabpfn.cache_hit", session_id=str(session_id))
        append_activity_event(s, {"type": "cache_hit", "stage": "analyzing"})
        transition_stage(s, SessionStage.EXPLAINING)
        set_status(s, SessionStatus.RUNNING)
        await db.commit()
        await publisher({"type": "stage_transition", "from": "analyzing", "to": "explaining"})
        await run_explanation_service(session_id, engine)
        return
```

Replace the fresh-analysis completion block (currently lines 252-264):

```python
    db.add(ar)
    analysis_event: dict[str, Any] = {
        "type": "artifact_ready",
        "kind": "analysis",
        "artifact_id": str(artifact_id),
        "regime": regime_result.get("regime") if regime_result else None,
    }
    append_activity_event(s, analysis_event)
    # PR 2: skip EXPLAINING (ExplanationAgent is PR 4), go straight to FOLLOW_UP
    transition_stage(s, SessionStage.FOLLOW_UP)
    set_status(s, SessionStatus.WAITING)
    await db.commit()
    await publisher(analysis_event)
```

with:

```python
    db.add(ar)
    analysis_event: dict[str, Any] = {
        "type": "artifact_ready",
        "kind": "analysis",
        "artifact_id": str(artifact_id),
        "regime": regime_result.get("regime") if regime_result else None,
    }
    append_activity_event(s, analysis_event)
    transition_stage(s, SessionStage.EXPLAINING)
    set_status(s, SessionStatus.RUNNING)
    await db.commit()
    await publisher(analysis_event)
    await run_explanation_service(session_id, engine)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_tabpfn_service.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full backend test suite to check for regressions**

Run: `cd backend && uv run python -m pytest`
Expected: PASS — all tests green, including `test_explanation_agent.py`,
`test_explanation_service.py`, `test_tabpfn_service.py`, and the existing `test_pipeline.py`,
`test_chat.py`, `test_discovery_service.py` suites (none of which directly exercise
`tabpfn._run`'s internals, so they should be unaffected by this change).

- [ ] **Step 6: Commit**

```bash
cd backend
git add src/services/tabpfn.py tests/test_tabpfn_service.py
git commit -m "fix: chain EXPLAINING into the pipeline instead of skipping to FOLLOW_UP"
```

---

## Final check

- [ ] **Run lint/type-check**

Run: `cd backend && uv run ruff check . && uv run mypy .`
Expected: no new errors introduced by `explanation_agent.py`, `explanation.py`, or the
`tabpfn.py` edits.

- [ ] **Run the full test suite one more time**

Run: `cd backend && uv run python -m pytest`
Expected: all green.

At this point the pipeline runs `ANALYZING → EXPLAINING → FOLLOW_UP` end-to-end (whether or not
the analysis hit the within-session cache), `AnalysisResult.summary` is populated by
`ExplanationAgent`, and the activity feed shows an `artifact_ready` (`kind: analysis_summary`)
event plus the `explaining`/`follow_up` stage transitions. `FollowUpAgent` and extending
`POST /chat` to `FOLLOW_UP` remain out of scope — that is a separate, future spec/plan.
