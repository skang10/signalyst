from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.discovery import DiscoveryContext, make_discovery_agent


def _tool_resp(name: str, args: dict, call_id: str = "c1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump.return_value = {"role": "assistant"}
    r = MagicMock()
    r.choices = [MagicMock(message=msg)]
    return r


def _mock_client(responses: list) -> MagicMock:
    idx = {"v": 0}

    async def create(**kwargs):  # type: ignore[return]
        resp = responses[min(idx["v"], len(responses) - 1)]
        idx["v"] += 1
        return resp

    c = MagicMock()
    c.chat.completions.create = create
    return c


@pytest.mark.asyncio
async def test_discovery_agent_writes_pending_sources() -> None:
    ctx = DiscoveryContext(
        market_profile="oil",
        timeframe_start="2023-01-01",
        timeframe_end="2023-06-30",
    )

    sources = [
        {"connector_id": "yfinance", "params": {"tickers": ["CL=F", "BZ=F"]}},
        {"connector_id": "fred", "params": {"series_ids": ["INDPRO"]}},
    ]

    events: list[dict] = []

    async def pub(e: dict) -> None:
        events.append(e)

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client([_tool_resp("approve_sources", {"sources": sources})])
        agent = make_discovery_agent()
        await agent.run(context=ctx, publisher=pub)

    assert ctx.pending_sources == sources


@pytest.mark.asyncio
async def test_discovery_agent_list_connectors_tool_returns_registry() -> None:
    ctx = DiscoveryContext(
        market_profile="oil",
        timeframe_start="2023-01-01",
        timeframe_end="2023-06-30",
    )

    captured: list[dict] = []

    async def pub(e: dict) -> None:
        if e["type"] == "tool_result" and e["tool"] == "list_available_connectors":
            captured.append(e["output"])

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client(
            [
                _tool_resp("list_available_connectors", {}, "c1"),
                _tool_resp("approve_sources", {"sources": []}, "c2"),
            ]
        )
        agent = make_discovery_agent()
        await agent.run(context=ctx, publisher=pub)

    assert len(captured) == 1
    assert "available" in captured[0]
