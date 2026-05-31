from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal

import openai
import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent import tabpfn_progress as _tabpfn_progress
from src.agent.registry import registry
from src.agent.tools import AgentContext
from src.config import settings
from src.db.models import Run, RunStatus
from src.db.session import engine

log = structlog.get_logger()

_tabpfn_progress.install()

SYSTEM_PROMPT_BASE = (
    "You are an oil market intelligence analyst. You have access to tools "
    "to fetch market data, engineer features, run TabPFN classification, and explain "
    "predictions.\n\n"
)


def build_system_prompt(
    analysis_mode: Literal["quick", "full"] = "quick", tasks: list[str] | None = None
) -> str:
    tasks = tasks or []
    task_names = {task.lower() for task in tasks}
    explicit_backtest = bool({"backtest", "historical_validation"} & task_names)

    workflow = (
        "Given a date range and analysis tasks, use the tools in this order:\n"
        "1. list_data_sources — discover which data connectors are available and which are "
        "blocked (e.g. missing API key). Note any blocked sources in your reasoning.\n"
        "2. fetch_from_source — for each available connector relevant to the analysis, fetch "
        "the data. At minimum fetch price series (yfinance) and geopolitical risk (gpr). "
        "Fetch macro data (fred) and inventory data (eia) if available. "
        "For each blocked source, mention the gap in your thought.\n"
        "3. engineer_features — featurize with windows [5, 20, 60] and lags [1, 5, 20]\n"
        "4. detect_drift — check if recent feature distributions have shifted\n"
        "5. run_tabpfn with task='regime' — classify the current oil market regime\n"
        "6. run_tabpfn with task='direction' — predict WTI price direction over the next "
        "20 trading days\n"
    )

    if analysis_mode == "quick":
        if explicit_backtest:
            validation_instruction = (
                "7. evaluate_features with top_n=5 and max_samples=5 — compute lightweight SHAP "
                "feature importances from the latest regime test rows\n"
                "8. backtest with horizon=20, step=60, max_windows=3 — run lightweight historical "
                "validation because the tasks explicitly request it\n"
                "9. explain_prediction — pass the regime, direction, confidence, and top feature "
                "names from evaluate_features\n\n"
            )
        else:
            validation_instruction = (
                "7. evaluate_features with top_n=5 and max_samples=5 — compute lightweight SHAP "
                "feature importances from the latest regime test rows\n"
                "8. Do not call backtest in quick mode unless tasks explicitly include "
                "'backtest' or 'historical_validation'.\n"
                "9. explain_prediction — pass the regime, direction, confidence, and top feature "
                "names from evaluate_features\n\n"
            )
    else:
        validation_instruction = (
            "7. evaluate_features with top_n=10, max_samples=50, and n_repeats=3 — compute "
            "permutation feature importances (n_repeats×n_features+1 TabPFN calls) "
            "from the regime classifier\n"
            "8. backtest with horizon=20, step=20, max_windows=null — run full walk-forward "
            "regime accuracy + direction strategy Sharpe vs SPY\n"
            "9. explain_prediction — pass the regime, direction, confidence, and top feature "
            "names from evaluate_features\n\n"
        )

    return (
        SYSTEM_PROMPT_BASE
        + workflow
        + validation_instruction
        + "After calling explain_prediction, write a concise natural language summary "
        "(3-5 sentences) grounded in the actual confidence scores and feature values returned "
        "by the tools."
    )


SYSTEM_PROMPT = build_system_prompt("quick")

MAX_ITERATIONS = 10


class RunCanceled(Exception):
    """Raised when a run has been canceled cooperatively."""


TOOL_PHASES = {
    "list_data_sources": "discovering_data_sources",
    "fetch_from_source": "fetching_data",
    "engineer_features": "engineering_features",
    "detect_drift": "detecting_drift",
    "evaluate_features": "evaluating_features",
    "backtest": "backtesting",
    "explain_prediction": "explaining",
}


def estimate_tabpfn_calls(
    analysis_mode: Literal["quick", "full"], tasks: list[str]
) -> dict[str, Any]:
    task_names = {task.lower() for task in tasks}
    quick_backtest = analysis_mode == "quick" and bool(
        {"backtest", "historical_validation"} & task_names
    )
    known_calls = (
        2  # regime + direction (evaluate_features uses correlation in quick mode — 0 extra calls)
    )
    unknown_backtest = analysis_mode == "full"
    if quick_backtest:
        known_calls += 6  # max_windows=3, two TabPFN models per window
    return {
        "known_calls": known_calls,
        "unknown_backtest": unknown_backtest,
        "note": (
            "Full backtest call count depends on feature row count"
            if unknown_backtest
            else "Estimate includes configured TabPFN-backed tools"
        ),
    }


def phase_for_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "run_tabpfn":
        task = arguments.get("task")
        if task == "regime":
            return "predicting_regime"
        if task == "direction":
            return "predicting_direction"
    return TOOL_PHASES.get(name, "running_tool")


def format_result_context(
    result: dict[str, Any],
    date_range_start: str,
    date_range_end: str,
) -> str:
    """Format a Run.result dict as a readable LLM context message."""
    lines = [f"Previous analysis result ({date_range_start} to {date_range_end}):"]

    regime = result.get("regime")
    if isinstance(regime, dict):
        lines.append(
            f"Regime: {regime.get('regime')} (confidence {regime.get('confidence', 0):.2f})"
        )

    direction = result.get("direction")
    if isinstance(direction, dict):
        dir_conf = direction.get("confidence", 0)
        lines.append(f"Direction: {direction.get('direction')} (confidence {dir_conf:.2f})")

    drift = result.get("drift")
    if isinstance(drift, dict):
        detected = drift.get("drift_detected", False)
        psi = drift.get("psi_score", 0)
        features = drift.get("drifted_features") or []
        features_str = ", ".join(features) if features else "none"
        lines.append(
            f"Drift detected: {detected}, PSI score {psi:.2f}, drifted features: {features_str}"
        )

    fi = result.get("feature_importance")
    if isinstance(fi, dict):
        top = (fi.get("top_features") or [])[:3]
        if top:
            top_str = ", ".join(f"{f['name']} ({f['importance']:.2f})" for f in top)
            lines.append(f"Top features: {top_str}")

    summary = result.get("summary", "")
    if summary:
        lines.append(f"Summary: {summary}")

    return "\n".join(lines)


def tabpfn_calls_for_tool(name: str, arguments: dict[str, Any], result: dict[str, Any]) -> int:
    if name == "run_tabpfn":
        return 1
    if name == "evaluate_features":
        n_repeats = arguments.get("n_repeats", 0)
        if n_repeats == 0:
            return 0
        n_features = result.get("n_features_evaluated")
        if isinstance(n_features, int):
            return 1 + int(n_repeats) * n_features
        return 1
    if name == "backtest":
        max_windows = arguments.get("max_windows")
        n_windows = result.get("n_windows")
        if isinstance(n_windows, int):
            return n_windows * 2
        if isinstance(max_windows, int):
            return max_windows * 2
    return 0


async def _publish(redis_client: aioredis.Redis, channel: str, message: dict) -> None:  # type: ignore[type-arg]
    await redis_client.publish(channel, json.dumps(message, default=str))


async def _publish_phase(
    redis_client: aioredis.Redis,  # type: ignore[type-arg]
    channel: str,
    run_id: uuid.UUID,
    phase: str,
    tool: str | None = None,
) -> None:
    extra = {"tool": tool} if tool else {}
    log.info("agent.phase", run_id=str(run_id), phase=phase, **extra)
    await _publish(redis_client, channel, {"type": "phase", "phase": phase, "tool": tool})


async def _publish_tabpfn_progress(
    redis_client: aioredis.Redis,  # type: ignore[type-arg]
    channel: str,
    run_id: uuid.UUID,
    estimate: dict[str, Any],
    completed_calls: int,
    tool: str | None = None,
) -> None:
    payload = {
        "type": "tabpfn_progress",
        "tools_done": completed_calls,
        "tools_total": estimate["known_calls"],
        "variable_backtest": estimate["unknown_backtest"],
        "tool": tool,
    }
    log.info(
        "agent.tabpfn_progress",
        run_id=str(run_id),
        tools_done=completed_calls,
        tools_total=estimate["known_calls"],
        tool=tool,
    )
    await _publish(redis_client, channel, payload)


async def _raise_if_canceled(run_id: uuid.UUID) -> None:
    async with AsyncSession(engine) as session:
        run = await session.get(Run, run_id)
        if run is not None and run.status == RunStatus.CANCELED:
            raise RunCanceled


async def run_agent_loop(
    run_id: uuid.UUID,
    date_range_start: str,
    date_range_end: str,
    tasks: list[str],
    analysis_mode: Literal["quick", "full"] = "quick",
    pre_messages: list[str] | None = None,
) -> None:
    """Drive the ReAct loop for one analysis run.

    Accepts primitive fields (not AnalyzeRequest) to avoid a circular import
    between src.agent.loop and api.routes.analyze.

    Creates its own DB session and Redis connection — must not reuse the
    HTTP request's session, which is closed once the response is sent.
    """
    redis_client: aioredis.Redis = aioredis.from_url(settings.redis_url)  # type: ignore[type-arg]
    channel = f"run:{run_id}"
    _tabpfn_progress.register_run(str(run_id))

    try:
        await _raise_if_canceled(run_id)
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is None:
                return
            run.status = RunStatus.RUNNING
            await session.commit()

        openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        context = AgentContext(
            date_range_start=date_range_start,
            date_range_end=date_range_end,
        )

        messages: list[dict] = [  # type: ignore[type-arg]
            {"role": "system", "content": build_system_prompt(analysis_mode, tasks)},
        ]
        for pre_msg in pre_messages or []:
            messages.append({"role": "user", "content": pre_msg})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Analyze {date_range_start} to {date_range_end}. "
                    f"Tasks: {tasks}. Analysis mode: {analysis_mode}."
                ),
            }
        )

        log.info(
            "agent.loop.start",
            run_id=str(run_id),
            model=settings.agent_model,
            date_range=f"{date_range_start}/{date_range_end}",
            tasks=tasks,
            mode=analysis_mode,
        )
        await _publish_phase(redis_client, channel, run_id, "starting")
        tabpfn_estimate = estimate_tabpfn_calls(analysis_mode, tasks)
        tabpfn_completed_calls = 0
        await _publish(
            redis_client,
            channel,
            {"type": "tabpfn_estimate", **tabpfn_estimate},
        )
        last_text = ""
        total_input_tokens = 0
        total_output_tokens = 0
        for _ in range(MAX_ITERATIONS):
            await _raise_if_canceled(run_id)
            response = await openai_client.chat.completions.create(
                model=settings.agent_model,
                tools=registry.schemas(),  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )
            if response.usage:
                total_input_tokens += response.usage.prompt_tokens
                total_output_tokens += response.usage.completion_tokens
            choice = response.choices[0]

            if choice.message.content:
                last_text = choice.message.content
                await _publish(redis_client, channel, {"type": "thought", "content": last_text})

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                assistant_msg: dict = {  # type: ignore[type-arg]
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,  # type: ignore[union-attr]
                                "arguments": tc.function.arguments,  # type: ignore[union-attr]
                            },
                        }
                        for tc in choice.message.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                for tc in choice.message.tool_calls:
                    name = tc.function.name  # type: ignore[union-attr]
                    arguments = json.loads(tc.function.arguments)  # type: ignore[union-attr]
                    await _raise_if_canceled(run_id)
                    await _publish_phase(
                        redis_client,
                        channel,
                        run_id,
                        phase_for_tool(name, arguments),
                        tool=name,
                    )
                    await _publish(
                        redis_client,
                        channel,
                        {"type": "tool_call", "tool": name, "input": arguments},
                    )
                    _log_keys = ("task", "horizon", "top_n")
                    _extra = {k: v for k, v in arguments.items() if k in _log_keys}
                    log.info("agent.tool.start", run_id=str(run_id), tool=name, **_extra)
                    _t0 = perf_counter()
                    if tabpfn_calls_for_tool(name, arguments, {}) > 0:
                        _pred_total: int | None = None
                        if name == "evaluate_features" and context._regime_X_test is not None:
                            _n_repeats = arguments.get("n_repeats", 0)
                            if _n_repeats > 0:
                                _pred_total = 1 + _n_repeats * context._regime_X_test.shape[1]
                        _tabpfn_progress.set_callback(
                            _tabpfn_progress.make_callback(
                                asyncio.get_running_loop(),
                                redis_client,
                                channel,
                                str(run_id),
                                name,
                                task=arguments.get("task"),
                                total=_pred_total,
                            )
                        )
                    try:
                        result = await asyncio.to_thread(
                            registry.dispatch, name, arguments, context
                        )
                    except _tabpfn_progress.RunCanceledInThread:
                        raise RunCanceled
                    finally:
                        _tabpfn_progress.set_callback(None)
                    _ms = round((perf_counter() - _t0) * 1000)
                    log.info("agent.tool.done", run_id=str(run_id), tool=name, duration_ms=_ms)
                    await _raise_if_canceled(run_id)
                    completed_for_tool = tabpfn_calls_for_tool(name, arguments, result)
                    tabpfn_completed_calls += completed_for_tool
                    if completed_for_tool:
                        await _publish_tabpfn_progress(
                            redis_client,
                            channel,
                            run_id,
                            tabpfn_estimate,
                            tabpfn_completed_calls,
                            tool=name,
                        )
                    await _publish(
                        redis_client,
                        channel,
                        {"type": "tool_result", "tool": name, "output": result},
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
            else:
                break
        else:
            raise RuntimeError(f"Agent loop exceeded max iterations ({MAX_ITERATIONS})")

        estimated_cost = (
            total_input_tokens / 1000 * settings.agent_model_input_cost_per_1k
            + total_output_tokens / 1000 * settings.agent_model_output_cost_per_1k
        )
        usage = {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
        }

        log.info("agent.loop.done", run_id=str(run_id), model=settings.agent_model, **usage)
        await _publish_phase(redis_client, channel, run_id, "completed")
        await _publish(
            redis_client,
            channel,
            {"type": "done", "summary": last_text, "usage": usage},
        )

        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.COMPLETED
                run.completed_at = datetime.now(UTC).replace(tzinfo=None)
                run.result = {
                    "regime": context.regime_result,
                    "direction": context.direction_result,
                    "drift": context.drift_result,
                    "feature_importance": context.shap_result,
                    "backtest": context.backtest_result,
                    "summary": last_text,
                    "usage": usage,
                    "data_manifest": context.data_manifest,
                }
                await session.commit()

    except RunCanceled:
        await _publish_phase(redis_client, channel, run_id, "canceled")
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.CANCELED
                run.completed_at = datetime.now(UTC).replace(tzinfo=None)
                run.error = run.error or "Canceled by user"
                await session.commit()

    except Exception as exc:
        log.error("agent.loop.error", run_id=str(run_id), error=str(exc), exc_info=True)
        await _publish_phase(redis_client, channel, run_id, "failed")
        await _publish(redis_client, channel, {"type": "error", "message": str(exc)})
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.FAILED
                run.error = str(exc)
                await session.commit()

    finally:
        _tabpfn_progress.unregister_run(str(run_id))
        await redis_client.aclose()  # type: ignore[attr-defined]


async def run_agent_continuation(
    run_id: uuid.UUID,
    messages: list[dict],  # type: ignore[type-arg]
    date_range_start: str,
    date_range_end: str,
) -> None:
    """Drive the ReAct loop for a post-run continuation.

    Takes a pre-built messages list [system, result_context, user_message].
    Creates its own DB session and Redis connection.
    """
    redis_client: aioredis.Redis = aioredis.from_url(settings.redis_url)  # type: ignore[type-arg]
    channel = f"run:{run_id}"
    _tabpfn_progress.register_run(str(run_id))

    try:
        await _raise_if_canceled(run_id)
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is None:
                return
            run.status = RunStatus.RUNNING
            await session.commit()

        openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        context = AgentContext(
            date_range_start=date_range_start,
            date_range_end=date_range_end,
        )

        log.info("agent.continuation.start", run_id=str(run_id), model=settings.agent_model)
        await _publish_phase(redis_client, channel, run_id, "starting")

        last_text = ""
        total_input_tokens = 0
        total_output_tokens = 0

        for _ in range(MAX_ITERATIONS):
            await _raise_if_canceled(run_id)
            response = await openai_client.chat.completions.create(
                model=settings.agent_model,
                tools=registry.schemas(),  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )
            if response.usage:
                total_input_tokens += response.usage.prompt_tokens
                total_output_tokens += response.usage.completion_tokens
            choice = response.choices[0]

            if choice.message.content:
                last_text = choice.message.content
                await _publish(redis_client, channel, {"type": "thought", "content": last_text})

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                assistant_msg: dict = {  # type: ignore[type-arg]
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,  # type: ignore[union-attr]
                                "arguments": tc.function.arguments,  # type: ignore[union-attr]
                            },
                        }
                        for tc in choice.message.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                for tc in choice.message.tool_calls:
                    name = tc.function.name  # type: ignore[union-attr]
                    arguments = json.loads(tc.function.arguments)  # type: ignore[union-attr]
                    await _raise_if_canceled(run_id)
                    await _publish_phase(
                        redis_client, channel, run_id, phase_for_tool(name, arguments), tool=name
                    )
                    await _publish(
                        redis_client,
                        channel,
                        {"type": "tool_call", "tool": name, "input": arguments},
                    )
                    log.info("agent.tool.start", run_id=str(run_id), tool=name)
                    _t0 = perf_counter()
                    try:
                        result = await asyncio.to_thread(
                            registry.dispatch, name, arguments, context
                        )
                    except _tabpfn_progress.RunCanceledInThread:
                        raise RunCanceled
                    finally:
                        _tabpfn_progress.set_callback(None)
                    _ms = round((perf_counter() - _t0) * 1000)
                    log.info("agent.tool.done", run_id=str(run_id), tool=name, duration_ms=_ms)
                    await _raise_if_canceled(run_id)
                    await _publish(
                        redis_client,
                        channel,
                        {"type": "tool_result", "tool": name, "output": result},
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
            else:
                break
        else:
            raise RuntimeError(f"Agent loop exceeded max iterations ({MAX_ITERATIONS})")

        estimated_cost = (
            total_input_tokens / 1000 * settings.agent_model_input_cost_per_1k
            + total_output_tokens / 1000 * settings.agent_model_output_cost_per_1k
        )
        usage = {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
        }

        log.info("agent.continuation.done", run_id=str(run_id), model=settings.agent_model, **usage)

        # Commit to DB before publishing done — frontend calls api.getRun immediately
        # on receiving the done event, so the result must already be persisted.
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.COMPLETED
                run.completed_at = datetime.now(UTC).replace(tzinfo=None)
                run.result = {
                    "regime": context.regime_result,
                    "direction": context.direction_result,
                    "drift": context.drift_result,
                    "feature_importance": context.shap_result,
                    "backtest": context.backtest_result,
                    "summary": last_text,
                    "usage": usage,
                    "data_manifest": context.data_manifest,
                }
                await session.commit()

        await _publish_phase(redis_client, channel, run_id, "completed")
        await _publish(
            redis_client, channel, {"type": "done", "summary": last_text, "usage": usage}
        )

    except RunCanceled:
        await _publish_phase(redis_client, channel, run_id, "canceled")
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.CANCELED
                run.completed_at = datetime.now(UTC).replace(tzinfo=None)
                run.error = run.error or "Canceled by user"
                await session.commit()

    except Exception as exc:
        log.error("agent.continuation.error", run_id=str(run_id), error=str(exc), exc_info=True)
        await _publish_phase(redis_client, channel, run_id, "failed")
        await _publish(redis_client, channel, {"type": "error", "message": str(exc)})
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.FAILED
                run.error = str(exc)
                await session.commit()

    finally:
        _tabpfn_progress.unregister_run(str(run_id))
        await redis_client.aclose()  # type: ignore[attr-defined]
