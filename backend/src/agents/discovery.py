from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from src.agents.base import BaseAgent
from src.data.registry import connector_registry

_SYSTEM_PROMPT = """\
You are DataSourceDiscoveryAgent. Recommend the best data sources for a market analysis session.

Steps:
1. Call list_available_connectors() to see what's built-in.
2. Select the most relevant sources for the given market profile.
3. For oil markets: recommend WTI + Brent + DXY via yfinance, INDPRO via fred, eia (no params),\
 gpr (no params).
4. Call approve_sources(sources) to finalise. Each source: {"connector_id": "...", "params": {...}}.

Only call approve_sources() — never end without it.
"""


@dataclass
class DiscoveryContext:
    market_profile: str
    timeframe_start: str
    timeframe_end: str
    pending_sources: list[dict[str, Any]] = field(default_factory=list)


def make_discovery_agent() -> BaseAgent:
    agent = BaseAgent(name="DataSourceDiscoveryAgent", system_prompt=_SYSTEM_PROMPT)

    def list_available_connectors(context: DiscoveryContext | None = None) -> dict[str, Any]:
        """List all built-in connectors and their availability."""
        return connector_registry.list()

    def approve_sources(
        sources: list[dict[str, Any]], context: DiscoveryContext | None = None
    ) -> dict[str, Any]:
        """Approve the recommended data sources and hand off to DataAgent."""
        if context is not None:
            context.pending_sources = list(sources)
        return {"approved": len(sources), "sources": sources}

    def http_get(
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        context: DiscoveryContext | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP GET request to explore an external data API."""
        try:
            r = httpx.get(url, headers=headers or {}, params=params or {}, timeout=10)
            return {"status_code": r.status_code, "body": r.text[:2000]}
        except Exception as exc:
            return {"error": str(exc)}

    agent.register_tool(
        list_available_connectors,
        {"type": "object", "properties": {}, "required": []},
    )
    agent.register_tool(
        approve_sources,
        {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "connector_id": {"type": "string"},
                            "params": {"type": "object"},
                        },
                        "required": ["connector_id", "params"],
                    },
                }
            },
            "required": ["sources"],
        },
        is_stop=True,
    )
    agent.register_tool(
        http_get,
        {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "headers": {"type": "object"},
                "params": {"type": "object"},
            },
            "required": ["url"],
        },
    )

    return agent
