from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

from src.agent.tools import AgentContext
from src.agents.data_agent import make_data_agent
from src.db.models import DataArtifact, SessionStage, UploadedSource
from src.db.models import Session as SessionModel
from src.services.data_agent import _run


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


@pytest.mark.asyncio
async def test_run_merges_uploaded_source_with_fresh_connector_data() -> None:
    """An "upload" entry in pending_sources should re-attach its columns to the
    freshly-fetched connector data, surviving a connector-driven re-run."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    dates = pd.date_range("2023-01-01", periods=60, freq="D")
    uploaded_series = pd.Series(range(60), index=dates, dtype=float)

    async with AsyncSession(engine) as db:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2023, 1, 1),
            timeframe_end=date(2023, 6, 30),
            stage=SessionStage.DATA_GATHERING,
            pending_sources=[
                {"connector_id": "yfinance", "params": {"tickers": ["CL=F"]}},
                {"connector_id": "upload", "source_name": "my_upload", "columns": ["custom_col"]},
            ],
        )
        db.add(s)
        db.add(
            UploadedSource(
                session_id=s.id,
                source_name="my_upload",
                columns=["custom_col"],
                raw_data={
                    "custom_col": {
                        "index": [str(d.date()) for d in dates],
                        "data": [float(v) for v in uploaded_series],
                    }
                },
            )
        )
        await db.commit()
        await db.refresh(s)
        session_id = s.id

        fake_series = pd.Series(range(60), index=dates, name="CL=F", dtype=float)

        def fake_fetch(name: str, params: dict, context: AgentContext) -> dict:
            for ticker in params.get("tickers", []):
                context.signals[ticker] = fake_series
            return {
                "fetched": {t: len(fake_series) for t in params.get("tickers", [])},
                "skipped": [],
            }

        async def fake_run(*, context, publisher, initial_user_message=None):
            fake_fetch("yfinance", {"tickers": ["CL=F"]}, context)

        redis_mock = MagicMock()
        redis_mock.publish = AsyncMock()
        redis_mock.aclose = AsyncMock()

        with (
            patch("src.services.data_agent.aioredis.Redis.from_url", return_value=redis_mock),
            patch("src.services.data_agent.make_data_agent") as make_agent,
        ):
            make_agent.return_value.run = fake_run
            await _run(s, db)

        result = (
            (await db.execute(select(DataArtifact).where(DataArtifact.session_id == session_id)))
            .scalars()
            .first()
        )

    assert result is not None
    assert set(result.raw_data.keys()) == {"CL=F", "custom_col"}
    assert {src["connector_id"] for src in result.sources} == {"yfinance", "upload"}


@pytest.mark.asyncio
async def test_run_skips_agent_when_no_new_sources() -> None:
    """A chat-triggered refetch with no actual new tickers should not call the
    agent at all — the previous artifact's data is carried over as-is."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    dates = pd.date_range("2023-01-01", periods=60, freq="D")
    cl_series = pd.Series(range(60), index=dates, name="CL=F", dtype=float)

    async with AsyncSession(engine) as db:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2023, 1, 1),
            timeframe_end=date(2023, 6, 30),
            stage=SessionStage.DATA_GATHERING,
            pending_sources=[{"connector_id": "yfinance", "params": {"tickers": ["CL=F"]}}],
        )
        db.add(s)
        await db.commit()
        await db.refresh(s)
        session_id = s.id

        prev_artifact = DataArtifact(
            session_id=session_id,
            round=1,
            sources=[{"connector_id": "yfinance", "params": {"tickers": ["CL=F"]}}],
            data_manifest={"tickers": ["CL=F"], "rows": 60},
            raw_data={
                "CL=F": {
                    "index": [str(d.date()) for d in dates],
                    "data": [float(v) for v in cl_series],
                }
            },
            source_hash="old-hash",
        )
        db.add(prev_artifact)
        await db.commit()
        await db.refresh(s)

        redis_mock = MagicMock()
        redis_mock.publish = AsyncMock()
        redis_mock.aclose = AsyncMock()

        with (
            patch("src.services.data_agent.aioredis.Redis.from_url", return_value=redis_mock),
            patch("src.services.data_agent.make_data_agent") as make_agent,
        ):
            await _run(s, db)

        make_agent.assert_not_called()

        result = (
            (
                await db.execute(
                    select(DataArtifact)
                    .where(DataArtifact.session_id == session_id)
                    .order_by(DataArtifact.round.desc())  # type: ignore[attr-defined]
                )
            )
            .scalars()
            .first()
        )

    assert result is not None
    assert result.round == 2
    assert set(result.raw_data.keys()) == {"CL=F"}
    assert result.data_manifest["rows"] == 60


@pytest.mark.asyncio
async def test_run_diff_fetches_only_new_tickers() -> None:
    """A chat-triggered refetch that adds a new ticker should only ask the agent
    to fetch the new ticker, and merge it with the carried-over previous data."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    dates = pd.date_range("2023-01-01", periods=60, freq="D")
    cl_series = pd.Series(range(60), index=dates, name="CL=F", dtype=float)
    ng_series = pd.Series(range(60), index=dates, name="NG=F", dtype=float)

    async with AsyncSession(engine) as db:
        s = SessionModel(
            market_profile="oil",
            timeframe_start=date(2023, 1, 1),
            timeframe_end=date(2023, 6, 30),
            stage=SessionStage.DATA_GATHERING,
            pending_sources=[{"connector_id": "yfinance", "params": {"tickers": ["CL=F", "NG=F"]}}],
        )
        db.add(s)
        await db.commit()
        await db.refresh(s)
        session_id = s.id

        prev_artifact = DataArtifact(
            session_id=session_id,
            round=1,
            sources=[{"connector_id": "yfinance", "params": {"tickers": ["CL=F"]}}],
            data_manifest={"tickers": ["CL=F"], "rows": 60},
            raw_data={
                "CL=F": {
                    "index": [str(d.date()) for d in dates],
                    "data": [float(v) for v in cl_series],
                }
            },
            source_hash="old-hash",
        )
        db.add(prev_artifact)
        await db.commit()
        await db.refresh(s)

        captured_msg = {}

        async def fake_run(*, context, publisher, initial_user_message=None):
            captured_msg["msg"] = initial_user_message
            context.signals["NG=F"] = ng_series

        redis_mock = MagicMock()
        redis_mock.publish = AsyncMock()
        redis_mock.aclose = AsyncMock()

        with (
            patch("src.services.data_agent.aioredis.Redis.from_url", return_value=redis_mock),
            patch("src.services.data_agent.make_data_agent") as make_agent,
        ):
            make_agent.return_value.run = fake_run
            await _run(s, db)

        result = (
            (
                await db.execute(
                    select(DataArtifact)
                    .where(DataArtifact.session_id == session_id)
                    .order_by(DataArtifact.round.desc())  # type: ignore[attr-defined]
                )
            )
            .scalars()
            .first()
        )

    assert "NG=F" in captured_msg["msg"]
    assert "CL=F" not in captured_msg["msg"]
    assert result is not None
    assert set(result.raw_data.keys()) == {"CL=F", "NG=F"}
