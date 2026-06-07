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
