from unittest.mock import patch


def test_market_snapshot_returns_200(client):
    with patch(
        "api.routes.market._fetch_price_change", return_value={"price": 83.0, "change_pct": 1.2}
    ):
        res = client.get("/api/market/snapshot")
    assert res.status_code == 200
    body = res.json()
    assert "fetched_at" in body
    assert "wti" in body
    assert "brent" in body
    assert "dxy" in body


def test_market_snapshot_returns_null_on_failure(client):
    with patch("api.routes.market._fetch_price_change", side_effect=Exception("network error")):
        res = client.get("/api/market/snapshot")
    assert res.status_code == 200
    body = res.json()
    assert body["wti"] is None
    assert body["brent"] is None
