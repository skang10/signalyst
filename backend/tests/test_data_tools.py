from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agent.tools import AgentContext, fetch_from_source, list_data_sources
from src.data.registry import ConnectorRegistry


@pytest.fixture
def ctx():
    return AgentContext(date_range_start="2024-01-01", date_range_end="2024-06-30")


@pytest.fixture
def mock_registry(tmp_path):
    """A registry with one free connector and one key-gated connector."""
    free_dir = tmp_path / "connectors" / "freeconn"
    free_dir.mkdir(parents=True)
    (free_dir / "manifest.yaml").write_text(
        "name: freeconn\n"
        "description: Free test connector\n"
        "provides: [test]\n"
        "params:\n"
        "  type: object\n"
        "  properties:\n"
        "    tickers: {type: array, items: {type: string}}\n"
        "  required: [tickers]\n"
        "compute_tier: low\n"
        "examples:\n"
        "  - tickers: ['TEST']\n"
    )
    (free_dir / "connector.py").write_text(
        "def fetch(params, context):\n" "    return {'fetched': {'TEST': 3}, 'skipped': []}\n"
    )

    keyed_dir = tmp_path / "connectors" / "keyedconn"
    keyed_dir.mkdir(parents=True)
    (keyed_dir / "manifest.yaml").write_text(
        "name: keyedconn\n"
        "description: Key-gated test connector\n"
        "provides: [macro]\n"
        "params:\n"
        "  type: object\n"
        "  properties: {}\n"
        "  required: []\n"
        "requires:\n"
        "  env: FAKE_API_KEY\n"
        "compute_tier: low\n"
    )
    (keyed_dir / "connector.py").write_text(
        "def fetch(params, context):\n" "    return {'fetched': {}, 'skipped': []}\n"
    )

    reg = ConnectorRegistry()
    reg.scan(tmp_path / "connectors")
    return reg


# ── list_data_sources ─────────────────────────────────────────────────────────


def test_list_data_sources_returns_available_and_blocked(mock_registry, monkeypatch):
    monkeypatch.delenv("FAKE_API_KEY", raising=False)
    with patch("src.agent.tools.connector_registry", mock_registry):
        result = list_data_sources(context=None)

    assert "available" in result
    assert "blocked" in result
    assert any(c["name"] == "freeconn" for c in result["available"])
    assert any(c["name"] == "keyedconn" for c in result["blocked"])


def test_list_data_sources_keyed_available_when_key_set(mock_registry, monkeypatch):
    monkeypatch.setenv("FAKE_API_KEY", "secret")
    with patch("src.agent.tools.connector_registry", mock_registry):
        result = list_data_sources(context=None)

    assert any(c["name"] == "keyedconn" for c in result["available"])


# ── fetch_from_source ─────────────────────────────────────────────────────────


def test_fetch_from_source_dispatches_to_connector(mock_registry, ctx):
    with patch("src.agent.tools.connector_registry", mock_registry):
        result = fetch_from_source(
            source_name="freeconn",
            params={"tickers": ["TEST"]},
            context=ctx,
        )

    assert result == {"fetched": {"TEST": 3}, "skipped": []}


def test_fetch_from_source_unknown_source_returns_error(mock_registry, ctx):
    with patch("src.agent.tools.connector_registry", mock_registry):
        result = fetch_from_source(
            source_name="nonexistent",
            params={},
            context=ctx,
        )

    assert result["error"] == "unknown_source"
    assert "nonexistent" in result["detail"]


def test_fetch_from_source_blocked_returns_error(mock_registry, ctx, monkeypatch):
    monkeypatch.delenv("FAKE_API_KEY", raising=False)
    with patch("src.agent.tools.connector_registry", mock_registry):
        result = fetch_from_source(
            source_name="keyedconn",
            params={},
            context=ctx,
        )

    assert result["error"] == "blocked"
    assert "FAKE_API_KEY" in result["reason"]
