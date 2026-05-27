from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

from api.ws import stream_handler


class _FakePubSub:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.closed = False
        self._messages = [
            {"type": "message", "data": json.dumps({"type": "thought", "content": "working"})},
        ]

    async def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    async def unsubscribe(self, channel: str) -> None:
        self.subscribed.remove(channel)

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 1.0):
        if self._messages:
            return self._messages.pop(0)
        raise WebSocketDisconnect()

    async def close(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(self, pubsub: _FakePubSub) -> None:
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self) -> _FakePubSub:
        return self._pubsub

    async def aclose(self) -> None:
        self.closed = True


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)


@pytest.mark.asyncio
async def test_stream_handler_forwards_redis_messages_to_websocket() -> None:
    pubsub = _FakePubSub()
    redis = _FakeRedis(pubsub)
    websocket = _FakeWebSocket()

    with patch("api.ws.aioredis.from_url", MagicMock(return_value=redis)):
        await stream_handler(websocket, "run-1")  # type: ignore[arg-type]

    assert websocket.accepted
    assert websocket.sent == [{"type": "thought", "content": "working"}]
    assert pubsub.closed
    assert redis.closed
