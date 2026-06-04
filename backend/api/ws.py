from __future__ import annotations

import redis.asyncio as aioredis
import structlog
from fastapi import WebSocket, WebSocketDisconnect

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
        await r.aclose()  # type: ignore[attr-defined]
