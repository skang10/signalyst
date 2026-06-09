# FollowUpAgent (PR 4b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `FollowUpAgent` — the LLM agent that handles chat at the `FOLLOW_UP` stage, answering questions directly from session context or triggering a featurizer/data-gathering re-run — and wire `POST /sessions/{id}/chat` to dispatch to it.

**Architecture:** A two-tool `BaseAgent` (`rerun_featurizer`, `rerun_data_gathering`, both `is_stop=True`, each returning `{action: "rerun", stage, ..., reply}` in one LLM round-trip) backed by `run_followup_service` — a background service mirroring `run_explanation_service`'s shape (publisher closure, stage/status guards, snapshot-before-await, cancellation guard, `FAILED`-on-exception) that either writes a plain-text reply or performs a stage regression and directly `await`-chains the target services (`run_featurizer_service → run_tabpfn_service`, or the 3-stage data-gathering chain), exactly like `tabpfn._run` chains to `run_explanation_service`. `chat.py` gains a `FOLLOW_UP` branch that appends the message and enqueues the service as a background task.

**Tech Stack:** FastAPI, SQLModel + asyncpg/aiosqlite, Redis pub/sub (`redis.asyncio`), OpenAI-compatible chat-completions client (`openai.AsyncOpenAI`), pytest + pytest-asyncio + `unittest.mock`.

**Reference spec:** `docs/superpowers/specs/2026-06-08-followup-agent-design.md`

---

## Task 1: FollowUpAgent — agent definition and tools

**Files:**
- Create: `backend/src/agents/followup_agent.py`
- Test: `backend/tests/test_followup_agent.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_followup_agent.py`:

```python
from __future__ import annotations

from src.agents.followup_agent import make_followup_agent


def test_make_followup_agent_registers_rerun_tools_as_stop_tools() -> None:
    agent = make_followup_agent()
    assert agent.name == "FollowUpAgent"
    assert set(agent._tools) == {"rerun_featurizer", "rerun_data_gathering"}
    assert agent._tools["rerun_featurizer"].is_stop is True
    assert agent._tools["rerun_data_gathering"].is_stop is True


def test_followup_agent_system_prompt_instructs_never_invent_and_reply() -> None:
    agent = make_followup_agent()
    prompt = agent.system_prompt.lower()
    assert "never invent" in prompt
    assert "reply" in prompt


def test_rerun_featurizer_tool_returns_rerun_intent_with_reply() -> None:
    agent = make_followup_agent()
    fn = agent._tools["rerun_featurizer"].fn
    result = fn(
        featurizer_config_patch={"windows": [60]},
        reply="Sure, switching to 60-day windows.",
        context=None,
    )
    assert result == {
        "action": "rerun",
        "stage": "featurizing",
        "patch": {"windows": [60]},
        "reply": "Sure, switching to 60-day windows.",
    }


def test_rerun_data_gathering_tool_returns_rerun_intent_with_reply() -> None:
    agent = make_followup_agent()
    fn = agent._tools["rerun_data_gathering"].fn
    result = fn(
        sources_to_add=["Brent crude futures"],
        reply="Adding Brent crude now.",
        context=None,
    )
    assert result == {
        "action": "rerun",
        "stage": "data_gathering",
        "sources_to_add": ["Brent crude futures"],
        "reply": "Adding Brent crude now.",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_followup_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.followup_agent'`

- [ ] **Step 3: Write `make_followup_agent()`**

Create `backend/src/agents/followup_agent.py`:

```python
from __future__ import annotations

from typing import Any

from src.agent.tools import AgentContext
from src.agents.base import BaseAgent

_SYSTEM_PROMPT = """\
You are FollowUpAgent. The user is looking at a completed market regime analysis and may ask \
follow-up questions or ask you to change settings and re-run.

You will be given, in the user message:
- The regime classification result (regime label + confidence) and the price-direction \
prediction (direction + confidence)
- Drift-detection findings (whether drift was detected, drifted features, PSI score)
- Feature-importance (SHAP) and backtest results — these may be present or may be null/missing
- The data sources used (data manifest) and the featurizer settings (featurizer_config)
- A comparable prior session for this market profile, if one exists \
({"available": true, "regime": ..., "direction": ..., "summary": ..., "timeframe": ...} \
or {"available": false})
- Recent conversation turns

For questions about the regime, direction, drift, data sources, featurizer settings, or how \
this session compares to the prior one, answer directly and tersely from the information above \
— do not call a tool for these.

IMPORTANT: Only discuss feature-importance (SHAP) or backtest results if they are explicitly \
present and non-null in the input, and only discuss the comparable session if its `available` \
field is true. If something is missing, say so plainly — never invent or speculate about data \
you were not given.

If — and only if — the user clearly asks you to change featurizer settings (e.g. window sizes, \
lags, feature families) or to add new data sources and re-run the analysis, call the matching \
tool:
- rerun_featurizer: patch featurizer_config and re-run from featurizing
- rerun_data_gathering: add data sources and re-run the full pipeline from data gathering

Both tools require a `reply` argument: a short, friendly natural-language confirmation of what \
you're about to do. This `reply` is the ONLY text the user will see for this turn, so always \
include one when calling either tool.

When answering directly, respond with plain text only — no JSON, no markdown headers.
"""


def make_followup_agent() -> BaseAgent:
    agent = BaseAgent(name="FollowUpAgent", system_prompt=_SYSTEM_PROMPT)

    def rerun_featurizer(
        featurizer_config_patch: dict[str, Any],
        reply: str,
        context: AgentContext | None = None,
    ) -> dict[str, Any]:
        """Patch the featurizer config and re-run featurizing (and downstream analysis)."""
        return {
            "action": "rerun",
            "stage": "featurizing",
            "patch": featurizer_config_patch,
            "reply": reply,
        }

    def rerun_data_gathering(
        sources_to_add: list[str],
        reply: str,
        context: AgentContext | None = None,
    ) -> dict[str, Any]:
        """Add data sources and re-run the full pipeline from data gathering."""
        return {
            "action": "rerun",
            "stage": "data_gathering",
            "sources_to_add": sources_to_add,
            "reply": reply,
        }

    agent.register_tool(
        rerun_featurizer,
        {
            "type": "object",
            "properties": {
                "featurizer_config_patch": {
                    "type": "object",
                    "description": (
                        'Partial featurizer_config to merge in, e.g. {"windows": [5, 30, 90]}'
                    ),
                },
                "reply": {
                    "type": "string",
                    "description": (
                        "Short natural-language confirmation of what you're about to do"
                    ),
                },
            },
            "required": ["featurizer_config_patch", "reply"],
        },
        is_stop=True,
    )
    agent.register_tool(
        rerun_data_gathering,
        {
            "type": "object",
            "properties": {
                "sources_to_add": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Natural-language descriptions of data sources to add, "
                        'e.g. "Brent crude futures"'
                    ),
                },
                "reply": {
                    "type": "string",
                    "description": (
                        "Short natural-language confirmation of what you're about to do"
                    ),
                },
            },
            "required": ["sources_to_add", "reply"],
        },
        is_stop=True,
    )
    return agent
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_followup_agent.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd backend && git add src/agents/followup_agent.py tests/test_followup_agent.py
git commit -m "feat: add FollowUpAgent with rerun_featurizer and rerun_data_gathering tools"
```

---

## Task 2: `run_followup_service`

**Files:**
- Create: `backend/src/services/followup.py`
- Test: `backend/tests/test_followup_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_followup_service.py`:

```python
from __future__ import annotations

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlmodel import SQLModel

import src.db.models  # noqa: F401 — registers all tables
from src.db.models import AnalysisResult, DataArtifact, FeatureArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.services.followup import run_followup_service


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


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append(json.loads(message))

    async def aclose(self) -> None:
        pass


async def _make_engine() -> AsyncEngine:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _seed_session(engine: AsyncEngine, *, stage: str, status: str) -> uuid.UUID:
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
                        "content": "what regime are we in?",
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
                summary="WTI is in a bull_supercycle regime.",
                feature_hash="feature-hash",
            )
        )
        await db.commit()

    return session_id


@pytest.mark.asyncio
async def test_run_followup_service_answers_directly_and_stays_in_follow_up() -> None:
    engine = await _make_engine()
    session_id = await _seed_session(
        engine, stage=SessionStage.FOLLOW_UP.value, status=SessionStatus.WAITING.value
    )
    fake_redis = _FakeRedis()

    with (
        patch("src.agents.base.openai.AsyncOpenAI") as cls,
        patch("src.services.followup.aioredis.Redis.from_url", return_value=fake_redis),
    ):
        cls.return_value = _mock_client(
            [_text_resp("We're in a bull_supercycle regime with an upward bias.")]
        )
        await run_followup_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)

    assert s is not None
    assert s.stage == SessionStage.FOLLOW_UP.value
    assert s.status == SessionStatus.WAITING.value
    last = s.conversation[-1]
    assert last["role"] == "assistant"
    assert last["content"] == "We're in a bull_supercycle regime with an upward bias."
    assert any(e["type"] == "chat_reply" for e in s.activity_events)
    assert any(m["type"] == "chat_reply" for m in fake_redis.published)


@pytest.mark.asyncio
async def test_run_followup_service_rerun_featurizer_intent_chains_to_tabpfn() -> None:
    engine = await _make_engine()
    session_id = await _seed_session(
        engine, stage=SessionStage.FOLLOW_UP.value, status=SessionStatus.WAITING.value
    )
    fake_redis = _FakeRedis()

    with (
        patch("src.agents.base.openai.AsyncOpenAI") as cls,
        patch("src.services.followup.aioredis.Redis.from_url", return_value=fake_redis),
        patch(
            "src.services.followup.run_featurizer_service", new_callable=AsyncMock
        ) as mock_feat,
        patch(
            "src.services.followup.run_tabpfn_service", new_callable=AsyncMock
        ) as mock_tabpfn,
    ):
        cls.return_value = _mock_client(
            [
                _tool_resp(
                    "rerun_featurizer",
                    {
                        "featurizer_config_patch": {"windows": [60, 120]},
                        "reply": "Sure — re-running with 60/120-day windows.",
                    },
                )
            ]
        )
        await run_followup_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)

    assert s is not None
    assert s.featurizer_config["windows"] == [60, 120]
    assert s.featurizer_config["lags"] == [1]  # untouched keys survive the patch merge
    assert s.stage == SessionStage.FEATURIZING.value
    assert s.status == SessionStatus.RUNNING.value
    assert s.conversation[-1]["content"] == "Sure — re-running with 60/120-day windows."
    mock_feat.assert_awaited_once_with(session_id, engine)
    mock_tabpfn.assert_awaited_once_with(session_id, engine)
    assert any(
        m["type"] == "stage_transition" and m["to"] == "featurizing" for m in fake_redis.published
    )


@pytest.mark.asyncio
async def test_run_followup_service_rerun_data_gathering_intent_chains_full_pipeline() -> None:
    engine = await _make_engine()
    session_id = await _seed_session(
        engine, stage=SessionStage.FOLLOW_UP.value, status=SessionStatus.WAITING.value
    )
    fake_redis = _FakeRedis()

    with (
        patch("src.agents.base.openai.AsyncOpenAI") as cls,
        patch("src.services.followup.aioredis.Redis.from_url", return_value=fake_redis),
        patch(
            "src.services.followup.run_data_agent_service", new_callable=AsyncMock
        ) as mock_data,
        patch(
            "src.services.followup.run_featurizer_service", new_callable=AsyncMock
        ) as mock_feat,
        patch(
            "src.services.followup.run_tabpfn_service", new_callable=AsyncMock
        ) as mock_tabpfn,
    ):
        cls.return_value = _mock_client(
            [
                _tool_resp(
                    "rerun_data_gathering",
                    {
                        "sources_to_add": ["Brent crude futures"],
                        "reply": "Got it — adding Brent crude and re-running from data gathering.",
                    },
                )
            ]
        )
        await run_followup_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)

    assert s is not None
    assert s.pending_sources == [{"connector_id": "Brent crude futures", "params": {}}]
    assert s.stage == SessionStage.DATA_GATHERING.value
    assert s.status == SessionStatus.RUNNING.value
    assert (
        s.conversation[-1]["content"]
        == "Got it — adding Brent crude and re-running from data gathering."
    )
    mock_data.assert_awaited_once_with(session_id, engine)
    mock_feat.assert_awaited_once_with(session_id, engine)
    mock_tabpfn.assert_awaited_once_with(session_id, engine)
    assert any(
        m["type"] == "stage_transition" and m["to"] == "data_gathering"
        for m in fake_redis.published
    )


@pytest.mark.asyncio
async def test_run_followup_service_noop_when_stage_is_not_follow_up() -> None:
    engine = await _make_engine()
    session_id = await _seed_session(
        engine, stage=SessionStage.EXPLAINING.value, status=SessionStatus.RUNNING.value
    )
    fake_redis = _FakeRedis()

    with patch("src.services.followup.aioredis.Redis.from_url", return_value=fake_redis):
        await run_followup_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)

    assert s is not None
    assert s.stage == SessionStage.EXPLAINING.value
    assert len(s.conversation) == 1


@pytest.mark.asyncio
async def test_run_followup_service_noop_when_session_is_canceled() -> None:
    engine = await _make_engine()
    session_id = await _seed_session(
        engine, stage=SessionStage.FOLLOW_UP.value, status=SessionStatus.CANCELED.value
    )
    fake_redis = _FakeRedis()

    with patch("src.services.followup.aioredis.Redis.from_url", return_value=fake_redis):
        await run_followup_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)

    assert s is not None
    assert s.status == SessionStatus.CANCELED.value
    assert len(s.conversation) == 1


@pytest.mark.asyncio
async def test_run_followup_service_skips_write_when_canceled_midrun() -> None:
    engine = await _make_engine()
    session_id = await _seed_session(
        engine, stage=SessionStage.FOLLOW_UP.value, status=SessionStatus.WAITING.value
    )
    fake_redis = _FakeRedis()

    async def create(**kwargs):  # type: ignore[return]
        # Simulate a cancellation arriving while the LLM call is in flight.
        async with AsyncSession(engine) as cancel_db:
            fresh = await cancel_db.get(SessionModel, session_id)
            assert fresh is not None
            fresh.status = SessionStatus.CANCELED.value
            await cancel_db.commit()
        return _text_resp("a reply that should never be written")

    mock_client = MagicMock()
    mock_client.chat.completions.create = create

    with (
        patch("src.agents.base.openai.AsyncOpenAI") as cls,
        patch("src.services.followup.aioredis.Redis.from_url", return_value=fake_redis),
    ):
        cls.return_value = mock_client
        await run_followup_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)

    assert s is not None
    assert len(s.conversation) == 1  # only the seeded user turn — no reply appended
    assert s.stage == SessionStage.FOLLOW_UP.value
    assert s.status == SessionStatus.CANCELED.value


@pytest.mark.asyncio
async def test_run_followup_service_marks_failed_on_exception() -> None:
    engine = await _make_engine()
    session_id = await _seed_session(
        engine, stage=SessionStage.FOLLOW_UP.value, status=SessionStatus.WAITING.value
    )
    fake_redis = _FakeRedis()

    with (
        patch("src.agents.base.openai.AsyncOpenAI", side_effect=RuntimeError("llm down")),
        patch("src.services.followup.aioredis.Redis.from_url", return_value=fake_redis),
    ):
        await run_followup_service(session_id, engine)

    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)

    assert s is not None
    assert s.status == SessionStatus.FAILED.value
    assert s.error == "llm down"
    assert any(
        e["type"] == "error" and e.get("stage") == "follow_up" for e in s.activity_events
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_followup_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.followup'`

- [ ] **Step 3: Write `run_followup_service`**

Create `backend/src/services/followup.py`:

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

from src.agents.followup_agent import make_followup_agent
from src.config import settings
from src.db.models import AnalysisResult, DataArtifact, SessionStage, SessionStatus
from src.db.models import Session as SessionModel
from src.services.data_agent import run_data_agent_service
from src.services.featurizer import run_featurizer_service
from src.services.featurizer_config import apply_config_patch
from src.services.stage import append_activity_event, set_status, transition_stage
from src.services.tabpfn import run_tabpfn_service

log = structlog.get_logger()

Publisher = Callable[[dict[str, Any]], Awaitable[None]]


async def run_followup_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
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
                log.error("followup.session_not_found", session_id=session_id_str)
                return
            if s.status == SessionStatus.CANCELED:
                log.info("followup.canceled", session_id=session_id_str)
                return
            if s.stage != SessionStage.FOLLOW_UP:
                log.info("followup.wrong_stage", session_id=session_id_str, stage=s.stage)
                return

            try:
                await _run(s, db, engine, publisher)
            except Exception as exc:
                log.error("followup.failed", session_id=session_id_str, error=str(exc))
                set_status(s, SessionStatus.FAILED, error=str(exc))
                err_event: dict[str, Any] = {
                    "type": "error",
                    "stage": "follow_up",
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
    comparable_session: dict[str, Any],
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
        f"Comparable prior session: {json.dumps(comparable_session)}\n"
        f"Recent conversation:\n{history}\n"
        "Respond to the user's latest message now."
    )


async def _find_comparable_session(
    db: AsyncSession, *, market_profile: str, exclude_id: uuid.UUID
) -> dict[str, Any]:
    stmt = (
        select(SessionModel)
        .where(SessionModel.market_profile == market_profile)
        .where(SessionModel.stage == SessionStage.FOLLOW_UP.value)
        .where(SessionModel.id != exclude_id)
        .order_by(SessionModel.created_at.desc())  # type: ignore[attr-defined]
        .limit(1)
    )
    other = (await db.execute(stmt)).scalars().first()
    if other is None:
        return {"available": False}

    ar = (
        (
            await db.execute(
                select(AnalysisResult)
                .where(AnalysisResult.session_id == other.id)
                .order_by(AnalysisResult.created_at.desc())  # type: ignore[attr-defined]
            )
        )
        .scalars()
        .first()
    )
    return {
        "available": True,
        "regime": ar.regime if ar else None,
        "direction": ar.direction if ar else None,
        "summary": ar.summary if ar else None,
        "timeframe": {
            "start": other.timeframe_start.isoformat(),
            "end": other.timeframe_end.isoformat(),
        },
    }


async def _run(
    s: SessionModel, db: AsyncSession, engine: AsyncEngine, publisher: Publisher
) -> None:
    session_id = s.id
    session_id_str = str(session_id)

    # Snapshot everything before the first await — asyncpg expires the object
    # when the connection returns to the pool between async calls.
    current_conversation = list(s.conversation or [])
    current_featurizer_config = dict(s.featurizer_config or {})
    current_pending = list(s.pending_sources or [])
    market_profile = s.market_profile

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

    comparable_session = await _find_comparable_session(
        db, market_profile=market_profile, exclude_id=session_id
    )

    context_block = _build_context_block(
        regime,
        direction,
        drift,
        feature_importance,
        backtest,
        data_manifest,
        current_featurizer_config,
        current_conversation,
        comparable_session,
    )

    agent = make_followup_agent()
    raw_result = await agent.run(
        context=None,
        publisher=publisher,
        initial_user_message=context_block,
    )

    intent: dict[str, Any] | None = None
    try:
        parsed = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and parsed.get("action") == "rerun":
        intent = parsed

    # `s` is expired after the agent's await — re-fetch fresh, and guard against
    # a cancellation that arrived while the (possibly long) LLM round-trip ran.
    async with AsyncSession(engine) as fresh_db:
        fresh_s = await fresh_db.get(SessionModel, session_id)
        if fresh_s is None or fresh_s.status == SessionStatus.CANCELED:
            log.info("followup.canceled_midrun", session_id=session_id_str)
            return

        now = datetime.now(UTC)
        reply_text = intent["reply"] if intent is not None else raw_result
        reply_event: dict[str, Any] = {"type": "chat_reply", "reply": reply_text}

        fresh_s.conversation = [
            *current_conversation,
            {"role": "assistant", "content": reply_text, "created_at": now.isoformat()},
        ]
        append_activity_event(fresh_s, reply_event)

        transition_event: dict[str, Any] | None = None
        if intent is None:
            set_status(fresh_s, SessionStatus.WAITING)
        elif intent["stage"] == "featurizing":
            fresh_s.featurizer_config = apply_config_patch(
                current_featurizer_config, intent.get("patch", {})
            )
            transition_stage(fresh_s, SessionStage.FEATURIZING)
            set_status(fresh_s, SessionStatus.RUNNING)
            transition_event = {
                "type": "stage_transition",
                "from": "follow_up",
                "to": "featurizing",
            }
        else:  # "data_gathering"
            sources_to_add = intent.get("sources_to_add", [])
            fresh_s.pending_sources = [
                *current_pending,
                *[{"connector_id": sid, "params": {}} for sid in sources_to_add],
            ]
            transition_stage(fresh_s, SessionStage.DATA_GATHERING)
            set_status(fresh_s, SessionStatus.RUNNING)
            transition_event = {
                "type": "stage_transition",
                "from": "follow_up",
                "to": "data_gathering",
            }

        await fresh_db.commit()
        log.info("followup.committed", session_id=session_id_str, has_intent=intent is not None)

    await publisher(reply_event)
    if transition_event is not None:
        await publisher(transition_event)

    if intent is None:
        log.info("followup.answered", session_id=session_id_str)
        return

    log.info("followup.rerun_dispatched", session_id=session_id_str, stage=intent["stage"])
    if intent["stage"] == "featurizing":
        await run_featurizer_service(session_id, engine)
        await run_tabpfn_service(session_id, engine)
    else:
        await run_data_agent_service(session_id, engine)
        await run_featurizer_service(session_id, engine)
        await run_tabpfn_service(session_id, engine)
```

A few things to note while implementing:
- The whole reply-write + (optional) stage-regression mutation happens in **one** `fresh_db.commit()` — this is safer than two separate commits (single atomic write, no risk of a reply existing without its accompanying transition if something fails in between) and matches the codebase's "snapshot everything, mutate, single commit" convention used throughout `explanation._run`/`tabpfn._run`/`data_agent._finish_stage`. It still achieves the spec's goal of "the user sees the reply before the slow chain starts," since both commits in the spec's framing would have happened back-to-back before the chain regardless.
- `run_featurizer_service`/`run_tabpfn_service`/`run_data_agent_service` are imported at module level (not lazily) — same as `tabpfn.py` imports `run_explanation_service` at module level. There's no circular-import risk: none of `featurizer.py`, `tabpfn.py`, or `data_agent.py` import from `followup.py`.
- The `else: # "data_gathering"` branch relies on the tools only ever producing `"featurizing"` or `"data_gathering"` as `stage` (enforced by `followup_agent.py`'s two tool definitions) — no `elif`/validation needed for a third case that can't occur.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_followup_service.py -v`
Expected: 7 passed

- [ ] **Step 5: Run the full backend test suite to check for regressions**

Run: `cd backend && uv run pytest -q`
Expected: all tests pass, with 7 more passing than before this task (the new
`test_followup_service.py` file)

- [ ] **Step 6: Commit**

```bash
cd backend && git add src/services/followup.py tests/test_followup_service.py
git commit -m "feat: add run_followup_service with reply/rerun-intent handling and chaining"
```

---

## Task 3: Wire `POST /sessions/{id}/chat` to `FollowUpAgent` at the `FOLLOW_UP` stage

**Files:**
- Modify: `backend/api/routes/chat.py:18,25,66-67`
- Test: `backend/tests/test_chat.py`

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_chat.py` and add these imports at the top (alongside the existing `import io`, `import json`, etc.):

```python
import asyncio
import uuid
from datetime import date
```

and add this import alongside the existing `import pandas as pd`:

```python
from src.db.models import Session as SessionModel
from src.db.models import SessionStage, SessionStatus
```

Then add this helper function near `_setup_session_at_user_review` (it seeds a session directly into `FOLLOW_UP` by reaching through the test client's `get_session` dependency override — there's no API path that reaches `FOLLOW_UP` without running the full agent pipeline):

```python
def _seed_session_at_follow_up(client) -> str:
    async def _seed() -> uuid.UUID:
        from api.main import app
        from src.db.session import get_session

        session_id = uuid.uuid4()
        override = app.dependency_overrides[get_session]
        agen = override()
        db = await agen.__anext__()
        try:
            db.add(
                SessionModel(
                    id=session_id,
                    market_profile="oil",
                    timeframe_start=date(2023, 1, 1),
                    timeframe_end=date(2023, 6, 30),
                    stage=SessionStage.FOLLOW_UP.value,
                    status=SessionStatus.WAITING.value,
                    conversation=[],
                )
            )
            await db.commit()
        finally:
            await agen.aclose()
        return session_id

    return str(asyncio.run(_seed()))
```

Then add these two test functions at the end of the file:

```python
def test_chat_at_follow_up_returns_202_and_enqueues_followup_service(client):
    session_id = _seed_session_at_follow_up(client)

    with patch("api.routes.chat.run_followup_service", new_callable=AsyncMock) as mock_followup:
        res = client.post(
            f"/api/sessions/{session_id}/chat",
            json={"message": "what regime are we in?"},
        )

    assert res.status_code == 202
    mock_followup.assert_called_once()

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["stage"] == "follow_up"
    assert detail["status"] == "running"
    assert detail["conversation"][-1]["role"] == "user"
    assert detail["conversation"][-1]["content"] == "what regime are we in?"


def test_chat_at_follow_up_does_not_invoke_review_interpreter(client):
    session_id = _seed_session_at_follow_up(client)

    with (
        patch("api.routes.chat.run_followup_service", new_callable=AsyncMock),
        patch("api.routes.chat.ReviewInterpreter") as mock_cls,
    ):
        client.post(f"/api/sessions/{session_id}/chat", json={"message": "hi"})

    mock_cls.assert_not_called()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_chat.py -k follow_up -v`
Expected: FAIL — `test_chat_at_follow_up_returns_202_and_enqueues_followup_service` fails with
`AttributeError` (no `run_followup_service` in `api.routes.chat` to patch) or a 409 (stage not yet
allowed); `test_chat_at_follow_up_does_not_invoke_review_interpreter` fails because
`ReviewInterpreter` *is* still called at this stage today

- [ ] **Step 3: Wire the route**

In `backend/api/routes/chat.py`, change the import line at line 18:

```python
from src.services.featurizer_config import apply_config_patch
```

to:

```python
from src.services.featurizer_config import apply_config_patch
from src.services.followup import run_followup_service
```

Change line 25:

```python
_CHAT_ALLOWED_STAGES = {SessionStage.USER_REVIEW.value}
```

to:

```python
_CHAT_ALLOWED_STAGES = {SessionStage.USER_REVIEW.value, SessionStage.FOLLOW_UP.value}
```

Then, immediately after the existing stage-gate check (currently lines 66-67):

```python
    if s.stage not in _CHAT_ALLOWED_STAGES:
        raise HTTPException(status_code=409, detail=f"chat not available at stage {s.stage}")
```

add a new branch that intercepts `FOLLOW_UP` before any of the `USER_REVIEW`/`ReviewInterpreter`
logic runs:

```python
    if s.stage == SessionStage.FOLLOW_UP.value:
        now = datetime.now(UTC)
        s.conversation = [
            *s.conversation,
            {"role": "user", "content": req.message, "created_at": now.isoformat()},
        ]
        s.status = SessionStatus.RUNNING.value
        s.updated_at = now.replace(tzinfo=None)
        await db.commit()
        background_tasks.add_task(run_followup_service, uid, engine)
        return ChatResponse(session_id=session_id)
```

(`SessionStatus`, `datetime`, `UTC`, `engine`, and `ChatResponse` are all already imported in this
file — no other import changes needed.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_chat.py -k follow_up -v`
Expected: 2 passed

- [ ] **Step 5: Run the full chat test file to check for regressions**

Run: `cd backend && uv run pytest tests/test_chat.py -v`
Expected: all tests pass (existing `USER_REVIEW`-stage tests are untouched and still pass; the
409-at-wrong-stage test still passes since `CONFIGURING`/`DATA_GATHERING` etc. remain disallowed)

- [ ] **Step 6: Commit**

```bash
cd backend && git add api/routes/chat.py tests/test_chat.py
git commit -m "feat: route FOLLOW_UP-stage chat to FollowUpAgent via background task"
```

---

## Task 4: Final verification

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && uv run pytest -q`
Expected: all tests pass, zero failures

- [ ] **Step 2: Run lint and type-check**

Run: `cd backend && uv run ruff check . && uv run mypy .`
Expected: ruff reports no issues in the new/changed files; mypy reports no *new* errors (compare
against `git stash`-ed output if any pre-existing errors appear, the same way PR 4a's mypy check
was verified — see `backend/tests/test_explanation_service.py`'s `_make_engine` annotation fix
for the kind of issue to watch for: untyped async helper functions called in typed contexts)

- [ ] **Step 3: Discard any incidental `uv.lock` changes**

Run: `git status backend/uv.lock`
If it shows as modified (a known artifact of `uv run` syncing — not an intended change), run:
`git checkout -- backend/uv.lock`

- [ ] **Step 4: Confirm git log shows three feature commits plus this plan/spec**

Run: `git log --oneline -6`
Expected to see (top to bottom): the chat-wiring commit, the service commit, the agent commit,
the design-spec commit (`docs: add FollowUpAgent (PR 4b) design spec`), then the prior
ExplanationAgent merge commit
