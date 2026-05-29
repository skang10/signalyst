# Data Discovery Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `fetch_data` + `fetch_geopolitical_risk` tools with a `ConnectorRegistry` that auto-discovers connector manifests, and two new agent tools — `list_data_sources` and `fetch_from_source` — so the agent discovers what data is available and chooses what to pull rather than following a fixed list.

**Architecture:** A `ConnectorRegistry` scans `backend/src/data/connectors/` at import time, reads each subdirectory's `manifest.yaml`, checks env for required API keys, and builds `available`/`blocked` lists. The existing fetch functions in `connectors.py` and `gpr.py` are migrated into per-connector `connector.py` files. Two new tools replace `fetch_data` and `fetch_geopolitical_risk`; the system prompt is updated to tell the agent to discover before fetching.

**Tech Stack:** Python, `pyyaml`, `importlib`, existing `yfinance` / `fredapi` / `httpx` / `pandas` dependencies already in `pyproject.toml`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/src/data/registry.py` | `ConnectorMeta` dataclass, `ConnectorRegistry` class, module-level singleton |
| Create | `backend/src/data/connectors/yfinance/manifest.yaml` | yfinance connector manifest |
| Create | `backend/src/data/connectors/yfinance/connector.py` | `fetch(params, context)` — wraps `fetch_price_series` |
| Create | `backend/src/data/connectors/fred/manifest.yaml` | FRED connector manifest |
| Create | `backend/src/data/connectors/fred/connector.py` | `fetch(params, context)` — wraps `fetch_fred_series` |
| Create | `backend/src/data/connectors/gpr/manifest.yaml` | GPR connector manifest |
| Create | `backend/src/data/connectors/gpr/connector.py` | `fetch(params, context)` — wraps `fetch_gpr_series` |
| Create | `backend/src/data/connectors/eia/manifest.yaml` | EIA connector manifest |
| Create | `backend/src/data/connectors/eia/connector.py` | `fetch(params, context)` — wraps `fetch_eia_inventory` |
| Modify | `backend/src/data/__init__.py` | Export `connector_registry` singleton; keep old exports for backward compat |
| Create | `backend/tests/test_connector_registry.py` | Registry unit tests |
| Modify | `backend/src/agent/tools.py` | Add `list_data_sources` + `fetch_from_source`; remove `fetch_data` + `fetch_geopolitical_risk` |
| Create | `backend/tests/test_data_tools.py` | Tests for the two new agent tools |
| Modify | `backend/src/agent/loop.py` | Update `TOOL_PHASES` map; update system prompt data sourcing section |

> `backend/src/data/connectors.py` and `backend/src/data/gpr.py` are **kept** — the new connector.py files import from them. This avoids breaking existing tests (`test_data_connectors.py`, `test_gpr_connector.py`).

---

## Task 1: Add pyyaml dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Check if pyyaml is already present**

```bash
cd backend && grep pyyaml pyproject.toml
```

If output is non-empty, skip to Task 2. If empty, continue.

- [ ] **Step 2: Add pyyaml to dependencies**

Open `backend/pyproject.toml`. In the `dependencies` list add:

```toml
    "pyyaml>=6.0",
```

Place it alphabetically among existing dependencies.

- [ ] **Step 3: Sync the venv**

```bash
cd backend && uv sync
```

Expected: resolves without conflict. `pyyaml` appears in output.

- [ ] **Step 4: Verify import**

```bash
cd backend && uv run python -c "import yaml; print(yaml.__version__)"
```

Expected: prints a version string like `6.0.2`.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "feat: add pyyaml dependency for connector manifests"
```

---

## Task 2: ConnectorRegistry

**Files:**
- Create: `backend/src/data/registry.py`
- Create: `backend/tests/test_connector_registry.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_connector_registry.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.data.registry import ConnectorMeta, ConnectorRegistry


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
        "def fetch(params, context):\n"
        "    return {'fetched': {}, 'skipped': []}\n"
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
        "def fetch(params, context):\n"
        "    return {'echoed': params['msg']}\n"
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
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
cd backend && uv run pytest tests/test_connector_registry.py -v
```

Expected: `ImportError` — `src.data.registry` does not exist.

- [ ] **Step 3: Implement `backend/src/data/registry.py`**

```python
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml


@dataclass
class ConnectorMeta:
    name: str
    description: str
    provides: list[str]
    params_schema: dict[str, Any]
    requires_env: str | None
    compute_tier: str
    examples: list[dict[str, Any]]
    module: ModuleType


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, ConnectorMeta] = {}

    def scan(self, connectors_dir: Path) -> None:
        """Scan a directory for connector subdirs containing manifest.yaml."""
        if not connectors_dir.is_dir():
            return
        for subdir in sorted(connectors_dir.iterdir()):
            manifest_path = subdir / "manifest.yaml"
            connector_path = subdir / "connector.py"
            if not manifest_path.exists() or not connector_path.exists():
                continue
            with manifest_path.open() as f:
                data = yaml.safe_load(f)
            module = _load_module(data["name"], connector_path)
            meta = ConnectorMeta(
                name=data["name"],
                description=data.get("description", ""),
                provides=data.get("provides", []),
                params_schema=data.get("params", {"type": "object", "properties": {}, "required": []}),
                requires_env=data.get("requires", {}).get("env"),
                compute_tier=data.get("compute_tier", "low"),
                examples=data.get("examples", []),
                module=module,
            )
            self._connectors[meta.name] = meta

    def list(self) -> dict[str, Any]:
        """Return available and blocked connector metadata."""
        available = []
        blocked = []
        for meta in self._connectors.values():
            if meta.requires_env and not os.environ.get(meta.requires_env):
                blocked.append({
                    "name": meta.name,
                    "reason": f"{meta.requires_env} not set",
                })
            else:
                available.append({
                    "name": meta.name,
                    "description": meta.description,
                    "provides": meta.provides,
                    "params_schema": meta.params_schema,
                    "examples": meta.examples,
                })
        return {"available": available, "blocked": blocked}

    def is_available(self, name: str) -> bool:
        if name not in self._connectors:
            return False
        meta = self._connectors[name]
        return not meta.requires_env or bool(os.environ.get(meta.requires_env))

    def fetch(self, name: str, params: dict[str, Any], context: Any) -> dict[str, Any]:
        """Dispatch to the named connector's fetch() function."""
        if name not in self._connectors:
            raise KeyError(f"Unknown connector: {name!r}")
        meta = self._connectors[name]
        if meta.requires_env and not os.environ.get(meta.requires_env):
            raise RuntimeError(
                f"Connector {name!r} requires env var {meta.requires_env!r} which is not set"
            )
        return meta.module.fetch(params, context)  # type: ignore[no-any-return]


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"connectors.{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


connector_registry = ConnectorRegistry()
```

- [ ] **Step 4: Run tests, confirm they PASS**

```bash
cd backend && uv run pytest tests/test_connector_registry.py -v
```

Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/data/registry.py backend/tests/test_connector_registry.py
git commit -m "feat: add ConnectorRegistry with manifest-based auto-discovery"
```

---

## Task 3: Connector manifests and connector.py files

**Files:**
- Create: `backend/src/data/connectors/yfinance/manifest.yaml`
- Create: `backend/src/data/connectors/yfinance/connector.py`
- Create: `backend/src/data/connectors/fred/manifest.yaml`
- Create: `backend/src/data/connectors/fred/connector.py`
- Create: `backend/src/data/connectors/gpr/manifest.yaml`
- Create: `backend/src/data/connectors/gpr/connector.py`
- Create: `backend/src/data/connectors/eia/manifest.yaml`
- Create: `backend/src/data/connectors/eia/connector.py`

- [ ] **Step 1: Create the connectors directory**

```bash
mkdir -p backend/src/data/connectors/yfinance
mkdir -p backend/src/data/connectors/fred
mkdir -p backend/src/data/connectors/gpr
mkdir -p backend/src/data/connectors/eia
```

- [ ] **Step 2: Create yfinance manifest**

Create `backend/src/data/connectors/yfinance/manifest.yaml`:

```yaml
name: yfinance
description: >
  Daily price series from Yahoo Finance. Supports equities, ETFs, and
  futures — e.g. WTI crude (CL=F), Brent (BZ=F), DXY (DX-Y.NYB),
  energy sector ETF (XLE), S&P 500 (SPY).
provides:
  - price_series
  - equity_prices
  - futures_prices
params:
  type: object
  properties:
    tickers:
      type: array
      items:
        type: string
      description: "yfinance ticker symbols, e.g. ['CL=F', 'DX-Y.NYB', 'XLE', 'SPY']"
  required:
    - tickers
compute_tier: low
examples:
  - tickers: ["CL=F", "DX-Y.NYB", "XLE", "SPY"]
```

- [ ] **Step 3: Create yfinance connector.py**

Create `backend/src/data/connectors/yfinance/connector.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.data.connectors import fetch_price_series

if TYPE_CHECKING:
    from src.agent.tools import AgentContext


def fetch(params: dict[str, Any], context: AgentContext) -> dict[str, Any]:
    """Fetch daily close price series for each ticker into context.signals."""
    tickers: list[str] = params["tickers"]
    fetched: dict[str, int] = {}
    skipped: list[str] = []

    for ticker in tickers:
        try:
            series = fetch_price_series(ticker, context.date_range_start, context.date_range_end)
            context.signals[ticker] = series
            fetched[ticker] = len(series)
        except Exception as exc:
            skipped.append(f"{ticker}: {exc}")

    return {"fetched": fetched, "skipped": skipped}
```

- [ ] **Step 4: Create fred manifest**

Create `backend/src/data/connectors/fred/manifest.yaml`:

```yaml
name: fred
description: >
  Macro time series from the St. Louis Fed FRED database — industrial
  production (INDPRO), unemployment (UNRATE), 10-year breakeven
  inflation (T10YIE), trade-weighted USD (DTWEXBGS), and more.
provides:
  - macro_series
  - economic_indicators
params:
  type: object
  properties:
    series_ids:
      type: array
      items:
        type: string
      description: "FRED series IDs, e.g. ['INDPRO', 'UNRATE']"
  required:
    - series_ids
requires:
  env: FRED_API_KEY
compute_tier: low
examples:
  - series_ids: ["INDPRO", "UNRATE"]
```

- [ ] **Step 5: Create fred connector.py**

Create `backend/src/data/connectors/fred/connector.py`:

```python
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from src.data.connectors import fetch_fred_series

if TYPE_CHECKING:
    from src.agent.tools import AgentContext


def fetch(params: dict[str, Any], context: AgentContext) -> dict[str, Any]:
    """Fetch FRED macro series into context.signals."""
    series_ids: list[str] = params["series_ids"]
    api_key = os.environ.get("FRED_API_KEY", "")
    fetched: dict[str, int] = {}
    skipped: list[str] = []

    for series_id in series_ids:
        try:
            series = fetch_fred_series(
                series_id, context.date_range_start, context.date_range_end, api_key=api_key
            )
            context.signals[series_id] = series
            fetched[series_id] = len(series)
        except Exception as exc:
            skipped.append(f"{series_id}: {exc}")

    return {"fetched": fetched, "skipped": skipped}
```

- [ ] **Step 6: Create gpr manifest**

Create `backend/src/data/connectors/gpr/manifest.yaml`:

```yaml
name: gpr
description: >
  Daily Geopolitical Risk Index (GPR) from Matteo Iacoviello's page at
  the Federal Reserve. Quantifies geopolitical tensions from news
  coverage — spikes during wars, sanctions, and political crises.
  No API key required; data is fetched from a public URL.
provides:
  - geopolitical_risk
  - gpr_index
params:
  type: object
  properties: {}
  required: []
compute_tier: low
examples:
  - {}
```

- [ ] **Step 7: Create gpr connector.py**

Create `backend/src/data/connectors/gpr/connector.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.data.gpr import fetch_gpr_series

if TYPE_CHECKING:
    from src.agent.tools import AgentContext


def fetch(params: dict[str, Any], context: AgentContext) -> dict[str, Any]:
    """Fetch daily GPR index into context.signals['GPR']."""
    try:
        series = fetch_gpr_series(context.date_range_start, context.date_range_end)
        context.signals["GPR"] = series
        return {"fetched": {"GPR": len(series)}, "skipped": []}
    except Exception as exc:
        return {"fetched": {}, "skipped": [f"GPR: {exc}"]}
```

- [ ] **Step 8: Create eia manifest**

Create `backend/src/data/connectors/eia/manifest.yaml`:

```yaml
name: eia
description: >
  Weekly US crude oil inventory change from the EIA (Energy Information
  Administration). Positive values = inventory build (bearish for price),
  negative = inventory draw (bullish). Requires a free EIA API key.
provides:
  - inventory_data
  - eia_inventory
params:
  type: object
  properties: {}
  required: []
requires:
  env: EIA_API_KEY
compute_tier: low
examples:
  - {}
```

- [ ] **Step 9: Create eia connector.py**

Create `backend/src/data/connectors/eia/connector.py`:

```python
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from src.data.connectors import fetch_eia_inventory

if TYPE_CHECKING:
    from src.agent.tools import AgentContext


def fetch(params: dict[str, Any], context: AgentContext) -> dict[str, Any]:
    """Fetch weekly EIA crude oil inventory changes into context.signals."""
    api_key = os.environ.get("EIA_API_KEY", "")
    try:
        series = fetch_eia_inventory(
            context.date_range_start, context.date_range_end, api_key=api_key
        )
        context.signals["eia_inventory_change"] = series
        return {"fetched": {"eia_inventory_change": len(series)}, "skipped": []}
    except Exception as exc:
        return {"fetched": {}, "skipped": [f"eia_inventory_change: {exc}"]}
```

- [ ] **Step 10: Verify the registry scans the built-in connectors**

```bash
cd backend && uv run python -c "
from pathlib import Path
from src.data.registry import ConnectorRegistry
reg = ConnectorRegistry()
reg.scan(Path('src/data/connectors'))
print('Found:', list(reg._connectors.keys()))
"
```

Expected: `Found: ['eia', 'fred', 'gpr', 'yfinance']` (order may vary).

- [ ] **Step 11: Commit**

```bash
git add backend/src/data/connectors/
git commit -m "feat: add yfinance, fred, gpr, eia connector manifests and fetch modules"
```

---

## Task 4: Wire registry into src/data/__init__.py and scan at import

**Files:**
- Modify: `backend/src/data/__init__.py`

- [ ] **Step 1: Update `backend/src/data/__init__.py`**

Replace the current contents:

```python
from pathlib import Path

from src.data.connectors import fetch_eia_inventory, fetch_fred_series, fetch_price_series
from src.data.registry import ConnectorRegistry, connector_registry

_CONNECTORS_DIR = Path(__file__).parent / "connectors"
connector_registry.scan(_CONNECTORS_DIR)

__all__ = [
    "connector_registry",
    "fetch_eia_inventory",
    "fetch_fred_series",
    "fetch_price_series",
]
```

- [ ] **Step 2: Verify registry is populated on import**

```bash
cd backend && uv run python -c "
from src.data import connector_registry
result = connector_registry.list()
print('Available:', [c['name'] for c in result['available']])
print('Blocked:', [c['name'] for c in result['blocked']])
"
```

Expected: yfinance and gpr in `available`; fred and eia in `blocked` (unless those keys are set in your `.env`).

- [ ] **Step 3: Run existing data tests to confirm nothing broke**

```bash
cd backend && uv run pytest tests/test_data_connectors.py tests/test_gpr_connector.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/src/data/__init__.py
git commit -m "feat: auto-scan connector manifests on src.data import"
```

---

## Task 5: New agent tools — list_data_sources and fetch_from_source

**Files:**
- Modify: `backend/src/agent/tools.py`
- Create: `backend/tests/test_data_tools.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_data_tools.py`:

```python
from __future__ import annotations

from pathlib import Path
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
        "def fetch(params, context):\n"
        "    return {'fetched': {'TEST': 3}, 'skipped': []}\n"
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
        "def fetch(params, context):\n"
        "    return {'fetched': {}, 'skipped': []}\n"
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
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
cd backend && uv run pytest tests/test_data_tools.py -v
```

Expected: `ImportError` — `fetch_from_source` and `list_data_sources` not yet defined.

- [ ] **Step 3: Add the two new tools to `backend/src/agent/tools.py`**

Add this import near the top of the file (after the existing imports):

```python
from src.data import connector_registry
```

Then add the two tool functions. Place them immediately before the `engineer_features` function (after `fetch_data`). Do **not** remove `fetch_data` or `fetch_geopolitical_risk` yet — that happens in Task 6.

```python
@registry.tool(
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    }
)
def list_data_sources(context: AgentContext | None = None) -> dict[str, Any]:
    """List all available data connectors and which ones are blocked due to missing config."""
    return connector_registry.list()


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "source_name": {
                "type": "string",
                "description": "Name of the connector to fetch from, as returned by list_data_sources",
            },
            "params": {
                "type": "object",
                "description": "Connector-specific parameters — see the params_schema in list_data_sources output",
            },
        },
        "required": ["source_name", "params"],
    }
)
def fetch_from_source(
    source_name: str,
    params: dict[str, Any],
    context: AgentContext | None = None,
) -> dict[str, Any]:
    """Fetch data from a named connector into the analysis context. Returns a fetch summary or an error dict."""
    if source_name not in connector_registry._connectors:
        return {"error": "unknown_source", "detail": f"No connector named {source_name!r}"}
    if not connector_registry.is_available(source_name):
        meta = connector_registry._connectors[source_name]
        return {
            "error": "blocked",
            "reason": f"{meta.requires_env} not set",
        }
    try:
        return connector_registry.fetch(source_name, params, context)
    except Exception as exc:
        return {"error": "fetch_failed", "detail": str(exc)}
```

- [ ] **Step 4: Run tests, confirm they PASS**

```bash
cd backend && uv run pytest tests/test_data_tools.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Run full test suite to catch regressions**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agent/tools.py backend/tests/test_data_tools.py
git commit -m "feat: add list_data_sources and fetch_from_source agent tools"
```

---

## Task 6: Remove fetch_data and fetch_geopolitical_risk tools

**Files:**
- Modify: `backend/src/agent/tools.py`
- Modify: `backend/src/agent/loop.py`
- Modify: `backend/tests/test_agent_tools.py`
- Modify: `backend/tests/test_deferred_tools.py`

- [ ] **Step 1: Check which tests reference fetch_data / fetch_geopolitical_risk**

```bash
cd backend && grep -rn "fetch_data\|fetch_geopolitical_risk" tests/
```

Note every file and test name — you'll update or delete those tests below.

- [ ] **Step 2: Remove fetch_data and fetch_geopolitical_risk from tools.py**

In `backend/src/agent/tools.py`:

1. Remove the `@registry.tool(...)` block for `fetch_data` (the decorator + function, approximately lines 64–115)
2. Remove the `@registry.tool(...)` block for `fetch_geopolitical_risk` (approximately lines 447–457)
3. Remove the now-unused imports:
   - `from src.data.connectors import fetch_fred_series, fetch_price_series`
   - `from src.data.gpr import fetch_gpr_series`
4. Update any error messages inside other tools that say "Call fetch_data first" — change to "Call fetch_from_source first":
   - In `engineer_features`: `raise ValueError("No signals in context. Call fetch_from_source first.")`
   - In `run_tabpfn` (two occurrences): replace "Call fetch_data with tickers=['CL=F', ...]" with "Call fetch_from_source with source_name='yfinance' and params={'tickers': ['CL=F', ...]}"

- [ ] **Step 3: Update TOOL_PHASES in loop.py**

In `backend/src/agent/loop.py`, update the `TOOL_PHASES` dict. Replace:

```python
TOOL_PHASES = {
    "fetch_data": "fetching_market_data",
    "fetch_geopolitical_risk": "fetching_geopolitical_risk",
    ...
}
```

With:

```python
TOOL_PHASES = {
    "list_data_sources": "discovering_data_sources",
    "fetch_from_source": "fetching_data",
    "engineer_features": "engineering_features",
    "detect_drift": "detecting_drift",
    "evaluate_features": "evaluating_features",
    "backtest": "backtesting",
    "explain_prediction": "explaining",
}
```

- [ ] **Step 4: Update tests that reference the removed tools**

In `backend/tests/test_agent_tools.py`, delete any test functions that test `fetch_data` or `fetch_geopolitical_risk` directly (they are superseded by `test_data_tools.py`). Keep all other tests untouched.

In `backend/tests/test_deferred_tools.py`, check for `fetch_geopolitical_risk` references and remove or replace them if they import or call that function directly.

- [ ] **Step 5: Run full test suite**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass. If any test fails because it imported `fetch_data` or `fetch_geopolitical_risk`, remove that test — it is now covered by `test_data_tools.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agent/tools.py backend/src/agent/loop.py \
        backend/tests/test_agent_tools.py backend/tests/test_deferred_tools.py
git commit -m "feat: remove fetch_data and fetch_geopolitical_risk, wire TOOL_PHASES"
```

---

## Task 7: Update the system prompt

**Files:**
- Modify: `backend/src/agent/loop.py`

- [ ] **Step 1: Update `build_system_prompt` in `backend/src/agent/loop.py`**

Replace the data sourcing lines in the `workflow` string. Currently:

```python
workflow = (
    "Given a date range and analysis tasks, use the tools in this order:\n"
    "1. fetch_data — pull WTI (CL=F), DXY (DX-Y.NYB), XLE, SPY price series and INDPRO macro "
    "data\n"
    "2. fetch_geopolitical_risk — add GPR index to signals\n"
    "3. engineer_features — featurize with windows [5, 20, 60] and lags [1, 5, 20]\n"
    "4. detect_drift — check if recent feature distributions have shifted\n"
    "5. run_tabpfn with task='regime' — classify the current oil market regime\n"
    "6. run_tabpfn with task='direction' — predict WTI price direction over the next "
    "20 trading days\n"
)
```

Replace with:

```python
workflow = (
    "Given a date range and analysis tasks, use the tools in this order:\n"
    "1. list_data_sources — discover which data connectors are available and which are "
    "blocked (e.g. missing API key). Note any blocked sources in your reasoning.\n"
    "2. fetch_from_source — for each available connector relevant to the analysis, fetch "
    "the data. At minimum fetch price series (yfinance) and geopolitical risk (gpr). "
    "Fetch macro data (fred) and inventory data (eia) if available. "
    "For each blocked source, mention the gap in your thought.\n"
    "3. engineer_features — featurize with windows [5, 20, 60] and lags [1, 5, 20]\n"
    "4. detect_drift — check if recent feature distributions have shifted\n"
    "5. run_tabpfn with task='regime' — classify the current oil market regime\n"
    "6. run_tabpfn with task='direction' — predict WTI price direction over the next "
    "20 trading days\n"
)
```

- [ ] **Step 2: Verify the prompt builds without error**

```bash
cd backend && uv run python -c "
from src.agent.loop import build_system_prompt
print(build_system_prompt('quick'))
"
```

Expected: prints the full system prompt with the new data sourcing steps. No errors.

- [ ] **Step 3: Run the full test suite**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Run lint and type check**

```bash
cd backend && uv run ruff check src/agent/loop.py src/agent/tools.py src/data/registry.py src/data/connectors/
cd backend && uv run mypy src/agent/loop.py src/agent/tools.py src/data/registry.py
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/loop.py
git commit -m "feat: update system prompt for discovery-first data sourcing"
```

---

## Task 8: Integration smoke test

**Files:**
- No new files — verify end-to-end wiring

- [ ] **Step 1: Verify registry is populated and tools are registered**

```bash
cd backend && uv run python -c "
from src.data import connector_registry
from src.agent.tools import list_data_sources, fetch_from_source
from src.agent.registry import registry

tool_names = list(registry._tools.keys())
print('Registered tools:', tool_names)
assert 'list_data_sources' in tool_names, 'list_data_sources missing'
assert 'fetch_from_source' in tool_names, 'fetch_from_source missing'
assert 'fetch_data' not in tool_names, 'fetch_data still registered'
assert 'fetch_geopolitical_risk' not in tool_names, 'fetch_geopolitical_risk still registered'

sources = connector_registry.list()
print('Available connectors:', [c['name'] for c in sources['available']])
print('Blocked connectors:', [c['name'] for c in sources['blocked']])
print('OK')
"
```

Expected: `list_data_sources` and `fetch_from_source` in tools; `fetch_data` and `fetch_geopolitical_risk` absent; at least `yfinance` and `gpr` in available.

- [ ] **Step 2: Run list_data_sources tool directly**

```bash
cd backend && uv run python -c "
from src.agent.tools import list_data_sources
result = list_data_sources(context=None)
import json
print(json.dumps(result, indent=2))
"
```

Expected: JSON with `available` and `blocked` arrays. yfinance and gpr are available; fred and eia are blocked (unless keys are set).

- [ ] **Step 3: Run full test suite one final time**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: data discovery layer complete — registry, connectors, tools, prompt"
```
