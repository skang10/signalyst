import json

import redis.asyncio as aioredis
import structlog
from fastapi import WebSocket, WebSocketDisconnect

from src.config import settings

log = structlog.get_logger()


async def stream_handler(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    log.info("ws.connected", run_id=run_id)
    redis_client = aioredis.from_url(settings.redis_url)
    pubsub = redis_client.pubsub()
    channel = f"run:{run_id}"
    try:
        await pubsub.subscribe(channel)
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            await websocket.send_json(json.loads(data))
    except WebSocketDisconnect:
        log.info("ws.disconnected", run_id=run_id)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis_client.aclose()
