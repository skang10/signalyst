def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200


def test_derivatives_missing_required_fields(client):
    res = client.post("/api/derivatives/price", json={})
    assert res.status_code == 422


def test_derivatives_invalid_option_type(client):
    res = client.post(
        "/api/derivatives/price",
        json={
            "regime": "geopolitical_spike",
            "spot": 87.5,
            "strike": 90.0,
            "tenor_days": 30,
            "option_type": "swap",
        },
    )
    assert res.status_code == 422


def test_derivatives_invalid_style(client):
    res = client.post(
        "/api/derivatives/price",
        json={
            "regime": "geopolitical_spike",
            "spot": 87.5,
            "strike": 90.0,
            "tenor_days": 30,
            "style": "asian",
        },
    )
    assert res.status_code == 422
