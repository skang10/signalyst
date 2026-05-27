from __future__ import annotations

import logging
from typing import Any

NOISY_ACCESS_PATHS = ("/health",)
NOISY_ACCESS_PREFIXES = ("/api/runs/",)


class NoisyEndpointFilter(logging.Filter):
    """Suppress high-frequency polling and health-check access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        method, path = _extract_access_request(record)
        return should_log_request(method, path)


def configure_logging() -> None:
    """Apply backend logging defaults once."""
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(log_filter, NoisyEndpointFilter) for log_filter in access_logger.filters):
        access_logger.addFilter(NoisyEndpointFilter())
    # Suppress low-level WebSocket protocol noise ("connection open/closed").
    # ws.connected / ws.disconnected in structlog cover the same events with run_id context.
    logging.getLogger("uvicorn.protocols.websockets").setLevel(logging.WARNING)


def request_log_level(method: str | None, path: str | None) -> str:
    return "debug" if _is_noisy_request(method, path) else "info"


def should_log_request(
    method: str | None, path: str | None, *, include_noisy: bool = False
) -> bool:
    if include_noisy:
        return True
    return not _is_noisy_request(method, path)


def _is_noisy_request(method: str | None, path: str | None) -> bool:
    if method != "GET" or path is None:
        return False
    if path in NOISY_ACCESS_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in NOISY_ACCESS_PREFIXES)


def _extract_access_request(record: logging.LogRecord) -> tuple[str | None, str | None]:
    args = record.args
    if isinstance(args, tuple) and len(args) >= 5:
        return _as_str(args[1]), _as_str(args[2])

    message = record.getMessage()
    parts = message.split('"')
    if len(parts) < 2:
        return None, None

    request_line = parts[1].split()
    if len(request_line) < 2:
        return None, None
    return request_line[0], request_line[1]


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
