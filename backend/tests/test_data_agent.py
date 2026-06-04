from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.agent.tools import AgentContext
from src.agents.data_agent import make_data_agent


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
async def test_data_agent_fetch_yfinance_populates_signals() -> None:
    ctx = AgentContext(date_range_start="2023-01-01", date_range_end="2023-06-30")
    dates = pd.date_range("2023-01-01", periods=60, freq="D")
    fake_series = pd.Series(range(60), index=dates, name="CL=F", dtype=float)

    async def pub(e: dict) -> None:
        pass

    def fake_fetch(name: str, params: dict, context: AgentContext) -> dict:
        for ticker in params.get("tickers", []):
            context.signals[ticker] = fake_series
        return {"fetched": {t: len(fake_series) for t in params.get("tickers", [])}, "skipped": []}

    with (
        patch("src.agents.base.openai.AsyncOpenAI") as cls,
        patch("src.agents.data_agent.connector_registry.fetch", side_effect=fake_fetch),
    ):
        cls.return_value = _mock_client(
            [
                _tool_resp("fetch_yfinance", {"tickers": ["CL=F"]}, "c1"),
                _tool_resp("complete", {"summary": "done"}, "c2"),
            ]
        )
        agent = make_data_agent()
        await agent.run(context=ctx, publisher=pub)

    assert "CL=F" in ctx.signals
    assert len(ctx.signals["CL=F"]) == 60


@pytest.mark.asyncio
async def test_data_agent_complete_stops_loop() -> None:
    ctx = AgentContext(date_range_start="2023-01-01", date_range_end="2023-06-30")

    call_count = {"n": 0}

    async def pub(e: dict) -> None:
        if e["type"] == "tool_call":
            call_count["n"] += 1

    with patch("src.agents.base.openai.AsyncOpenAI") as cls:
        cls.return_value = _mock_client(
            [
                _tool_resp("complete", {"summary": "done"}, "c1"),
                _tool_resp("complete", {"summary": "should not run"}, "c2"),
            ]
        )
        agent = make_data_agent()
        await agent.run(context=ctx, publisher=pub)

    assert call_count["n"] == 1
