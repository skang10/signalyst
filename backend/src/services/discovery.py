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
            append_activity_event(s, {"type": "error", "stage": "configuring", "message": str(exc)})
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
        await r.aclose()  # type: ignore[attr-defined]
