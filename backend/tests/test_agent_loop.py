from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.loop import (
    RunCanceled,
    build_system_prompt,
    estimate_tabpfn_calls,
    phase_for_tool,
    run_agent_loop,
    tabpfn_calls_for_tool,
)
from src.db.models import RunStatus


class _SessionContext:
    def __init__(self, run: MagicMock) -> None:
        self.session = AsyncMock()
        self.session.get.return_value = run

    async def __aenter__(self) -> AsyncMock:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


class _SessionFactory:
    def __init__(self, run: MagicMock) -> None:
        self.run = run
        self.contexts: list[_SessionContext] = []

    def __call__(self, *args: object, **kwargs: object) -> _SessionContext:
        context = _SessionContext(self.run)
        self.contexts.append(context)
        return context


def _tool_call_response(name: str = "explain_prediction") -> SimpleNamespace:
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name=name,
                                arguments=json.dumps(
                                    {
                                        "regime": "range_bound",
                                        "direction": "up",
                                        "confidence": 0.7,
                                        "key_features": ["CL=F_roc_20d"],
                                    }
                                ),
                            ),
                        )
                    ],
                ),
            )
        ],
    )


def test_quick_prompt_limits_shap_and_skips_backtest_by_default() -> None:
    prompt = build_system_prompt("quick", ["regime_classification"])

    assert "evaluate_features with top_n=5 and max_samples=5" in prompt
    assert "Do not call backtest in quick mode unless tasks explicitly include" in prompt


def test_quick_prompt_allows_limited_backtest_when_requested() -> None:
    prompt = build_system_prompt("quick", ["backtest"])

    assert "backtest with horizon=20, step=60, max_windows=3" in prompt


def test_full_prompt_runs_full_backtest() -> None:
    prompt = build_system_prompt("full", ["regime_classification"])

    assert "evaluate_features with top_n=10, max_samples=50, and n_repeats=3" in prompt
    assert "backtest with horizon=20, step=20, max_windows=null" in prompt


def test_phase_for_tool_maps_regime_and_direction() -> None:
    assert phase_for_tool("run_tabpfn", {"task": "regime"}) == "predicting_regime"
    assert phase_for_tool("run_tabpfn", {"task": "direction"}) == "predicting_direction"


def test_phase_for_tool_maps_other_tools() -> None:
    assert phase_for_tool("fetch_data", {}) == "fetching_market_data"
    assert phase_for_tool("evaluate_features", {}) == "evaluating_features"
    assert phase_for_tool("backtest", {}) == "backtesting"


def test_estimate_tabpfn_calls_quick_without_backtest() -> None:
    estimate = estimate_tabpfn_calls("quick", ["regime_classification"])

    assert (
        estimate["known_calls"] == 2
    )  # regime + direction; evaluate_features uses correlation (0 calls)
    assert estimate["unknown_backtest"] is False


def test_estimate_tabpfn_calls_quick_with_backtest() -> None:
    estimate = estimate_tabpfn_calls("quick", ["backtest"])

    assert estimate["known_calls"] == 8  # 2 base + 6 backtest windows
    assert estimate["unknown_backtest"] is False


def test_estimate_tabpfn_calls_full_marks_unknown_backtest() -> None:
    estimate = estimate_tabpfn_calls("full", ["regime_classification"])

    assert (
        estimate["known_calls"] == 2
    )  # regime + direction; evaluate_features n_repeats unknown at estimate time
    assert estimate["unknown_backtest"] is True


def test_tabpfn_calls_for_tool() -> None:
    assert tabpfn_calls_for_tool("run_tabpfn", {"task": "regime"}, {}) == 1
    assert tabpfn_calls_for_tool("run_tabpfn", {"task": "direction"}, {}) == 1
    assert (
        tabpfn_calls_for_tool("evaluate_features", {}, {}) == 0
    )  # n_repeats=0 default → correlation
    assert (
        tabpfn_calls_for_tool("evaluate_features", {"n_repeats": 1}, {"n_features_evaluated": 5})
        == 6
    )
    assert tabpfn_calls_for_tool("backtest", {"max_windows": 3}, {"n_windows": 3}) == 6


@pytest.mark.asyncio
async def test_run_agent_loop_stops_if_run_already_canceled() -> None:
    run = MagicMock()
    run.status = RunStatus.CANCELED
    sessions = _SessionFactory(run)
    redis_client = AsyncMock()
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock()

    with (
        patch("src.agent.loop.AsyncSession", sessions),
        patch("src.agent.loop.aioredis.from_url", return_value=redis_client),
        patch("src.agent.loop.openai.AsyncOpenAI", return_value=openai_client),
    ):
        await run_agent_loop(uuid.uuid4(), "2024-01-01", "2024-02-01", ["regime"])

    openai_client.chat.completions.create.assert_not_called()
    assert run.status == RunStatus.CANCELED
    phase_messages = [
        call.args[1]
        for call in redis_client.publish.await_args_list
        if json.loads(call.args[1]).get("type") == "phase"
    ]
    assert json.loads(phase_messages[-1])["phase"] == "canceled"


@pytest.mark.asyncio
async def test_run_agent_loop_preserves_canceled_status() -> None:
    run = MagicMock()
    run.status = RunStatus.RUNNING
    sessions = _SessionFactory(run)
    redis_client = AsyncMock()

    with (
        patch("src.agent.loop.AsyncSession", sessions),
        patch("src.agent.loop.aioredis.from_url", return_value=redis_client),
        patch("src.agent.loop.openai.AsyncOpenAI", side_effect=RunCanceled),
    ):
        await run_agent_loop(uuid.uuid4(), "2024-01-01", "2024-02-01", ["regime"])

    assert run.status == RunStatus.CANCELED


@pytest.mark.asyncio
async def test_run_agent_loop_marks_failed_when_openai_credentials_missing() -> None:
    run = MagicMock()
    sessions = _SessionFactory(run)
    redis_client = AsyncMock()

    with (
        patch("src.agent.loop.AsyncSession", sessions),
        patch("src.agent.loop.aioredis.from_url", return_value=redis_client),
        patch("src.agent.loop.openai.AsyncOpenAI", side_effect=RuntimeError("missing key")),
    ):
        await run_agent_loop(uuid.uuid4(), "2024-01-01", "2024-02-01", ["regime"])

    assert run.status == RunStatus.FAILED
    assert "missing key" in run.error
    redis_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_agent_loop_marks_failed_when_max_iterations_exhausted() -> None:
    run = MagicMock()
    sessions = _SessionFactory(run)
    redis_client = AsyncMock()
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(return_value=_tool_call_response())

    with (
        patch("src.agent.loop.AsyncSession", sessions),
        patch("src.agent.loop.aioredis.from_url", return_value=redis_client),
        patch("src.agent.loop.openai.AsyncOpenAI", return_value=openai_client),
    ):
        await run_agent_loop(uuid.uuid4(), "2024-01-01", "2024-02-01", ["regime"])

    assert openai_client.chat.completions.create.await_count == 10
    assert run.status == RunStatus.FAILED
    assert "max iterations" in run.error.lower()
    phase_messages = [
        call.args[1]
        for call in redis_client.publish.await_args_list
        if json.loads(call.args[1]).get("type") == "phase"
    ]
    phases = [json.loads(message)["phase"] for message in phase_messages]
    assert phases[0] == "starting"
    assert "explaining" in phases
    assert phases[-1] == "failed"


@pytest.mark.asyncio
async def test_run_agent_loop_publishes_tabpfn_estimate_and_progress() -> None:
    run = MagicMock()
    sessions = _SessionFactory(run)
    redis_client = AsyncMock()
    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        side_effect=[
            _tool_call_response("run_tabpfn"),
            SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content="done"),
                    )
                ],
            ),
        ]
    )

    with (
        patch("src.agent.loop.AsyncSession", sessions),
        patch("src.agent.loop.aioredis.from_url", return_value=redis_client),
        patch("src.agent.loop.openai.AsyncOpenAI", return_value=openai_client),
        patch("src.agent.loop.registry.dispatch", return_value={"task": "regime"}),
    ):
        await run_agent_loop(uuid.uuid4(), "2024-01-01", "2024-02-01", ["regime"])

    messages = [json.loads(call.args[1]) for call in redis_client.publish.await_args_list]
    assert any(message.get("type") == "tabpfn_estimate" for message in messages)
    progress = [message for message in messages if message.get("type") == "tabpfn_progress"]
    assert progress
    assert progress[-1]["tools_done"] == 1
