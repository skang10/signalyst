"""
Tests for discovery and data agent services.

Service behavior is verified through the HTTP API (same pattern as test_pipeline.py).
Pure utility functions in the services are tested directly.
"""

from __future__ import annotations

from datetime import UTC
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest


def _create_session(client, **extra) -> str:
    with patch("api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock):
        res = client.post(
            "/api/sessions",
            json={
                "market_profile": "oil",
                "timeframe_start": "2023-01-01",
                "timeframe_end": "2023-06-30",
                **extra,
            },
        )
    return res.json()["session_id"]


def test_create_session_launches_discovery_background_task(client):
    with patch(
        "api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock
    ) as mock_bg:
        res = client.post(
            "/api/sessions",
            json={
                "market_profile": "oil",
                "timeframe_start": "2023-01-01",
                "timeframe_end": "2023-06-30",
            },
        )
    assert res.status_code == 202
    assert mock_bg.called


def test_created_session_status_is_running(client):
    session_id = _create_session(client)
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["status"] == "running"


def test_rerun_data_gathering_stage_is_accepted(client):
    session_id = _create_session(client)
    # status=RUNNING from creation; cancel first so rerun is available
    client.post(f"/api/sessions/{session_id}/cancel")

    with patch("api.routes.pipeline._run_data_agent_background", new_callable=AsyncMock):
        res = client.post(
            f"/api/sessions/{session_id}/rerun",
            json={"stage": "data_gathering"},
        )
    # 202 = accepted, not 422 (invalid stage)
    assert res.status_code == 202


def test_data_agent_service_manifest_helpers():
    """Verify _series_to_raw_data and _build_manifest produce correct shapes."""
    from src.services.data_agent import _build_manifest, _series_to_raw_data

    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    signals: dict = {"CL=F": pd.Series([70.0, 71.0, 72.0, 73.0, 74.0], index=dates)}

    raw = _series_to_raw_data(signals)
    assert "CL=F" in raw
    assert len(raw["CL=F"]["index"]) == 5
    assert raw["CL=F"]["data"][0] == 70.0

    manifest = _build_manifest(signals)
    assert manifest["tickers"] == ["CL=F"]
    assert manifest["rows"] == 5
    assert manifest["summary_stats"]["CL=F"]["mean"] == 72.0


def test_data_agent_service_manifest_empty_signals():
    from src.services.data_agent import _build_manifest

    manifest = _build_manifest({})
    assert manifest["tickers"] == []
    assert manifest["rows"] == 0


@pytest.mark.asyncio
async def test_finish_stage_preserves_pending_sources():
    """Regression: _finish_stage must not clear pending_sources (config page sync bug)."""
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession

    from src.db.models import Session as SessionModel
    from src.db.models import SessionStage, SessionStatus
    from src.services.data_agent import _finish_stage

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            from sqlmodel import SQLModel

            await conn.run_sync(SQLModel.metadata.create_all)

        async with AsyncSession(engine) as db:
            sources = [{"connector_id": "yfinance", "params": {"tickers": ["CL=F"]}}]
            s = SessionModel(
                market_profile="oil",
                timeframe_start=date(2023, 1, 1),
                timeframe_end=date(2023, 6, 30),
                stage=SessionStage.DATA_GATHERING.value,
                status=SessionStatus.RUNNING.value,
                pending_sources=sources,
            )
            db.add(s)
            await db.commit()
            await db.refresh(s)

            now = datetime.now(UTC).isoformat()
            artifact_event = {
                "event_id": "e1",
                "created_at": now,
                "type": "artifact_ready",
                "kind": "data",
                "artifact_id": "a1",
                "rows": 10,
                "tickers": ["CL=F"],
            }
            await _finish_stage(
                s,
                db,
                str(s.id),
                False,
                list(s.activity_events or []),
                list(s.stage_history or []),
                list(s.conversation or []),
                {"tickers": ["CL=F"], "rows": 10, "date_range": {}, "missing_pct": {}},
                artifact_event,
            )
            await db.commit()
            await db.refresh(s)

            assert s.pending_sources == sources
    finally:
        async with engine.begin() as conn:
            from sqlmodel import SQLModel

            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()
