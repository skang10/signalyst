from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import openai

from src.config import settings

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
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        if initial_user_message:
            messages.append({"role": "user", "content": initial_user_message})

        schemas = self._schemas()

        for _ in range(self.max_iterations):
            kwargs: dict[str, Any] = {"model": settings.agent_model, "messages": messages}
            if schemas:
                kwargs["tools"] = schemas

            resp = await client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message

            if msg.content:
                await publisher({"type": "thought", "agent": self.name, "content": msg.content})

            if not msg.tool_calls:
                return msg.content or ""

            messages.append(msg.model_dump(exclude_unset=True))

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                args = json.loads(tc.function.arguments)

                await publisher(
                    {"type": "tool_call", "agent": self.name, "tool": fn_name, "input": args}
                )

                entry = self._tools.get(fn_name)
                if entry is None:
                    result: Any = {"error": f"unknown tool: {fn_name}"}
                else:
                    try:
                        result = entry.fn(**args, context=context)
                    except Exception as exc:
                        result = {"error": str(exc)}

                await publisher(
                    {"type": "tool_result", "agent": self.name, "tool": fn_name, "output": result}
                )

                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)}
                )

                if entry is not None and entry.is_stop:
                    return json.dumps(result)

        return "max_iterations_reached"
