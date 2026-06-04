from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from api.ws import session_stream_handler


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def receive_text(self) -> str:
        raise WebSocketDisconnect()


def _make_pubsub(messages: list[dict]) -> MagicMock:
    msgs = list(messages)

    async def listen():  # type: ignore[return]
        for m in msgs:
            yield m

    ps = MagicMock()
    ps.subscribe = AsyncMock()
    ps.unsubscribe = AsyncMock()
    ps.listen = listen
    return ps


@pytest.mark.asyncio
async def test_ws_accepts_connection() -> None:
    ws = _FakeWebSocket()
    pubsub = _make_pubsub([])

    with patch("api.ws.aioredis.Redis.from_url") as mock_redis:
        mock_redis.return_value.pubsub.return_value = pubsub
        mock_redis.return_value.aclose = AsyncMock()
        await session_stream_handler(ws, "test-session-id")  # type: ignore[arg-type]

    assert ws.accepted


@pytest.mark.asyncio
async def test_ws_forwards_message_events() -> None:
    ws = _FakeWebSocket()
    event = {"type": "thought", "agent": "DataAgent", "content": "fetching data"}
    pubsub = _make_pubsub(
        [
            {"type": "message", "data": json.dumps(event).encode()},
        ]
    )

    with patch("api.ws.aioredis.Redis.from_url") as mock_redis:
        mock_redis.return_value.pubsub.return_value = pubsub
        mock_redis.return_value.aclose = AsyncMock()
        await session_stream_handler(ws, "test-session-id")  # type: ignore[arg-type]

    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0])["type"] == "thought"


@pytest.mark.asyncio
async def test_ws_ignores_non_message_events() -> None:
    ws = _FakeWebSocket()
    pubsub = _make_pubsub(
        [
            {"type": "subscribe", "data": 1},
            {"type": "message", "data": json.dumps({"type": "done"}).encode()},
        ]
    )

    with patch("api.ws.aioredis.Redis.from_url") as mock_redis:
        mock_redis.return_value.pubsub.return_value = pubsub
        mock_redis.return_value.aclose = AsyncMock()
        await session_stream_handler(ws, "test-session-id")  # type: ignore[arg-type]

    assert len(ws.sent) == 1
