# Agent Tools & ReAct Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `src/agent/` — a tool registry, 4 core tool functions, and an async ReAct loop that drives an OpenAI model to orchestrate the oil-market analysis pipeline, with each step streamed to Redis and the final result persisted to the `Run` DB row.

**Architecture:** A `@tool` decorator registers functions in a module-level `ToolRegistry` that auto-builds OpenAI function-calling schemas. `run_agent_loop` runs as a FastAPI `BackgroundTask`: it creates its own DB session, drives the OpenAI chat completions ReAct loop (up to 10 iterations), dispatches tool calls via the registry, publishes every step to a Redis channel `run:{run_id}`, and marks the run COMPLETED or FAILED.

**Tech Stack:** `openai` (AsyncOpenAI, chat completions with tool use), `redis.asyncio` (pub/sub), `sqlalchemy.ext.asyncio` (AsyncSession), FastAPI BackgroundTasks, existing `src.data`, `src.featurizer`, `src.inference` modules.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `backend/pyproject.toml` | add `openai>=1.0.0` dependency |
| Modify | `backend/src/config.py` | add `openai_api_key`, `agent_model`, `agent_model_fast` |
| Create | `backend/src/agent/registry.py` | `ToolRegistry` class + `@tool` decorator + module singleton |
| Create | `backend/src/agent/tools.py` | `AgentContext` dataclass + 4 tool functions |
| Create | `backend/src/agent/loop.py` | `run_agent_loop` async function + `SYSTEM_PROMPT` constant |
| Modify | `backend/src/agent/__init__.py` | re-export `run_agent_loop` |
| Modify | `backend/api/routes/analyze.py` | wire `BackgroundTask` → `run_agent_loop`, save `Run` row |
| Create | `backend/tests/test_agent_tools.py` | unit tests for registry + tool functions |
| Create | `backend/tests/test_analyze_route.py` | integration test for updated analyze endpoint |

---

## Task 1: Add openai dependency and config settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/config.py`

- [ ] **Step 1: Add openai to pyproject.toml**

Open `backend/pyproject.toml`. In the `dependencies` list, under the `# Agent` comment, replace:

```toml
    # Agent
    "anthropic>=0.40.0",
```

with:

```toml
    # Agent
    "anthropic>=0.40.0",
    "openai>=1.0.0",
```

- [ ] **Step 2: Install the new dependency**

```bash
cd backend && uv sync
```

Expected: resolves without conflict, `openai` appears in `.venv`.

- [ ] **Step 3: Add settings fields to config.py**

Open `backend/src/config.py`. Add three fields after `anthropic_api_key`:

```python
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    agent_model: str = "gpt-5.4"
    agent_model_fast: str = "gpt-5.4-mini"
```

Full file after edit:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://temporal:temporal@localhost:5432/temporal_agent"
    redis_url: str = "redis://localhost:6379"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    agent_model: str = "gpt-5.4"
    agent_model_fast: str = "gpt-5.4-mini"

    fred_api_key: str = ""
    eia_api_key: str = ""
    tabpfn_token: str = ""

    sentry_dsn: str = ""

    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
```

- [ ] **Step 4: Verify imports**

```bash
cd backend && uv run python -c "import openai; from src.config import settings; print(settings.agent_model)"
```

Expected: `gpt-5.4`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/src/config.py
git commit -m "feat: add openai dependency and agent model config settings"
```

---

## Task 2: ToolRegistry

**Files:**
- Create: `backend/src/agent/registry.py`
- Create: `backend/tests/test_agent_tools.py` (registry section)

- [ ] **Step 1: Write the failing registry tests**

Create `backend/tests/test_agent_tools.py`:

```python
from src.agent.registry import ToolRegistry, tool


# ── Registry tests ────────────────────────────────────────────────────────────

def test_tool_decorator_registers_function():
    reg = ToolRegistry()

    @reg.tool({"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]})
    def my_func(x: int, context=None) -> int:
        """Double x."""
        return x * 2

    assert "my_func" in reg._tools


def test_registry_schemas_returns_openai_format():
    reg = ToolRegistry()

    @reg.tool({"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]})
    def add_one(x: int, context=None) -> int:
        """Add one to x."""
        return x + 1

    schemas = reg.schemas()
    assert len(schemas) == 1
    schema = schemas[0]
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "add_one"
    assert schema["function"]["description"] == "Add one to x."
    assert schema["function"]["parameters"]["properties"]["x"]["type"] == "integer"


def test_registry_dispatch_calls_function_with_context():
    reg = ToolRegistry()

    class FakeContext:
        value = 0

    @reg.tool({"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]})
    def set_value(n: int, context=None) -> dict:
        """Set context value."""
        context.value = n
        return {"set": n}

    ctx = FakeContext()
    result = reg.dispatch("set_value", {"n": 42}, ctx)
    assert result == {"set": 42}
    assert ctx.value == 42


def test_registry_dispatch_raises_on_unknown_tool():
    reg = ToolRegistry()
    import pytest
    with pytest.raises(KeyError):
        reg.dispatch("nonexistent", {}, None)
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
cd backend && uv run pytest tests/test_agent_tools.py -v
```

Expected: `ImportError` — `src.agent.registry` does not exist.

- [ ] **Step 3: Implement `backend/src/agent/registry.py`**

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class _ToolEntry:
    fn: Callable[..., Any]
    description: str
    parameters: dict[str, Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, _ToolEntry] = {}

    def tool(self, parameters: dict[str, Any]) -> Callable:
        """Decorator that registers a function in this registry."""
        def decorator(fn: Callable) -> Callable:
            self._tools[fn.__name__] = _ToolEntry(
                fn=fn,
                description=(fn.__doc__ or "").strip().splitlines()[0],
                parameters=parameters,
            )
            return fn
        return decorator

    def register(self, fn: Callable, parameters: dict[str, Any]) -> None:
        self._tools[fn.__name__] = _ToolEntry(
            fn=fn,
            description=(fn.__doc__ or "").strip().splitlines()[0],
            parameters=parameters,
        )

    def schemas(self) -> list[dict[str, Any]]:
        """Return tool list in OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": entry.description,
                    "parameters": entry.parameters,
                },
            }
            for name, entry in self._tools.items()
        ]

    def dispatch(self, name: str, arguments: dict[str, Any], context: Any) -> Any:
        """Call the named tool with **arguments and context kwarg."""
        entry = self._tools[name]  # raises KeyError if not found
        return entry.fn(**arguments, context=context)


registry = ToolRegistry()
```

- [ ] **Step 4: Run tests, confirm they PASS**

```bash
cd backend && uv run pytest tests/test_agent_tools.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/registry.py backend/tests/test_agent_tools.py
git commit -m "feat: add ToolRegistry with @tool decorator and dispatch"
```

---

## Task 3: AgentContext + tool functions

**Files:**
- Create: `backend/src/agent/tools.py`
- Modify: `backend/tests/test_agent_tools.py` (add tool tests)

- [ ] **Step 1: Add tool function tests to `backend/tests/test_agent_tools.py`**

Append to the existing file:

```python
import uuid
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.agent.tools import AgentContext, engineer_features, explain_prediction, fetch_data, run_tabpfn


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ctx():
    return AgentContext(date_range_start="2024-01-01", date_range_end="2024-12-31")


@pytest.fixture
def ctx_with_signals(ctx):
    dates = pd.date_range("2022-01-01", periods=300, freq="D")
    ctx.signals["CL=F"] = pd.Series(np.linspace(70, 90, 300), index=dates, name="CL=F")
    ctx.signals["SPY"] = pd.Series(np.linspace(400, 500, 300), index=dates, name="SPY")
    return ctx


@pytest.fixture
def ctx_with_features(ctx_with_signals):
    dates = pd.date_range("2022-03-01", periods=200, freq="D")
    ctx_with_signals.features = pd.DataFrame(
        np.random.randn(200, 5),
        index=dates,
        columns=["f1", "f2", "f3", "f4", "f5"],
    )
    return ctx_with_signals


# ── fetch_data tests ──────────────────────────────────────────────────────────

def test_fetch_data_returns_signal_summary(ctx):
    fake_series = pd.Series(
        [70.0, 71.0, 72.0],
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
        name="CL=F",
    )
    with patch("src.agent.tools.fetch_price_series", return_value=fake_series):
        result = fetch_data(tickers=["CL=F"], fred_series=[], context=ctx)

    assert result["fetched"]["CL=F"] == 3
    assert ctx.signals["CL=F"] is not None


def test_fetch_data_skips_fred_without_api_key(ctx):
    fake_series = pd.Series(
        [70.0],
        index=pd.date_range("2024-01-01", periods=1, freq="D"),
        name="CL=F",
    )
    with patch("src.agent.tools.fetch_price_series", return_value=fake_series), \
         patch("src.agent.tools.settings") as mock_settings:
        mock_settings.fred_api_key = ""
        mock_settings.eia_api_key = ""
        result = fetch_data(tickers=["CL=F"], fred_series=["INDPRO"], context=ctx)

    assert "INDPRO" in result["skipped"]


def test_fetch_data_populates_context_signals(ctx):
    fake_wti = pd.Series([80.0] * 5, index=pd.date_range("2024-01-01", periods=5, freq="D"), name="CL=F")
    fake_spy = pd.Series([450.0] * 5, index=pd.date_range("2024-01-01", periods=5, freq="D"), name="SPY")

    def fake_fetch(ticker, start, end):
        return fake_wti if ticker == "CL=F" else fake_spy

    with patch("src.agent.tools.fetch_price_series", side_effect=fake_fetch):
        fetch_data(tickers=["CL=F", "SPY"], fred_series=[], context=ctx)

    assert "CL=F" in ctx.signals
    assert "SPY" in ctx.signals


# ── engineer_features tests ───────────────────────────────────────────────────

def test_engineer_features_returns_shape(ctx_with_signals):
    result = engineer_features(windows=[5, 20], lags=[1, 5], context=ctx_with_signals)

    assert "shape" in result
    assert result["shape"][1] > 0
    assert ctx_with_signals.features is not None


def test_engineer_features_raises_without_signals(ctx):
    with pytest.raises(ValueError, match="fetch_data"):
        engineer_features(windows=[5], lags=[1], context=ctx)


# ── run_tabpfn tests ──────────────────────────────────────────────────────────

def test_run_tabpfn_regime_returns_summary(ctx_with_features):
    test_idx = ctx_with_features.features.index[-40:]

    with patch("src.agent.tools.OilRegimeClassifier") as MockCls:
        inst = MockCls.return_value
        inst.predict.return_value = pd.Series(["range_bound"] * 40, index=test_idx, name="regime")
        inst.predict_proba.return_value = pd.DataFrame(
            {"range_bound": [0.8] * 40, "bust": [0.2] * 40}, index=test_idx
        )
        inst.uncertainty.return_value = pd.Series([0.5] * 40, index=test_idx, name="uncertainty")

        result = run_tabpfn(task="regime", horizon=20, context=ctx_with_features)

    assert result["task"] == "regime"
    assert "mean_confidence" in result
    assert "mean_entropy" in result
    assert "current_prediction" in result
    assert ctx_with_features.regime_result is not None


def test_run_tabpfn_direction_returns_summary(ctx_with_features):
    test_idx = ctx_with_features.features.index[-40:]

    with patch("src.agent.tools.DirectionClassifier") as MockCls:
        inst = MockCls.return_value
        inst.predict.return_value = pd.Series(["up"] * 40, index=test_idx, name="direction")
        inst.predict_proba.return_value = pd.DataFrame(
            {"up": [0.7] * 40, "down": [0.3] * 40}, index=test_idx
        )
        inst.uncertainty.return_value = pd.Series([0.6] * 40, index=test_idx, name="uncertainty")

        result = run_tabpfn(task="direction", horizon=20, context=ctx_with_features)

    assert result["task"] == "direction"
    assert "mean_confidence" in result
    assert ctx_with_features.direction_result is not None


def test_run_tabpfn_raises_without_features(ctx):
    with pytest.raises(ValueError, match="engineer_features"):
        run_tabpfn(task="regime", horizon=20, context=ctx)


def test_run_tabpfn_raises_without_wti_signal(ctx):
    ctx.features = pd.DataFrame(
        np.random.randn(100, 3),
        index=pd.date_range("2024-01-01", periods=100, freq="D"),
        columns=["f1", "f2", "f3"],
    )
    with pytest.raises(ValueError, match="CL=F"):
        run_tabpfn(task="regime", horizon=20, context=ctx)


# ── explain_prediction tests ──────────────────────────────────────────────────

def test_explain_prediction_returns_structured_dict(ctx):
    result = explain_prediction(
        regime="bust",
        direction="down",
        confidence=0.82,
        key_features=["wti_ret_60", "eia_inventory_slope"],
        context=ctx,
    )

    assert result["regime"] == "bust"
    assert result["direction"] == "down"
    assert result["confidence"] == 0.82
    assert result["key_features"] == ["wti_ret_60", "eia_inventory_slope"]
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
cd backend && uv run pytest tests/test_agent_tools.py -v -k "fetch_data or engineer_features or run_tabpfn or explain_prediction"
```

Expected: `ImportError` — `src.agent.tools` does not exist.

- [ ] **Step 3: Implement `backend/src/agent/tools.py`**

```python
from __future__ import annotations

import pandas as pd
from dataclasses import dataclass, field
from typing import Any

from src.agent.registry import registry
from src.config import settings
from src.data.connectors import fetch_fred_series, fetch_price_series
from src.featurizer import TimeSeriesFeaturizer
from src.inference import DirectionClassifier, OilRegimeClassifier

# Hand-labeled historical regime periods (same as demo.py — source of truth).
_KNOWN_REGIMES: list[tuple[str, str, str]] = [
    ("2014-07-01", "2016-12-31", "bust"),
    ("2020-02-01", "2020-10-31", "bust"),
    ("2021-01-01", "2022-06-30", "bull_supercycle"),
    ("2022-02-01", "2022-04-30", "geopolitical_spike"),
    ("2023-10-01", "2023-12-31", "geopolitical_spike"),
]


@dataclass
class AgentContext:
    date_range_start: str
    date_range_end: str
    signals: dict[str, pd.Series] = field(default_factory=dict)
    features: pd.DataFrame | None = None
    regime_result: dict[str, Any] | None = None
    direction_result: dict[str, Any] | None = None


def _make_regime_labels(wti: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    wti_daily = wti.reindex(index, method="ffill")
    ret5 = wti_daily.pct_change(5)
    ret60 = wti_daily.pct_change(60)
    labels = pd.Series("range_bound", index=index, name="regime")
    labels[ret60 > 0.15] = "bull_supercycle"
    labels[ret60 < -0.15] = "bust"
    labels[ret5 > 0.08] = "geopolitical_spike"
    for start, end, regime in _KNOWN_REGIMES:
        mask = (index >= start) & (index <= end)
        labels[mask] = regime
    return labels


def _make_direction_labels(wti: pd.Series, index: pd.DatetimeIndex, horizon: int = 20) -> pd.Series:
    wti_daily = wti.reindex(index, method="ffill")
    forward_ret = wti_daily.shift(-horizon) / wti_daily - 1
    forward_ret = forward_ret.dropna()
    labels = forward_ret.map(lambda r: "up" if r > 0 else "down")
    labels.name = "direction"
    return labels


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "yfinance ticker symbols, e.g. ['CL=F', 'DX-Y.NYB', 'XLE', 'SPY']",
            },
            "fred_series": {
                "type": "array",
                "items": {"type": "string"},
                "description": "FRED series IDs, e.g. ['INDPRO']. Skipped if FRED_API_KEY not set.",
            },
        },
        "required": ["tickers", "fred_series"],
    }
)
def fetch_data(tickers: list[str], fred_series: list[str], context: AgentContext) -> dict[str, Any]:
    """Fetch price series from yfinance and macro series from FRED."""
    fetched: dict[str, int] = {}
    skipped: list[str] = []

    for ticker in tickers:
        series = fetch_price_series(ticker, context.date_range_start, context.date_range_end)
        context.signals[ticker] = series
        fetched[ticker] = len(series)

    for series_id in fred_series:
        if not settings.fred_api_key:
            skipped.append(series_id)
            continue
        series = fetch_fred_series(series_id, context.date_range_start, context.date_range_end, api_key=settings.fred_api_key)
        context.signals[series_id] = series
        fetched[series_id] = len(series)

    return {"fetched": fetched, "skipped": skipped}


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "windows": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Rolling window sizes in days, e.g. [5, 20, 60]",
            },
            "lags": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Lag periods in days, e.g. [1, 5, 20]",
            },
        },
        "required": ["windows", "lags"],
    }
)
def engineer_features(windows: list[int], lags: list[int], context: AgentContext) -> dict[str, Any]:
    """Featurize the fetched signals into a tabular feature matrix."""
    if not context.signals:
        raise ValueError("No signals in context. Call fetch_data first.")
    featurizer = TimeSeriesFeaturizer(windows=windows, lags=lags)
    features = featurizer.transform(context.signals)
    context.features = features
    start = str(features.index[0].date())
    end = str(features.index[-1].date())
    return {"shape": list(features.shape), "date_range": [start, end]}


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "enum": ["regime", "direction"],
                "description": "'regime' for OilRegimeClassifier, 'direction' for DirectionClassifier",
            },
            "horizon": {
                "type": "integer",
                "description": "Forward-return horizon in trading days for direction labels (ignored for regime)",
                "default": 20,
            },
        },
        "required": ["task"],
    }
)
def run_tabpfn(task: str, horizon: int = 20, context: AgentContext | None = None) -> dict[str, Any]:
    """Run TabPFN classification for regime or price direction."""
    if context is None or context.features is None:
        raise ValueError("No features in context. Call engineer_features first.")
    if "CL=F" not in context.signals:
        raise ValueError("WTI price series ('CL=F') not found in context.signals. Call fetch_data with tickers=['CL=F', ...].")

    features = context.features.dropna()
    wti = context.signals["CL=F"]

    if task == "regime":
        labels = _make_regime_labels(wti, features.index)
        split = int(len(features) * 0.8)
        X_train, X_test = features.iloc[:split], features.iloc[split:]
        y_train = labels.iloc[:split]
        clf = OilRegimeClassifier(n_estimators=8)
        clf.fit(X_train, y_train)
        pred = clf.predict(X_test)
        proba = clf.predict_proba(X_test)
        uncertainty = clf.uncertainty(X_test)
        mean_conf = float(proba.max(axis=1).mean())
        mean_entropy = float(uncertainty.mean())
        current = str(pred.iloc[-1])
        distribution = pred.value_counts().to_dict()
        context.regime_result = {
            "regime": current,
            "confidence": mean_conf,
            "entropy": mean_entropy,
            "distribution": {str(k): int(v) for k, v in distribution.items()},
        }
        return {
            "task": "regime",
            "current_prediction": current,
            "mean_confidence": mean_conf,
            "mean_entropy": mean_entropy,
            "test_size": len(X_test),
            "label_distribution": {str(k): int(v) for k, v in distribution.items()},
        }

    # direction
    direction_labels = _make_direction_labels(wti, features.index, horizon=horizon)
    common_idx = features.index.intersection(direction_labels.index)
    features_dir = features.loc[common_idx]
    labels_dir = direction_labels.loc[common_idx]
    split = int(len(features_dir) * 0.8)
    X_train, X_test = features_dir.iloc[:split], features_dir.iloc[split:]
    y_train = labels_dir.iloc[:split]
    clf = DirectionClassifier(n_estimators=8)
    clf.fit(X_train, y_train)
    pred = clf.predict(X_test)
    proba = clf.predict_proba(X_test)
    uncertainty = clf.uncertainty(X_test)
    mean_conf = float(proba.max(axis=1).mean())
    mean_entropy = float(uncertainty.mean())
    current = str(pred.iloc[-1])
    distribution = pred.value_counts().to_dict()
    context.direction_result = {
        "direction": current,
        "confidence": mean_conf,
        "entropy": mean_entropy,
        "distribution": {str(k): int(v) for k, v in distribution.items()},
    }
    return {
        "task": "direction",
        "current_prediction": current,
        "mean_confidence": mean_conf,
        "mean_entropy": mean_entropy,
        "test_size": len(X_test),
        "label_distribution": {str(k): int(v) for k, v in distribution.items()},
    }


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "regime": {"type": "string", "description": "Predicted regime label"},
            "direction": {"type": "string", "description": "Predicted price direction ('up' or 'down')"},
            "confidence": {"type": "number", "description": "Mean confidence score 0–1"},
            "key_features": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Feature names most relevant to this prediction",
            },
        },
        "required": ["regime", "direction", "confidence", "key_features"],
    }
)
def explain_prediction(
    regime: str,
    direction: str,
    confidence: float,
    key_features: list[str],
    context: AgentContext | None = None,
) -> dict[str, Any]:
    """Assemble prediction inputs for the agent's final narrative explanation."""
    return {
        "regime": regime,
        "direction": direction,
        "confidence": confidence,
        "key_features": key_features,
    }
```

- [ ] **Step 4: Run tests, confirm they PASS**

```bash
cd backend && uv run pytest tests/test_agent_tools.py -v
```

Expected: all tests pass (registry + tool tests).

- [ ] **Step 5: Run lint and type check**

```bash
cd backend && uv run ruff check src/agent/tools.py src/agent/registry.py && uv run mypy src/agent/tools.py src/agent/registry.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agent/tools.py backend/tests/test_agent_tools.py
git commit -m "feat: add AgentContext and 4 tool functions with tool registry"
```

---

## Task 4: ReAct loop

**Files:**
- Create: `backend/src/agent/loop.py`

- [ ] **Step 1: Implement `backend/src/agent/loop.py`**

```python
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

import openai
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.registry import registry
from src.agent.tools import AgentContext
from src.config import settings
from src.db.models import Run, RunStatus
from src.db.session import engine

SYSTEM_PROMPT = """You are an oil market intelligence analyst. You have access to tools \
to fetch market data, engineer features, run TabPFN classification, and explain predictions.

Given a date range and analysis tasks, use the tools in this order:
1. fetch_data — pull WTI (CL=F), DXY (DX-Y.NYB), XLE, SPY price series and INDPRO macro data
2. engineer_features — featurize with windows [5, 20, 60] and lags [1, 5, 20]
3. run_tabpfn with task="regime" — classify the current oil market regime
4. run_tabpfn with task="direction" — predict WTI price direction over the next 20 trading days
5. explain_prediction — pass the regime, direction, confidence, and 2-3 key feature names

After calling explain_prediction, write a concise natural language summary (3-5 sentences) \
grounded in the actual confidence scores and feature values returned by the tools."""

MAX_ITERATIONS = 10


async def _publish(redis_client: aioredis.Redis, channel: str, message: dict) -> None:
    await redis_client.publish(channel, json.dumps(message, default=str))


async def run_agent_loop(
    run_id: uuid.UUID,
    date_range_start: str,
    date_range_end: str,
    tasks: list[str],
) -> None:
    """Drive the ReAct loop for one analysis run.

    Accepts primitive fields (not AnalyzeRequest) to avoid a circular import
    between src.agent.loop and api.routes.analyze.

    Creates its own DB session and Redis connection — must not reuse the
    HTTP request's session, which is closed once the response is sent.
    """
    redis_client: aioredis.Redis = aioredis.from_url(settings.redis_url)
    openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    channel = f"run:{run_id}"

    async with AsyncSession(engine) as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        run.status = RunStatus.RUNNING
        await session.commit()

    context = AgentContext(
        date_range_start=date_range_start,
        date_range_end=date_range_end,
    )

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Analyze {date_range_start} to {date_range_end}. "
                f"Tasks: {tasks}"
            ),
        },
    ]

    last_text = ""
    try:
        for _ in range(MAX_ITERATIONS):
            response = await openai_client.chat.completions.create(
                model=settings.agent_model,
                tools=registry.schemas(),
                messages=messages,
            )
            choice = response.choices[0]

            if choice.message.content:
                last_text = choice.message.content
                await _publish(redis_client, channel, {"type": "thought", "content": last_text})

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                assistant_msg: dict = {
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in choice.message.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                for tc in choice.message.tool_calls:
                    name = tc.function.name
                    arguments = json.loads(tc.function.arguments)
                    await _publish(redis_client, channel, {"type": "tool_call", "tool": name, "input": arguments})
                    result = await asyncio.to_thread(registry.dispatch, name, arguments, context)
                    await _publish(redis_client, channel, {"type": "tool_result", "tool": name, "output": result})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    })
            else:
                break

        await _publish(redis_client, channel, {"type": "done", "summary": last_text})

        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.COMPLETED
                run.completed_at = datetime.now(UTC).replace(tzinfo=None)
                run.result = {
                    "regime": context.regime_result,
                    "direction": context.direction_result,
                    "summary": last_text,
                }
                await session.commit()

    except Exception as exc:
        await _publish(redis_client, channel, {"type": "error", "message": str(exc)})
        async with AsyncSession(engine) as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.FAILED
                run.error = str(exc)
                await session.commit()

    finally:
        await redis_client.aclose()
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd backend && uv run python -c "from src.agent.loop import run_agent_loop; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Add smoke test to `backend/tests/test_agent_tools.py`**

Append to the file:

```python
# ── Smoke test (requires OPENAI_API_KEY) ──────────────────────────────────────

@pytest.mark.skipif(
    not settings.openai_api_key,
    reason="OPENAI_API_KEY not set — skipping live agent loop smoke test",
)
async def test_full_loop_smoke():
    """Runs the real agent loop end-to-end against the OpenAI API."""
    import uuid
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.agent.loop import run_agent_loop

    run_id = uuid.uuid4()

    mock_run = MagicMock()
    mock_run.id = run_id

    with patch("src.agent.loop.AsyncSession") as MockSession, \
         patch("src.agent.loop.aioredis.from_url") as mock_redis_factory:
        mock_session_ctx = AsyncMock()
        mock_session_ctx.get.return_value = mock_run
        MockSession.return_value.__aenter__.return_value = mock_session_ctx

        mock_redis = AsyncMock()
        mock_redis_factory.return_value = mock_redis

        await run_agent_loop(
            run_id,
            "2023-01-01",
            "2023-06-30",
            ["regime_classification", "price_direction"],
        )

    assert mock_run.status is not None
```

- [ ] **Step 4: Run tests (smoke test skipped without API key)**

```bash
cd backend && uv run pytest tests/test_agent_tools.py -v
```

Expected: all previous tests pass, smoke test skipped.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/loop.py backend/tests/test_agent_tools.py
git commit -m "feat: add async ReAct loop with OpenAI tool use and Redis pub/sub"
```

---

## Task 5: Update `__init__.py` and wire analyze route

**Files:**
- Modify: `backend/src/agent/__init__.py`
- Modify: `backend/api/routes/analyze.py`
- Create: `backend/tests/test_analyze_route.py`

- [ ] **Step 1: Write the failing analyze route test**

Create `backend/tests/test_analyze_route.py`:

```python
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.db import get_session


@pytest.fixture
def client_with_mock_db():
    """TestClient with DB session dependency overridden by an AsyncMock."""
    async def override_get_session():
        # Run.id is set by default_factory=uuid.uuid4 at construction time,
        # so the mock session just needs to not raise.
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_analyze_returns_run_id(client_with_mock_db):
    with patch("api.routes.analyze.run_agent_loop"):
        response = client_with_mock_db.post(
            "/api/analyze",
            json={"date_range_start": "2024-01-01", "date_range_end": "2024-12-31"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert len(data["run_id"]) == 36  # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx


def test_analyze_accepts_custom_tasks(client_with_mock_db):
    with patch("api.routes.analyze.run_agent_loop"):
        response = client_with_mock_db.post(
            "/api/analyze",
            json={
                "date_range_start": "2024-01-01",
                "date_range_end": "2024-12-31",
                "tasks": ["regime_classification"],
            },
        )

    assert response.status_code == 200


def test_analyze_rejects_missing_dates(client_with_mock_db):
    response = client_with_mock_db.post("/api/analyze", json={})
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests, confirm they FAIL**

```bash
cd backend && uv run pytest tests/test_analyze_route.py -v
```

Expected: tests fail — the route still raises 501.

- [ ] **Step 3: Update `backend/src/agent/__init__.py`**

```python
from src.agent.loop import run_agent_loop

__all__ = ["run_agent_loop"]
```

- [ ] **Step 4: Update `backend/api/routes/analyze.py`**

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import RunResult
from src.agent import run_agent_loop
from src.db import Run, get_session

router = APIRouter(tags=["analyze"])


class AnalyzeRequest(BaseModel):
    date_range_start: str
    date_range_end: str
    tasks: list[str] = ["regime_classification", "price_direction", "equity_outperformance"]


class AnalyzeResponse(BaseModel):
    run_id: str


@router.post("/analyze", response_model=AnalyzeResponse)
async def trigger_analysis(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> AnalyzeResponse:
    run = Run(
        date_range_start=request.date_range_start,
        date_range_end=request.date_range_end,
        tasks=request.tasks,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    background_tasks.add_task(
        run_agent_loop,
        run.id,
        request.date_range_start,
        request.date_range_end,
        request.tasks,
    )
    return AnalyzeResponse(run_id=str(run.id))


@router.get("/runs/{run_id}", response_model=RunResult)
async def get_run(run_id: str) -> RunResult:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run storage is not implemented yet.",
    )
```

- [ ] **Step 5: Run tests, confirm they PASS**

```bash
cd backend && uv run pytest tests/test_analyze_route.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Run full test suite**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Run lint and type check**

```bash
cd backend && uv run ruff check src/agent/ api/routes/analyze.py && uv run mypy src/agent/ api/routes/analyze.py
```

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/src/agent/__init__.py backend/api/routes/analyze.py backend/tests/test_analyze_route.py
git commit -m "feat: wire analyze route to run_agent_loop background task"
```

---

## Next Sessions

| Session | Focus |
|---|---|
| Session 5 | Wire `GET /runs/{run_id}` + `GET /history`, WebSocket Redis subscriber, deferred tools (`detect_drift`, `backtest`, `evaluate_features`, `fetch_geopolitical_risk`) |
| Session 6 | Frontend — RegimeDashboard + AgentStream components |
