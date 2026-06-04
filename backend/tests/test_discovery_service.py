"""
Tests for discovery and data agent services.

Service behavior is verified through the HTTP API (same pattern as test_pipeline.py).
Pure utility functions in the services are tested directly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pandas as pd


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
