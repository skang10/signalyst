from __future__ import annotations

from typing import Any

from src.agent.tools import AgentContext
from src.agents.base import BaseAgent
from src.data.registry import connector_registry

_SYSTEM_PROMPT = """\
You are DataAgent. Your job is to fetch all approved data sources for the analysis session.

You will receive a list of approved sources. Fetch each one using the appropriate tool:
- fetch_yfinance: for yfinance sources (pass the tickers from params)
- fetch_fred: for fred sources (pass the series_ids from params)
- fetch_eia: for eia sources (no params needed)
- fetch_gpr: for gpr sources (no params needed)

When all sources have been fetched (or attempted), call complete(summary) to finish.
"""


def make_data_agent() -> BaseAgent:
    agent = BaseAgent(name="DataAgent", system_prompt=_SYSTEM_PROMPT)

    def fetch_yfinance(tickers: list[str], context: AgentContext | None = None) -> dict[str, Any]:
        """Fetch daily price series from Yahoo Finance for the given tickers."""
        if context is None:
            return {"error": "no context"}
        return connector_registry.fetch("yfinance", {"tickers": tickers}, context)

    def fetch_fred(series_ids: list[str], context: AgentContext | None = None) -> dict[str, Any]:
        """Fetch macro time series from FRED for the given series IDs."""
        if context is None:
            return {"error": "no context"}
        return connector_registry.fetch("fred", {"series_ids": series_ids}, context)

    def fetch_eia(context: AgentContext | None = None) -> dict[str, Any]:
        """Fetch weekly EIA crude oil inventory change series."""
        if context is None:
            return {"error": "no context"}
        return connector_registry.fetch("eia", {}, context)

    def fetch_gpr(context: AgentContext | None = None) -> dict[str, Any]:
        """Fetch daily Geopolitical Risk Index (GPR)."""
        if context is None:
            return {"error": "no context"}
        return connector_registry.fetch("gpr", {}, context)

    def list_available_connectors(context: AgentContext | None = None) -> dict[str, Any]:
        """List available data connectors."""
        return connector_registry.list()

    def complete(summary: str = "", context: AgentContext | None = None) -> dict[str, Any]:
        """Signal that data gathering is complete."""
        return {"n_signals": len(context.signals) if context else 0, "summary": summary}

    agent.register_tool(
        fetch_yfinance,
        {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "yfinance ticker symbols",
                }
            },
            "required": ["tickers"],
        },
    )
    agent.register_tool(
        fetch_fred,
        {
            "type": "object",
            "properties": {
                "series_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "FRED series IDs",
                }
            },
            "required": ["series_ids"],
        },
    )
    agent.register_tool(fetch_eia, {"type": "object", "properties": {}, "required": []})
    agent.register_tool(fetch_gpr, {"type": "object", "properties": {}, "required": []})
    agent.register_tool(
        list_available_connectors, {"type": "object", "properties": {}, "required": []}
    )
    agent.register_tool(
        complete,
        {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was fetched",
                }
            },
            "required": [],
        },
        is_stop=True,
    )

    return agent
