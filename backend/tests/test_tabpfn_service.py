from __future__ import annotations

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
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


async def _make_engine() -> AsyncEngine:
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
