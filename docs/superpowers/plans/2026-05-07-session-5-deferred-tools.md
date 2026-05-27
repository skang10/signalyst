# Session 5 — Deferred Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four deferred agent tools (`fetch_geopolitical_risk`, `detect_drift`, `evaluate_features`, `backtest`) plus the modules they depend on, then wire them into the ReAct loop system prompt and `run.result`.

**Architecture:** New domain modules (`src/data/gpr.py`, `src/eval/backtest.py`) handle non-trivial logic; `src/agent/tools.py` holds thin tool wrappers. `AgentContext` gets new fields so each tool can read prior state without refitting. `loop.py` system prompt is extended to include all 9 steps and `run.result` is extended to persist all new outputs.

**Tech Stack:** Python 3.12, pandas, numpy, scipy (KS test), openpyxl (GPR `.xls` parsing), tabpfn-extensions (SHAP), existing `OilRegimeClassifier`/`DirectionClassifier`, pytest with `unittest.mock`.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/src/data/gpr.py` | GPR fetch + module-level TTL cache |
| Create | `backend/src/eval/backtest.py` | Walk-forward backtest engine |
| Modify | `backend/src/agent/tools.py` | 4 new tools, 2 helpers, `AgentContext` extensions, `run_tabpfn` + `fetch_data` updates |
| Modify | `backend/src/agent/loop.py` | System prompt (9 steps), `run.result` (all 5 new fields) |
| Modify | `backend/src/config.py` | `gpr_data_url`, `gpr_cache_ttl_hours` settings |
| Modify | `backend/pyproject.toml` | `openpyxl`, `tabpfn-extensions`, `scipy` dependencies |
| Modify | `.env.example` | Document `GPR_DATA_URL`, `GPR_CACHE_TTL_HOURS` |
| Create | `backend/tests/test_gpr_connector.py` | Tests for `fetch_gpr_series` |
| Create | `backend/tests/test_backtest.py` | Tests for `walk_forward_backtest` |
| Create | `backend/tests/test_deferred_tools.py` | Tests for all 4 new tools and `AgentContext` extensions |

---

## Task 1: Config, dependencies, and `.env.example`

**Files:**
- Modify: `backend/src/config.py`
- Modify: `backend/pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_config.py` (file already exists; append these two tests):

```python
def test_settings_has_gpr_data_url():
    from src.config import settings
    assert settings.gpr_data_url == "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"


def test_settings_has_gpr_cache_ttl_hours():
    from src.config import settings
    assert settings.gpr_cache_ttl_hours == 24
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_config.py::test_settings_has_gpr_data_url tests/test_config.py::test_settings_has_gpr_cache_ttl_hours -v
```

Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add settings to `src/config.py`**

Add these two lines inside the `Settings` class, after the `sentry_dsn` field:

```python
    gpr_data_url: str = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
    gpr_cache_ttl_hours: int = 24
```

- [ ] **Step 4: Add dependencies to `backend/pyproject.toml`**

In the `dependencies` list under the `# Data sources` block, append:

```toml
    "openpyxl>=3.1.0",
    "scipy>=1.11.0",
```

In the `dependencies` list under the `# ML` block, append:

```toml
    "tabpfn-extensions>=0.0.14",
```

- [ ] **Step 5: Document new env vars in `.env.example`**

Append to `.env.example` (after `TABPFN_TOKEN` line):

```
# GPR data (optional overrides)
GPR_DATA_URL=
GPR_CACHE_TTL_HOURS=
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_config.py::test_settings_has_gpr_data_url tests/test_config.py::test_settings_has_gpr_cache_ttl_hours -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/src/config.py backend/pyproject.toml .env.example backend/tests/test_config.py
git commit -m "feat: add GPR settings and session-5 dependencies"
```

---

## Task 2: GPR data connector (`src/data/gpr.py`)

**Files:**
- Create: `backend/src/data/gpr.py`
- Create: `backend/tests/test_gpr_connector.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_gpr_connector.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.data.gpr import _GPR_CACHE, fetch_gpr_series


def _excel_bytes(n_rows: int = 30) -> bytes:
    dates = pd.date_range("2023-01-01", periods=n_rows, freq="D")
    df = pd.DataFrame({"date": dates, "GPRD": np.linspace(80, 120, n_rows)})
    buf = BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def clear_cache():
    _GPR_CACHE.clear()
    yield
    _GPR_CACHE.clear()


def test_fetch_gpr_series_returns_series_named_gpr():
    mock_resp = MagicMock()
    mock_resp.content = _excel_bytes(30)
    with patch("src.data.gpr.requests.get", return_value=mock_resp):
        result = fetch_gpr_series("2023-01-05", "2023-01-15")
    assert result.name == "GPR"
    assert isinstance(result.index, pd.DatetimeIndex)


def test_fetch_gpr_series_trims_to_date_range():
    mock_resp = MagicMock()
    mock_resp.content = _excel_bytes(30)
    with patch("src.data.gpr.requests.get", return_value=mock_resp):
        result = fetch_gpr_series("2023-01-05", "2023-01-15")
    assert all(result.index >= pd.Timestamp("2023-01-05"))
    assert all(result.index <= pd.Timestamp("2023-01-15"))


def test_fetch_gpr_series_caches_on_first_call():
    mock_resp = MagicMock()
    mock_resp.content = _excel_bytes(30)
    with patch("src.data.gpr.requests.get", return_value=mock_resp) as mock_get:
        fetch_gpr_series("2023-01-01", "2023-01-10")
        fetch_gpr_series("2023-01-01", "2023-01-10")
    assert mock_get.call_count == 1


def test_fetch_gpr_series_bypasses_stale_cache():
    stale_time = datetime.now() - timedelta(hours=25)
    _GPR_CACHE["gpr"] = (stale_time, pd.Series([], name="GPR", dtype=float))
    mock_resp = MagicMock()
    mock_resp.content = _excel_bytes(30)
    with patch("src.data.gpr.requests.get", return_value=mock_resp) as mock_get:
        fetch_gpr_series("2023-01-01", "2023-01-10")
    assert mock_get.call_count == 1


def test_fetch_gpr_series_raises_on_missing_gprd_column():
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    df = pd.DataFrame({"date": dates, "WRONG": [1, 2, 3, 4, 5]})
    buf = BytesIO()
    df.to_excel(buf, index=False)
    mock_resp = MagicMock()
    mock_resp.content = buf.getvalue()
    with (
        patch("src.data.gpr.requests.get", return_value=mock_resp),
        pytest.raises(ValueError, match="schema"),
    ):
        fetch_gpr_series("2023-01-01", "2023-01-05")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_gpr_connector.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.data.gpr'`

- [ ] **Step 3: Create `backend/src/data/gpr.py`**

```python
from __future__ import annotations

import datetime
from io import BytesIO

import pandas as pd
import requests

from src.config import settings

_GPR_CACHE: dict[str, tuple[datetime.datetime, pd.Series]] = {}


def fetch_gpr_series(start: str, end: str) -> pd.Series:
    """Fetch daily GPR index from Matteo Iacoviello's page.

    Returns a pd.Series named 'GPR', DatetimeIndex named 'date', trimmed to [start, end].
    Results are cached in-process for `settings.gpr_cache_ttl_hours` hours.
    """
    now = datetime.datetime.now()
    ttl = datetime.timedelta(hours=settings.gpr_cache_ttl_hours)

    if "gpr" in _GPR_CACHE:
        cached_at, full_series = _GPR_CACHE["gpr"]
        if now - cached_at < ttl:
            return full_series.loc[start:end]

    response = requests.get(settings.gpr_data_url, timeout=30)
    response.raise_for_status()

    df = pd.read_excel(BytesIO(response.content), engine="openpyxl")

    if not {"date", "GPRD"}.issubset(df.columns):
        raise ValueError(
            f"GPR data schema changed. Expected columns {{'date', 'GPRD'}}, got {set(df.columns)}"
        )

    df["date"] = pd.to_datetime(df["date"])
    full_series = df.set_index("date")["GPRD"].rename("GPR")
    full_series.index.name = "date"

    _GPR_CACHE["gpr"] = (now, full_series)

    return full_series.loc[start:end]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_gpr_connector.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/src/data/gpr.py backend/tests/test_gpr_connector.py
git commit -m "feat: add GPR data connector with TTL cache"
```

---

## Task 3: Walk-forward backtest engine (`src/eval/backtest.py`)

**Files:**
- Create: `backend/src/eval/backtest.py`
- Create: `backend/tests/test_backtest.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_backtest.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.eval.backtest import _annualised_sharpe, walk_forward_backtest


def _make_data(n: int = 300) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    np.random.seed(42)
    features = pd.DataFrame(
        np.random.randn(n, 5), index=dates, columns=[f"f{i}" for i in range(5)]
    )
    wti = pd.Series(np.linspace(50, 80, n) + np.random.randn(n), index=dates, name="CL=F")
    spy = pd.Series(np.linspace(300, 400, n) + np.random.randn(n), index=dates, name="SPY")
    return features, wti, spy


def _mock_clf(default_label: str) -> MagicMock:
    clf = MagicMock()
    clf.fit.return_value = None
    clf.predict.side_effect = lambda X: pd.Series(default_label, index=X.index)
    return clf


def test_walk_forward_backtest_returns_required_keys():
    features, wti, spy = _make_data()
    with (
        patch("src.eval.backtest.OilRegimeClassifier", return_value=_mock_clf("range_bound")),
        patch("src.eval.backtest.DirectionClassifier", return_value=_mock_clf("up")),
    ):
        result = walk_forward_backtest(features, wti, spy, horizon=20, step=20, min_train=120)

    assert set(result.keys()) == {
        "regime_accuracy",
        "strategy_sharpe",
        "benchmark_sharpe",
        "n_windows",
        "date_range",
    }


def test_walk_forward_backtest_produces_multiple_windows():
    features, wti, spy = _make_data()
    with (
        patch("src.eval.backtest.OilRegimeClassifier", return_value=_mock_clf("range_bound")),
        patch("src.eval.backtest.DirectionClassifier", return_value=_mock_clf("up")),
    ):
        result = walk_forward_backtest(features, wti, spy, horizon=20, step=20, min_train=120)

    assert result["n_windows"] > 0


def test_walk_forward_backtest_sharpes_are_floats():
    features, wti, spy = _make_data()
    with (
        patch("src.eval.backtest.OilRegimeClassifier", return_value=_mock_clf("range_bound")),
        patch("src.eval.backtest.DirectionClassifier", return_value=_mock_clf("up")),
    ):
        result = walk_forward_backtest(features, wti, spy, horizon=20, step=20, min_train=120)

    assert isinstance(result["strategy_sharpe"], float)
    assert isinstance(result["benchmark_sharpe"], float)


def test_annualised_sharpe_zero_for_constant_returns():
    assert _annualised_sharpe([0.01, 0.01, 0.01]) == 0.0


def test_annualised_sharpe_positive_for_mostly_positive_returns():
    returns = [0.01] * 50 + [-0.001] * 5
    assert _annualised_sharpe(returns) > 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_backtest.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.eval.backtest'`

- [ ] **Step 3: Create `backend/src/eval/backtest.py`**

```python
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.agent.tools import _make_direction_labels, _make_regime_labels
from src.inference import DirectionClassifier, OilRegimeClassifier


def _annualised_sharpe(returns: list[float]) -> float:
    s = pd.Series(returns).dropna()
    if s.std() == 0:
        return 0.0
    return float((s.mean() / s.std()) * (252**0.5))


def walk_forward_backtest(
    features: pd.DataFrame,
    wti: pd.Series,
    spy: pd.Series,
    horizon: int = 20,
    step: int = 20,
    min_train: int = 120,
) -> dict[str, Any]:
    """Walk-forward evaluation using an expanding window.

    Returns regime accuracy, strategy Sharpe (long WTI on 'up' signal, flat otherwise),
    benchmark Sharpe (buy-and-hold SPY), window count, and date range.
    """
    regime_labels = _make_regime_labels(wti, features.index)
    direction_labels = _make_direction_labels(wti, features.index, horizon=horizon)

    regime_correct = 0
    regime_total = 0
    strategy_returns: list[float] = []
    spy_returns: list[float] = []
    n_windows = 0

    for t in range(min_train, len(features) - horizon, step):
        X_train = features.iloc[:t]
        X_test = features.iloc[t : t + horizon]
        y_regime_train = regime_labels.iloc[:t]
        y_regime_test = regime_labels.iloc[t : t + horizon]
        y_dir_train = direction_labels.reindex(X_train.index).dropna()
        y_dir_test = direction_labels.reindex(X_test.index).dropna()

        # Regime accuracy
        clf = OilRegimeClassifier(n_estimators=8)
        clf.fit(X_train, y_regime_train)
        preds = clf.predict(X_test)
        regime_correct += int((preds == y_regime_test).sum())
        regime_total += len(y_regime_test)

        # Direction strategy returns
        if len(y_dir_train) > 0 and len(y_dir_test) > 0:
            dir_clf = DirectionClassifier(n_estimators=8)
            dir_clf.fit(X_train.loc[y_dir_train.index], y_dir_train)
            pred_dir = dir_clf.predict(X_test.loc[y_dir_test.index])
            wti_ret = wti.pct_change().reindex(y_dir_test.index)
            strategy_returns.extend(wti_ret.where(pred_dir == "up", 0).tolist())
            spy_ret = spy.pct_change().reindex(y_dir_test.index)
            spy_returns.extend(spy_ret.tolist())

        n_windows += 1

    regime_accuracy = regime_correct / regime_total if regime_total > 0 else 0.0

    return {
        "regime_accuracy": round(regime_accuracy, 4),
        "strategy_sharpe": _annualised_sharpe(strategy_returns),
        "benchmark_sharpe": _annualised_sharpe(spy_returns),
        "n_windows": n_windows,
        "date_range": [str(features.index[0].date()), str(features.index[-1].date())],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_backtest.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/src/eval/backtest.py backend/tests/test_backtest.py
git commit -m "feat: add walk-forward backtest engine"
```

---

## Task 4: Extend `AgentContext`, update `run_tabpfn` and `fetch_data`

**Files:**
- Modify: `backend/src/agent/tools.py` (lines 24–31 for `AgentContext`, lines 162–188 for `run_tabpfn` regime path, lines 75–98 for `fetch_data`)
- Create: `backend/tests/test_deferred_tools.py` (partial — just the AgentContext and run_tabpfn tests for now)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_deferred_tools.py` with this content:

```python
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from src.agent.tools import AgentContext, fetch_data, run_tabpfn


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def ctx():
    return AgentContext(date_range_start="2022-01-01", date_range_end="2022-12-31")


@pytest.fixture
def ctx_with_features(ctx):
    n = 200
    dates = pd.date_range("2022-03-01", periods=n, freq="B")
    ctx.signals["CL=F"] = pd.Series(np.linspace(70, 90, n), index=dates, name="CL=F")
    ctx.features = pd.DataFrame(
        np.random.randn(n, 5),
        index=dates,
        columns=["f1", "f2", "f3", "f4", "f5"],
    )
    return ctx


# ── AgentContext new fields ────────────────────────────────────────────────────


def test_agent_context_has_new_fields(ctx):
    assert ctx.backtest_result is None
    assert ctx.drift_result is None
    assert ctx.shap_result is None
    assert ctx._regime_clf is None
    assert ctx._regime_X_test is None
    assert ctx._regime_y_test is None
    assert ctx.data_manifest == {}


# ── run_tabpfn stores classifier and test split ────────────────────────────────


def test_run_tabpfn_regime_stores_clf_and_test_split(ctx_with_features):
    test_idx = ctx_with_features.features.index[-40:]

    with patch("src.agent.tools.OilRegimeClassifier") as MockCls:
        inst = MockCls.return_value
        inst.predict.return_value = pd.Series("range_bound", index=test_idx, name="regime")
        inst.predict_proba.return_value = pd.DataFrame(
            {"range_bound": [0.8] * 40}, index=test_idx
        )
        inst.uncertainty.return_value = pd.Series([0.5] * 40, index=test_idx)

        run_tabpfn(task="regime", context=ctx_with_features)

    assert ctx_with_features._regime_clf is not None
    assert ctx_with_features._regime_X_test is not None
    assert ctx_with_features._regime_y_test is not None


# ── fetch_data writes to data_manifest ────────────────────────────────────────


def test_fetch_data_writes_to_data_manifest(ctx):
    fake_series = pd.Series(
        [70.0] * 5,
        index=pd.date_range("2022-01-01", periods=5, freq="D"),
        name="CL=F",
    )
    with patch("src.agent.tools.fetch_price_series", return_value=fake_series):
        fetch_data(tickers=["CL=F"], fred_series=[], context=ctx)

    assert "data_sources" in ctx.data_manifest
    assert "CL=F" in ctx.data_manifest["data_sources"]
    entry = ctx.data_manifest["data_sources"]["CL=F"]
    assert entry["rows"] == 5
    assert entry["provider"] == "yfinance"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_agent_context_has_new_fields tests/test_deferred_tools.py::test_run_tabpfn_regime_stores_clf_and_test_split tests/test_deferred_tools.py::test_fetch_data_writes_to_data_manifest -v
```

Expected: FAIL (`AttributeError` on `ctx.backtest_result` etc.)

- [ ] **Step 3: Extend `AgentContext` in `backend/src/agent/tools.py`**

Replace the `AgentContext` dataclass (lines 24–31):

```python
@dataclass
class AgentContext:
    date_range_start: str
    date_range_end: str
    signals: dict[str, pd.Series] = field(default_factory=dict)
    features: pd.DataFrame | None = None
    regime_result: dict[str, Any] | None = None
    direction_result: dict[str, Any] | None = None
    backtest_result: dict[str, Any] | None = None
    drift_result: dict[str, Any] | None = None
    shap_result: dict[str, Any] | None = None
    _regime_clf: Any | None = None
    _regime_X_test: pd.DataFrame | None = None
    _regime_y_test: pd.Series | None = None
    data_manifest: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Update `fetch_data` to write the data manifest**

In `fetch_data`, after `context.signals[ticker] = series` and `fetched[ticker] = len(series)`, add:

```python
        context.data_manifest.setdefault("data_sources", {})[ticker] = {
            "rows": len(series),
            "start": context.date_range_start,
            "end": context.date_range_end,
            "provider": "yfinance",
        }
```

After `context.signals[series_id] = series` and `fetched[series_id] = len(series)` in the FRED loop, add:

```python
        context.data_manifest.setdefault("data_sources", {})[series_id] = {
            "rows": len(series),
            "start": context.date_range_start,
            "end": context.date_range_end,
            "provider": "fredapi",
        }
```

- [ ] **Step 5: Update `run_tabpfn` regime path to store classifier and test split**

In `run_tabpfn`, in the `if task == "regime":` block, after `regime_clf = OilRegimeClassifier(n_estimators=8)` and `regime_clf.fit(X_train, y_train)`, add:

```python
        context._regime_clf = regime_clf
        context._regime_X_test = X_test
        context._regime_y_test = labels.iloc[split:]
```

The full updated regime block (replace starting at `if task == "regime":`):

```python
    if task == "regime":
        labels = _make_regime_labels(wti, features.index)
        split = int(len(features) * 0.8)
        X_train, X_test = features.iloc[:split], features.iloc[split:]
        y_train = labels.iloc[:split]
        regime_clf = OilRegimeClassifier(n_estimators=8)
        regime_clf.fit(X_train, y_train)
        context._regime_clf = regime_clf
        context._regime_X_test = X_test
        context._regime_y_test = labels.iloc[split:]
        pred = regime_clf.predict(X_test)
        proba = regime_clf.predict_proba(X_test)
        uncertainty = regime_clf.uncertainty(X_test)
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
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_agent_context_has_new_fields tests/test_deferred_tools.py::test_run_tabpfn_regime_stores_clf_and_test_split tests/test_deferred_tools.py::test_fetch_data_writes_to_data_manifest -v
```

Expected: 3 PASSED

- [ ] **Step 7: Run the full test suite to confirm no regressions**

```bash
cd backend && uv run pytest tests/test_agent_tools.py -v
```

Expected: all existing tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/src/agent/tools.py backend/tests/test_deferred_tools.py
git commit -m "feat: extend AgentContext with session-5 fields, store regime classifier in run_tabpfn, write data_manifest in fetch_data"
```

---

## Task 5: `detect_drift` tool

**Files:**
- Modify: `backend/src/agent/tools.py` (add `_psi` helper and `detect_drift` tool at the end)
- Modify: `backend/tests/test_deferred_tools.py` (append drift tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_deferred_tools.py`:

```python
# ── detect_drift ──────────────────────────────────────────────────────────────

from src.agent.tools import detect_drift  # noqa: E402


def test_detect_drift_flags_shifted_distribution(ctx):
    n = 100
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    np.random.seed(0)
    # f1: last 20% shifted by +10 (big shift), f2: random noise (no shift)
    data_f1 = np.concatenate([np.random.randn(80), np.random.randn(20) + 10])
    data_f2 = np.random.randn(n)
    ctx.features = pd.DataFrame({"f1": data_f1, "f2": data_f2}, index=dates)

    result = detect_drift(context=ctx)

    assert result["drift_detected"] is True
    assert "f1" in result["drifted_features"]
    assert ctx.drift_result is not None


def test_detect_drift_result_has_required_keys(ctx):
    n = 100
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    np.random.seed(0)
    ctx.features = pd.DataFrame(
        {"f1": np.random.randn(n), "f2": np.random.randn(n)}, index=dates
    )

    result = detect_drift(context=ctx)

    assert set(result.keys()) == {"drift_detected", "psi_score", "drifted_features", "ks_results"}
    assert isinstance(result["psi_score"], float)
    assert isinstance(result["ks_results"], dict)


def test_detect_drift_raises_without_features(ctx):
    from src.agent.tools import detect_drift
    with pytest.raises(ValueError, match="engineer_features"):
        detect_drift(context=ctx)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_detect_drift_flags_shifted_distribution tests/test_deferred_tools.py::test_detect_drift_result_has_required_keys tests/test_deferred_tools.py::test_detect_drift_raises_without_features -v
```

Expected: FAIL with `ImportError` (detect_drift not defined yet)

- [ ] **Step 3: Add `_psi` helper and `detect_drift` to `backend/src/agent/tools.py`**

Add at the top of `tools.py`, after `import pandas as pd`:

```python
import numpy as np
```

Then append to the end of `tools.py`:

```python
def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    """Population Stability Index between two distributions."""
    breakpoints = np.percentile(expected, np.linspace(0, 100, buckets + 1))
    expected_dist = np.histogram(expected, bins=breakpoints)[0] / len(expected)
    actual_dist = np.histogram(actual, bins=breakpoints)[0] / len(actual)
    expected_dist = np.clip(expected_dist, 1e-4, None)
    actual_dist = np.clip(actual_dist, 1e-4, None)
    return float(np.sum((actual_dist - expected_dist) * np.log(actual_dist / expected_dist)))


@registry.tool(
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    }
)
def detect_drift(context: AgentContext) -> dict[str, Any]:
    """Detect feature distribution drift between the historical (first 80%) and recent (last 20%) data."""
    if context.features is None:
        raise ValueError("No features in context. Call engineer_features first.")

    from scipy.stats import ks_2samp

    features = context.features.dropna()
    split = int(len(features) * 0.8)
    historical = features.iloc[:split]
    recent = features.iloc[split:]

    ks_results: dict[str, Any] = {}
    drifted: list[str] = []
    for col in features.columns:
        stat, pval = ks_2samp(historical[col].values, recent[col].values)
        ks_results[col] = {"statistic": round(float(stat), 4), "p_value": round(float(pval), 4)}
        if pval < 0.05:
            drifted.append(col)

    psi_score = float(
        np.mean([_psi(historical[col].values, recent[col].values) for col in features.columns])
    )

    context.drift_result = {
        "drift_detected": psi_score >= 0.1,
        "psi_score": round(psi_score, 4),
        "drifted_features": drifted,
        "ks_results": ks_results,
    }
    return context.drift_result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_detect_drift_flags_shifted_distribution tests/test_deferred_tools.py::test_detect_drift_result_has_required_keys tests/test_deferred_tools.py::test_detect_drift_raises_without_features -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/tools.py backend/tests/test_deferred_tools.py
git commit -m "feat: add detect_drift tool with KS test and PSI"
```

---

## Task 6: `evaluate_features` tool

**Files:**
- Modify: `backend/src/agent/tools.py` (append `_compute_shap_values` and `evaluate_features`)
- Modify: `backend/tests/test_deferred_tools.py` (append evaluate_features tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_deferred_tools.py`:

```python
# ── evaluate_features ─────────────────────────────────────────────────────────

from src.agent.tools import evaluate_features  # noqa: E402


def test_evaluate_features_returns_ranked_top_features(ctx):
    n_samples, n_features, n_classes = 20, 5, 3
    dates = pd.date_range("2022-01-01", periods=n_samples, freq="B")
    # Build fixed SHAP: feature index 2 has highest importance, index 0 second
    shap_vals = np.zeros((n_samples, n_features, n_classes))
    shap_vals[:, 2, :] = 1.0
    shap_vals[:, 0, :] = 0.5

    ctx._regime_clf = MagicMock()
    ctx._regime_X_test = pd.DataFrame(
        np.random.randn(n_samples, n_features),
        index=dates,
        columns=["f0", "f1", "f2", "f3", "f4"],
    )

    with patch("src.agent.tools._compute_shap_values", return_value=shap_vals):
        result = evaluate_features(top_n=3, context=ctx)

    assert len(result["top_features"]) == 3
    assert result["top_features"][0]["name"] == "f2"
    assert result["top_features"][1]["name"] == "f0"
    assert result["n_features_evaluated"] == 5
    assert ctx.shap_result is not None


def test_evaluate_features_raises_without_regime_clf(ctx):
    with pytest.raises(ValueError, match="run_tabpfn"):
        evaluate_features(context=ctx)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_evaluate_features_returns_ranked_top_features tests/test_deferred_tools.py::test_evaluate_features_raises_without_regime_clf -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Append `_compute_shap_values` and `evaluate_features` to `backend/src/agent/tools.py`**

```python
def _compute_shap_values(clf: OilRegimeClassifier, X: pd.DataFrame) -> np.ndarray:
    from tabpfn_extensions import interpretability

    explainer = interpretability.TabPFNExplainer(clf.estimators_[0])
    return explainer.shap_values(X)  # shape: (n_samples, n_features, n_classes)


@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "top_n": {
                "type": "integer",
                "description": "Number of top features to return by SHAP importance. Default 10.",
                "default": 10,
            }
        },
        "required": [],
    }
)
def evaluate_features(top_n: int = 10, context: AgentContext | None = None) -> dict[str, Any]:
    """Compute SHAP feature importances using the fitted regime classifier."""
    if context is None or context._regime_clf is None or context._regime_X_test is None:
        raise ValueError(
            "No fitted regime classifier in context. Call run_tabpfn(task='regime') first."
        )

    shap_vals = _compute_shap_values(context._regime_clf, context._regime_X_test)
    # shap_vals shape: (n_samples, n_features, n_classes)
    importance = np.abs(shap_vals).mean(axis=(0, 2))

    feature_names = list(context._regime_X_test.columns)
    ranked = sorted(zip(feature_names, importance.tolist()), key=lambda x: x[1], reverse=True)

    top = [{"name": name, "importance": round(imp, 4)} for name, imp in ranked[:top_n]]

    context.shap_result = {
        "top_features": top,
        "n_features_evaluated": len(feature_names),
    }
    return context.shap_result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_evaluate_features_returns_ranked_top_features tests/test_deferred_tools.py::test_evaluate_features_raises_without_regime_clf -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/tools.py backend/tests/test_deferred_tools.py
git commit -m "feat: add evaluate_features tool with SHAP via tabpfn-extensions"
```

---

## Task 7: `fetch_geopolitical_risk` tool

**Files:**
- Modify: `backend/src/agent/tools.py` (add import + tool)
- Modify: `backend/tests/test_deferred_tools.py` (append GPR tool tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_deferred_tools.py`:

```python
# ── fetch_geopolitical_risk ────────────────────────────────────────────────────

from src.agent.tools import fetch_geopolitical_risk  # noqa: E402


def test_fetch_geopolitical_risk_populates_signals(ctx):
    dates = pd.date_range("2022-01-01", periods=10, freq="D")
    fake_gpr = pd.Series(range(10), index=dates, name="GPR", dtype=float)

    with patch("src.agent.tools.fetch_gpr_series", return_value=fake_gpr):
        result = fetch_geopolitical_risk(context=ctx)

    assert "GPR" in ctx.signals
    assert len(ctx.signals["GPR"]) == 10
    assert result["fetched"]["GPR"] == 10


def test_fetch_geopolitical_risk_writes_data_manifest(ctx):
    dates = pd.date_range("2022-01-01", periods=10, freq="D")
    fake_gpr = pd.Series(range(10), index=dates, name="GPR", dtype=float)

    with patch("src.agent.tools.fetch_gpr_series", return_value=fake_gpr):
        fetch_geopolitical_risk(context=ctx)

    entry = ctx.data_manifest["data_sources"]["GPR"]
    assert entry["rows"] == 10
    assert entry["provider"] == "matteoiacoviello.com"
    assert entry["start"] == ctx.date_range_start
    assert entry["end"] == ctx.date_range_end
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_fetch_geopolitical_risk_populates_signals tests/test_deferred_tools.py::test_fetch_geopolitical_risk_writes_data_manifest -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Add import and tool to `backend/src/agent/tools.py`**

Add to the imports block at the top of `tools.py` (after `from src.data.connectors import ...`):

```python
from src.data.gpr import fetch_gpr_series
```

Append the tool at the end of `tools.py`:

```python
@registry.tool(
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    }
)
def fetch_geopolitical_risk(context: AgentContext) -> dict[str, Any]:
    """Fetch the Geopolitical Risk (GPR) index and add it to context signals."""
    series = fetch_gpr_series(context.date_range_start, context.date_range_end)
    context.signals["GPR"] = series
    context.data_manifest.setdefault("data_sources", {})["GPR"] = {
        "rows": len(series),
        "start": context.date_range_start,
        "end": context.date_range_end,
        "provider": "matteoiacoviello.com",
    }
    return {"fetched": {"GPR": len(series)}}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_fetch_geopolitical_risk_populates_signals tests/test_deferred_tools.py::test_fetch_geopolitical_risk_writes_data_manifest -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/tools.py backend/tests/test_deferred_tools.py
git commit -m "feat: add fetch_geopolitical_risk tool"
```

---

## Task 8: `backtest` tool wrapper

**Files:**
- Modify: `backend/src/agent/tools.py` (add import + tool)
- Modify: `backend/tests/test_deferred_tools.py` (append backtest tool tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_deferred_tools.py`:

```python
# ── backtest tool wrapper ──────────────────────────────────────────────────────

from src.agent.tools import backtest  # noqa: E402


def test_backtest_tool_stores_result_in_context(ctx):
    n = 50
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    ctx.features = pd.DataFrame(
        np.random.randn(n, 3), index=dates, columns=["f1", "f2", "f3"]
    )
    ctx.signals["CL=F"] = pd.Series(np.linspace(70, 80, n), index=dates, name="CL=F")
    ctx.signals["SPY"] = pd.Series(np.linspace(400, 450, n), index=dates, name="SPY")

    fake_result = {
        "regime_accuracy": 0.71,
        "strategy_sharpe": 1.43,
        "benchmark_sharpe": 0.89,
        "n_windows": 5,
        "date_range": ["2022-01-01", "2022-03-31"],
    }

    with patch("src.eval.backtest.walk_forward_backtest", return_value=fake_result):
        result = backtest(horizon=20, step=20, context=ctx)

    assert ctx.backtest_result == fake_result
    assert result == fake_result


def test_backtest_tool_raises_without_features(ctx):
    with pytest.raises(ValueError, match="engineer_features"):
        backtest(context=ctx)


def test_backtest_tool_raises_without_spy(ctx):
    n = 50
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    ctx.features = pd.DataFrame(np.random.randn(n, 2), index=dates, columns=["f1", "f2"])
    ctx.signals["CL=F"] = pd.Series(np.linspace(70, 80, n), index=dates, name="CL=F")

    with pytest.raises(ValueError, match="SPY"):
        backtest(context=ctx)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_backtest_tool_stores_result_in_context tests/test_deferred_tools.py::test_backtest_tool_raises_without_features tests/test_deferred_tools.py::test_backtest_tool_raises_without_spy -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Append the `backtest` tool to `backend/src/agent/tools.py`**

> **Note:** Do NOT add `from src.eval.backtest import walk_forward_backtest` at module level.
> `backtest.py` imports `_make_regime_labels` / `_make_direction_labels` from `tools.py`, so a
> module-level cross-import would be circular. Use a lazy import inside the function instead.
> The test patches `src.eval.backtest.walk_forward_backtest` (the source module), which works
> because Python's import cache is patched before the lazy import resolves.

Append the tool at the end of `tools.py`:

```python
@registry.tool(
    parameters={
        "type": "object",
        "properties": {
            "horizon": {
                "type": "integer",
                "description": "Forward-return horizon in trading days. Default 20.",
                "default": 20,
            },
            "step": {
                "type": "integer",
                "description": "Walk-forward step size in days. Default 20.",
                "default": 20,
            },
        },
        "required": [],
    }
)
def backtest(horizon: int = 20, step: int = 20, context: AgentContext | None = None) -> dict[str, Any]:
    """Walk-forward backtest: regime accuracy + direction strategy Sharpe vs SPY buy-and-hold."""
    if context is None or context.features is None:
        raise ValueError("No features in context. Call engineer_features first.")
    if "CL=F" not in context.signals:
        raise ValueError("WTI signal ('CL=F') not found. Call fetch_data first.")
    if "SPY" not in context.signals:
        raise ValueError("SPY signal not found. Call fetch_data with tickers=['CL=F', ..., 'SPY'].")

    from src.eval.backtest import walk_forward_backtest as _wfb

    result = _wfb(
        features=context.features.dropna(),
        wti=context.signals["CL=F"],
        spy=context.signals["SPY"],
        horizon=horizon,
        step=step,
    )
    context.backtest_result = result
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py::test_backtest_tool_stores_result_in_context tests/test_deferred_tools.py::test_backtest_tool_raises_without_features tests/test_deferred_tools.py::test_backtest_tool_raises_without_spy -v
```

Expected: 3 PASSED

- [ ] **Step 5: Run all deferred tool tests**

```bash
cd backend && uv run pytest tests/test_deferred_tools.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/src/agent/tools.py backend/tests/test_deferred_tools.py
git commit -m "feat: add backtest tool wrapper"
```

---

## Task 9: Update `loop.py` system prompt and `run.result`

**Files:**
- Modify: `backend/src/agent/loop.py` (lines 21–36 for `SYSTEM_PROMPT`, lines 169–174 for `run.result`)

- [ ] **Step 1: Replace the `SYSTEM_PROMPT` constant in `loop.py`**

Replace the `SYSTEM_PROMPT` assignment (lines 21–36):

```python
SYSTEM_PROMPT = (
    "You are an oil market intelligence analyst. You have access to tools "
    "to fetch market data, engineer features, run TabPFN classification, and explain "
    "predictions.\n\n"
    "Given a date range and analysis tasks, use the tools in this order:\n"
    "1. fetch_data — pull WTI (CL=F), DXY (DX-Y.NYB), XLE, SPY price series and INDPRO macro "
    "data\n"
    "2. fetch_geopolitical_risk — add GPR index to signals\n"
    "3. engineer_features — featurize with windows [5, 20, 60] and lags [1, 5, 20]\n"
    "4. detect_drift — check if recent feature distributions have shifted\n"
    "5. run_tabpfn with task='regime' — classify the current oil market regime\n"
    "6. run_tabpfn with task='direction' — predict WTI price direction over the next 20 trading "
    "days\n"
    "7. evaluate_features — compute SHAP feature importances from the regime classifier\n"
    "8. backtest — walk-forward regime accuracy + direction strategy Sharpe vs SPY\n"
    "9. explain_prediction — pass the regime, direction, confidence, and top feature names from "
    "evaluate_features\n\n"
    "After calling explain_prediction, write a concise natural language summary (3-5 sentences) "
    "grounded in the actual confidence scores and feature values returned by the tools."
)
```

- [ ] **Step 2: Extend `run.result` in `loop.py`**

Replace the `run.result` assignment block inside `run_agent_loop` (currently lines 169–174):

```python
                run.result = {
                    "regime": context.regime_result,
                    "direction": context.direction_result,
                    "summary": last_text,
                    "usage": usage,
                }
```

With:

```python
                run.result = {
                    "regime": context.regime_result,
                    "direction": context.direction_result,
                    "drift": context.drift_result,
                    "feature_importance": context.shap_result,
                    "backtest": context.backtest_result,
                    "summary": last_text,
                    "usage": usage,
                    "data_manifest": context.data_manifest,
                }
```

- [ ] **Step 3: Run the agent loop tests to confirm no regressions**

```bash
cd backend && uv run pytest tests/test_agent_loop.py -v
```

Expected: all existing tests PASS

- [ ] **Step 4: Run the full test suite**

```bash
cd backend && uv run pytest -q
```

Expected: all tests pass, no failures

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/loop.py
git commit -m "feat: extend loop system prompt to 9 steps, persist all session-5 fields in run.result"
```

---

## Final verification

- [ ] **Run the complete test suite one final time**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass

- [ ] **Run linting**

```bash
cd backend && uv run ruff check . && uv run mypy src/ --ignore-missing-imports
```

Expected: no errors
