def test_list_connectors_returns_four_builtins(client):
    res = client.get("/api/connectors")
    assert res.status_code == 200
    ids = {c["id"] for c in res.json()}
    assert ids == {"yfinance", "fred", "eia", "gpr"}


def test_list_connectors_each_has_required_fields(client):
    res = client.get("/api/connectors")
    for c in res.json():
        assert "id" in c
        assert "name" in c
        assert "type" in c
        assert "available" in c


def test_create_connector_stores_spec(client):
    body = {
        "id": "custom_test",
        "name": "Test Connector",
        "description": "A test connector",
        "spec": {"url": "https://example.com/api", "method": "GET"},
    }
    res = client.post("/api/connectors", json=body)
    assert res.status_code == 201
    assert res.json()["id"] == "custom_test"
    assert res.json()["type"] == "spec"


def test_create_connector_conflict_returns_409(client):
    body = {"id": "dup_test", "name": "Dup", "description": "", "spec": {}}
    client.post("/api/connectors", json=body)
    res = client.post("/api/connectors", json=body)
    assert res.status_code == 409


def test_created_connector_appears_in_list(client):
    client.post(
        "/api/connectors",
        json={"id": "listed_test", "name": "Listed", "description": "", "spec": {}},
    )
    res = client.get("/api/connectors")
    ids = {c["id"] for c in res.json()}
    assert "listed_test" in ids
