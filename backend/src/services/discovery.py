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

log = structlog.get_logger()


async def run_discovery_service(session_id: uuid.UUID, engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        s = await db.get(SessionModel, session_id)
        if s is None:
            log.error("discovery.session_not_found", session_id=str(session_id))
            return
        if s.status == SessionStatus.CANCELED:
            return
        await _run(s, db)


async def _run(s: SessionModel, db: AsyncSession) -> None:
    # Snapshot everything before the first await — asyncpg expires the object
    # when the connection returns to the pool between async calls.
    session_id_str = str(s.id)
    current_conversation = list(s.conversation or [])
    current_activity_events = list(s.activity_events or [])
    current_stage_history = list(s.stage_history or [])
    market_profile = s.market_profile
    timeframe_start = str(s.timeframe_start)
    timeframe_end = str(s.timeframe_end)

    r = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    channel = f"session:{session_id_str}:stream"

    async def publisher(event: dict[str, Any]) -> None:
        enriched = {**event, "created_at": datetime.now(UTC).isoformat()}
        await r.publish(channel, json.dumps(enriched))

    try:
        log.info(
            "discovery.starting",
            session_id=session_id_str,
            market_profile=market_profile,
            timeframe=f"{timeframe_start} → {timeframe_end}",
        )
        ctx = DiscoveryContext(
            market_profile=market_profile,
            timeframe_start=timeframe_start,
            timeframe_end=timeframe_end,
        )
        agent = make_discovery_agent()
        await agent.run(context=ctx, publisher=publisher)

        # All writes below use snapshots — no reads from expired s
        n_sources = len(ctx.pending_sources)
        now = datetime.now(UTC)
        new_event: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "created_at": now.isoformat(),
            "type": "stage_transition",
            "from": SessionStage.CONFIGURING,
            "to": SessionStage.DATA_GATHERING,
            "n_sources": n_sources,
        }
        new_stage_entry = {
            "stage": SessionStage.DATA_GATHERING.value,
            "entered_at": now.isoformat(),
        }

        s.pending_sources = list(ctx.pending_sources)
        s.conversation = [
            *current_conversation,
            {"role": "assistant", "content": f"Recommended {n_sources} data sources."},
        ]
        s.activity_events = [*current_activity_events, new_event]
        s.stage = SessionStage.DATA_GATHERING.value
        s.stage_history = [*current_stage_history, new_stage_entry]
        s.status = SessionStatus.RUNNING.value
        s.updated_at = now.replace(tzinfo=None)

        await db.commit()
        log.info("discovery.complete", session_id=session_id_str, n_sources=n_sources)
    except Exception as exc:
        log.error("discovery.failed", session_id=session_id_str, error=str(exc))
        now = datetime.now(UTC)
        error_event: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "created_at": now.isoformat(),
            "type": "error",
            "stage": "configuring",
            "message": str(exc),
        }
        s.status = SessionStatus.FAILED.value
        s.error = str(exc)
        s.updated_at = now.replace(tzinfo=None)
        s.activity_events = [*current_activity_events, error_event]
        await db.commit()
    finally:
        await r.aclose()  # type: ignore[attr-defined]
