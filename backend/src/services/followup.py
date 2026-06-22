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

            log.info(
                "followup.started",
                session_id=session_id_str,
                conversation_len=len(s.conversation or []),
            )

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
        f"Feature importance (Spearman correlation): {json.dumps(feature_importance)}\n"
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
