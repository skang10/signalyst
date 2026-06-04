from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.ws import session_stream_handler


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        pass


def _make_empty_pubsub() -> MagicMock:
    async def listen():  # type: ignore[return]
        return
        yield  # makes it an async generator

    ps = MagicMock()
    ps.subscribe = AsyncMock()
    ps.unsubscribe = AsyncMock()
    ps.listen = listen
    return ps


@pytest.mark.asyncio
async def test_session_stream_handler_accepts_and_disconnects() -> None:
    ws = _FakeWebSocket()

    with patch("api.ws.aioredis.Redis.from_url") as mock_redis:
        mock_redis.return_value.pubsub.return_value = _make_empty_pubsub()
        mock_redis.return_value.aclose = AsyncMock()
        await session_stream_handler(ws, "test-session-id")  # type: ignore[arg-type]

    assert ws.accepted
