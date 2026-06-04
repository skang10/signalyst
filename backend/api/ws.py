import structlog
from fastapi import WebSocket, WebSocketDisconnect

log = structlog.get_logger()


async def session_stream_handler(websocket: WebSocket, session_id: str) -> None:
    """WebSocket stub for PR 1. Accepts connections; agent events arrive in PR 3."""
    await websocket.accept()
    log.info("ws.connected", session_id=session_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log.info("ws.disconnected", session_id=session_id)
