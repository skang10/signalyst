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


def test_get_analysis_artifact_returns_analysis_result_detail(client):
    import asyncio
    import uuid

    from src.db.models import AnalysisResult

    session_id = _create_session(client)
    artifact_id = uuid.uuid4()

    async def _seed() -> None:
        from api.main import app
        from src.db.session import get_session

        override = app.dependency_overrides[get_session]
        agen = override()
        db = await agen.__anext__()
        try:
            db.add(
                AnalysisResult(
                    id=artifact_id,
                    session_id=uuid.UUID(session_id),
                    feature_artifact_id=uuid.uuid4(),
                    regime={
                        "regime": "bull_supercycle",
                        "confidence": 0.8,
                        "distribution": {"bull_supercycle": 10},
                    },
                    direction={
                        "direction": "up",
                        "confidence": 0.7,
                        "distribution": {"up": 8, "down": 2},
                    },
                    feature_importance={
                        "top_features": [{"name": "CL=F_ret_5", "importance": 0.42}],
                        "n_features_evaluated": 12,
                        "n_samples_explained": 20,
                    },
                    drift={"psi_score": 0.05, "drift_detected": False},
                    backtest={
                        "strategy_sharpe": 1.2,
                        "benchmark_sharpe": 0.8,
                        "regime_accuracy": 0.65,
                        "n_windows": 5,
                    },
                    summary="Markets are in a bull supercycle.",
                )
            )
            await db.commit()
        finally:
            await agen.aclose()

    asyncio.run(_seed())

    res = client.get(f"/api/sessions/{session_id}/analysis/{artifact_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "analysis"
    assert body["artifact_id"] == str(artifact_id)
    assert body["regime"]["regime"] == "bull_supercycle"
    assert body["direction"]["direction"] == "up"
    assert body["feature_importance"]["top_features"][0]["name"] == "CL=F_ret_5"
    assert body["drift"]["psi_score"] == 0.05
    assert body["backtest"]["strategy_sharpe"] == 1.2
    assert body["summary"] == "Markets are in a bull supercycle."
    assert body["cache_hit"] is False
    assert body["cached_from_session_id"] is None


def test_get_analysis_artifact_not_found_returns_404(client):
    session_id = _create_session(client)
    res = client.get(f"/api/sessions/{session_id}/analysis/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_get_analysis_artifact_wrong_session_returns_404(client):
    import asyncio
    import uuid
    from datetime import date

    from src.db.models import AnalysisResult, SessionStage, SessionStatus
    from src.db.models import Session as SessionModel

    session_id = _create_session(client)
    other_session_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    async def _seed() -> None:
        from api.main import app
        from src.db.session import get_session

        override = app.dependency_overrides[get_session]
        agen = override()
        db = await agen.__anext__()
        try:
            db.add(
                SessionModel(
                    id=other_session_id,
                    market_profile="oil",
                    timeframe_start=date(2023, 1, 1),
                    timeframe_end=date(2023, 6, 30),
                    stage=SessionStage.FOLLOW_UP.value,
                    status=SessionStatus.WAITING.value,
                    conversation=[],
                )
            )
            db.add(
                AnalysisResult(
                    id=artifact_id,
                    session_id=other_session_id,
                    feature_artifact_id=uuid.uuid4(),
                )
            )
            await db.commit()
        finally:
            await agen.aclose()

    asyncio.run(_seed())

    res = client.get(f"/api/sessions/{session_id}/analysis/{artifact_id}")
    assert res.status_code == 404
