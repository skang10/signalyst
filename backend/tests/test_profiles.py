def test_list_profiles_returns_list(client):
    res = client.get("/api/profiles")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_list_profiles_includes_oil(client):
    res = client.get("/api/profiles")
    ids = [p["id"] for p in res.json()]
    assert "oil" in ids


def test_get_oil_profile(client):
    res = client.get("/api/profiles/oil")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "oil"
    assert body["name"] == "Oil Markets"
    assert "bull_supercycle" in body["regime_labels"]
    assert "windows" in body["default_featurizer_config"]


def test_get_profile_not_found(client):
    res = client.get("/api/profiles/nonexistent")
    assert res.status_code == 404


def test_list_profiles_includes_sp500_and_eurusd(client):
    res = client.get("/api/profiles")
    ids = [p["id"] for p in res.json()]
    assert "sp500" in ids
    assert "eurusd" in ids


def test_get_sp500_profile(client):
    res = client.get("/api/profiles/sp500")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "sp500"
    assert body["name"] == "S&P 500"
    assert body["regime_labels"] == ["bull_market", "range_bound", "bear_market", "high_volatility"]
    assert "windows" in body["default_featurizer_config"]


def test_get_eurusd_profile(client):
    res = client.get("/api/profiles/eurusd")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "eurusd"
    assert body["name"] == "EUR/USD"
    assert body["regime_labels"] == ["uptrend", "range_bound", "downtrend", "volatility_spike"]
    assert "windows" in body["default_featurizer_config"]
