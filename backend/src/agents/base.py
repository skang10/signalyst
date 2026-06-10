from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import openai
import structlog

from src.config import settings

log = structlog.get_logger()

Publisher = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class _ToolEntry:
    fn: Callable[..., Any]
    schema: dict[str, Any]
    is_stop: bool = False


class BaseAgent:
    def __init__(self, name: str, system_prompt: str, max_iterations: int = 10) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self._tools: dict[str, _ToolEntry] = {}

    def register_tool(
        self, fn: Callable[..., Any], schema: dict[str, Any], is_stop: bool = False
    ) -> None:
        self._tools[fn.__name__] = _ToolEntry(fn=fn, schema=schema, is_stop=is_stop)

    def _schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": (entry.fn.__doc__ or "").strip().splitlines()[0],
                    "parameters": entry.schema,
                },
            }
            for name, entry in self._tools.items()
        ]

    async def run(
        self,
        context: Any,
        publisher: Publisher,
        initial_user_message: str = "",
    ) -> str:
        client = openai.AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=60.0,  # fail fast — hanging forever means a stuck session
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        if initial_user_message:
            messages.append({"role": "user", "content": initial_user_message})

        schemas = self._schemas()
        agent_log = log.bind(agent=self.name)
        agent_log.info("agent.started", model=settings.agent_model, tools=list(self._tools))
        _run_start = time.monotonic()

        for iteration in range(self.max_iterations):
            kwargs: dict[str, Any] = {"model": settings.agent_model, "messages": messages}
            if schemas:
                kwargs["tools"] = schemas

            agent_log.info("agent.llm_call", iteration=iteration, model=settings.agent_model)
            _llm_start = time.monotonic()
            resp = await client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            agent_log.info(
                "agent.llm_call_done",
                iteration=iteration,
                duration_ms=round((time.monotonic() - _llm_start) * 1000, 2),
                usage=resp.usage.model_dump() if resp.usage else None,
            )

            if msg.content:
                agent_log.debug("agent.thought", content=msg.content[:120])
                await publisher({"type": "thought", "agent": self.name, "content": msg.content})

            if not msg.tool_calls:
                agent_log.info(
                    "agent.finished",
                    iterations=iteration + 1,
                    reason="no_tool_calls",
                    duration_ms=round((time.monotonic() - _run_start) * 1000, 2),
                )
                return msg.content or ""

            messages.append(msg.model_dump(exclude_unset=True))

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                args = json.loads(tc.function.arguments)

                agent_log.debug("agent.tool_call", tool=fn_name)
                await publisher(
                    {"type": "tool_call", "agent": self.name, "tool": fn_name, "input": args}
                )

                entry = self._tools.get(fn_name)
                if entry is None:
                    result: Any = {"error": f"unknown tool: {fn_name}"}
                    agent_log.warning("agent.unknown_tool", tool=fn_name)
                else:
                    try:
                        result = entry.fn(**args, context=context)
                    except Exception as exc:
                        result = {"error": str(exc)}
                        agent_log.warning("agent.tool_error", tool=fn_name, error=str(exc))

                await publisher(
                    {"type": "tool_result", "agent": self.name, "tool": fn_name, "output": result}
                )

                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)}
                )

                if entry is not None and entry.is_stop:
                    agent_log.info(
                        "agent.finished",
                        iterations=iteration + 1,
                        reason="stop_tool",
                        tool=fn_name,
                        duration_ms=round((time.monotonic() - _run_start) * 1000, 2),
                    )
                    return json.dumps(result)

        agent_log.warning(
            "agent.max_iterations_reached",
            max=self.max_iterations,
            duration_ms=round((time.monotonic() - _run_start) * 1000, 2),
        )
        return "max_iterations_reached"
