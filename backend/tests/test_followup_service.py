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
        patch("src.services.followup.run_featurizer_service", new_callable=AsyncMock) as mock_feat,
        patch("src.services.followup.run_tabpfn_service", new_callable=AsyncMock) as mock_tabpfn,
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
        patch("src.services.followup.run_data_agent_service", new_callable=AsyncMock) as mock_data,
        patch("src.services.followup.run_featurizer_service", new_callable=AsyncMock) as mock_feat,
        patch("src.services.followup.run_tabpfn_service", new_callable=AsyncMock) as mock_tabpfn,
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
    assert any(e["type"] == "error" and e.get("stage") == "follow_up" for e in s.activity_events)
