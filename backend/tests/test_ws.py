from __future__ import annotations

import pytest
from fastapi import WebSocketDisconnect

from api.ws import session_stream_handler


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self._messages: list[str | WebSocketDisconnect] = ["ping", WebSocketDisconnect()]

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        msg = self._messages.pop(0)
        if isinstance(msg, WebSocketDisconnect):
            raise msg
        return msg


@pytest.mark.asyncio
async def test_session_stream_handler_accepts_and_disconnects() -> None:
    ws = _FakeWebSocket()
    await session_stream_handler(ws, "test-session-id")  # type: ignore[arg-type]
    assert ws.accepted
