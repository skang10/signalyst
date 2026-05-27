from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class _ToolEntry:
    fn: Callable[..., Any]
    description: str
    parameters: dict[str, Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, _ToolEntry] = {}

    def tool(self, parameters: dict[str, Any]) -> Callable[..., Any]:
        """Decorator that registers a function in this registry."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[fn.__name__] = _ToolEntry(
                fn=fn,
                description=(fn.__doc__ or "").strip().splitlines()[0],
                parameters=parameters,
            )
            return fn

        return decorator

    def register(self, fn: Callable[..., Any], parameters: dict[str, Any]) -> None:
        self._tools[fn.__name__] = _ToolEntry(
            fn=fn,
            description=(fn.__doc__ or "").strip().splitlines()[0],
            parameters=parameters,
        )

    def schemas(self) -> list[dict[str, Any]]:
        """Return tool list in OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": entry.description,
                    "parameters": entry.parameters,
                },
            }
            for name, entry in self._tools.items()
        ]

    def dispatch(self, name: str, arguments: dict[str, Any], context: Any) -> Any:
        """Call the named tool with **arguments and context kwarg."""
        entry = self._tools[name]  # raises KeyError if not found
        return entry.fn(**arguments, context=context)


registry = ToolRegistry()
