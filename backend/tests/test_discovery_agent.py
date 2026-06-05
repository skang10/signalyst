from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel

from src.agents.discovery import DiscoveryContext, make_discovery_agent
from src.db.models import Session, SessionStage, SessionStatus
from src.db.seed import seed_profiles
from src.services.discovery import _run


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


@pytest.mark.asyncio
async def test_discovery_service_uses_profile_defaults_when_agent_approves_fewer() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    class DummyRedis:
        async def publish(self, channel: str, message: str) -> None:
            pass

        async def aclose(self) -> None:
            pass

    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as db:
            await seed_profiles(db)
            s = Session(
                market_profile="oil",
                timeframe_start=date(2023, 1, 1),
                timeframe_end=date(2023, 6, 30),
                stage=SessionStage.CONFIGURING.value,
                status=SessionStatus.RUNNING.value,
            )
            db.add(s)
            await db.commit()
            await db.refresh(s)

            with patch("src.services.discovery.make_discovery_agent") as mock_agent:
                with patch(
                    "src.services.discovery.aioredis.Redis.from_url", return_value=DummyRedis()
                ):
                    await _run(s, db)

            mock_agent.assert_not_called()

            await db.refresh(s)
            assert s.pending_sources == [
                {"connector_id": "yfinance", "params": {"tickers": ["CL=F", "BZ=F", "DX-Y.NYB"]}},
                {"connector_id": "fred", "params": {"series_ids": ["INDPRO"]}},
                {"connector_id": "eia", "params": {}},
                {"connector_id": "gpr", "params": {}},
            ]
            assert s.conversation[-1]["content"] == "Recommended 4 data sources."
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()


@pytest.mark.asyncio
async def test_discovery_service_falls_back_to_agent_when_profile_has_no_defaults() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    class DummyRedis:
        async def publish(self, channel: str, message: str) -> None:
            pass

        async def aclose(self) -> None:
            pass

    class AgentApprovingSources:
        async def run(self, context: DiscoveryContext, publisher) -> None:  # type: ignore[no-untyped-def]
            context.pending_sources = [{"connector_id": "custom", "params": {"symbol": "ABC"}}]

    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as db:
            s = Session(
                market_profile="custom",
                timeframe_start=date(2023, 1, 1),
                timeframe_end=date(2023, 6, 30),
                stage=SessionStage.CONFIGURING.value,
                status=SessionStatus.RUNNING.value,
            )
            db.add(s)
            await db.commit()
            await db.refresh(s)

            with (
                patch(
                    "src.services.discovery.make_discovery_agent",
                    return_value=AgentApprovingSources(),
                ) as mock_agent,
                patch("src.services.discovery.aioredis.Redis.from_url", return_value=DummyRedis()),
            ):
                await _run(s, db)

            mock_agent.assert_called_once()
            await db.refresh(s)
            assert s.pending_sources == [{"connector_id": "custom", "params": {"symbol": "ABC"}}]
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()
