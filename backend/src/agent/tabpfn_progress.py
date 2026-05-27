"""
Intercepts TabPFN's internal run_task to emit per-operation progress events.

Call install() once at startup; use make_callback() + set_callback() around
each TabPFN tool dispatch in the agent loop.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import threading
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger()

_callback: contextvars.ContextVar[Callable[[str], None] | None] = contextvars.ContextVar(
    "tabpfn_cb", default=None
)
_installed = False

# cancel_events[run_id] is set when the user cancels mid-prediction so the
# in-flight thread can abort cleanly without finishing all ensemble calls.
_cancel_events: dict[str, threading.Event] = {}

# Expected op counts per tool — used by the frontend for a determinate progress bar.
# evaluate_features total is computed from the feature matrix shape before dispatch.
EXPECTED_OPS: dict[str, int] = {
    "run_tabpfn:regime": 4,  # 1 Fitting + 3 Predicting
    "run_tabpfn:direction": 5,  # 1 Fitting + 4 Predicting
}


class RunCanceledInThread(Exception):
    """Raised inside a TabPFN thread when the run is cancelled mid-prediction."""


def install() -> None:
    """Monkey-patch tabpfn_client.estimator.run_task once at startup."""
    global _installed
    if _installed:
        return

    import tabpfn_client.estimator as _est

    _orig = _est.run_task

    def _patched(task: Callable[[], Any], message: str, with_spinner: bool = True) -> Any:
        result = _orig(task, message, with_spinner=False)
        cb = _callback.get()
        if cb is not None:
            cb(message)
        return result

    _est.run_task = _patched
    _installed = True


def register_run(run_id: str) -> None:
    _cancel_events[run_id] = threading.Event()


def cancel(run_id: str) -> None:
    event = _cancel_events.get(run_id)
    if event:
        event.set()


def unregister_run(run_id: str) -> None:
    _cancel_events.pop(run_id, None)


def make_callback(
    loop: asyncio.AbstractEventLoop,
    redis_client: aioredis.Redis,  # type: ignore[type-arg]
    channel: str,
    run_id: str,
    tool: str,
    task: str | None = None,
    total: int | None = None,
) -> Callable[[str], None]:
    """Return a callback that fires after each TabPFN Fitting/Predicting call."""
    count = [0]
    key = f"{tool}:{task}" if task else tool
    resolved_total = total if total is not None else EXPECTED_OPS.get(key)
    cancel_event = _cancel_events.get(run_id)

    def on_prediction(message: str) -> None:
        if cancel_event and cancel_event.is_set():
            raise RunCanceledInThread(run_id)
        count[0] += 1
        log.info(
            "agent.tabpfn_prediction",
            run_id=run_id,
            tool=tool,
            operation=message.lower(),
            count=count[0],
            total=resolved_total,
        )
        payload = json.dumps(
            {
                "type": "tabpfn_prediction",
                "operation": message.lower(),
                "count": count[0],
                "total": resolved_total,
                "tool": tool,
            }
        )
        asyncio.run_coroutine_threadsafe(
            redis_client.publish(channel, payload),
            loop,
        )

    return on_prediction


def set_callback(cb: Callable[[str], None] | None) -> None:
    _callback.set(cb)
