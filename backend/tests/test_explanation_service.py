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
    assert any(e["type"] == "error" and e.get("stage") == "explaining" for e in s.activity_events)
