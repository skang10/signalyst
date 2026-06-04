from __future__ import annotations

from typing import Any

import structlog

from src.agent.tools import AgentContext
from src.agents.base import BaseAgent
from src.data.registry import connector_registry

log = structlog.get_logger()

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
        log.info("data_agent.fetch", connector="yfinance", tickers=tickers)
        result = connector_registry.fetch("yfinance", {"tickers": tickers}, context)
        log.info("data_agent.fetch_done", connector="yfinance", result=result)
        return result

    def fetch_fred(series_ids: list[str], context: AgentContext | None = None) -> dict[str, Any]:
        """Fetch macro time series from FRED for the given series IDs."""
        if context is None:
            return {"error": "no context"}
        log.info("data_agent.fetch", connector="fred", series_ids=series_ids)
        result = connector_registry.fetch("fred", {"series_ids": series_ids}, context)
        log.info("data_agent.fetch_done", connector="fred", result=result)
        return result

    def fetch_eia(context: AgentContext | None = None) -> dict[str, Any]:
        """Fetch weekly EIA crude oil inventory change series."""
        if context is None:
            return {"error": "no context"}
        log.info("data_agent.fetch", connector="eia")
        result = connector_registry.fetch("eia", {}, context)
        log.info("data_agent.fetch_done", connector="eia", result=result)
        return result

    def fetch_gpr(context: AgentContext | None = None) -> dict[str, Any]:
        """Fetch daily Geopolitical Risk Index (GPR)."""
        if context is None:
            return {"error": "no context"}
        log.info("data_agent.fetch", connector="gpr")
        result = connector_registry.fetch("gpr", {}, context)
        log.info("data_agent.fetch_done", connector="gpr", result=result)
        return result

    def list_available_connectors(context: AgentContext | None = None) -> dict[str, Any]:
        """List available data connectors."""
        return connector_registry.list()

    def complete(summary: str = "", context: AgentContext | None = None) -> dict[str, Any]:
        """Signal that data gathering is complete."""
        n_signals = len(context.signals) if context else 0
        log.info("data_agent.complete_called", n_signals=n_signals, summary=summary)
        return {"n_signals": n_signals, "summary": summary}

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
