import io
from unittest.mock import AsyncMock, patch

import pandas as pd


def _make_csv(dates, col="CL=F") -> bytes:
    df = pd.DataFrame({"date": [str(d.date()) for d in dates], col: range(len(dates))})
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


def test_upload_no_date_column_returns_422(client):
    session_id = _create_session(client)
    df = pd.DataFrame({"CL=F": range(80)})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode()
    res = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        data={"source_name": "test"},
    )
    assert res.status_code == 422
    assert "date" in res.json()["detail"].lower()


def test_upload_too_few_rows_returns_422(client):
    session_id = _create_session(client)
    dates = pd.date_range("2023-01-01", periods=20, freq="D")
    csv_bytes = _make_csv(dates)
    res = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        data={"source_name": "test"},
    )
    assert res.status_code == 422
    assert "rows" in res.json()["detail"].lower()


def test_upload_date_range_mismatch_warns_in_manifest(client):
    session_id = _create_session(client)
    # Session timeframe: 2023-01-01 → 2023-06-30; upload: 2020-01-01 → 2020-06-30
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    csv_bytes = _make_csv(dates)
    res = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        data={"source_name": "test"},
    )
    assert res.status_code == 202
    artifact_id = res.json()["artifact_id"]
    detail = client.get(f"/api/sessions/{session_id}/artifacts/{artifact_id}").json()
    warnings = detail["data_manifest"].get("warnings")
    assert warnings is not None
    assert any("overlap" in w.lower() for w in warnings)


def test_upload_no_wti_column_warns_in_manifest(client):
    session_id = _create_session(client)
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    csv_bytes = _make_csv(dates, col="custom_price")
    res = client.post(
        f"/api/sessions/{session_id}/upload",
        files={"file": ("data.csv", csv_bytes, "text/csv")},
        data={"source_name": "test"},
    )
    assert res.status_code == 202
    artifact_id = res.json()["artifact_id"]
    detail = client.get(f"/api/sessions/{session_id}/artifacts/{artifact_id}").json()
    warnings = detail["data_manifest"].get("warnings")
    assert warnings is not None
    assert any("wti" in w.lower() for w in warnings)
