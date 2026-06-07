from unittest.mock import AsyncMock, patch

_BG = "api.routes.sessions._run_data_pipeline_background"


def _create(client, **extra):
    with patch(_BG, new_callable=AsyncMock):
        return client.post(
            "/api/sessions",
            json={
                "market_profile": "oil",
                "timeframe_start": "2024-01-01",
                "timeframe_end": "2024-06-30",
                **extra,
            },
        )


def test_create_session_returns_202(client):
    res = _create(client)
    assert res.status_code == 202
    assert "session_id" in res.json()


def test_create_session_seeds_featurizer_config_from_profile_defaults(client):
    res = _create(client)
    session_id = res.json()["session_id"]
    s = client.get(f"/api/sessions/{session_id}").json()
    assert s["featurizer_config"] == {
        "windows": [5, 20, 60],
        "lags": [1, 5, 20],
        "feature_families": ["rolling_stats", "momentum", "regime", "lag"],
        "energy_specific": True,
    }


def test_create_session_missing_fields_returns_422(client):
    res = client.post("/api/sessions", json={})
    assert res.status_code == 422


def test_list_sessions_returns_list(client):
    res = client.get("/api/sessions")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_session_not_found_returns_404(client):
    res = client.get("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


def test_get_session_invalid_uuid_returns_422(client):
    res = client.get("/api/sessions/not-a-uuid")
    assert res.status_code == 422


def test_get_session_roundtrip(client):
    create_res = _create(client, auto=True)
    session_id = create_res.json()["session_id"]

    get_res = client.get(f"/api/sessions/{session_id}")
    assert get_res.status_code == 200
    body = get_res.json()
    assert body["session_id"] == session_id
    assert body["market_profile"] == "oil"
    assert body["stage"] == "configuring"
    assert body["status"] == "running"
    assert body["auto"] is True
    assert body["artifacts"] == {"data": [], "features": [], "analysis": []}


def test_delete_session(client):
    session_id = _create(client).json()["session_id"]
    del_res = client.delete(f"/api/sessions/{session_id}")
    assert del_res.status_code == 200
    get_res = client.get(f"/api/sessions/{session_id}")
    assert get_res.status_code == 404


def test_delete_session_not_found_returns_404(client):
    res = client.delete("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
