from __future__ import annotations

import asyncio

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
    disconnect_task = asyncio.create_task(websocket.receive_text())
    listener = pubsub.listen()
    message_task = asyncio.create_task(anext(listener))

    try:
        while True:
            done, _pending = await asyncio.wait(
                {message_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if disconnect_task in done:
                await disconnect_task
                break

            try:
                message = message_task.result()
            except StopAsyncIteration:
                break
            message_task = asyncio.create_task(anext(listener))
            if message["type"] == "message":
                data = message["data"]
                text = data.decode() if isinstance(data, bytes) else data
                await websocket.send_text(text)
    except (WebSocketDisconnect, RuntimeError):
        log.info("ws.disconnected", session_id=short_id)
    except asyncio.CancelledError:
        log.info("ws.cancelled", session_id=short_id)
        raise
    finally:
        disconnect_task.cancel()
        message_task.cancel()
        await pubsub.unsubscribe(f"session:{session_id}:stream")
        await r.aclose()  # type: ignore[attr-defined]
