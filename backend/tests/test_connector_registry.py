from __future__ import annotations

import pytest

from src.data.registry import ConnectorRegistry

# ── scan ──────────────────────────────────────────────────────────────────────


def test_registry_scan_finds_manifests(tmp_path):
    """Registry discovers connectors from a directory of manifest.yaml files."""
    conn_dir = tmp_path / "connectors" / "myconn"
    conn_dir.mkdir(parents=True)
    (conn_dir / "manifest.yaml").write_text(
        "name: myconn\n"
        "description: Test connector\n"
        "provides: [test_data]\n"
        "params:\n"
        "  type: object\n"
        "  properties:\n"
        "    tickers:\n"
        "      type: array\n"
        "      items: {type: string}\n"
        "  required: [tickers]\n"
        "compute_tier: low\n"
    )
    (conn_dir / "connector.py").write_text(
        "def fetch(params, context):\n    return {'fetched': {}, 'skipped': []}\n"
    )

    reg = ConnectorRegistry()
    reg.scan(tmp_path / "connectors")

    assert "myconn" in reg._connectors


def test_registry_scan_ignores_dir_without_manifest(tmp_path):
    conn_dir = tmp_path / "connectors" / "nomanifest"
    conn_dir.mkdir(parents=True)
    (conn_dir / "connector.py").write_text("def fetch(params, context): pass\n")

    reg = ConnectorRegistry()
    reg.scan(tmp_path / "connectors")

    assert "nomanifest" not in reg._connectors


# ── list ──────────────────────────────────────────────────────────────────────


def test_registry_list_available_when_no_key_required(tmp_path):
    """Connectors with no requires_env are always available."""
    conn_dir = tmp_path / "connectors" / "free"
    conn_dir.mkdir(parents=True)
    (conn_dir / "manifest.yaml").write_text(
        "name: free\n"
        "description: Free connector\n"
        "provides: [prices]\n"
        "params:\n"
        "  type: object\n"
        "  properties: {}\n"
        "  required: []\n"
        "compute_tier: low\n"
    )
    (conn_dir / "connector.py").write_text("def fetch(params, context): return {}\n")

    reg = ConnectorRegistry()
    reg.scan(tmp_path / "connectors")
    result = reg.list()

    assert any(c["name"] == "free" for c in result["available"])
    assert not any(c["name"] == "free" for c in result["blocked"])


def test_registry_list_blocked_when_key_missing(tmp_path, monkeypatch):
    """Connectors whose required env var is absent appear in blocked."""
    monkeypatch.delenv("MY_SECRET_KEY", raising=False)

    conn_dir = tmp_path / "connectors" / "keyed"
    conn_dir.mkdir(parents=True)
    (conn_dir / "manifest.yaml").write_text(
        "name: keyed\n"
        "description: Keyed connector\n"
        "provides: [macro]\n"
        "params:\n"
        "  type: object\n"
        "  properties: {}\n"
        "  required: []\n"
        "requires:\n"
        "  env: MY_SECRET_KEY\n"
        "compute_tier: low\n"
    )
    (conn_dir / "connector.py").write_text("def fetch(params, context): return {}\n")

    reg = ConnectorRegistry()
    reg.scan(tmp_path / "connectors")
    result = reg.list()

    assert any(c["name"] == "keyed" for c in result["blocked"])
    blocked = next(c for c in result["blocked"] if c["name"] == "keyed")
    assert "MY_SECRET_KEY" in blocked["reason"]


def test_registry_list_available_when_key_present(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_SECRET_KEY", "abc123")

    conn_dir = tmp_path / "connectors" / "keyed"
    conn_dir.mkdir(parents=True)
    (conn_dir / "manifest.yaml").write_text(
        "name: keyed\n"
        "description: Keyed connector\n"
        "provides: [macro]\n"
        "params:\n"
        "  type: object\n"
        "  properties: {}\n"
        "  required: []\n"
        "requires:\n"
        "  env: MY_SECRET_KEY\n"
        "compute_tier: low\n"
    )
    (conn_dir / "connector.py").write_text("def fetch(params, context): return {}\n")

    reg = ConnectorRegistry()
    reg.scan(tmp_path / "connectors")
    result = reg.list()

    assert any(c["name"] == "keyed" for c in result["available"])


# ── fetch ─────────────────────────────────────────────────────────────────────


def test_registry_fetch_dispatches_to_connector(tmp_path):
    conn_dir = tmp_path / "connectors" / "echo"
    conn_dir.mkdir(parents=True)
    (conn_dir / "manifest.yaml").write_text(
        "name: echo\n"
        "description: Echoes params\n"
        "provides: [test]\n"
        "params:\n"
        "  type: object\n"
        "  properties:\n"
        "    msg: {type: string}\n"
        "  required: [msg]\n"
        "compute_tier: low\n"
    )
    (conn_dir / "connector.py").write_text(
        "def fetch(params, context):\n    return {'echoed': params['msg']}\n"
    )

    reg = ConnectorRegistry()
    reg.scan(tmp_path / "connectors")
    result = reg.fetch("echo", {"msg": "hello"}, context=None)

    assert result == {"echoed": "hello"}


def test_registry_fetch_unknown_raises(tmp_path):
    reg = ConnectorRegistry()
    reg.scan(tmp_path)

    with pytest.raises(KeyError, match="nonexistent"):
        reg.fetch("nonexistent", {}, context=None)


def test_registry_fetch_blocked_connector_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)

    conn_dir = tmp_path / "connectors" / "blocked"
    conn_dir.mkdir(parents=True)
    (conn_dir / "manifest.yaml").write_text(
        "name: blocked\n"
        "description: Needs key\n"
        "provides: [data]\n"
        "params:\n"
        "  type: object\n"
        "  properties: {}\n"
        "  required: []\n"
        "requires:\n"
        "  env: MISSING_KEY\n"
        "compute_tier: low\n"
    )
    (conn_dir / "connector.py").write_text("def fetch(params, context): return {}\n")

    reg = ConnectorRegistry()
    reg.scan(tmp_path / "connectors")

    with pytest.raises(RuntimeError, match="MISSING_KEY"):
        reg.fetch("blocked", {}, context=None)
