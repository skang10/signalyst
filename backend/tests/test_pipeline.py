import io
from unittest.mock import AsyncMock, patch

import pandas as pd


def _make_csv_bytes() -> bytes:
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    df = pd.DataFrame({"date": [str(d.date()) for d in dates], "CL=F": range(70, 170)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def _create_session(client) -> str:
    with patch("api.routes.sessions._run_data_pipeline_background", new_callable=AsyncMock):
        res = client.post(
            "/api/sessions",
            json={
                "market_profile": "oil",
                "timeframe_start": "2023-01-01",
                "timeframe_end": "2023-06-30",
            },
        )
    return res.json()["session_id"]


def test_upload_returns_202(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        res = client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "My WTI data"},
        )
    assert res.status_code == 202
    assert "artifact_id" in res.json()


def test_upload_transitions_session_to_user_review(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["stage"] == "user_review"


def test_proceed_from_user_review_returns_202(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        res = client.post(f"/api/sessions/{session_id}/proceed")
    assert res.status_code == 202


def test_proceed_from_wrong_stage_returns_409(client):
    session_id = _create_session(client)
    # Session is at CONFIGURING, not USER_REVIEW
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        res = client.post(f"/api/sessions/{session_id}/proceed")
    assert res.status_code == 409


def test_proceed_with_featurizer_config_patch_merges_into_session(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        res = client.post(
            f"/api/sessions/{session_id}/proceed",
            json={"featurizer_config_patch": {"windows": [5, 30, 90]}},
        )
    assert res.status_code == 202
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["featurizer_config"]["windows"] == [5, 30, 90]


def test_update_config_returns_200_and_merges_patch(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"featurizer_config_patch": {"windows": [7, 30, 90]}},
    )
    assert res.status_code == 200
    assert res.json() == {"session_id": session_id}
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["featurizer_config"]["windows"] == [7, 30, 90]


def test_update_config_outside_user_review_returns_409(client):
    session_id = _create_session(client)
    # Session is at CONFIGURING, not USER_REVIEW
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"featurizer_config_patch": {"windows": [7, 30, 90]}},
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "featurizer config can only be edited during user_review"


def test_update_config_timeframe_succeeds_at_configuring(client):
    session_id = _create_session(client)
    # Session is at CONFIGURING — timeframe patch should succeed (no stage gate)
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"timeframe_start": "2024-01-01", "timeframe_end": "2024-12-31"},
    )
    assert res.status_code == 200
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["timeframe_start"] == "2024-01-01"
    assert s["timeframe_end"] == "2024-12-31"


def test_update_config_pending_sources_succeeds(client):
    session_id = _create_session(client)
    sources = [{"connector_id": "yfinance", "params": {"tickers": ["CL=F"]}}]
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"pending_sources": sources},
    )
    assert res.status_code == 200
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["pending_sources"] == sources


def test_update_config_empty_patch_succeeds(client):
    session_id = _create_session(client)
    # All fields optional — empty patch is valid (no-op)
    res = client.patch(f"/api/sessions/{session_id}/config", json={})
    assert res.status_code == 200


def test_update_config_drops_unknown_patch_keys(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
    res = client.patch(
        f"/api/sessions/{session_id}/config",
        json={"featurizer_config_patch": {"rolling_windows_days": [1, 2, 3], "lags": [2, 10]}},
    )
    assert res.status_code == 200
    s = client.get(f"/api/sessions/{session_id}").json()
    assert "rolling_windows_days" not in s["featurizer_config"]
    assert s["featurizer_config"]["lags"] == [2, 10]


def test_cancel_running_session_returns_200(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()

    # Upload to get DataArtifact, then proceed to set RUNNING
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "test"},
        )
        client.post(f"/api/sessions/{session_id}/proceed")

    res = client.post(f"/api/sessions/{session_id}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "canceled"


def test_cancel_running_session_at_creation_returns_200(client):
    # Sessions now start RUNNING (pipeline background task launched immediately)
    session_id = _create_session(client)
    res = client.post(f"/api/sessions/{session_id}/cancel")
    assert res.status_code == 200


def test_rerun_invalid_stage_returns_422(client):
    session_id = _create_session(client)
    res = client.post(f"/api/sessions/{session_id}/rerun", json={"stage": "invalid_stage"})
    assert res.status_code == 422


def test_get_artifact_returns_data(client):
    session_id = _create_session(client)
    csv_bytes = _make_csv_bytes()
    with patch("api.routes.pipeline._run_featurizer_background", new_callable=AsyncMock):
        up_res = client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", csv_bytes, "text/csv")},
            data={"source_name": "My WTI data"},
        )
    artifact_id = up_res.json()["artifact_id"]

    ar_res = client.get(f"/api/sessions/{session_id}/artifacts/{artifact_id}")
    assert ar_res.status_code == 200
    body = ar_res.json()
    assert body["kind"] == "data"
    assert body["artifact_id"] == artifact_id
    assert "data_manifest" in body
    assert "series_preview" in body
    assert "CL=F" in body["series_preview"]


def test_get_artifact_not_found_returns_404(client):
    session_id = _create_session(client)
    res = client.get(f"/api/sessions/{session_id}/artifacts/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
